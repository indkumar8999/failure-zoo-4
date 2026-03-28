# Running Experiments & Collecting Metrics from Prometheus

This guide walks you through setting up the failure zoo, running chaos experiments, and querying metrics from Prometheus.

---

## Part 1: Start the Infrastructure

### Step 1: Start all services
```bash
cd /Users/rekhanarasimha/Downloads/failure-zoo-4
docker compose up -d --build
```

This will start:
- **App** (http://localhost:8000) — Main application with chaos endpoints
- **Downstream** (http://localhost:9000) — Mock service for retry storms
- **Toxiproxy** (http://localhost:8474) — Network chaos proxy
- **PostgreSQL** (port 5432) — Database for slow query testing
- **Prometheus** (http://localhost:9090) — Metrics collector
- **Grafana** (http://localhost:3000) — Visualization (admin/admin)
- **cAdvisor** (http://localhost:8080) — Container metrics

### Step 2: Verify all services are running
```bash
docker compose ps
```

### Step 3: Check app is healthy
```bash
curl http://localhost:8000/health
# Expected: {"ok":true}
```

---

## Part 2: Run Experiments

All chaos modes can be triggered via the chaos CLI or direct API calls.

### Option A: Using the Chaos CLI (Recommended)

#### Experiment 1: CPU Saturation
```bash
# Turn on CPU chaos with 4 worker threads
docker compose run --rm chaos cpu on 4

# Let it run for 30 seconds to collect metrics
sleep 30

# Turn off CPU chaos
docker compose run --rm chaos cpu off
```

#### Experiment 2: Lock Contention
```bash
# Start lock convoy with 150 threads
docker compose run --rm chaos lock on 150

# Run for 30 seconds
sleep 30

# Stop
docker compose run --rm chaos lock off
```

#### Experiment 3: Memory Leak
```bash
# Start leaking 50 MB/sec (capped at 800 MB)
docker compose run --rm chaos memleak on 50

# Run for 20 seconds
sleep 20

# Stop
docker compose run --rm chaos memleak off
```

#### Experiment 4: File Descriptor Leak
```bash
# Start leaking 200 FDs/sec (capped at 5000)
docker compose run --rm chaos fdleak on 200

# Run for 30 seconds
sleep 30

# Stop
docker compose run --rm chaos fdleak off
```

#### Experiment 5: Disk I/O Stress
```bash
# Fill disk with 2000 MB
docker compose run --rm chaos disk fill 2000

# Run for 30 seconds
sleep 30

# Clear
docker compose run --rm chaos disk clear
```

#### Experiment 6: Database Gate (Inflight Limit)
```bash
# Limit concurrent DB operations to 1
docker compose run --rm chaos dbgate 1

# Trigger slow DB queries
for i in {1..5}; do
  curl -s http://localhost:8000/db/slow?seconds=2 &
done
wait

# Reset to default (10)
docker compose run --rm chaos dbgate 10
```

#### Experiment 7: Retry Storm
```bash
# Start retry storm: 50 QPS on the /flaky endpoint, 3 retries
docker compose run --rm chaos retrystorm on 50

# Let it run for 30 seconds
sleep 30

# Stop
docker compose run --rm chaos retrystorm off
```

#### Experiment 8: Network Latency
```bash
# Add 400ms latency to downstream service
docker compose run --rm chaos net latency 400

# Make some requests
for i in {1..10}; do
  curl -s http://localhost:8000/dns/test &
done
wait

# Clear
docker compose run --rm chaos net clear
```

#### Experiment 9: Network Bandwidth Throttling
```bash
# Limit bandwidth to 64 kbps
docker compose run --rm chaos net bandwidth 64

# Run for 30 seconds
sleep 30

# Clear
docker compose run --rm chaos net clear
```

#### Experiment 10: DNS Failure
```bash
# Set DNS server to invalid IP
docker compose run --rm chaos dns bad

# Try DNS lookup (will fail)
curl http://localhost:8000/dns/test?name=example.com

# Restore DNS
docker compose run --rm chaos dns ok
```

#### Reset All Chaos
```bash
docker compose run --rm chaos reset
```

---

### Option B: Direct API Calls (Alternative)

If you prefer to trigger experiments directly:

```bash
# CPU on
curl -X POST http://localhost:8000/chaos/cpu/start?workers=4

# CPU off
curl -X POST http://localhost:8000/chaos/cpu/stop

# Memory leak on
curl -X POST http://localhost:8000/chaos/mem/leak/start?mb_per_sec=50

# Memory leak off
curl -X POST http://localhost:8000/chaos/mem/leak/stop

# FD leak on
curl -X POST http://localhost:8000/chaos/fd/leak/start?rate_per_sec=200

# FD leak off
curl -X POST http://localhost:8000/chaos/fd/leak/stop

# Retry storm on
curl -X POST http://localhost:8000/chaos/retry_storm/start?qps=50

# Retry storm off
curl -X POST http://localhost:8000/chaos/retry_storm/stop

# Reset all
curl -X POST http://localhost:8000/chaos/reset
```

---

## Part 3: View Metrics in Prometheus

### Step 1: Open Prometheus UI
```
http://localhost:9090
```

### Step 2: Query Metrics

Prometheus scrapes metrics every 5 seconds from the app (`/metrics` endpoint) and cAdvisor.

#### Key Metrics to Query

**1. HTTP Request Metrics**
```promql
# Total requests per path
http_requests_total

# Request latency histogram
http_request_latency_seconds_bucket

# Average latency per path
rate(http_request_latency_seconds_sum[1m]) / rate(http_request_latency_seconds_count[1m])
```

**2. Chaos Mode Status**
```promql
# All active chaos modes
chaos_mode

# Specific mode (e.g., CPU)
chaos_mode{mode="cpu"}

# Filter for enabled chaos only
chaos_mode == 1
```

**3. Resource Metrics**
```promql
# Leaked memory (MB)
leak_mb

# Open file descriptors
open_fds_simulated

# Disk filled (MB)
disk_fill_mb

# In-flight DB operations
db_inflight
```

**4. Retry Storm Metrics**
```promql
# Total retry attempts
retry_calls_total

# Retry attempts by result type
retry_calls_total{result="ok"}
retry_calls_total{result="failed"}
retry_calls_total{result="exception"}

# Success rate
rate(retry_calls_total{result="ok"}[1m]) / rate(retry_calls_total{result="attempt"}[1m])
```

**5. Container Resource Metrics (from cAdvisor)**
```promql
# CPU usage
container_cpu_usage_seconds_total{name="failure-zoo-4-app-1"}

# Memory usage (bytes)
container_memory_usage_bytes{name="failure-zoo-4-app-1"}

# Memory limit
container_spec_memory_limit_bytes{name="failure-zoo-4-app-1"}
```

**6. Rate of Change (per minute)**
```promql
# Request rate
rate(http_requests_total[1m])

# Error rate
rate(http_requests_total{code=~"[45].."}[1m])
```

---

## Part 4: Complete End-to-End Experiment

Here's a complete example running multiple experiments sequentially:

```bash
#!/bin/bash
# File: run_experiment.sh

cd /Users/rekhanarasimha/Downloads/failure-zoo-4

echo "=== Starting Failure Zoo Experiment ==="

# Warm up with baseline metrics
echo "Baseline (30s)..."
sleep 30

# Experiment 1: CPU Saturation
echo "CPU Saturation Experiment (60s)..."
docker compose run --rm chaos cpu on 4
sleep 60
docker compose run --rm chaos cpu off
sleep 10

# Experiment 2: Memory Leak
echo "Memory Leak Experiment (60s)..."
docker compose run --rm chaos memleak on 50
sleep 60
docker compose run --rm chaos memleak off
sleep 10

# Experiment 3: Retry Storm
echo "Retry Storm Experiment (60s)..."
docker compose run --rm chaos retrystorm on 50
sleep 60
docker compose run --rm chaos retrystorm off
sleep 10

# Experiment 4: Combined: CPU + Memory + Network Latency
echo "Combined Chaos (60s)..."
docker compose run --rm chaos cpu on 2
docker compose run --rm chaos memleak on 30
docker compose run --rm chaos net latency 200
sleep 60
docker compose run --rm chaos reset

echo "=== Experiment Complete ==="
echo "Access Prometheus: http://localhost:9090"
echo "Access Grafana: http://localhost:3000 (admin/admin)"
```

Save and run:
```bash
chmod +x run_experiment.sh
./run_experiment.sh
```

---

## Part 5: Export Data from Prometheus

### Option 1: Use Prometheus UI
1. Go to http://localhost:9090
2. Run a query (e.g., `chaos_mode`)
3. Click **"Graph"** tab for visualization
4. Export data via browser console or screenshot

### Option 2: Query Prometheus API
```bash
# Get raw metric data (instant query)
curl 'http://localhost:9090/api/v1/query?query=http_requests_total' | jq .

# Get time-series data (range query)
curl 'http://localhost:9090/api/v1/query_range?query=chaos_mode&start=1699123200&end=1699209600&step=5s' | jq .

# Get available metrics
curl 'http://localhost:9090/api/v1/label/__name__/values' | jq .
```

### Option 3: Use Grafana
1. Go to http://localhost:3000 (admin/admin)
2. Create a new dashboard
3. Add panels with queries like:
   - `rate(http_requests_total[1m])`
   - `leak_mb`
   - `chaos_mode`
4. Export dashboard or take screenshots

---

## Part 6: Inspect Raw Data Files

All data is persisted in `./data/`:

```bash
# Chaos events timeline (ground truth labels)
cat ./data/app/events/chaos_events.jsonl | jq .

# Syscall traces
ls -lh ./data/app/syscalls/

# Prometheus time-series database
ls -lh ./data/prometheus/

# Application logs
tail -f ./data/app/logs/app_stdout.log
tail -f ./data/app/logs/app_stderr.log
```

---

## Part 7: Cleanup

### Stop containers (data persists)
```bash
docker compose down
```

### Delete all data
```bash
rm -rf ./data
```

---

## Tips for Better Experiments

1. **Wait between experiments**: Give Prometheus 30-60 seconds between experiments to stabilize
2. **Use short intervals**: Query with `[1m]` or `[5m]` ranges to see trends
3. **Monitor multiple metrics**: CPU, memory, requests, and errors together tell the full story
4. **Check event log**: `./data/app/events/chaos_events.jsonl` shows exactly when chaos was enabled/disabled
5. **Long-running experiments**: Run experiments for at least 2-3 minutes to get meaningful statistical data
6. **Capture screenshots**: Take screenshots of Prometheus graphs during experiments for documentation

---

## Useful Prometheus Query Patterns

```promql
# 95th percentile latency
histogram_quantile(0.95, rate(http_request_latency_seconds_bucket[5m]))

# Error rate (5xx or 4xx)
sum(rate(http_requests_total{code=~"[45].."}[5m])) / sum(rate(http_requests_total[5m]))

# Memory pressure (leaked vs limit)
leak_mb / (800)  # as percentage of 800MB cap

# FD pressure
open_fds_simulated / 5000  # as percentage of 5000 cap

# Combined resource pressure
(leak_mb / 800) + (open_fds_simulated / 5000) + (disk_fill_mb / 50000)
```

