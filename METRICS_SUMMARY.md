# Metrics Summary: Wide Variety of System Behavior

This document provides a high-level summary of all metrics available in the failure-zoo application, organized by system behavior category.

## 📊 Metrics by System Behavior Category

### 1. **Request & API Performance** (HTTP Layer)

| Metric | Type | Labels | Covers |
|--------|------|--------|--------|
| `http_requests_total` | Counter | path, code | Request volume, error rates, endpoint usage |
| `http_request_latency_seconds` | Histogram | path | Response time distribution, SLA tracking |

**System Behavior**: Request handling, API responsiveness, endpoint-specific performance

---

### 2. **CPU & Computational Load**

| Metric | Type | Labels | Covers |
|--------|------|--------|--------|
| `process_cpu_seconds_total` | Counter | - | CPU consumption over time |
| `chaos_mode{mode="cpu"}` | Gauge | mode | CPU chaos state (active/inactive) |

**System Behavior**: CPU saturation, computational load, background processing

---

### 3. **Memory & Leaks**

| Metric | Type | Labels | Covers |
|--------|------|--------|--------|
| `process_resident_memory_bytes` | Gauge | - | Physical RAM consumption |
| `process_virtual_memory_bytes` | Gauge | - | Virtual address space usage |
| `leak_mb` | Gauge | - | Simulated memory leak amount |
| `python_gc_objects_collected_total` | Counter | generation | Garbage collection effectiveness |
| `python_gc_objects_uncollectable_total` | Counter | generation | Memory leak indicators |
| `python_gc_collections_total` | Counter | generation | GC frequency and pressure |
| `chaos_mode{mode="mem_leak"}` | Gauge | mode | Memory leak chaos state |
| `chaos_mode{mode="mem_pressure"}` | Gauge | mode | Memory pressure chaos state |

**System Behavior**: Memory consumption, leaks, garbage collection, memory pressure

---

### 4. **File Descriptor Management**

| Metric | Type | Labels | Covers |
|--------|------|--------|--------|
| `process_open_fds` | Gauge | - | System-level open file descriptors |
| `process_max_fds` | Gauge | - | FD ulimit / maximum available |
| `open_fds_simulated` | Gauge | - | Simulated FD leak amount |
| `chaos_mode{mode="fd_leak"}` | Gauge | mode | FD leak chaos state |

**System Behavior**: FD exhaustion, resource limits, system capacity

---

### 5. **Disk & Storage I/O**

| Metric | Type | Labels | Covers |
|--------|------|--------|--------|
| `disk_fill_mb` | Gauge | - | Disk fill amount (simulated) |
| `chaos_mode{mode="disk_fill"}` | Gauge | mode | Disk fill chaos state |
| `chaos_mode{mode="fsync_storm"}` | Gauge | mode | Filesystem sync storm state |

**System Behavior**: Disk usage, storage pressure, I/O patterns

---

### 6. **Database & Connection Pool**

| Metric | Type | Labels | Covers |
|--------|------|--------|--------|
| `db_inflight` | Gauge | - | In-flight DB operations (gated) |
| `chaos_mode` | Gauge | mode | DB-related chaos states |

**System Behavior**: Database connection pool, throttling, concurrency limits

---

### 7. **Network & Connectivity**

| Metric | Type | Labels | Covers |
|--------|------|--------|--------|
| `chaos_mode{mode="net_latency"}` | Gauge | mode | Network latency injection state |
| `chaos_mode{mode="net_bandwidth"}` | Gauge | mode | Bandwidth throttling state |
| `chaos_mode{mode="net_reset_peer"}` | Gauge | mode | Connection reset state |
| `http_request_latency_seconds` | Histogram | path | Network latency effects on APIs |

**System Behavior**: Network delays, bandwidth constraints, connection failures

---

### 8. **Concurrency & Locking**

| Metric | Type | Labels | Covers |
|--------|------|--------|--------|
| `chaos_mode{mode="lock_convoy"}` | Gauge | mode | Lock contention simulation state |

**System Behavior**: Lock contention, concurrency bottlenecks, mutex pressure

---

### 9. **Reliability & Retry Behavior**

| Metric | Type | Labels | Covers |
|--------|------|--------|--------|
| `chaos_mode{mode="retry_storm"}` | Gauge | mode | Retry storm chaos state |
| `retry_calls_total` | Counter | endpoint, result | Retry behavior, success/failure rates |

**System Behavior**: Failure handling, retry patterns, reliability testing

---

### 10. **DNS & Name Resolution**

| Metric | Type | Labels | Covers |
|--------|------|--------|--------|
| `chaos_mode{mode="dns_test"}` | Gauge | mode | DNS override chaos state |

**System Behavior**: DNS resolution failures, service discovery issues

---

### 11. **Python Runtime Health**

| Metric | Type | Labels | Covers |
|--------|------|--------|--------|
| `python_info` | Gauge | implementation, version | Python version and implementation |
| `python_gc_*` | Counter/Gauge | generation | Garbage collection health |

**System Behavior**: Runtime health, version tracking, memory management

---

### 12. **Process Lifecycle & Uptime**

| Metric | Type | Labels | Covers |
|--------|------|--------|--------|
| `process_start_time_seconds` | Gauge | - | Process start timestamp |
| `process_cpu_seconds_total` | Counter | - | Uptime (via CPU accumulated) |

**System Behavior**: Service availability, restarts, uptime tracking

---

## 🎯 System Behavior Coverage Matrix

### What Each Category Reveals

```
┌─────────────────────────┬──────────────────────────────────────────────┐
│ System Behavior         │ Metrics That Reveal It                       │
├─────────────────────────┼──────────────────────────────────────────────┤
│ Healthy Operation       │ Low latency, stable memory, low FD count     │
│ CPU Overload            │ High CPU time, high latency, GC pressure     │
│ Memory Leak             │ Rising resident memory, leak_mb increases    │
│ FD Exhaustion           │ open_fds_simulated near limit, system FDs up │
│ Disk Pressure           │ disk_fill_mb increases, fsync_storm active   │
│ Network Issues          │ High latency, net_* chaos modes active       │
│ Database Bottleneck     │ db_inflight at max, slow queries detected    │
│ Lock Contention         │ Latency spikes, lock_convoy active           │
│ Cascading Failures      │ retry_calls_total failures spike, HTTP 5xx   │
│ Resource Exhaustion     │ Multiple limits approaching simultaneously   │
│ Graceful Degradation    │ Throttling active, requests still succeeding │
│ Complete Failure        │ High latency + timeouts + failures everywhere│
└─────────────────────────┴──────────────────────────────────────────────┘
```

---

## 📈 Recommended Monitoring Setup

### Essential Metrics (Minimum Set)

For basic system health monitoring:

```
1. http_request_latency_seconds     → API responsiveness
2. process_resident_memory_bytes    → Memory usage
3. process_open_fds                 → FD availability
4. db_inflight                      → Database saturation
5. chaos_mode (all modes)           → What chaos is active
```

### Comprehensive Monitoring (Complete Set)

For detailed failure injection analysis:

```
All Application Custom Metrics:
- http_requests_total               → Request volume & error rates
- http_request_latency_seconds      → Response time distribution
- chaos_mode (12 variants)          → All chaos states
- leak_mb                           → Memory leak tracking
- open_fds_simulated                → FD leak tracking
- disk_fill_mb                      → Disk usage tracking
- db_inflight                       → Database gate status
- retry_calls_total                 → Retry storm behavior

Plus Python Runtime Metrics:
- process_resident_memory_bytes     → Physical memory
- process_virtual_memory_bytes      → Virtual address space
- process_open_fds                  → System-level FD count
- process_cpu_seconds_total         → CPU usage
- python_gc_*                       → Garbage collection
```

---

## 🔍 Key Insights from Metric Combinations

### Insight 1: "System Under CPU Load"
```
chaos_mode{mode="cpu"} == 1
↓
process_cpu_seconds_total increases rapidly
↓
http_request_latency_seconds increases
↓
python_gc_collections_total increases (more GC pressure)
```

### Insight 2: "Memory Leak Detected"
```
leak_mb increases steadily
↓
process_resident_memory_bytes increases
↓
python_gc_objects_uncollectable_total increases
↓
Eventually hits CHAOS_MEM_LIMIT_MB (800 MB)
```

### Insight 3: "Network Chaos Impact"
```
chaos_mode{mode="net_latency"} == 1
↓
http_request_latency_seconds percentiles all increase
↓
http_requests_total may decrease (timeouts)
↓
http_requests_total{code!="200"} may increase
```

### Insight 4: "Database Throttling"
```
db_inflight reaches MAX_DB_INFLIGHT limit
↓
http_requests_total{path="/db/*"} plateaus
↓
http_request_latency_seconds{path="/db/*"} increases sharply
↓
Queue depth builds up (clients waiting)
```

### Insight 5: "Cascading Failure"
```
Multiple chaos_mode flags == 1 simultaneously
↓
All latency metrics increase
↓
open_fds_simulated + process_open_fds approach limit
↓
retry_calls_total{result="failure"} spikes
↓
http_requests_total{code="5xx"} increases
```

---

## 📋 Metrics Checklist

Use this checklist to verify you're monitoring all system behaviors:

- [ ] **Request Performance**: `http_requests_total`, `http_request_latency_seconds`
- [ ] **CPU Health**: `process_cpu_seconds_total`, `chaos_mode{cpu}`
- [ ] **Memory Health**: `process_resident_memory_bytes`, `leak_mb`, `python_gc_*`
- [ ] **FD Health**: `process_open_fds`, `open_fds_simulated`
- [ ] **Disk Health**: `disk_fill_mb`, `chaos_mode{disk_fill}`
- [ ] **Database Health**: `db_inflight`, throughput metrics
- [ ] **Network Health**: `chaos_mode{net_*}`, latency metrics
- [ ] **Concurrency**: `chaos_mode{lock_convoy}`
- [ ] **Reliability**: `retry_calls_total`, error rates
- [ ] **DNS**: `chaos_mode{dns_test}`
- [ ] **Runtime**: `python_info`, `python_gc_*`
- [ ] **Uptime**: `process_start_time_seconds`

---

## 🚨 Alert Thresholds Reference

| Metric | Yellow Alert | Red Alert | Notes |
|--------|--------------|-----------|-------|
| `process_resident_memory_bytes` | >2GB | >3GB | Adjust per environment |
| `leak_mb` | >500MB | >750MB | Approaching 800MB limit |
| `open_fds_simulated` | >4000 | >4800 | Approaching 5000 limit |
| `process_open_fds` | >800 | >1000 | System-level FD usage |
| `db_inflight` | >8 | >9 | Approaching 10 limit |
| `http_request_latency_seconds` (p95) | >500ms | >1s | Response time SLA |
| `http_requests_total{code!="200"}` rate | >5/min | >10/min | Error rate threshold |
| `process_cpu_seconds_total` rate | >80 | >100 | CPU usage derivative |

---

## 📚 Quick Reference: What to Measure

### For Performance Testing
- `http_request_latency_seconds` - Baseline vs chaos
- `http_requests_total` - Throughput comparison
- `process_cpu_seconds_total` - CPU efficiency

### For Reliability Testing
- `retry_calls_total` - Failure and retry rates
- `http_requests_total{code!="200"}` - Error rates
- `chaos_mode` - Which failures are injected

### For Resource Testing
- `process_resident_memory_bytes` vs `leak_mb` - Memory behavior
- `process_open_fds` vs `open_fds_simulated` - FD behavior
- `db_inflight` - Concurrency limits

### For Chaos Engineering
- All `chaos_mode{mode="*"}` - Active chaos verification
- Corresponding behavior metrics - Impact measurement
- Latency/throughput/error metrics - System response

