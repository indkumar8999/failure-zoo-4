# UBL Fault Injection Report

## Mean Metrics by Variant and Fault

| Fault | Variant | n | paper_AT | paper_AF | TPR | FPR (alarm stream) | Alarm FP frac | Precision | Recall | F1 (95% CI) | Lead Time (s, 95% CI) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| disk_fill | paper_fidelity_research_anchor | 2 | 1.000 | 0.000 | 1.000 | 0.000 | 0.000 | 1.000 | 1.000 | 1.000 [1.000, 1.000] | 4.13 [1.93, 6.34] |
| lock_convoy | paper_fidelity_research_anchor | 4 | 1.000 | 0.000 | 1.000 | 0.000 | 0.000 | 1.000 | 1.000 | 1.000 [1.000, 1.000] | 4.10 [3.06, 5.14] |

## Paper-Faithful Findings

- `disk_fill` / `paper_fidelity_research_anchor`: F1=1.000, precision=1.000, recall=1.000, paper_AT=1.000, paper_AF=0.000, FPR_alarm=0.000, faithfulness=paper-faithful-with-proxy
- `lock_convoy` / `paper_fidelity_research_anchor`: F1=1.000, precision=1.000, recall=1.000, paper_AT=1.000, paper_AF=0.000, FPR_alarm=0.000, faithfulness=paper-faithful-with-proxy

## Extended Findings

- No extended rows in this campaign.

## Interaction Effects and Deltas vs Paper Fidelity

- No delta rows (paper_fidelity anchor missing or no comparator variants).

## Key Negative Results and Caveats

- No variant/fault pairs with mean F1 below 0.5 in this campaign (single-run or high-F1 matrices may only appear in the rollup table above).

## Stratified Rollups

| Group Type | Group Name | n | Mean F1 | Mean Precision | Mean Recall | Mean TPR | Mean paper_AF | Mean FPR (alarm) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| ablation_block | decision | 6 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 |
| fault_family | extended | 6 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 |
| study_scope | paper_faithful | 6 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 |
| variant_fault_family | paper_fidelity_research_anchor|extended | 6 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 |

## SOM checkpoint summary

Per-run SOM fields are merged into `run_metrics.csv` (prefix `som_`). Topology uses mean L2 distance between adjacent map units (U-matrix proxy); quantization proxy is mean BMU distance on feature vectors sampled from `anomaly_events.jsonl` when available.

| Variant | Fault | n (SOM) | mean val acc | mean U-matrix | mean QE proxy |
|---|---|---:|---:|---:|---:|
| paper_fidelity_research_anchor | disk_fill | 2 | 0.9417 | 140.5599 | 25253.1185 |
| paper_fidelity_research_anchor | lock_convoy | 4 | 0.9250 | 9.0574 | 12.9587 |

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
- Paper-style offline threshold replay ran: `False`.
- Pending-window sweep present: `False`.
- PCA/kNN comparator present: `False`.

## Failure Accounting

- No failed runs recorded.

## Paired Significance

- No paired significance rows generated.

## Validity Notes

- Pending-window scoring (`W`) approximates prediction quality and should be stress-tested per workload.
- **paper_AT** / **paper_AF** follow UBL Eq. 5 style on this lab’s labels; **FPR (alarm stream)** is `fp/(fp+tp)` (same as alarm FP fraction), not paper AF. See `validity_ledger.json` and `run_metrics.csv`.
- Toxiproxy-based `net_hog_like` is a proxy for paper NetHog, not a byte-for-byte replica.
- If the learner runs in `bmu` mode, results are baseline comparisons and not strict UBL replication.
- **`bootstrap_vectors_ok`** matches **`schedule_bootstrap_polls_ok`**: matrix poll budget during the bootstrap phase, not learner-collected sample counts. Use **`manifest_bootstrap_samples`** / **`learner_bootstrap_collected_ok`** (from run `manifest.json` → `learner_status_post_bootstrap`) when auditing training readiness.
