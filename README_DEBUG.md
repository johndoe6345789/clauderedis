# Debug Logging Implementation - Complete Summary

## What Was Implemented

Debug logging has been added to the Claude cache server to investigate why different cache keys are being generated for the same input ("hi"). The implementation includes:

### 1. **Cache Key Generation Logging**
   - Logs the `x-claude-project` header value and its length
   - Logs the extracted user text and its length
   - Logs the cache key material before hashing
   - Logs the final generated hash

### 2. **Cache Lookup Logging**
   - Logs when a cache lookup is attempted
   - Shows whether it's a cache hit or miss
   - Logs the full cache key being queried

### 3. **Cache Write Logging**
   - Logs when a response is cached
   - Shows data size and TTL
   - Confirms successful cache storage

### 4. **Debug Inspection Endpoints**
   - **GET /debug/cache/keys** - List all cached entries
   - **POST /debug/cache/flush** - Clear cache (safe with confirmation)
   - **GET /debug/cache/stats** - View cache statistics

## Key Insight: The Cache Key Formula

```
cache_key = SHA256(x-claude-project + ":" + last_user_message)
```

This means the cache key depends on:
1. The `x-claude-project` header value
2. The user's last message

If either changes, a different cache key is generated, even for the same input.

## How to Use the Debug Logging

### Watch Logs in Real-Time

```bash
# Terminal 1: Start monitoring
docker logs claude-cache-server -f | grep -E "\[CACHE\]|\[REQUEST\]|⚡|❌|✅"
```

### Send Test Request

```bash
# Terminal 2: Send request
ANTHROPIC_BASE_URL=http://localhost:8000 claude
# Type: hi
# Press Enter
```

### Interpret the Logs

**First "hi" (should be a cache miss):**
```
[REQUEST] x-claude-project header: '' (len=0)
[CACHE_KEY] Input: project_context='' (len=0)
[CACHE_KEY] Extracted user_text: 'hi' (len=2)
[CACHE_KEY] Key material: ':hi'
[CACHE_KEY] Generated hash: 28c614c9...
[CACHE] Full cache key: claude:resp:28c614c9...
❌ Cache miss (generates cache)
✅ Cached response
```

**Second "hi" (should be a cache hit if everything is consistent):**
```
[REQUEST] x-claude-project header: '' (len=0)
[CACHE_KEY] Generated hash: 28c614c9...  ← SAME HASH
[CACHE] Full cache key: claude:resp:28c614c9...
⚡ Cache hit  ← SUCCESS!
```

## What the Debug Logging Will Reveal

### If You See Different Hashes
```
Request 1: [CACHE_KEY] Generated hash: 28c614c9...
Request 2: [CACHE_KEY] Generated hash: 03b659fb...
```
**Problem:** The cache key material is different.

**Check these in the logs:**
- `[REQUEST] x-claude-project header:` - Is it the same?
- `[CACHE_KEY] Key material:` - Is it different?

This is what we're investigating to find the root cause.

### If project_context Differs
```
Request 1: [REQUEST] x-claude-project header: '' (len=0)
Request 2: [REQUEST] x-claude-project header: 'myproject' (len=9)
```
**Problem:** The header is changing between requests.

### If user_text Differs
```
Request 1: [CACHE_KEY] Extracted user_text: 'hi' (len=2)
Request 2: [CACHE_KEY] Extracted user_text: ' hi' (len=3)  ← Whitespace!
```
**Problem:** Extra whitespace or formatting is being added.

## Quick Reference

| Command | Purpose |
|---------|---------|
| `curl http://localhost:8000/debug/cache/keys` | List all cached keys |
| `curl http://localhost:8000/debug/cache/stats` | View cache statistics |
| `curl -X POST "http://localhost:8000/debug/cache/flush?confirm=yes"` | Clear all cache |
| `docker logs cache-server -f \| grep "\[CACHE"` | Watch cache operations |

## File Locations

| File | Purpose |
|------|---------|
| `/Users/rmac/Documents/claude_cache/claude_cache_server.py` | Updated cache server with debug logging |
| `/Users/rmac/Documents/claude_cache/DEBUG_LOGGING_IMPLEMENTATION.md` | Detailed implementation documentation |
| `/Users/rmac/Documents/claude_cache/DEBUG_QUICK_START.md` | Quick reference guide |
| `/Users/rmac/Documents/claude_cache/TESTING_INSTRUCTIONS.md` | Step-by-step testing guide |
| `/Users/rmac/Documents/claude_cache/IMPLEMENTATION_SUMMARY.txt` | Plain text summary |

## Implementation Status

✅ Code modified and deployed  
✅ Debug endpoints created and tested  
✅ Logging activated  
✅ Cache flushed (clean state)  
✅ Container restarted with new code  

## Next Step: Test and Investigate

Run the test procedure in `TESTING_INSTRUCTIONS.md` to:
1. Send "hi" twice
2. Monitor the logs
3. Look for different cache keys
4. Identify what's changing

The debug logs will pinpoint exactly where the issue is!

---

**Note:** The implementation adds detailed logging without changing the caching behavior. All changes are additive and safe to run in production.
