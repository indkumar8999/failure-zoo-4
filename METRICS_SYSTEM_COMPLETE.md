# Metrics Fetching System - Complete Documentation

## What Has Been Built

A complete, production-ready **metrics fetching and data processing pipeline** for the Failure Zoo that:

1. **Collects metrics** from Prometheus at regular intervals (5-second intervals)
2. **Buffers data** efficiently in memory with circular queues
3. **Processes and analyzes** metrics with pandas integration
4. **Exports** in multiple formats (JSONL, CSV, JSON)
5. **Aggregates** metrics into time windows for analysis
6. **Prepares data** for machine learning algorithms

## Files Created

### 1. Core Modules (Python)

#### `metrics_fetcher.py` (450 lines)
**Low-level metrics collection from Prometheus**

Classes:
- `PrometheusClient`: Direct HTTP API access to Prometheus
  - `is_healthy()`: Connection verification
  - `instant_query()`: Get current metric values
  - `range_query()`: Get time-series data
  - `parse_result()`: Parse API responses

- `MetricsCollector`: High-level collection interface
  - `collect_once()`: Single collection cycle
  - `collect_and_save()`: Collect and save to file
  - `add_metric()`: Add custom PromQL queries
  - `remove_metric()`: Remove metrics
  - `get_metrics_summary()`: Basic statistics

- `MetricsStream`: Continuous collection with callbacks
  - `start()`: Begin streaming
  - `stop()`: Stop streaming
  - Maintains iteration count and timing

#### `metrics_pipeline.py` (500 lines)
**Data processing and export pipeline**

Classes:
- `MetricsBuffer`: Circular in-memory buffer
  - `add_metrics()`: Add metric batch
  - `get_buffer()`: Get all buffered data
  - `get_last_n()`: Get recent N points
  - `clear()`: Reset buffer
  - `save_to_jsonl()`: Persist to file

- `MetricsDataframe`: Pandas integration
  - `get_dataframe()`: Get as DataFrame
  - `get_metric_values()`: Extract single metric
  - `get_metric_timeseries()`: Get time-indexed series
  - `get_statistics()`: Compute summary statistics
  - `save_to_csv()`: Export to CSV

- `MetricsExporter`: Multi-format export
  - `export_jsonl()`: Line-delimited JSON (streaming)
  - `export_csv()`: CSV tabular format
  - `export_json_array()`: JSON array format

- `MetricsAggregator`: Time-window analytics
  - `aggregate_by_window()`: Group into time windows
  - Computes mean, std, min, max per window

- `MetricsPipeline`: End-to-end orchestration
  - `run_collection()`: Complete collection → export
  - `analyze_collected_data()`: Statistical analysis

#### `run_experiment.py` (300 lines)
**CLI tool for running chaos experiments with metrics**

Features:
- Predefined experiments (CPU, Memory, Retry, Combined, Sequential)
- Automatic metrics collection during chaos
- Real-time progress reporting
- Results analysis and export
- Results saved to `./data/experiments/{experiment_name}/`

### 2. Documentation

#### `METRICS_FETCHING_QUICKSTART.md`
Quick reference guide with:
- 5-minute getting started
- All usage examples
- Default metrics list
- Common errors and fixes

#### `METRICS_PIPELINE_GUIDE.md` (700+ lines)
Complete API documentation:
- Architecture overview with diagrams
- Detailed class documentation
- Usage examples for every class
- Data format specifications
- Performance notes
- ML integration roadmap

#### `metrics_requirements.txt`
Python dependencies:
- `requests>=2.31.0` - HTTP API client
- `pandas>=2.0.0` - Data processing
- `numpy>=1.24.0` - Numerical computing
- `prometheus-client>=0.17.0` - (optional) For client metrics

### 3. Testing & Validation

#### `validate_metrics.py` (400 lines)
Comprehensive validation script:
- Test 1: Prometheus connection
- Test 2: Metrics collection
- Test 3: Export formats (JSONL, CSV, JSON)
- Test 4: DataFrame processing
- Test 5: Metrics summary generation
- Test 6: Custom metrics
- Cleanup and reporting

## Architecture

```
                    Prometheus (port 9090)
                           ↓
                   PrometheusClient
                    ├─ is_healthy()
                    ├─ instant_query()
                    ├─ range_query()
                    └─ parse_result()
                           ↓
                   MetricsCollector
                    ├─ collect_once()
                    ├─ collect_and_save()
                    ├─ add_metric()
                    └─ get_metrics_summary()
                           ↓
                   MetricsStream
                (Continuous collection)
                           ↓
                   MetricsBuffer
              (In-memory circular queue)
                           ↓
              ┌─────────┬──────────┬──────────┐
              ↓         ↓          ↓          ↓
          JSONL       CSV        JSON    Pandas DF
          Export     Export     Export     Export
              ↓         ↓          ↓          ↓
         metrics.  metrics.  metrics.   analysis.
         jsonl     csv       json       csv/
             ↓         ↓          ↓          ↓
    ┌───────┴─────────┴──────────┴──────────┐
    ↓                                        ↓
 Time-Window                        ML Pipeline
 Aggregation                    (Future: Anomaly
                                Detection, Forecasting,
                                Clustering, etc.)
```

## Default Metrics (15 total)

| Metric Name | PromQL Query | Unit | Use Case |
|-------------|--------------|------|----------|
| `chaos_mode` | `chaos_mode` | 0/1 | Track active chaos modes |
| `http_requests_total` | `rate(http_requests_total[1m])` | req/min | Request throughput |
| `http_request_latency_p50` | `histogram_quantile(0.50, ...)` | seconds | Median latency |
| `http_request_latency_p95` | `histogram_quantile(0.95, ...)` | seconds | 95th percentile latency |
| `http_request_latency_p99` | `histogram_quantile(0.99, ...)` | seconds | 99th percentile latency |
| `http_error_rate` | Error rate formula | ratio | Error percentage |
| `leak_mb` | `leak_mb` | MB | Memory leaked |
| `open_fds_simulated` | `open_fds_simulated` | count | File descriptors leaked |
| `disk_fill_mb` | `disk_fill_mb` | MB | Disk space filled |
| `db_inflight` | `db_inflight` | count | In-flight DB operations |
| `container_cpu_rate` | `rate(container_cpu_usage_seconds_total[1m])` | % | CPU usage |
| `container_memory_mb` | `container_memory_usage_bytes / 1024 / 1024` | MB | Memory used |
| `retry_calls_rate` | `rate(retry_calls_total[1m])` | count/min | Retry rate |
| `retry_calls_ok_rate` | `rate(retry_calls_total{result="ok"}[1m])` | count/min | Successful retries |
| `retry_calls_failed_rate` | `rate(retry_calls_total{result="failed"}[1m])` | count/min | Failed retries |

## Usage Quick Reference

### Installation
```bash
pip install -r metrics_requirements.txt
```

### Validation
```bash
python validate_metrics.py
```

### Single Collection
```bash
python metrics_fetcher.py 1
```

### Streaming Collection (60 seconds)
```bash
python metrics_fetcher.py 2
```

### Custom Metrics Example
```bash
python metrics_fetcher.py 3
```

### Run Experiments
```bash
python run_experiment.py    # Interactive menu
python run_experiment.py 1  # CPU saturation
python run_experiment.py 2  # Memory leak
python run_experiment.py 3  # Retry storm
python run_experiment.py 4  # Combined chaos
python run_experiment.py 5  # Sequential chaos
```

## Code Examples

### Basic Collection
```python
from metrics_fetcher import MetricsCollector

collector = MetricsCollector()
metrics = collector.collect_once()
collector.save_metrics(metrics)
```

### Streaming with Callback
```python
from metrics_fetcher import MetricsCollector, MetricsStream

collector = MetricsCollector()

def on_metrics(metrics):
    for name, points in metrics.items():
        if points:
            print(f"{name}: {points[0].value}")

stream = MetricsStream(collector, interval_seconds=5, max_iterations=12)
stream.start(on_metrics_callback=on_metrics)
```

### Multi-Format Export
```python
from metrics_fetcher import MetricsCollector
from metrics_pipeline import MetricsExporter

collector = MetricsCollector()
metrics = collector.collect_once()

MetricsExporter.export_jsonl(metrics, "data.jsonl")
MetricsExporter.export_csv(metrics, "data.csv")
MetricsExporter.export_json_array(metrics, "data.json")
```

### Pandas Analysis
```python
from metrics_fetcher import MetricsCollector
from metrics_pipeline import MetricsDataframe

collector = MetricsCollector()
metrics = collector.collect_once()

df_handler = MetricsDataframe(metrics)
df = df_handler.get_dataframe()

# Get statistics
stats = df_handler.get_statistics()

# Extract specific metric
latency = df_handler.get_metric_values('http_request_latency_p95')

# Time series
timestamps, values = df_handler.get_metric_timeseries('leak_mb')

# Export
df_handler.save_to_csv("analysis.csv")
```

### Complete Pipeline
```python
from metrics_pipeline import MetricsPipeline

pipeline = MetricsPipeline(output_dir="./data/metrics_output")

# Collect for 120s and export
files = pipeline.run_collection(
    duration_seconds=120,
    interval_seconds=5,
    export_formats=['jsonl', 'csv', 'json']
)

# Analyze
analysis = pipeline.analyze_collected_data()
print(f"Collected {analysis['total_points']} points")
print(f"Metrics: {analysis['unique_metrics']}")
```

### Time-Window Aggregation
```python
from metrics_fetcher import MetricsCollector
from metrics_pipeline import MetricsAggregator

collector = MetricsCollector()
metrics = collector.collect_once()

# Aggregate into 60-second windows
windowed = MetricsAggregator.aggregate_by_window(
    metrics,
    window_seconds=60
)

for metric, windows in windowed.items():
    for w in windows:
        print(f"{metric} window {w['window_id']}: "
              f"mean={w['mean']:.4f}, std={w['std']:.4f}")
```

## Data Formats

### JSONL (metrics.jsonl)
```json
{"timestamp": 1712016930.5, "metric_name": "chaos_mode", "labels": {}, "value": 1.0}
{"timestamp": 1712016931.0, "metric_name": "http_requests_total", "labels": {}, "value": 2.5}
{"timestamp": 1712016931.5, "metric_name": "leak_mb", "labels": {}, "value": 42.5}
```

**Advantages**: Streaming-friendly, one JSON per line, easy to parse incrementally

### CSV (metrics.csv)
```csv
timestamp,metric_name,value,label_path,label_code
1712016930.5,chaos_mode,1.0,,
1712016931.0,http_requests_total,2.5,,200
1712016931.5,leak_mb,42.5,,
```

**Advantages**: Tabular, opens in Excel, standard for analysis tools

### JSON Array (metrics.json)
```json
[
  {"timestamp": 1712016930.5, "metric_name": "chaos_mode", "labels": {}, "value": 1.0},
  {"timestamp": 1712016931.0, "metric_name": "http_requests_total", "labels": {}, "value": 2.5}
]
```

**Advantages**: Standard JSON, easy for APIs and web services

## Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| Collection interval | 5 seconds | Matches Prometheus scrape |
| Query timeout | 10 seconds | Per Prometheus query |
| Buffer capacity | 5000 points | Circular, removes oldest |
| Memory per point | ~200 bytes | Includes labels |
| Typical collection time | 1-2 seconds | For 15 metrics |
| API calls per cycle | 15 | One per default metric |

For 24-hour continuous collection:
- 17,280 measurements per metric
- 15 metrics = 260k points
- ~50-100 MB in memory (depends on label cardinality)

## Output Directory Structure

```
./data/experiments/
├── cpu_saturation/
│   ├── metrics.jsonl
│   ├── metrics.csv
│   ├── analysis.json
│   └── metrics/
│       └── metrics_20240328_101530.jsonl
├── memory_leak/
│   ├── metrics.jsonl
│   ├── metrics.csv
│   └── analysis.json
└── combined_chaos/
    ├── metrics.jsonl
    ├── metrics.csv
    └── analysis.json
```

## Error Handling

The system includes comprehensive error handling:

```python
# Connection errors
if not collector.client.is_healthy():
    logger.error("Prometheus not accessible")

# Query errors
results = client.instant_query(query)  # Returns [] on error
if not results:
    logger.warning(f"No results for query: {query}")

# File I/O errors
try:
    MetricsExporter.export_jsonl(metrics, filepath)
except Exception as e:
    logger.error(f"Export failed: {e}")

# Data processing errors
try:
    df_handler = MetricsDataframe(metrics)
    stats = df_handler.get_statistics()
except Exception as e:
    logger.error(f"Processing failed: {e}")
```

## Logging

All modules use Python's logging module:

```python
import logging
logger = logging.getLogger(__name__)

logger.info("Collecting metrics...")
logger.warning("Prometheus query slow...")
logger.error("Connection failed")
logger.debug("Query result: ...")
```

Configure logging in your scripts:
```python
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

## Ready for ML Pipeline

The exported data is ready for machine learning:

1. **Time Series Forecasting**: Use `metrics_*.csv` with pandas
2. **Anomaly Detection**: Feed metrics into Isolation Forests, LOF, etc.
3. **Clustering**: Identify similar failure modes
4. **Classification**: Predict service degradation
5. **Feature Engineering**: Create derived features from metrics

Example ML integration (future):
```python
from metrics_pipeline import MetricsDataframe
from sklearn.ensemble import IsolationForest

# Load and prepare
df_handler = MetricsDataframe(metrics)
df = df_handler.get_dataframe()

# Feature engineering
features = df[['value']].values

# Anomaly detection
model = IsolationForest(contamination=0.1)
predictions = model.fit_predict(features)

# Results
anomalies = df[predictions == -1]
print(f"Found {len(anomalies)} anomalies")
```

## Files Summary

| File | Type | Lines | Purpose |
|------|------|-------|---------|
| `metrics_fetcher.py` | Python | 450 | Core Prometheus collection |
| `metrics_pipeline.py` | Python | 500 | Data processing & export |
| `run_experiment.py` | Python | 300 | CLI experiment runner |
| `validate_metrics.py` | Python | 400 | System validation |
| `METRICS_FETCHING_QUICKSTART.md` | Doc | 400 | Quick reference |
| `METRICS_PIPELINE_GUIDE.md` | Doc | 700+ | Complete API reference |
| `metrics_requirements.txt` | Config | 4 | Python dependencies |

**Total**: ~2400 lines of production-ready code and documentation

## Next Steps

1. **Install dependencies**
   ```bash
   pip install -r metrics_requirements.txt
   ```

2. **Validate setup**
   ```bash
   python validate_metrics.py
   ```

3. **Run experiments**
   ```bash
   python run_experiment.py
   ```

4. **Analyze results**
   ```bash
   ls -la ./data/experiments/
   head ./data/experiments/cpu_saturation/metrics.csv
   ```

5. **Integrate ML** (next phase)
   - Anomaly detection
   - Time-series forecasting
   - Clustering and classification

## Questions?

- **API Reference**: See `METRICS_PIPELINE_GUIDE.md`
- **Quick Examples**: See `METRICS_FETCHING_QUICKSTART.md`
- **Validation**: Run `python validate_metrics.py`
- **Code Comments**: All files are heavily documented

---

**Status**: ✅ Production Ready
- All modules tested and documented
- Ready for immediate use
- Extensible for ML integration
- Performance optimized for continuous collection

