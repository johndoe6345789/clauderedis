# Testing the Debug Logging Implementation

This guide walks you through testing the new debug logging in the cache server.

## Pre-Test Checklist

- [ ] Cache server is running: `docker ps | grep cache`
- [ ] Redis is running: `docker ps | grep redis`
- [ ] Cache is empty: `curl http://localhost:8000/debug/cache/stats`

If cache has keys, flush first:
```bash
curl -X POST "http://localhost:8000/debug/cache/flush?confirm=yes"
```

## Test Procedure

### Terminal 1: Watch Cache Logs

Start monitoring cache operations:

```bash
docker logs claude-cache-server -f | grep -E "\[CACHE\]|\[REQUEST\]|\[CACHE_KEY\]|\[CACHE_WRITE\]|⚡|❌|✅"
```

You should see:
```
INFO:claude_cache_server:[REQUEST] x-claude-project header: '' (len=0)
INFO:claude_cache_server:[CACHE_KEY] Input: project_context='' (len=0)
INFO:claude_cache_server:[CACHE_KEY] Extracted user_text: 'hi' (len=2)
INFO:claude_cache_server:[CACHE_KEY] Key material: ':hi'
INFO:claude_cache_server:[CACHE_KEY] Generated hash: 28c614c9...
INFO:claude_cache_server:[CACHE] Full cache key: claude:resp:28c614c9...
INFO:claude_cache_server:❌ Cache miss: claude:resp:28c614c9...
INFO:claude_cache_server:[CACHE_WRITE] Caching response with key: claude:resp:28c614c9...
INFO:claude_cache_server:[CACHE_WRITE] Data size: 1234 bytes, TTL: 86400s
INFO:claude_cache_server:✅ Cached response: claude:resp:28c614c9...
```

### Terminal 2: Send First "hi" Request

```bash
ANTHROPIC_BASE_URL=http://localhost:8000 claude
# Type: hi
# Press Enter
# Observe response
# Type: exit or Ctrl+D
```

Expected in Terminal 1 logs:
- `[REQUEST]` header logged
- `[CACHE_KEY]` generation details logged
- `❌ Cache miss` shown
- `[CACHE_WRITE]` indicates response being cached
- `✅ Cached response` confirms successful write

### Terminal 2: Send Second "hi" Request

```bash
ANTHROPIC_BASE_URL=http://localhost:8000 claude
# Type: hi
# Press Enter
# Should get identical response immediately
# Type: exit or Ctrl+D
```

Expected in Terminal 1 logs:
- Same `[REQUEST]` header value (empty string)
- Same `[CACHE_KEY]` generated hash (28c614c9...)
- **⚡ Cache hit** shown (THIS IS SUCCESS!)
- No `[CACHE_WRITE]` (because it was a hit)

### Terminal 2: Check Cache Contents

```bash
curl http://localhost:8000/debug/cache/keys | jq .
```

Expected output:
```json
{
  "count": 1,
  "keys": [
    {
      "key": "claude:resp:28c614c9fb372293...",
      "ttl": 86395,
      "size": 1245,
      "preview": "{\n  \"id\": \"msg_0...\",\n  \"type\": \"message\",\n  \"role\": \"assistant\",..."
    }
  ]
}
```

**Key observations:**
- `count: 1` - Only ONE cache key for "hi"
- `ttl` decreasing - Cache entry is aging normally
- `size` is consistent - Same response cached

## Success Criteria

✅ **Test Passes If:**

1. First "hi" shows `❌ Cache miss` and `✅ Cached response`
2. Second "hi" shows `⚡ Cache hit`
3. Both requests show same generated hash: `28c614c9...`
4. Both requests show same project_context: `''` (empty)
5. Cache keys endpoint shows exactly 1 key
6. Both responses are identical

❌ **Test Fails If:**

1. Different hashes generated for same input
   - Indicates project_context is changing
   - Or user text is being extracted differently

2. Cache hit doesn't occur on second request
   - Indicates Redis issue or cache key mismatch
   - Or cache was invalidated

3. Multiple cache keys created for single prompt
   - Look for different project_context values in logs
   - Check for whitespace differences in user_text

## Interpreting the Logs

### Cache Hit Log (SUCCESS)
```
[REQUEST] x-claude-project header: '' (len=0)
[CACHE_KEY] Generated hash: 28c614c9...
⚡ Cache hit: claude:resp:28c614c9...
```
→ Request found matching cached response instantly

### Cache Miss Log (EXPECTED FIRST TIME)
```
[REQUEST] x-claude-project header: '' (len=0)
[CACHE_KEY] Generated hash: 28c614c9...
❌ Cache miss: claude:resp:28c614c9...
[CACHE_WRITE] Caching response with key: claude:resp:28c614c9...
✅ Cached response: claude:resp:28c614c9...
```
→ No cached response found, fetched from Claude, then cached

### Inconsistent Hash Log (PROBLEM!)
```
Request 1: [CACHE_KEY] Generated hash: 28c614c9...
Request 2: [CACHE_KEY] Generated hash: 03b659fb...
```
→ Different hashes = different cache keys = different responses
→ Check project_context values in REQUEST lines

## Debugging Commands

### View all cache keys
```bash
curl http://localhost:8000/debug/cache/keys | jq .keys[].key
```

### View cache statistics
```bash
curl http://localhost:8000/debug/cache/stats | jq .
```

### Clear cache for fresh test
```bash
curl -X POST "http://localhost:8000/debug/cache/flush?confirm=yes"
```

### Watch just cache hits
```bash
docker logs claude-cache-server -f | grep "⚡ Cache hit"
```

### Watch just cache misses
```bash
docker logs claude-cache-server -f | grep "❌ Cache miss"
```

### See detailed key generation
```bash
docker logs claude-cache-server -f | grep "\[CACHE_KEY\]"
```

## Next Steps

1. **If test passes (cache hits on second "hi"):**
   - Issue is RESOLVED! ✅
   - Both "hi" prompts now return identical cached responses

2. **If different hashes appear:**
   - Project context is inconsistent
   - Look for what's changing the `x-claude-project` header
   - Check Claude Code plugin configuration

3. **If cache hit doesn't occur:**
   - Check Redis connection: `docker logs redis --tail 5`
   - Verify key exists: `curl http://localhost:8000/debug/cache/keys`
   - Check if key was invalidated in cache write logic

## Expected Full Log Example

```bash
# First "hi" request
[REQUEST] x-claude-project header: '' (len=0)
[CACHE_KEY] Input: project_context='' (len=0)
[CACHE_KEY] Extracted user_text: 'hi' (len=2)
[CACHE_KEY] Key material: ':hi'
[CACHE_KEY] Generated hash: 28c614c9fb372293e5b5c51fb6aed2819c0e8e1f...
[CACHE] Full cache key: claude:resp:28c614c9fb372293e5b5c51fb6aed2819c0e8e1f...
❌ Cache miss: claude:resp:28c614c9fb372293e5b5c51fb6aed2819c0e8e1f...
[CACHE_WRITE] Caching response with key: claude:resp:28c614c9fb372293e5b5c51fb6aed2819c0e8e1f...
[CACHE_WRITE] Data size: 1245 bytes, TTL: 86400s
✅ Cached response: claude:resp:28c614c9fb372293e5b5c51fb6aed2819c0e8e1f...

# Second "hi" request
[REQUEST] x-claude-project header: '' (len=0)
[CACHE_KEY] Input: project_context='' (len=0)
[CACHE_KEY] Extracted user_text: 'hi' (len=2)
[CACHE_KEY] Key material: ':hi'
[CACHE_KEY] Generated hash: 28c614c9fb372293e5b5c51fb6aed2819c0e8e1f...
[CACHE] Full cache key: claude:resp:28c614c9fb372293e5b5c51fb6aed2819c0e8e1f...
⚡ Cache hit: claude:resp:28c614c9fb372293e5b5c51fb6aed2819c0e8e1f...
```

This demonstrates identical cache key generation and successful cache hit!
