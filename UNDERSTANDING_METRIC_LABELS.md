# Understanding Metric Labels: `instance` and Other Labels

## Quick Answer

The `instance` label in metrics tells you **which service/server** the metric came from. For example:

- `instance: app:8000` → Metric from the **app container** on port 8000
- `instance: cadvisor:8080` → Metric from the **cAdvisor container** on port 8080  
- `instance: prometheus:9090` → Metric from **Prometheus** on port 9090

---

## What Are Metric Labels?

In Prometheus/metrics, each data point has:
1. **Metric Name** - What is being measured (e.g., `cpu_usage`, `memory_mb`)
2. **Value** - The actual measurement (e.g., 42.5)
3. **Labels** - Key-value pairs that add context/filtering capability

```
Example metric:
  Name: container_memory_mb
  Value: 921.73 MB
  Labels: {
    instance: cadvisor:8080,    ← Which source
    job: cadvisor,              ← Job name
    id: /docker                 ← Container ID
  }
```

---

## Label Meanings in Failure Zoo

### Standard Labels (All Metrics)

| Label | Meaning | Example |
|-------|---------|---------|
| `instance` | The service/host:port where metric comes from | `app:8000`, `cadvisor:8080` |
| `job` | Job name (identifies scrape config in Prometheus) | `app`, `cadvisor` |

### Application-Specific Labels (from `app:8000`)

| Label | Metrics | Meaning | Example |
|-------|---------|---------|---------|
| `mode` | `chaos_mode` | Chaos injection mode | `cpu`, `mem_leak`, `lock_convoy` |
| `path` | `http_requests_total`, `http_request_latency` | HTTP endpoint path | `/health`, `/metrics`, `/db/slow` |
| `code` | `http_requests_total` | HTTP response code | `200`, `400`, `500` |
| `endpoint` | `retry_calls_total` | Downstream endpoint | `/ok`, `/flaky` |
| `result` | `retry_calls_total` | Retry result type | `ok`, `failed`, `exception` |

### Container Metrics Labels (from `cadvisor:8080`)

| Label | Metrics | Meaning | Example |
|-------|---------|---------|---------|
| `id` | `container_cpu_rate`, `container_memory_mb` | Container/cgroup path | `/`, `/docker`, `/docker/failure-zoo-4-app-1` |
| `cpu` | `container_cpu_rate` | CPU identifier | `total`, `0`, `1` |
| `name` | Container metrics | Container name | `failure-zoo-4-app-1` |

---

## Real Examples from Failure Zoo

### Example 1: Application Chaos Metric
```python
MetricPoint(
    metric_name='chaos_mode',
    value=1.0,
    labels={
        'instance': 'app:8000',      # From app container
        'job': 'app',
        'mode': 'cpu'                # CPU chaos is active
    }
)
```
**Interpretation**: CPU chaos is currently enabled on the app container

---

### Example 2: Application HTTP Request Metric
```python
MetricPoint(
    metric_name='http_requests_total',
    value=150.5,
    labels={
        'instance': 'app:8000',      # From app container
        'job': 'app',
        'path': '/metrics',          # Metrics endpoint
        'code': '200'                # All requests succeeded
    }
)
```
**Interpretation**: 150.5 requests/min to `/metrics` endpoint with 200 status

---

### Example 3: Container CPU Metric from cAdvisor
```python
MetricPoint(
    metric_name='container_cpu_rate',
    value=0.757969,
    labels={
        'instance': 'cadvisor:8080',        # From cAdvisor
        'job': 'cadvisor',
        'id': '/docker',                    # Docker cgroup
        'cpu': 'total'                      # Total across all CPUs
    }
)
```
**Interpretation**: Docker containers are using 75.79% of total CPU

---

### Example 4: Specific Container Memory Metric
```python
MetricPoint(
    metric_name='container_memory_mb',
    value=921.73,
    labels={
        'instance': 'cadvisor:8080',                    # From cAdvisor
        'job': 'cadvisor',
        'id': '/docker/failure-zoo-4-app-1',          # Specific container
        'name': 'failure-zoo-4-app-1'                 # Container name
    }
)
```
**Interpretation**: The app container is using 921.73 MB of memory

---

### Example 5: Retry Storm Metric
```python
MetricPoint(
    metric_name='retry_calls_total',
    value=50.0,
    labels={
        'instance': 'app:8000',
        'job': 'app',
        'endpoint': '/flaky',           # Which downstream endpoint
        'result': 'ok'                  # Successful responses
    }
)
```
**Interpretation**: 50 successful retries/min to the `/flaky` endpoint

---

## Why Labels Matter

Labels allow you to:

1. **Filter metrics** in Prometheus/Grafana
   ```promql
   # Get CPU only from app container
   container_cpu_rate{instance="app:8000"}
   
   # Get errors only
   http_requests_total{code="500"}
   
   # Get CPU chaos mode
   chaos_mode{mode="cpu"}
   ```

2. **Compare across services**
   ```promql
   # Compare memory between app and cadvisor
   container_memory_mb{instance=~"app:8000|cadvisor:8080"}
   ```

3. **Aggregate data**
   ```promql
   # Total requests across all endpoints
   sum(http_requests_total) by (instance)
   ```

4. **Export and filter in CSV/JSONL**
   ```
   # You'll see columns like: label_instance, label_job, label_mode, etc.
   timestamp,metric_name,value,label_instance,label_job,label_mode
   1234567890,chaos_mode,1.0,app:8000,app,cpu
   ```

---

## Instance vs Job

### `job`
- **Defined in Prometheus config** (`prometheus.yml`)
- Groups related scrape targets
- Example: `job: "app"` collects all metrics from the app job

### `instance`
- **Derived from target address** (what Prometheus scrapes)
- Usually `hostname:port` or `service:port`
- Example: `instance: "app:8000"` is the actual address being scraped

### In This System

```yaml
# From prometheus.yml
scrape_configs:
  - job_name: "app"
    static_configs:
      - targets: ["app:8000"]      # This becomes instance: app:8000
  
  - job_name: "cadvisor"
    static_configs:
      - targets: ["cadvisor:8080"]  # This becomes instance: cadvisor:8080
```

---

## What `cadvisor:8080` Specifically Means

`instance: cadvisor:8080` means:

1. **Source**: Metrics came from **cAdvisor** (container metrics exporter)
2. **Address**: Running on `cadvisor` (Docker container name) at port `8080`
3. **Type of metrics**: Container-level metrics like:
   - CPU usage by container
   - Memory usage by container
   - Network I/O
   - Disk I/O
   - Container processes

### Metrics with `instance: cadvisor:8080`
- `container_cpu_usage_seconds_total`
- `container_memory_usage_bytes`
- `container_network_*`
- `container_fs_*`

### Metrics with `instance: app:8000`
- `chaos_mode`
- `http_requests_total`
- `http_request_latency_*`
- `leak_mb`
- `open_fds_simulated`
- `db_inflight`
- `retry_calls_total`

---

## Container IDs in cAdvisor Metrics

When you see `id: "/docker/failure-zoo-4-app-1"`, this is:

- `/` = Root (host)
- `/docker` = All Docker containers
- `/docker/failure-zoo-4-app-1` = Specific container (failure zoo app)
- `/restricted` = Restricted resources

### Common `id` Values

| Value | Meaning |
|-------|---------|
| `/` | Host/root system |
| `/docker` | All Docker containers aggregate |
| `/docker/{container_name}` | Specific container |
| `/sys/fs/cgroup/...` | Cgroup path |

---

## Querying by Instance in Your Scripts

### In Python
```python
from metrics_fetcher import MetricsCollector

collector = MetricsCollector()
metrics = collector.collect_once()

# Filter by instance
for metric_name, points in metrics.items():
    for point in points:
        # Get only app metrics
        if point.metric_labels.get('instance') == 'app:8000':
            print(f"{metric_name}: {point.value}")
        
        # Get only cAdvisor metrics
        if point.metric_labels.get('instance') == 'cadvisor:8080':
            print(f"{metric_name}: {point.value}")
```

### In Prometheus
```promql
# App metrics only
{instance="app:8000"}

# cAdvisor metrics only
{instance="cadvisor:8080"}

# Specific container
container_memory_mb{id="/docker/failure-zoo-4-app-1"}

# CPU chaos mode
chaos_mode{mode="cpu"}
```

### In CSV/Pandas
```python
import pandas as pd

df = pd.read_csv("metrics.csv")

# App metrics only
app_metrics = df[df['label_instance'] == 'app:8000']

# cAdvisor metrics only
cadvisor_metrics = df[df['label_instance'] == 'cadvisor:8080']

# App chaos metrics
chaos = df[df['label_mode'] == 'cpu']
```

---

## Summary Table

| Instance | Source | Metrics | Purpose |
|----------|--------|---------|---------|
| `app:8000` | Failure Zoo App | chaos_mode, http_*, leak_mb, db_inflight, retry_* | Application behavior, chaos status |
| `cadvisor:8080` | cAdvisor Container | container_cpu_*, container_memory_* | Container resource usage |
| `localhost:8080` | cAdvisor (if local) | container_* | Same as cadvisor:8080 |
| `prometheus:9090` | Prometheus | up, scrape_* | Prometheus internals (if scraped) |

---

## Common Use Cases

### Q: "I want to see how much CPU the app container is using"
```python
# In metrics
for point in metrics['container_cpu_rate']:
    if point.metric_labels['instance'] == 'cadvisor:8080':
        if 'failure-zoo-4-app-1' in point.metric_labels['id']:
            print(f"App CPU: {point.value:.2%}")
```

### Q: "Is chaos currently enabled?"
```python
# In metrics
for point in metrics['chaos_mode']:
    if point.metric_labels['instance'] == 'app:8000':
        mode = point.metric_labels['mode']
        enabled = point.value == 1.0
        print(f"{mode}: {enabled}")
```

### Q: "How many HTTP requests per minute?"
```python
# In metrics
for point in metrics['http_requests_total']:
    if point.metric_labels['instance'] == 'app:8000':
        path = point.metric_labels['path']
        code = point.metric_labels['code']
        print(f"{path} ({code}): {point.value:.1f} req/min")
```

---

## Reference: All Instances in Your System

```
┌─────────────────────────────────────┐
│      Your Failure Zoo System        │
├─────────────────────────────────────┤
│                                     │
│  ┌──────────────────────────────┐  │
│  │ App Container                │  │
│  │ instance: app:8000           │  │
│  │                              │  │
│  │ • Chaos mode                 │  │
│  │ • HTTP metrics               │  │
│  │ • Resource leaks             │  │
│  └──────────────────────────────┘  │
│                                     │
│  ┌──────────────────────────────┐  │
│  │ cAdvisor Container           │  │
│  │ instance: cadvisor:8080      │  │
│  │                              │  │
│  │ • CPU usage                  │  │
│  │ • Memory usage               │  │
│  │ • All containers             │  │
│  └──────────────────────────────┘  │
│                                     │
│  ┌──────────────────────────────┐  │
│  │ Prometheus                   │  │
│  │ instance: prometheus:9090    │  │
│  │                              │  │
│  │ • Scrapes app:8000           │  │
│  │ • Scrapes cadvisor:8080      │  │
│  └──────────────────────────────┘  │
│                                     │
└─────────────────────────────────────┘
```

---

## Key Takeaway

**The `instance` label tells you which service produced that metric.**

- `instance: app:8000` = App container metrics
- `instance: cadvisor:8080` = Container resource metrics
- These combined give you **application behavior + system resource usage**

This is how you correlate what your app is doing with the underlying system resources it's consuming!

