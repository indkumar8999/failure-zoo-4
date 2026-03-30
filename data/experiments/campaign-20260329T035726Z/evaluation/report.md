# UBL Fault Injection Report

## Mean Metrics by Variant and Fault

| Fault | Variant | n | paper_AT | paper_AF | TPR | FPR (alarm stream) | Alarm FP frac | Precision | Recall | F1 (95% CI) | Lead Time (s, 95% CI) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cpu_hog_like | paper_fidelity_anchor | 2 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |
| cpu_hog_like | screen_smooth_streak | 2 | 1.000 | 1.000 | 1.000 | 0.949 | 0.949 | 0.051 | 1.000 | 0.097 [0.090, 0.104] | 32.22 [29.10, 35.33] |
| cpu_hog_like | screen_threshold | 2 | 0.000 | 1.000 | 0.000 | 1.000 | 1.000 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |
| cpu_hog_like | screen_training_topology | 2 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |
| mem_leak | paper_fidelity_anchor | 2 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |
| mem_leak | screen_smooth_streak | 2 | 1.000 | 1.000 | 1.000 | 0.895 | 0.895 | 0.105 | 1.000 | 0.190 [0.131, 0.249] | 43.31 [21.91, 64.71] |
| mem_leak | screen_threshold | 2 | 0.000 | 1.000 | 0.000 | 1.000 | 1.000 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |
| mem_leak | screen_training_topology | 2 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |

## Paper-Faithful Findings

- `cpu_hog_like` / `paper_fidelity_anchor`: F1=0.000, precision=0.000, recall=0.000, paper_AT=0.000, paper_AF=0.000, FPR_alarm=0.000, faithfulness=paper-faithful-with-proxy
- `mem_leak` / `paper_fidelity_anchor`: F1=0.000, precision=0.000, recall=0.000, paper_AT=0.000, paper_AF=0.000, FPR_alarm=0.000, faithfulness=paper-faithful-with-proxy

## Extended Findings

- `mem_leak` / `screen_smooth_streak`: F1=0.190, precision=0.105, recall=1.000, lead=43.31s, ablation_block=decision
- `cpu_hog_like` / `screen_smooth_streak`: F1=0.097, precision=0.051, recall=1.000, lead=32.22s, ablation_block=decision
- `cpu_hog_like` / `screen_threshold`: F1=0.000, precision=0.000, recall=0.000, lead=0.00s, ablation_block=decision
- `cpu_hog_like` / `screen_training_topology`: F1=0.000, precision=0.000, recall=0.000, lead=0.00s, ablation_block=training
- `mem_leak` / `screen_threshold`: F1=0.000, precision=0.000, recall=0.000, lead=0.00s, ablation_block=decision
- `mem_leak` / `screen_training_topology`: F1=0.000, precision=0.000, recall=0.000, lead=0.00s, ablation_block=training

## Interaction Effects and Deltas vs Paper Fidelity

- `mem_leak` / `screen_smooth_streak` vs `paper_fidelity`: ΔF1=+0.190, ΔTPR=+1.000, ΔFPR=+0.895, ΔLead=+43.31s
- `cpu_hog_like` / `screen_smooth_streak` vs `paper_fidelity`: ΔF1=+0.097, ΔTPR=+1.000, ΔFPR=+0.949, ΔLead=+32.22s
- `cpu_hog_like` / `screen_threshold` vs `paper_fidelity`: ΔF1=+0.000, ΔTPR=+0.000, ΔFPR=+1.000, ΔLead=+0.00s
- `cpu_hog_like` / `screen_training_topology` vs `paper_fidelity`: ΔF1=+0.000, ΔTPR=+0.000, ΔFPR=+0.000, ΔLead=+0.00s
- `mem_leak` / `screen_threshold` vs `paper_fidelity`: ΔF1=+0.000, ΔTPR=+0.000, ΔFPR=+1.000, ΔLead=+0.00s
- `mem_leak` / `screen_training_topology` vs `paper_fidelity`: ΔF1=+0.000, ΔTPR=+0.000, ΔFPR=+0.000, ΔLead=+0.00s

## Key Negative Results and Caveats

- Low-F1 case `cpu_hog_like` / `paper_fidelity_anchor`: F1=0.000, precision=0.000, recall=0.000, paper_AF=0.000, FPR_alarm=0.000
- Low-F1 case `cpu_hog_like` / `screen_threshold`: F1=0.000, precision=0.000, recall=0.000, paper_AF=1.000, FPR_alarm=1.000
- Low-F1 case `cpu_hog_like` / `screen_training_topology`: F1=0.000, precision=0.000, recall=0.000, paper_AF=0.000, FPR_alarm=0.000
- Low-F1 case `mem_leak` / `paper_fidelity_anchor`: F1=0.000, precision=0.000, recall=0.000, paper_AF=0.000, FPR_alarm=0.000
- Low-F1 case `mem_leak` / `screen_threshold`: F1=0.000, precision=0.000, recall=0.000, paper_AF=1.000, FPR_alarm=1.000

## Stratified Rollups

| Group Type | Group Name | n | Mean F1 | Mean Precision | Mean Recall | Mean TPR | Mean paper_AF | Mean FPR (alarm) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| ablation_block | decision | 12 | 0.048 | 0.026 | 0.333 | 0.333 | 0.667 | 0.641 |
| ablation_block | training | 4 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| fault_family | paper_aligned | 16 | 0.036 | 0.020 | 0.250 | 0.250 | 0.500 | 0.480 |
| study_scope | extended | 12 | 0.048 | 0.026 | 0.333 | 0.333 | 0.667 | 0.641 |
| study_scope | paper_faithful | 4 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| variant_fault_family | paper_fidelity_anchor|paper_aligned | 4 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| variant_fault_family | screen_smooth_streak|paper_aligned | 4 | 0.143 | 0.078 | 1.000 | 1.000 | 1.000 | 0.922 |
| variant_fault_family | screen_threshold|paper_aligned | 4 | 0.000 | 0.000 | 0.000 | 0.000 | 1.000 | 1.000 |
| variant_fault_family | screen_training_topology|paper_aligned | 4 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

## SOM checkpoint summary

Per-run SOM fields are merged into `run_metrics.csv` (prefix `som_`). Topology uses mean L2 distance between adjacent map units (U-matrix proxy); quantization proxy is mean BMU distance on feature vectors sampled from `anomaly_events.jsonl` when available.

| Variant | Fault | n (SOM) | mean val acc | mean U-matrix | mean QE proxy |
|---|---|---:|---:|---:|---:|
| paper_fidelity_anchor | cpu_hog_like | 2 | 0.9231 | 4.4543 | 575.2401 |
| screen_smooth_streak | cpu_hog_like | 2 | 0.9231 | 7.3637 | 16297.5632 |
| screen_threshold | cpu_hog_like | 2 | 0.9231 | 562.1763 | 6242.0517 |
| screen_training_topology | cpu_hog_like | 2 | 0.8438 | 1.7502 | 114.7761 |
| paper_fidelity_anchor | mem_leak | 2 | 0.8497 | 2.8243 | 60750.5934 |
| screen_smooth_streak | mem_leak | 2 | 0.9231 | 7.8832 | 24062.1091 |
| screen_threshold | mem_leak | 2 | 0.9231 | 490.7668 | 8039.1765 |
| screen_training_topology | mem_leak | 2 | 0.8500 | 2.9595 | 243.0831 |

## Reproducibility Artifacts

- Source metrics: `run_metrics.csv`, `rollup_metrics.csv`, `stratified_rollup_metrics.csv`, `delta_vs_paper_fidelity.csv`, `som_rollup_metrics.csv` (SOM lattice / checkpoint aggregates).
- ROC-style threshold points: `roc_points.csv`.
- Matching mode: `many_to_many`.
- Validity ledger: `validity_ledger.json`.
- Campaign metadata: captured in `summary.json` under `campaign_meta`.
- Paired significance results captured in `paired_significance.csv`.
- UBL fidelity checks captured in `fidelity_checks.json`.

## UBL Fidelity Checks

- Sampling interval includes 1s: `True`.
- Percentile threshold sweep present: `True`.
- Pending-window sweep present: `False`.
- PCA/kNN comparator present: `False`.

## Failure Accounting

- No failed runs recorded.

## Paired Significance

| Fault | Variant | n Pairs | Mean ΔF1 | p(F1) | p(F1,BH) | Mean ΔTPR | Mean ΔFPR | Mean ΔLead(s) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| cpu_hog_like | screen_smooth_streak | 2 | +0.097 | 0.5000 | 0.5000 | +1.000 | +0.949 | +32.22 |
| cpu_hog_like | screen_threshold | 2 | +0.000 | 0.5000 | 0.5000 | +0.000 | +1.000 | +0.00 |
| cpu_hog_like | screen_training_topology | 2 | +0.000 | 0.5000 | 0.5000 | +0.000 | +0.000 | +0.00 |
| mem_leak | screen_smooth_streak | 2 | +0.190 | 0.5000 | 0.5000 | +1.000 | +0.895 | +43.31 |
| mem_leak | screen_threshold | 2 | +0.000 | 0.5000 | 0.5000 | +0.000 | +1.000 | +0.00 |
| mem_leak | screen_training_topology | 2 | +0.000 | 0.5000 | 0.5000 | +0.000 | +0.000 | +0.00 |

## Validity Notes

- Pending-window scoring (`W`) approximates prediction quality and should be stress-tested per workload.
- **paper_AT** / **paper_AF** follow UBL Eq. 5 style on this lab’s labels; **FPR (alarm stream)** is `fp/(fp+tp)` (same as alarm FP fraction), not paper AF. See `validity_ledger.json` and `run_metrics.csv`.
- Toxiproxy-based `net_hog_like` is a proxy for paper NetHog, not a byte-for-byte replica.
- If the learner runs in `bmu` mode, results are baseline comparisons and not strict UBL replication.
