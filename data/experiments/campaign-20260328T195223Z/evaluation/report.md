# UBL Fault Injection Report

## Mean Metrics by Variant and Fault

| Fault | Variant | n | TPR | FPR | Precision | Recall | F1 | Lead Time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| cpu_hog_like | paper_fidelity | 2 | 1.000 | 0.965 | 0.035 | 1.000 | 0.067 | 30.73 |
| lock_convoy | paper_fidelity | 1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.00 |
| mem_leak | paper_fidelity | 2 | 1.000 | 0.967 | 0.033 | 1.000 | 0.064 | 32.25 |
| net_hog_like_latency | paper_fidelity | 2 | 1.000 | 0.962 | 0.038 | 1.000 | 0.072 | 26.72 |

## Validity Notes

- Pending-window scoring (`W`) approximates prediction quality and should be stress-tested per workload.
- Toxiproxy-based `net_hog_like` is a proxy for paper NetHog, not a byte-for-byte replica.
- If the learner runs in `bmu` mode, results are baseline comparisons and not strict UBL replication.
