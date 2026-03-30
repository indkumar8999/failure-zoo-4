# UBL Fault Injection Report

## Mean Metrics by Variant and Fault

| Fault | Variant | n | paper_AT | paper_AF | TPR | FPR (alarm stream) | Alarm FP frac | Precision | Recall | F1 (95% CI) | Lead Time (s, 95% CI) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cpu_hog_like | paper_fidelity_research_anchor | 6 | 0.667 | 0.167 | 0.667 | 0.139 | 0.139 | 0.528 | 0.667 | 0.548 [0.142, 0.953] | 2.57 [0.61, 4.53] |
| disk_fill | paper_fidelity_research_anchor | 2 | 1.000 | 0.000 | 1.000 | 0.000 | 0.000 | 1.000 | 1.000 | 1.000 [1.000, 1.000] | 4.86 [4.39, 5.32] |
| lock_convoy | paper_fidelity_research_anchor | 5 | 1.000 | 0.000 | 1.000 | 0.000 | 0.000 | 1.000 | 1.000 | 1.000 [1.000, 1.000] | 3.99 [2.58, 5.40] |
| mem_leak | paper_fidelity_research_anchor | 6 | 0.931 | 0.002 | 0.931 | 0.028 | 0.028 | 0.972 | 0.931 | 0.948 [0.884, 1.013] | 4.52 [4.15, 4.89] |
| net_hog_like_latency | paper_fidelity_research_anchor | 6 | 0.333 | 0.000 | 0.333 | 0.000 | 0.000 | 0.333 | 0.333 | 0.333 [-0.080, 0.747] | 0.78 [-0.26, 1.83] |

## Paper-Faithful Findings

- `disk_fill` / `paper_fidelity_research_anchor`: F1=1.000, precision=1.000, recall=1.000, paper_AT=1.000, paper_AF=0.000, FPR_alarm=0.000, faithfulness=paper-faithful-with-proxy
- `lock_convoy` / `paper_fidelity_research_anchor`: F1=1.000, precision=1.000, recall=1.000, paper_AT=1.000, paper_AF=0.000, FPR_alarm=0.000, faithfulness=paper-faithful-with-proxy
- `mem_leak` / `paper_fidelity_research_anchor`: F1=0.948, precision=0.972, recall=0.931, paper_AT=0.931, paper_AF=0.002, FPR_alarm=0.028, faithfulness=paper-faithful-with-proxy
- `cpu_hog_like` / `paper_fidelity_research_anchor`: F1=0.548, precision=0.528, recall=0.667, paper_AT=0.667, paper_AF=0.167, FPR_alarm=0.139, faithfulness=paper-faithful-with-proxy
- `net_hog_like_latency` / `paper_fidelity_research_anchor`: F1=0.333, precision=0.333, recall=0.333, paper_AT=0.333, paper_AF=0.000, FPR_alarm=0.000, faithfulness=paper-faithful-with-proxy

## Extended Findings

- No extended rows in this campaign.

## Interaction Effects and Deltas vs Paper Fidelity

- No delta rows (paper_fidelity anchor missing or no comparator variants).

## Key Negative Results and Caveats

- Low-F1 case `net_hog_like_latency` / `paper_fidelity_research_anchor`: F1=0.333, precision=0.333, recall=0.333, paper_AF=0.000, FPR_alarm=0.000

## Stratified Rollups

| Group Type | Group Name | n | Mean F1 | Mean Precision | Mean Recall | Mean TPR | Mean paper_AF | Mean FPR (alarm) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| ablation_block | decision | 25 | 0.719 | 0.720 | 0.743 | 0.743 | 0.040 | 0.040 |
| fault_family | extended | 7 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 |
| fault_family | paper_aligned | 18 | 0.610 | 0.611 | 0.644 | 0.644 | 0.056 | 0.056 |
| study_scope | paper_faithful | 25 | 0.719 | 0.720 | 0.743 | 0.743 | 0.040 | 0.040 |
| variant_fault_family | paper_fidelity_research_anchor|extended | 7 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 |
| variant_fault_family | paper_fidelity_research_anchor|paper_aligned | 18 | 0.610 | 0.611 | 0.644 | 0.644 | 0.056 | 0.056 |

## SOM checkpoint summary

Per-run SOM fields are merged into `run_metrics.csv` (prefix `som_`). Topology uses mean L2 distance between adjacent map units (U-matrix proxy); quantization proxy is mean BMU distance on feature vectors sampled from `anomaly_events.jsonl` when available.

| Variant | Fault | n (SOM) | mean val acc | mean U-matrix | mean QE proxy |
|---|---|---:|---:|---:|---:|
| paper_fidelity_research_anchor | cpu_hog_like | 6 | 0.9222 | 4.7396 | 13.2144 |
| paper_fidelity_research_anchor | disk_fill | 2 | 0.9417 | 245.2544 | 33850.7483 |
| paper_fidelity_research_anchor | lock_convoy | 5 | 0.9333 | 4.0284 | 3.3560 |
| paper_fidelity_research_anchor | mem_leak | 6 | 0.9278 | 218.7042 | 30139.3128 |
| paper_fidelity_research_anchor | net_hog_like_latency | 6 | 0.9278 | 2.2088 | 0.6441 |

## Reproducibility Artifacts

- Source metrics: `run_metrics.csv`, `rollup_metrics.csv`, `stratified_rollup_metrics.csv`, `delta_vs_paper_fidelity.csv`, `som_rollup_metrics.csv` (SOM lattice / checkpoint aggregates).
- ROC-style threshold points: `roc_points.csv`.
- Matching mode: `many_to_many`.
- Validity ledger: `validity_ledger.json`.
- Campaign metadata: captured in `summary.json` under `campaign_meta`.
- Failed runs captured in `failed_runs.csv` (included in `summary.json`).
- UBL fidelity checks captured in `fidelity_checks.json`.

## UBL Fidelity Checks

- Sampling interval includes 1s: `True`.
- Percentile threshold sweep present: `False`.
- Paper-style offline threshold replay ran: `False`.
- Pending-window sweep present: `False`.
- PCA/kNN comparator present: `False`.

## Failure Accounting

| Run ID | Fault | Variant | Failed Phase | Reason |
|---|---|---|---|---|
| 20260330T101857Z-paper_fidelity_research_anchor-lock_convoy-ihigh-dlong-wbase-s01-r01 | lock_convoy | paper_fidelity_research_anchor | execution | Command '['docker', 'compose', '--profile', 'tools', 'run', '--rm', 'chaos', 'lock', 'off']' returned non-zero exit status 1. |

## Paired Significance

- No paired significance rows generated.

## Validity Notes

- Pending-window scoring (`W`) approximates prediction quality and should be stress-tested per workload.
- **paper_AT** / **paper_AF** follow UBL Eq. 5 style on this lab’s labels; **FPR (alarm stream)** is `fp/(fp+tp)` (same as alarm FP fraction), not paper AF. See `validity_ledger.json` and `run_metrics.csv`.
- Toxiproxy-based `net_hog_like` is a proxy for paper NetHog, not a byte-for-byte replica.
- If the learner runs in `bmu` mode, results are baseline comparisons and not strict UBL replication.
- **`bootstrap_vectors_ok`** matches **`schedule_bootstrap_polls_ok`**: matrix poll budget during the bootstrap phase, not learner-collected sample counts. Use **`manifest_bootstrap_samples`** / **`learner_bootstrap_collected_ok`** (from run `manifest.json` → `learner_status_post_bootstrap`) when auditing training readiness.
