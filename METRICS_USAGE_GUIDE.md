# Metrics Usage Guide & Examples

This guide provides practical examples for using the failure-zoo application metrics.

## Quick Start: Viewing Metrics

### 1. Raw Prometheus Format
```bash
curl http://localhost:8000/metrics
```

### 2. Filter Specific Metrics
```bash
# View only application custom metrics (exclude Python runtime)
curl -s http://localhost:8000/metrics | grep -v "^python_\|^process_"

# View only chaos mode status
curl -s http://localhost:8000/metrics | grep "^chaos_mode"

# View only resource leaks
curl -s http://localhost:8000/metrics | grep -E "leak_mb|open_fds_simulated|disk_fill_mb"
```

### 3. Parse with jq (convert to JSON)
```bash
# Install: brew install jq
curl -s http://localhost:8000/metrics | python3 -c "
import sys
for line in sys.stdin:
    if line.startswith('#'):
        continue
    if line.strip():
        parts = line.split()
        if len(parts) >= 2:
            print(f'{parts[0]}: {parts[-1]}')
" | sort
```

---

## Practical Monitoring Scenarios

### Scenario 1: Monitor a CPU Chaos Test

**Setup:**
```bash
# Start CPU chaos
curl -X POST "http://localhost:8000/chaos/cpu/start?workers=4"
```

**Query metrics in real-time:**
```bash
#!/bin/bash
while true; do
  echo "=== CPU Chaos Monitoring ==="
  echo "Chaos Mode Status:"
  curl -s http://localhost:8000/metrics | grep "chaos_mode{mode=\"cpu\"}"
  
  echo ""
  echo "CPU Time (seconds):"
  curl -s http://localhost:8000/metrics | grep "process_cpu_seconds_total"
  
  echo ""
  echo "Request Latency (last 10 requests):"
  curl -s http://localhost:8000/metrics | grep "http_request_latency_seconds_count" | head -5
  
  sleep 5
done
```

**Expected Output:**
```
=== CPU Chaos Monitoring ===
Chaos Mode Status:
chaos_mode{mode="cpu"} 1.0

CPU Time (seconds):
process_cpu_seconds_total 45.23

Request Latency (last 10 requests):
http_request_latency_seconds_count{path="/health"} 150.0
http_request_latency_seconds_count{path="/metrics"} 145.0
```

**What to observe:**
- `chaos_mode{mode="cpu"}` should be 1.0 (active)
- `process_cpu_seconds_total` should increase rapidly
- `http_request_latency_seconds_sum` should increase (slower responses)
- `process_resident_memory_bytes` may increase slightly

---

### Scenario 2: Monitor Memory Leak

**Setup:**
```bash
# Start memory leak
curl -X POST "http://localhost:8000/chaos/mem/leak/start?mb_per_sec=50"
```

**Monitor memory:**
```bash
#!/bin/bash
echo "Time,Leak_MB,Resident_MB,Virtual_MB" > memory_leak.csv
for i in {1..60}; do
  METRICS=$(curl -s http://localhost:8000/metrics)
  LEAK=$(echo "$METRICS" | grep "^leak_mb " | awk '{print $2}')
  RES=$(echo "$METRICS" | grep "^process_resident_memory_bytes " | awk '{print $2}')
  VIRT=$(echo "$METRICS" | grep "^process_virtual_memory_bytes " | awk '{print $2}')
  echo "$i,$LEAK,$RES,$VIRT" >> memory_leak.csv
  sleep 1
done
```

**Analyze results:**
```bash
# Calculate leak rate (MB/sec)
python3 << 'EOF'
import csv
with open('memory_leak.csv') as f:
    reader = csv.DictReader(f)
    rows = list(reader)
    first_leak = float(rows[0]['Leak_MB'])
    last_leak = float(rows[-1]['Leak_MB'])
    time_elapsed = len(rows) - 1
    leak_rate = (last_leak - first_leak) / time_elapsed
    print(f"Leak rate: {leak_rate:.2f} MB/sec")
    print(f"Total leaked: {last_leak - first_leak:.1f} MB")
    print(f"Duration: {time_elapsed} seconds")
EOF
```

**Expected Output:**
```
Leak rate: 50.00 MB/sec
Total leaked: 3000.0 MB (would hit cap of 800 MB)
Duration: 60 seconds
```

---

### Scenario 3: Monitor Network Chaos Impact

**Setup:**
```bash
# Start network latency
curl -X POST "http://localhost:8000/chaos/net/latency?ms=500"
```

**Monitor impact on latency:**
```bash
#!/bin/bash
echo "Time,Path,P50_ms,P95_ms,P99_ms,Request_Count" > network_impact.csv

# Make some requests to generate latency data
for i in {1..100}; do
  curl -s http://localhost:8000/health > /dev/null &
done
wait

# Extract latency percentiles
METRICS=$(curl -s http://localhost:8000/metrics)

# Calculate percentiles from histogram buckets
python3 << 'EOF'
import re
metrics = '''''' + METRICS + ''''''
buckets = {}
for line in metrics.split('\n'):
    if 'http_request_latency_seconds_bucket' in line and 'path="/health"' in line:
        le_match = re.search(r'le="([^"]+)"', line)
        count_match = re.search(r'}\s+([0-9.]+)', line)
        if le_match and count_match:
            le = float(le_match.group(1)) if le_match.group(1) != '+Inf' else float('inf')
            count = float(count_match.group(1))
            buckets[le] = count

total = buckets.get(float('inf'), 0)
if total > 0:
    for le in sorted(buckets.keys()):
        pct = (buckets[le] / total) * 100
        print(f"  ≤ {le:>6}s: {pct:>5.1f}% ({int(buckets[le]):>3})")
EOF
```

---

### Scenario 4: Track File Descriptor Exhaustion

**Setup:**
```bash
# Start FD leak
curl -X POST "http://localhost:8000/chaos/fd/leak/start?alloc_fds=500"
```

**Monitor FD usage:**
```bash
#!/bin/bash
echo "=== FD Leak Monitoring ==="

# Get current FD status
METRICS=$(curl -s http://localhost:8000/metrics)

SIMULATED_FDS=$(echo "$METRICS" | grep "^open_fds_simulated " | awk '{print $2}')
SYSTEM_FDS=$(echo "$METRICS" | grep "^process_open_fds " | awk '{print $2}')
MAX_FDS=$(echo "$METRICS" | grep "^process_max_fds " | awk '{print $2}')

echo "Simulated FD leak: $SIMULATED_FDS (capped at 5000)"
echo "System open FDs:   $SYSTEM_FDS"
echo "System max FDs:    $MAX_FDS"

# Calculate usage percentage
USAGE=$(echo "scale=1; ($SYSTEM_FDS / $MAX_FDS) * 100" | bc)
echo "System FD usage:   ${USAGE}%"

# Calculate headroom
if (( $(echo "$SYSTEM_FDS < $MAX_FDS" | bc -l) )); then
    HEADROOM=$(echo "$MAX_FDS - $SYSTEM_FDS" | bc)
    echo "Remaining headroom: $HEADROOM FDs"
fi
```

---

### Scenario 5: Monitor Database Gate Throttling

**Setup:**
```bash
# Set DB connection limit to 5
curl -X POST "http://localhost:8000/chaos/db_gate/set?limit=5"

# Trigger slow queries to block the gate
for i in {1..20}; do
  curl -s "http://localhost:8000/db/slow" > /dev/null &
done
```

**Monitor gate status:**
```bash
#!/bin/bash
echo "Time,DB_Inflight,Requests_Total" >> db_gate.log

for i in {1..30}; do
  METRICS=$(curl -s http://localhost:8000/metrics)
  INFLIGHT=$(echo "$METRICS" | grep "^db_inflight " | awk '{print $2}')
  TOTAL=$(echo "$METRICS" | grep "http_requests_total{code=\"200\"" | tail -1 | awk '{print $2}')
  
  echo "$(date +%s),$INFLIGHT,$TOTAL" >> db_gate.log
  echo "DB Inflight: $INFLIGHT/5 ($(echo "scale=0; $INFLIGHT * 20" | bc)%)"
  sleep 1
done
```

---

### Scenario 6: Compare Baseline vs Chaos

**Create baseline:**
```bash
#!/bin/bash
echo "=== Collecting Baseline Metrics (60 seconds) ==="

for i in {1..60}; do
  METRICS=$(curl -s http://localhost:8000/metrics)
  
  # Extract key metrics
  LAT=$(echo "$METRICS" | grep "http_request_latency_seconds_sum{path=\"/health\"}" | awk '{print $2}')
  COUNT=$(echo "$METRICS" | grep "http_request_latency_seconds_count{path=\"/health\"}" | awk '{print $2}')
  MEM=$(echo "$METRICS" | grep "^process_resident_memory_bytes " | awk '{print $2}')
  CPU=$(echo "$METRICS" | grep "^process_cpu_seconds_total " | awk '{print $2}')
  
  echo "$i,$LAT,$COUNT,$MEM,$CPU" >> baseline.csv
  sleep 1
done

# Calculate baseline averages
python3 << 'EOF'
import csv
import statistics

with open('baseline.csv') as f:
    reader = csv.DictReader(f, fieldnames=['time', 'lat_sum', 'count', 'mem', 'cpu'])
    rows = list(reader)
    
    lat_avgs = []
    for row in rows:
        count = float(row['count'])
        if count > 0:
            lat_avgs.append(float(row['lat_sum']) / count * 1000)  # Convert to ms
    
    print(f"Baseline latency (avg): {statistics.mean(lat_avgs):.2f}ms")
    print(f"Baseline latency (p95): {sorted(lat_avgs)[int(len(lat_avgs)*0.95)]:.2f}ms")
    print(f"Baseline memory: {float(rows[-1]['mem'])/(1024**3):.2f}GB")
EOF
```

**Compare with chaos:**
```bash
# Enable chaos
curl -X POST "http://localhost:8000/chaos/net/latency?ms=200"
curl -X POST "http://localhost:8000/chaos/cpu/start?workers=2"

# Collect chaos metrics
echo "=== Collecting Chaos Metrics (60 seconds) ==="
for i in {1..60}; do
  METRICS=$(curl -s http://localhost:8000/metrics)
  LAT=$(echo "$METRICS" | grep "http_request_latency_seconds_sum{path=\"/health\"}" | awk '{print $2}')
  COUNT=$(echo "$METRICS" | grep "http_request_latency_seconds_count{path=\"/health\"}" | awk '{print $2}')
  MEM=$(echo "$METRICS" | grep "^process_resident_memory_bytes " | awk '{print $2}')
  CPU=$(echo "$METRICS" | grep "^process_cpu_seconds_total " | awk '{print $2}')
  echo "$i,$LAT,$COUNT,$MEM,$CPU" >> chaos.csv
  sleep 1
done

# Compare
python3 << 'EOF'
import csv

def analyze_file(filename):
    with open(filename) as f:
        reader = csv.DictReader(f, fieldnames=['time', 'lat_sum', 'count', 'mem', 'cpu'])
        rows = list(reader)
        lat_avgs = []
        for row in rows:
            count = float(row['count'])
            if count > 0:
                lat_avgs.append(float(row['lat_sum']) / count * 1000)
        return lat_avgs

baseline = analyze_file('baseline.csv')
chaos = analyze_file('chaos.csv')

print(f"Baseline avg latency: {sum(baseline)/len(baseline):.2f}ms")
print(f"Chaos avg latency:    {sum(chaos)/len(chaos):.2f}ms")
print(f"Increase:             {(sum(chaos)/len(chaos)) / (sum(baseline)/len(baseline)):.1f}x")
EOF
```

---

## Creating Prometheus Dashboards

### Using Grafana

1. **Add Data Source:**
   - Type: Prometheus
   - URL: `http://prometheus:9090`

2. **Create Dashboard:**
   ```
   Dashboard Name: Failure Zoo Monitoring
   ```

3. **Add Panels:**

**Panel 1: Chaos Mode Status**
```
SELECT:
- chaos_mode
LEGEND: {{mode}}
VISUALIZATION: Stat (shows 0 or 1)
```

**Panel 2: Memory Tracking**
```
SELECT:
- leak_mb
- process_resident_memory_bytes / (1024^3)  [GB]
LEGEND: Leaked | System Memory
VISUALIZATION: Graph
```

**Panel 3: Request Latency**
```
SELECT:
- rate(http_request_latency_seconds_sum[5m]) / rate(http_request_latency_seconds_count[5m]) * 1000  [ms]
BY: path
VISUALIZATION: Graph with multiple series
```

**Panel 4: FD Status**
```
SELECT:
- open_fds_simulated / 5000 * 100  [% of limit]
- process_open_fds
LEGEND: Simulated % | System Open FDs
VISUALIZATION: Gauge + Graph
```

---

## Alert Configuration Examples

### Prometheus Alert Rules

Save as `alerts.yml`:

```yaml
groups:
  - name: failure_zoo
    rules:
      - alert: HighMemoryLeak
        expr: leak_mb > 600
        for: 2m
        annotations:
          summary: "High memory leak detected: {{ $value }}MB"
      
      - alert: FDExhaustion
        expr: open_fds_simulated / 5000 > 0.8
        for: 1m
        annotations:
          summary: "FD usage at {{ $value | humanizePercentage }}"
      
      - alert: DatabaseGateSaturated
        expr: db_inflight / 10 > 0.9
        for: 1m
        annotations:
          summary: "DB gate at {{ $value | humanizePercentage }} capacity"
      
      - alert: HighLatency
        expr: rate(http_request_latency_seconds_sum[5m]) / rate(http_request_latency_seconds_count[5m]) > 1
        for: 5m
        annotations:
          summary: "Request latency exceeding 1 second"
```

---

## Exporting Metrics

### Prometheus Remote Write

Add to `prometheus.yml`:
```yaml
remote_write:
  - url: "https://your-monitoring-service/api/prom/push"
    write_relabel_configs:
      - source_labels: [__name__]
        regex: 'failure_zoo_.*'
        action: keep
```

### Custom Export Script

```bash
#!/bin/bash
# Export metrics every 60 seconds

while true; do
  TIMESTAMP=$(date +%s)
  METRICS=$(curl -s http://localhost:8000/metrics)
  
  # Write to InfluxDB
  while IFS= read -r line; do
    if [[ ! $line =~ ^# ]] && [[ -n $line ]]; then
      # Convert Prometheus to InfluxDB line protocol
      echo "$line timestamp=$TIMESTAMP" | \
        curl -X POST "http://localhost:8086/write?db=failure_zoo" --data-binary @-
    fi
  done <<< "$METRICS"
  
  sleep 60
done
```

---

## Troubleshooting Metrics

### Metrics Not Updating

```bash
# Check if metrics endpoint is responding
curl -v http://localhost:8000/metrics | head -20

# Verify chaos modes are being tracked
curl -s http://localhost:8000/metrics | grep "chaos_mode"
```

### Latency Metrics Missing

```bash
# Make a request first to generate latency data
curl http://localhost:8000/health

# Then check latency metrics
curl -s http://localhost:8000/metrics | grep "http_request_latency"
```

### Memory Leak Not Increasing

```bash
# Verify chaos mode is active
curl -s http://localhost:8000/metrics | grep "chaos_mode{mode=\"mem_leak\"}"

# Check if memory is actually allocated
curl -s http://localhost:8000/metrics | grep "leak_mb"
```

