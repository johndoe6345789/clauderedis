# Debug Quick Start Guide

## 1. Watch Cache Logs in Real-time

```bash
docker logs claude-cache-server -f | grep -E "\[CACHE|\[REQUEST|⚡|❌|✅"
```

## 2. Send Test Request

In another terminal:
```bash
ANTHROPIC_BASE_URL=http://localhost:8000 claude
# Type: hi
# Press Enter
# Type: exit
```

## 3. Check Cache Keys

```bash
curl http://localhost:8000/debug/cache/keys | jq .
```

Output shows:
- How many keys are cached
- Full key names
- TTL remaining
- Data size
- Preview of cached content

## 4. Check Cache Stats

```bash
curl http://localhost:8000/debug/cache/stats
```

Output shows:
- Total keys in Redis
- Number of cache keys
- Memory usage
- Uptime

## 5. Flush Cache (Start Fresh)

```bash
curl -X POST "http://localhost:8000/debug/cache/flush?confirm=yes"
```

Returns how many keys were deleted.

## Expected Behavior

### First "hi" Request
```
[REQUEST] x-claude-project header: '' (len=0)
[CACHE_KEY] Input: project_context='' (len=0)
[CACHE_KEY] Extracted user_text: 'hi' (len=2)
[CACHE_KEY] Key material: ':hi'
[CACHE_KEY] Generated hash: 28c614c9...
[CACHE] Full cache key: claude:resp:28c614c9...
❌ Cache miss: claude:resp:28c614c9...
[CACHE_WRITE] Caching response with key: claude:resp:28c614c9...
[CACHE_WRITE] Data size: 1234 bytes, TTL: 86400s
✅ Cached response: claude:resp:28c614c9...
```

### Second "hi" Request (Should be Identical)
```
[REQUEST] x-claude-project header: '' (len=0)
[CACHE_KEY] Input: project_context='' (len=0)
[CACHE_KEY] Extracted user_text: 'hi' (len=2)
[CACHE_KEY] Key material: ':hi'
[CACHE_KEY] Generated hash: 28c614c9...  # SAME
[CACHE] Full cache key: claude:resp:28c614c9...  # SAME
⚡ Cache hit: claude:resp:28c614c9...
```

## Troubleshooting

### Different hashes for same input?
- Check `[CACHE_KEY]` lines for different `key_material` values
- Look at `project_context` length - if it changes, that's the issue
- Check `user_text` - may have whitespace differences

### Cache miss on second request?
- Check if `cache_key` value is changing
- Check Redis is still running: `docker ps | grep redis`
- Check `[CACHE_WRITE]` was logged on first request

### No logs appearing?
- Verify logging is enabled: `docker logs claude-cache-server --tail 5`
- Check container is running: `docker ps | grep cache`
- Restart container: `docker restart claude-cache-server`

## Debug Endpoints Summary

| Endpoint | Method | Purpose | Example |
|----------|--------|---------|---------|
| `/debug/cache/keys` | GET | List all cached keys | `curl http://localhost:8000/debug/cache/keys` |
| `/debug/cache/stats` | GET | Cache statistics | `curl http://localhost:8000/debug/cache/stats` |
| `/debug/cache/flush` | POST | Clear all cache | `curl -X POST "http://localhost:8000/debug/cache/flush?confirm=yes"` |

All endpoints are available locally on `http://localhost:8000`.
