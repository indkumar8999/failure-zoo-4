---
name: Revise Mid-Project Slides
overview: Create a comprehensive markdown reference document organized in implementation order, covering exact minute details of the system setup, chaos implementation, normal behavior, SOM learner, experiments that broke/fixed, evaluation, and campaigns -- with every input, output, storage location, and logging detail.
todos:
  - id: write-slide-content
    content: Write the full detailed markdown file (experiments/reports/experiment_slides_revised.md) covering every component in implementation order with exact inputs/outputs/storage/logging
    status: pending
isProject: false
---

# Mid-Project Slides -- Reference Document (Implementation Order)

## What This Is

A detailed markdown file organized in **implementation order** (the order things must be understood), not chronological timeline. Every section covers exact inputs, outputs, storage locations, logging, and configuration for each component. This is a reference while building PowerPoint slides.

## Deliverable

One markdown file: `experiments/reports/experiment_slides_revised.md`

## Structure (in implementation order)

### Section 1: System Setup -- The Application Under Test

**What it is**: A FastAPI web service (`app/main.py`, 451 lines) running in Docker (Python 3.12-slim base image, port 8000). It is the "system under test" that will be broken by chaos injection and monitored by the SOM learner.

**What it does in normal operation**:

- Serves a `/work` endpoint: when called, runs a small CPU-bound hash loop (3000 iterations of XOR hashing), then sleeps for `ms` milliseconds (default 20), then returns `{"ok": true, "cpu_dt_ms": ..., "x": ...}`
- Connects to **PostgreSQL** via SQLAlchemy (`DATABASE_URL=postgresql+psycopg2://postgres:postgres@postgres:5432/postgres`). Connection pool: 10 pool_size, 20 max_overflow, pre-ping enabled.
- Calls a **downstream dependency** through Toxiproxy. The app talks to `http://toxiproxy:8666`, which proxies to `http://downstream:9000`. The downstream mock returns `{"ok": true}` on `/ok` and is 50/50 ok/fail on `/flaky`.
- Has a `/db/slow` endpoint that runs `SELECT pg_sleep(N)` inside a `db_gate` semaphore (BoundedSemaphore, default max_inflight=10).
- Has a `/dns/test` endpoint that resolves a DNS name (default `example.com`) via `dns.resolver`.

**What metrics it exposes** (Prometheus, scraped every 5s):

- `http_requests_total{path, code}` -- Counter of all HTTP requests, labeled by path and status code
- `http_request_latency_seconds{path}` -- Histogram of request latency per path
- `chaos_mode{mode}` -- Gauge, one label per fault type (cpu, mem_leak, lock_convoy, fd_leak, disk_fill, retry_storm, dns_test, net_latency, net_reset_peer, net_bandwidth, db_gate, fsync_storm). Value 1 when that fault is active, 0 when off.
- `leak_mb` -- Gauge: approximate leaked memory in MB
- `open_fds_simulated` -- Gauge: number of file descriptors held open by FD leak
- `disk_fill_mb` -- Gauge: MB written to /data/fill.bin by disk fill
- `db_inflight` -- Gauge: current number of DB operations in flight
- `retry_calls_total{endpoint, result}` -- Counter of retry storm calls (attempt, ok, non_200, exception, failed)
- `process_resident_memory_bytes`, `process_open_fds` -- standard Python process metrics from prometheus_client

**How it runs in Docker**: Built from `app/Dockerfile` (python:3.12-slim + strace + procps). Entry point is `entrypoint.sh` which creates `/data/syscalls`, `/data/events`, `/data/logs` directories, then launches `uvicorn main:app` under `strace -ff -ttt -T -s 200 -yy` with network/file/process/descriptor/signal filters. Strace writes per-thread trace files to `/data/syscalls/trace.*`. Uvicorn stdout/stderr go to `/data/logs/app_stdout.log` and `app_stderr.log`. Requires `SYS_PTRACE` capability and `seccomp:unconfined` for strace to work.

**Storage locations** (all under `./data/app/` bind mount):

- `/data/events/chaos_events.jsonl` -- every chaos on/off/reset event with timestamp, mode, enabled flag, and parameters
- `/data/logs/app_stdout.log`, `app_stderr.log`, `entrypoint.log`
- `/data/syscalls/trace.*` -- per-thread strace output

---

### Section 2: Supporting Infrastructure -- Every Service

**Downstream** (`downstream/main.py`, 17 lines): Minimal FastAPI on port 9000. Two endpoints: `/ok` returns `{"ok": true}`, `/flaky` returns ok 50% of the time and `{"ok": false, "code": 500}` the other 50% with a 50ms delay. This is the target for retry storm fault injection.

**Toxiproxy** (Shopify's `ghcr.io/shopify/toxiproxy:latest`): A TCP proxy sitting between the app and downstream. Listens on port 8666 (proxy traffic) and 8474 (control API). A proxy named "downstream" maps `0.0.0.0:8666` to `downstream:9000`. The app's `DOWNSTREAM_URL=http://toxiproxy:8666` so all downstream traffic goes through this proxy. Network faults (latency, reset_peer, bandwidth) are injected by adding "toxics" to this proxy via its REST API.

**PostgreSQL** (`postgres:16`): Standard Postgres, password `postgres`, port 5432. Data persisted to `./data/postgres/`. Used by the app for `/db/slow` queries and connection pool behavior.

**Load Generator** (`loadgen/main.py`, 55 lines): Runs in an infinite loop sending HTTP requests to the app. Configuration via env vars:

- `LOADGEN_PROFILE`: `steady` (random path from PATHS list), `mixed` (randomly picks from /work, /health, /dns/test, /db/slow?seconds=1), or `bursty` (always /work, with 80/20 slow/fast split)
- `LOADGEN_RPS`: requests per second (default 5.0, research stages use 6.0)
- `LOADGEN_WORK_MS`: ms parameter passed to /work endpoint (default 20)
- `LOADGEN_JITTER`: +/- jitter fraction on sleep interval (default 0.1 = 10%)
- `LOADGEN_SEED`: RNG seed for reproducibility
- In `steady` mode at 6 RPS with 20ms work: the app handles 6 requests/sec, each taking ~20ms, producing a consistent telemetry signal the SOM can learn as "normal"

**cAdvisor** (`gcr.io/cadvisor/cadvisor:v0.49.1`, port 8080): Reads container-level metrics (CPU usage, memory, network I/O, disk I/O) from Docker's cgroups and exposes them as Prometheus metrics. Mounted read-only on `/`, `/var/run`, `/sys`, `/var/lib/docker/`.

**Prometheus** (`prom/prometheus:v2.54.1`, port 9090): Central metrics store. Config in `prometheus/prometheus.yml`:

- Global scrape interval: **5 seconds**
- Scrapes 3 targets: `app:8000/metrics`, `cadvisor:8080/metrics`, `learner:8100/metrics`
- Storage: TSDB at `/prometheus` (bind-mounted to `./data/prometheus/`), 7-day retention
- The SOM learner queries Prometheus's HTTP API (`/api/v1/query`) to get feature values

**Grafana** (`grafana/grafana:11.1.4`, port 3000): Dashboards for visual monitoring. Admin/admin credentials. Data in `./data/grafana/`.

**How everything wires together**:

- loadgen -> app:8000 (HTTP GET /work, /health, /dns/test, /db/slow)
- app -> toxiproxy:8666 -> downstream:9000 (downstream calls)
- app -> postgres:5432 (DB queries)
- Prometheus scrapes app:8000/metrics, cadvisor:8080/metrics, learner:8100/metrics every 5s
- learner polls Prometheus:9090/api/v1/query every POLL_SEC (1s or 2s)
- chaos CLI -> app:8000/chaos/* (process-level faults) AND toxiproxy:8474 (network faults)

---

### Section 3: Normal Behavior -- What the System Looks Like When Healthy

**How normal behavior is established**: The load generator continuously sends 6 requests/sec to the app. Under normal (no-fault) operation, the 9 features the SOM observes stabilize into a consistent pattern:

- `req_rate`: ~6 req/sec (from loadgen)
- `latency_p95`: low (a few ms for /work + 20ms sleep)
- `db_inflight`: near 0 (no concurrent slow queries unless /db/slow is called by mixed profile)
- `leak_mb`: 0 (no memory leak active)
- `open_fds_sim`: 0 (no FD leak active)
- `disk_fill_mb`: 0 (no disk fill active)
- `retry_rate`: 0 (no retry storm active)
- `proc_mem_bytes`: stable baseline (~50-100 MB for Python process)
- `proc_open_fds`: stable baseline (normal file descriptors)

**How the SOM learns "normal"**: During the bootstrap phase (first 240s of a run), the learner collects feature vectors only when `sum(chaos_mode) == 0` (no faults active). These 180+ normal-only vectors become the training data. The SOM learns the manifold of normal behavior in this 9-dimensional feature space. After training, any sample that deviates significantly from the learned normal manifold is scored as anomalous.

**What "normal" stored artifacts look like**: `score_stream.jsonl` during bootstrap shows scores dropping as the SOM converges. After training, normal samples score below the 85th percentile threshold. `anomaly_events.jsonl` should be empty during normal operation (no alarms).

---

### Section 4: Chaos Implementation -- Exact Details of Every Fault

The chaos system has two layers. **Layer 1** is inside the app itself (process-level faults via HTTP endpoints). **Layer 2** is Toxiproxy (network-level faults). `chaosctl.py` (195 lines) is the CLI that orchestrates both.

#### 4.1 Memory Leak (`memleak on {mb_per_sec}` / `memleak off`)

**Input**: `mb_per_sec` (integer, default 20). Example: `memleak on 50` means leak 50 MB per second.

**How it works inside the app**: When `/chaos/mem/leak/start?mb_per_sec=50` is called, it spawns a background daemon thread. Every 1 second, that thread:

1. Checks current total leaked: `sum(len(b) for b in mem_leak) // (1024*1024)`
2. If below `CHAOS_MEM_LIMIT_MB` (800 MB cap), allocates a `bytearray(50 * 1024 * 1024)` (50 MB)
3. Touches every 4096th byte (`b[j] = 1`) to force physical page allocation (prevents the OS from lazy-allocating)
4. Appends the bytearray to the `mem_leak` list (Python list, never freed until stop)
5. Updates `leak_mb` Prometheus gauge to current total

**What it perturbs** (which of the 9 features change):

- `leak_mb` goes from 0 to 50, 100, 150... up to 800 MB
- `proc_mem_bytes` increases correspondingly
- Under high pressure: `latency_p95` may increase due to GC pressure, `req_rate` may drop

**How it stops**: `/chaos/mem/leak/stop` sets `mem_leak_stop` event, then `mem_leak.clear()` frees all bytearrays, `LEAK_MB.set(0)`.

**Logging**: On start: writes `{"type":"chaos","mode":"mem_leak","enabled":true,"mb_per_sec":50,"cap_mb":800,"ts":...}` to `chaos_events.jsonl`. On stop: writes `{"type":"chaos","mode":"mem_leak","enabled":false,"ts":...}`. Sets `chaos_mode{mode="mem_leak"}` gauge to 1/0.

**Intensity ladder in experiments**: low=20 MB/s, medium=50 MB/s, high=80 MB/s. In research stages, also `very_low=10 MB/s` in Stage 2.

#### 4.2 CPU Hog (`cpu on {workers}` / `cpu off`)

**Input**: `workers` (integer, default 2). Example: `cpu on 4` spawns 4 CPU-burning threads.

**How it works**: `/chaos/cpu/start?workers=4` spawns N daemon threads (capped at 64). Each thread runs `_cpu_burner()`: an infinite loop doing `for i in range(500000): x ^= i` -- pure CPU busy-wait with no sleep. These threads compete with the app's uvicorn workers for CPU time.

**What it perturbs**: 

- `latency_p95` increases (app requests take longer due to CPU contention)
- `req_rate` may drop (fewer requests complete per second)
- Per-container CPU metrics in cAdvisor spike

**How it stops**: Sets `cpu_stop` event, threads exit their while loop, list cleared.

**Logging**: Same pattern -- `chaos_events.jsonl` with `mode=cpu`, `workers=4`. Gauge `chaos_mode{mode="cpu"}` set to 1/0.

**Intensity ladder**: low=2 workers, medium=4, high=8.

**Paper note**: UBL paper section 3.2.1 notes that smoothing can wash out fast CPU-hog precursors. The fault creates sudden CPU spikes that smooth over with K=5 averaging.

#### 4.3 Network Latency (`net latency {ms}` / `net clear`)

**Input**: `ms` (integer, default 200). Example: `net latency 400` adds 400ms latency with 80ms jitter.

**How it works**: This is a **Toxiproxy** fault, not an app-side fault. `chaosctl.py`:

1. Calls `ensure_proxy()` to verify the "downstream" proxy exists (creates it if not: `POST /proxies {"name":"downstream","listen":"0.0.0.0:8666","upstream":"downstream:9000"}`)
2. Calls `clear_toxics()` to remove any existing toxics
3. Calls `add_toxic("latency", "latency", {"latency": 400, "jitter": 80}, stream="downstream")` which POSTs to `http://toxiproxy:8474/proxies/downstream/toxics`
4. Calls `mark("net_latency", True, 400)` to POST to app's `/chaos/mark` endpoint, which sets `chaos_mode{mode="net_latency"}` gauge to 1

**What it perturbs**: 

- Every request from the app to downstream now takes an extra 400ms +/- 80ms
- `latency_p95` increases for any path that touches downstream (like /work if it calls downstream)
- But the perturbation is **subtle in the feature space** because latency changes are relatively small compared to the metric range, and the SOM's smoothing further dampens the signal

**How it stops**: `net clear` calls `clear_toxics()` which DELETEs each toxic from Toxiproxy, then marks gauges off.

**Logging**: App-side: `chaos_events.jsonl` gets a `mark` event with `mode=net_latency`. Toxiproxy-side: toxics exist in Toxiproxy's state but are not separately logged.

**Intensity ladder**: low=150ms, medium=400ms, high=700ms.

**Why this fault is hard to detect**: Toxiproxy only adds latency to downstream calls. The app's overall latency_p95 includes all paths (health checks, DB queries, work), so the downstream latency contribution is diluted. The SOM sees a small bump in one feature out of 9.

#### 4.4 Lock Convoy (`lock on {threads}` / `lock off`)

**Input**: `threads` (integer, default 80). Example: `lock on 60` spawns 60 lock-contention threads.

**How it works**: `/chaos/lock_convoy/start?threads=60` uses FastAPI's `BackgroundTasks` to spawn workers after the HTTP response returns (avoids control-plane timeout). Each worker thread runs `_lock_convoy()`: an infinite `while not stop: with convoy_lock: pass` -- every thread grabs and immediately releases a single global `threading.Lock`. With 60 threads all fighting for one lock, this creates severe lock contention, thread scheduling overhead, and context-switch storms.

**What it perturbs**:

- `latency_p95` increases dramatically (app's own request handling contends with convoy threads)
- `req_rate` drops
- CPU usage spikes (not from computation but from context switching)

**How it stops**: Sets `lock_convoy_stop`, threads exit, list cleared.

**Known issue**: The lock_convoy start uses `BackgroundTasks` which means the HTTP response returns before threads are fully spawned. The stop command tries to set the event and clear the list. In some experiments, `lock off` failed with exit code 1 (Docker/command-path issue), leaving threads running until the container was recreated.

**Intensity ladder**: low=20 threads, medium=40, high=60.

#### 4.5 Disk Fill (`disk fill {mb}` / `disk clear`)

**Input**: `mb` (integer, default 200, capped at 50000). Example: `disk fill 2000` writes 2 GB.

**How it works**: `/chaos/disk/fill?mb=2000` opens `/data/fill.bin` in append mode and writes `mb` chunks of 1 MB zeros (`b"\0" * 1024 * 1024`). Optional `fsync_each_mb` forces an fsync after each 1 MB write. Updates `disk_fill_mb` gauge to total file size.

**What it perturbs**:

- `disk_fill_mb` jumps from 0 to 2000
- Disk I/O metrics in cAdvisor spike
- If disk fills completely: potential write failures throughout the app

**How it stops**: `disk clear` removes `/data/fill.bin`, sets gauge to 0.

**Intensity ladder**: low=500 MB, medium=2000 MB, high=5000 MB.

#### 4.6 Other Faults (FD leak, DB gate, Retry storm, DNS)

**FD Leak** (`fdleak on {rate}`): Opens `rate_per_sec` file handles to `/data/fd_leak.tmp` per second, never closing them, capped at `CHAOS_FD_LIMIT=5000`. Perturbs `open_fds_sim` and `proc_open_fds`.

**DB Gate** (`dbgate {max_inflight}`): Replaces the `db_gate` BoundedSemaphore with a new one of size N. Setting it to 1 means only 1 concurrent DB query allowed, creating queueing. Perturbs `db_inflight` and `latency_p95` on DB-touching paths.

**Retry Storm** (`retrystorm on {qps}`): Spawns a thread making `qps` requests/sec to downstream's `/flaky` endpoint with 3 retries and 200ms timeout. Since /flaky fails 50% of the time, this creates a burst of extra downstream traffic. Perturbs `retry_rate`.

**DNS** (`dns bad`): Sets the app's DNS resolver to `203.0.113.123` (non-routable bogus IP). All DNS lookups fail. Perturbs `/dns/test` endpoint behavior.

#### 4.7 Reset -- How Everything Gets Cleaned Up

`chaos reset` calls every stop function in sequence: `chaos_cpu_stop()`, `chaos_lock_convoy_stop()`, `chaos_mem_leak_stop()`, `chaos_fd_leak_stop()`, `retry_storm_stop_fn()`, `chaos_disk_clear()`, `dns_set_server(None)`, `set_db_gate(10)`. Then writes a reset event to `chaos_events.jsonl`. This is called at the start and end of every experiment run.

---

### Section 5: SOM Learner -- Exact Implementation Details

**Service**: FastAPI app (`learner/main.py`, 685 lines) running in Docker (Python 3.12-slim, port 8100). Background worker thread does all the SOM logic.

#### 5.1 Data Input -- How the Learner Gets Features

Every `POLL_SEC` (1.0s in paper mode, 2.0s default), the worker thread:

1. For each of the 9 feature names, sends `GET http://prometheus:9090/api/v1/query?query=...` with the PromQL query
2. Parses the JSON response, extracts the scalar value (first result's value[1]), defaults to 0.0 on error
3. Also queries `sum(chaos_mode)` to check if any fault is active
4. Bundles into a `Sample(ts=time.time(), values=np.array([9 floats]), chaos_on=bool)`

**The 9 PromQL queries** (exact strings):

- `sum(rate(http_requests_total[1m]))` -- request rate over last 1 minute
- `histogram_quantile(0.95, sum by (le) (rate(http_request_latency_seconds_bucket[1m])))` -- p95 latency
- `max(db_inflight)` -- current DB operations in flight
- `max(leak_mb)` -- current memory leak size
- `max(open_fds_simulated)` -- current simulated open file descriptors
- `max(disk_fill_mb)` -- current disk fill size
- `sum(rate(retry_calls_total[1m]))` -- retry storm call rate
- `max(process_resident_memory_bytes)` -- process RSS
- `max(process_open_fds)` -- process open file descriptors

#### 5.2 Bootstrap Phase -- Collecting Normal Data

**Input**: Raw feature samples from Prometheus.
**Gate**: Only samples where `chaos_on == False` (sum(chaos_mode) == 0) are appended to `bootstrap_normal` list.
**Target**: Collect `BOOTSTRAP_SAMPLES` (180 in paper mode) normal samples.
**Duration**: At POLL_SEC=1.0, this takes 180 seconds minimum of fault-free operation.
**Output**: A list of 180 nine-dimensional numpy arrays representing the normal operating manifold.

**What Prometheus gauges show during bootstrap**:

- `som_model_ready` = 0 (not yet trained)
- `som_training_samples` increments from 0 to 180
- `som_total_samples` increments every poll (including chaos samples, but those aren't stored)

**HTTP status during bootstrap**: `GET /status` returns `{"trained": false, "bootstrap_samples": N, "bootstrap_target": 180, ...}`. The experiment runner polls this to know when to proceed.

#### 5.3 Training Phase -- Building the SOM Model

**Triggered**: When `len(bootstrap_normal) >= BOOTSTRAP_SAMPLES`.

**Step 1 -- Normalization**:

- Stack 180 samples into matrix shape (180, 9)
- Compute per-feature max: `scale = np.max(samples, axis=0)`, replace any 0.0 with 1.0
- Normalize: `(samples / scale) * 100.0` -- all features now in [0, 100] range
- This is the `train_max_100` normalization mode

**Step 2 -- K-fold Cross-Validation**:

- Split 180 samples into K=3 folds (60 samples each) using random permutation with seed
- For each fold (3 iterations):
  - Train set = 120 samples (other 2 folds), validation set = 60 samples (this fold)
  - For each random init (3 trials per fold):
    - Initialize 32x32 SOM weights uniformly in [0, 100] with unique seed per (fold, init)
    - Run 8 epochs of full-batch training: for each sample in random order, find BMU, update weights with Gaussian neighborhood influence
    - Compute threshold: UBL area score at BMU for every training sample, take 85th percentile
    - Compute validation accuracy: fraction of validation samples with area score < threshold
  - Total: 3 folds x 3 inits = **9 candidate models**

**Step 3 -- Model Selection**:

- Pick the model with the highest validation accuracy
- Record which fold and which init won, plus the winning val_acc

**Step 4 -- Persistence**:

- Save to `som_model.npz` (numpy compressed archive): weights (32x32x9 = 9216 floats), threshold, scale vector, feature names, training metadata (kfold, init_trials, selected_fold, selected_init, validation_accuracy, normalization_mode), UBL training scores
- File location: `/data/model/som_model.npz` (bind-mounted to `./data/learner/model/som_model.npz` on host)

**Output**: A trained SOM model file + threshold. `som_model_ready` gauge set to 1. `/status` now returns `trained: true`.

#### 5.4 Scoring Phase -- Online Anomaly Detection

**Input**: Each new 9-feature sample from Prometheus, every POLL_SEC.

**Step 1 -- Smoothing**: Maintain a deque of the last K=5 raw sample vectors. Compute the element-wise mean across the window. This is the smoothed sample.

**Step 2 -- Normalization**: Apply the frozen training scale: `x = (smoothed / scale) * 100.0`. Optional clip (none in paper mode, clip_300 in baseline mode).

**Step 3 -- BMU Lookup**: Compute Euclidean distance from `x` to all 1024 neuron weight vectors. Find the neuron with minimum distance = BMU (Best Matching Unit). Returns (row, col, distance).

**Step 4 -- UBL Area Score**: Compute the "neighborhood area" at the BMU: for the BMU at position (r,c), sum the L1 (Manhattan) distances between the BMU's weight vector and each of its 4 neighbors' weight vectors (up, down, left, right, skipping edges). This area measures how "stretched" the map is around this neuron. In regions where many normal samples cluster, neurons are close together (small area). In sparse/anomalous regions, neurons are far apart (large area).

**Step 5 -- Anomaly Decision**: If `area_score >= threshold` (85th percentile from training), this sample is **anomalous**. Increment `anomaly_streak_count`. If the streak reaches `ANOMALY_STREAK=3` consecutive anomalous samples, fire an **alarm**.

**Step 6 -- Cause Inference** (when alarm fires): Find Q=5 nearest normal-region neurons (neurons with area < threshold, closest in lattice distance to the anomalous BMU). For each, compute the per-feature absolute difference between the anomalous BMU's weights and the normal neighbor's weights. Rank features by majority vote: which feature has the largest difference most often across the Q neighbors. Output: ranked list of features most responsible for the anomaly.

**Step 7 -- Logging**:

- **Score stream** (`score_stream.jsonl`): Every sample gets a line: `{"ts":..., "type":"som_score", "score":..., "bmu_score":..., "chaos_on":..., "threshold":..., "scoring_mode":"ubl_area"}`
- **Alarm log** (`anomaly_events.jsonl`): Only when alarm fires: `{"ts":..., "type":"som_anomaly", "score":..., "bmu_score":..., "threshold":..., "scoring_mode":"ubl_area", "anomaly_streak_count":3, "alarm_streak_target":3, "smooth_k":5, "chaos_on":..., "cause_inference":{...}, "model_meta":{...}, "features":{...}}`

**Step 8 -- Online Learning**: If `chaos_on == False` (no active fault), call `model.train_step(x)` to incrementally update the SOM toward this new normal sample. This is an extension beyond the paper's strict static-bootstrap approach.

**Step 9 -- Periodic Save**: Every 30 samples, re-persist the model to `som_model.npz`.

---

### Section 6: How the Two Scoring Modes Compare

**Paper-fidelity config** (`paper_fidelity` / `paper_fidelity_research_anchor`):

- 32x32 SOM (1024 neurons), UBL area scoring, 5-point smoothing, 3-consecutive streak, 0.85 quantile threshold, 3-fold CV with 3 inits (9 models compared), train_max_100 normalization, no online clipping, fresh bootstrap each run, POLL_SEC=1.0

**Baseline config** (`current_default`):

- 20x20 SOM (400 neurons), BMU distance scoring, no smoothing (K=1), single-sample alarm (streak=1), 0.99 quantile threshold, no CV (K=1, 1 init), clip features at 300, warm-start (reuse prior model), POLL_SEC=2.0

**Four screening variants tested** (in ablation campaigns):

- `paper_fidelity_anchor`: the paper config above
- `screen_smooth_streak`: same topology but K=1 smooth, streak=1, q=0.85 (more sensitive, more false alarms)
- `screen_threshold`: same topology but K=5 smooth, streak=3, q=0.99 (higher threshold, fewer alarms but misses weak faults)
- `screen_training_topology`: 20x20 SOM, K=1 fold, 1 init (simpler/faster training)

---

### Section 7: Experiment Orchestration -- How a Campaign Works

**Implementation**: `experiments/run_experiments.py` (1107 lines).

**Input**: A YAML fault matrix file (e.g., `fault_matrix_research_stage1_paper_geometry.yaml`) that defines:

- `meta`: timing (warmup_s, bootstrap_s, inject_s, cooldown_s, fault_window_on_delay_s), seeds, repeats, loadgen profile/RPS, prediction_target_mode
- `learner.variants`: list of SOM configurations to test, each with name and env overrides
- `faults`: list of fault definitions, each with id, family, command_on/off templates, intensity_ladder, duration_ladder

**Matrix expansion**: The runner computes the full Cartesian product:

- For each variant x each fault x each intensity level x each duration level x each seed x each repeat
- Example: 1 variant x 3 faults x 2 intensities x 2 durations x 2 seeds x 1 repeat = 24 RunConfigs

**Campaign directory created**: `data/experiments/campaign-{UTC_timestamp}/` with:

- `campaign_meta.json`: matrix path, git SHA, compose config hash, Docker image list, loadgen settings, mode, run count
- `matrix.resolved.json`: the fully expanded matrix with all defaults filled in
- `run_index.json`: written at the end with the status of every run

**Per-run execution** (exact 19-step sequence described in Section 6 of previous plan version -- the runner clears alarm logs, recreates the learner container with run-specific env vars, waits for app health, resets chaos, sleeps warmup + bootstrap, gates on learner trained + model file, injects fault, waits delay + duration, stops fault, sleeps cooldown, resets chaos, snapshots artifacts to run directory, writes manifest.json)

**Per-run output** (`campaign-{id}/{run-id}/`):

- `manifest.json`: full run metadata including learner_status_post_bootstrap (trained, bootstrap_samples, threshold), run_status (completed/failed), failure_reason, timing durations, learner env
- `run_events.jsonl`: timestamped phase events (warmup start, bootstrap start, inject_start, fault_window on, inject_hold, inject_stop, fault_window off, cooldown, completed/failed)
- `artifacts/chaos_events.jsonl`: copy of app's chaos event log for this run
- `artifacts/anomaly_events.jsonl`: copy of learner's alarm log for this run
- `artifacts/som_model.npz`: copy of the trained SOM model

---

### Section 8: Evaluation Pipeline -- How Results Are Measured

**Implementation**: `experiments/evaluate.py` (1048 lines).

**Input per run**: `run_events.jsonl` (phase timestamps), `artifacts/anomaly_events.jsonl` (alarm timestamps + scores), `manifest.json` (metadata + status).

**How fault windows are built**: Parse `run_events.jsonl` for `type=fault_window` events. The "on" event marks fault window start (t1), the "off" event marks fault window end (t2). Everything between t1 and t2 is the fault-active period. Everything after `post_bootstrap_ts` but outside fault windows is the "normal" period.

**How alarms are matched** (many_to_many mode):

- Each alarm timestamp from `anomaly_events.jsonl` is checked against fault windows
- **True Positive**: alarm falls within a fault window
- **False Positive**: alarm falls outside all fault windows (but after post-bootstrap)
- **False Negative**: a fault window has zero alarms inside it
- Alarms can match multiple windows and windows can have multiple alarms (many-to-many)

**Metrics computed per run**:

- Precision = TP / (TP + FP)
- Recall = TP / (TP + FN)
- F1 = 2 * Precision * Recall / (Precision + Recall)
- Lead time = time between first alarm and fault window end
- paper_AT (paper-style alarm trueness): based on UBL Eq. 5 style
- paper_AF (paper-style alarm falseness): false alarm rate in paper's formulation

**Campaign-level aggregation output files**:

- `evaluation/run_metrics.csv`: one row per completed run, all metrics + SOM metadata columns
- `evaluation/rollup_metrics.csv`: mean metrics grouped by (variant, fault_id), with 95% confidence intervals
- `evaluation/stratified_rollup_metrics.csv`: mean metrics grouped by fault_family, study_scope, ablation_block
- `evaluation/som_rollup_metrics.csv`: mean SOM quality metrics (validation accuracy, U-matrix proxy, quantization error)
- `evaluation/failed_runs.csv`: run_id, fault, variant, failed_phase, reason
- `evaluation/roc_points.csv`: threshold sweep data for ROC-style analysis
- `evaluation/summary.json`: full JSON with all aggregated stats
- `evaluation/report.md`: human-readable markdown report with tables of all above

---

### Section 9: SOM Experiments -- What We Tried, What Broke, What We Fixed

#### 9.1 First Attempts -- F1=0 Everywhere

**What we ran**: 2 variants (paper_fidelity, current_default) x 3 faults (mem_leak, cpu_hog, net_latency). Timing: warmup 20s, bootstrap 30s, inject 20s, cooldown 20s. BOOTSTRAP_SAMPLES=180 but only 30s of collection at 2s polling = maximum 15 samples collected.

**What happened**: Every run produced F1=0.000 with FPR=1.000. The SOM never completed training (needed 180 samples, could only collect ~15), so the threshold was essentially random. Every alarm was a false positive.

**Second attempt with same config**: TPR jumped to 1.000 but FPR=0.96-0.99 -- the detector was alarming on everything, normal and anomalous alike. Lead times of 44-54s (alarms started during warmup/bootstrap, not during the fault injection).

**What we learned**: Bootstrap timing was catastrophically wrong. 30s of collection cannot produce 180 samples. Need to either reduce BOOTSTRAP_SAMPLES or increase bootstrap time.

#### 9.2 Short Timing Experiments -- Partial Campaigns

**What we ran**: Cut timings further (warmup 10s, bootstrap 15s, inject 10s, cooldown 10s), added lock_convoy fault, 2 repeats.

**What happened**: Only 7 of 16 planned runs materialized. Lock_convoy injection got stuck (run_events showed inject_start but never completed). CPU hog run truncated mid-injection. Most campaigns were partial -- Docker orchestration was fragile under rapid cycling.

**What we learned**: Lock convoy has orchestration issues (the BackgroundTasks-based spawning means threads start after HTTP response, making stop unreliable). Short timings make everything worse.

#### 9.3 Screening Matrix Attempts -- Docker Flakiness

**What we ran**: Screening matrix with 4 variants x 4 faults x 3 repeats = 48 runs. Longer timing (warmup 30s, bootstrap 120s, inject 90s, cooldown 45s).

**What happened**: Only 10 of 48 runs completed (all paper_fidelity_anchor variant). Then tried smoke mode (12 runs): multiple partial attempts (2/12, 4/12, 1/12 completed). The learner container repeatedly failed to start (`docker compose up learner` exit code 1).

**What fixed it**: Adding `reuse_learner_if_env_unchanged` flag -- if the next run uses the same learner configuration, skip stop/rm/up cycle and keep the running container. Also `--force-recreate` on actual rebuilds. After this fix: 12/12 screening smoke completed.

**What we learned**: Docker container lifecycle is the bottleneck, not the SOM. Learner reuse between compatible runs avoids the rebuild flakiness entirely.

#### 9.4 Minimal Single-Run Debugging -- Isolating the Problem

**What we ran**: New `fault_matrix_minimal.yaml` -- 1 variant (minimal_ubl, 16x16 SOM, 30 bootstrap samples), 1 fault (mem_leak), 1 run. Timing: warmup 5s, bootstrap 75s (enough for 30 samples at 1s polling), inject 15s, cooldown 8s.

**What happened**: Run completed but F1=0.000, FPR=1.000. However, SOM checkpoint tracking now showed `val_acc=0.933` -- the SOM was correctly learning normal behavior with 93% validation accuracy. The model was good, the detection was failing.

**What we changed next**: 

- Evaluation matching mode switched from `one_to_one` to `many_to_many`
- Alarm log clearing added between runs (delete anomaly_events.jsonl before each run)
- Paper-style metrics (paper_AT, paper_AF) added to the evaluator

**Result**: Next minimal run with same timing and config: **F1=1.000, paper_AT=1.0, paper_AF=0.0, lead_time=5.85s, 5 TP, 0 FP**. First successful end-to-end detection.

**What we learned**: The SOM was working all along. The problems were: (1) alarm stream contamination from prior runs (old alarms counted as FP in new run), (2) evaluation matching mode was too strict (one_to_one only counted one alarm per window), (3) the evaluator needed paper-aligned metrics.

#### 9.5 First Real Ablation -- Sensitivity vs False Alarms

**What we ran**: `fault_matrix_ablation_start.yaml`, 4 variants x 2 faults x 10 repeats = 80 runs. Timing: warmup 20s, bootstrap 120s, inject 60s, cooldown 25s.

**Exact inputs/outputs per variant**:

- `paper_fidelity_anchor` (32x32, ubl_area, K=5, streak=3, q=0.85): **F1=0.000** for both mem_leak and cpu_hog. Zero detections. The strict streak=3 and smooth=5 setting required 3 consecutive anomalous smoothed samples -- with only 60s of injection and the smoothing window averaging out the fault signal, the score never crossed the threshold 3 times in a row. Precision=0.000, Recall=0.000, paper_AF=0.005 (near zero false alarms but zero true detections too).
- `screen_smooth_streak` (K=1, streak=1, q=0.85): **paper_AT=0.4-0.6, FPR=0.99+, F1=0.011-0.018**. High recall (detected faults 40-60% of the time) but 99% false alarm rate. Without smoothing or streak, every slight score fluctuation triggered an alarm. Lead times of 30-34s.
- `screen_threshold` (K=5, streak=3, q=0.99): **paper_AT=0.6, FPR=0.996, F1=0.007-0.009**. Similar to smooth_streak -- detected faults but drowned in false alarms. The 99th percentile threshold was too high in absolute terms but didn't help because the scoring noise was also high.
- `screen_training_topology` (20x20, K=1, fold=1, init=1): **F1=0.000, FPR=0.000**. Complete silence. The smaller SOM with no cross-validation produced a model that never triggered any alarms at all. Underfitting.

**Paired significance**: All p-values > 0.75 (BH-corrected). No variant was statistically significantly better than the anchor.

**What we learned**: Single fixed config cannot work for all situations. Paper-fidelity is too conservative for short inject windows. Removing smoothing/streak causes alarm floods. Need to find the right combination of smoothing, streak, and threshold -- or accept that different fault families need different detector settings.

#### 9.6 Infrastructure Failures -- Docker and App Crashes

**What happened across multiple campaigns**:

- 80-run ablation at full scale: 57/80 completed (23 failed = 29% failure rate). Failures: `docker compose up learner` exit code 1, `docker compose rm loadgen` exit code 1, "learner not trained within 200s" with connection resets, "app not healthy within 90s"
- Smoke mode (8 runs): **8/8 failed** -- BOOTSTRAP_SAMPLES capped to 15 in smoke mode, but learner timeout was 85s. Bootstrap couldn't complete in time.
- Minimal single-run after many campaigns: **failed** -- "App did not become healthy within 90s, connection reset by peer". Accumulated state from prior chaos runs corrupted the Docker stack.

**What we fixed**: 

- Added `chaosctl.py` retry logic: `app_post()` retries 8 times with 1s backoff on any failure
- Full `docker compose down` between experiment sessions (not just cycling individual services)
- Use `full` mode (not smoke) for paper-faithful experiments
- Added `--strict-artifact-snapshot` flag to catch bind-mount issues early

#### 9.7 Geometry Studies -- Finding What the SOM Can Actually Detect

**What we ran**: Paper-faithful learner (32x32, ubl_area, full paper config), fixed across all runs. Varied only the fault type, intensity, and duration. Full timing (warmup 60s, bootstrap 240s, inject 60-180s, cooldown 90s, delay 14s).

**8-run minimal geometry** (2 faults x 2 intensities x 2 durations):

- lock_convoy: **F1=1.000** (4/4 runs perfect -- 100% detection, 0 false alarms)
- mem_leak: **F1=0.500** (2/4 detected, 2/4 missed -- low intensity + short duration cells missed)
- All 8 runs completed, 0 failures. learner_status_post_bootstrap confirmed: trained=true, 80/80 samples collected, threshold ~19.71

**What we learned**: With proper timing (240s bootstrap, 60s+ inject, 14s onset delay), the paper-fidelity config actually works well for some faults. Lock convoy creates such a strong telemetry signature that the SOM detects it every time. Memory leak detection depends on intensity and duration -- needs enough time for the leak to accumulate and perturb metrics visibly.

This led directly to the 3-stage research campaigns (Stages 1-3, which you already have slides for).

---

### Section 10: Summary of Problems, Fixes, and Learnings

**Problem 1 -- Bootstrap too short**: Needed 180 samples at 1s polling = 180s. Early configs used 30s bootstrap. **Fix**: Set bootstrap_s=240 (with buffer) and POLL_SEC=1.0.

**Problem 2 -- No training gate**: Faults injected before SOM finished training. **Fix**: Added `wait_for_learner_trained()` polling /status + checking som_model.npz exists.

**Problem 3 -- Alarm log contamination**: Old alarms from prior runs counted as FP in new run. **Fix**: Delete anomaly_events.jsonl and score_stream.jsonl before each run.

**Problem 4 -- Wrong evaluation matching**: one_to_one mode only counted one alarm per fault window. **Fix**: Switched to many_to_many matching.

**Problem 5 -- Docker container rebuild flakiness**: `docker compose up --build learner` failed intermittently. **Fix**: `--force-recreate`, learner reuse between compatible runs.

**Problem 6 -- Smoke mode too aggressive**: BOOTSTRAP_SAMPLES capped too low, learner never trains. **Fix**: Use `full` mode for paper-faithful experiments.

**Problem 7 -- App crash from accumulated chaos**: Prior chaos injections left residual state. **Fix**: Full `docker compose down` between sessions; `chaos reset` at start and end of every run.

**Problem 8 -- lock_convoy stop failures**: BackgroundTasks spawning + stop race condition. **Fix**: Retry logic in chaosctl (8 retries, 1s backoff).

**Problem 9 -- Artifact snapshot missing**: som_model.npz not copied from Docker bind mount. **Fix**: Fixed bind-mount paths and added `--strict-artifact-snapshot` flag.

**Problem 10 -- SOM parameters not pinned**: Default values from docker-compose.yml differed from matrix intent. **Fix**: Explicitly set all SOM env vars in YAML matrix for every variant.

---

### SLIDE 1: Application Under Test -- What We Built

**The target application** (`app/main.py`, 450+ lines):

- A FastAPI web service running on port 8000 inside Docker
- Connects to **PostgreSQL** (`:5432`) for database operations
- Calls a **downstream** dependency (`:9000`) through **Toxiproxy** (`:8666`) as a network proxy
- Exposes a `/work` endpoint that does real DB queries and downstream HTTP calls
- Exposes **Prometheus metrics**: `http_requests_total`, `http_request_latency_seconds_bucket`, `db_inflight`, `leak_mb`, `open_fds_simulated`, `disk_fill_mb`, `retry_calls_total`, `process_resident_memory_bytes`, `process_open_fds`, `chaos_mode` (per fault type)
- Has built-in **chaos endpoints** (`/chaos/*`) for 11 fault types -- the app literally breaks itself on demand
- Runs with `SYS_PTRACE` + `seccomp:unconfined` for strace syscall tracing

**The downstream mock** (`downstream/main.py`): simple HTTP responder simulating a backend dependency.

**Load generator** (`loadgen/main.py`): configurable traffic -- steady or mixed profile, target RPS, jitter, paths. Drives continuous `/work` requests so the system produces telemetry during both normal and fault periods.

---

### SLIDE 2: Chaos Injection System -- Exact Implementation

**Two-layer architecture**: `chaosctl.py` (195-line CLI) orchestrates faults via two backends:

**Layer 1 -- App-side faults** (HTTP POST to `http://app:8000/chaos/*`):


| Fault       | Command            | What it does in the app                                                                                         | Parameter                  |
| ----------- | ------------------ | --------------------------------------------------------------------------------------------------------------- | -------------------------- |
| CPU hog     | `cpu on 4`         | Spawns N busy-loop threads (`threading.Thread` spinning `while not stop`)                                       | workers (default 2)        |
| Memory leak | `memleak on 50`    | Background thread appends `bytearray(1MB)` every `1/rate` seconds to a list, capped at `CHAOS_MEM_LIMIT_MB=800` | mb_per_sec (default 20)    |
| Lock convoy | `lock on 60`       | Spawns N threads that all compete on a single `threading.Lock`, creating contention                             | threads (default 80)       |
| FD leak     | `fdleak on 200`    | Opens `/dev/null` handles at `rate_per_sec`, capped at `CHAOS_FD_LIMIT=5000`                                    | rate_per_sec (default 200) |
| Disk fill   | `disk fill 2000`   | Writes `mb` megabytes to `/data/fill.bin` in 1MB chunks, optional `fsync` per MB                                | mb (default 200)           |
| DB gate     | `dbgate 1`         | Sets `MAX_DB_INFLIGHT` semaphore to N (restricts concurrent DB queries)                                         | max_inflight (default 2)   |
| Retry storm | `retrystorm on 50` | Background thread fires `qps` requests/sec to `/flaky` with retries=3, timeout=0.2s                             | qps (default 20)           |
| DNS         | `dns bad`          | Points resolver at `203.0.113.123` (bogus IP) so DNS lookups fail                                               | server IP                  |


**Layer 2 -- Network faults via Toxiproxy** (`http://toxiproxy:8474`):


| Fault            | Command            | Toxiproxy toxic    | Details                                              |
| ---------------- | ------------------ | ------------------ | ---------------------------------------------------- |
| Latency          | `net latency 400`  | `latency` toxic    | Adds `ms` latency + 20% jitter to downstream traffic |
| Connection reset | `net reset_peer`   | `reset_peer` toxic | Resets TCP connections to downstream                 |
| Bandwidth limit  | `net bandwidth 64` | `bandwidth` toxic  | Limits downstream to `kbps` throughput               |


**Command flow example**: `docker compose --profile tools run --rm chaos memleak on 50` -> `chaosctl.py` parses args -> `POST http://app:8000/chaos/mem/leak/start?mb_per_sec=50` (with 8 retries, 1s backoff) -> app spawns leak thread -> app sets `chaos_mode{mode="mem_leak"}` Prometheus gauge to 1 -> writes event to `chaos_events.jsonl`

**Reset**: `chaos reset` calls `chaos_cpu_stop()`, `chaos_lock_convoy_stop()`, `chaos_mem_leak_stop()`, `chaos_fd_leak_stop()`, `retry_storm_stop()`, `chaos_disk_clear()`, `dns_set_server(None)`, `set_db_gate(10)` + clears all Toxiproxy toxics.

---

### SLIDE 3: Monitoring and Observability Stack

**Data pipeline**: app + cAdvisor -> Prometheus (scrapes every 15s, 7-day retention) -> Grafana dashboards -> SOM learner polls Prometheus API

**Exact services in `docker-compose.yml`** (10 services):

- `app` (FastAPI, port 8000) -- the service under test
- `downstream` (port 9000) -- backend dependency mock
- `toxiproxy` (ports 8474 control + 8666 proxy) -- network fault injection proxy between app and downstream
- `postgres` (PostgreSQL 16, port 5432) -- app database
- `loadgen` -- synthetic traffic generator
- `cadvisor` (v0.49.1, port 8080) -- container-level metrics (CPU, memory, network I/O)
- `prometheus` (v2.54.1, port 9090) -- metrics store
- `grafana` (v11.1.4, port 3000) -- dashboards
- `learner` (FastAPI, port 8100) -- SOM anomaly detector
- `chaos` (profile: tools) -- fault injection CLI, only runs on demand

**All data persisted** to `./data/` bind mounts: `data/app/logs/`, `data/app/events/chaos_events.jsonl`, `data/learner/events/anomaly_events.jsonl`, `data/learner/model/som_model.npz`, `data/prometheus/`

---

### SLIDE 4: SOM Learner -- Exact Training Pipeline

**Implementation**: `learner/main.py` (685 lines), runs as a FastAPI service with a background worker thread.

**9 Feature Queries** (each is an instant PromQL query to Prometheus):

1. `req_rate` = `sum(rate(http_requests_total[1m]))`
2. `latency_p95` = `histogram_quantile(0.95, sum by (le) (rate(http_request_latency_seconds_bucket[1m])))`
3. `db_inflight` = `max(db_inflight)`
4. `leak_mb` = `max(leak_mb)`
5. `open_fds_sim` = `max(open_fds_simulated)`
6. `disk_fill_mb` = `max(disk_fill_mb)`
7. `retry_rate` = `sum(rate(retry_calls_total[1m]))`
8. `proc_mem_bytes` = `max(process_resident_memory_bytes)`
9. `proc_open_fds` = `max(process_open_fds)`

- Plus: `chaos_on` = `sum(chaos_mode) > 0` (used to gate which samples go into training -- only normal samples collected)

**Phase 1 -- Bootstrap (collecting normal data)**:

- Poll Prometheus every `POLL_SEC` (1.0s in paper-fidelity mode)
- If `chaos_mode == 0` (no active faults), append the 9-feature vector to `bootstrap_normal` list
- Continue until `len(bootstrap_normal) >= BOOTSTRAP_SAMPLES` (180 in paper mode)
- This takes ~180 seconds of clean operation minimum

**Phase 2 -- Training** (triggered once after bootstrap):

1. Stack all 180 samples into a numpy matrix (shape: 180 x 9)
2. Compute per-feature max: `scale = max(samples, axis=0)` (replace zeros with 1.0)
3. Normalize: `(samples / scale) * 100.0` so all features are in [0, 100]
4. **K-fold cross-validation** (K=3 folds):
  - For each fold: hold out 1/3 as validation, train on remaining 2/3
  - For each fold: try `SOM_INIT_TRIALS=3` different random weight initializations
  - Total: 3 folds x 3 inits = **9 SOM models trained and compared**
5. Per trial: initialize 32x32 SOM weights uniformly in [0, 100], run **8 epochs** of full-batch training
6. SOM training step: find BMU (best matching unit), compute Gaussian neighborhood influence, update all weights toward input vector
7. Score each model: compute neighborhood area scores on validation fold, threshold = `quantile(scores, 0.85)`, measure `val_acc` = fraction of validation samples below threshold
8. **Pick best**: model with highest validation accuracy wins
9. Persist to `som_model.npz`

**Phase 3 -- Online scoring** (continuous after training):

1. Every `POLL_SEC`: collect 9-feature sample from Prometheus
2. **Smooth**: sliding window mean over last `SOM_SMOOTH_K=5` samples
3. **Normalize**: using frozen training scale -> clip (optional) -> input vector `x`
4. **Score**: find BMU of `x` in SOM grid -> compute **UBL neighborhood area** at BMU (sum of L1 distances between BMU weight vector and its 4 Manhattan neighbors' weight vectors)
5. **Anomaly**: `area_score >= threshold` ?
6. **Streak**: count consecutive anomalous samples; alarm fires only after `ANOMALY_STREAK=3` consecutive anomalies
7. **Cause inference**: when alarm fires, find Q=5 nearest normal-region neurons, vote on which feature dimensions differ most between anomalous BMU and normal neighbors
8. **Log**: write alarm to `anomaly_events.jsonl` with score, threshold, features, cause ranking
9. **Online learning**: if no chaos active, also call `train_step(x)` to incrementally update the SOM

---

### SLIDE 5: SOM Scoring Modes -- What We Tested

**Two scoring modes implemented and compared**:


| Setting                | `paper_fidelity` (UBL paper-aligned)   | `current_default` (baseline comparison) |
| ---------------------- | -------------------------------------- | --------------------------------------- |
| `SOM_SCORING_MODE`     | `ubl_area` (neighborhood area)         | `bmu` (BMU distance only)               |
| `SOM_SMOOTH_K`         | 5 (5-point moving average)             | 1 (no smoothing)                        |
| `ANOMALY_STREAK`       | 3 (3 consecutive anomalies)            | 1 (single anomaly triggers alarm)       |
| `ANOMALY_QUANTILE`     | 0.85 (85th percentile threshold)       | 0.99 (99th percentile)                  |
| `SOM_ROWS x SOM_COLS`  | 32 x 32 = 1024 neurons                 | 20 x 20 = 400 neurons                   |
| `SOM_KFOLD`            | 3 (3-fold cross-validation)            | 1 (no CV, train on all)                 |
| `SOM_INIT_TRIALS`      | 3 (3 random inits per fold)            | 1 (single init)                         |
| `SOM_ONLINE_CLIP_MODE` | `none`                                 | `clip_300` (cap features at 300)        |
| `train_mode`           | `fresh_bootstrap` (new model each run) | `warm_start` (reuse prior model)        |


**UBL area scoring** (paper method): For each neuron, sum the L1 distances to all 4 adjacent neurons' weight vectors. Neurons in "crowded" regions of the map (where many normal samples cluster) have small areas; neurons in sparse/anomalous regions have large areas. Score = area at the BMU of the input sample.

**BMU distance scoring** (baseline): Simply the Euclidean distance from input to its BMU weight vector. Simpler but less paper-faithful.

---

### SLIDE 6: Experiment Orchestration -- Exact Run Protocol

**Implementation**: `experiments/run_experiments.py` (1107 lines)

**Input**: A YAML "fault matrix" file that defines:

- Learner variants (SOM configs to test)
- Fault definitions (command_on/off, intensity ladders, duration ladders)
- Global timing (warmup, bootstrap, inject, cooldown)
- Seeds, repeats, loadgen profile

**Matrix expansion**: The runner computes the full Cartesian product: `variants x faults x intensity_levels x duration_levels x seeds x repeats` = all `RunConfig` objects.

**Per-run execution sequence** (exact steps from code):

1. Delete `anomaly_events.jsonl` and `score_stream.jsonl` (clean slate for alarms)
2. If `fresh_bootstrap`: delete `som_model.npz` (force learner to retrain from scratch)
3. `docker compose stop learner` -> `rm -f learner` -> `up -d --build --force-recreate learner` (with run-specific env vars: SOM_ROWS, SOM_COLS, ANOMALY_QUANTILE, UBL_RANDOM_SEED, etc.)
4. `wait_for_app_ready()`: poll `http://localhost:8000/health` every 1s for up to 90s
5. `chaos reset` (clear any lingering faults from prior run)
6. Sleep **warmup** (60s in research stages) -- app + loadgen run normally, learner starts collecting
7. Sleep **bootstrap** (240s in research stages) -- learner accumulates 180+ normal samples
8. `wait_for_learner_trained()`: poll `http://localhost:8100/status` every 1s for up to 300s, confirm `trained=true` AND `som_model.npz` exists on disk
9. Log `inject_start` event
10. Execute fault: `docker compose --profile tools run --rm chaos {command_on}` (e.g., `memleak on 50`)
11. Sleep **fault_window_on_delay** (14s) -- gives the fault time to manifest in telemetry before we start counting
12. Log `fault_window on` event (evaluation starts counting from here)
13. Sleep **inject hold** (fault duration: 60-300s depending on ladder)
14. Log `inject_stop`, execute `chaos {command_off}`
15. Log `fault_window off`
16. Sleep **cooldown** (90s) -- observe recovery
17. `chaos reset` (final cleanup)
18. Snapshot artifacts: copy `chaos_events.jsonl`, `anomaly_events.jsonl`, `som_model.npz` into `campaign-{id}/{run-id}/artifacts/`
19. Write `manifest.json` with full run metadata (timing, env, status, learner_status_post_bootstrap)

**Campaign output structure**:

```
data/experiments/campaign-20260329T235958Z/
  campaign_meta.json          # matrix path, git SHA, compose hash, mode
  matrix.resolved.json        # expanded matrix with all env vars
  run_index.json              # status of every run (completed/failed/reason)
  {run-id}/
    manifest.json             # per-run metadata
    run_events.jsonl           # timestamped phase events (warmup, bootstrap, inject, etc.)
    artifacts/
      chaos_events.jsonl       # what faults were active when
      anomaly_events.jsonl     # what alarms the learner fired
      som_model.npz            # trained SOM weights + threshold
```

---

### SLIDE 7: Evaluation Pipeline -- How We Measure Detection

**Implementation**: `experiments/evaluate.py` (1048 lines)

**Per-run evaluation**:

1. Parse `run_events.jsonl` to find exact `fault_window on/off` timestamps and `post_bootstrap_ts`
2. Parse `artifacts/anomaly_events.jsonl` to get all alarm timestamps and scores
3. Match alarms to fault windows using `many_to_many` matching:
  - **True Positive (TP)**: alarm during a fault window
  - **False Positive (FP)**: alarm outside any fault window
  - **False Negative (FN)**: fault window with no alarm
  - **True Negative (TN)**: no alarm in non-fault period
4. Compute: Precision, Recall, F1, lead time (how far before fault window end the first alarm fires)
5. **Paper-style metrics** (`paper_AT` / `paper_AF`): UBL Equation 5 style on our lab labels
6. Extract SOM metadata from `som_model.npz`: validation accuracy, U-matrix topology proxy, quantization error

**Campaign-level aggregation**:

- `run_metrics.csv` -- one row per run with all metrics
- `rollup_metrics.csv` -- mean metrics grouped by (variant, fault_id) with 95% CI
- `stratified_rollup_metrics.csv` -- mean metrics by fault_family, study_scope, ablation_block
- `som_rollup_metrics.csv` -- SOM topology/quality summaries per (variant, fault)
- `failed_runs.csv` -- runs that didn't complete with failure phase and reason
- `report.md` -- human-readable summary of everything above

---

### SLIDE 8: Phase 1 -- First Experiments, Everything Broke (March 28, 3:29-4:47pm)

**Context**: SOM was just implemented (commit `05d3a18` at 5:41pm, feature queries updated at 6:20pm, merged at 6:27pm). First experiments start ~1 hour after the merge.

**Campaign 1** (`campaign-20260328T192927Z`, 7:29pm):

- Config: 2 variants (paper_fidelity, current_default) x 3 faults (mem_leak, cpu_hog, net_latency) x 1 repeat = **6 runs**
- Timing: warmup **20s**, bootstrap **30s**, inject **20s**, cooldown **20s** -- **extremely short**
- BOOTSTRAP_SAMPLES still at default 180, but only 30s of collection time at 2s polling = max 15 samples collected
- **Result: ALL F1=0.000, ALL FPR=1.000** -- every alarm scored as false positive, zero true detections
- **Root cause**: With only 15 samples (bootstrap couldn't complete in 30s), the SOM was never properly trained. The threshold was effectively random. But the evaluator scored everything as FP because the fault window timing was misaligned.

**Campaign 2** (`campaign-20260328T194046Z`, 7:40pm):

- **Identical matrix** to Campaign 1 (same timings, same variants)
- **Result: TPR=1.000 but FPR=0.96-0.99, F1=0.016 to 0.076**
- The detector was alarming on **everything** -- normal and anomalous periods alike
- Lead times of 44-54s (alarm fires ~45s into a 20s inject -- before/during warmup, not during the fault)
- **What changed**: runs were staggered (serial vs near-simultaneous), so evaluator saw slightly different alarm/window alignment. But fundamentally same problem: untrained SOM alarming continuously.

**Campaign 3** (`campaign-20260328T195223Z`, 7:52pm):

- **Changed**: Added `lock_convoy` (4th fault), cut timings further (warmup **10s**, bootstrap **15s**, inject **10s**, cooldown **10s**), added **2 repeats**
- Planned: 4 faults x 2 variants x 2 repeats = **16 runs**. Only **7 runs** materialized (all paper_fidelity only).
- **lock_convoy run aborted**: `run_events.jsonl` shows warmup -> bootstrap -> `inject_start` then **nothing** -- the injection never completed. First evidence that lock_convoy has orchestration issues.
- **6 other runs** evaluated: similar pathological metrics to Campaigns 1-2.

**Campaign 4** (`campaign-20260328T200447Z`, 8:04pm):

- Dropped lock_convoy (back to 3 faults), same short timings
- Only **4 of 12 planned runs** completed; `cpu_hog r02` truncated (reached `inject_stop` but no `completed` phase)
- **Pattern**: partial campaigns becoming the norm -- infrastructure instability

**What we learned from Phase 1**:

- **Timing was catastrophically wrong**: 30s bootstrap at 2s polling = 15 samples. Need 180 samples = 360s at minimum.
- **Evaluation couldn't score properly** because alarms fired during bootstrap (before faults) and the evaluator had no way to distinguish pre-training noise from real detections
- **Lock convoy injection has orchestration issues** (first hint of a recurring problem)
- **Most campaigns were partial** -- Docker orchestration was fragile under rapid experiment iteration

---

### SLIDE 9: Phase 2 -- Trying to Get the Screening Matrix Working (March 28, 8:00-11:30pm)

**Rapid iteration**: 10+ campaigns in 3.5 hours, most never fully completing.

**Campaign `201006Z` (8:10pm)**: Tried the smallest possible config -- 2 faults, 1 variant, timings: warmup **5s**, bootstrap **10s**, inject **8s**, cooldown **8s**. **Never executed** -- matrix file only, no runs on disk.

**Campaign `201647Z` (8:16pm)**: Reverted to original 20/30/20/20 timing with all 3 faults, both variants. **6/6 completed**. Metrics show high FPR still, `net_hog_like_latency` still F1=0 with current_default.

**Campaign `203554Z` (8:35pm)**: Same faults but now **explicit SOM parameters pinned in matrix** for first time -- `SOM_ROWS=32`, `SOM_COLS=32`, `SOM_KFOLD=3`, `SOM_INIT_TRIALS=3`, `SOM_NORMALIZATION_MODE=train_max_100`, `SOM_CAUSE_Q=5`. Previously these were unset (using Docker compose defaults). **6/6 completed** but no evaluation report generated.

**Campaign `210509Z` (9:05pm)** -- **First Screening Matrix Campaign**:

- Switched to `fault_matrix_screening.yaml`: **4 variants** (paper_fidelity_anchor, screen_smooth_streak, screen_threshold, screen_training_topology) x **4 faults** (+ lock_convoy) x 3 repeats = **48 planned**
- Timing: warmup **30s**, bootstrap **120s**, inject **90s**, cooldown **45s** -- much longer
- **Only 10 runs completed** (all paper_fidelity_anchor variant). Lock_convoy only got 1/3 repeats. No other variants executed. **38 runs missing from disk**.

**Campaign `221540Z` (10:15pm)** -- **First `dry_run: true` screening smoke**:

- `fault_matrix_screening.yaml`, 4 variants x 3 faults = **12 planned, 12 "completed"** in index. But `dry_run=true`, so Docker commands were printed but not actually executed. **Validated matrix expansion logic**.

**Campaigns `222443Z` through `224912Z` (10:24-10:49pm)** -- **Three attempts at real screening smoke**:

- `222443Z`: Started 2/12 runs, then abandoned (manifests stuck at `"running"`)
- `223031Z`: Got to 4/12, then stopped (added first non-anchor variant: `screen_smooth_streak` on `mem_leak`)
- `224912Z`: Only 1/12 (regression -- less progress than prior attempt)
- **Problem**: Docker learner container repeatedly failing to start or stalling

**Campaign `225112Z` (10:51pm)** -- **First complete screening smoke**:

- Same 12-run screening smoke, but with `**reuse_learner_if_env_unchanged: true`** (new flag!)
- Tightened phases: bootstrap **15s**, warmup **10s**, cooldown **10s**
- **12/12 completed**. First time all screening variants actually ran.
- **What changed**: learner reuse between runs with same config avoided the Docker rebuild flakiness. Shorter phases meant faster iteration.

**What we learned from Phase 2**:

- **Docker container lifecycle is fragile**: `docker compose up --build learner` fails intermittently under rapid iteration. Learner reuse between compatible runs was the fix.
- **Need to pin all SOM parameters explicitly** in the matrix, not rely on compose defaults
- **Screening matrix (48 runs) is too large** for initial debugging; need minimal single-run matrices first
- **Dry runs are useful** for validating matrix expansion before spending real compute

---

### SLIDE 10: Phase 2b -- Switching to Minimal Matrices (March 28 11:30pm - March 29 1am)

**Key insight**: Stop trying to run 48-run screening campaigns and debug with a single run first.

**Campaign `231201Z` (11:12pm)** -- **Dry-run main matrix with seed sweep**:

- `fault_matrix.yaml` (main matrix), 2 variants x 3 faults x 3 seeds = **18 runs, dry_run=true**
- **18/18 "completed"** -- validated the multi-seed expansion. Matching mode was `one_to_one`.

**Campaign `231458Z` (11:14pm)** -- **Same 18-run matrix, but live**:

- **10 completed, 8 failed**. Failures: `docker compose up -d --build learner` returned exit code 1 for 8 runs (all `net_hog_like_latency` seeds for paper_fidelity, some mem/net for current_default)
- **Docker build flakiness** again -- the learner image build was intermittently failing.

**Campaign `231825Z` (11:18pm)** -- **Minimal single-run, dry_run**:

- New `fault_matrix_minimal.yaml`: **1 variant** (`minimal_ubl`), **1 fault** (`mem_leak`), **1 run**
- Timing: warmup **5s**, bootstrap **75s**, inject **15s**, cooldown **8s**, fault_window_on_delay **14s**
- Small SOM: 16x16 grid, BOOTSTRAP_SAMPLES=30 (can actually complete in 75s at 1s polling)
- **1/1 completed** (dry run)

**Campaign `231843Z` (11:18pm)** -- **Minimal single-run, LIVE**:

- Identical to 231825Z but `dry_run: false`
- **1/1 completed**... but **F1=0.000, FPR=1.000** (same pathological result as Campaign 1)
- **Why still broken**: The 16x16 SOM with 30 bootstrap samples trained successfully (evidenced by model file existing), but the evaluation was still using the old matching mode or the alarm stream was contaminated

**Campaign `000451Z` (12:04am, March 29)** -- **Same minimal run, new insight**:

- **1/1 completed, F1=0.000** -- 0 TP, 3 FP, 1 FN
- But now SOM checkpoint tracking was added: **val_acc=0.933** -- the SOM was correctly learning normal behavior with 93.3% validation accuracy!
- **Critical realization**: The SOM trains correctly. The problem is not training. It's one of: (a) alarm timing vs fault window alignment, (b) evaluation matching mode, (c) alarm stream contamination from prior runs

---

### SLIDE 11: Phase 3 -- Debugging Alarm/Evaluation Pipeline (March 29, 12am-3am)

**Campaign `001055Z` (12:10am)** -- **Paper-faithful smoke dry run**:

- New `fault_matrix_ubl_exact_smoke.yaml`: 1 variant (`paper_fidelity_smoke`) x 3 faults = 3 runs
- Timing: warmup **10s**, bootstrap **180s** (paper-aligned!), inject **20s**, cooldown **10s**, delay **14s**
- **3/3 completed** (dry run, validating new matrix)

**Campaign `001256Z` (12:12am)** -- **Paper-faithful smoke, LIVE**:

- Same config, `dry_run: false`
- **3/3 completed but all F1=0.000**. CPU and net rows show `som_model_present: false` in evaluation -- the SOM model was not being found by the evaluator even though it existed
- **Bug identified**: artifact snapshot was not copying `som_model.npz` correctly from the Docker bind mount. The evaluator couldn't find the model, so SOM quality metrics were blank.

**Campaign `003753Z` (12:37am)** -- **Extended bootstrap window**:

- Same paper-faithful smoke but bootstrap raised to **240s** (from 180) and `BOOTSTRAP_SAMPLES` explicitly set to **180** in matrix
- **3/3 completed**. SOM model now copying correctly to artifacts.

**Campaign `010813Z` (1:08am)** -- **Replication smoke dry run**:

- `fault_matrix_ubl_replication_smoke.yaml`: warmup **30s**, bootstrap **300s**, inject **60s**, cooldown **30s**, mixed load at 6 RPS
- **18/18 completed** (dry). Testing scaling to multi-seed, longer phases.

**Campaign `011344Z` (1:13am)** -- **2-hour smoke, LIVE**:

- `fault_matrix_ubl_2h.yaml`: 6 runs, warmup **20s**, bootstrap **240s**, inject **45s**, cooldown **20s**
- **6/6 completed but F1 very low**: cpu_hog F1=0 with 8 FP; mem_leak F1=0.19-0.26
- **Still broken** for CPU hog; mem_leak improving but not reliable. Evaluation pipeline now producing paper_AT/paper_AF columns for first time (pipeline upgrade happened between earlier campaigns).

**Campaign `033154Z` (3:31am)** -- **THE BREAKTHROUGH**:

- Back to `fault_matrix_minimal.yaml`, 1 run, mem_leak only
- Same timing as `000451Z` (warmup 5, bootstrap 75, inject 15, cooldown 8, delay 14)
- Same learner env... **except different `UBL_RANDOM_SEED`** (811420061 vs 2970075567)
- **Result: F1=1.000, paper_AT=1.0, paper_AF=0.0, lead_time=5.85s, 5 TP, 0 FP**
- **What actually changed between `000451Z` (F1=0) and `033154Z` (F1=1.0)**:
  - Same matrix, same timing, same learner hyperparameters
  - Different seed -> different SOM weight initialization -> different map topology
  - Between these runs: evaluation pipeline was upgraded (paper_AT/paper_AF metrics added, matching mode changed to `many_to_many`)
  - Alarm log clearing between runs was fixed (no contamination from prior run)
- **This proved the full system works end-to-end for the first time**: chaos injection -> metric deviation -> SOM scores anomaly -> streak triggers alarm -> evaluator correctly matches alarm to fault window

---

### SLIDE 12: Phase 3b -- ROC Sweep and Ablation Start (March 29, 3:30am-5:30am)

**Campaign `033841Z` (3:38am)** -- **Quantile threshold ROC sweep**:

- `fault_matrix_ubl_roc.yaml`: 5 runs sweeping `ANOMALY_QUANTILE` (0.70, 0.76, ...) on mem_leak
- Same minimal timing (5/75/14/15/8)
- **5/5 completed** -- first systematic hyperparameter sensitivity study

**Campaign `035726Z` (3:57am)** -- **Ablation start, 16 runs**:

- `fault_matrix_ablation_start.yaml`: 4 variants x 2 faults (mem_leak, cpu_hog) x 1 repeat = 16 runs
- Timing: warmup **15s**, bootstrap **90s**, inject **45s**, cooldown **25s**, no fault_window_on_delay
- Mixed load at 5 RPS / 18ms
- **16/16 completed** -- first multi-variant ablation to finish completely!

**Campaign `052721Z` (5:27am)** -- **Full 80-run ablation**:

- Same `fault_matrix_ablation_start.yaml` but **10 repeats** per cell, **longer phases** (warmup 20, bootstrap 120, inject 60, cooldown 25)
- **80/80 completed, 0 failed**
- Results per variant:
  - `paper_fidelity_anchor` (32x32, ubl_area, K=5, streak=3, q=0.85): **F1=0.000** for both faults -- paper-aligned config was too strict, zero detections
  - `screen_smooth_streak` (K=1, streak=1, q=0.85): **TPR=0.4-0.6, FPR=0.99+** -- detected faults but overwhelming false alarm flood
  - `screen_threshold` (K=5, streak=3, q=0.99): **TPR=0.6, FPR=0.996** -- same pattern: high recall but noise
  - `screen_training_topology` (20x20 SOM, K=1/fold=1/init=1): **F1=0.000, FPR=0.000** -- completely silent, detected nothing
- Paired significance tests: **all p > 0.75** -- no statistically significant differences
- **Key learning**: The paper_fidelity anchor is too conservative for short inject windows. But relaxing streak/smooth causes alarm floods. The 20x20 topology with minimal training (1 fold, 1 init) doesn't produce a useful model. There's a fundamental sensitivity-vs-false-alarm tradeoff.

---

### SLIDE 13: Phase 4 -- Infrastructure Flakiness and Docker Failures (March 29, 3-7pm)

**Campaign `152310Z` (3:23pm)** -- **Retry 80-run ablation with full mode**:

- Same `fault_matrix_ablation_start.yaml`, 80 runs
- **57 completed, 23 failed** (29% failure rate)
- Failure modes:
  - `docker compose up learner` exit code 1 (learner container won't start)
  - `docker compose rm/stop loadgen` exit code 1 (loadgen cleanup fails)
  - "Learner not trained/model-ready within 200s" with connection resets
  - "App did not become healthy within 90s" (app container crashed)
- **Docker orchestration under rapid run cycling was extremely fragile**

**Campaign `152523Z` (3:25pm)** -- **Quick smoke ablation, 8 runs**:

- Same matrix in smoke mode (trimmed to 8 runs)
- Timing: warmup/bootstrap/inject/cooldown all **10-15s** (smoke-trimmed)
- **8 planned, 8 FAILED** -- every single run failed
- Reason: bootstrap only 15s, BOOTSTRAP_SAMPLES capped to 15 in smoke mode, but learner wait timeout was 85s -- either bootstrap didn't finish or learner wasn't reachable (connection reset/refused)
- **Learning**: Smoke mode caps phases too aggressively for the learner to ever finish training

**Campaign `154031Z` (3:40pm)** -- **Retry smoke**:

- **4 completed, 4 failed** -- mixed results. Anchor variant and some screening variants on mem_leak worked; others timed out
- Confirms: smoke mode has ~50% success rate due to timing pressure

**Campaign `154850Z` (3:48pm)** -- **Another full 80-run attempt**:

- **44 completed, 36 failed** (55% completion) -- worse than `152310Z`'s 71%
- Docker flakiness not improving; campaigns running back-to-back without letting infrastructure stabilize

**Campaign `194351Z` (7:43pm)** -- **Minimal single-run, LIVE**:

- `fault_matrix_minimal.yaml`, 1 run, steady load at 4 RPS
- **1 planned, 1 FAILED**: "App did not become healthy within 90s" -- Connection reset by peer
- **The app container itself was crashing** -- accumulated state from many prior chaos runs without full Docker restart
- **Fix**: need to `docker compose down` and start fresh, not just cycle individual services

---

### SLIDE 14: Phase 5 -- Geometry Studies and Path to Research Stages (March 29, 8pm - midnight)

**Campaign `200229Z` (8:02pm)** -- **Minimal single-run retry after fresh stack start**:

- Same minimal config that failed 17 minutes earlier
- **1/1 completed** -- fresh Docker stack resolved the health issue

**Campaign `202341Z` (8:23pm)** -- **Minimal with updated config**:

- Updated `fault_matrix_minimal.yaml`: quantile **0.8** (from 0.85), streak **1** (from 2), bootstrap **90s** (from 75s)
- **1/1 completed**
- **First time `learner_status_post_bootstrap` was recorded**: trained=true, bootstrap_samples=30/30 collected, total_samples=47, threshold=39.66
- **Now we can verify** the learner actually trained before faults hit

**Campaign `203835Z` (8:38pm)** -- **First fault geometry sweep (smoke)**:

- New `fault_matrix_fault_geometry_paper_learner.yaml`: 1 paper-faithful variant, 4 faults, intensity x duration ladders
- **Smoke mode: 3 runs** (trimmed from full matrix)
- **2 completed, 1 failed**: cpu_hog failed (learner not trained within 85s with connection reset). mem_leak and net_latency completed.
- Artifact warning: `som_model.npz` not snapshotted (bind-mount issue) -- model trained but wasn't copied to host
- **Learning**: Smoke caps BOOTSTRAP_SAMPLES to 15, which is too small for reliable training; need full mode for paper-faithful experiments

**Campaign `210002Z` (9:00pm)** -- **Minimal geometry, FULL MODE** (the key transition):

- New `fault_matrix_fault_geometry_paper_learner_minimal.yaml`: 2 faults (mem_leak + lock_convoy), 2x2 intensity x duration = **8 runs**
- Full timing: warmup **60s**, bootstrap **240s**, inject variable (60-180s), cooldown **90s**, delay **14s**
- BOOTSTRAP_SAMPLES=**80** (smaller SOM, fewer needed), steady 6 RPS load
- **8/8 completed, 0 failed** -- first fully clean campaign with paper-aligned timings!
- `learner_status_post_bootstrap` confirmed: trained=true, 80/80 samples collected
- Results:
  - lock_convoy: **F1=1.000** (4/4 runs perfect)
  - mem_leak: **F1=0.500** (2/4 runs detected, 2/4 missed -- intensity/duration dependent)
- **This was the proof** that with proper timing and full mode, the system is stable and reliable

**Campaign `235958Z` (midnight)** -- **Research Stage 1 begins**:

- `fault_matrix_research_stage1_paper_geometry.yaml`
- 3 faults x 2 intensities x 2 durations x 2 seeds = **24 runs**
- Full research timing: warmup 60, bootstrap 240, inject variable, cooldown 90, delay 14
- BOOTSTRAP_SAMPLES=**180**, `paper_fidelity_research_anchor` variant (32x32 SOM, ubl_area, K=5, streak=3, q=0.85)
- **24/24 completed, 0 failed**
- **[You already have slides for this and Stages 2-3]**

---

### SLIDE 15: Summary of What Broke, How We Fixed It, and Key Numbers


| Problem                                   | When                                     | How We Found It                                            | Fix                                                                     | Impact                                                    |
| ----------------------------------------- | ---------------------------------------- | ---------------------------------------------------------- | ----------------------------------------------------------------------- | --------------------------------------------------------- |
| Bootstrap too short (30s for 180 samples) | Campaign 1-4 (March 28 7-8pm)            | F1=0 across all runs despite SOM training                  | Increased bootstrap from 30s to 240s; set POLL_SEC=1.0                  | Enabled SOM to actually complete training                 |
| No `wait_for_learner_trained` gate        | Campaigns 1-8                            | Faults injected before SOM finished training               | Added 300s polling gate on `/status` + `som_model.npz`                  | Guaranteed trained model before fault injection           |
| Docker learner build flakiness            | Campaigns `231458Z`, `222443Z`-`224912Z` | 8/18 failures, 10/12 failures, etc.                        | Added `--force-recreate`, retry logic, `reuse_learner_if_env_unchanged` | Went from ~50% to 100% completion rate                    |
| SOM parameters not pinned                 | Campaigns 1-6                            | Different results between runs with no config change       | Explicitly pin all SOM env vars in YAML matrix                          | Reproducible configurations                               |
| Alarm log contamination                   | Campaigns `000451Z` vs `033154Z`         | F1=0 with trained SOM (val_acc=0.933)                      | Delete anomaly_events.jsonl before each run                             | Clean alarm stream per run                                |
| Evaluation matching mode                  | Early campaigns                          | F1=0 despite alarms during faults                          | Changed from `one_to_one` to `many_to_many`                             | Correct TP/FP/FN counting                                 |
| `som_model.npz` not snapshotted           | Campaign `203835Z`                       | SOM quality columns blank in evaluation                    | Fixed bind-mount artifact copy path                                     | SOM metrics available for analysis                        |
| App health crash                          | Campaign `194351Z`                       | "Connection reset by peer" after 90s                       | Full `docker compose down` between experiment sessions                  | Stable fresh-start infrastructure                         |
| Smoke mode too aggressive                 | Campaign `152523Z` (8/8 failed)          | BOOTSTRAP_SAMPLES capped to 15, learner never trains       | Use `full` mode for paper-faithful experiments                          | All research campaigns use full mode                      |
| `lock_convoy off` command failure         | Campaign `195223Z`, Stage 2              | `run_events.jsonl` stuck after `inject_start`; exit code 1 | Retry logic in `chaosctl.py` (8 retries, 1s backoff)                    | Reduced but not eliminated (1 failure in 30 Stage 2 runs) |


**By the numbers**: 57 campaigns, ~350+ individual runs attempted, 22 campaigns with full evaluation reports, code evolved from 685-line learner + 152-line chaosctl to a 1107-line experiment runner + 1048-line evaluator + expanded chaosctl/app -- all in 48 hours.

---

## Implementation Notes

The deliverable is a single markdown file `experiments/reports/experiment_slides_revised.md` containing all the above slide content with exact numbers, ready to copy-paste into the PowerPoint. All numbers are sourced from actual `campaign_meta.json`, `run_index.json`, `manifest.json`, and `evaluation/report.md` files.