# UBL Fault Injection Report

## Mean Metrics by Variant and Fault

| Fault | Variant | n | TPR | FPR | Precision | Recall | F1 | Lead Time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| cpu_hog_like | current_default | 1 | 1.000 | 0.996 | 0.004 | 1.000 | 0.007 | 52.63 |
| cpu_hog_like | paper_fidelity | 1 | 1.000 | 0.976 | 0.024 | 1.000 | 0.047 | 44.18 |
| mem_leak | current_default | 1 | 1.000 | 0.998 | 0.002 | 1.000 | 0.004 | 59.26 |
| mem_leak | paper_fidelity | 1 | 1.000 | 0.951 | 0.049 | 1.000 | 0.094 | 31.66 |
| net_hog_like_latency | current_default | 1 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 | 0.00 |
| net_hog_like_latency | paper_fidelity | 1 | 1.000 | 0.956 | 0.044 | 1.000 | 0.084 | 32.32 |

## Paper-Faithful Findings

- No rows tagged as paper-faithful scope in this campaign.

## Extended Findings

- `mem_leak` / `paper_fidelity`: F1=0.094, lead=31.66s, ablation_block=fault
- `net_hog_like_latency` / `paper_fidelity`: F1=0.084, lead=32.32s, ablation_block=fault
- `cpu_hog_like` / `paper_fidelity`: F1=0.047, lead=44.18s, ablation_block=fault
- `cpu_hog_like` / `current_default`: F1=0.007, lead=52.63s, ablation_block=fault
- `mem_leak` / `current_default`: F1=0.004, lead=59.26s, ablation_block=fault
- `net_hog_like_latency` / `current_default`: F1=0.000, lead=0.00s, ablation_block=fault

## Interaction Effects and Deltas vs Paper Fidelity

- `cpu_hog_like` / `current_default` vs `paper_fidelity`: ΔF1=-0.040, ΔTPR=+0.000, ΔFPR=+0.020, ΔLead=+8.45s
- `net_hog_like_latency` / `current_default` vs `paper_fidelity`: ΔF1=-0.084, ΔTPR=-1.000, ΔFPR=+0.044, ΔLead=-32.32s
- `mem_leak` / `current_default` vs `paper_fidelity`: ΔF1=-0.090, ΔTPR=+0.000, ΔFPR=+0.047, ΔLead=+27.60s

## Key Negative Results and Caveats

- Low-F1 case `net_hog_like_latency` / `current_default`: F1=0.000, TPR=0.000, FPR=1.000
- Low-F1 case `mem_leak` / `current_default`: F1=0.004, TPR=1.000, FPR=0.998
- Low-F1 case `cpu_hog_like` / `current_default`: F1=0.007, TPR=1.000, FPR=0.996
- Low-F1 case `cpu_hog_like` / `paper_fidelity`: F1=0.047, TPR=1.000, FPR=0.976
- Low-F1 case `net_hog_like_latency` / `paper_fidelity`: F1=0.084, TPR=1.000, FPR=0.956

## Stratified Rollups

| Group Type | Group Name | n | Mean F1 | Mean TPR | Mean FPR |
|---|---|---:|---:|---:|---:|
| ablation_block | fault | 6 | 0.039 | 0.833 | 0.980 |
| fault_family | paper_aligned | 6 | 0.039 | 0.833 | 0.980 |
| study_scope | extended | 6 | 0.039 | 0.833 | 0.980 |
| variant_fault_family | current_default|paper_aligned | 3 | 0.004 | 0.667 | 0.998 |
| variant_fault_family | paper_fidelity|paper_aligned | 3 | 0.075 | 1.000 | 0.961 |

## Reproducibility Artifacts

- Source metrics: `run_metrics.csv`, `rollup_metrics.csv`, `stratified_rollup_metrics.csv`, `delta_vs_paper_fidelity.csv`.
- Validity ledger: `validity_ledger.json`.

## Validity Notes

- Pending-window scoring (`W`) approximates prediction quality and should be stress-tested per workload.
- Toxiproxy-based `net_hog_like` is a proxy for paper NetHog, not a byte-for-byte replica.
- If the learner runs in `bmu` mode, results are baseline comparisons and not strict UBL replication.
