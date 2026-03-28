# Setting up Grafana Dashboards for Metrics Visualization

Your Grafana is empty because we need to add data sources and create dashboards. Follow these steps to visualize metrics from cAdvisor and the app.

---

## Step 1: Add Prometheus Data Source to Grafana

### Via UI (Recommended)
1. Open Grafana: **http://localhost:3000**
2. Log in with **admin / admin**
3. Click on **Settings** (gear icon) → **Data Sources**
4. Click **Add data source**
5. Select **Prometheus**
6. Configure:
   - **Name**: `Prometheus`
   - **URL**: `http://prometheus:9090`
   - **Scrape interval**: `5s` (matches Prometheus config)
7. Click **Save & test**
   - You should see **"Data source is working"** ✓

---

## Step 2: Import Pre-built cAdvisor Dashboard

### Option A: Quick Import (Easiest)
1. In Grafana, click **+** (Create) → **Import**
2. Enter dashboard ID: **893** (cAdvisor dashboard)
3. Click **Load**
4. Select **Prometheus** as the data source
5. Click **Import**

This will give you container metrics automatically.

### Option B: Manual Dashboard Creation

If the import doesn't work, create a new dashboard:

1. Click **+** → **Dashboard**
2. Click **Add a new panel**
3. Follow the instructions in **Step 3** below

---

## Step 3: Create Custom Panels for App Metrics

### Panel 1: Active Chaos Modes

1. Click **Add a new panel**
2. In the query editor, paste:
```promql
chaos_mode
```
3. Configure:
   - **Panel title**: `Active Chaos Modes`
   - **Visualization**: `Gauge` or `Stat`
   - **Threshold**: Set max to 1
4. Click **Apply**

---

### Panel 2: Memory Leak Over Time

1. Click **Add a new panel**
2. Query:
```promql
leak_mb
```
3. Configure:
   - **Panel title**: `Memory Leaked (MB)`
   - **Visualization**: `Time series` (default)
   - **Axis**: Y-axis min=0, max=800
4. Click **Apply**

---

### Panel 3: File Descriptors Leaked

1. Click **Add a new panel**
2. Query:
```promql
open_fds_simulated
```
3. Configure:
   - **Panel title**: `Open File Descriptors`
   - **Visualization**: `Time series`
   - **Axis**: Y-axis min=0, max=5000
4. Click **Apply**

---

### Panel 4: HTTP Request Rate

1. Click **Add a new panel**
2. Query:
```promql
rate(http_requests_total[1m])
```
3. Configure:
   - **Panel title**: `Request Rate (per minute)`
   - **Visualization**: `Time series`
   - **Legend**: Show legend with values
4. Click **Apply**

---

### Panel 5: Request Latency (95th Percentile)

1. Click **Add a new panel**
2. Query:
```promql
histogram_quantile(0.95, rate(http_request_latency_seconds_bucket[5m]))
```
3. Configure:
   - **Panel title**: `P95 Latency (seconds)`
   - **Visualization**: `Time series`
   - **Unit**: `s` (seconds)
4. Click **Apply**

---

### Panel 6: Error Rate

1. Click **Add a new panel**
2. Query:
```promql
sum(rate(http_requests_total{code=~"[45].."}[1m])) / sum(rate(http_requests_total[1m]))
```
3. Configure:
   - **Panel title**: `Error Rate`
   - **Visualization**: `Gauge`
   - **Unit**: `percentunit` (will show as %)
   - **Thresholds**: 0% (green), 5% (yellow), 10% (red)
4. Click **Apply**

---

### Panel 7: Container CPU Usage

1. Click **Add a new panel**
2. Query:
```promql
rate(container_cpu_usage_seconds_total{name="failure-zoo-4-app-1"}[1m])
```
3. Configure:
   - **Panel title**: `Container CPU Usage`
   - **Visualization**: `Time series`
   - **Unit**: `short` (or `percentunit` if you want %)
4. Click **Apply**

---

### Panel 8: Container Memory Usage

1. Click **Add a new panel**
2. Query:
```promql
container_memory_usage_bytes{name="failure-zoo-4-app-1"} / 1024 / 1024
```
3. Configure:
   - **Panel title**: `Container Memory (MB)`
   - **Visualization**: `Time series`
   - **Unit**: `short`
   - **Axis**: Y-axis min=0
4. Click **Apply**

---

### Panel 9: DB Inflight Operations

1. Click **Add a new panel**
2. Query:
```promql
db_inflight
```
3. Configure:
   - **Panel title**: `DB Inflight Operations`
   - **Visualization**: `Gauge`
   - **Min**: 0, **Max**: 10
4. Click **Apply**

---

### Panel 10: Disk Fill Status

1. Click **Add a new panel**
2. Query:
```promql
disk_fill_mb
```
3. Configure:
   - **Panel title**: `Disk Filled (MB)`
   - **Visualization**: `Time series`
   - **Axis**: Y-axis min=0
4. Click **Apply**

---

## Step 4: Save Your Dashboard

1. Click **Save dashboard** (top right)
2. Name it: `Failure Zoo Metrics`
3. Choose folder: `General`
4. Click **Save**

---

## Step 5: Organize Panels (Optional)

Arrange panels in a logical order:
- **Row 1**: Status (Chaos Modes, Error Rate)
- **Row 2**: Resource Pressure (Memory, FDs, Disk)
- **Row 3**: Performance (Latency, Request Rate)
- **Row 4**: Container Metrics (CPU, Memory, DB)

---

## Troubleshooting: Why is Grafana Still Empty?

### Issue 1: No Data in Queries
**Solution**: Check if Prometheus is collecting data
```bash
# Test Prometheus directly
curl 'http://localhost:9090/api/v1/query?query=up'
```

If it returns no data, the app hasn't run any experiments yet. **Run an experiment first**:
```bash
docker compose run --rm chaos cpu on 2
sleep 30
docker compose run --rm chaos cpu off
```

### Issue 2: Wrong Container Name
**Solution**: Find your actual container name
```bash
docker compose ps
# Look for the app container name (usually: failure-zoo-4-app-1)
```

Update cAdvisor queries with the correct name:
```promql
container_cpu_usage_seconds_total{name="YOUR-CONTAINER-NAME"}
```

### Issue 3: Data Source Connection Failed
**Solution**: Verify Prometheus URL
- Inside Docker: `http://prometheus:9090` ✓
- From host: `http://localhost:9090` (if accessing from outside containers)

If you're getting errors, check:
```bash
# Verify Prometheus is running
docker compose ps | grep prometheus

# Test connectivity from Grafana container
docker compose exec grafana curl http://prometheus:9090
```

### Issue 4: Metrics Not Yet Generated
**Solution**: Prometheus needs scrape cycles to collect data
- Prometheus scrapes every **5 seconds**
- Metrics appear after first scrape
- Run experiments for **at least 30-60 seconds** for meaningful data

---

## Quick Test: Verify Data Source Works

1. In Grafana, go to **Data Sources**
2. Click on **Prometheus**
3. Scroll to **Test your connection**
4. Click **Test**
5. You should see **"Data source is working"**

If not:
```bash
# Check if Prometheus is running
docker compose ps

# Check Prometheus logs
docker compose logs prometheus | tail -20

# Verify app metrics are being scraped
curl http://localhost:8000/metrics | head -20
```

---

## Advanced: Import Pre-built Dashboards

Grafana has many pre-built dashboards. To find more:

1. Go to **Dashboards** → **Browse**
2. Search for dashboard IDs:
   - **893** - cAdvisor (container metrics)
   - **1860** - Node Exporter (system metrics)
   - **3662** - Prometheus Stats

3. When you find one, go to **Create** → **Import**
4. Paste the dashboard ID
5. Select **Prometheus** data source
6. Click **Import**

---

## Example: Complete Setup in 5 Minutes

```bash
# 1. Start everything
docker compose up -d --build
sleep 10

# 2. Run an experiment to generate data
docker compose run --rm chaos cpu on 2 &
CHAOS_PID=$!

# 3. Give it time to collect metrics
sleep 60

# 4. Stop chaos
kill $CHAOS_PID 2>/dev/null || true
docker compose run --rm chaos cpu off

# 5. Open Grafana
open http://localhost:3000

# 6. Login: admin / admin
# 7. Add Prometheus data source (URL: http://prometheus:9090)
# 8. Create a panel with query: chaos_mode
# 9. You should see data!
```

---

## Next Steps

Once you have dashboards set up:

1. **Run experiments** (see EXPERIMENTS_GUIDE.md)
2. **Watch metrics change** in real-time on Grafana
3. **Export dashboards** for documentation:
   - Click **Share** → **Export as JSON**
4. **Set up alerts** (optional):
   - Click **Alert** on any panel
   - Set thresholds for automatic notifications

---

## Reference: Common PromQL Queries for Grafana

```promql
# CPU
rate(container_cpu_usage_seconds_total[1m])

# Memory (in MB)
container_memory_usage_bytes / 1024 / 1024

# Requests per second
rate(http_requests_total[1m])

# Average response time
rate(http_request_latency_seconds_sum[5m]) / rate(http_request_latency_seconds_count[5m])

# P95 latency
histogram_quantile(0.95, rate(http_request_latency_seconds_bucket[5m]))

# Error rate (%)
sum(rate(http_requests_total{code=~"[45].."}[1m])) * 100 / sum(rate(http_requests_total[1m]))

# Active connections/operations
sum(db_inflight)

# Resource pressure gauges
leak_mb
open_fds_simulated
disk_fill_mb
```

