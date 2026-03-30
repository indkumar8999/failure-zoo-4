# UBL Fault Injection Report

## Mean Metrics by Variant and Fault

| Fault | Variant | n | TPR | FPR | Precision | Recall | F1 | Lead Time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| cpu_hog_like | current_default | 1 | 1.000 | 0.979 | 0.021 | 1.000 | 0.041 | 51.99 |
| cpu_hog_like | paper_fidelity | 1 | 1.000 | 0.962 | 0.038 | 1.000 | 0.073 | 44.28 |
| mem_leak | current_default | 1 | 1.000 | 0.979 | 0.021 | 1.000 | 0.042 | 54.32 |
| mem_leak | paper_fidelity | 1 | 1.000 | 0.961 | 0.039 | 1.000 | 0.076 | 47.14 |
| net_hog_like_latency | current_default | 1 | 1.000 | 0.992 | 0.008 | 1.000 | 0.016 | 54.23 |
| net_hog_like_latency | paper_fidelity | 1 | 1.000 | 0.977 | 0.023 | 1.000 | 0.045 | 46.74 |

## Validity Notes

- Pending-window scoring (`W`) approximates prediction quality and should be stress-tested per workload.
- Toxiproxy-based `net_hog_like` is a proxy for paper NetHog, not a byte-for-byte replica.
- If the learner runs in `bmu` mode, results are baseline comparisons and not strict UBL replication.
