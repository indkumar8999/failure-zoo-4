# 🚀 Quick Reference: Network Chaos API

## What Was Fixed

**Problem:** "Method Not Allowed" error when running:
```bash
docker compose run --rm chaos net latency 200
docker compose run --rm chaos net bandwidth 64
docker compose run --rm chaos net reset_peer
```

**Solution:** Implemented 5 missing network chaos endpoints in `app/main.py`

---

## New Endpoints

### 1️⃣ Latency
```bash
curl -X POST "http://localhost:8000/chaos/net/latency?ms=200"
docker compose run --rm chaos net latency 200
```
**Adds network delay:** 0-10000 ms (default: 200 ms)

### 2️⃣ Bandwidth
```bash
curl -X POST "http://localhost:8000/chaos/net/bandwidth?kbps=64"
docker compose run --rm chaos net bandwidth 64
```
**Limits bandwidth:** 1-100000 kbps (default: 64 kbps)

### 3️⃣ Reset Peer
```bash
curl -X POST "http://localhost:8000/chaos/net/reset_peer"
docker compose run --rm chaos net reset_peer
```
**Randomly closes connections**

### 4️⃣ Clear
```bash
curl -X POST "http://localhost:8000/chaos/net/clear"
docker compose run --rm chaos net clear
```
**Removes all network chaos**

### 5️⃣ Status
```bash
curl "http://localhost:8000/chaos/net/status"
```
**Shows current network toxics**

---

## Usage Examples

### Single Chaos
```bash
# Add 500ms latency
docker compose run --rm chaos net latency 500

# Limit to 256 kbps
docker compose run --rm chaos net bandwidth 256

# Random resets
docker compose run --rm chaos net reset_peer

# Clear
docker compose run --rm chaos net clear
```

### Combined Chaos
```bash
# CPU + Memory
docker compose run --rm chaos cpu on
docker compose run --rm chaos memleak on

# Network + Retry Storm
docker compose run --rm chaos net latency 300
docker compose run --rm chaos retrystorm on

# Clean up
docker compose run --rm chaos reset
```

---

## Implementation Details

| Item | Value |
|------|-------|
| **File** | `app/main.py` |
| **Lines Added** | ~120 |
| **New Endpoints** | 5 |
| **New Functions** | 4 |
| **Dependencies** | None (uses existing) |
| **Breaking Changes** | None |

---

## How It Works

```
Your Request
    ↓
FastAPI Endpoint
    ↓
ToxiProxy API Call
    ↓
Network Effects Applied
    ↓
Traffic to Downstream
```

**Example:** When you add 200ms latency:
- All requests to downstream get 200ms delay
- Plus 20% random jitter (±40ms)
- Helps test application resilience

---

## Testing

```bash
# Test 1: Add latency
curl -X POST "http://localhost:8000/chaos/net/latency?ms=200"

# Test 2: Check it's working
curl "http://localhost:8000/chaos/net/status" | jq .count

# Test 3: Via chaosctl
docker compose run --rm chaos net latency 300

# Test 4: Clear
curl -X POST "http://localhost:8000/chaos/net/clear"
```

---

## All Chaos Modes (Complete List)

| Mode | Endpoints | Status |
|------|-----------|--------|
| CPU | start, stop | ✅ |
| Lock | start, stop | ✅ |
| Memory | leak (start/stop), pressure | ✅ |
| FD | leak (start/stop) | ✅ |
| Disk | fill, clear | ✅ |
| Database | slow query, gate control | ✅ |
| Retry | start, stop | ✅ |
| DNS | set server, test | ✅ |
| **Network** | **latency, bandwidth, reset, clear, status** | **✅ NEW** |

**Total:** 25+ endpoints, all working!

---

## Troubleshooting

### Still Getting "Method Not Allowed"?
1. Rebuild the app container:
   ```bash
   docker compose down
   docker compose up --build
   ```
2. Check container logs:
   ```bash
   docker compose logs app
   ```

### ToxiProxy errors?
1. Check ToxiProxy is running:
   ```bash
   docker compose ps toxiproxy
   ```
2. View logs:
   ```bash
   docker compose logs toxiproxy
   ```

### Latency not working?
Make sure app requests go through ToxiProxy:
```bash
# This goes through toxiproxy (correct):
docker compose exec app curl http://toxiproxy:8666/ok

# This bypasses toxiproxy (wrong):
docker compose exec app curl http://downstream:9000/ok
```

---

## Documentation Files

📄 **`API_IMPLEMENTATION_STATUS.md`** - Full API status report  
📄 **`IMPLEMENT_NETWORK_CHAOS_ENDPOINTS.md`** - Implementation details  
📄 **`NETWORK_CHAOS_ENDPOINTS_COMPLETE.md`** - Complete API reference  
📄 **`API_IMPLEMENTATION_COMPLETE.md`** - Before/after comparison  

---

## Summary

✅ Fixed "Method Not Allowed" errors  
✅ Added all 5 network chaos endpoints  
✅ No breaking changes  
✅ Works with existing infrastructure  
✅ Ready to use immediately  

**Start using network chaos now:**
```bash
docker compose run --rm chaos net latency 200
```

