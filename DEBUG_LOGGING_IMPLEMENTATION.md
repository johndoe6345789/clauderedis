# Debug Logging Implementation - Complete ✅

## Summary

Debug logging has been successfully added to the cache server to provide visibility into:
- Cache key generation (project context, user text, hash calculation)
- Cache lookups (hits vs misses)
- Cache writes (serialization, TTL, storage)
- Cache inspection (three new debug endpoints)

All changes deployed and running.

## Files Modified

### `/Users/rmac/Documents/claude_cache/claude_cache_server.py`

#### 1. Cache Key Generation Logging (lines 115-162)

Added detailed logging to `get_cache_key()`:

```
[CACHE_KEY] Input: project_context='' (len=0)
[CACHE_KEY] Extracted user_text: 'hi' (len=2)
[CACHE_KEY] Key material: ':hi'
[CACHE_KEY] Generated hash: 28c614c9fb372293...
```

This reveals:
- Whether `x-claude-project` header is being passed
- What user text is extracted (detects whitespace issues)
- What key material is being hashed
- The final cache key hash

#### 2. Cache Lookup Logging (lines 305-352)

Added logging to messages endpoint:

```
[REQUEST] x-claude-project header: '' (len=0)
[CACHE] Full cache key: claude:resp:28c614c9fb372293...
⚡ Cache hit: claude:resp:28c614c9fb372293...
```

or

```
❌ Cache miss: No user message found, skipping cache
```

#### 3. Cache Write Logging (lines 443-457)

Added logging when storing responses:

```
[CACHE_WRITE] Caching response with key: claude:resp:28c614c9fb372293...
[CACHE_WRITE] Data size: 1234 bytes, TTL: 86400s
✅ Cached response: claude:resp:28c614c9fb372293...
```

#### 4. New Debug Endpoints (lines 549-603)

Three new endpoints for cache inspection:

**GET /debug/cache/keys** - List all cache entries
```bash
curl http://localhost:8000/debug/cache/keys
```

Returns:
```json
{
  "count": 1,
  "keys": [
    {
      "key": "claude:resp:28c614c9fb372293...",
      "ttl": 86398,
      "size": 1234,
      "preview": "{\n  \"id\": \"msg_...\",\n  \"type\": \"message\",\n  \"role\": \"assistant\",\n..."
    }
  ]
}
```

**POST /debug/cache/flush** - Clear cache (requires confirmation)
```bash
curl -X POST "http://localhost:8000/debug/cache/flush?confirm=yes"
```

Returns:
```json
{"deleted": 4, "remaining": 0}
```

**GET /debug/cache/stats** - Cache statistics
```bash
curl http://localhost:8000/debug/cache/stats
```

Returns:
```json
{
  "total_keys": 1,
  "cache_keys": 1,
  "memory_used": "1.45M",
  "uptime_seconds": 3600
}
```

## Deployment Status

✅ Code changes implemented and tested
✅ Container restarted with new code
✅ Debug endpoints verified working
✅ Cache flushed (clean slate for testing)

## Testing Instructions

### Step 1: Watch Cache Debug Logs

```bash
docker logs claude-cache-server -f | grep -E "\[CACHE|\[REQUEST|Cache hit|Cache miss"
```

### Step 2: Send Test Request

In another terminal:

```bash
ANTHROPIC_BASE_URL=http://localhost:8000 claude
# Type: hi
# Press Enter
```

### Step 3: Verify Logs Show Cache Key Generation

Expected output in log tail:
```
[REQUEST] x-claude-project header: '' (len=0)
[CACHE_KEY] Input: project_context='' (len=0)
[CACHE_KEY] Extracted user_text: 'hi' (len=2)
[CACHE_KEY] Key material: ':hi'
[CACHE_KEY] Generated hash: 28c614c9fb372293...
[CACHE] Full cache key: claude:resp:28c614c9fb372293...
❌ Cache miss: claude:resp:28c614c9fb372293...
[CACHE_WRITE] Caching response with key: claude:resp:28c614c9fb372293...
✅ Cached response: claude:resp:28c614c9fb372293...
```

### Step 4: Verify Cache Key Consistency

Send another "hi" request:

Expected output:
```
[CACHE_KEY] Generated hash: 28c614c9fb372293...  # SAME HASH
⚡ Cache hit: claude:resp:28c614c9fb372293...
```

### Step 5: Inspect Cache Contents

```bash
curl http://localhost:8000/debug/cache/keys | jq '.keys[0].key'
# Should output: "claude:resp:28c614c9fb372293..."

curl http://localhost:8000/debug/cache/stats
# Should show cache_keys: 1
```

## Key Debugging Insights

The debug logs will help identify:

1. **Project Context Issue**: If `x-claude-project` header has inconsistent values
   - Empty string in one request
   - Non-empty in another
   - This would generate different cache keys

2. **User Text Extraction**: If different text is being extracted
   - Leading/trailing whitespace differences
   - Content block handling differences

3. **Hash Consistency**: If the same key material generates different hashes
   - Would indicate encoding issues

4. **Cache Hit Rate**: Track if subsequent "hi" requests result in hits or misses

## Expected Behavior After Fix

Once the issue is resolved, typing "hi" multiple times should:
1. Generate the same cache key each time: `hash(":hi")`
2. Miss once (first request), then hit on subsequent requests
3. Return identical responses (same MetaBuilder greeting)

## Current Cache State

```
✅ Cache: Empty (4 keys flushed)
✅ Debug Endpoints: Available
✅ Logging: Active and detailed
✅ Container: Running with new code
```

## Next Steps

1. **Test with "hi" input**: Verify single cache key is generated
2. **Monitor logs**: Look for different project_context or key material values
3. **Verify consistency**: Confirm identical responses for identical queries
4. **Identify root cause**: Debug logs will reveal what's causing different cache keys

## Log Filtering Commands

To monitor cache activity in real-time:

```bash
# Watch all cache operations
docker logs claude-cache-server -f | grep -E "\[CACHE|\[REQUEST"

# Watch only cache hits
docker logs claude-cache-server -f | grep "⚡ Cache hit"

# Watch only cache misses
docker logs claude-cache-server -f | grep "❌ Cache miss"

# Watch cache key generation
docker logs claude-cache-server -f | grep "\[CACHE_KEY\]"

# Watch cache writes
docker logs claude-cache-server -f | grep "\[CACHE_WRITE\]"
```

## Configuration

Debug endpoints use the same Redis instance:
- Host: `redis` (Docker network)
- Port: `6379`
- Cache TTL: `86400` seconds (24 hours)
- Cache key prefix: `claude:resp:`

All debug operations are non-destructive reads except `/debug/cache/flush` which requires explicit `?confirm=yes` confirmation.
