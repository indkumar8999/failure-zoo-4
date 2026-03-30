# RQ-Style Ablation Report: Fault Geometry Under Fixed SOM

## 1) Study Context and Goal

This report documents a staged ablation study of UBL-style anomaly prediction in a containerized distributed-systems testbed. The main objective is to isolate how **fault family**, **fault intensity**, and **fault duration** affect prediction behavior while keeping SOM and decision settings largely fixed (paper-faithful-with-proxy profile).

The reader assumption is an advanced distributed-systems practitioner who is not familiar with this codebase. The report therefore emphasizes executable methodology, precise parameterization, and explicit caveats about partial campaign completion.

## 2) Research Questions

- **RQ1 (Stage 1):** How do paper-aligned fault families respond to intensity/duration geometry under a fixed SOM profile?
- **RQ2 (Stage 2):** How do those trends change when geometry is expanded to a mixed paper-aligned + extended fault family set?
- **RQ3 (Stage 3):** Are extended-family findings robust in a confirmatory transfer-focused run?

## 3) Experimental Procedure (What Was Executed)

This section focuses on what was done in each run. Environment details are intentionally brief.

Minimal runtime context:

- Services used: `app`, `learner`, `loadgen`, `downstream`, `toxiproxy`, `postgres` (plus observability services).
- Workload remained on for all stages with `loadgen_profile=steady`, `loadgen_rps=6`, `loadgen_ms=20`.
- Campaign bootstrap performed image build + service startup + app health gate before run loops.

These details matter only insofar as they enable the run procedure in Section 5.1.

## 4) Fixed Learner Profile and Why It Was Frozen

All stages use a single learner variant (`paper_fidelity_research_anchor`) with fixed decision/SOM controls:

- `SOM_SCORING_MODE=ubl_area`
- `SOM_SMOOTH_K=5`
- `ANOMALY_STREAK=3`
- `ANOMALY_QUANTILE=0.85`
- `POLL_SEC=1.0`
- `SOM_ROWS=32`, `SOM_COLS=32`
- `SOM_LR=0.7`, `SOM_SIGMA=4.0`
- `SOM_KFOLD=3`, `SOM_INIT_TRIALS=3`
- `SOM_NORMALIZATION_MODE=train_max_100`
- `SOM_ONLINE_CLIP_MODE=none`
- `SOM_CAUSE_Q=5`
- `BOOTSTRAP_SAMPLES=180`
- `train_mode=fresh_bootstrap`

This freeze is deliberate: it shifts explanatory power to fault geometry instead of detector tuning.

Sources:

- `failure-zoo-4/experiments/fault_matrix_research_stage1_paper_geometry.yaml`
- `failure-zoo-4/experiments/fault_matrix_research_stage2_memleak_boundary.yaml`
- `failure-zoo-4/experiments/fault_matrix_research_stage3_extended_transfer.yaml`

## 5) Fault Injection Methodology

### 5.1 Injection Execution Flow Per Run

This is the primary methodological sequence used for all reported results:

1. Reset per-run logs/artifacts (`anomaly_events.jsonl`, `score_stream.jsonl`)
2. Recreate learner container (`stop/rm/up --build --force-recreate`) for clean env uptake
3. `chaos reset`
4. `warmup` sleep
5. `bootstrap` sleep
6. learner gate: wait until `trained=true` on learner status and `som_model.npz` exists
7. `fault_on` command
8. `fault_window_on_delay_s` sleep (14s)
9. injection hold (`duration_ladder_s` cell value)
10. `fault_off` command
11. `cooldown` sleep
12. `chaos reset`
13. snapshot artifacts into run folder

Source: `failure-zoo-4/experiments/run_experiments.py`.

### 5.2 Fault Families and Command-Level Injection

Faults are applied via tool-container commands mapped in matrix `command_on`/`command_off`.

- `mem_leak`: `memleak on {intensity}` / `memleak off`
- `cpu_hog_like`: `cpu on {intensity}` / `cpu off`
- `net_hog_like_latency`: `net latency {intensity}` / `net clear`
- `lock_convoy`: `lock on {intensity}` / `lock off`
- `disk_fill`: `disk fill {intensity}` / `disk clear`

Notes:

- Network faults are Toxiproxy-based proxies.
- `disk_fill` may induce long writes and occasional control-path instability under heavy MB values.

Sources:

- Stage matrices in `failure-zoo-4/experiments/*.yaml` listed above
- Chaos CLI mapping in `failure-zoo-4/chaos/chaosctl.py`

## 6) Evaluation Methodology

### 6.1 Raw Inputs and Artifact Path

Each run records:

- `run_events.jsonl`: phase and fault window timeline
- `manifest.json`: run metadata, run status, learner snapshot metadata
- `artifacts/`: `chaos_events.jsonl`, `anomaly_events.jsonl` (if present), `som_model.npz` (if present)

Campaign evaluation aggregates to:

- `run_metrics.csv`
- `rollup_metrics.csv`
- `stratified_rollup_metrics.csv`
- `som_rollup_metrics.csv`
- `failed_runs.csv` (when failures exist)
- `summary.json`
- `report.md`

Source: `failure-zoo-4/experiments/evaluate.py`, `failure-zoo-4/experiments/report.py`.

### 6.2 Metric Computation Path

- Fault windows are inferred from `run_events.jsonl` `fault_window` markers.
- Alarms come from `artifacts/anomaly_events.jsonl`.
- Matching mode used in these campaigns: `many_to_many`.
- `paper_AT` and `paper_AF` are computed in evaluator/UBL metric pipeline and reported separately from legacy alarm-stream FPR.
- Lead-time metrics are computed from alarm vs target-window timing.

Critical caveat: legacy `fpr` column in run metrics corresponds to alarm-stream `fp/(fp+tp)` and is not equivalent to paper AF. Use `paper_af` for paper-style false alarm interpretation.

Source: `failure-zoo-4/experiments/evaluate.py`.

## 7) Stage Definitions and Planned Geometry

## 7.1 Stage 1 (R1): Paper-Aligned Geometry Baseline

Matrix: `failure-zoo-4/experiments/fault_matrix_research_stage1_paper_geometry.yaml`

- Faults: `mem_leak`, `cpu_hog_like`, `net_hog_like_latency`
- Intensity ladder: 2 levels each (`low`, `high`)
- Duration ladder: 2 levels each (`short`, `long`)
- Seeds: `[41, 42]`
- Repeats: 1
- Planned runs: `3 x 2 x 2 x 2 = 24`

## 7.2 Stage 2 (R2): Cross-Family Geometry Consolidation

Matrix: `failure-zoo-4/experiments/fault_matrix_research_stage2_memleak_boundary.yaml`  
(`meta.name`: `ubl_research_stage2_cross_family_geometry`)

- Faults: `mem_leak`, `cpu_hog_like`, `net_hog_like_latency`, `lock_convoy`, `disk_fill`
- Intensity ladder: 3 levels each (mem includes `very_low`)
- Duration ladder: 2 levels each
- Seeds: `[42]`
- Repeats: 1
- Planned runs: `5 x 3 x 2 x 1 = 30`

## 7.3 Stage 3 (R3): Extended-Family Confirmatory Transfer

Matrix: `failure-zoo-4/experiments/fault_matrix_research_stage3_extended_transfer.yaml`

- Faults: `lock_convoy`, `disk_fill`
- Intensity ladder: 2 levels each
- Duration ladder: 2 levels each
- Seeds: `[42]`
- Repeats: 1
- Planned runs: `2 x 2 x 2 x 1 = 8`

## 8) Results by Research Question

## 8.1 RQ1 (Stage 1): Paper-Aligned Family Response Under Fixed SOM

Campaign: `campaign-20260329T235958Z`

Per-fault rollup (from evaluation report):

- `mem_leak` (`n=8`): F1 `0.958`, precision `1.000`, recall/paper_AT `0.925`, paper_AF `0.000`, lead time `4.89s`.
- `cpu_hog_like` (`n=8`): F1 `0.750`, precision `0.750`, recall/paper_AT `0.750`, paper_AF `0.000`, lead time `2.54s`.
- `net_hog_like_latency` (`n=8`): F1 `0.125`, precision/recall/paper_AT `0.125`, paper_AF `0.000`, lead time `0.41s`.

Interpretation:

- `mem_leak` is consistently detectable with useful lead time.
- `cpu_hog_like` is intermediate.
- `net_hog_like_latency` is a clear negative result under fixed decision thresholds.

Completion/failure status:

- planned 24, completed 24, failed 0.

## 8.2 RQ2 (Stage 2): Cross-Family Geometry Effects

Campaign: `campaign-20260330T101857Z`

Per-fault rollup:

- `mem_leak` (`n=6`): F1 `0.948`, precision `0.972`, recall/paper_AT `0.931`, paper_AF `0.002`, lead `4.52s`.
- `cpu_hog_like` (`n=6`): F1 `0.548`, precision `0.528`, recall/paper_AT `0.667`, paper_AF `0.167`, alarm-FPR `0.139`, lead `2.57s`.
- `net_hog_like_latency` (`n=6`): F1 `0.333`, precision/recall `0.333`, paper_AF `0.000`, lead `0.78s`.
- `lock_convoy` (`n=5`): F1 `1.000`, recall `1.000`, paper_AF `0.000`, lead `3.99s`.
- `disk_fill` (`n=2`): F1 `1.000`, recall `1.000`, paper_AF `0.000`, lead `4.86s`.

Stratified rollups:

- `extended` family: mean F1 `1.000` (`n=7`)
- `paper_aligned` family: mean F1 `0.610` (`n=18`)

Interpretation:

- Family dependence persists strongly under broader geometry.
- Extended families are highly detectable in completed cells.
- `cpu_hog_like` introduces the main false-alarm burden.
- `net_hog_like_latency` remains the hardest family.

Completion/failure status:

- planned 30
- completed/evaluated rows: 25
- failed runs recorded: 1 (`lock_convoy ... lock off` command failure)
- remaining planned slots absent from evaluation: 4 (interruption/partial completion context)

## 8.3 RQ3 (Stage 3): Confirmatory Extended-Family Transfer

Campaign: `campaign-20260330T165222Z`

Per-fault rollup:

- `lock_convoy` (`n=4`): F1 `1.000`, precision/recall/paper_AT `1.000`, paper_AF `0.000`, lead `4.10s`.
- `disk_fill` (`n=2`): F1 `1.000`, precision/recall/paper_AT `1.000`, paper_AF `0.000`, lead `4.13s`.

Stratified extended-family row:

- mean F1 `1.000`, mean paper_AF `0.000`, `n=6`.

Interpretation:

- Stage 3 provides confirmatory evidence that extended-family transfer is robust in completed cells.
- Claim strength remains limited by small `n` for `disk_fill`.

Completion/failure status:

- planned 8
- completed/evaluated rows: 6
- failed runs recorded in evaluation: 0
- two planned slots missing due campaign interruption context.

## 9) Discussion

### 9.1 What Was Learned Across Stages

1. **Fault-family dependency is the dominant finding.**
  Under a fixed paper-faithful SOM profile, some fault families (mem_leak, lock_convoy, disk_fill) are reliably detectable while others (net_hog_like_latency, partly cpu_hog_like) are substantially harder.
2. **Lead-time tracks detectability quality.**
  Strong families generally preserve multi-second lead windows; weak network latency faults show very short lead times.
3. **False-alarm behavior is family-specific, not uniform.**
  The main non-zero AF/FPR pressure in completed data is concentrated in `cpu_hog_like`, not in all families.

### 9.2 Why This Matters for System Operators

- A single global threshold policy may be insufficient for heterogeneous fault regimes.
- Operational risk is concentrated in low-detectability families; those should receive either family-specific calibration or additional observability features.

### 9.3 Stage-2 Partial Completion Impact

- Stage 2 still supports directional conclusions because completed runs cover all families and ladders materially.
- However, Stage 2 should be interpreted as **partially complete**; confidence on exact aggregate magnitudes is lower than in a fully completed 30-run campaign.

## 10) Threats to Validity and Failure Accounting

1. **Infrastructure interruptions**
  - Docker engine interruptions and chaos command failures caused partial completion in Stages 2 and 3.
  - This induces unbalanced sample sizes by fault and cell.
2. **Proxy fidelity**
  - Network and some system faults are proxy implementations; results are faithful-with-proxy rather than exact historical paper replication.
3. **Metric caveat**
  - Alarm-stream FPR (`fp/(fp+tp)`) differs from paper AF; paper claims must use `paper_AF`.
4. **Small-n strata**
  - `disk_fill` in later stages has low `n`; robust directional support exists, but tight variance claims are limited.

## 11) Conclusions and Next Targeted Experiments

## 11.1 Claims Supported Strongly

- Under fixed paper-faithful SOM settings, extended `lock_convoy` and completed `disk_fill` cells are highly detectable with zero paper-AF in observed runs.
- `mem_leak` remains strongly detectable across Stage 1 and Stage 2.

## 11.2 Claims Supported Directionally (Not Final)

- `net_hog_like_latency` remains difficult under current fixed settings, even after geometry expansion.
- `cpu_hog_like` presents a sensitivity/false-alarm tradeoff in expanded geometry.

## 11.3 Recommended Follow-Up

1. Run a targeted completion matrix only for missing Stage 2/Stage 3 cells to balance counts.
2. Keep SOM topology fixed; test decision-level adaptations for hard families (`net_hog_like_latency`, `cpu_hog_like`):
  - threshold sweeps (`ANOMALY_QUANTILE`)
  - pending-window sensitivity
3. Add a focused report appendix explicitly enumerating completed vs failed vs missing cells per stage to keep claims auditable.

## 12) Reproducibility Pointers

- Runner and protocol logic: `failure-zoo-4/experiments/run_experiments.py`
- Evaluator and metric aggregation: `failure-zoo-4/experiments/evaluate.py`
- Stage matrices:
  - `failure-zoo-4/experiments/fault_matrix_research_stage1_paper_geometry.yaml`
  - `failure-zoo-4/experiments/fault_matrix_research_stage2_memleak_boundary.yaml`
  - `failure-zoo-4/experiments/fault_matrix_research_stage3_extended_transfer.yaml`
- Stage evaluation outputs:
  - `failure-zoo-4/data/experiments/campaign-20260329T235958Z/evaluation/`
  - `failure-zoo-4/data/experiments/campaign-20260330T101857Z/evaluation/`
  - `failure-zoo-4/data/experiments/campaign-20260330T165222Z/evaluation/`

