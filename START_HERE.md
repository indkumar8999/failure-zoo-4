# 🚀 START HERE - Metrics Fetching System Guide

Welcome! This document is your entry point to the metrics collection and ML pipeline system.

---

## ⚡ 60-Second Start

```bash
# 1. Install dependencies
pip install -r metrics_requirements.txt

# 2. Validate system works
python validate_metrics.py

# 3. Run an experiment with metrics
python run_experiment.py

# 4. Check results
ls ./data/experiments/
head ./data/experiments/cpu_saturation/metrics.csv
```

**Done!** You're collecting metrics. 🎉

---

## 📚 Documentation Map

Choose your path based on what you want to do:

### 🏃 "I want to get started NOW"
→ Read: **This file** + run the 60-second start above

### 🎯 "I want to understand the system"
→ Read: `SYSTEM_SUMMARY.md` (quick overview) or `INDEX.md` (comprehensive)

### 📖 "I want complete documentation"
→ Read: `METRICS_PIPELINE_GUIDE.md` (full API reference)

### 🔨 "I want to use it in my code"
→ Read: `METRICS_FETCHING_QUICKSTART.md` (all examples)

### 📂 "I want to know what files were created"
→ Read: `README_METRICS.md` (file organization)

---

## 🎯 What This System Does

```
Prometheus Metrics (every 5 seconds)
        ↓
Collects 15+ metrics automatically
        ↓
Processes & buffers in memory
        ↓
Exports in 3 formats (JSONL, CSV, JSON)
        ↓
Ready for analysis & machine learning
```

---

## 📦 What You Get

### Python Modules (Ready to use)
1. `metrics_fetcher.py` - Collect metrics from Prometheus
2. `metrics_pipeline.py` - Process and export data
3. `run_experiment.py` - Run chaos experiments with metrics
4. `validate_metrics.py` - Test the system

### Documentation (Get help)
5. `METRICS_FETCHING_QUICKSTART.md` - Quick examples
6. `METRICS_PIPELINE_GUIDE.md` - Complete reference
7. `METRICS_SYSTEM_COMPLETE.md` - Full overview
8. `INDEX.md` - Main entry point

### Configuration
9. `metrics_requirements.txt` - Install dependencies

---

## ✅ Minimal Setup (5 minutes)

### Step 1: Install
```bash
pip install -r metrics_requirements.txt
```

### Step 2: Test
```bash
python validate_metrics.py
```

Expected output:
```
✓ PASS: Connection
✓ PASS: Collection
✓ PASS: Export
✓ PASS: Dataframe
✓ PASS: Summary
✓ PASS: Custom
```

### Step 3: Use
Pick one:

**Option A: Run an experiment**
```bash
python run_experiment.py 1  # CPU saturation with metrics
```

**Option B: Collect metrics once**
```bash
python metrics_fetcher.py 1
```

**Option C: Stream for 60 seconds**
```bash
python metrics_fetcher.py 2
```

### Step 4: Check results
```bash
ls ./data/experiments/
cat ./data/experiments/cpu_saturation/metrics.csv
```

---

## 💡 3 Main Use Cases

### Use Case 1: Run Chaos + Collect Metrics
```bash
python run_experiment.py
# Choose: 1-5 for different chaos types
# Results saved to ./data/experiments/{name}/
```

**Best for:** Correlating metrics with chaos injection

---

### Use Case 2: Quick Metrics Collection
```python
from metrics_fetcher import MetricsCollector

collector = MetricsCollector()
metrics = collector.collect_once()
collector.save_metrics(metrics)
# Output: metrics_TIMESTAMP.jsonl
```

**Best for:** Getting current metrics snapshot

---

### Use Case 3: Analysis & Export
```python
from metrics_fetcher import MetricsCollector
from metrics_pipeline import MetricsDataframe, MetricsExporter

collector = MetricsCollector()
metrics = collector.collect_once()

# Export multiple formats
MetricsExporter.export_jsonl(metrics, "data.jsonl")
MetricsExporter.export_csv(metrics, "data.csv")

# Analyze with pandas
df_handler = MetricsDataframe(metrics)
stats = df_handler.get_statistics()
print(stats)
```

**Best for:** Data analysis and preparation for ML

---

## 📊 Metrics Collected

**15 metrics, automatically:**

| Type | Metrics | Examples |
|------|---------|----------|
| Chaos | chaos_mode | 0 = off, 1 = on |
| HTTP | requests, latency, errors | req/min, seconds, % |
| Resources | memory, fds, disk | MB, count, MB |
| DB | inflight operations | count |
| Container | CPU, memory | %, MB |

All with timestamps and labels for filtering.

---

## 📁 Where Is My Data?

```
After running experiments:
./data/experiments/
├── cpu_saturation/
│   ├── metrics.jsonl          ← Raw data
│   ├── metrics.csv            ← For analysis
│   └── analysis.json          ← Statistics
├── memory_leak/
├── retry_storm/
└── combined_chaos/
```

Each format optimized for different purposes:
- **JSONL**: Streaming, line-by-line processing
- **CSV**: Excel, pandas, analysis tools
- **JSON**: APIs, web services

---

## 🚀 Common Commands

```bash
# Single collection
python metrics_fetcher.py 1

# Streaming (60 seconds)
python metrics_fetcher.py 2

# Custom metrics example
python metrics_fetcher.py 3

# Validate system
python validate_metrics.py

# Run experiment (interactive)
python run_experiment.py

# Run specific experiment
python run_experiment.py 1  # CPU
python run_experiment.py 2  # Memory
python run_experiment.py 3  # Retry
python run_experiment.py 4  # Combined
python run_experiment.py 5  # Sequential
```

---

## 💻 Code Examples

### Example 1: Collect Metrics (5 lines)
```python
from metrics_fetcher import MetricsCollector

collector = MetricsCollector()
metrics = collector.collect_once()
collector.save_metrics(metrics)
```

### Example 2: Stream Metrics (8 lines)
```python
from metrics_fetcher import MetricsCollector, MetricsStream

collector = MetricsCollector()
stream = MetricsStream(collector, max_iterations=12)  # 60 seconds
stream.start()
```

### Example 3: Export Formats (5 lines)
```python
from metrics_fetcher import MetricsCollector
from metrics_pipeline import MetricsExporter

metrics = MetricsCollector().collect_once()
MetricsExporter.export_jsonl(metrics, "data.jsonl")
MetricsExporter.export_csv(metrics, "data.csv")
```

### Example 4: Analyze Data (6 lines)
```python
from metrics_pipeline import MetricsDataframe
from metrics_fetcher import MetricsCollector

metrics = MetricsCollector().collect_once()
df = MetricsDataframe(metrics).get_dataframe()
print(df.describe())
print(MetricsDataframe(metrics).get_statistics())
```

---

## 🔍 Troubleshooting

### Problem: "Connection refused"
```
Solution: docker compose up -d
```

### Problem: "No metrics found"
```
Solution: Run an experiment first
         docker compose run --rm chaos cpu on 2
         sleep 30
         docker compose run --rm chaos cpu off
```

### Problem: Import errors
```
Solution: pip install -r metrics_requirements.txt
```

---

## 🎓 Learning Path

**Beginner**: (30 minutes)
1. Read this file
2. Run `python validate_metrics.py`
3. Run `python run_experiment.py 1`
4. Check results in `./data/experiments/`

**Intermediate**: (1 hour)
1. Read `METRICS_FETCHING_QUICKSTART.md`
2. Try code examples
3. Collect custom metrics
4. Export to different formats

**Advanced**: (2 hours)
1. Read `METRICS_PIPELINE_GUIDE.md`
2. Study `metrics_fetcher.py` code
3. Study `metrics_pipeline.py` code
4. Create custom analysis scripts

**ML Integration**: (Next phase)
1. Load exported CSV data
2. Use pandas for exploration
3. Train ML models
4. Evaluate predictions

---

## 📈 Output Examples

### metrics.jsonl (Line-delimited JSON)
```json
{"timestamp": 1712016930.5, "metric_name": "chaos_mode", "value": 1.0}
{"timestamp": 1712016931.0, "metric_name": "http_requests_total", "value": 2.5}
```

### metrics.csv (Tabular format)
```csv
timestamp,metric_name,value
1712016930.5,chaos_mode,1.0
1712016931.0,http_requests_total,2.5
```

### analysis.json (Statistics)
```json
{
  "total_metric_points": 450,
  "unique_metrics": 15,
  "statistics": {
    "http_requests_total": {
      "count": 30,
      "mean": 2.5,
      "std": 0.5,
      "min": 1.0,
      "max": 4.0
    }
  }
}
```

---

## 🎯 Next Steps

### Immediate (Now)
1. ✅ Run validation: `python validate_metrics.py`
2. ✅ Run experiment: `python run_experiment.py`
3. ✅ Check results: `ls ./data/experiments/`

### Short-term (Today)
1. 📖 Read quick start guide
2. 🔨 Try code examples
3. 📊 Export and analyze data

### Medium-term (This week)
1. 📚 Read full API documentation
2. 💡 Integrate into your workflow
3. 🧪 Run multiple experiments
4. 📈 Build analysis scripts

### Long-term (This month)
1. 🤖 Prepare data for ML
2. 🔬 Train ML models
3. 📊 Create dashboards
4. 🚀 Automate workflows

---

## 📞 Help & Support

### Quick Questions
Check the relevant doc:
- **How do I...?** → `METRICS_FETCHING_QUICKSTART.md`
- **What does this class do?** → `METRICS_PIPELINE_GUIDE.md`
- **How is the system organized?** → `README_METRICS.md`

### System Not Working
Run validation:
```bash
python validate_metrics.py
```

This will tell you exactly what's wrong.

### Code Examples
All modules have examples:
- Comments in code
- Docstrings with usage
- CLI examples (`run_experiment.py`)
- Documentation examples

---

## 🏁 TL;DR (Too Long; Didn't Read)

**In 30 seconds:**
```bash
pip install -r metrics_requirements.txt
python validate_metrics.py
python run_experiment.py 1
ls ./data/experiments/cpu_saturation/
```

**Result**: Metrics collected from Prometheus during CPU saturation chaos

**Files created**:
- `metrics.jsonl` - Raw data
- `metrics.csv` - For analysis
- `analysis.json` - Statistics

**Now what?**: Read `METRICS_FETCHING_QUICKSTART.md` for examples

---

## ✨ Key Features

✅ Collect 15+ metrics automatically
✅ Multi-format export (JSONL/CSV/JSON)
✅ Real-time streaming with callbacks
✅ Pandas DataFrame integration
✅ Time-window aggregation
✅ Experiment automation
✅ System validation included
✅ Production-ready code
✅ Comprehensive documentation
✅ ML-ready data formats

---

## 🎉 You're Ready!

You now have everything needed to:
- 📊 Collect metrics from Prometheus
- 📈 Run chaos experiments with metrics
- 💾 Export data in multiple formats
- 🔍 Analyze metrics with pandas
- 🤖 Prepare data for machine learning

**Start now**: Pick a use case above and follow the steps!

---

## 📖 Full Documentation

This is just the quick start. For more:

| Document | Purpose | When |
|----------|---------|------|
| `SYSTEM_SUMMARY.md` | Complete overview | Want details |
| `INDEX.md` | Full index | Want navigation |
| `METRICS_FETCHING_QUICKSTART.md` | Quick reference | Want examples |
| `METRICS_PIPELINE_GUIDE.md` | API reference | Want details |
| `README_METRICS.md` | File guide | Want organization |

---

**Ready to go?** Run this now:
```bash
python run_experiment.py
```

Then check: `./data/experiments/`

**Questions?** Read the docs or run: `python validate_metrics.py`

