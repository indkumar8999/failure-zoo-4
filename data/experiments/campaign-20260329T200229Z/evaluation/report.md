# UBL Fault Injection Report

## Mean Metrics by Variant and Fault

| Fault | Variant | n | paper_AT | paper_AF | TPR | FPR (alarm stream) | Alarm FP frac | Precision | Recall | F1 (95% CI) | Lead Time (s, 95% CI) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| mem_leak | minimal_ubl | 1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |

## Paper-Faithful Findings

- No rows tagged as paper-faithful scope in this campaign.

## Extended Findings

- `mem_leak` / `minimal_ubl`: F1=0.000, precision=0.000, recall=0.000, lead=0.00s, ablation_block=decision

## Interaction Effects and Deltas vs Paper Fidelity

- No delta rows (paper_fidelity anchor missing or no comparator variants).

## Key Negative Results and Caveats

- Low-F1 case `mem_leak` / `minimal_ubl`: F1=0.000, precision=0.000, recall=0.000, paper_AF=0.000, FPR_alarm=0.000

## Stratified Rollups

| Group Type | Group Name | n | Mean F1 | Mean Precision | Mean Recall | Mean TPR | Mean paper_AF | Mean FPR (alarm) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| ablation_block | decision | 1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| fault_family | paper_aligned | 1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| study_scope | extended | 1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| variant_fault_family | minimal_ubl|paper_aligned | 1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

## SOM checkpoint summary

Per-run SOM fields are merged into `run_metrics.csv` (prefix `som_`). Topology uses mean L2 distance between adjacent map units (U-matrix proxy); quantization proxy is mean BMU distance on feature vectors sampled from `anomaly_events.jsonl` when available.

- No SOM rollup rows (no `som_model.npz` snapshots in completed runs, or re-run `evaluate.py` to refresh).

## Reproducibility Artifacts

- Source metrics: `run_metrics.csv`, `rollup_metrics.csv`, `stratified_rollup_metrics.csv`, `delta_vs_paper_fidelity.csv`, `som_rollup_metrics.csv` (SOM lattice / checkpoint aggregates).
- ROC-style threshold points: `roc_points.csv`.
- Matching mode: `many_to_many`.
- Validity ledger: `validity_ledger.json`.
- Campaign metadata: captured in `summary.json` under `campaign_meta`.
- UBL fidelity checks captured in `fidelity_checks.json`.

## UBL Fidelity Checks

- Sampling interval includes 1s: `False`.
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
