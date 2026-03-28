# Metrics Fetching & Machine Learning Pipeline

This directory contains a complete system for collecting metrics from Prometheus at regular intervals and preparing them for machine learning analysis.

## Architecture

```
┌─────────────────┐
│   Prometheus    │  Metrics scraped every 5s
│   (9090)        │
└────────┬────────┘
         │
         │ HTTP API
         ▼
┌──────────────────────────┐
│  metrics_fetcher.py      │  Core fetcher
│  - PrometheusClient      │  - Instant queries
│  - MetricsCollector      │  - Range queries
│  - MetricsStream         │  - Continuous collection
└────────┬─────────────────┘
         │
         │ MetricPoint objects
         ▼
┌──────────────────────────┐
│  metrics_pipeline.py     │  Data processing
│  - MetricsBuffer         │  - Buffering
│  - MetricsDataframe      │  - Aggregation
│  - MetricsExporter       │  - Export (JSONL/CSV/JSON)
│  - MetricsAggregator     │  - Statistics
└────────┬─────────────────┘
         │
         │ Processed data
         ▼
┌──────────────────────────┐
│   Data Files             │
│  - metrics_*.jsonl       │  For streaming processing
│  - metrics_*.csv         │  For pandas/sklearn
│  - metrics_*.json        │  For ML pipeline
└──────────────────────────┘
         │
         ▼
┌──────────────────────────┐
│   ML Algorithm Layer     │  (Future: anomaly detection,
│   (placeholder)          │   forecasting, clustering)
└──────────────────────────┘
```

## Files

### 1. `metrics_fetcher.py` - Core Metrics Collection
Provides:
- **PrometheusClient**: Low-level API client
  - `is_healthy()`: Check if Prometheus is accessible
  - `instant_query(query)`: Get current metric values
  - `range_query(query, start, end, step)`: Get time series data
  - `parse_result(result)`: Parse API responses

- **MetricsCollector**: High-level collection interface
  - `collect_once()`: Single collection cycle
  - `collect_and_save()`: Collect and persist to file
  - `add_metric(name, query)`: Add custom metrics
  - `get_metrics_summary()`: Basic statistics

- **MetricsStream**: Continuous collection
  - `start()`: Begin continuous collection
  - `stop()`: Stop collection
  - Callback support for real-time processing

### 2. `metrics_pipeline.py` - Data Processing Pipeline
Provides:
- **MetricsBuffer**: In-memory buffering with circular queue
  - `add_metrics()`: Add metric batch
  - `get_last_n()`: Retrieve last N points
  - `save_to_jsonl()`: Persist to file

- **MetricsDataframe**: Convert to pandas DataFrame
  - `get_dataframe()`: Get DataFrame
  - `get_metric_values()`: Extract specific metric
  - `get_metric_timeseries()`: Get time series
  - `get_statistics()`: Compute statistics
  - `save_to_csv()`: Export to CSV

- **MetricsExporter**: Multi-format export
  - `export_jsonl()`: Line-delimited JSON
  - `export_csv()`: CSV format
  - `export_json_array()`: JSON array

- **MetricsAggregator**: Time-window aggregation
  - `aggregate_by_window()`: Group metrics by time windows
  - Compute mean, std, min, max per window

- **MetricsPipeline**: Complete pipeline orchestration
  - `run_collection()`: End-to-end collection and export
  - `analyze_collected_data()`: Statistical analysis

## Usage

### Installation

```bash
cd /Users/rekhanarasimha/Downloads/failure-zoo-4
pip install -r metrics_requirements.txt
```

### Basic Usage: Single Collection

```python
from metrics_fetcher import MetricsCollector

# Create collector
collector = MetricsCollector()

# Verify Prometheus is accessible
if not collector.client.is_healthy():
    print("ERROR: Prometheus not accessible")
    exit(1)

# Collect once
metrics = collector.collect_once()

# Print summary
summary = collector.get_metrics_summary(metrics)
print(summary)

# Save to file
filepath = collector.save_metrics(metrics)
```

### Streaming Collection

```python
from metrics_fetcher import MetricsCollector, MetricsStream

collector = MetricsCollector()

# Stream for 60 seconds (12 iterations at 5s interval)
stream = MetricsStream(
    collector,
    interval_seconds=5,
    max_iterations=12
)

# Optional: callback for real-time processing
def on_metrics(metrics):
    print(f"Collected {len(metrics)} metric types")

stream.start(on_metrics_callback=on_metrics)
```

### Complete Pipeline (Collect → Process → Export)

```python
from metrics_pipeline import MetricsPipeline

pipeline = MetricsPipeline(output_dir="./data/metrics_output")

# Collect for 120 seconds and export in multiple formats
exported_files = pipeline.run_collection(
    duration_seconds=120,
    interval_seconds=5,
    export_formats=['jsonl', 'csv', 'json']
)

print("Exported files:")
for fmt, path in exported_files.items():
    print(f"  {fmt}: {path}")

# Analyze
analysis = pipeline.analyze_collected_data()
print(f"Total points: {analysis['total_points']}")
print(f"Metrics: {analysis['unique_metrics']}")
for metric, stats in analysis['statistics'].items():
    print(f"  {metric}: mean={stats['mean']:.4f}, std={stats['std']:.4f}")
```

### Add Custom Metrics

```python
from metrics_fetcher import MetricsCollector

collector = MetricsCollector()

# Add custom PromQL queries
collector.add_metric("custom_p99_latency", 
    "histogram_quantile(0.99, rate(http_request_latency_seconds_bucket[5m]))")
collector.add_metric("custom_memory_percent",
    "container_memory_usage_bytes / container_spec_memory_limit_bytes * 100")

metrics = collector.collect_once()
collector.save_metrics(metrics)
```

### Convert to Pandas DataFrame

```python
from metrics_fetcher import MetricsCollector
from metrics_pipeline import MetricsDataframe

collector = MetricsCollector()
metrics = collector.collect_once()

# Convert to DataFrame
df_handler = MetricsDataframe(metrics)
df = df_handler.get_dataframe()

# Analyze
print(df.head())
print(df.describe())

# Get specific metric
latency_values = df_handler.get_metric_values('http_request_latency_p95')
print(f"P95 latency: {latency_values}")

# Time series for plotting
timestamps, values = df_handler.get_metric_timeseries('leak_mb')
print(f"Memory leak over time: {list(zip(timestamps, values))}")

# Export
df_handler.save_to_csv('./metrics_output.csv')
```

### Export in Multiple Formats

```python
from metrics_fetcher import MetricsCollector
from metrics_pipeline import MetricsExporter

collector = MetricsCollector()
metrics = collector.collect_once()

# Export as JSONL (one JSON per line, streaming-friendly)
MetricsExporter.export_jsonl(metrics, './metrics.jsonl')

# Export as CSV (tabular format)
MetricsExporter.export_csv(metrics, './metrics.csv')

# Export as JSON array (for APIs)
MetricsExporter.export_json_array(metrics, './metrics.json')
```

### Aggregate Metrics into Time Windows

```python
from metrics_fetcher import MetricsCollector
from metrics_pipeline import MetricsAggregator

collector = MetricsCollector()
metrics = collector.collect_once()

# Aggregate into 60-second windows
windowed = MetricsAggregator.aggregate_by_window(metrics, window_seconds=60)

for metric_name, windows in windowed.items():
    print(f"\n{metric_name}:")
    for window in windows:
        print(f"  Window {window['window_id']}: mean={window['mean']:.4f}, "
              f"std={window['std']:.4f}, count={window['count']}")
```

## Default Metrics Collected

| Metric | PromQL Query | Description |
|--------|--------------|-------------|
| `chaos_mode` | `chaos_mode` | Active chaos modes (0=off, 1=on) |
| `http_requests_total` | `rate(http_requests_total[1m])` | Requests per minute |
| `http_request_latency_p50` | `histogram_quantile(0.50, ...)` | Median latency |
| `http_request_latency_p95` | `histogram_quantile(0.95, ...)` | P95 latency |
| `http_request_latency_p99` | `histogram_quantile(0.99, ...)` | P99 latency |
| `http_error_rate` | Error rate percentage | Percentage of requests with 4xx/5xx |
| `leak_mb` | `leak_mb` | Memory leaked (MB) |
| `open_fds_simulated` | `open_fds_simulated` | Open file descriptors |
| `disk_fill_mb` | `disk_fill_mb` | Disk space filled (MB) |
| `db_inflight` | `db_inflight` | In-flight database operations |
| `container_cpu_rate` | `rate(container_cpu_usage_seconds_total[1m])` | CPU usage |
| `container_memory_mb` | `container_memory_usage_bytes / 1024 / 1024` | Memory used (MB) |
| `retry_calls_rate` | `rate(retry_calls_total[1m])` | Retry attempts per minute |
| `retry_calls_ok_rate` | `rate(retry_calls_total{result="ok"}[1m])` | Successful retries per minute |
| `retry_calls_failed_rate` | `rate(retry_calls_total{result="failed"}[1m])` | Failed retries per minute |

## Data Formats

### JSONL Format (metrics.jsonl)
```json
{"timestamp": 1234567890.0, "metric_name": "chaos_mode", "labels": {}, "value": 1.0}
{"timestamp": 1234567890.1, "metric_name": "http_requests_total", "labels": {"path": "/metrics"}, "value": 2.5}
{"timestamp": 1234567890.2, "metric_name": "leak_mb", "labels": {}, "value": 42.5}
```

### CSV Format (metrics.csv)
```csv
timestamp,metric_name,value,label_path,label_code
1234567890.0,chaos_mode,1.0,,
1234567890.1,http_requests_total,2.5,/metrics,200
1234567890.2,leak_mb,42.5,,
```

### JSON Array Format (metrics.json)
```json
[
  {"timestamp": 1234567890.0, "metric_name": "chaos_mode", "labels": {}, "value": 1.0},
  {"timestamp": 1234567890.1, "metric_name": "http_requests_total", "labels": {"path": "/metrics"}, "value": 2.5}
]
```

## Running Examples

### Command Line Examples

```bash
# Single collection
python metrics_fetcher.py 1

# Streaming collection (60 seconds)
python metrics_fetcher.py 2

# Custom metrics
python metrics_fetcher.py 3

# Complete pipeline
python metrics_pipeline.py
```

### Programmatic Examples

Create `my_experiment.py`:

```python
from metrics_pipeline import MetricsPipeline
from metrics_fetcher import MetricsCollector, MetricsStream

# Example 1: Simple collection
print("Example 1: Single Collection")
collector = MetricsCollector()
metrics = collector.collect_once()
print(f"Collected {len(metrics)} metric types")

# Example 2: Complete pipeline
print("\nExample 2: Complete Pipeline")
pipeline = MetricsPipeline()
files = pipeline.run_collection(
    duration_seconds=60,
    interval_seconds=5,
    export_formats=['jsonl', 'csv', 'json']
)
print(f"Exported to: {files}")

# Example 3: Analysis
print("\nExample 3: Analysis")
analysis = pipeline.analyze_collected_data()
print(f"Total data points: {analysis['total_points']}")
for metric, stats in analysis['statistics'].items():
    print(f"{metric}: mean={stats['mean']:.4f}")
```

Then run:
```bash
python my_experiment.py
```

## Error Handling

### Common Issues

**Issue**: `connection refused` on Prometheus
```python
if not collector.client.is_healthy():
    print("Prometheus is not accessible")
    # Make sure: docker compose up -d
```

**Issue**: No metrics found
```
# Run an experiment to generate metrics first
docker compose run --rm chaos cpu on 2
sleep 30
docker compose run --rm chaos cpu off
```

**Issue**: Import errors
```bash
pip install -r metrics_requirements.txt
```

## Performance Notes

- **Collection interval**: 5 seconds (matches Prometheus scrape interval)
- **Buffer size**: 5000 points by default (circular, removes oldest when full)
- **Query timeout**: 10 seconds per query
- **Typical memory per point**: ~200 bytes

For 24-hour continuous collection at 5-second intervals:
- ~17,280 measurements per metric
- Default 15 metrics = ~260k points
- Approx 50-100 MB in memory depending on label cardinality

## Next Steps: Machine Learning

Once you have metrics collected, the data is ready for:

1. **Anomaly Detection**
   - Isolation Forests
   - One-Class SVM
   - LOF (Local Outlier Factor)

2. **Time Series Forecasting**
   - ARIMA
   - Prophet
   - LSTM/RNNs

3. **Clustering**
   - K-means
   - DBSCAN
   - Hierarchical clustering

4. **Classification**
   - Identify failure modes
   - Detect chaos injection
   - Predict service degradation

See `metrics_ml.py` (coming soon) for implementations.

## File Organization

```
./data/metrics_output/
├── metrics_20240328_101530.jsonl      # Raw JSONL export
├── metrics_20240328_101530.csv        # CSV export for analysis
├── metrics_20240328_101530.json       # JSON array export
└── metrics_analysis.json              # Statistical summary
```

All files are timestamped for easy tracking and can be archived for historical analysis.

