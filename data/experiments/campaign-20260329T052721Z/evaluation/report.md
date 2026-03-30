# UBL Fault Injection Report

## Mean Metrics by Variant and Fault

| Fault | Variant | n | paper_AT | paper_AF | TPR | FPR (alarm stream) | Alarm FP frac | Precision | Recall | F1 (95% CI) | Lead Time (s, 95% CI) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cpu_hog_like | paper_fidelity_anchor | 10 | 0.000 | 0.005 | 0.000 | 0.100 | 0.100 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |
| cpu_hog_like | screen_smooth_streak | 10 | 0.600 | 1.000 | 0.600 | 0.995 | 0.995 | 0.005 | 0.600 | 0.011 [0.005, 0.017] | 33.92 [10.79, 57.04] |
| cpu_hog_like | screen_threshold | 10 | 0.600 | 1.000 | 0.600 | 0.996 | 0.996 | 0.004 | 0.600 | 0.009 [0.003, 0.015] | 33.36 [11.84, 54.87] |
| cpu_hog_like | screen_training_topology | 10 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |
| mem_leak | paper_fidelity_anchor | 10 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |
| mem_leak | screen_smooth_streak | 10 | 0.400 | 1.000 | 0.400 | 0.991 | 0.991 | 0.009 | 0.400 | 0.018 [-0.001, 0.036] | 30.15 [5.04, 55.25] |
| mem_leak | screen_threshold | 10 | 0.600 | 1.000 | 0.600 | 0.996 | 0.996 | 0.004 | 0.600 | 0.007 [0.002, 0.013] | 33.08 [8.94, 57.22] |
| mem_leak | screen_training_topology | 10 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 [0.000, 0.000] | 0.00 [0.00, 0.00] |

## Paper-Faithful Findings

- `cpu_hog_like` / `paper_fidelity_anchor`: F1=0.000, precision=0.000, recall=0.000, paper_AT=0.000, paper_AF=0.005, FPR_alarm=0.100, faithfulness=paper-faithful-with-proxy
- `mem_leak` / `paper_fidelity_anchor`: F1=0.000, precision=0.000, recall=0.000, paper_AT=0.000, paper_AF=0.000, FPR_alarm=0.000, faithfulness=paper-faithful-with-proxy

## Extended Findings

- `mem_leak` / `screen_smooth_streak`: F1=0.018, precision=0.009, recall=0.400, lead=30.15s, ablation_block=decision
- `cpu_hog_like` / `screen_smooth_streak`: F1=0.011, precision=0.005, recall=0.600, lead=33.92s, ablation_block=decision
- `cpu_hog_like` / `screen_threshold`: F1=0.009, precision=0.004, recall=0.600, lead=33.36s, ablation_block=decision
- `mem_leak` / `screen_threshold`: F1=0.007, precision=0.004, recall=0.600, lead=33.08s, ablation_block=decision
- `cpu_hog_like` / `screen_training_topology`: F1=0.000, precision=0.000, recall=0.000, lead=0.00s, ablation_block=training
- `mem_leak` / `screen_training_topology`: F1=0.000, precision=0.000, recall=0.000, lead=0.00s, ablation_block=training

## Interaction Effects and Deltas vs Paper Fidelity

- `mem_leak` / `screen_smooth_streak` vs `paper_fidelity`: ΔF1=+0.018, ΔTPR=+0.400, ΔFPR=+0.991, ΔLead=+30.15s
- `cpu_hog_like` / `screen_smooth_streak` vs `paper_fidelity`: ΔF1=+0.011, ΔTPR=+0.600, ΔFPR=+0.895, ΔLead=+33.92s
- `cpu_hog_like` / `screen_threshold` vs `paper_fidelity`: ΔF1=+0.009, ΔTPR=+0.600, ΔFPR=+0.896, ΔLead=+33.36s
- `mem_leak` / `screen_threshold` vs `paper_fidelity`: ΔF1=+0.007, ΔTPR=+0.600, ΔFPR=+0.996, ΔLead=+33.08s
- `cpu_hog_like` / `screen_training_topology` vs `paper_fidelity`: ΔF1=+0.000, ΔTPR=+0.000, ΔFPR=-0.100, ΔLead=+0.00s
- `mem_leak` / `screen_training_topology` vs `paper_fidelity`: ΔF1=+0.000, ΔTPR=+0.000, ΔFPR=+0.000, ΔLead=+0.00s

## Key Negative Results and Caveats

- Low-F1 case `cpu_hog_like` / `paper_fidelity_anchor`: F1=0.000, precision=0.000, recall=0.000, paper_AF=0.005, FPR_alarm=0.100
- Low-F1 case `cpu_hog_like` / `screen_training_topology`: F1=0.000, precision=0.000, recall=0.000, paper_AF=0.000, FPR_alarm=0.000
- Low-F1 case `mem_leak` / `paper_fidelity_anchor`: F1=0.000, precision=0.000, recall=0.000, paper_AF=0.000, FPR_alarm=0.000
- Low-F1 case `mem_leak` / `screen_training_topology`: F1=0.000, precision=0.000, recall=0.000, paper_AF=0.000, FPR_alarm=0.000
- Low-F1 case `mem_leak` / `screen_threshold`: F1=0.007, precision=0.004, recall=0.600, paper_AF=1.000, FPR_alarm=0.996

## Stratified Rollups

| Group Type | Group Name | n | Mean F1 | Mean Precision | Mean Recall | Mean TPR | Mean paper_AF | Mean FPR (alarm) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| ablation_block | decision | 60 | 0.007 | 0.004 | 0.367 | 0.367 | 0.667 | 0.680 |
| ablation_block | training | 20 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| fault_family | paper_aligned | 80 | 0.006 | 0.003 | 0.275 | 0.275 | 0.501 | 0.510 |
| study_scope | extended | 60 | 0.007 | 0.004 | 0.367 | 0.367 | 0.667 | 0.663 |
| study_scope | paper_faithful | 20 | 0.000 | 0.000 | 0.000 | 0.000 | 0.002 | 0.050 |
| variant_fault_family | paper_fidelity_anchor|paper_aligned | 20 | 0.000 | 0.000 | 0.000 | 0.000 | 0.002 | 0.050 |
| variant_fault_family | screen_smooth_streak|paper_aligned | 20 | 0.014 | 0.007 | 0.500 | 0.500 | 1.000 | 0.993 |
| variant_fault_family | screen_threshold|paper_aligned | 20 | 0.008 | 0.004 | 0.600 | 0.600 | 1.000 | 0.996 |
| variant_fault_family | screen_training_topology|paper_aligned | 20 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

## SOM checkpoint summary

Per-run SOM fields are merged into `run_metrics.csv` (prefix `som_`). Topology uses mean L2 distance between adjacent map units (U-matrix proxy); quantization proxy is mean BMU distance on feature vectors sampled from `anomaly_events.jsonl` when available.

| Variant | Fault | n (SOM) | mean val acc | mean U-matrix | mean QE proxy |
|---|---|---:|---:|---:|---:|
| paper_fidelity_anchor | cpu_hog_like | 10 | 0.8682 | 15.3536 | 17.7303 |
| screen_smooth_streak | cpu_hog_like | 10 | 0.8846 | 4.5866 | 16452.7107 |
| screen_threshold | cpu_hog_like | 10 | 0.8846 | 220.4302 | 15015.0214 |
| screen_training_topology | cpu_hog_like | 10 | 0.7975 | 7.7935 | 10.3570 |
| paper_fidelity_anchor | mem_leak | 10 | 0.8756 | 350.3058 | 28546.4725 |
| screen_smooth_streak | mem_leak | 10 | 0.8846 | 6.7527 | 15994.4782 |
| screen_threshold | mem_leak | 10 | 0.8846 | 230.9252 | 18659.8016 |
| screen_training_topology | mem_leak | 10 | 0.8000 | 12.4794 | 10.1952 |

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
| cpu_hog_like | screen_smooth_streak | 10 | +0.011 | 0.7539 | 0.7539 | +0.600 | +0.895 | +33.92 |
| cpu_hog_like | screen_threshold | 10 | +0.009 | 0.7539 | 0.7539 | +0.600 | +0.896 | +33.36 |
| cpu_hog_like | screen_training_topology | 10 | +0.000 | 0.0020 | 0.0059 | +0.000 | -0.100 | +0.00 |
| mem_leak | screen_smooth_streak | 10 | +0.018 | 0.7539 | 0.7539 | +0.400 | +0.991 | +30.15 |
| mem_leak | screen_threshold | 10 | +0.007 | 0.7539 | 0.7539 | +0.600 | +0.996 | +33.08 |
| mem_leak | screen_training_topology | 10 | +0.000 | 0.0020 | 0.0059 | +0.000 | +0.000 | +0.00 |

## Validity Notes

- Pending-window scoring (`W`) approximates prediction quality and should be stress-tested per workload.
- **paper_AT** / **paper_AF** follow UBL Eq. 5 style on this lab’s labels; **FPR (alarm stream)** is `fp/(fp+tp)` (same as alarm FP fraction), not paper AF. See `validity_ledger.json` and `run_metrics.csv`.
- Toxiproxy-based `net_hog_like` is a proxy for paper NetHog, not a byte-for-byte replica.
- If the learner runs in `bmu` mode, results are baseline comparisons and not strict UBL replication.
