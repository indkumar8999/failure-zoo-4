# API Implementation Status Report

## Summary
The Failure Zoo app has **missing implementations** for network chaos control endpoints. The app endpoints are called through `chaosctl.py`, but some don't exist in `main.py`.

---

## API Implementation Matrix

### ✅ FULLY IMPLEMENTED

#### CPU Chaos
- ✅ `POST /chaos/cpu/start` - Start CPU saturation
- ✅ `POST /chaos/cpu/stop` - Stop CPU saturation

#### Lock Convoy (Threading)
- ✅ `POST /chaos/lock_convoy/start` - Start lock contention
- ✅ `POST /chaos/lock_convoy/stop` - Stop lock contention

#### Memory Chaos
- ✅ `POST /chaos/mem/leak/start` - Start memory leak
- ✅ `POST /chaos/mem/leak/stop` - Stop memory leak
- ✅ `POST /chaos/mem/pressure` - One-time memory pressure (blocks for 30s)

#### File Descriptor Leak
- ✅ `POST /chaos/fd/leak/start` - Start FD leak
- ✅ `POST /chaos/fd/leak/stop` - Stop FD leak

#### Disk Chaos
- ✅ `POST /chaos/disk/fill` - Fill disk with data
- ✅ `POST /chaos/disk/clear` - Clear disk data

#### Database Chaos
- ✅ `GET /db/slow` - Slow query (hangs DB connections)
- ✅ `POST /chaos/db_gate/set` - Control max inflight DB connections

#### Retry Storm
- ✅ `POST /chaos/retry_storm/start` - Start retry storm
- ✅ `POST /chaos/retry_storm/stop` - Stop retry storm

#### DNS Chaos
- ✅ `POST /chaos/dns/set_server` - Configure DNS server
- ✅ `GET /dns/test` - Test DNS lookup

#### System Control
- ✅ `POST /chaos/reset` - Stop all chaos
- ✅ `GET /health` - Health check
- ✅ `GET /metrics` - Prometheus metrics
- ✅ `GET /work` - CPU work generator

---

### ❌ MISSING / NOT IMPLEMENTED

#### Network Chaos (Called by chaosctl.py but NOT in app/main.py)

The following endpoints are referenced in `chaos/chaosctl.py` but **do NOT exist** in `app/main.py`:

```python
# From chaosctl.py line 119-129
if cmd == "net":
    action = sys.argv[2]
    if action == "clear":
        clear_toxics()  # ← Works (calls ToxiProxy)
        return
    if action == "latency":
        app_post("/chaos/net/latency", ...)  # ❌ MISSING
    if action == "reset_peer":
        app_post("/chaos/net/reset_peer", ...)  # ❌ MISSING  
    if action == "bandwidth":
        app_post("/chaos/net/bandwidth", ...)  # ❌ MISSING
```

**Missing Endpoints:**
- ❌ `POST /chaos/net/latency` - Add network latency
- ❌ `POST /chaos/net/reset_peer` - Reset peer connections
- ❌ `POST /chaos/net/bandwidth` - Limit bandwidth
- ❌ `POST /chaos/net/clear` - Clear network toxics (partially works via ToxiProxy)

---

## Error Analysis

### "Method Not Allowed" Error

When you run:
```bash
docker compose run --rm chaos net latency 200
docker compose run --rm chaos net bandwidth 64
docker compose run --rm chaos net reset_peer
```

The error occurs because:

1. `chaosctl.py` tries to call `app_post("/chaos/net/latency", ...)`
2. The FastAPI app receives `POST /chaos/net/latency`
3. FastAPI responds with **405 Method Not Allowed** because the route is not registered
4. The error occurs even though the route pattern doesn't exist (not a method mismatch)

### Why Network Chaos is Different

Network chaos is handled through **ToxiProxy** (a network proxy), not the app itself:

```
Client → ToxiProxy (8474) → adds latency/bandwidth throttling → Server
```

The `chaosctl.py` has **two approaches**:

1. **For ToxiProxy (Direct)**: Call `toxi()` function to manage proxies
   - Example: `toxi("POST", "/proxies/downstream/toxics", ...)`
   - Used for: `clear`, `latency`, `reset_peer`, `bandwidth`

2. **For App (Via HTTP)**: Call `app_post()` to app endpoints
   - Used for: CPU, memory, disk, DB, etc.
   - **PROBLEM**: App endpoints for network don't exist!

---

## Root Cause

The `chaosctl.py` script has a **design flaw**:

It tries to make app-level API calls for network chaos:
```python
# This is WRONG - these endpoints don't exist
app_post("/chaos/net/latency", ...)
app_post("/chaos/net/bandwidth", ...)
app_post("/chaos/net/reset_peer", ...)
```

But network chaos should go **directly to ToxiProxy**, not through the app:
```python
# This is RIGHT - ToxiProxy controls network
toxi("POST", "/proxies/downstream/toxics", ...)
```

---

## Solution Options

### Option 1: Add App Endpoints (Quick Fix)
Add proxy endpoints to `app/main.py` that forward to ToxiProxy:

```python
@app.post("/chaos/net/latency")
def net_add_latency(ms: int = 200):
    # Call ToxiProxy directly
    toxi("POST", "/proxies/downstream/toxics", {
        "name": "latency",
        "type": "latency",
        "stream": "downstream",
        "toxicity": 1.0,
        "attributes": {"latency": ms, "jitter": int(ms * 0.2)},
    })
    return {"latency_ms": ms}

@app.post("/chaos/net/bandwidth")
def net_limit_bandwidth(kbps: int = 64):
    # Call ToxiProxy directly
    toxi("POST", "/proxies/downstream/toxics", {...})
    return {"bandwidth_kbps": kbps}

@app.post("/chaos/net/reset_peer")
def net_reset_peer():
    # Call ToxiProxy directly
    toxi("POST", "/proxies/downstream/toxics", {...})
    return {"reset": True}

@app.post("/chaos/net/clear")
def net_clear():
    # Call ToxiProxy directly
    toxi("DELETE", "/proxies/downstream/toxics")
    return {"cleared": True}
```

### Option 2: Fix chaosctl.py (Better Long-term Fix)
Make `chaosctl.py` call ToxiProxy directly for network operations instead of app endpoints.

---

## Commands That Currently Fail

```bash
# All of these fail with "Method Not Allowed" (405)
docker compose run --rm chaos net latency 200
docker compose run --rm chaos net latency 500
docker compose run --rm chaos net bandwidth 64
docker compose run --rm chaos net bandwidth 256
docker compose run --rm chaos net reset_peer

# This works (uses ToxiProxy directly, not app):
docker compose run --rm chaos net clear

# This should work (disk endpoints ARE implemented):
docker compose run --rm chaos disk fill 500
docker compose run --rm chaos disk clear
```

---

## Commands That Currently Work

```bash
# All CPU/Memory/Lock/FD/DB/DNS chaos works:
docker compose run --rm chaos cpu on
docker compose run --rm chaos lock on
docker compose run --rm chaos memleak on
docker compose run --rm chaos fdleak on
docker compose run --rm chaos disk fill
docker compose run --rm chaos dbgate 5
docker compose run --rm chaos retrystorm on
docker compose run --rm chaos dns bad
docker compose run --rm chaos reset

# Direct app calls work:
curl -X POST http://localhost:8000/chaos/cpu/start
curl -X POST http://localhost:8000/chaos/mem/leak/start
curl -X GET http://localhost:8000/db/slow
```

---

## Implementation Status Summary

| Category | Status | Count |
|----------|--------|-------|
| Implemented Endpoints | ✅ | 20 |
| Missing Endpoints | ❌ | 4 |
| ToxiProxy Integration | ⚠️ | Partial (via chaosctl only) |
| **Total** | | **24** |

---

## Recommended Fix

**Implement all 4 missing network chaos endpoints in `app/main.py`:**

This allows:
1. Direct API calls to `http://localhost:8000/chaos/net/*`
2. `chaosctl.py` to work without modification
3. Consistent API interface (all chaos via app)
4. Easier testing and integration

See `IMPLEMENT_NETWORK_CHAOS_ENDPOINTS.md` for implementation code.
