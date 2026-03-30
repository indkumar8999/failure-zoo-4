# UBL Fault Injection Report

## Mean Metrics by Variant and Fault

| Fault | Variant | n | TPR | FPR | Precision | Recall | F1 (95% CI) | Lead Time (s, 95% CI) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| mem_leak | minimal_ubl | 1 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |

## Paper-Faithful Findings

- No rows tagged as paper-faithful scope in this campaign.

## Extended Findings

- `mem_leak` / `minimal_ubl`: F1=0.000, lead=0.00s, ablation_block=decision

## Interaction Effects and Deltas vs Paper Fidelity

- No delta rows (paper_fidelity anchor missing or no comparator variants).

## Key Negative Results and Caveats

- Low-F1 case `mem_leak` / `minimal_ubl`: F1=0.000, TPR=0.000, FPR=1.000

## Stratified Rollups

| Group Type | Group Name | n | Mean F1 | Mean TPR | Mean FPR |
|---|---|---:|---:|---:|---:|
| ablation_block | decision | 1 | 0.000 | 0.000 | 1.000 |
| fault_family | paper_aligned | 1 | 0.000 | 0.000 | 1.000 |
| study_scope | extended | 1 | 0.000 | 0.000 | 1.000 |
| variant_fault_family | minimal_ubl|paper_aligned | 1 | 0.000 | 0.000 | 1.000 |

## Reproducibility Artifacts

- Source metrics: `run_metrics.csv`, `rollup_metrics.csv`, `stratified_rollup_metrics.csv`, `delta_vs_paper_fidelity.csv`.
- ROC-style threshold points: `roc_points.csv`.
- Matching mode: `many_to_many`.
- Validity ledger: `validity_ledger.json`.
- Campaign metadata: captured in `summary.json` under `campaign_meta`.
- UBL fidelity checks captured in `fidelity_checks.json`.

## UBL Fidelity Checks

- Sampling interval includes 1s: `False`.
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
