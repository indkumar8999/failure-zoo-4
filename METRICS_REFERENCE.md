# Comprehensive Metrics Reference

This document describes all metrics exposed by the failure-zoo application via the `/metrics` endpoint (Prometheus format).

## Application Custom Metrics

### HTTP Request Metrics

#### `http_requests_total` (Counter)
- **Type**: Counter
- **Labels**: `path`, `code`
- **Description**: Total number of HTTP requests received
- **Units**: Count
- **Example**: 
  ```
  http_requests_total{code="200",path="/health"} 42.0
  http_requests_total{code="200",path="/chaos/cpu/start"} 5.0
  ```
- **Use Case**: Track request volume and error rates across endpoints

#### `http_request_latency_seconds` (Histogram)
- **Type**: Histogram with buckets
- **Labels**: `path`
- **Description**: HTTP request latency distribution
- **Units**: Seconds
- **Buckets**: 0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0, +Inf
- **Includes**: `_bucket`, `_count`, `_sum`, `_created` time series
- **Example**:
  ```
  http_request_latency_seconds_bucket{le="0.01",path="/health"} 100.0
  http_request_latency_seconds_sum{path="/health"} 0.5
  http_request_latency_seconds_count{path="/health"} 1000.0
  ```
- **Use Case**: Monitor API response times and detect performance degradation

---

### Chaos Mode Status Metrics

#### `chaos_mode` (Gauge)
- **Type**: Gauge (0 or 1)
- **Labels**: `mode`
- **Description**: Current state of each chaos injection mode (1 = enabled, 0 = disabled)
- **Modes Tracked**:
  - `cpu` - CPU saturation chaos
  - `lock_convoy` - Lock contention chaos
  - `mem_leak` - Memory leak injection
  - `mem_pressure` - Memory pressure simulation
  - `fd_leak` - File descriptor leak
  - `disk_fill` - Disk fill chaos
  - `fsync_storm` - Filesystem sync storm
  - `dns_test` - DNS override
  - `retry_storm` - Retry storm chaos
  - `net_latency` - Network latency injection
  - `net_bandwidth` - Network bandwidth throttling
  - `net_reset_peer` - Random connection resets
- **Example**:
  ```
  chaos_mode{mode="cpu"} 1.0          # CPU chaos is active
  chaos_mode{mode="mem_leak"} 0.0     # Memory leak is inactive
  chaos_mode{mode="net_latency"} 1.0  # Network latency is active
  ```
- **Use Case**: Monitor which chaos modes are currently active in the system

---

### Resource Leak Metrics

#### `leak_mb` (Gauge)
- **Type**: Gauge
- **Description**: Approximate amount of memory currently leaked by the simulator
- **Units**: Megabytes (MB)
- **Range**: 0 to `CHAOS_MEM_LIMIT_MB` (default: 800 MB)
- **Example**:
  ```
  leak_mb 250.5  # ~250.5 MB of memory is being leaked
  ```
- **Use Case**: Monitor memory consumption during memory chaos tests

#### `open_fds_simulated` (Gauge)
- **Type**: Gauge
- **Description**: Number of file descriptors currently held open by the FD leak simulator
- **Units**: Count
- **Range**: 0 to `CHAOS_FD_LIMIT` (default: 5000)
- **Example**:
  ```
  open_fds_simulated 1234  # 1234 file descriptors are currently held open
  ```
- **Use Case**: Monitor FD exhaustion during FD leak chaos tests

#### `disk_fill_mb` (Gauge)
- **Type**: Gauge
- **Description**: Total amount of disk space currently filled by the simulator
- **Units**: Megabytes (MB)
- **Example**:
  ```
  disk_fill_mb 500.0  # 500 MB of disk space is filled
  ```
- **Use Case**: Monitor disk usage during disk chaos tests

---

### Database Metrics

#### `db_inflight` (Gauge)
- **Type**: Gauge
- **Description**: Number of database operations currently in-flight (blocked by the app gate)
- **Units**: Count
- **Range**: 0 to `MAX_DB_INFLIGHT` (default: 10)
- **Example**:
  ```
  db_inflight 7  # 7 out of 10 allowed DB operations are in-flight
  ```
- **Use Case**: Monitor database gate throttling and connection pool pressure

---

### Retry Storm Metrics

#### `retry_calls_total` (Counter)
- **Type**: Counter
- **Labels**: `endpoint`, `result`
- **Description**: Total number of downstream API calls attempted during retry storm
- **Labels**:
  - `endpoint`: The downstream endpoint being called
  - `result`: "success" or "failure"
- **Example**:
  ```
  retry_calls_total{endpoint="/endpoint1",result="success"} 150.0
  retry_calls_total{endpoint="/endpoint1",result="failure"} 45.0
  retry_calls_total{endpoint="/endpoint2",result="success"} 200.0
  ```
- **Use Case**: Monitor retry behavior and failure rates during retry storm tests

---

## Python Runtime Metrics (Auto-exported)

These metrics are automatically collected by the `prometheus_client` library:

### Garbage Collection Metrics

#### `python_gc_objects_collected_total` (Counter)
- **Type**: Counter
- **Labels**: `generation` (0, 1, or 2)
- **Description**: Objects collected during garbage collection
- **Use Case**: Monitor garbage collection behavior and memory pressure

#### `python_gc_objects_uncollectable_total` (Counter)
- **Type**: Counter
- **Labels**: `generation`
- **Description**: Uncollectable objects found during GC
- **Use Case**: Detect memory leaks and circular references

#### `python_gc_collections_total` (Counter)
- **Type**: Counter
- **Labels**: `generation`
- **Description**: Number of times each GC generation was collected
- **Use Case**: Monitor GC pressure and frequency

### Process Metrics

#### `process_virtual_memory_bytes` (Gauge)
- **Type**: Gauge
- **Description**: Virtual memory size of the process
- **Units**: Bytes
- **Use Case**: Monitor memory address space

#### `process_resident_memory_bytes` (Gauge)
- **Type**: Gauge
- **Description**: Resident memory size (physical RAM actually in use)
- **Units**: Bytes
- **Use Case**: Monitor actual memory consumption

#### `process_cpu_seconds_total` (Counter)
- **Type**: Counter
- **Description**: Total user and system CPU time spent by the process
- **Units**: Seconds
- **Use Case**: Monitor CPU usage over time

#### `process_open_fds` (Gauge)
- **Type**: Gauge
- **Description**: Number of open file descriptors for the process
- **Units**: Count
- **Use Case**: Monitor system-level FD usage (complement to `open_fds_simulated`)

#### `process_max_fds` (Gauge)
- **Type**: Gauge
- **Description**: Maximum number of file descriptors the process can open
- **Units**: Count
- **Use Case**: Compare against open FDs to see headroom

#### `process_start_time_seconds` (Gauge)
- **Type**: Gauge
- **Description**: Unix timestamp when the process started
- **Units**: Seconds since epoch
- **Use Case**: Calculate process uptime

### Python Info Metrics

#### `python_info` (Gauge)
- **Type**: Gauge
- **Labels**: `implementation`, `major`, `minor`, `patchlevel`, `version`
- **Description**: Python platform information
- **Example**:
  ```
  python_info{implementation="CPython",major="3",minor="12",patchlevel="13",version="3.12.13"} 1.0
  ```
- **Use Case**: Identify Python version and implementation

---

## Metrics Collection Strategy

### Query Examples

**Check if CPU chaos is active:**
```
chaos_mode{mode="cpu"} == 1
```

**Monitor average request latency:**
```
rate(http_request_latency_seconds_sum{path="/health"}[5m]) / 
rate(http_request_latency_seconds_count{path="/health"}[5m])
```

**Alert on memory leaks exceeding threshold:**
```
leak_mb > 600
```

**Track request error rate:**
```
rate(http_requests_total{code!="200"}[5m]) / 
rate(http_requests_total[5m]) * 100
```

**Monitor FD exhaustion:**
```
open_fds_simulated / 5000 * 100  # Percentage of FD limit used
```

**Track database gate saturation:**
```
db_inflight / 10 * 100  # Percentage of DB inflight limit
```

---

## Recommended Dashboards

### System Health Dashboard
- `process_resident_memory_bytes` - Memory consumption
- `process_cpu_seconds_total` - CPU usage
- `process_open_fds` - System FD usage
- Request latency distribution (histogram)

### Chaos Injection Dashboard
- All `chaos_mode` gauges (shows active chaos modes)
- `leak_mb` - Current memory leak
- `open_fds_simulated` - Current FD leak
- `disk_fill_mb` - Current disk fill
- `db_inflight` - DB gate status

### Network Chaos Dashboard
- `chaos_mode{mode="net_latency"}` - Latency status
- `chaos_mode{mode="net_bandwidth"}` - Bandwidth status
- `chaos_mode{mode="net_reset_peer"}` - Connection reset status
- Request latency (should increase with network chaos)

### Reliability Dashboard
- `http_requests_total` by endpoint and status code
- `http_request_latency_seconds` histogram percentiles
- `retry_calls_total` success/failure breakdown
- `db_inflight` saturation

---

## Monitoring Tips

1. **Baseline Metrics**: Record normal operation metrics before enabling chaos
2. **Alert Thresholds**:
   - Memory: Alert at 70% of `CHAOS_MEM_LIMIT_MB`
   - FDs: Alert at 80% of `CHAOS_FD_LIMIT`
   - DB Inflight: Alert at 90% of `MAX_DB_INFLIGHT`
   - Request Latency: Alert when p95 exceeds 1 second

3. **Correlation Analysis**: 
   - Correlate `http_request_latency_seconds` with active `chaos_mode` values
   - Correlate `process_resident_memory_bytes` with `leak_mb`
   - Correlate `process_open_fds` with `open_fds_simulated`

4. **Time Series Analysis**:
   - Use PromQL to calculate rate of change: `rate(metric[5m])`
   - Use `increase()` for total accumulation over time windows
   - Use `deriv()` for instantaneous rate calculations
