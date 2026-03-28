# Normal Behavior Testing Guide

Quick commands to verify normal behavior is working and to test with chaos.

---

## Verify Normal Behavior is Running

### Check Events File
```bash
# View last 5 events
tail -5 /Users/rekhanarasimha/Downloads/failure-zoo-4/data/app/events/chaos_events.jsonl

# Count events by type (last minute)
tail -100 /Users/rekhanarasimha/Downloads/failure-zoo-4/data/app/events/chaos_events.jsonl | \
  grep -o '"operation":"[^"]*"' | sort | uniq -c
```

### Check Metrics
```bash
# View CPU time (should be increasing)
curl -s http://localhost:8000/metrics | grep "process_cpu_seconds_total"

# View request count (should increase)
curl -s http://localhost:8000/metrics | grep "http_requests_total" | grep /work

# View memory (should be stable or slightly increasing)
curl -s http://localhost:8000/metrics | grep "process_resident_memory_bytes"
```

### Watch Live Events
```bash
# Follow events in real-time
tail -f /Users/rekhanarasimha/Downloads/failure-zoo-4/data/app/events/chaos_events.jsonl | grep normal_behavior
```

---

## Test 1: Normal Workload Baseline (5 minutes)

**Goal:** Record baseline metrics without chaos

```bash
#!/bin/bash
echo "=== Collecting baseline (5 min) ==="
sleep 300

# Metrics from chaos_events.jsonl
echo "Matrix computations (expect ~60):"
tail -300 /Users/rekhanarasimha/Downloads/failure-zoo-4/data/app/events/chaos_events.jsonl | \
  grep matrix_multiplication | wc -l

echo "File operations (expect ~150):"
tail -300 /Users/rekhanarasimha/Downloads/failure-zoo-4/data/app/events/chaos_events.jsonl | \
  grep -E '"operation":"file_' | wc -l

echo "Web requests (expect ~100):"
tail -300 /Users/rekhanarasimha/Downloads/failure-zoo-4/data/app/events/chaos_events.jsonl | \
  grep web_request | wc -l
```

---

## Test 2: CPU Chaos Impact

**Goal:** See how CPU chaos affects normal computation

```bash
# 1. Start CPU chaos
echo "Starting CPU chaos..."
curl -X POST "http://localhost:8000/chaos/cpu/start?workers=4"

# 2. Wait 30 seconds for events to accumulate
sleep 30

# 3. Extract matrix computation result means (should be similar)
echo "=== Matrix result means (should be ~25) ==="
tail -50 /Users/rekhanarasimha/Downloads/failure-zoo-4/data/app/events/chaos_events.jsonl | \
  grep matrix_multiplication | grep -o '"result_mean":[0-9.]*' | cut -d: -f2

# 4. Check CPU time increased
echo ""
echo "=== CPU time (should be significantly higher) ==="
curl -s http://localhost:8000/metrics | grep "process_cpu_seconds_total"

# 5. Stop CPU chaos
curl -X POST "http://localhost:8000/chaos/cpu/stop"
```

---

## Test 3: Network Latency Impact

**Goal:** Measure how network chaos affects request latency

```bash
# 1. Collect baseline latencies (30 sec)
echo "=== Baseline request times (30 sec) ==="
for i in {1..10}; do
  curl -s http://localhost:8000/metrics | grep 'http_request_latency_seconds_sum{path="/work"}'
  sleep 3
done

# 2. Start network latency (500ms)
echo ""
echo "Starting 500ms network latency..."
curl -X POST "http://localhost:8000/chaos/net/latency?ms=500"

# 3. Collect chaos latencies (30 sec)
echo ""
echo "=== With 500ms latency (30 sec) ==="
for i in {1..10}; do
  curl -s http://localhost:8000/metrics | grep 'http_request_latency_seconds_sum{path="/work"}'
  sleep 3
done

# 4. Check events for actual response times
echo ""
echo "=== Actual response times from events ==="
tail -50 /Users/rekhanarasimha/Downloads/failure-zoo-4/data/app/events/chaos_events.jsonl | \
  grep web_request | grep -o '"response_time_ms":[0-9.]*' | cut -d: -f2 | sort -n

# 5. Clear chaos
curl -X POST "http://localhost:8000/chaos/net/clear"
```

---

## Test 4: Disk I/O with Chaos

**Goal:** See how disk fill affects file operations

```bash
# 1. Check initial file count
echo "Initial file count:"
ls -1 /Users/rekhanarasimha/Downloads/failure-zoo-4/data/normal_files | wc -l

# 2. Start disk fill (200 MB)
echo "Starting disk fill..."
curl -X POST "http://localhost:8000/chaos/disk/fill?mb=200"

# 3. Monitor file operations for 30 seconds
echo ""
echo "File operations during disk fill:"
sleep 30
tail -100 /Users/rekhanarasimha/Downloads/failure-zoo-4/data/app/events/chaos_events.jsonl | \
  grep -E '"operation":"file_' | tail -20

# 4. Clear disk chaos
curl -X POST "http://localhost:8000/chaos/disk/clear"
```

---

## Test 5: Memory Leak with Normal Operations

**Goal:** Observe how memory pressure affects normal workload

```bash
# 1. Get baseline memory
echo "=== Baseline memory ==="
curl -s http://localhost:8000/metrics | grep "process_resident_memory_bytes"

# 2. Start memory leak (50 MB/sec)
echo ""
echo "Starting 50 MB/sec memory leak..."
curl -X POST "http://localhost:8000/chaos/mem/leak/start?mb_per_sec=50"

# 3. Monitor memory and operations for 30 seconds
echo ""
echo "Monitoring for 30 seconds..."
for i in {1..6}; do
  echo ""
  echo "=== Sample $i (at ${i}0 seconds) ==="
  curl -s http://localhost:8000/metrics | grep -E "process_resident_memory_bytes|leak_mb" | grep -v "^#"
  
  # Show recent operations
  tail -20 /Users/rekhanarasimha/Downloads/failure-zoo-4/data/app/events/chaos_events.jsonl | \
    grep '"operation"' | tail -3 | sed 's/.*"operation":"\([^"]*\).*/  - \1/'
  
  sleep 5
done

# 4. Stop memory leak
echo ""
echo "Stopping memory leak..."
curl -X POST "http://localhost:8000/chaos/mem/leak/stop"
```

---

## Test 6: Combined Chaos Test

**Goal:** Run multiple chaos modes simultaneously

```bash
#!/bin/bash

echo "=== COMBINED CHAOS TEST ==="
echo ""
echo "Starting CPU chaos..."
curl -s -X POST "http://localhost:8000/chaos/cpu/start?workers=2" | python3 -m json.tool

echo ""
echo "Starting network latency (200ms)..."
curl -s -X POST "http://localhost:8000/chaos/net/latency?ms=200" | python3 -m json.tool

echo ""
echo "Starting memory leak (30 MB/sec)..."
curl -s -X POST "http://localhost:8000/chaos/mem/leak/start?mb_per_sec=30" | python3 -m json.tool

echo ""
echo "Monitoring for 60 seconds..."
for i in {1..12}; do
  echo ""
  echo "--- Sample $i (at ${i*5} seconds) ---"
  
  # Get metrics
  METRICS=$(curl -s http://localhost:8000/metrics)
  
  echo "CPU time:"
  echo "$METRICS" | grep "process_cpu_seconds_total " | tail -1 | grep -o '[0-9.]*$'
  
  echo "Memory (MB):"
  echo "$METRICS" | grep "process_resident_memory_bytes " | grep -o '[0-9.]*$' | awk '{printf "%.0f MB\n", $1 / 1024 / 1024}'
  
  echo "Memory leak (MB):"
  echo "$METRICS" | grep "^leak_mb " | awk '{print $2}'
  
  echo "Recent operations:"
  tail -10 /Users/rekhanarasimha/Downloads/failure-zoo-4/data/app/events/chaos_events.jsonl | \
    grep normal_behavior | sed 's/.*"operation":"\([^"]*\)".*/  - \1/' | head -3
  
  sleep 5
done

echo ""
echo "=== Resetting all chaos ==="
curl -s -X POST "http://localhost:8000/chaos/reset" | python3 -m json.tool
```

---

## Test 7: Check File Operations Directory

```bash
# View file operation directory
ls -lh /Users/rekhanarasimha/Downloads/failure-zoo-4/data/normal_files

# Count files
ls /Users/rekhanarasimha/Downloads/failure-zoo-4/data/normal_files | wc -l

# Check total size
du -sh /Users/rekhanarasimha/Downloads/failure-zoo-4/data/normal_files

# Watch files being created/deleted
watch -n 1 'ls /Users/rekhanarasimha/Downloads/failure-zoo-4/data/normal_files | wc -l'
```

---

## Quick Stats Script

Save this as `check_normal_behavior.sh`:

```bash
#!/bin/bash

EVENTS_FILE="/Users/rekhanarasimha/Downloads/failure-zoo-4/data/app/events/chaos_events.jsonl"
NORMAL_DIR="/Users/rekhanarasimha/Downloads/failure-zoo-4/data/normal_files"

echo "╔════════════════════════════════════════════╗"
echo "║   Normal Behavior Status Report            ║"
echo "╚════════════════════════════════════════════╝"
echo ""

# Count recent events
echo "=== Recent Events (last 100 lines) ==="
echo "Matrix computations: $(tail -100 "$EVENTS_FILE" | grep -c matrix_multiplication)"
echo "File creates:        $(tail -100 "$EVENTS_FILE" | grep -c '"operation":"file_create')"
echo "File reads:          $(tail -100 "$EVENTS_FILE" | grep -c '"operation":"file_read')"
echo "File deletes:        $(tail -100 "$EVENTS_FILE" | grep -c '"operation":"file_delete')"
echo "Web requests:        $(tail -100 "$EVENTS_FILE" | grep -c '"operation":"web_request')"

echo ""
echo "=== File Operations Directory ==="
echo "Files in /data/normal_files: $(ls "$NORMAL_DIR" 2>/dev/null | wc -l)"
echo "Total size: $(du -sh "$NORMAL_DIR" 2>/dev/null | cut -f1)"

echo ""
echo "=== Current System Metrics ==="
METRICS=$(curl -s http://localhost:8000/metrics 2>/dev/null)

echo "CPU time: $(echo "$METRICS" | grep "process_cpu_seconds_total " | grep -o '[0-9.]*$') seconds"
echo "Memory: $(echo "$METRICS" | grep "process_resident_memory_bytes " | grep -o '[0-9.]*$' | awk '{printf "%.0f MB\n", $1 / 1024 / 1024}')"
echo "Open FDs: $(echo "$METRICS" | grep "^process_open_fds " | grep -o '[0-9.]*$')"

echo ""
echo "=== Last 5 Events ==="
tail -5 "$EVENTS_FILE" | python3 -c "
import sys, json
for line in sys.stdin:
  try:
    data = json.loads(line)
    op = data.get('operation', 'unknown')
    print(f'  {op}')
  except:
    pass
"
```

Usage:
```bash
chmod +x check_normal_behavior.sh
./check_normal_behavior.sh
```

---

## Expected Behavior

### Healthy System (No Chaos)
- Matrix computations: 1 per 5 seconds
- File operations: ~1 every 2 seconds (random create/read/delete)
- Web requests: 1 per 3 seconds
- Response times: 20-50ms
- CPU time: Increasing steadily (~1-2 sec per 10 sec)
- Memory: Stable (~50-150 MB)

### With CPU Chaos (4 workers)
- Matrix computations: Still 1 per 5 sec (same count, higher CPU time)
- File operations: Slightly slower (more latency)
- Web requests: Respond slower (~50-100ms instead of 20-50ms)
- CPU time: Increasing rapidly

### With Network Latency (500ms)
- Web request response times: +500ms (so 520-550ms total)
- Other operations: Unaffected (local)
- Event counts: Same

### With Memory Leak (50 MB/sec)
- Memory: Increasing by ~50 MB per second
- File operations: May slow down as memory pressure builds
- Garbage collection: Triggered more frequently
- Eventually hits 800 MB cap

