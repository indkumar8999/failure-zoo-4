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

## Validity Notes

- Pending-window scoring (`W`) approximates prediction quality and should be stress-tested per workload.
- Toxiproxy-based `net_hog_like` is a proxy for paper NetHog, not a byte-for-byte replica.
- If the learner runs in `bmu` mode, results are baseline comparisons and not strict UBL replication.
