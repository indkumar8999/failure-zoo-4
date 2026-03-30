# Research Ablation Design

This document defines staged, research-grade ablations to avoid a full Cartesian explosion while still covering all moving parts.

## Stage 0: Bounded start (recommended first)

Use `experiments/fault_matrix_ablation_start.yaml` for a **small** screening-style pass (**16 runs** by default: four learner variants × two paper-aligned faults × two repeats, one seed). Same hypotheses as Stage 1 below, without intensity/duration ladders or extra faults—good for validating Docker/learner stability before the full screening Cartesian product.

```bash
python3 experiments/run_experiments.py --mode full --matrix experiments/fault_matrix_ablation_start.yaml
```

## Stage 1: Screening Matrix

Use `experiments/fault_matrix_screening.yaml` to quickly identify sensitive factors:

- Fault block: family, intensity, and duration.
- Decision block: smoothing `k`, streak rule, and quantile threshold.
- Training block: K-fold/init trials.
- SOM block: geometry and learning parameters.

Expected output:

- Initial factor importance ranking (effect size on F1, TPR, FPR, lead time).
- Candidate interactions to carry into focused study.

## Stage 2: Focused Matrix

Use `experiments/fault_matrix_focused.yaml` to run denser sweeps on high-sensitivity factors and interactions:

- `SOM_SMOOTH_K × ANOMALY_STREAK`
- `ANOMALY_QUANTILE × fault intensity`
- `SOM_KFOLD × SOM_INIT_TRIALS`
- SOM geometry (`rows/cols`) with selected learning params.

Expected output:

- Confidence intervals for effect direction and magnitude.
- Stability and tradeoff curves per fault family.

## Required Metadata Tags

Every variant/fault should carry:

- `study_scope`: `paper_faithful` or `extended`
- `ablation_block`: `fault`, `decision`, `training`, or `som`
- `hypothesis_id`: concise experiment claim key
- `interpretation_note`: plain-language expectation for report synthesis

These are propagated to manifests and evaluator outputs for stratified rollups and plot generation.

## Research fault geometry series (paper-faithful learner fixed)

Use this when the objective is research-grade, hypothesis-driven fault geometry analysis with minimal confounding from learner drift.

### Stage R1: Paper-aligned geometry baseline

- Matrix: `experiments/fault_matrix_research_stage1_paper_geometry.yaml`
- Purpose: estimate direction and magnitude of intensity/duration effects for paper-aligned families.
- Faults: `mem_leak`, `cpu_hog_like`, `net_hog_like_latency`
- Expected budget: 24 runs (`3 faults x 2 intensity x 2 duration x 2 seeds`)
- Hypothesis: gradual faults (`mem_leak`) should show stronger duration dependence; rapid faults should be less duration-sensitive.

### Stage R2: Cross-family geometry consolidation

- Matrix: `experiments/fault_matrix_research_stage2_memleak_boundary.yaml`
- Purpose: evaluate the full research question across paper-aligned and selected extended families under one fixed learner profile.
- Faults: `mem_leak`, `cpu_hog_like`, `net_hog_like_latency`, `lock_convoy`, `disk_fill`
- Expected budget: 30 runs (`5 faults x 3 intensity x 2 duration x 1 seed`)
- Hypothesis: geometry trends are fault-family dependent; low-end `mem_leak` remains a boundary case but is interpreted in global context.

### Stage R3: Extended family transfer test

- Matrix: `experiments/fault_matrix_research_stage3_extended_transfer.yaml`
- Purpose: test whether the fixed paper-faithful detector transfers to selected extended families.
- Faults: `lock_convoy`, `disk_fill`
- Expected budget: 8 runs (`2 faults x 2 intensity x 2 duration x 1 seed`)
- Hypothesis: transfer remains strong for `lock_convoy`; `disk_fill` may expose different boundary behavior.

### Run order and progression gates

- Run in strict order: `R1 -> R2 -> R3`.
- Advance `R1 -> R2` if any paper-aligned fault has `mean_f1 < 0.8` or large seed variance.
- Advance `R2 -> R3` once cross-family geometry ordering is stable (direction of intensity and duration effects is consistent across most families).
- Stop adding geometry cells when confidence intervals overlap and no directional change appears in two consecutive added cells.

### Execution

```bash
bash experiments/run_research_series.sh
```
