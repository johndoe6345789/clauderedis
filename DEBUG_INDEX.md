# Debug Logging Implementation - File Index

## Overview

Complete debug logging implementation for the Claude cache server to identify why different cache keys are generated for the same input.

**Status:** ✅ Complete and Deployed

---

## Documentation Files

### 1. **README_DEBUG.md** (Start Here!)
   - **Purpose:** Quick overview of what was implemented
   - **Content:**
     - What debug logging does
     - The cache key formula
     - How to use the debug features
     - Quick reference commands
   - **Read time:** 5 minutes
   - **Best for:** Getting started quickly

### 2. **TESTING_INSTRUCTIONS.md** (How to Test)
   - **Purpose:** Step-by-step guide to test the implementation
   - **Content:**
     - Pre-test checklist
     - Detailed test procedure with 2 terminals
     - Success criteria
     - How to interpret logs
     - Debugging commands
   - **Read time:** 10 minutes
   - **Best for:** Running actual tests

### 3. **DEBUG_QUICK_START.md** (Cheat Sheet)
   - **Purpose:** Quick reference for common commands
   - **Content:**
     - Quick commands to watch logs
     - Send test requests
     - Check cache contents
     - Expected behavior examples
   - **Read time:** 2 minutes
   - **Best for:** Quick lookups while testing

### 4. **DEBUG_LOGGING_IMPLEMENTATION.md** (Technical Details)
   - **Purpose:** Detailed technical documentation
   - **Content:**
     - What code was modified and where
     - Debug endpoints specification
     - Expected log output examples
     - Current cache state
     - Log filtering commands
   - **Read time:** 15 minutes
   - **Best for:** Understanding implementation details

### 5. **IMPLEMENTATION_SUMMARY.txt** (Plain Text Summary)
   - **Purpose:** Plain text overview of implementation
   - **Content:**
     - Objective and hypothesis
     - Step-by-step what was done
     - Deployment status
     - Root cause hypothesis
     - Next steps
   - **Read time:** 5 minutes
   - **Best for:** Quick reference in terminal

### 6. **DEBUG_INDEX.md** (This File)
   - **Purpose:** Guide to all documentation
   - **Content:** What you're reading now

---

## Code Changes

### File Modified
- **`/Users/rmac/Documents/claude_cache/claude_cache_server.py`**
  - Lines 128-160: Cache key generation logging
  - Lines 307-352: Cache lookup logging
  - Lines 446-453: Cache write logging
  - Lines 551-603: New debug endpoints

---

## Quick Start (5 Minutes)

1. **Read:** README_DEBUG.md
2. **Understand:** The cache key formula and debug endpoints
3. **Test:** Follow TESTING_INSTRUCTIONS.md

---

## Testing Workflow

```
Terminal 1: Watch Logs
├── docker logs claude-cache-server -f | grep -E "\[CACHE\]|\[REQUEST\]|⚡|❌|✅"
└── Ready to see cache operations

Terminal 2: Send Requests
├── ANTHROPIC_BASE_URL=http://localhost:8000 claude
├── Type "hi"
└── Observe cache behavior

Terminal 3: Inspect Cache
├── curl http://localhost:8000/debug/cache/keys | jq .
├── curl http://localhost:8000/debug/cache/stats | jq .
└── Verify single cache key created
```

---

## What You'll See in Logs

### Cache Miss (First "hi" Request)
```
[REQUEST] x-claude-project header: '' (len=0)
[CACHE_KEY] Input: project_context='' (len=0)
[CACHE_KEY] Extracted user_text: 'hi' (len=2)
[CACHE_KEY] Key material: ':hi'
[CACHE_KEY] Generated hash: 28c614c9...
[CACHE] Full cache key: claude:resp:28c614c9...
❌ Cache miss: claude:resp:28c614c9...
[CACHE_WRITE] Caching response with key: claude:resp:28c614c9...
[CACHE_WRITE] Data size: 1245 bytes, TTL: 86400s
✅ Cached response: claude:resp:28c614c9...
```

### Cache Hit (Second "hi" Request)
```
[REQUEST] x-claude-project header: '' (len=0)
[CACHE_KEY] Input: project_context='' (len=0)
[CACHE_KEY] Extracted user_text: 'hi' (len=2)
[CACHE_KEY] Key material: ':hi'
[CACHE_KEY] Generated hash: 28c614c9...
[CACHE] Full cache key: claude:resp:28c614c9...
⚡ Cache hit: claude:resp:28c614c9...
```

---

## Key Debug Endpoints

| Endpoint | Method | Purpose | Command |
|----------|--------|---------|---------|
| `/debug/cache/keys` | GET | List all cached keys | `curl http://localhost:8000/debug/cache/keys \| jq .` |
| `/debug/cache/stats` | GET | Cache statistics | `curl http://localhost:8000/debug/cache/stats \| jq .` |
| `/debug/cache/flush` | POST | Clear cache | `curl -X POST "http://localhost:8000/debug/cache/flush?confirm=yes"` |

---

## Expected Test Results

### ✅ Success (Single Cache Key for "hi")
- First "hi" → Cache miss, writes to cache
- Second "hi" → Cache hit, returns instantly
- Cache keys endpoint shows 1 entry: `28c614c9...`
- Both responses are identical

### ❌ Problem (Different Cache Keys for "hi")
- Different hashes in log output: `28c614c9...` vs `03b659fb...`
- Check `x-claude-project` header values
- Check user text extraction
- Look for whitespace differences

---

## Debug Log Patterns

### To Find Cache Operations
```bash
docker logs claude-cache-server -f | grep "\[CACHE"
```

### To Find Cache Hits
```bash
docker logs claude-cache-server -f | grep "⚡ Cache hit"
```

### To Find Cache Misses
```bash
docker logs claude-cache-server -f | grep "❌ Cache miss"
```

### To Find Key Generation
```bash
docker logs claude-cache-server -f | grep "\[CACHE_KEY\]"
```

---

## Root Cause Investigation

The debug logs will reveal if the issue is:

1. **Inconsistent project_context**
   - Look at `[REQUEST] x-claude-project header:` values
   - If length changes: `(len=0)` vs `(len=9)`, that's the problem

2. **Different user text extraction**
   - Look at `[CACHE_KEY] Extracted user_text:` values
   - If length changes: `'hi' (len=2)` vs `' hi' (len=3)`, that's whitespace

3. **Hash inconsistency**
   - Look at `[CACHE_KEY] Generated hash:` values
   - Same input should always produce same hash

---

## When Things Go Wrong

### No logs appearing?
```bash
# Check container is running
docker ps | grep cache

# Restart container
docker restart claude-cache-server

# Watch logs
docker logs claude-cache-server -f
```

### Redis connection issues?
```bash
# Check Redis is running
docker ps | grep redis

# Test Redis
docker exec redis redis-cli ping
```

### Cache endpoints not responding?
```bash
# Verify endpoint
curl http://localhost:8000/debug/cache/stats

# Check container logs for errors
docker logs claude-cache-server --tail 20
```

---

## Next Steps

1. **Read README_DEBUG.md** - Understand what was implemented
2. **Follow TESTING_INSTRUCTIONS.md** - Run the test
3. **Monitor logs** - Watch for different cache keys
4. **Identify root cause** - Check project_context or user_text differences
5. **Report findings** - Share which value is inconsistent

---

## Implementation Summary

- ✅ Code deployed and running
- ✅ Debug logging active
- ✅ Debug endpoints working
- ✅ Cache flushed (clean state)
- ✅ Container restarted with new code
- ✅ Documentation complete
- ✅ Ready for testing

**Start with:** README_DEBUG.md → TESTING_INSTRUCTIONS.md → Observe logs
