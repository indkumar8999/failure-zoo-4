# UBL Fault Injection Report

## Mean Metrics by Variant and Fault

| Fault | Variant | n | paper_AT | paper_AF | TPR | FPR (alarm stream) | Alarm FP frac | Precision | Recall | F1 (95% CI) | Lead Time (s, 95% CI) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cpu_hog_like | paper_fidelity_anchor | 2 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |
| cpu_hog_like | screen_smooth_streak | 6 | 0.333 | 0.344 | 0.333 | 0.556 | 0.556 | 0.111 | 0.333 | 0.167 [-0.040, 0.373] | 29.56 [-7.08, 66.21] |
| cpu_hog_like | screen_threshold | 10 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |
| cpu_hog_like | screen_training_topology | 3 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |
| mem_leak | paper_fidelity_anchor | 5 | 0.200 | 0.000 | 0.200 | 0.000 | 0.000 | 0.200 | 0.200 | 0.200 [-0.192, 0.592] | 2.43 [-2.33, 7.20] |
| mem_leak | screen_smooth_streak | 3 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |
| mem_leak | screen_threshold | 10 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |
| mem_leak | screen_training_topology | 5 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |

## Paper-Faithful Findings

- `mem_leak` / `paper_fidelity_anchor`: F1=0.200, precision=0.200, recall=0.200, paper_AT=0.200, paper_AF=0.000, FPR_alarm=0.000, faithfulness=paper-faithful-with-proxy
- `cpu_hog_like` / `paper_fidelity_anchor`: F1=0.000, precision=0.000, recall=0.000, paper_AT=0.000, paper_AF=0.000, FPR_alarm=0.000, faithfulness=paper-faithful-with-proxy

## Extended Findings

- `cpu_hog_like` / `screen_smooth_streak`: F1=0.167, precision=0.111, recall=0.333, lead=29.56s, ablation_block=decision
- `cpu_hog_like` / `screen_threshold`: F1=0.000, precision=0.000, recall=0.000, lead=0.00s, ablation_block=decision
- `cpu_hog_like` / `screen_training_topology`: F1=0.000, precision=0.000, recall=0.000, lead=0.00s, ablation_block=training
- `mem_leak` / `screen_smooth_streak`: F1=0.000, precision=0.000, recall=0.000, lead=0.00s, ablation_block=decision
- `mem_leak` / `screen_threshold`: F1=0.000, precision=0.000, recall=0.000, lead=0.00s, ablation_block=decision
- `mem_leak` / `screen_training_topology`: F1=0.000, precision=0.000, recall=0.000, lead=0.00s, ablation_block=training

## Interaction Effects and Deltas vs Paper Fidelity

- `cpu_hog_like` / `screen_smooth_streak` vs `paper_fidelity`: ΔF1=+0.167, ΔTPR=+0.333, ΔFPR=+0.556, ΔLead=+29.56s
- `cpu_hog_like` / `screen_threshold` vs `paper_fidelity`: ΔF1=+0.000, ΔTPR=+0.000, ΔFPR=+0.000, ΔLead=+0.00s
- `cpu_hog_like` / `screen_training_topology` vs `paper_fidelity`: ΔF1=+0.000, ΔTPR=+0.000, ΔFPR=+0.000, ΔLead=+0.00s
- `mem_leak` / `screen_smooth_streak` vs `paper_fidelity`: ΔF1=-0.200, ΔTPR=-0.200, ΔFPR=+0.000, ΔLead=-2.43s
- `mem_leak` / `screen_threshold` vs `paper_fidelity`: ΔF1=-0.200, ΔTPR=-0.200, ΔFPR=+0.000, ΔLead=-2.43s
- `mem_leak` / `screen_training_topology` vs `paper_fidelity`: ΔF1=-0.200, ΔTPR=-0.200, ΔFPR=+0.000, ΔLead=-2.43s

## Key Negative Results and Caveats

- Low-F1 case `cpu_hog_like` / `paper_fidelity_anchor`: F1=0.000, precision=0.000, recall=0.000, paper_AF=0.000, FPR_alarm=0.000
- Low-F1 case `cpu_hog_like` / `screen_threshold`: F1=0.000, precision=0.000, recall=0.000, paper_AF=0.000, FPR_alarm=0.000
- Low-F1 case `cpu_hog_like` / `screen_training_topology`: F1=0.000, precision=0.000, recall=0.000, paper_AF=0.000, FPR_alarm=0.000
- Low-F1 case `mem_leak` / `screen_smooth_streak`: F1=0.000, precision=0.000, recall=0.000, paper_AF=0.000, FPR_alarm=0.000
- Low-F1 case `mem_leak` / `screen_threshold`: F1=0.000, precision=0.000, recall=0.000, paper_AF=0.000, FPR_alarm=0.000

## Stratified Rollups

| Group Type | Group Name | n | Mean F1 | Mean Precision | Mean Recall | Mean TPR | Mean paper_AF | Mean FPR (alarm) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| ablation_block | decision | 36 | 0.056 | 0.046 | 0.083 | 0.083 | 0.057 | 0.093 |
| ablation_block | training | 8 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| fault_family | paper_aligned | 44 | 0.045 | 0.038 | 0.068 | 0.068 | 0.047 | 0.076 |
| study_scope | extended | 37 | 0.027 | 0.018 | 0.054 | 0.054 | 0.056 | 0.090 |
| study_scope | paper_faithful | 7 | 0.143 | 0.143 | 0.143 | 0.143 | 0.000 | 0.000 |
| variant_fault_family | paper_fidelity_anchor|paper_aligned | 7 | 0.143 | 0.143 | 0.143 | 0.143 | 0.000 | 0.000 |
| variant_fault_family | screen_smooth_streak|paper_aligned | 9 | 0.111 | 0.074 | 0.222 | 0.222 | 0.230 | 0.370 |
| variant_fault_family | screen_threshold|paper_aligned | 20 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| variant_fault_family | screen_training_topology|paper_aligned | 8 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

## SOM checkpoint summary

Per-run SOM fields are merged into `run_metrics.csv` (prefix `som_`). Topology uses mean L2 distance between adjacent map units (U-matrix proxy); quantization proxy is mean BMU distance on feature vectors sampled from `anomaly_events.jsonl` when available.

| Variant | Fault | n (SOM) | mean val acc | mean U-matrix | mean QE proxy |
|---|---|---:|---:|---:|---:|
| paper_fidelity_anchor | cpu_hog_like | 2 | 0.8504 | 25.7315 | 19.8136 |
| screen_smooth_streak | cpu_hog_like | 6 | 0.8889 | 254.4158 | 8394.5419 |
| screen_threshold | cpu_hog_like | 10 | 0.8889 | 222.1201 | 58.5707 |
| screen_training_topology | cpu_hog_like | 3 | 0.7875 | 7.5566 | 7.5034 |
| paper_fidelity_anchor | mem_leak | 4 | 0.8019 | 279.8138 | 21827.2989 |
| screen_smooth_streak | mem_leak | 3 | 0.9126 | 191.5087 | 23918.7755 |
| screen_threshold | mem_leak | 10 | 0.8889 | 221.9999 | 1451.6277 |
| screen_training_topology | mem_leak | 5 | 0.7950 | 11.9760 | 68.4450 |

## Reproducibility Artifacts

- Source metrics: `run_metrics.csv`, `rollup_metrics.csv`, `stratified_rollup_metrics.csv`, `delta_vs_paper_fidelity.csv`, `som_rollup_metrics.csv` (SOM lattice / checkpoint aggregates).
- ROC-style threshold points: `roc_points.csv`.
- Matching mode: `many_to_many`.
- Validity ledger: `validity_ledger.json`.
- Campaign metadata: captured in `summary.json` under `campaign_meta`.
- Failed runs captured in `failed_runs.csv` (included in `summary.json`).
- Paired significance results captured in `paired_significance.csv`.
- UBL fidelity checks captured in `fidelity_checks.json`.

## UBL Fidelity Checks

- Sampling interval includes 1s: `True`.
- Percentile threshold sweep present: `True`.
- Pending-window sweep present: `False`.
- PCA/kNN comparator present: `False`.

## Failure Accounting

| Run ID | Fault | Variant | Failed Phase | Reason |
|---|---|---|---|---|
| 20260329T154850Z-paper_fidelity_anchor-cpu_hog_like-ibase-dbase-wbase-s01-r01 | cpu_hog_like | paper_fidelity_anchor | execution | Command '['docker', 'compose', 'rm', '-f', 'loadgen']' returned non-zero exit status 1. |
| 20260329T154850Z-paper_fidelity_anchor-cpu_hog_like-ibase-dbase-wbase-s01-r03 | cpu_hog_like | paper_fidelity_anchor | execution | Command '['docker', 'compose', 'rm', '-f', 'loadgen']' returned non-zero exit status 1. |
| 20260329T154850Z-paper_fidelity_anchor-cpu_hog_like-ibase-dbase-wbase-s01-r04 | cpu_hog_like | paper_fidelity_anchor | execution | Command '['docker', 'compose', 'up', '-d', '--build', 'learner']' returned non-zero exit status 1. |
| 20260329T154850Z-paper_fidelity_anchor-cpu_hog_like-ibase-dbase-wbase-s01-r06 | cpu_hog_like | paper_fidelity_anchor | execution | Command '['docker', 'compose', 'rm', '-f', 'loadgen']' returned non-zero exit status 1. |
| 20260329T154850Z-paper_fidelity_anchor-cpu_hog_like-ibase-dbase-wbase-s01-r07 | cpu_hog_like | paper_fidelity_anchor | execution | Command '['docker', 'compose', 'up', '-d', '--build', 'learner']' returned non-zero exit status 1. |
| 20260329T154850Z-paper_fidelity_anchor-cpu_hog_like-ibase-dbase-wbase-s01-r08 | cpu_hog_like | paper_fidelity_anchor | execution | Command '['docker', 'compose', 'rm', '-f', 'loadgen']' returned non-zero exit status 1. |
| 20260329T154850Z-paper_fidelity_anchor-cpu_hog_like-ibase-dbase-wbase-s01-r09 | cpu_hog_like | paper_fidelity_anchor | execution | Command '['docker', 'compose', 'up', '-d', 'loadgen']' returned non-zero exit status 1. |
| 20260329T154850Z-paper_fidelity_anchor-cpu_hog_like-ibase-dbase-wbase-s01-r10 | cpu_hog_like | paper_fidelity_anchor | execution | Command '['docker', 'compose', 'up', '-d', '--build', 'learner']' returned non-zero exit status 1. |
| 20260329T154850Z-paper_fidelity_anchor-mem_leak-ibase-dbase-wbase-s01-r02 | mem_leak | paper_fidelity_anchor | execution | Command '['docker', 'compose', 'up', '-d', '--build', 'learner']' returned non-zero exit status 1. |
| 20260329T154850Z-paper_fidelity_anchor-mem_leak-ibase-dbase-wbase-s01-r05 | mem_leak | paper_fidelity_anchor | execution | Command '['docker', 'compose', 'rm', '-f', 'loadgen']' returned non-zero exit status 1. |
| 20260329T154850Z-paper_fidelity_anchor-mem_leak-ibase-dbase-wbase-s01-r06 | mem_leak | paper_fidelity_anchor | execution | Command '['docker', 'compose', 'up', '-d', '--build', 'learner']' returned non-zero exit status 1. |
| 20260329T154850Z-paper_fidelity_anchor-mem_leak-ibase-dbase-wbase-s01-r08 | mem_leak | paper_fidelity_anchor | execution | Command '['docker', 'compose', 'rm', '-f', 'loadgen']' returned non-zero exit status 1. |
| 20260329T154850Z-paper_fidelity_anchor-mem_leak-ibase-dbase-wbase-s01-r09 | mem_leak | paper_fidelity_anchor | execution | Command '['docker', 'compose', 'up', '-d', '--build', 'learner']' returned non-zero exit status 1. |
| 20260329T154850Z-screen_smooth_streak-cpu_hog_like-ibase-dbase-wbase-s01-r02 | cpu_hog_like | screen_smooth_streak | execution | Command '['docker', 'compose', 'up', '-d', 'loadgen']' returned non-zero exit status 1. |
| 20260329T154850Z-screen_smooth_streak-cpu_hog_like-ibase-dbase-wbase-s01-r03 | cpu_hog_like | screen_smooth_streak | execution | Command '['docker', 'compose', 'up', '-d', 'loadgen']' returned non-zero exit status 1. |
| 20260329T154850Z-screen_smooth_streak-cpu_hog_like-ibase-dbase-wbase-s01-r04 | cpu_hog_like | screen_smooth_streak | execution | Command '['docker', 'compose', 'up', '-d', 'loadgen']' returned non-zero exit status 1. |
| 20260329T154850Z-screen_smooth_streak-cpu_hog_like-ibase-dbase-wbase-s01-r08 | cpu_hog_like | screen_smooth_streak | execution | Command '['docker', 'compose', 'up', '-d', '--build', 'learner']' returned non-zero exit status 1. |
| 20260329T154850Z-screen_smooth_streak-mem_leak-ibase-dbase-wbase-s01-r01 | mem_leak | screen_smooth_streak | execution | Command '['docker', 'compose', 'rm', '-f', 'loadgen']' returned non-zero exit status 1. |
| 20260329T154850Z-screen_smooth_streak-mem_leak-ibase-dbase-wbase-s01-r02 | mem_leak | screen_smooth_streak | execution | Command '['docker', 'compose', 'up', '-d', 'loadgen']' returned non-zero exit status 1. |
| 20260329T154850Z-screen_smooth_streak-mem_leak-ibase-dbase-wbase-s01-r04 | mem_leak | screen_smooth_streak | execution | Command '['docker', 'compose', 'rm', '-f', 'loadgen']' returned non-zero exit status 1. |

## Paired Significance

| Fault | Variant | n Pairs | Mean ΔF1 | p(F1) | p(F1,BH) | Mean ΔTPR | Mean ΔFPR | Mean ΔLead(s) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| cpu_hog_like | screen_smooth_streak | 1 | +0.500 | 1.0000 | 1.0000 | +1.000 | +0.667 | +87.96 |
| cpu_hog_like | screen_threshold | 2 | +0.000 | 0.5000 | 1.0000 | +0.000 | +0.000 | +0.00 |
| cpu_hog_like | screen_training_topology | 1 | +0.000 | 1.0000 | 1.0000 | +0.000 | +0.000 | +0.00 |
| mem_leak | screen_smooth_streak | 1 | -1.000 | 1.0000 | 1.0000 | -1.000 | +0.000 | -12.15 |
| mem_leak | screen_threshold | 5 | -0.200 | 0.0625 | 0.3750 | -0.200 | +0.000 | -2.43 |
| mem_leak | screen_training_topology | 3 | -0.333 | 0.2500 | 0.7500 | -0.333 | +0.000 | -4.05 |

## Validity Notes

- Pending-window scoring (`W`) approximates prediction quality and should be stress-tested per workload.
- **paper_AT** / **paper_AF** follow UBL Eq. 5 style on this lab’s labels; **FPR (alarm stream)** is `fp/(fp+tp)` (same as alarm FP fraction), not paper AF. See `validity_ledger.json` and `run_metrics.csv`.
- Toxiproxy-based `net_hog_like` is a proxy for paper NetHog, not a byte-for-byte replica.
- If the learner runs in `bmu` mode, results are baseline comparisons and not strict UBL replication.
