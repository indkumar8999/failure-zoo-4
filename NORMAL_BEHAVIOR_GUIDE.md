# Normal Application Behavior: Background Workers

## Overview

The application now includes three background workers that simulate normal, realistic application behavior. These workers run continuously and independently of chaos injection, providing a baseline workload to measure against.

---

## Three Normal Behavior Functions

### 1. **Matrix Computation Worker** (`_normal_behavior_matrix_computation`)

**What it does:**
- Performs 100×100 random matrix multiplication every 5 seconds
- CPU-intensive operation simulating computational workload
- Uses NumPy for efficient linear algebra

**Behavior:**
```
Every 5 seconds:
├─ Create two 100×100 random matrices
├─ Multiply them (intensive computation)
├─ Calculate mean value
└─ Record event with result
```

**Metrics tracked:**
- Operation type: `matrix_multiplication`
- Matrix size: 100
- Result mean value

**Use case:** 
- Tests how chaos injection affects CPU-intensive workloads
- Measures latency impact on background computations
- Verifies CPU chaos works alongside normal operations

---

### 2. **File Operations Worker** (`_normal_behavior_file_operations`)

**What it does:**
- Randomly creates, reads, and deletes files in `/data/normal_files`
- I/O-intensive operation simulating file system activity
- Simulates a service that caches or logs data

**Behavior:**
```
Every 2 seconds (random operation):
├─ CREATE: Write 1000-byte file with random content
├─ READ:   Read random existing file
└─ DELETE: Remove random existing file

Plus cleanup:
└─ Keep max 50 files (prevent accumulation)
```

**Metrics tracked:**
- Operation: `file_create`, `file_read`, or `file_delete`
- File path
- File size (for reads)

**Use case:**
- Tests how disk chaos affects normal I/O operations
- Measures impact of disk fill chaos
- Verifies file descriptor leaks don't break normal operations

---

### 3. **Web Request Worker** (`_normal_behavior_web_requests`)

**What it does:**
- Makes HTTP requests to the `/work` endpoint every 3 seconds
- Network I/O operation simulating API calls
- Tracks response times and success/failure

**Behavior:**
```
Every 3 seconds:
├─ GET /work endpoint
├─ Record response time (ms)
├─ Record HTTP status code
├─ Record success/failure
└─ Handle timeouts/exceptions
```

**Metrics tracked:**
- Operation: `web_request`
- Endpoint: `/work`
- Status code (200, 5xx, etc.)
- Response time (milliseconds)
- Success flag

**Use case:**
- Tests how network chaos affects normal API calls
- Measures latency injection impact on request times
- Verifies bandwidth throttling doesn't break connectivity
- Detects connection reset issues

---

## Architecture

### Thread Management
```
Application Startup
    ↓
@app.on_event("startup") called
    ↓
_start_normal_behavior()
    ├─ Matrix worker thread (daemon)
    ├─ File operations thread (daemon)
    └─ Web requests thread (daemon)
        ↓
    All run continuously in background
```

### Control Flow
```
normal_behavior_stop Event (threading.Event)
    ├─ cleared on startup (allow threads to run)
    ├─ checked in every thread's while loop
    └─ can be set to gracefully stop all workers
```

### Threading Model
- **Daemon threads**: Threads won't block app shutdown
- **Independent threads**: Each worker is separate, failures don't cascade
- **State lock**: File operations use mutual exclusion where needed
- **Exception handling**: Each worker catches and logs its errors

---

## Event Tracking

All normal behavior is logged to `/data/app/events/chaos_events.jsonl`:

### Example Events

**Matrix Computation:**
```json
{
  "type": "normal_behavior",
  "operation": "matrix_multiplication",
  "size": 100,
  "result_mean": 24.952438903043305,
  "ts": 1774735937.5471518
}
```

**File Operations:**
```json
{
  "type": "normal_behavior",
  "operation": "file_create",
  "path": "/data/normal_files/file_3823.txt",
  "ts": 1774735938.6092465
}
```

**Web Requests:**
```json
{
  "type": "normal_behavior",
  "operation": "web_request",
  "endpoint": "/work",
  "status_code": 200,
  "response_time_ms": 26.57914161682129,
  "success": true,
  "ts": 1774735937.7093866
}
```

---

## Timing Schedule

| Worker | Interval | Operation Frequency |
|--------|----------|-------------------|
| Matrix | Every 5 sec | 1 computation per 5 sec |
| Files | Every 2 sec | 1 I/O operation per 2 sec |
| Requests | Every 3 sec | 1 HTTP request per 3 sec |

**Total overhead:** ~3 operations per second across all workers

---

## Observing Normal Behavior

### View Events
```bash
# Last 20 normal behavior events
tail -20 /data/app/events/chaos_events.jsonl | grep normal_behavior

# Count operations by type
cat /data/app/events/chaos_events.jsonl | grep normal_behavior | \
  python3 -c "import sys, json; ops={}; 
  [ops.update({json.loads(l)['operation']:ops.get(json.loads(l)['operation'],0)+1}) 
   for l in sys.stdin]; 
  print(ops)"
```

### Monitor in Real-Time
```bash
# Watch matrix computation times
watch -n 1 'tail -1 /data/app/events/chaos_events.jsonl | grep matrix_multiplication'

# Count file operations in last 60 seconds
watch -n 1 'tail -30 /data/app/events/chaos_events.jsonl | grep file_ | wc -l'

# Monitor web request response times
watch -n 1 'tail -10 /data/app/events/chaos_events.jsonl | grep web_request'
```

### With Chaos Active
```bash
# Start chaos + watch impact
curl -X POST http://localhost:8000/chaos/net/latency?ms=500

# Response times in events should increase
tail -f /data/app/events/chaos_events.jsonl | grep web_request
```

---

## Metrics Affected

The normal behavior workers generate Prometheus metrics:

| Metric | Impact |
|--------|--------|
| `process_cpu_seconds_total` | Increases due to matrix computation |
| `process_resident_memory_bytes` | Increases (matrices + file buffers) |
| `http_requests_total` | Incremented for /work requests |
| `http_request_latency_seconds` | Populated with real response times |
| `process_open_fds` | Increases with file operations |

---

## Dependencies Added

Added to `app/requirements.txt`:
```
numpy==1.26.4
```

NumPy is used for efficient matrix multiplication in the computation worker.

---

## Testing Scenarios

### Scenario 1: CPU Chaos with Normal Workload
```bash
# Start CPU chaos
curl -X POST http://localhost:8000/chaos/cpu/start?workers=4

# Matrix computation times should increase
tail -f /data/app/events/chaos_events.jsonl | grep matrix_multiplication
```

### Scenario 2: Disk Chaos with Normal I/O
```bash
# Start disk fill
curl -X POST http://localhost:8000/chaos/disk/fill?mb=500

# File operations should start failing or slowing down
tail -f /data/app/events/chaos_events.jsonl | grep file_
```

### Scenario 3: Network Chaos with Normal Requests
```bash
# Start network latency
curl -X POST http://localhost:8000/chaos/net/latency?ms=500

# Web request response times should increase by ~500ms
tail -f /data/app/events/chaos_events.jsonl | grep web_request
```

### Scenario 4: All Chaos + All Workers
```bash
# Start multiple chaos modes
curl -X POST http://localhost:8000/chaos/cpu/start?workers=2
curl -X POST http://localhost:8000/chaos/net/latency?ms=200
curl -X POST http://localhost:8000/chaos/mem/leak/start?mb_per_sec=50

# All workers should be affected
tail -f /data/app/events/chaos_events.jsonl
```

---

## Graceful Shutdown

If needed to stop normal behavior:

```python
# Internally called by /chaos/reset
normal_behavior_stop.set()

# Or make a custom endpoint:
@app.post("/normal/stop")
def stop_normal_behavior():
    normal_behavior_stop.set()
    return {"stopped": True}
```

---

## Code Location

All code is in `app/main.py`:

- **Lines 73-74**: `normal_behavior_stop` event flag
- **Lines 88-137**: `_normal_behavior_matrix_computation()` function
- **Lines 140-197**: `_normal_behavior_file_operations()` function
- **Lines 200-248**: `_normal_behavior_web_requests()` function
- **Lines 251-280**: `_start_normal_behavior()` coordinator function
- **Lines 770-773**: `@app.on_event("startup")` trigger

---

## Performance Impact

The three workers generate approximately:
- **3-5 MB/sec** of event log data
- **~2-5% CPU** usage on idle system
- **~10-20 file operations/sec** to disk
- **~1 HTTP request/sec** to internal endpoint

These are intentionally lightweight to simulate real application behavior without overwhelming the system.

