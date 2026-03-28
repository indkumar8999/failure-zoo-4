# 🐛 Bug Fixes: ToxiProxy Integration

**Date:** March 28, 2026

---

## Bug #1: ToxiProxy DELETE Endpoint 405 Error

### Problem
When clearing toxics, the code tried to DELETE `/proxies/downstream/toxics` which isn't a valid ToxiProxy API endpoint.

### Original Code (BROKEN)
```python
# app/main.py - OLD VERSION
def _clear_toxics():
    """Clear all toxics from the downstream proxy."""
    try:
        _ensure_proxy()
        _toxi_request("DELETE", "/proxies/downstream/toxics")  # ❌ 405 Error
        _write_event({"type": "chaos", "mode": "net_clear", "enabled": True})
    except Exception as e:
        raise HTTPException(503, f"Failed to clear toxics: {e}")

# chaos/chaosctl.py - OLD VERSION
def clear_toxics():
    ensure_proxy()
    toxi("DELETE", "/proxies/downstream/toxics")  # ❌ 405 Error
```

### Error Message
```
405 Client Error: Method Not Allowed for url: 
http://toxiproxy:8474/proxies/downstream/toxics
```

### Root Cause
ToxiProxy doesn't support bulk deletion of all toxics. Each toxic must be deleted individually by name:
```
DELETE /proxies/downstream/toxics/{toxic_name}
```

### Fixed Code
```python
# app/main.py - NEW VERSION
def _clear_toxics():
    """Clear all toxics from the downstream proxy."""
    try:
        _ensure_proxy()
        # Get existing toxics
        proxies = _toxi_request("GET", "/proxies") or {}
        downstream = proxies.get("downstream", {})
        toxics = downstream.get("toxics", [])
        
        # Delete each toxic individually
        for toxic in toxics:
            toxic_name = toxic.get("name", "")
            if toxic_name:
                try:
                    # ✅ Delete by name
                    _toxi_request("DELETE", f"/proxies/downstream/toxics/{toxic_name}")
                except Exception:
                    pass  # Ignore errors deleting individual toxics
        
        _write_event({"type": "chaos", "mode": "net_clear", "enabled": True})
    except Exception as e:
        raise HTTPException(503, f"Failed to clear toxics: {e}")

# chaos/chaosctl.py - NEW VERSION
def clear_toxics():
    ensure_proxy()
    # Get existing toxics and delete them one by one
    proxies = toxi("GET", "/proxies") or {}
    downstream = proxies.get("downstream", {})
    toxics = downstream.get("toxics", [])
    for toxic in toxics:
        toxic_name = toxic.get("name", "")
        if toxic_name:
            try:
                # ✅ Delete by name
                toxi("DELETE", f"/proxies/downstream/toxics/{toxic_name}")
            except Exception:
                pass  # Ignore errors deleting individual toxics
```

### How It Works

#### Before (Broken)
```
DELETE /proxies/downstream/toxics
    ↓
ToxiProxy responds: 405 Method Not Allowed
```

#### After (Fixed)
```
GET /proxies
    ↓
Parse toxics list: ["latency", "bandwidth"]
    ↓
DELETE /proxies/downstream/toxics/latency
    ↓
DELETE /proxies/downstream/toxics/bandwidth
    ↓
All toxics cleared ✅
```

### Test Results

#### Before
```
$ curl -X POST "http://localhost:8000/chaos/net/latency?ms=200"
{
  "detail": "Failed to clear toxics: 503: ToxiProxy error: 405 Client Error..."
}
```

#### After
```
$ curl -X POST "http://localhost:8000/chaos/net/latency?ms=200"
{
  "latency_ms": 200,
  "jitter_ms": 40
}
✅ Success
```

---

## Bug #2: chaosctl.py clear_toxics() Same Issue

### Problem
The `clear_toxics()` function in `chaos/chaosctl.py` had the same bug as `app/main.py`.

### Original Code (BROKEN)
```python
# chaos/chaosctl.py - OLD VERSION
def clear_toxics():
    ensure_proxy()
    toxi("DELETE", "/proxies/downstream/toxics")  # ❌ Same 405 error
```

### Error When Running CLI Commands
```
$ docker compose run --rm chaos net latency 300
Traceback (most recent call last):
  ...
  File "/tool/chaosctl.py", line 33, in clear_toxics
    toxi("DELETE", "/proxies/downstream/toxics")
  ...
requests.exceptions.HTTPError: 405 Client Error: Method Not Allowed for url: 
http://toxiproxy:8474/proxies/downstream/toxics
```

### Fixed Code
```python
# chaos/chaosctl.py - NEW VERSION
def clear_toxics():
    ensure_proxy()
    # Get existing toxics and delete them one by one
    proxies = toxi("GET", "/proxies") or {}
    downstream = proxies.get("downstream", {})
    toxics = downstream.get("toxics", [])
    for toxic in toxics:
        toxic_name = toxic.get("name", "")
        if toxic_name:
            try:
                # ✅ Delete by name
                toxi("DELETE", f"/proxies/downstream/toxics/{toxic_name}")
            except Exception:
                pass  # Ignore errors deleting individual toxics
```

### Test Results

#### Before
```
$ docker compose run --rm chaos net latency 300
405 Client Error: Method Not Allowed
```

#### After
```
$ docker compose run --rm chaos net latency 300
200 {"name":"latency",...}
✅ Success
```

---

## Summary of Fixes

| Bug | Location | Issue | Fix | Impact |
|-----|----------|-------|-----|--------|
| #1 | `app/main.py` _clear_toxics() | DELETE /proxies/downstream/toxics returns 405 | Delete each toxic by name individually | Network endpoints now work ✅ |
| #2 | `chaos/chaosctl.py` clear_toxics() | Same 405 error | Same fix as above | CLI commands now work ✅ |

---

## Verification

### API Testing
```
✅ curl -X POST "http://localhost:8000/chaos/net/latency?ms=200"
✅ curl -X POST "http://localhost:8000/chaos/net/bandwidth?kbps=64"
✅ curl -X POST "http://localhost:8000/chaos/net/reset_peer"
✅ curl -X POST "http://localhost:8000/chaos/net/clear"
```

### CLI Testing
```
✅ docker compose run --rm chaos net latency 300
✅ docker compose run --rm chaos net bandwidth 128
✅ docker compose run --rm chaos net reset_peer
✅ docker compose run --rm chaos net clear
```

### Status
All tests passing ✅

---

## ToxiProxy API Reference

### Getting Proxies
```
GET /proxies
Response:
{
  "downstream": {
    "name": "downstream",
    "toxics": [
      {"name": "latency", "type": "latency", ...},
      {"name": "bandwidth", "type": "bandwidth", ...}
    ]
  }
}
```

### Adding a Toxic
```
POST /proxies/downstream/toxics
{
  "name": "latency",
  "type": "latency",
  "stream": "downstream",
  "toxicity": 1.0,
  "attributes": {"latency": 200, "jitter": 40}
}
```

### Deleting a Specific Toxic
```
DELETE /proxies/downstream/toxics/{toxic_name}
Example: DELETE /proxies/downstream/toxics/latency
```

### ❌ NOT SUPPORTED
```
DELETE /proxies/downstream/toxics  ← Returns 405
```

---

## Lesson Learned

Always check the API documentation for the service you're integrating with. ToxiProxy requires:
- ✅ Individual toxic deletion by name
- ✅ Not bulk deletion of all toxics
- ✅ Getting the toxic list first to know the names

---

## Files Changed

1. **`app/main.py`** (line 457-476)
   - Fixed `_clear_toxics()` function
   - Now deletes toxics by name

2. **`chaos/chaosctl.py`** (line 31-43)
   - Fixed `clear_toxics()` function
   - Mirrors the fix from app/main.py

---

## Status: ✅ Both Bugs Fixed and Verified

