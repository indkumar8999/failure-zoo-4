# UBL Fault Injection Report

## Mean Metrics by Variant and Fault

| Fault | Variant | n | TPR | FPR | Precision | Recall | F1 | Lead Time (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| cpu_hog_like | paper_fidelity | 2 | 0.500 | 0.484 | 0.016 | 0.500 | 0.031 | 17.52 |
| mem_leak | paper_fidelity | 2 | 1.000 | 0.961 | 0.039 | 1.000 | 0.076 | 37.05 |

## Validity Notes

- Pending-window scoring (`W`) approximates prediction quality and should be stress-tested per workload.
- Toxiproxy-based `net_hog_like` is a proxy for paper NetHog, not a byte-for-byte replica.
- If the learner runs in `bmu` mode, results are baseline comparisons and not strict UBL replication.
