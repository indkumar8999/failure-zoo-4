"""
Summarize persisted SOM checkpoints (`som_model.npz`) for campaign evaluation.

Topology metrics use only the weight lattice (U-matrix–style neighbor distances).
Optional mean BMU distance (quantization-error proxy) uses feature vectors from
`anomaly_events.jsonl` when available, with the same scale/normalization as the learner.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np


def _apply_online_clip(x: np.ndarray, mode: str) -> np.ndarray:
    y = np.maximum(x, 0.0)
    m = (mode or "none").strip().lower()
    if m == "none":
        return y
    if m == "clip_200":
        return np.clip(y, 0.0, 200.0)
    if m == "clip_300":
        return np.clip(y, 0.0, 300.0)
    return y


def _normalize_with_scale(samples: np.ndarray, scale: np.ndarray, normalization_mode: str) -> np.ndarray:
    _ = normalization_mode  # reserved; learner uses train_max_100 path
    return (samples / scale) * 100.0


def _neighbor_distances(weights: np.ndarray) -> tuple[float, float, float]:
    """Mean L2 edge distances: horizontal, vertical, combined (U-matrix proxy)."""
    r, c, _d = weights.shape
    if r < 1 or c < 1:
        return 0.0, 0.0, 0.0
    h_list: List[float] = []
    v_list: List[float] = []
    for i in range(r):
        for j in range(c - 1):
            h_list.append(float(np.linalg.norm(weights[i, j] - weights[i, j + 1])))
    for i in range(r - 1):
        for j in range(c):
            v_list.append(float(np.linalg.norm(weights[i, j] - weights[i + 1, j])))
    h_mean = float(np.mean(h_list)) if h_list else 0.0
    v_mean = float(np.mean(v_list)) if v_list else 0.0
    all_e = h_list + v_list
    u_mean = float(np.mean(all_e)) if all_e else 0.0
    return h_mean, v_mean, u_mean


def _bmu_min_dist(weights: np.ndarray, x: np.ndarray) -> float:
    dists = np.linalg.norm(weights - x.reshape(1, 1, weights.shape[2]), axis=2)
    return float(np.min(dists))


def _quantization_proxy_from_anomalies(
    weights: np.ndarray,
    scale: np.ndarray,
    feature_names: List[str],
    normalization_mode: str,
    online_clip_mode: str,
    anomaly_path: Path,
    max_samples: int = 2500,
) -> tuple[Optional[float], int]:
    if not anomaly_path.exists():
        return None, 0
    rows: List[Dict[str, Any]] = []
    with anomaly_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not rows:
        return None, 0
    dim = weights.shape[2]
    if len(feature_names) != dim:
        return None, 0
    vecs: List[np.ndarray] = []
    for row in rows:
        feat = row.get("features")
        if not isinstance(feat, dict):
            continue
        try:
            arr = np.array([float(feat.get(name, float("nan"))) for name in feature_names], dtype=np.float64)
        except (TypeError, ValueError):
            continue
        if arr.shape[0] != dim or np.any(~np.isfinite(arr)):
            continue
        vecs.append(arr)
        if len(vecs) >= max_samples:
            break
    if not vecs:
        return None, 0
    scale_safe = scale.astype(np.float64).copy()
    scale_safe[scale_safe == 0.0] = 1.0
    dists: List[float] = []
    for raw in vecs:
        x = _apply_online_clip(_normalize_with_scale(raw, scale_safe, normalization_mode), online_clip_mode)
        dists.append(_bmu_min_dist(weights, x))
    return float(np.mean(dists)), len(dists)


def _empty_som_summary() -> Dict[str, Any]:
    return {
        "som_model_present": False,
        "som_metrics_error": "",
        "som_rows": "",
        "som_cols": "",
        "som_dim": "",
        "som_training_steps": "",
        "som_lr": "",
        "som_sigma": "",
        "som_threshold_saved": "",
        "som_kfold": "",
        "som_init_trials": "",
        "som_selected_fold": "",
        "som_selected_init": "",
        "som_validation_accuracy": "",
        "som_normalization_mode": "",
        "som_online_clip_mode": "",
        "som_scale_mean": "",
        "som_scale_std": "",
        "som_scale_min": "",
        "som_scale_max": "",
        "som_weight_mean": "",
        "som_weight_std": "",
        "som_weight_frobenius": "",
        "som_unit_weight_l2_mean": "",
        "som_unit_weight_l2_std": "",
        "som_neighbor_dist_h_mean": "",
        "som_neighbor_dist_v_mean": "",
        "som_umatrix_mean": "",
        "som_quantization_mean_bmu_dist": "",
        "som_quantization_n_samples": "",
    }


# Roll up only snapshot fields, not learner config columns like `som_smooth_k` on the same row.
_SOM_SNAPSHOT_SKIP_ROLLUP = frozenset(
    {
        "som_model_present",
        "som_metrics_error",
        "som_normalization_mode",
        "som_online_clip_mode",
    }
)


def som_snapshot_keys_for_rollup() -> List[str]:
    base = _empty_som_summary()
    return sorted(k for k in base if k.startswith("som_") and k not in _SOM_SNAPSHOT_SKIP_ROLLUP)


def summarize_som_npz(
    npz_path: Path,
    anomaly_events_path: Optional[Path] = None,
    max_anomaly_samples: int = 2500,
) -> Dict[str, Any]:
    """
    Flat dict suitable for merging into run_metrics rows (string keys, JSON/CSV-safe values).
    """
    empty = _empty_som_summary()
    if not npz_path.exists():
        return dict(empty)
    try:
        data = np.load(npz_path, allow_pickle=True)
        weights = data["weights"].astype(np.float64)
        r, c, dim = weights.shape
        scale = data["scale"].astype(np.float64) if "scale" in data else np.ones(dim, dtype=np.float64)
        thr = float(data["threshold"]) if "threshold" in data else 0.0
        steps = int(data["steps"]) if "steps" in data else 0
        lr = float(data["lr"]) if "lr" in data else 0.0
        sigma = float(data["sigma"]) if "sigma" in data else 0.0
        kfold = int(data["kfold"]) if "kfold" in data else 1
        init_trials = int(data["init_trials"]) if "init_trials" in data else 1
        selected_fold = int(data["selected_fold"]) if "selected_fold" in data else -1
        selected_init = int(data["selected_init"]) if "selected_init" in data else -1
        val_acc = float(data["validation_accuracy"]) if "validation_accuracy" in data else 0.0
        norm_mode = str(data["normalization_mode"]) if "normalization_mode" in data else "train_max_100"
        clip_mode = str(data["online_clip_mode"]) if "online_clip_mode" in data else "none"
        if "feature_names" in data:
            fn = data["feature_names"]
            feature_names = [str(x) for x in (list(fn) if hasattr(fn, "__iter__") else [])]
        else:
            feature_names = []

        h_mean, v_mean, u_mean = _neighbor_distances(weights)
        flat = weights.reshape(-1, dim)
        unit_l2 = np.linalg.norm(flat, axis=1)

        out = dict(_empty_som_summary())
        out.update(
            {
                "som_model_present": True,
                "som_metrics_error": "",
                "som_rows": r,
                "som_cols": c,
                "som_dim": dim,
                "som_training_steps": steps,
                "som_lr": lr,
                "som_sigma": sigma,
                "som_threshold_saved": thr,
                "som_kfold": kfold,
                "som_init_trials": init_trials,
                "som_selected_fold": selected_fold,
                "som_selected_init": selected_init,
                "som_validation_accuracy": val_acc,
                "som_normalization_mode": norm_mode,
                "som_online_clip_mode": clip_mode,
                "som_scale_mean": float(np.mean(scale)),
                "som_scale_std": float(np.std(scale)),
                "som_scale_min": float(np.min(scale)),
                "som_scale_max": float(np.max(scale)),
                "som_weight_mean": float(np.mean(weights)),
                "som_weight_std": float(np.std(weights)),
                "som_weight_frobenius": float(np.linalg.norm(weights)),
                "som_unit_weight_l2_mean": float(np.mean(unit_l2)),
                "som_unit_weight_l2_std": float(np.std(unit_l2)),
                "som_neighbor_dist_h_mean": h_mean,
                "som_neighbor_dist_v_mean": v_mean,
                "som_umatrix_mean": u_mean,
            }
        )
        if anomaly_events_path is not None and feature_names:
            q_mean, q_n = _quantization_proxy_from_anomalies(
                weights,
                scale,
                feature_names,
                norm_mode,
                clip_mode,
                anomaly_events_path,
                max_samples=max_anomaly_samples,
            )
            out["som_quantization_mean_bmu_dist"] = q_mean if q_mean is not None else ""
            out["som_quantization_n_samples"] = q_n
        return out
    except Exception as exc:
        err = dict(_empty_som_summary())
        err["som_metrics_error"] = str(exc)[:500]
        return err


def build_som_rollup(run_rows: List[dict]) -> List[dict]:
    """Mean numeric snapshot fields per (variant, fault_id) for completed runs with a model."""
    numeric_keys = som_snapshot_keys_for_rollup()
    if not numeric_keys:
        return []
    groups: Dict[tuple[str, str], List[dict]] = {}
    for row in run_rows:
        if not row.get("som_model_present"):
            continue
        key = (str(row.get("variant", "")), str(row.get("fault_id", "")))
        groups.setdefault(key, []).append(row)
    out_rows: List[dict] = []
    for (variant, fault_id), g in sorted(groups.items()):
        row: Dict[str, Any] = {
            "variant": variant,
            "fault_id": fault_id,
            "n_runs_with_som": len(g),
        }
        for nk in numeric_keys:
            vals = []
            for r in g:
                v = r.get(nk, "")
                if v == "" or v is None:
                    continue
                try:
                    vals.append(float(v))
                except (TypeError, ValueError):
                    continue
            if vals:
                row[f"mean_{nk}"] = float(sum(vals) / len(vals))
        out_rows.append(row)
    return out_rows
