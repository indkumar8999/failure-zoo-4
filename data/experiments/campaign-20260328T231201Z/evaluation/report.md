# UBL Fault Injection Report

## Mean Metrics by Variant and Fault

| Fault | Variant | n | TPR | FPR | Precision | Recall | F1 (95% CI) | Lead Time (s, 95% CI) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| cpu_hog_like | current_default | 3 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |
| cpu_hog_like | paper_fidelity | 3 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |
| mem_leak | current_default | 3 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |
| mem_leak | paper_fidelity | 3 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |
| net_hog_like_latency | current_default | 3 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |
| net_hog_like_latency | paper_fidelity | 3 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |

## Paper-Faithful Findings

- `cpu_hog_like` / `paper_fidelity`: F1=0.000, TPR=0.000, FPR=0.000, faithfulness=paper-faithful-with-proxy
- `mem_leak` / `paper_fidelity`: F1=0.000, TPR=0.000, FPR=0.000, faithfulness=paper-faithful-with-proxy
- `net_hog_like_latency` / `paper_fidelity`: F1=0.000, TPR=0.000, FPR=0.000, faithfulness=paper-faithful-with-proxy

## Extended Findings

- `cpu_hog_like` / `current_default`: F1=0.000, lead=0.00s, ablation_block=decision
- `mem_leak` / `current_default`: F1=0.000, lead=0.00s, ablation_block=decision
- `net_hog_like_latency` / `current_default`: F1=0.000, lead=0.00s, ablation_block=decision

## Interaction Effects and Deltas vs Paper Fidelity

- `cpu_hog_like` / `current_default` vs `paper_fidelity`: ΔF1=+0.000, ΔTPR=+0.000, ΔFPR=+0.000, ΔLead=+0.00s
- `mem_leak` / `current_default` vs `paper_fidelity`: ΔF1=+0.000, ΔTPR=+0.000, ΔFPR=+0.000, ΔLead=+0.00s
- `net_hog_like_latency` / `current_default` vs `paper_fidelity`: ΔF1=+0.000, ΔTPR=+0.000, ΔFPR=+0.000, ΔLead=+0.00s

## Key Negative Results and Caveats

- Low-F1 case `cpu_hog_like` / `current_default`: F1=0.000, TPR=0.000, FPR=0.000
- Low-F1 case `cpu_hog_like` / `paper_fidelity`: F1=0.000, TPR=0.000, FPR=0.000
- Low-F1 case `mem_leak` / `current_default`: F1=0.000, TPR=0.000, FPR=0.000
- Low-F1 case `mem_leak` / `paper_fidelity`: F1=0.000, TPR=0.000, FPR=0.000
- Low-F1 case `net_hog_like_latency` / `current_default`: F1=0.000, TPR=0.000, FPR=0.000

## Stratified Rollups

| Group Type | Group Name | n | Mean F1 | Mean TPR | Mean FPR |
|---|---|---:|---:|---:|---:|
| ablation_block | decision | 18 | 0.000 | 0.000 | 0.000 |
| fault_family | paper_aligned | 18 | 0.000 | 0.000 | 0.000 |
| study_scope | extended | 9 | 0.000 | 0.000 | 0.000 |
| study_scope | paper_faithful | 9 | 0.000 | 0.000 | 0.000 |
| variant_fault_family | current_default|paper_aligned | 9 | 0.000 | 0.000 | 0.000 |
| variant_fault_family | paper_fidelity|paper_aligned | 9 | 0.000 | 0.000 | 0.000 |

## Reproducibility Artifacts

- Source metrics: `run_metrics.csv`, `rollup_metrics.csv`, `stratified_rollup_metrics.csv`, `delta_vs_paper_fidelity.csv`.
- ROC-style threshold points: `roc_points.csv`.
- Matching mode: `one_to_one`.
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
| cpu_hog_like | current_default | 1 | +0.000 | 1.0000 | 1.0000 | +0.000 | +0.000 | +0.00 |
| mem_leak | current_default | 1 | +0.000 | 1.0000 | 1.0000 | +0.000 | +0.000 | +0.00 |
| net_hog_like_latency | current_default | 1 | +0.000 | 1.0000 | 1.0000 | +0.000 | +0.000 | +0.00 |

## Validity Notes

- Pending-window scoring (`W`) approximates prediction quality and should be stress-tested per workload.
- `TN` and `FPR` rely on evaluator approximation of negative opportunities; interpret absolute FPR as proxy-level, not a canonical binary denominator.
- Toxiproxy-based `net_hog_like` is a proxy for paper NetHog, not a byte-for-byte replica.
- If the learner runs in `bmu` mode, results are baseline comparisons and not strict UBL replication.
