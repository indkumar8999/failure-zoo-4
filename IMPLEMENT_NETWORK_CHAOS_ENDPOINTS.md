# Network Chaos Endpoints Implementation

This document provides the code to add the 4 missing network chaos endpoints to `app/main.py`.

## Missing Endpoints to Implement

1. `POST /chaos/net/latency` - Add network latency
2. `POST /chaos/net/bandwidth` - Limit bandwidth
3. `POST /chaos/net/reset_peer` - Reset peer connections
4. `POST /chaos/net/clear` - Clear network toxics

---

## Implementation Code

Add this code to `app/main.py` **before the `@app.post("/chaos/reset")` endpoint** (around line 378):

```python
# Network chaos (via ToxiProxy)
import json

TOXI_URL = os.getenv("TOXI_URL", "http://toxiproxy:8474")

def _toxi_request(method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Make request to ToxiProxy API."""
    url = f"{TOXI_URL}{path}"
    try:
        r = requests.request(method, url, json=payload, timeout=5)
        r.raise_for_status()
        if r.headers.get("content-type", "").startswith("application/json"):
            return r.json()
        return None
    except Exception as e:
        raise HTTPException(503, f"ToxiProxy error: {e}")


def _ensure_proxy():
    """Ensure the downstream proxy exists in ToxiProxy."""
    try:
        proxies = _toxi_request("GET", "/proxies") or {}
        if "downstream" not in proxies:
            _toxi_request("POST", "/proxies", {
                "name": "downstream",
                "listen": "0.0.0.0:8666",
                "upstream": "downstream:9000"
            })
    except Exception:
        pass  # Proxy may already exist


def _add_toxic(name: str, toxic_type: str, attributes: Dict[str, Any], toxicity: float = 1.0):
    """Add a toxic to the downstream proxy."""
    _ensure_proxy()
    _toxi_request("POST", "/proxies/downstream/toxics", {
        "name": name,
        "type": toxic_type,
        "stream": "downstream",
        "toxicity": toxicity,
        "attributes": attributes,
    })
    _write_event({"type": "chaos", "mode": f"net_{toxic_type}", "enabled": True, "toxic": name, "attributes": attributes})


def _clear_toxics():
    """Clear all toxics from the downstream proxy."""
    try:
        _ensure_proxy()
        _toxi_request("DELETE", "/proxies/downstream/toxics")
        _write_event({"type": "chaos", "mode": "net_clear", "enabled": True})
    except Exception as e:
        raise HTTPException(503, f"Failed to clear toxics: {e}")


@app.post("/chaos/net/latency")
def chaos_net_latency(ms: int = 200):
    """Add network latency to downstream connections."""
    ms = max(0, min(ms, 10000))  # 0-10000 ms
    _clear_toxics()
    jitter = int(ms * 0.2)  # 20% jitter
    _add_toxic("latency", "latency", {"latency": ms, "jitter": jitter})
    return {"latency_ms": ms, "jitter_ms": jitter}


@app.post("/chaos/net/bandwidth")
def chaos_net_bandwidth(kbps: int = 64):
    """Limit bandwidth to downstream connections."""
    kbps = max(1, min(kbps, 100000))  # 1-100000 kbps
    _clear_toxics()
    _add_toxic("bandwidth", "bandwidth", {"rate": kbps})
    return {"bandwidth_kbps": kbps}


@app.post("/chaos/net/reset_peer")
def chaos_net_reset_peer():
    """Reset peer connections (close connections randomly)."""
    _clear_toxics()
    _add_toxic("reset", "reset_peer", {})
    return {"reset_peer": True}


@app.post("/chaos/net/clear")
def chaos_net_clear():
    """Clear all network toxics."""
    _clear_toxics()
    CHAOS.labels(mode="net_latency").set(0)
    CHAOS.labels(mode="net_bandwidth").set(0)
    CHAOS.labels(mode="net_reset_peer").set(0)
    return {"cleared": True}


@app.get("/chaos/net/status")
def chaos_net_status():
    """Get current network toxics status."""
    try:
        proxies = _toxi_request("GET", "/proxies") or {}
        downstream = proxies.get("downstream", {})
        toxics = downstream.get("toxics", [])
        return {
            "proxy_exists": "downstream" in proxies,
            "toxics": toxics,
            "count": len(toxics)
        }
    except Exception as e:
        raise HTTPException(503, f"Failed to get status: {e}")
```

---

## Step-by-Step Installation

### Step 1: Find the Location in main.py

Open `app/main.py` and find the line with:
```python
@app.post("/chaos/reset")
def chaos_reset():
```

This is around **line 378**. You'll add the network endpoints **BEFORE** this function.

### Step 2: Add the Import (if not already present)

At the top of the file (around line 5), verify you have:
```python
from typing import Optional, Dict, Any
```

This should already be there.

### Step 3: Add the Implementation

Copy the code block above (starting with `# Network chaos (via ToxiProxy)`) and insert it before the `@app.post("/chaos/reset")` line.

### Step 4: Verify the Installation

The file structure should be:
```
...
@app.post("/chaos/dns/set_server")
def dns_set_server(server: Optional[str] = None):
    ...

@app.get("/dns/test")
def dns_test(name: str = "example.com"):
    ...

# ← INSERT NETWORK CHAOS CODE HERE ←

@app.post("/chaos/reset")
def chaos_reset():
    ...
```

### Step 5: Test

After adding the code, test with:

```bash
# Test latency
curl -X POST "http://localhost:8000/chaos/net/latency?ms=200"

# Test bandwidth
curl -X POST "http://localhost:8000/chaos/net/bandwidth?kbps=64"

# Test reset_peer
curl -X POST "http://localhost:8000/chaos/net/reset_peer"

# Test clear
curl -X POST "http://localhost:8000/chaos/net/clear"

# Check status
curl "http://localhost:8000/chaos/net/status"

# Test with chaosctl
docker compose run --rm chaos net latency 200
docker compose run --rm chaos net bandwidth 64
docker compose run --rm chaos net reset_peer
docker compose run --rm chaos net clear
```

---

## Code Integration Points

### 1. Required Imports
Your file already has these, but make sure:
- ✅ `os` - for environment variables
- ✅ `requests` - for HTTP calls
- ✅ `Optional, Dict, Any` - from typing
- ✅ `HTTPException` - from fastapi

### 2. Environment Variables Used
```python
TOXI_URL = os.getenv("TOXI_URL", "http://toxiproxy:8474")
```
- Default: `http://toxiproxy:8474` (Docker Compose network)
- Override with: `TOXI_URL=...` environment variable

### 3. Event Logging
Uses existing `_write_event()` function to log network changes:
```python
_write_event({"type": "chaos", "mode": f"net_{toxic_type}", ...})
```

### 4. Metrics
Integrates with existing `CHAOS` gauge:
```python
CHAOS.labels(mode="net_latency").set(0)
```

---

## How It Works

### Network Traffic Flow

```
┌─────────────────────────────────────────────────────────────┐
│ Your Application (http://localhost:8000)                    │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Calls: POST /chaos/net/latency                             │
│          ↓                                                   │
│  _add_toxic("latency", "latency", {...})                   │
│          ↓                                                   │
│  _toxi_request("POST", "/proxies/downstream/toxics", ...)  │
│          ↓                                                   │
│  HTTP POST to http://toxiproxy:8474/proxies/.../toxics     │
│          ↓                                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ToxiProxy (http://localhost:8474)                   │   │
│  │                                                      │   │
│  │ Proxy: downstream                                   │   │
│  │   Listen: 0.0.0.0:8666                             │   │
│  │   Upstream: downstream:9000                        │   │
│  │                                                      │   │
│  │ Toxics Applied:                                    │   │
│  │   - latency: 200ms ± 40ms                          │   │
│  │   - bandwidth: 64 kbps (if added)                  │   │
│  │   - reset_peer: random connection resets (if added)│   │
│  └─────────────────────────────────────────────────────┘   │
│          ↓                                                   │
│  HTTP calls from app now go through ToxiProxy:             │
│  app → toxiproxy:8666 → downstream:9000                    │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Toxic Types

| Type | Effect | Parameters |
|------|--------|------------|
| `latency` | Add network delay | `latency` (ms), `jitter` (ms) |
| `bandwidth` | Throttle bandwidth | `rate` (kbps) |
| `reset_peer` | Random connection resets | (none) |
| `timeout` | Close connections after delay | `timeout` (ms) |
| `slicer` | Slice packets | `average_size`, `delay` |

---

## Testing Scenarios

### Scenario 1: Verify Latency Works
```bash
# Terminal 1: Start the app
docker compose up

# Terminal 2: Add latency
curl -X POST "http://localhost:8000/chaos/net/latency?ms=500"

# Terminal 3: Make a request (should be slow)
time curl "http://localhost:8000/health"
# Expected: ~500ms+ delay

# Clean up
curl -X POST "http://localhost:8000/chaos/net/clear"
```

### Scenario 2: Test via chaosctl
```bash
docker compose run --rm chaos net latency 300
docker compose run --rm chaos net clear

docker compose run --rm chaos net bandwidth 128
docker compose run --rm chaos net clear

docker compose run --rm chaos net reset_peer
docker compose run --rm chaos net clear
```

### Scenario 3: Monitor Metrics
```bash
# Watch ToxiProxy status
curl "http://localhost:8000/chaos/net/status" | jq

# Expected output:
{
  "proxy_exists": true,
  "toxics": [
    {
      "name": "latency",
      "type": "latency",
      "stream": "downstream",
      "toxicity": 1.0,
      "attributes": {
        "latency": 500,
        "jitter": 100
      }
    }
  ],
  "count": 1
}
```

---

## Troubleshooting

### Issue: "ToxiProxy error: Connection refused"
**Solution**: Ensure ToxiProxy is running:
```bash
docker compose ps  # Check if toxiproxy service is up
docker compose logs toxiproxy  # Check logs
```

### Issue: "Failed to add toxic: 404 Not Found"
**Solution**: Proxy might not exist. Try:
```bash
# Clear and recreate
curl -X POST "http://localhost:8000/chaos/net/clear"
curl -X POST "http://localhost:8000/chaos/net/latency?ms=200"
```

### Issue: Network chaos not affecting requests
**Solution**: Verify the proxy is in the request path:
```bash
# Check where requests are actually going
docker compose exec app curl -v http://downstream:9000/ok
# Should NOT go through proxy

# Correct path:
docker compose exec app curl -v http://toxiproxy:8666/ok
# This goes through proxy
```

---

## Additional Enhancements (Optional)

### Add Prometheus Metrics for Network Chaos

```python
NET_LATENCY_MS = Gauge("net_latency_ms", "Current network latency in ms")
NET_BANDWIDTH_KBPS = Gauge("net_bandwidth_kbps", "Current bandwidth limit in kbps")

@app.post("/chaos/net/latency")
def chaos_net_latency(ms: int = 200):
    ...
    NET_LATENCY_MS.set(ms)  # Add this line
    ...
```

### Add Combined Chaos Scenario

```python
@app.post("/chaos/combined/network_and_cpu")
def combined_network_cpu(latency_ms: int = 200, cpu_workers: int = 2):
    """Simultaneously add network latency and CPU saturation."""
    chaos_net_latency(latency_ms)
    chaos_cpu_start(cpu_workers)
    return {"network_latency_ms": latency_ms, "cpu_workers": cpu_workers}
```

---

## Summary

After adding this code:

✅ **New Endpoints Available:**
- `POST /chaos/net/latency?ms=200` - Add 200ms latency
- `POST /chaos/net/bandwidth?kbps=64` - Limit to 64 kbps
- `POST /chaos/net/reset_peer` - Random connection resets
- `POST /chaos/net/clear` - Remove all network chaos
- `GET /chaos/net/status` - Check current toxics

✅ **Commands Now Work:**
- `docker compose run --rm chaos net latency 500`
- `docker compose run --rm chaos net bandwidth 256`
- `docker compose run --rm chaos net reset_peer`
- `docker compose run --rm chaos net clear`

✅ **Benefits:**
- Consistent API interface (all chaos via `/chaos/*`)
- Direct HTTP access to network chaos
- Integration with chaosctl works without errors
- Better monitoring and logging

