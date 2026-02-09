import os
import json
import time
import asyncio
import hashlib
import logging
import re
from typing import Dict, Any, Optional, Callable
from contextlib import asynccontextmanager

import redis
import httpx
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------
# Configuration
# -----------------------------

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "7379"))
REDIS_CONNECT_TIMEOUT = int(os.getenv("REDIS_CONNECT_TIMEOUT", "5"))
CACHE_TTL  = int(os.getenv("CACHE_TTL", "86400"))  # 24h
LOCK_TTL   = 60

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_VERSION = "2023-06-01"
CONNECT_TIMEOUT = float(os.getenv("CONNECT_TIMEOUT", "10.0"))
READ_TIMEOUT = float(os.getenv("READ_TIMEOUT", "300.0"))  # 5 min for streaming responses

# Global httpx client with connection pooling
http_client: Optional[httpx.AsyncClient] = None

# Redis client with connection pooling
redis_client: Optional[redis.Redis] = None

async def init_http_client():
    global http_client
    limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
    http_client = httpx.AsyncClient(
        limits=limits,
        timeout=httpx.Timeout(
            CONNECT_TIMEOUT,
            read=READ_TIMEOUT,
            write=10.0,
            pool=5.0  # Timeout waiting for connection from pool
        ),
        http2=False,  # Use HTTP/1.1 for better compatibility
    )
    logger.info("HTTP client initialized")

async def init_redis():
    global redis_client
    try:
        redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True,
            socket_connect_timeout=REDIS_CONNECT_TIMEOUT,
            socket_keepalive=True,
            health_check_interval=30,
        )
        redis_client.ping()
        logger.info(f"Redis connected: {REDIS_HOST}:{REDIS_PORT}")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_http_client()
    await init_redis()
    yield
    # Shutdown
    if http_client:
        await http_client.aclose()
    logger.info("Shutdown complete")

app = FastAPI(lifespan=lifespan)

# Middleware to detect hanging requests
class TimeoutMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            # Add a hard timeout for all requests
            response = await asyncio.wait_for(
                call_next(request),
                timeout=READ_TIMEOUT + CONNECT_TIMEOUT + 10  # Hard timeout with buffer
            )
            return response
        except asyncio.TimeoutError:
            logger.error(f"Request timeout: {request.method} {request.url.path}")
            return JSONResponse(
                status_code=504,
                content={"error": {"type": "timeout", "message": "Request timed out"}}
            )
        except Exception as e:
            logger.error(f"Middleware error: {type(e).__name__}: {e}")
            return JSONResponse(
                status_code=500,
                content={"error": {"type": "internal_error", "message": str(e)}}
            )

app.add_middleware(TimeoutMiddleware)

# -----------------------------
# Utilities
# -----------------------------

def strip_system_reminders(text: str) -> str:
    """Remove <system-reminder>...</system-reminder> blocks from text."""
    # Pattern matches <system-reminder>...</system-reminder> including nested tags
    pattern = r'<system-reminder>.*?</system-reminder>'
    cleaned = re.sub(pattern, '', text, flags=re.DOTALL)
    # Remove extra whitespace that may be left behind
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def normalize_text(text: str) -> str:
    """Normalize text for consistent cache hashing: lowercase and normalize whitespace."""
    # Lowercase for case-insensitive matching
    normalized = text.lower()
    # Normalize whitespace (multiple spaces/tabs/newlines → single space)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


def get_cache_key(body: Dict[str, Any], project_context: str = "") -> Optional[str]:
    """
    Stateless cache key = project + last user prompt only.
    Ignores conversation history for maximum cache hit rate.

    This means:
    - Same prompt in same project → Cache hit
    - Same prompt in different project → Different cache (new key)
    - Same prompt later in conversation → Cache hit (history ignored)

    Trade-off: Context-dependent prompts like "fix it" won't have conversation context,
    but cache effectiveness is dramatically improved.
    """
    logger.info(f"[CACHE_KEY] Input: project_context='{project_context}' (len={len(project_context)})")

    messages = body.get("messages", [])
    if not messages:
        logger.info(f"[CACHE_KEY] No messages found")
        return None

    # Get ONLY the last user message
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")

            # Handle string content
            if isinstance(content, str):
                user_text = strip_system_reminders(content)
            # Handle content blocks (list of dicts)
            elif isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        block_text = block.get("text", "")
                        # Filter system-reminders from each block
                        cleaned_text = strip_system_reminders(block_text)
                        if cleaned_text:  # Only add non-empty cleaned text
                            text_parts.append(cleaned_text)
                user_text = " ".join(text_parts)
            else:
                continue

            if user_text:
                logger.info(f"[CACHE_KEY] Extracted user_text: '{user_text[:100]}...' (len={len(user_text)})")
                # Normalize text before hashing for consistent cache keys
                normalized_text = normalize_text(user_text)
                logger.info(f"[CACHE_KEY] Normalized user_text: '{normalized_text[:100]}...' (len={len(normalized_text)})")
                # Simple key: project + prompt
                key_material = f"{project_context}:{normalized_text}"
                logger.info(f"[CACHE_KEY] Key material: '{key_material[:150]}...'")
                cache_hash = hashlib.sha256(key_material.encode("utf-8")).hexdigest()
                logger.info(f"[CACHE_KEY] Generated hash: {cache_hash}")
                return cache_hash

    return None


async def wait_for_cache(key: str, timeout: float = 2.0):
    """
    Wait briefly for another in-flight request to populate cache.
    """
    start = time.time()
    while time.time() - start < timeout:
        try:
            cached = redis_client.get(key)
            if cached:
                logger.debug(f"Cache populated: {key}")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Redis error while waiting for cache: {e}")
            break
        await asyncio.sleep(0.05)
    return None


def is_low_quality_response(data: dict) -> tuple[bool, str]:
    """
    Detect low-quality responses that shouldn't be cached.
    Returns (is_low_quality, reason).
    """
    if not isinstance(data, dict):
        return False, ""

    # Check 1: Minimum token threshold
    output_tokens = data.get("usage", {}).get("output_tokens", 0)
    if output_tokens < 20:
        return True, f"too few tokens ({output_tokens} < 20)"

    # Check 2: Detect JSON-only responses
    content = data.get("content", [])
    if isinstance(content, list) and len(content) > 0:
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "").strip()

                # Check if response is pure JSON
                if text.startswith("{") and text.endswith("}"):
                    try:
                        parsed = json.loads(text)
                        # If it's valid JSON with metadata-like keys, reject it
                        if isinstance(parsed, dict):
                            metadata_keys = {"isNewTopic", "title", "type", "status"}
                            if any(key in parsed for key in metadata_keys):
                                return True, "response is JSON metadata, not conversational"
                    except json.JSONDecodeError:
                        pass

    return False, ""


def extract_claude_headers(req: Request) -> Dict[str, str]:
    headers = {
        "content-type": "application/json",
        "anthropic-version": CLAUDE_VERSION,
    }

    # Accept BOTH auth styles
    if "x-api-key" in req.headers:
        headers["x-api-key"] = req.headers["x-api-key"]
    elif "authorization" in req.headers:
        headers["authorization"] = req.headers["authorization"]
    else:
        logger.warning("Request missing API key")
        raise HTTPException(status_code=401, detail="Missing API key")

    # Forward beta headers if present
    if "anthropic-beta" in req.headers:
        headers["anthropic-beta"] = req.headers["anthropic-beta"]

    return headers

async def call_claude_api(url: str, headers: Dict[str, str], body: Dict[str, Any]) -> httpx.Response:
    """
    Call Claude API with timeout detection.
    """
    try:
        logger.debug(f"Calling Claude API: {url}")
        response = await asyncio.wait_for(
            http_client.post(url, headers=headers, json=body),
            timeout=READ_TIMEOUT + CONNECT_TIMEOUT + 5  # Hard timeout as safety net
        )
        logger.info(f"Claude API response: status={response.status_code}")
        return response
    except asyncio.TimeoutError:
        logger.error(f"Hard timeout: request exceeded {READ_TIMEOUT + CONNECT_TIMEOUT + 5}s")
        raise HTTPException(
            status_code=504,
            detail={"type": "timeout", "message": "Claude API request timed out"}
        )
    except httpx.TimeoutException as e:
        logger.error(f"Request timeout: {e}")
        raise HTTPException(
            status_code=504,
            detail={"type": "timeout", "message": "Claude API request timed out"}
        )
    except (httpx.ConnectError, httpx.RemoteProtocolError) as e:
        logger.error(f"Connection error: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=503,
            detail={"type": "connection_error", "message": "Cannot reach Claude API"}
        )
    except httpx.ReadError as e:
        logger.error(f"Read error: {e}")
        raise HTTPException(
            status_code=502,
            detail={"type": "read_error", "message": "Error reading API response"}
        )
    except Exception as e:
        logger.error(f"Unexpected error: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=503,
            detail={"type": "unknown_error", "message": "Claude API call failed"}
        )

# -----------------------------
# Claude-compatible endpoint
# -----------------------------

def parse_sse_stream(content: bytes) -> Optional[Dict[str, Any]]:
    """
    Parse server-sent events stream and reconstruct the final message.
    SSE format: event: <type>\ndata: <json>\n\n
    Returns the reconstructed message object from final message_delta event.
    """
    try:
        lines = content.decode("utf-8").split("\n")
        message_obj = None

        for i, line in enumerate(lines):
            if line.startswith("data: "):
                try:
                    event_data = json.loads(line[6:])  # Remove "data: " prefix

                    if event_data.get("type") == "message_start":
                        message_obj = event_data.get("message", {})
                    elif event_data.get("type") == "message_delta":
                        # Update with delta
                        if "delta" in event_data:
                            delta = event_data["delta"]
                            if "content" in delta and message_obj:
                                if "content" not in message_obj:
                                    message_obj["content"] = []
                                message_obj["content"].extend(delta.get("content", []))
                            if "usage" in delta and message_obj:
                                message_obj["usage"] = delta["usage"]
                    elif event_data.get("type") == "message_stop":
                        # Final message is complete
                        return message_obj
                except (json.JSONDecodeError, KeyError):
                    pass

        return message_obj
    except Exception as e:
        logger.warning(f"Failed to parse SSE stream: {e}")
        return None


@app.post("/v1/messages", response_class=JSONResponse)
async def messages(req: Request):
    try:
        body = await req.json()
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request: {e}")
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON in request body"}
        )

    logger.info(f"Messages request: model={body.get('model')}, messages={len(body.get('messages', []))}")

    is_streaming = body.get("stream", False)

    # Extract project context from headers (Claude Code passes this)
    project_context = req.headers.get("x-claude-project", "")
    logger.info(f"[REQUEST] x-claude-project header: '{project_context}' (len={len(project_context)})")

    cache_key_base = get_cache_key(body, project_context)

    # If we have a cache key, try cache first
    cache_key = None
    if cache_key_base:
        cache_key = f"claude:resp:{cache_key_base}"
        logger.info(f"[CACHE] Full cache key: {cache_key}")
        try:
            cached = redis_client.get(cache_key)
            if cached:
                try:
                    data = json.loads(cached)
                    # Validate cached data
                    is_valid = False
                    if isinstance(data, dict):
                        # Must have id or error
                        if not (data.get("id") or data.get("error")):
                            is_valid = False
                        # Reject incomplete responses
                        elif data.get("content") == [] and data.get("stop_reason") is None:
                            is_valid = False
                        # Reject zero-token responses
                        elif data.get("usage", {}).get("output_tokens", 0) < 1:
                            is_valid = False
                        else:
                            is_valid = True

                    if is_valid:
                        logger.info(f"⚡ Cache hit: {cache_key}")
                        return JSONResponse(data)
                    else:
                        logger.warning(f"Invalid cached data, invalidating: {cache_key}")
                        try:
                            redis_client.delete(cache_key)
                        except:
                            pass
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Corrupted cache entry, invalidating: {e}")
                    redis_client.delete(cache_key)
        except Exception as e:
            logger.warning(f"Redis error during cache lookup: {e}")
            # Continue on Redis failure
    else:
        logger.info("❌ Cache miss: No user message found, skipping cache")

    # 2. Acquire lock for concurrent request deduplication (if caching)
    lock_acquired = True
    if cache_key:
        lock_key = f"claude:lock:{cache_key_base}"
        try:
            lock_acquired = redis_client.set(
                lock_key, "1", nx=True, ex=LOCK_TTL
            )
        except Exception as e:
            logger.warning(f"Redis error during lock acquisition: {e}")
            lock_acquired = True  # Fail open

        if not lock_acquired:
            # Another request is already fetching this
            logger.debug(f"Waiting for concurrent request...")
            cached = await wait_for_cache(cache_key)
            if cached:
                logger.info(f"Got result from concurrent request")
                return JSONResponse(cached)

    # 3. Call Claude API
    try:
        headers = extract_claude_headers(req)
    except HTTPException as e:
        return JSONResponse(status_code=401, content={"error": "Missing API key"})

    try:
        claude_resp = await call_claude_api(CLAUDE_API_URL, headers, body)
    except HTTPException as e:
        # Return the error with proper structure
        return JSONResponse(
            status_code=e.status_code,
            content={"error": e.detail}
        )
    except Exception as e:
        logger.error(f"Unexpected error calling Claude API: {type(e).__name__}: {e}")
        return JSONResponse(
            status_code=503,
            content={"error": "Claude API call failed"}
        )

    # Handle error responses
    if claude_resp.status_code >= 400:
        logger.warning(f"Claude API error: status={claude_resp.status_code}")
        try:
            error_data = claude_resp.json()
            return JSONResponse(error_data, status_code=claude_resp.status_code)
        except (json.JSONDecodeError, ValueError):
            return JSONResponse(
                {"error": f"API error: {claude_resp.status_code}"},
                status_code=claude_resp.status_code
            )

    # Parse response: handle streaming or non-streaming
    data = None
    if is_streaming:
        # Parse SSE stream to reconstruct final message
        logger.debug("Parsing SSE stream response")
        data = parse_sse_stream(claude_resp.content)
        if not data:
            logger.error(f"Failed to parse streaming response")
            raise HTTPException(status_code=502, detail="Invalid streaming response")
    else:
        # Regular JSON response
        try:
            data = claude_resp.json()
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse JSON response: {e}, content: {claude_resp.text[:500]}")
            raise HTTPException(status_code=502, detail="Invalid response from Claude API")

    # 4. Cache the parsed response (if we have a cache key)
    if cache_key:
        should_cache = True
        reason = ""

        if isinstance(data, dict):
            # Must have an id or error
            if not (data.get("id") or data.get("error")):
                should_cache = False
                reason = "no id or error"
            # Reject incomplete responses: empty content with null stop_reason
            elif data.get("content") == [] and data.get("stop_reason") is None:
                should_cache = False
                reason = f"incomplete streaming (empty content, no stop_reason)"
            # Reject responses with suspiciously low token output (likely incomplete)
            elif data.get("usage", {}).get("output_tokens", 0) < 1:
                should_cache = False
                reason = "zero output tokens (incomplete)"
            # Check for low-quality responses (JSON metadata, too few tokens, etc)
            else:
                is_low_quality, quality_reason = is_low_quality_response(data)
                if is_low_quality:
                    should_cache = False
                    reason = f"low quality: {quality_reason}"

        if should_cache:
            try:
                response_data = json.dumps(data, ensure_ascii=False)
                logger.info(f"[CACHE_WRITE] Caching response with key: {cache_key}")
                logger.info(f"[CACHE_WRITE] Data size: {len(response_data)} bytes, TTL: {CACHE_TTL}s")
                redis_client.setex(
                    cache_key,
                    CACHE_TTL,
                    response_data
                )
                logger.info(f"✅ Cached response: {cache_key}")
            except Exception as e:
                logger.warning(f"Failed to cache response: {e}")
        else:
            logger.warning(f"⛔ Skipping cache: {reason}")

    return JSONResponse(data)

@app.post("/v1/messages/count_tokens", response_class=JSONResponse)
async def count_tokens(req: Request):
    try:
        headers = extract_claude_headers(req)
        body = await req.json()
    except HTTPException as e:
        return JSONResponse(status_code=401, content={"error": "Missing API key"})
    except Exception as e:
        logger.error(f"Error in count_tokens request setup: {e}")
        return JSONResponse(status_code=400, content={"error": "Invalid request"})

    try:
        resp = await call_claude_api(
            "https://api.anthropic.com/v1/messages/count_tokens",
            headers,
            body
        )
    except HTTPException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={"error": e.detail}
        )
    except Exception as e:
        logger.error(f"Error calling count_tokens API: {type(e).__name__}: {e}")
        return JSONResponse(status_code=503, content={"error": "Count tokens API failed"})

    # Parse response
    try:
        data = resp.json()
        return JSONResponse(data, status_code=resp.status_code)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Failed to parse count_tokens response: {e}")
        return JSONResponse(
            status_code=502,
            content={"error": "Invalid response from API"}
        )

# -----------------------------
# Health check
# -----------------------------

@app.get("/health")
def health():
    health_status = {"status": "ok"}

    # Check Redis
    try:
        redis_client.ping()
        health_status["redis"] = "ok"
    except Exception as e:
        health_status["redis"] = f"error: {str(e)}"
        health_status["status"] = "degraded"

    return health_status

@app.get("/health/detailed")
def health_detailed():
    """Detailed health check for monitoring."""
    status = {
        "service": "claude-cache-server",
        "version": "1.0",
        "timestamp": time.time(),
        "checks": {}
    }

    # Redis check
    try:
        redis_client.ping()
        status["checks"]["redis"] = {"status": "ok", "host": REDIS_HOST, "port": REDIS_PORT}
    except Exception as e:
        status["checks"]["redis"] = {"status": "error", "message": str(e)}

    # HTTP client check
    status["checks"]["http_client"] = {
        "status": "ok" if http_client else "not_initialized"
    }

    # Overall status
    if all(c.get("status") == "ok" for c in status["checks"].values()):
        status["status"] = "healthy"
    elif any(c.get("status") == "error" for c in status["checks"].values()):
        status["status"] = "unhealthy"
    else:
        status["status"] = "degraded"

    return status


# Debug endpoints for cache inspection

@app.get("/debug/cache/keys")
async def list_cache_keys():
    """List all cache keys with details."""
    try:
        keys = redis_client.keys("claude:resp:*")
        results = []
        for key in keys:
            ttl = redis_client.ttl(key)
            data = redis_client.get(key)
            size = len(data) if data else 0
            preview = data[:200] if data else ""
            results.append({
                "key": key,
                "ttl": ttl,
                "size": size,
                "preview": preview
            })
        return {"count": len(keys), "keys": results}
    except Exception as e:
        logger.error(f"Error listing cache keys: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/debug/cache/flush")
async def flush_cache(confirm: str = ""):
    """Flush all cache keys with confirmation."""
    if confirm != "yes":
        raise HTTPException(status_code=400, detail="Must include ?confirm=yes")

    try:
        before = len(redis_client.keys("*"))
        redis_client.flushall()
        after = len(redis_client.keys("*"))
        logger.info(f"Cache flushed: {before} keys deleted, {after} remaining")
        return {"deleted": before - after, "remaining": after}
    except Exception as e:
        logger.error(f"Error flushing cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/debug/cache/stats")
async def cache_stats():
    """Get cache statistics."""
    try:
        info = redis_client.info()
        return {
            "total_keys": redis_client.dbsize(),
            "cache_keys": len(redis_client.keys("claude:resp:*")),
            "memory_used": info.get("used_memory_human"),
            "uptime_seconds": info.get("uptime_in_seconds")
        }
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

