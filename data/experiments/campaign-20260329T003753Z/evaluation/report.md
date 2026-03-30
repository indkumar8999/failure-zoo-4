# UBL Fault Injection Report

## Mean Metrics by Variant and Fault

| Fault | Variant | n | TPR | FPR | Precision | Recall | F1 (95% CI) | Lead Time (s, 95% CI) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| cpu_hog_like | paper_fidelity_smoke | 1 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |
| mem_leak | paper_fidelity_smoke | 1 | 1.000 | 0.833 | 0.167 | 1.000 | 0.286 [0.286, 0.286] | 3.44 [3.44, 3.44] |
| net_hog_like_latency | paper_fidelity_smoke | 1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |

## Paper-Faithful Findings

- `mem_leak` / `paper_fidelity_smoke`: F1=0.286, precision=0.167, recall=1.000, TPR=1.000, FPR=0.833, faithfulness=paper-faithful-with-proxy
- `cpu_hog_like` / `paper_fidelity_smoke`: F1=0.000, precision=0.000, recall=0.000, TPR=0.000, FPR=1.000, faithfulness=paper-faithful-with-proxy
- `net_hog_like_latency` / `paper_fidelity_smoke`: F1=0.000, precision=0.000, recall=0.000, TPR=0.000, FPR=0.000, faithfulness=paper-faithful-with-proxy

## Extended Findings

- No extended rows in this campaign.

## Interaction Effects and Deltas vs Paper Fidelity

- No delta rows (paper_fidelity anchor missing or no comparator variants).

## Key Negative Results and Caveats

- Low-F1 case `cpu_hog_like` / `paper_fidelity_smoke`: F1=0.000, precision=0.000, recall=0.000, TPR=0.000, FPR=1.000
- Low-F1 case `net_hog_like_latency` / `paper_fidelity_smoke`: F1=0.000, precision=0.000, recall=0.000, TPR=0.000, FPR=0.000
- Low-F1 case `mem_leak` / `paper_fidelity_smoke`: F1=0.286, precision=0.167, recall=1.000, TPR=1.000, FPR=0.833

## Stratified Rollups

| Group Type | Group Name | n | Mean F1 | Mean Precision | Mean Recall | Mean TPR | Mean FPR |
|---|---|---:|---:|---:|---:|---:|---:|
| ablation_block | decision | 3 | 0.095 | 0.056 | 0.333 | 0.333 | 0.611 |
| fault_family | paper_aligned | 3 | 0.095 | 0.056 | 0.333 | 0.333 | 0.611 |
| study_scope | paper_faithful | 3 | 0.095 | 0.056 | 0.333 | 0.333 | 0.611 |
| variant_fault_family | paper_fidelity_smoke|paper_aligned | 3 | 0.095 | 0.056 | 0.333 | 0.333 | 0.611 |

## SOM checkpoint summary

Per-run SOM fields are merged into `run_metrics.csv` (prefix `som_`). Topology uses mean L2 distance between adjacent map units (U-matrix proxy); quantization proxy is mean BMU distance on feature vectors sampled from `anomaly_events.jsonl` when available.

| Variant | Fault | n (SOM) | mean val acc | mean U-matrix | mean QE proxy |
|---|---|---:|---:|---:|---:|
| paper_fidelity_smoke | cpu_hog_like | 1 | 0.9000 | 0.6240 | 73.6606 |
| paper_fidelity_smoke | mem_leak | 1 | 0.9000 | 2.1662 | 55432.8245 |
| paper_fidelity_smoke | net_hog_like_latency | 1 | 0.9333 | 3.9775 | — |

## Reproducibility Artifacts

- Source metrics: `run_metrics.csv`, `rollup_metrics.csv`, `stratified_rollup_metrics.csv`, `delta_vs_paper_fidelity.csv`, `som_rollup_metrics.csv` (SOM lattice / checkpoint aggregates).
- ROC-style threshold points: `roc_points.csv`.
- Matching mode: `many_to_many`.
- Validity ledger: `validity_ledger.json`.
- Campaign metadata: captured in `summary.json` under `campaign_meta`.
- UBL fidelity checks captured in `fidelity_checks.json`.

## UBL Fidelity Checks

- Sampling interval includes 1s: `True`.
- Percentile threshold sweep present: `False`.
- Pending-window sweep present: `False`.
- PCA/kNN comparator present: `False`.

## Failure Accounting

- No failed runs recorded.

## Paired Significance

- No paired significance rows generated.

## Validity Notes

- Pending-window scoring (`W`) approximates prediction quality and should be stress-tested per workload.
- `TN` and `FPR` rely on evaluator approximation of negative opportunities; interpret absolute FPR as proxy-level, not a canonical binary denominator.
- Toxiproxy-based `net_hog_like` is a proxy for paper NetHog, not a byte-for-byte replica.
- If the learner runs in `bmu` mode, results are baseline comparisons and not strict UBL replication.
