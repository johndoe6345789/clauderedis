import os
import json
import time
import asyncio
import hashlib
from typing import Dict, Any

import redis
import httpx
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse

# -----------------------------
# Configuration
# -----------------------------

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "7379"))
CACHE_TTL  = int(os.getenv("CACHE_TTL", "86400"))  # 24h
LOCK_TTL   = 60

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_VERSION = "2023-06-01"

# -----------------------------
# Init
# -----------------------------

app = FastAPI()
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True
)

# -----------------------------
# Utilities
# -----------------------------

def canonical_hash(body: Dict[str, Any]) -> str:
    """
    Deterministic hash of the Claude request body.
    Order-independent, whitespace-safe.
    """
    canonical = json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def wait_for_cache(key: str, timeout: float = 2.0):
    """
    Wait briefly for another in-flight request to populate cache.
    """
    start = time.time()
    while time.time() - start < timeout:
        cached = redis_client.get(key)
        if cached:
            return json.loads(cached)
        await asyncio.sleep(0.05)
    return None


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
        raise HTTPException(status_code=401, detail="Missing API key")

    # Forward beta headers if present
    if "anthropic-beta" in req.headers:
        headers["anthropic-beta"] = req.headers["anthropic-beta"]

    return headers

# -----------------------------
# Claude-compatible endpoint
# -----------------------------

@app.post("/v1/messages")
async def messages(req: Request):
    body = await req.json()

    cache_key = f"claude:resp:{canonical_hash(body)}"
    lock_key  = f"claude:lock:{cache_key}"

    # 1. Cache hit
    cached = redis_client.get(cache_key)
    if cached:
        return JSONResponse(json.loads(cached))

    # 2. Acquire lock (dogpile protection)
    lock_acquired = redis_client.set(
        lock_key, "1", nx=True, ex=LOCK_TTL
    )

    if not lock_acquired:
        # Another request is already fetching this
        cached = await wait_for_cache(cache_key)
        if cached:
            return JSONResponse(cached)

    # 3. Cache miss → call Claude
    headers = extract_claude_headers(req)

    async with httpx.AsyncClient(timeout=90) as client:
        claude_resp = await client.post(
            CLAUDE_API_URL,
            headers=headers,
            json=body
        )

    if claude_resp.status_code >= 400:
        return Response(
            content=claude_resp.content,
            status_code=claude_resp.status_code,
            media_type="application/json"
        )

    data = claude_resp.json()

    # 4. Store in Redis
    redis_client.setex(
        cache_key,
        CACHE_TTL,
        json.dumps(data, ensure_ascii=False)
    )

    return JSONResponse(data)

@app.post("/v1/messages/count_tokens")
async def count_tokens(req: Request):
    headers = extract_claude_headers(req)
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages/count_tokens",
            headers=headers,
            json=await req.json()
        )
    return JSONResponse(resp.json(), status_code=resp.status_code)

# -----------------------------
# Health check
# -----------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "redis": redis_client.ping()
    }

