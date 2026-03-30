# UBL Paper-to-Code Fidelity Checklist

This checklist records which parts of the current implementation are paper-faithful, partially faithful, or extended/diverged in this repository context.

## Fidelity Mapping

| UBL requirement | Code/config location | Status | Notes |
|---|---|---|---|
| SOM neighborhood-area scoring at BMU | `learner/main.py` (`_compute_area_map`, `_score_with_mode`, `SOM_SCORING_MODE=ubl_area`) | faithful | Implements Manhattan/L1 neighborhood area over 4-neighbors and thresholds BMU area. |
| Percentile-based anomaly threshold | `learner/main.py` (`THRESHOLD_Q`, `_threshold_for_model`) | faithful | Uses quantile on training scores; paper-style 0.85 available in matrix. |
| 3-consecutive anomalous samples before alarm | `learner/main.py` (`ANOMALY_STREAK`, `anomaly_streak_count`) | partial | Consecutive sample rule is implemented, but effective real-time duration depends on `POLL_SEC`. |
| K-point moving average smoothing | `learner/main.py` (`SOM_SMOOTH_K`, `smooth_window`) | faithful | Sliding mean smoothing over online samples. |
| SOM geometry 32x32 for paper mode | `experiments/fault_matrix.yaml` (`paper_fidelity` variant), `learner/main.py` (`SOM_ROWS`, `SOM_COLS`) | faithful | Configurable; paper_fidelity variant pins 32x32. |
| K-fold map selection with multi-init | `learner/main.py` (`SOM_KFOLD`, `SOM_INIT_TRIALS`, `_train_bootstrap`) | faithful | Variant supports K-fold and init trials; default mode may use K=1 for baseline. |
| Train-max normalization to [0,100] | `learner/main.py` (`SOM_NORMALIZATION_MODE=train_max_100`) | faithful | Mirrors train-max scaling behavior. |
| Fault families used for paper comparison | `experiments/fault_matrix.yaml` (`faults[].family=paper_aligned`) | partial | Paper-aligned in intent, but injected via practical proxies. |
| NetHog-like network fault | `README.md`, `experiments/fault_matrix.yaml` (`net_hog_like_latency`) | paper-faithful-with-proxy | Uses Toxiproxy toxics, not the original Xen/VCL stack. |
| Decentralized Xen learning VM migration | `README.md` (validity notes) | diverged (out of scope) | Not implemented in this Docker lab by design. |
| Online incremental model updates | `learner/main.py` (`state.model.train_step(x)`) | extended | Continuous adaptation beyond strict static-bootstrap replication. |

## Interpretation Rules

- `paper-faithful`: direct algorithmic and environment-level replication.
- `paper-faithful-with-proxy`: paper-aligned algorithm with practical proxy mappings for infrastructure/fault injection.
- `extended-beyond-paper`: new baseline modes, added fault classes, or architecture beyond paper scope.

## Usage in Campaigns

- Campaign runner writes per-run `faithfulness_label`, `study_scope`, and `ablation_block` into `manifest.json`.
- Evaluator propagates these tags into `run_metrics.csv`, `rollup_metrics.csv`, and `summary.json`.
- Reporting and plotting split all key results by faithfulness label to separate replication claims from extensions.
