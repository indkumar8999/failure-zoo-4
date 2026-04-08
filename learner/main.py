import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import requests
from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
from starlette.responses import Response

PROM_BASE = os.getenv("PROM_BASE", "http://prometheus:9090")
POLL_SEC = float(os.getenv("POLL_SEC", "2.0"))
BOOTSTRAP_SAMPLES = int(os.getenv("BOOTSTRAP_SAMPLES", "180"))
RANDOM_SEED = int(os.getenv("UBL_RANDOM_SEED", "42"))
GRID_ROWS = int(os.getenv("SOM_ROWS", "32"))
GRID_COLS = int(os.getenv("SOM_COLS", "32"))
LR = float(os.getenv("SOM_LR", "0.25"))
SIGMA = float(os.getenv("SOM_SIGMA", "3.0"))
THRESHOLD_Q = float(os.getenv("ANOMALY_QUANTILE", "0.85"))
SCORING_MODE = os.getenv("SOM_SCORING_MODE", "ubl_area").strip().lower()
SMOOTH_K = int(os.getenv("SOM_SMOOTH_K", "5"))
ANOMALY_STREAK = int(os.getenv("ANOMALY_STREAK", "3"))
# Minimum seconds between anomaly_events.jsonl rows when > 0 (reduces FP inflation from 1Hz alarms).
ALARM_LOG_MIN_INTERVAL_S = float(os.getenv("ALARM_LOG_MIN_INTERVAL_S", "0"))
SOM_KFOLD = int(os.getenv("SOM_KFOLD", "3"))
SOM_INIT_TRIALS = int(os.getenv("SOM_INIT_TRIALS", "3"))
SOM_NORMALIZATION_MODE = os.getenv("SOM_NORMALIZATION_MODE", "train_max_100").strip().lower()
SOM_ONLINE_CLIP_MODE = os.getenv("SOM_ONLINE_CLIP_MODE", "none").strip().lower()
SOM_CAUSE_Q = int(os.getenv("SOM_CAUSE_Q", "5"))
MODEL_PATH = Path(os.getenv("MODEL_PATH", "/data/model/som_model.npz"))
ANOMALY_LOG = Path(os.getenv("ANOMALY_LOG", "/data/events/anomaly_events.jsonl"))
_SCORE_STREAM_RAW = os.getenv("UBL_SCORE_STREAM_PATH", str(ANOMALY_LOG.parent / "score_stream.jsonl")).strip()
SCORE_STREAM_PATH = Path(_SCORE_STREAM_RAW) if _SCORE_STREAM_RAW else ANOMALY_LOG.parent / "score_stream.jsonl"
SCORE_STREAM_ENABLE = os.getenv("UBL_ENABLE_SCORE_STREAM", "1").strip().lower() not in ("0", "false", "no", "")

FEATURE_QUERIES: Dict[str, str] = {
    "req_rate": "sum(rate(http_requests_total[1m]))",
    "latency_p95": "histogram_quantile(0.95, sum by (le) (rate(http_request_latency_seconds_bucket[1m])))",
    "db_inflight": "max(db_inflight)",
    "leak_mb": "max(leak_mb)",
    "open_fds_sim": "max(open_fds_simulated)",
    "disk_fill_mb": "max(disk_fill_mb)",
    "retry_rate": "sum(rate(retry_calls_total[1m]))",
    "proc_mem_bytes": "max(process_resident_memory_bytes)",
    "proc_open_fds": "max(process_open_fds)",
}
CHAOS_QUERY = "sum(chaos_mode)"

SOM_READY = Gauge("som_model_ready", "SOM model is trained and serving scores")
SOM_THRESHOLD = Gauge("som_anomaly_threshold", "Current anomaly threshold")
SOM_LAST_SCORE = Gauge("som_last_score", "Distance score of latest sample")
SOM_TRAIN_SAMPLES = Gauge("som_training_samples", "Number of normal samples retained for bootstrap")
SOM_TOTAL_SAMPLES = Gauge("som_total_samples", "Total samples observed by learner")
SOM_LAST_CHAOS = Gauge("som_last_chaos_mode_count", "Latest sum of chaos_mode gauges")
SOM_LAST_ANOMALY = Gauge("som_last_anomaly", "1 if latest sample is anomalous")


@dataclass
class Sample:
    ts: float
    values: np.ndarray
    chaos_on: bool


class SOMModel:
    def __init__(self, rows: int, cols: int, dim: int, lr: float, sigma: float):
        self.rows = rows
        self.cols = cols
        self.dim = dim
        self.lr = lr
        self.sigma = sigma
        self.weights = (100.0 * np.random.random((rows, cols, dim))).astype(np.float64)
        self.steps = 0

    def _bmu(self, x: np.ndarray) -> tuple[int, int, float]:
        dists = np.linalg.norm(self.weights - x.reshape(1, 1, self.dim), axis=2)
        idx = int(np.argmin(dists))
        r, c = divmod(idx, self.cols)
        return r, c, float(dists[r, c])

    def _decayed(self) -> tuple[float, float]:
        decay = 1.0 / (1.0 + self.steps / 3000.0)
        return self.lr * decay, max(0.8, self.sigma * decay)

    def train_step(self, x: np.ndarray) -> float:
        r, c, dist = self._bmu(x)
        lr, sigma = self._decayed()
        rr, cc = np.indices((self.rows, self.cols))
        d2 = (rr - r) ** 2 + (cc - c) ** 2
        influence = np.exp(-d2 / (2.0 * sigma * sigma)).reshape(self.rows, self.cols, 1)
        self.weights += influence * lr * (x.reshape(1, 1, self.dim) - self.weights)
        self.steps += 1
        return dist

    def score(self, x: np.ndarray) -> float:
        _, _, dist = self._bmu(x)
        return dist

    def bmu_index(self, x: np.ndarray) -> tuple[int, int]:
        r, c, _ = self._bmu(x)
        return r, c


def _compute_area_map(weights: np.ndarray) -> np.ndarray:
    """Compute UBL neighborhood area size (Manhattan to 4-neighbors)."""
    rows, cols, _ = weights.shape
    area = np.zeros((rows, cols), dtype=np.float64)
    for r in range(rows):
        for c in range(cols):
            here = weights[r, c]
            s = 0.0
            if r > 0:
                s += float(np.sum(np.abs(here - weights[r - 1, c])))
            if r < rows - 1:
                s += float(np.sum(np.abs(here - weights[r + 1, c])))
            if c > 0:
                s += float(np.sum(np.abs(here - weights[r, c - 1])))
            if c < cols - 1:
                s += float(np.sum(np.abs(here - weights[r, c + 1])))
            area[r, c] = s
    return area


class LearnerState:
    def __init__(self):
        self.lock = threading.Lock()
        self.feature_names: List[str] = list(FEATURE_QUERIES.keys())
        self.bootstrap_normal: List[np.ndarray] = []
        self.model: Optional[SOMModel] = None
        self.threshold: float = 0.0
        self.total_samples: int = 0
        self.trained: bool = False
        self.last: Optional[dict] = None
        self.stop = threading.Event()
        self.smooth_window: deque[np.ndarray] = deque(maxlen=max(1, SMOOTH_K))
        self.anomaly_streak_count: int = 0
        self.model_meta: Dict[str, Any] = {}
        self.last_alarm_log_ts: float = 0.0
        self.ubl_train_scores: Optional[np.ndarray] = None


state = LearnerState()
app = FastAPI(title="som-learner")


def _query_prom_scalar(query: str) -> float:
    try:
        resp = requests.get(
            f"{PROM_BASE}/api/v1/query",
            params={"query": query},
            timeout=3,
        )
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data", {}).get("result", [])
        if not data:
            return 0.0
        val = data[0].get("value", [0, "0"])[1]
        return float(val)
    except Exception:
        return 0.0


def _collect_sample() -> Sample:
    vals = [_query_prom_scalar(FEATURE_QUERIES[name]) for name in state.feature_names]
    chaos_count = _query_prom_scalar(CHAOS_QUERY)
    SOM_LAST_CHAOS.set(chaos_count)
    return Sample(ts=time.time(), values=np.array(vals, dtype=np.float64), chaos_on=(chaos_count > 0.0))


def _feature_scale(samples: np.ndarray) -> np.ndarray:
    maxv = np.max(samples, axis=0)
    maxv[maxv == 0.0] = 1.0
    return maxv


def _normalize_with_scale(samples: np.ndarray, scale: np.ndarray) -> np.ndarray:
    if SOM_NORMALIZATION_MODE == "train_max_100":
        return (samples / scale) * 100.0
    # Default fallback remains train-max scaling to preserve stability.
    return (samples / scale) * 100.0


def _apply_online_clip(x: np.ndarray) -> np.ndarray:
    y = np.maximum(x, 0.0)
    if SOM_ONLINE_CLIP_MODE == "none":
        return y
    if SOM_ONLINE_CLIP_MODE == "clip_200":
        return np.clip(y, 0.0, 200.0)
    if SOM_ONLINE_CLIP_MODE == "clip_300":
        return np.clip(y, 0.0, 300.0)
    return y


def _score_with_mode(model: SOMModel, x: np.ndarray) -> tuple[float, float, tuple[int, int], Optional[np.ndarray]]:
    bmu_score = model.score(x)
    bmu_rc = model.bmu_index(x)
    if SCORING_MODE == "ubl_area":
        area_map = _compute_area_map(model.weights)
        r, c = bmu_rc
        return bmu_score, float(area_map[r, c]), bmu_rc, area_map
    return bmu_score, bmu_score, bmu_rc, None


def _train_model(train_norm: np.ndarray, init_seed: int, epochs: int = 8) -> SOMModel:
    model = SOMModel(GRID_ROWS, GRID_COLS, train_norm.shape[1], LR, SIGMA)
    rng_w = np.random.default_rng(init_seed)
    model.weights = rng_w.uniform(0.0, 100.0, size=(GRID_ROWS, GRID_COLS, train_norm.shape[1])).astype(np.float64)
    rng = np.random.default_rng(init_seed + 10007)
    for _ in range(epochs):
        for idx in rng.permutation(train_norm.shape[0]):
            model.train_step(train_norm[idx])
    return model


def _threshold_for_model(model: SOMModel, train_norm: np.ndarray) -> float:
    # Use quantile of all neuron area values for threshold calculation
    area_map = _compute_area_map(model.weights)
    area_values = area_map.flatten()
    return float(np.quantile(area_values, THRESHOLD_Q))


def _validation_accuracy(model: SOMModel, threshold: float, val_norm: np.ndarray) -> float:
    if val_norm.shape[0] == 0:
        return 0.0
    if SCORING_MODE == "ubl_area":
        area_map = _compute_area_map(model.weights)
        scores = np.array([area_map[model.bmu_index(v)] for v in val_norm], dtype=np.float64)
    else:
        scores = np.array([model.score(v) for v in val_norm], dtype=np.float64)
    # Validation data are normal-only, mirroring the paper's unsupervised setup.
    return float(np.mean(scores < threshold))


def _kfold_split_indices(n: int, k: int, seed: int = 42) -> List[np.ndarray]:
    if n <= 0:
        return []
    k_eff = max(1, min(int(k), n))
    rng = np.random.default_rng(seed)
    perm = rng.permutation(n)
    return [arr for arr in np.array_split(perm, k_eff) if arr.size > 0]


def _train_bootstrap(normal_samples: List[np.ndarray]) -> tuple[SOMModel, float, np.ndarray, Dict[str, Any], np.ndarray]:
    data = np.array(normal_samples, dtype=np.float64)
    scale = _feature_scale(data)
    norm = _normalize_with_scale(data, scale)

    folds = _kfold_split_indices(norm.shape[0], SOM_KFOLD, seed=RANDOM_SEED)
    best_model: Optional[SOMModel] = None
    best_threshold = 0.0
    best_acc = -1.0
    best_fold = -1
    best_init = -1
    best_train_norm: Optional[np.ndarray] = None

    for fold_idx, val_idx in enumerate(folds):
        train_idx = np.concatenate([folds[i] for i in range(len(folds)) if i != fold_idx], axis=0) if len(folds) > 1 else val_idx
        train_norm = norm[train_idx]
        val_norm = norm[val_idx]
        for init_idx in range(max(1, SOM_INIT_TRIALS)):
            init_seed = RANDOM_SEED + 1000 + (fold_idx * 137) + init_idx
            model = _train_model(train_norm, init_seed=init_seed, epochs=8)
            threshold = _threshold_for_model(model, train_norm)
            val_acc = _validation_accuracy(model, threshold, val_norm)
            if val_acc > best_acc:
                best_model = model
                best_threshold = threshold
                best_acc = val_acc
                best_fold = fold_idx
                best_init = init_idx
                best_train_norm = np.array(train_norm, dtype=np.float64, copy=True)

    assert best_model is not None
    if best_train_norm is None or best_train_norm.shape[0] == 0:
        best_train_norm = np.array(norm, dtype=np.float64, copy=True)
    area_map = _compute_area_map(best_model.weights)
    ubl_train_scores = np.array(
        [float(area_map[best_model.bmu_index(v)]) for v in best_train_norm],
        dtype=np.float64,
    )
    meta = {
        "random_seed": RANDOM_SEED,
        "kfold": max(1, min(SOM_KFOLD, norm.shape[0])),
        "init_trials": max(1, SOM_INIT_TRIALS),
        "selected_fold": best_fold,
        "selected_init": best_init,
        "validation_accuracy": best_acc,
        "normalization_mode": SOM_NORMALIZATION_MODE,
        "online_clip_mode": SOM_ONLINE_CLIP_MODE,
    }
    return best_model, best_threshold, scale, meta, ubl_train_scores, area_map


def _infer_anomaly_causes(
    model: SOMModel,
    area_map: np.ndarray,
    area_threshold: float,
    anomaly_rc: tuple[int, int],
    feature_names: List[str],
) -> Optional[dict]:
    rows, cols, dim = model.weights.shape
    ar, ac = anomaly_rc
    candidates: List[tuple[int, int, int, float, np.ndarray]] = []
    for r in range(rows):
        for c in range(cols):
            if r == ar and c == ac:
                continue
            if float(area_map[r, c]) >= area_threshold:
                continue
            lattice_dist = abs(r - ar) + abs(c - ac)
            diff_vec = np.abs(model.weights[ar, ac] - model.weights[r, c])
            candidates.append((lattice_dist, r, c, float(np.linalg.norm(diff_vec)), diff_vec))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], item[3]))
    selected = candidates[: max(1, SOM_CAUSE_Q)]
    rankings: List[List[int]] = [list(np.argsort(-item[4])) for item in selected]
    mean_deltas = np.mean(np.stack([item[4] for item in selected], axis=0), axis=0)

    ordered_metrics: List[int] = []
    remaining = set(range(dim))
    while remaining:
        votes: Dict[int, int] = {idx: 0 for idx in remaining}
        for rank in rankings:
            top_remaining = next((idx for idx in rank if idx in remaining), None)
            if top_remaining is not None:
                votes[top_remaining] += 1
        winner = max(votes.keys(), key=lambda idx: (votes[idx], float(mean_deltas[idx])))
        ordered_metrics.append(winner)
        remaining.remove(winner)

    ranking_payload = [
        {
            "metric": feature_names[idx],
            "votes": int(sum(1 for rank in rankings if rank and rank[0] == idx)),
            "mean_abs_delta": float(mean_deltas[idx]),
        }
        for idx in ordered_metrics
    ]
    neighbors = [{"row": int(r), "col": int(c), "lattice_dist": int(ld)} for ld, r, c, _, _ in selected]
    return {
        "method": "majority_vote_top_delta",
        "q": max(1, SOM_CAUSE_Q),
        "anomaly_bmu": {"row": int(ar), "col": int(ac)},
        "normal_neighbors": neighbors,
        "ranking": ranking_payload,
    }


def _persist_model(
    model: SOMModel,
    threshold: float,
    scale: np.ndarray,
    model_meta: Dict[str, Any],
    *,
    ubl_train_scores: Optional[np.ndarray] = None,
) -> None:
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {
        "rows": model.rows,
        "cols": model.cols,
        "dim": model.dim,
        "lr": model.lr,
        "sigma": model.sigma,
        "steps": model.steps,
        "threshold": threshold,
        "scale": scale,
        "weights": model.weights,
        "feature_names": np.array(state.feature_names, dtype=object),
        "kfold": int(model_meta.get("kfold", 1)),
        "init_trials": int(model_meta.get("init_trials", 1)),
        "selected_fold": int(model_meta.get("selected_fold", -1)),
        "selected_init": int(model_meta.get("selected_init", -1)),
        "validation_accuracy": float(model_meta.get("validation_accuracy", 0.0)),
        "normalization_mode": str(model_meta.get("normalization_mode", SOM_NORMALIZATION_MODE)),
        "online_clip_mode": str(model_meta.get("online_clip_mode", SOM_ONLINE_CLIP_MODE)),
    }
    if ubl_train_scores is not None and ubl_train_scores.size > 0:
        payload["ubl_train_scores"] = np.asarray(ubl_train_scores, dtype=np.float64)
    if "area_map" in locals() and area_map is not None:
        payload["area_map"] = np.asarray(area_map, dtype=np.float64)
    np.savez_compressed(MODEL_PATH, **payload)


def _load_model() -> tuple[Optional[SOMModel], float, Optional[np.ndarray], Dict[str, Any], Optional[np.ndarray]]:
    if not MODEL_PATH.exists():
        return None, 0.0, None, {}, None
    try:
        data = np.load(MODEL_PATH, allow_pickle=True)
        names = list(data["feature_names"]) if "feature_names" in data else state.feature_names
        if list(names) != state.feature_names:
            return None, 0.0, None, {}, None
        model = SOMModel(
            int(data["rows"]),
            int(data["cols"]),
            int(data["dim"]),
            float(data["lr"]),
            float(data["sigma"]),
        )
        model.steps = int(data["steps"])
        model.weights = data["weights"].astype(np.float64)
        threshold = float(data["threshold"])
        scale = data["scale"].astype(np.float64)
        meta = {
            "kfold": int(data["kfold"]) if "kfold" in data else max(1, SOM_KFOLD),
            "init_trials": int(data["init_trials"]) if "init_trials" in data else max(1, SOM_INIT_TRIALS),
            "selected_fold": int(data["selected_fold"]) if "selected_fold" in data else -1,
            "selected_init": int(data["selected_init"]) if "selected_init" in data else -1,
            "validation_accuracy": float(data["validation_accuracy"]) if "validation_accuracy" in data else 0.0,
            "normalization_mode": str(data["normalization_mode"]) if "normalization_mode" in data else SOM_NORMALIZATION_MODE,
            "online_clip_mode": str(data["online_clip_mode"]) if "online_clip_mode" in data else SOM_ONLINE_CLIP_MODE,
        }
        uts = None
        if "ubl_train_scores" in data:
            uts = np.asarray(data["ubl_train_scores"], dtype=np.float64)
            if uts.size == 0:
                uts = None
        return model, threshold, scale, meta, uts
    except Exception:
        return None, 0.0, None, {}, None


def _log_anomaly(event: dict) -> None:
    ANOMALY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(ANOMALY_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, separators=(",", ":")) + "\n")


def _log_score_stream(event: dict) -> None:
    if not SCORE_STREAM_ENABLE:
        return
    SCORE_STREAM_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SCORE_STREAM_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, separators=(",", ":")) + "\n")


def _worker_loop() -> None:
    model, threshold, scale, model_meta, loaded_train_scores = _load_model()
    with state.lock:
        state.model = model
        state.threshold = threshold
        state.trained = model is not None and scale is not None
        state.model_meta = model_meta
        state.ubl_train_scores = loaded_train_scores
    SOM_READY.set(1 if state.trained else 0)
    SOM_THRESHOLD.set(state.threshold)

    while not state.stop.is_set():
        raw_sample = _collect_sample()
        with state.lock:
            state.total_samples += 1
            SOM_TOTAL_SAMPLES.set(state.total_samples)
            state.smooth_window.append(raw_sample.values.copy())
            if len(state.smooth_window) == 0:
                smoothed = raw_sample.values.copy()
            else:
                smoothed = np.mean(np.stack(list(state.smooth_window), axis=0), axis=0)
            sample = Sample(ts=raw_sample.ts, values=smoothed, chaos_on=raw_sample.chaos_on)

            if not state.trained:
                if not sample.chaos_on:
                    state.bootstrap_normal.append(sample.values)
                    SOM_TRAIN_SAMPLES.set(len(state.bootstrap_normal))
                if len(state.bootstrap_normal) >= BOOTSTRAP_SAMPLES:
                    trained_model, trained_threshold, trained_scale, trained_meta, ubl_train_scores = _train_bootstrap(
                        state.bootstrap_normal
                    )
                    state.model = trained_model
                    state.threshold = trained_threshold
                    state.trained = True
                    state.model_meta = trained_meta
                    scale = trained_scale
                    _persist_model(
                        trained_model,
                        trained_threshold,
                        trained_scale,
                        trained_meta,
                        ubl_train_scores=ubl_train_scores,
                    )
                    SOM_READY.set(1)
                    SOM_THRESHOLD.set(trained_threshold)
                state.last = {
                    "ts": sample.ts,
                    "trained": state.trained,
                    "collecting_bootstrap": len(state.bootstrap_normal),
                    "chaos_on": sample.chaos_on,
                    "normalization_mode": SOM_NORMALIZATION_MODE,
                    "online_clip_mode": SOM_ONLINE_CLIP_MODE,
                }
                time.sleep(POLL_SEC)
                continue

            assert state.model is not None
            assert scale is not None
            x = _apply_online_clip(_normalize_with_scale(sample.values, scale))
            bmu_score, score, bmu_rc, area_map = _score_with_mode(state.model, x)
            is_anomaly = bool(score >= state.threshold)
            if is_anomaly:
                state.anomaly_streak_count += 1
            else:
                state.anomaly_streak_count = 0
            is_alarm = is_anomaly and (state.anomaly_streak_count >= max(1, ANOMALY_STREAK))
            cause_inference = None
            if is_alarm and SCORING_MODE == "ubl_area" and area_map is not None:
                cause_inference = _infer_anomaly_causes(
                    model=state.model,
                    area_map=area_map,
                    area_threshold=state.threshold,
                    anomaly_rc=bmu_rc,
                    feature_names=state.feature_names,
                )

            if not sample.chaos_on:
                state.model.train_step(x)

            SOM_LAST_SCORE.set(score)
            SOM_LAST_ANOMALY.set(1 if is_anomaly else 0)
            SOM_THRESHOLD.set(state.threshold)

            if SCORE_STREAM_ENABLE:
                _log_score_stream(
                    {
                        "ts": sample.ts,
                        "type": "som_score",
                        "score": score,
                        "bmu_score": bmu_score,
                        "chaos_on": bool(sample.chaos_on),
                        "threshold": state.threshold,
                        "scoring_mode": SCORING_MODE,
                    }
                )

            state.last = {
                "ts": sample.ts,
                "trained": True,
                "chaos_on": sample.chaos_on,
                "score": score,
                "bmu_score": bmu_score,
                "threshold": state.threshold,
                "is_anomaly": is_anomaly,
                "is_alarm": is_alarm,
                "anomaly_streak_count": state.anomaly_streak_count,
                "scoring_mode": SCORING_MODE,
                "smooth_k": max(1, SMOOTH_K),
                "alarm_streak_target": max(1, ANOMALY_STREAK),
                "normalization_mode": SOM_NORMALIZATION_MODE,
                "online_clip_mode": SOM_ONLINE_CLIP_MODE,
                "cause_inference": cause_inference,
                "model_meta": state.model_meta,
                "features": {
                    name: float(val) for name, val in zip(state.feature_names, sample.values)
                },
            }

            if is_alarm:
                log_alarm = True
                if ALARM_LOG_MIN_INTERVAL_S > 0.0 and state.last_alarm_log_ts > 0.0:
                    if (sample.ts - state.last_alarm_log_ts) < ALARM_LOG_MIN_INTERVAL_S:
                        log_alarm = False
                if log_alarm:
                    state.last_alarm_log_ts = float(sample.ts)
                    _log_anomaly(
                        {
                            "ts": sample.ts,
                            "type": "som_anomaly",
                            "score": score,
                            "bmu_score": bmu_score,
                            "threshold": state.threshold,
                            "scoring_mode": SCORING_MODE,
                            "anomaly_streak_count": state.anomaly_streak_count,
                            "alarm_streak_target": max(1, ANOMALY_STREAK),
                            "smooth_k": max(1, SMOOTH_K),
                            "normalization_mode": SOM_NORMALIZATION_MODE,
                            "online_clip_mode": SOM_ONLINE_CLIP_MODE,
                            "chaos_on": sample.chaos_on,
                            "cause_inference": cause_inference,
                            "model_meta": state.model_meta,
                            "features": state.last["features"],
                            "alarm_log_min_interval_s": ALARM_LOG_MIN_INTERVAL_S,
                        }
                    )

            if state.total_samples % 30 == 0:
                _persist_model(
                    state.model,
                    state.threshold,
                    scale,
                    state.model_meta,
                    ubl_train_scores=state.ubl_train_scores,
                )

        time.sleep(POLL_SEC)


@app.on_event("startup")
def startup_event() -> None:
    t = threading.Thread(target=_worker_loop, daemon=True)
    t.start()


@app.on_event("shutdown")
def shutdown_event() -> None:
    state.stop.set()


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/status")
def status() -> dict:
    with state.lock:
        return {
            "trained": state.trained,
            "bootstrap_samples": len(state.bootstrap_normal),
            "bootstrap_target": BOOTSTRAP_SAMPLES,
            "total_samples": state.total_samples,
            "threshold": state.threshold,
            "feature_names": state.feature_names,
            "model_path": str(MODEL_PATH),
            "anomaly_log": str(ANOMALY_LOG),
            "scoring_mode": SCORING_MODE,
            "smooth_k": max(1, SMOOTH_K),
            "alarm_streak_target": max(1, ANOMALY_STREAK),
            "normalization_mode": SOM_NORMALIZATION_MODE,
            "online_clip_mode": SOM_ONLINE_CLIP_MODE,
            "cause_q": max(1, SOM_CAUSE_Q),
            "model_meta": state.model_meta,
            "alarm_log_min_interval_s": ALARM_LOG_MIN_INTERVAL_S,
        }


@app.get("/latest")
def latest() -> dict:
    with state.lock:
        return state.last or {"trained": state.trained, "total_samples": state.total_samples}


@app.get("/signal")
def signal() -> dict:
    with state.lock:
        if not state.trained:
            return {
                "state": "training",
                "color": "yellow",
                "bootstrap_samples": len(state.bootstrap_normal),
                "bootstrap_target": BOOTSTRAP_SAMPLES,
            }

        if not state.last:
            return {
                "state": "unknown",
                "color": "yellow",
                "trained": True,
                "threshold": state.threshold,
            }

        is_anomaly = bool(state.last.get("is_anomaly", False))
        return {
            "state": "anomalous" if is_anomaly else "normal",
            "color": "red" if is_anomaly else "green",
            "trained": True,
            "chaos_on": bool(state.last.get("chaos_on", False)),
            "score": float(state.last.get("score", 0.0)),
            "threshold": state.threshold,
            "ts": state.last.get("ts"),
        }


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
