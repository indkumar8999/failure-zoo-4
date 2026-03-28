# Metrics Quick Reference Card

A one-page quick reference for all metrics in the failure-zoo application.

## 🎯 Metrics at a Glance

### Application Custom Metrics (13 total)

#### HTTP & Request Metrics
```
http_requests_total{path, code}
  → Total requests by endpoint and HTTP status
  → Use: Track request volume and errors

http_request_latency_seconds{path}
  → Response time distribution (histogram)
  → Use: Monitor API performance SLA
```

#### Chaos Mode Status (12 modes)
```
chaos_mode{mode="cpu"}              → CPU saturation active?
chaos_mode{mode="lock_convoy"}      → Lock contention active?
chaos_mode{mode="mem_leak"}         → Memory leak active?
chaos_mode{mode="mem_pressure"}     → Memory pressure active?
chaos_mode{mode="fd_leak"}          → FD leak active?
chaos_mode{mode="disk_fill"}        → Disk fill active?
chaos_mode{mode="fsync_storm"}      → Fsync storm active?
chaos_mode{mode="dns_test"}         → DNS chaos active?
chaos_mode{mode="retry_storm"}      → Retry storm active?
chaos_mode{mode="net_latency"}      → Network latency active?
chaos_mode{mode="net_bandwidth"}    → Bandwidth throttling active?
chaos_mode{mode="net_reset_peer"}   → Connection resets active?
  → Each is 1 (enabled) or 0 (disabled)
  → Use: Verify which chaos modes are running
```

#### Resource Leak Metrics
```
leak_mb
  → Current memory leaked (0 to 800 MB)
  → Use: Monitor memory leak progression

open_fds_simulated
  → Current FD leak (0 to 5000)
  → Use: Monitor FD exhaustion

disk_fill_mb
  → Current disk fill amount (MB)
  → Use: Monitor disk usage
```

#### Database Metrics
```
db_inflight
  → DB operations currently gated (0 to 10)
  → Use: Monitor database throttling

retry_calls_total{endpoint, result}
  → Calls attempted (success/failure)
  → Use: Monitor retry storm behavior
```

---

### Python Runtime Metrics (Auto-exported)

#### Memory Metrics
```
process_resident_memory_bytes     → Physical RAM used (bytes)
process_virtual_memory_bytes      → Virtual address space (bytes)
python_gc_objects_collected_total{generation}  → GC objects freed
python_gc_objects_uncollectable_total{generation}  → Uncollectable objects
python_gc_collections_total{generation}  → GC run count
```

#### CPU Metrics
```
process_cpu_seconds_total         → Total CPU time (seconds)
```

#### File Descriptor Metrics
```
process_open_fds                  → System FDs in use
process_max_fds                   → System FD limit
```

#### Process Metrics
```
process_start_time_seconds        → Process start time (epoch)
python_info{...}                  → Python version info
```

---

## 📊 Common Queries

### Query Template: Check if Chaos is Active
```
chaos_mode{mode="cpu"} == 1
chaos_mode{mode="net_latency"} == 1
```

### Query Template: Request Latency Over Time
```
rate(http_request_latency_seconds_sum{path="/health"}[5m]) / 
rate(http_request_latency_seconds_count{path="/health"}[5m])
```

### Query Template: Error Rate
```
rate(http_requests_total{code!="200"}[5m]) / 
rate(http_requests_total[5m]) * 100
```

### Query Template: Memory Usage %
```
(process_resident_memory_bytes / 3e9) * 100
```

### Query Template: FD Usage %
```
(open_fds_simulated + process_open_fds) / process_max_fds * 100
```

---

## 🚨 Alert Rules

```
Memory leak excessive:      leak_mb > 600
FD exhaustion danger:       open_fds_simulated > 4500
DB gate saturation:         db_inflight >= 9
High request latency:       histogram_quantile(0.95, ...) > 1s
Error rate spike:           rate(http_requests_total{code!="200"}[1m]) > 0.1
CPU intensive:              process_cpu_seconds_total > 300
```

---

## 🔄 Metric Update Frequency

| Metric | Update Frequency | Resolution |
|--------|-----------------|-----------|
| `http_requests_total` | Per request | Immediate |
| `http_request_latency_seconds` | Per request | Immediate |
| `chaos_mode` | On change | Immediate |
| `leak_mb` | Every ~100ms | 100ms |
| `open_fds_simulated` | Per FD leak | Immediate |
| `disk_fill_mb` | Per write | < 1s |
| `db_inflight` | On DB op | Immediate |
| `retry_calls_total` | Per call | Immediate |
| `process_resident_memory_bytes` | ~1s | ~1 second |
| `process_cpu_seconds_total` | ~100ms | ~100ms |
| `process_open_fds` | ~1s | ~1 second |

---

## 📈 Unit Reference

```
Bytes:       process_resident_memory_bytes, process_virtual_memory_bytes
Megabytes:   leak_mb, disk_fill_mb
Kilobytes:   N/A (use MB)
Seconds:     process_cpu_seconds_total, http_request_latency_seconds
Count:       http_requests_total, open_fds_simulated, db_inflight, retry_calls_total
Gauge (0-1): chaos_mode, python_info
Timestamp:   process_start_time_seconds
```

---

## 🎨 Dashboard Panels

### Panel 1: Chaos Status Board (1 row × 12 columns)
```
Each column shows one chaos_mode gauge (0 or 1)
Arrangement: cpu, lock_convoy, mem_leak, mem_pressure, fd_leak, disk_fill,
            fsync_storm, dns_test, retry_storm, net_latency, net_bandwidth, net_reset_peer
```

### Panel 2: Resource Usage Graph
```
Y-axis 1: process_resident_memory_bytes (MB)
Y-axis 2: leak_mb (MB)
Y-axis 3: open_fds_simulated (count)
Time range: Last 1 hour
```

### Panel 3: Request Performance
```
Latency percentiles: p50, p95, p99
Top left: http_requests_total (counter)
Top right: Error rate %
Bottom: Latency heatmap
```

### Panel 4: Database Status
```
Gauge 1: db_inflight / MAX (0-10)
Gauge 2: DB gate utilization %
Graph: retry_calls_total success vs failure
```

---

## 🔧 Troubleshooting

| Problem | Check | Solution |
|---------|-------|----------|
| Metrics not updating | `/metrics` endpoint responding? | Verify app is running |
| Latency not recorded | Make requests first | Hit any endpoint to generate data |
| Memory leak not showing | `chaos_mode{mem_leak} == 1`? | Start memory leak: `POST /chaos/mem/leak/start` |
| FD count not changing | `chaos_mode{fd_leak} == 1`? | Start FD leak: `POST /chaos/fd/leak/start` |
| Process metrics missing | Python prometheus_client installed? | Check app requirements.txt |

---

## 📞 Common Workflows

### Start CPU Chaos & Monitor
```bash
curl -X POST http://localhost:8000/chaos/cpu/start?workers=4
watch 'curl -s http://localhost:8000/metrics | grep "chaos_mode{mode=\"cpu\"}\|process_cpu_seconds_total"'
```

### Start Memory Leak & Track
```bash
curl -X POST http://localhost:8000/chaos/mem/leak/start?mb_per_sec=50
watch 'curl -s http://localhost:8000/metrics | grep "leak_mb\|process_resident_memory"'
```

### Monitor Network Chaos Impact
```bash
curl -X POST http://localhost:8000/chaos/net/latency?ms=500
watch 'curl -s http://localhost:8000/metrics | grep "http_request_latency_seconds_bucket"'
```

### Check Overall System State
```bash
curl -s http://localhost:8000/metrics | grep -E "^(chaos_mode|leak_mb|open_fds_simulated|disk_fill_mb|db_inflight)" | sort
```

---

## 📊 Baseline Metrics (Healthy System)

```
Typical values with NO chaos active:
- http_requests_total: 0-10 per minute (depends on traffic)
- http_request_latency_seconds: p50=1-5ms, p95=10-50ms
- chaos_mode: All 0.0 (no chaos active)
- leak_mb: 0.0 (no leak)
- open_fds_simulated: 0.0 (no FD leak)
- disk_fill_mb: 0.0 or small value
- db_inflight: 0-2 (normal queries)
- process_resident_memory_bytes: 50-100 MB
- process_open_fds: 10-30 (normal FD count)
- process_cpu_seconds_total: Slowly increasing (idle time)
- python_gc_collections_total: Slowly increasing (periodic GC)
```

---

## 📋 Metric Cardinality

| Metric | Cardinality | Risk |
|--------|-----------|------|
| `http_requests_total` | ~20 (path × code) | Low |
| `http_request_latency_seconds` | ~20 (path) | Low |
| `chaos_mode` | 12 (fixed modes) | None |
| `retry_calls_total` | ~50-100 (endpoints × result) | Medium |
| Other metrics | 1 (global) | None |
| **Total** | ~100-150 | Low |

---

## 🔌 Integration Points

### Prometheus Scrape Config
```yaml
- job_name: 'failure-zoo'
  static_configs:
    - targets: ['localhost:8000']
  metrics_path: '/metrics'
  scrape_interval: 15s
  scrape_timeout: 10s
```

### Grafana Data Source
```
Type: Prometheus
URL: http://prometheus:9090
Access: Browser
```

### Alert Manager Config
```
group_interval: 5m
repeat_interval: 1h
Notification channel: Slack, PagerDuty, Email, etc.
```

