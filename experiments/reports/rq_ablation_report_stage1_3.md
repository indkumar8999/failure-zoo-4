# RQ-Style Ablation Report: Fault Geometry Under a Fixed UBL Detector

## 1) Scope and Motivation

This study asks a targeted question: if we keep the anomaly detector configuration fixed, how much of prediction performance is explained by **fault family**, **fault intensity**, and **fault duration**?

The detector is inspired by UBL (Unsupervised Behavior Learning): a SOM-based model learns normal behavior from unlabeled operational telemetry, then raises alarms when runtime behavior deviates sufficiently from the learned manifold. The experiments are designed as staged ablations, not one-shot sweeps, so each stage answers a specific research question.

## 2) Reader Primer: What UBL Means in This Project

In this repository, UBL-style behavior prediction uses:

- a SOM trained on a bootstrap window of normal telemetry,
- a decision layer (smoothing + streak + quantile threshold) to convert scores into alarms,
- fault-window labels from run events to evaluate prediction quality.

The study label used in evaluation is `paper-faithful-with-proxy`. This means detector settings are aligned with paper-style choices, but fault realizations are practical lab proxies (for example Toxiproxy-based network faults rather than byte-identical historical infrastructure conditions).

## 3) Research Questions

- **RQ1 (Stage 1):** Under fixed SOM/decision settings, how do paper-aligned faults respond to intensity-duration geometry?
- **RQ2 (Stage 2):** Do those trends persist when extending to mixed paper-aligned + extended fault families?
- **RQ3 (Stage 3):** Are extended-family findings robust in a confirmatory transfer stage?

## 4) Methodology

### 4.1 Controlled Variables (Detector Frozen Across Stages)

All stages use a single learner variant (`paper_fidelity_research_anchor`) and keep detector parameters fixed:

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

Rationale: isolate geometry effects by minimizing detector-side confounding.

### 4.2 Run-Level Procedure (What Was Actually Executed)

Every run follows the same sequence:

1. Reset run artifacts (`anomaly_events.jsonl`, `score_stream.jsonl`).
2. Recreate learner container to guarantee clean env uptake.
3. Execute `chaos reset`.
4. Sleep `warmup_s`.
5. Sleep `bootstrap_s`.
6. Gate on readiness: continue only when learner reports `trained=true` and `som_model.npz` exists.
7. Execute fault-on command.
8. Sleep `fault_window_on_delay_s` (14s).
9. Hold injection for selected duration cell.
10. Execute fault-off command.
11. Sleep `cooldown_s`.
12. Execute `chaos reset`.
13. Snapshot run artifacts into run directory.

This procedure is implemented in `experiments/run_experiments.py` and is the core of methodological reproducibility.

### 4.3 Workload and Runtime Conditions

All three stages use steady foreground load:

- `loadgen_profile=steady`
- `loadgen_rps=6`
- `loadgen_ms=20`

This prevents degenerate idle behavior during warmup/bootstrap and provides consistent operational context for training and inference.

### 4.4 Fault Injection Setup and Fault Semantics

Faults are injected via `chaos` command mappings in stage matrices and `chaosctl`.

- `**mem_leak`**: `memleak on {intensity}` / `memleak off`  
Injects memory pressure with leak rate proportional to intensity.
- `**cpu_hog_like**`: `cpu on {intensity}` / `cpu off`  
Increases CPU contention via worker load.
- `**net_hog_like_latency**`: `net latency {intensity}` / `net clear`  
Adds proxy latency with Toxiproxy; intensity maps to latency magnitude.
- `**lock_convoy**`: `lock on {intensity}` / `lock off`  
Creates contention/convoy behavior via lock pressure.
- `**disk_fill**`: `disk fill {intensity}` / `disk clear`  
Writes to disk-fill target; higher intensity means larger write volume.

Observed operational behavior during campaigns:

- `mem_leak` and `cpu_hog_like` were generally stable to inject/clear.
- `net_hog_like_latency` was stable operationally but weak in detectability.
- `disk_fill` at high intensity occasionally stressed control paths and infrastructure (timeouts/engine instability risk).
- `lock_convoy` had one explicit command-off failure in Stage 2.

### 4.5 Stage Geometry and Planned Run Budgets

#### Stage 1 (R1): paper-aligned baseline

- Faults: `mem_leak`, `cpu_hog_like`, `net_hog_like_latency`
- Ladders: 2 intensity x 2 duration per fault
- Seeds: `[41, 42]`, repeats: 1
- Planned runs: `3 x 2 x 2 x 2 = 24`

#### Stage 2 (R2): cross-family consolidation

- Faults: `mem_leak`, `cpu_hog_like`, `net_hog_like_latency`, `lock_convoy`, `disk_fill`
- Ladders: 3 intensity x 2 duration per fault (mem includes `very_low`)
- Seeds: `[42]`, repeats: 1
- Planned runs: `5 x 3 x 2 x 1 = 30`

#### Stage 3 (R3): confirmatory extended transfer

- Faults: `lock_convoy`, `disk_fill`
- Ladders: 2 intensity x 2 duration per fault
- Seeds: `[42]`, repeats: 1
- Planned runs: `2 x 2 x 2 x 1 = 8`

### 4.6 Evaluation Pipeline (How Metrics Were Computed)

Per-run evaluation inputs:

- `run_events.jsonl` (phases, fault windows, timing)
- `artifacts/anomaly_events.jsonl` (alarm stream)
- `manifest.json` (run metadata/status)

Campaign aggregation outputs:

- `run_metrics.csv` (run-level metrics + SOM metadata)
- `rollup_metrics.csv` (variant/fault aggregate)
- `stratified_rollup_metrics.csv` (group-level aggregate)
- `som_rollup_metrics.csv` (SOM checkpoint summaries)
- `failed_runs.csv` (non-completed runs)
- `summary.json` and `report.md`

Evaluation mode in these campaigns: `matching_mode = many_to_many`.

Metric definitions used for claims:

- **Recall/TPR/F1/Precision** from alarm-vs-fault-window matching.
- **Lead time** from timing between alarms and evaluation target.
- **paper_AT / paper_AF** are the paper-style primary metrics in this project pipeline.
- **alarm-stream FPR** (`fp/(fp+tp)`) is reported too, but is not equivalent to paper AF.

## 5) Results by RQ

## 5.1 RQ1 (Stage 1): Paper-Aligned Fault Families

Campaign: `campaign-20260329T235958Z`  
Completion: planned 24, completed 24, failed 0.

Per-fault outcomes:

- `mem_leak` (`n=8`): F1 `0.958` (CI `[0.918, 0.998]`), precision `1.000`, recall/paper_AT `0.925`, paper_AF `0.000`, lead `4.89s`.
- `cpu_hog_like` (`n=8`): F1 `0.750` (CI `[0.429, 1.071]`), precision `0.750`, recall/paper_AT `0.750`, paper_AF `0.000`, lead `2.54s`.
- `net_hog_like_latency` (`n=8`): F1 `0.125` (CI `[-0.120, 0.370]`), precision/recall `0.125`, paper_AF `0.000`, lead `0.41s`.

Interpretation:

- Strong separation already appears in Stage 1: memory leak is highly detectable, network-latency proxy is difficult under fixed detector settings.

## 5.2 RQ2 (Stage 2): Cross-Family Geometry

Campaign: `campaign-20260330T101857Z`  
Completion: planned 30, evaluated completed rows 25, failed 1 (`lock_convoy ... lock off`), remaining planned slots not represented in rollups due interruption/partial completion.

Per-fault outcomes:

- `mem_leak` (`n=6`): F1 `0.948`, precision `0.972`, recall/paper_AT `0.931`, paper_AF `0.002`, lead `4.52s`.
- `cpu_hog_like` (`n=6`): F1 `0.548`, precision `0.528`, recall/paper_AT `0.667`, paper_AF `0.167`, alarm-FPR `0.139`, lead `2.57s`.
- `net_hog_like_latency` (`n=6`): F1 `0.333`, precision/recall `0.333`, paper_AF `0.000`, lead `0.78s`.
- `lock_convoy` (`n=5`): F1 `1.000`, recall `1.000`, paper_AF `0.000`, lead `3.99s`.
- `disk_fill` (`n=2`): F1 `1.000`, recall `1.000`, paper_AF `0.000`, lead `4.86s`.

Stratified family outcome:

- `extended` mean F1 `1.000` (`n=7`)
- `paper_aligned` mean F1 `0.610` (`n=18`)

Interpretation:

- Family dependence remains strong in mixed-family geometry.
- `cpu_hog_like` contributes the largest false-alarm burden.
- `net_hog_like_latency` remains the weakest regime despite some numerical improvement over Stage 1.

## 5.3 RQ3 (Stage 3): Confirmatory Extended Transfer

Campaign: `campaign-20260330T165222Z`  
Completion: planned 8, evaluated completed rows 6, failed recorded 0 (two planned slots absent due interruption context).

Per-fault outcomes:

- `lock_convoy` (`n=4`): F1 `1.000`, precision/recall/paper_AT `1.000`, paper_AF `0.000`, lead `4.10s`.
- `disk_fill` (`n=2`): F1 `1.000`, precision/recall/paper_AT `1.000`, paper_AF `0.000`, lead `4.13s`.

Interpretation:

- Stage 3 supports the Stage-2 directional claim that selected extended families are robustly detectable under the fixed detector profile.
- Confidence for `disk_fill` remains sample-size limited.

## 6) Cross-Stage Synthesis

1. **Primary empirical pattern:** detectability is strongly fault-family dependent when detector configuration is held fixed.
2. **Strong families:** `mem_leak`, `lock_convoy`, and completed `disk_fill` cells consistently show high recall/F1 and near-zero AF.
3. **Challenging families:** `net_hog_like_latency` remains difficult; `cpu_hog_like` exhibits a measurable sensitivity-vs-false-alarm tradeoff.
4. **Lead-time behavior:** stronger families preserve multi-second mean lead times; weak network-latency cases have shorter lead.

## 7) Discussion

### 7.1 Why Family Effects Dominate

Under this fixed SOM profile, fault families differ in how they perturb observed features:

- gradual memory/storage stressors create persistent deviations that are easier for score-and-streak rules to accumulate into alarms;
- short-lived or noisier network/CPU regimes can produce weaker or less stable pre-failure signatures.

This aligns with the observed split between high-performing (`mem_leak`, `lock_convoy`, `disk_fill`) and low-performing (`net_hog_like_latency`) families.

### 7.2 Detector Tradeoffs Observed

The same frozen decision policy produced:

- high precision and low AF in some regimes,
- but reduced sensitivity (or unstable precision/AF) in harder regimes.

This suggests the current detector is not uniformly calibrated across fault families. A single fixed threshold/streak setting may be robust for some families while underpowered or noisy for others.

### 7.3 Operational and Research Implications

- For operators: prioritize mitigation budgets around low-detectability families, not only average campaign metrics.
- For research: family-aware calibration should be tested after this geometry baseline, but only after recovering missing cells or explicitly reporting incomplete-cell uncertainty.

### 7.4 Effect of Partial Completion on Claim Strength

- Stage 1 claims are strongest (fully complete).
- Stage 2 and Stage 3 provide valid directional evidence but not complete-cell certainty.
- Claims about extended-family robustness are supported in completed runs, but small `n` and missing planned cells must remain explicit in conclusions.

## 8) Threats to Validity and Failure Accounting

1. **Partial campaign completion:** Stages 2 and 3 were interrupted; some planned cells were not evaluated.
2. **Run-level orchestration failure:** Stage 2 recorded one explicit failure (`lock off` command path).
3. **Proxy fault realism:** network and some system faults are proxy implementations, not literal infrastructure replicas.
4. **Metric interpretation caveat:** use `paper_AF` for paper-style false alarm claims; do not substitute alarm-stream FPR.
5. **Small-n extended cells:** especially `disk_fill`, limiting interval stability.

## 9) Conclusion

This three-stage ablation supports a clear conclusion: with SOM and decision settings held fixed, **fault geometry and family dominate predictive behavior**. The detector is strong for memory/storage/lock contention patterns in completed runs, weaker for network-latency proxy conditions, and mixed for CPU-hog-like conditions with nontrivial false-alarm pressure in Stage 2.

The practical next step is not another broad one-shot campaign. It is a targeted completion and calibration sequence:

- complete missing Stage 2/3 cells,
- keep SOM topology fixed,
- run focused decision-parameter sensitivity for hard families (`cpu_hog_like`, `net_hog_like_latency`),
- report claims with explicit cell-level completion accounting.

## 10) Reproducibility and Audit Paths

- Runner protocol: `failure-zoo-4/experiments/run_experiments.py`
- Evaluator logic and aggregation: `failure-zoo-4/experiments/evaluate.py`
- Stage matrices:
  - `failure-zoo-4/experiments/fault_matrix_research_stage1_paper_geometry.yaml`
  - `failure-zoo-4/experiments/fault_matrix_research_stage2_memleak_boundary.yaml`
  - `failure-zoo-4/experiments/fault_matrix_research_stage3_extended_transfer.yaml`
- Stage evaluation outputs:
  - `failure-zoo-4/data/experiments/campaign-20260329T235958Z/evaluation/`
  - `failure-zoo-4/data/experiments/campaign-20260330T101857Z/evaluation/`
  - `failure-zoo-4/data/experiments/campaign-20260330T165222Z/evaluation/`

