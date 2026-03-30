# Failure Zoo (Python) — syscalls + metrics persisted to ./data

This is a Docker Compose lab for generating reproducible failure modes and collecting:
- **Syscall traces** (via `strace` running inside the app container)
- **Application metrics** (`/metrics` Prometheus format)
- **System/container metrics** (cAdvisor)
- **Ground-truth labels** (JSONL events when chaos is toggled)

All data is stored in a `./data/` folder on your host so it remains after containers stop.

## Start
```bash
docker compose up -d --build
```

## URLs
- App health: http://localhost:8000/health
- App metrics: http://localhost:8000/metrics
- SOM learner health: http://localhost:8100/health
- SOM learner status: http://localhost:8100/status
- SOM learner signal: http://localhost:8100/signal
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)
- cAdvisor: http://localhost:8080
- Toxiproxy API: http://localhost:8474

## Trigger chaos
```bash
docker compose run --rm chaos cpu on 4
docker compose run --rm chaos cpu off

docker compose run --rm chaos lock on 60
docker compose run --rm chaos lock off

docker compose run --rm chaos memleak on 50
docker compose run --rm chaos memleak off

docker compose run --rm chaos fdleak on 200
docker compose run --rm chaos fdleak off

docker compose run --rm chaos disk fill 2000
docker compose run --rm chaos disk clear

docker compose run --rm chaos dbgate 1
docker compose run --rm chaos dbgate 10

docker compose run --rm chaos retrystorm on 50
docker compose run --rm chaos retrystorm off

docker compose run --rm chaos net latency 400
docker compose run --rm chaos net reset_peer
docker compose run --rm chaos net bandwidth 64
docker compose run --rm chaos net clear

docker compose run --rm chaos dns bad
curl "http://localhost:8000/dns/test?name=example.com"
docker compose run --rm chaos dns ok

docker compose run --rm chaos reset
```

## UBL-style fault injection study

The repo now includes a reproducible campaign runner and evaluator in `experiments/`.

### Baseline learner modes

- **Paper-fidelity mode**:
  - `SOM_SCORING_MODE=ubl_area`
  - `SOM_SMOOTH_K=5`
  - `ANOMALY_STREAK=3`
  - `ANOMALY_QUANTILE=0.85`
  - `SOM_ROWS=32`, `SOM_COLS=32`
  - `SOM_KFOLD=3`, `SOM_INIT_TRIALS=3`
  - `SOM_NORMALIZATION_MODE=train_max_100`
  - `SOM_ONLINE_CLIP_MODE=none`
  - `SOM_CAUSE_Q=5` (cause-ranking nearby normal neurons)
- **Current baseline mode**:
  - `SOM_SCORING_MODE=bmu`
  - `SOM_SMOOTH_K=1`
  - `ANOMALY_STREAK=1`
  - `ANOMALY_QUANTILE=0.99`
  - `SOM_ROWS=20`, `SOM_COLS=20`
  - `SOM_KFOLD=1`, `SOM_INIT_TRIALS=1`
  - `SOM_NORMALIZATION_MODE=train_max_100`
  - `SOM_ONLINE_CLIP_MODE=clip_300`

`docker-compose.yml` now supports these vars through environment overrides.

### Fault taxonomy and matrix

- Matrix file: `experiments/fault_matrix.yaml`
- Screening matrix: `experiments/fault_matrix_screening.yaml`
- Bounded ablation start (Stage 0): `experiments/fault_matrix_ablation_start.yaml` (16 runs: 4 variants × 2 faults × 2 repeats)
- Focused matrix: `experiments/fault_matrix_focused.yaml`
- Includes:
  - Paper-aligned proxies: `mem_leak`, `cpu_hog_like`, `net_hog_like_latency`
  - Extended faults: `lock_convoy`, `fd_leak`, `disk_fill`, `db_gate`, `retry_storm`, `dns_test`, `net_reset_peer`, `net_bandwidth`
- Metadata tags for ablations:
  - `study_scope`: `paper_faithful` or `extended`
  - `ablation_block`: `fault`, `decision`, `training`, `som`
  - `hypothesis_id`, `interpretation_note`
  - `train_mode`: `fresh_bootstrap` or `warm_start`
  - `intensity_level`, `duration_level`, `pending_level`

### Rich normal behavior (sustained load)

- Campaign matrices can enable load generation with:
  - `loadgen_enabled`
  - `loadgen_profile`
  - `loadgen_rps`
  - `loadgen_ms`
- `run_experiments.py` starts `loadgen` when enabled so warmup/bootstrap have non-degenerate request/latency behavior.
- Without load generation, `req_rate` and `latency_p95` can collapse near zero for long intervals.

### Run a smoke campaign

```bash
python3 -m pip install -r experiments/requirements.txt
python3 experiments/run_experiments.py --mode smoke
```

### Run full campaign

```bash
python3 experiments/run_experiments.py --mode full
```

### Run specific matrix (screening/focused)

```bash
python3 experiments/run_experiments.py --mode full --matrix experiments/fault_matrix_screening.yaml
python3 experiments/run_experiments.py --mode full --matrix experiments/fault_matrix_focused.yaml
```

### Start ablation studies (bounded)

Stage 0 ablation matrix (see `experiments/ablation_design.md`): four screening-style learner variants vs `mem_leak` and `cpu_hog_like`, two repeats, one seed—**16 planned runs**.

```bash
python3 experiments/run_experiments.py --mode full --matrix experiments/fault_matrix_ablation_start.yaml
```

Then evaluate and report as usual. Stratified rollups in `evaluation/stratified_rollup_metrics.csv` group by `ablation_block` (`decision`, `training`, `fault`) for comparison to the anchor variant.

### Evaluate and report

```bash
# replace campaign folder with your latest output
python3 experiments/evaluate.py --campaign-dir data/experiments/campaign-<timestamp>
python3 experiments/report.py --evaluation-dir data/experiments/campaign-<timestamp>/evaluation
python3 experiments/plot_results.py --evaluation-dir data/experiments/campaign-<timestamp>/evaluation
```

Outputs:
- Per-run manifests and labels: `run_events.jsonl`, `manifest.json`
- Snapshot artifacts: learner anomalies and chaos labels
- Metrics: `evaluation/run_metrics.csv` (includes per-run `som_*` fields from `artifacts/som_model.npz`), `evaluation/rollup_metrics.csv`, `evaluation/stratified_rollup_metrics.csv`, `evaluation/som_rollup_metrics.csv` (SOM checkpoint rollups by variant/fault)
- Anchor deltas: `evaluation/delta_vs_paper_fidelity.csv`
- Paired significance tests: `evaluation/paired_significance.csv`
- Failed run accounting: `evaluation/failed_runs.csv`
- UBL fidelity checks: `evaluation/fidelity_checks.json`
- Validity ledger: `evaluation/validity_ledger.json`
- Markdown summary: `evaluation/report.md`
- Figure-ready charts: `evaluation/figures/*.png`, `evaluation/figures/*.svg`, `evaluation/figures/*.pdf`
- Plot sidecars: `evaluation/figures/data/*.csv`
- Unified machine-readable bundle: `evaluation/summary.json`

### Research documentation assets

- Fidelity checklist: `experiments/fidelity_checklist.md`
- Staged ablation design: `experiments/ablation_design.md`
- Manifest/provenance schema: `experiments/manifest_schema.md`
- Validity ledger schema: `experiments/validity_ledger_schema.md`

## Persisted outputs (host)
- `./data/app/syscalls/trace.*` — syscall traces (epoch timestamps + duration)
- `./data/app/events/chaos_events.jsonl` — chaos on/off labels (epoch timestamps)
- `./data/app/logs/*` — app & strace logs
- `./data/learner/model/som_model.npz` — persisted SOM model
- `./data/learner/events/anomaly_events.jsonl` — SOM anomaly outputs
- `./data/prometheus/` — Prometheus TSDB blocks
- `./data/grafana/` — Grafana state
- `./data/postgres/` — Postgres data

## Stop (data remains)
```bash
docker compose down
```

## Delete data
```bash
rm -rf ./data
```

## Notes for macOS
`strace` runs inside the Linux container (Docker Desktop’s Linux VM kernel), so it works on macOS without installing any syscall tools on the host.

## Validity notes for paper replication

- This environment is a practical proxy, not a Xen/VCL replica from the original UBL paper.
- `net_hog_like` uses Toxiproxy-based network toxics rather than the original traffic injection setup.
- The learner now supports paper-aligned controls for map size, neighborhood-area scoring, 3-consecutive alarms, percentile thresholding, train-max normalization, and K-fold selection.
- The paper's decentralized Xen learning-VM placement/migration architecture is intentionally out of scope in this Docker-based lab.
- Report outputs classify results as `paper-faithful`, `paper-faithful-with-proxy`, or `extended-beyond-paper`.
- Failed injections are captured as structured run statuses (`run_status`, `failed_phase`, `failure_reason`) instead of being silently dropped.


## Note: toxiproxy image
This project uses `ghcr.io/shopify/toxiproxy:latest` because the old Docker Hub `shopify/toxiproxy` repository is deprecated.


## Syscall tracing requirements
The app container enables `SYS_PTRACE` and disables the default seccomp profile so `strace` can run inside Docker.
