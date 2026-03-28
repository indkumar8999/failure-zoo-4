import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import requests
from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
from starlette.responses import Response

PROM_BASE = os.getenv("PROM_BASE", "http://prometheus:9090")
POLL_SEC = float(os.getenv("POLL_SEC", "1.0"))
BOOTSTRAP_SAMPLES = int(os.getenv("BOOTSTRAP_SAMPLES", "180"))
GRID_ROWS = int(os.getenv("SOM_ROWS", "32"))
GRID_COLS = int(os.getenv("SOM_COLS", "32"))
LR = float(os.getenv("SOM_LR", "1.0"))
SIGMA = float(os.getenv("SOM_SIGMA", "2.0"))
NEIGHBORHOOD_RADIUS = float(os.getenv("NEIGHBORHOOD_RADIUS", "2.0"))
SMOOTH_WINDOW = int(os.getenv("SMOOTH_WINDOW", "20"))
THRESHOLD_Q = float(os.getenv("ANOMALY_QUANTILE", "0.99"))
MODEL_PATH = Path(os.getenv("MODEL_PATH", "/data/model/som_model.npz"))
ANOMALY_LOG = Path(os.getenv("ANOMALY_LOG", "/data/events/anomaly_events.jsonl"))

FEATURE_QUERIES: Dict[str, str] = {
    "process_resident_memory_bytes": "max(process_resident_memory_bytes{job=\"app\"})",
    "process_virtual_memory_bytes": "max(process_virtual_memory_bytes{job=\"app\"})",
    "python_gc_objects_collected_total": "sum(rate(python_gc_objects_collected_total{job=\"app\"}[1m]))",
    "python_gc_objects_uncollectable_total": "sum(rate(python_gc_objects_uncollectable_total{job=\"app\"}[1m]))",
    "python_gc_collections_total": "sum(rate(python_gc_collections_total{job=\"app\"}[1m]))",
    "process_cpu_seconds_total": "sum(rate(process_cpu_seconds_total{job=\"app\"}[1m]))",
    "process_open_fds": "max(process_open_fds{job=\"app\"})",
    "process_max_fds": "max(process_max_fds{job=\"app\"})",
    "process_start_time_seconds": "time() - max(process_start_time_seconds{job=\"app\"})",
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
    def __init__(self, rows: int, cols: int, dim: int, lr: float, sigma: float, smooth_window: int = 5):
        self.rows = rows
        self.cols = cols
        self.dim = dim
        self.lr = lr
        self.sigma = sigma
        # Keep weights in the same [0, 100] range as normalized input vectors.
        self.weights = (np.random.random((rows, cols, dim)) * 100.0).astype(np.float64)
        self.smooth_window = max(1, int(smooth_window))
        # Windowed smoothing state for each neuron's weight vector.
        self.smooth_history = np.zeros((rows, cols, self.smooth_window, dim), dtype=np.float64)
        self.smooth_sum = self.weights.copy()
        self.smooth_count = np.ones((rows, cols), dtype=np.int32)
        self.smooth_pos = np.zeros((rows, cols), dtype=np.int32)
        self.smooth_history[:, :, 0, :] = self.weights
        if self.smooth_window > 1:
            self.smooth_pos.fill(1)
        self.steps = 0

    def _bmu(self, x: np.ndarray) -> tuple[int, int, float]:
        dists = np.linalg.norm(self.weights - x.reshape(1, 1, self.dim), axis=2)
        idx = int(np.argmin(dists))
        r, c = divmod(idx, self.cols)
        return r, c, float(dists[r, c])

    def train_step(self, x: np.ndarray, radius: float = 2.0) -> float:
        r, c, dist = self._bmu(x)
        # Fixed learning coefficient L(t) = 1
        # Gaussian neighborhood influence based on lattice distance to BMU
        rr, cc = np.indices((self.rows, self.cols))
        d2 = (rr - r) ** 2 + (cc - c) ** 2
        # Select neurons within radius
        mask = d2 <= (radius * radius)
        # Gaussian influence: exp(-d^2 / (2 * radius^2))
        influence = np.exp(-d2[mask] / (2.0 * radius * radius))
        # First apply SOM update, then smooth with a fixed-size window over recent weights.
        old_w = self.weights[mask]
        raw_new = old_w + influence.reshape(-1, 1) * (x.reshape(1, self.dim) - old_w)
        indices = np.argwhere(mask)
        for i, (nr, nc) in enumerate(indices):
            cnt = int(self.smooth_count[nr, nc])
            pos = int(self.smooth_pos[nr, nc])

            if cnt == self.smooth_window:
                old_hist = self.smooth_history[nr, nc, pos]
                self.smooth_sum[nr, nc] -= old_hist
            else:
                self.smooth_count[nr, nc] = cnt + 1

            self.smooth_history[nr, nc, pos] = raw_new[i]
            self.smooth_sum[nr, nc] += raw_new[i]
            self.smooth_pos[nr, nc] = (pos + 1) % self.smooth_window

            denom = float(self.smooth_count[nr, nc])
            self.weights[nr, nc] = self.smooth_sum[nr, nc] / denom
        self.steps += 1
        return dist

    def score(self, x: np.ndarray) -> float:
        _, _, dist = self._bmu(x)
        return dist
    
    def area_score(self, bmu_r: int, bmu_c: int, radius: float) -> float:
        """Calculate area of BMU from weight-space Manhattan distances."""
        rr, cc = np.indices((self.rows, self.cols))
        euclidean_dist_sq = (rr - bmu_r) ** 2 + (cc - bmu_c) ** 2
        # Select neurons within radius
        mask = euclidean_dist_sq <= (radius * radius)
        # Manhattan distance is computed in feature space between neuron weights.
        bmu_w = self.weights[bmu_r, bmu_c]
        neighbor_w = self.weights[mask]
        manhattan_dists = np.sum(np.abs(neighbor_w - bmu_w.reshape(1, self.dim)), axis=1)
        area = float(np.sum(manhattan_dists))
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


def _feature_minmax(samples: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    minv = np.min(samples, axis=0)
    maxv = np.max(samples, axis=0)
    span = maxv - minv
    span[span == 0.0] = 1.0
    return minv, span


def _normalize_0_100(values: np.ndarray, minv: np.ndarray, span: np.ndarray, clip_hi: float = 100.0) -> np.ndarray:
    return np.clip(((values - minv) / span) * 100.0, 0.0, clip_hi)


def _train_bootstrap(normal_samples: List[np.ndarray]) -> tuple[SOMModel, float, np.ndarray, np.ndarray]:
    data = np.array(normal_samples, dtype=np.float64)
    minv, span = _feature_minmax(data)
    norm = _normalize_0_100(data, minv, span)

    model = SOMModel(GRID_ROWS, GRID_COLS, norm.shape[1], LR, SIGMA, smooth_window=SMOOTH_WINDOW)
    rng = np.random.default_rng(42)

    epochs = 8
    for _ in range(epochs):
        for idx in rng.permutation(norm.shape[0]):
            model.train_step(norm[idx], radius=NEIGHBORHOOD_RADIUS)

    # Calculate area for each neuron in the map
    areas = []
    for r in range(model.rows):
        for c in range(model.cols):
            area = model.area_score(r, c, NEIGHBORHOOD_RADIUS)
            areas.append(area)
    
    # Threshold is 85th percentile of all neuron areas
    areas_array = np.array(areas, dtype=np.float64)
    threshold = float(np.percentile(areas_array, 85.0))
    return model, threshold, minv, span


def _persist_model(model: SOMModel, threshold: float, scale_min: np.ndarray, scale_span: np.ndarray) -> None:
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        MODEL_PATH,
        rows=model.rows,
        cols=model.cols,
        dim=model.dim,
        lr=model.lr,
        sigma=model.sigma,
        smooth_window=model.smooth_window,
        steps=model.steps,
        threshold=threshold,
        scale_min=scale_min,
        scale_span=scale_span,
        weights=model.weights,
        smooth_sum=model.smooth_sum,
        smooth_history=model.smooth_history,
        smooth_count=model.smooth_count,
        smooth_pos=model.smooth_pos,
        feature_names=np.array(state.feature_names, dtype=object),
    )


def _load_model() -> tuple[Optional[SOMModel], float, Optional[np.ndarray], Optional[np.ndarray]]:
    if not MODEL_PATH.exists():
        return None, 0.0, None, None
    try:
        data = np.load(MODEL_PATH, allow_pickle=True)
        names = list(data["feature_names"]) if "feature_names" in data else state.feature_names
        if list(names) != state.feature_names:
            return None, 0.0, None, None
        smooth_window = int(data["smooth_window"]) if "smooth_window" in data else SMOOTH_WINDOW
        model = SOMModel(
            int(data["rows"]),
            int(data["cols"]),
            int(data["dim"]),
            float(data["lr"]),
            float(data["sigma"]),
            smooth_window=smooth_window,
        )
        model.steps = int(data["steps"])
        model.weights = data["weights"].astype(np.float64)
        if all(k in data for k in ["smooth_sum", "smooth_history", "smooth_count", "smooth_pos"]):
            model.smooth_sum = data["smooth_sum"].astype(np.float64)
            model.smooth_history = data["smooth_history"].astype(np.float64)
            model.smooth_count = data["smooth_count"].astype(np.int32)
            model.smooth_pos = data["smooth_pos"].astype(np.int32)
        else:
            # Backward compatibility for checkpoints without windowed smoothing state.
            model.smooth_sum = model.weights.copy()
            model.smooth_history = np.zeros((model.rows, model.cols, model.smooth_window, model.dim), dtype=np.float64)
            model.smooth_history[:, :, 0, :] = model.weights
            model.smooth_count = np.ones((model.rows, model.cols), dtype=np.int32)
            model.smooth_pos = np.zeros((model.rows, model.cols), dtype=np.int32)
            if model.smooth_window > 1:
                model.smooth_pos.fill(1)
        threshold = float(data["threshold"])
        if "scale_min" in data and "scale_span" in data:
            scale_min = data["scale_min"].astype(np.float64)
            scale_span = data["scale_span"].astype(np.float64)
        elif "scale" in data:
            # Backward compatibility with older checkpoints.
            scale_min = np.zeros_like(data["scale"], dtype=np.float64)
            scale_span = data["scale"].astype(np.float64)
            scale_span[scale_span == 0.0] = 1.0
        else:
            return None, 0.0, None, None
        return model, threshold, scale_min, scale_span
    except Exception:
        return None, 0.0, None, None


def _log_anomaly(event: dict) -> None:
    ANOMALY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(ANOMALY_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, separators=(",", ":")) + "\n")


def _worker_loop() -> None:
    model, threshold, scale_min, scale_span = _load_model()
    with state.lock:
        state.model = model
        state.threshold = threshold
        state.trained = model is not None and scale_min is not None and scale_span is not None
    SOM_READY.set(1 if state.trained else 0)
    SOM_THRESHOLD.set(state.threshold)

    while not state.stop.is_set():
        sample = _collect_sample()
        with state.lock:
            state.total_samples += 1
            SOM_TOTAL_SAMPLES.set(state.total_samples)

            if not state.trained:
                if not sample.chaos_on:
                    state.bootstrap_normal.append(sample.values)
                    SOM_TRAIN_SAMPLES.set(len(state.bootstrap_normal))
                if len(state.bootstrap_normal) >= BOOTSTRAP_SAMPLES:
                    trained_model, trained_threshold, trained_min, trained_span = _train_bootstrap(state.bootstrap_normal)
                    state.model = trained_model
                    state.threshold = trained_threshold
                    state.trained = True
                    scale_min = trained_min
                    scale_span = trained_span
                    _persist_model(trained_model, trained_threshold, trained_min, trained_span)
                    SOM_READY.set(1)
                    SOM_THRESHOLD.set(trained_threshold)
                state.last = {
                    "ts": sample.ts,
                    "trained": state.trained,
                    "collecting_bootstrap": len(state.bootstrap_normal),
                    "chaos_on": sample.chaos_on,
                }
                time.sleep(POLL_SEC)
                continue

            assert state.model is not None
            assert scale_min is not None
            assert scale_span is not None
            x = _normalize_0_100(sample.values, scale_min, scale_span)
            # Find BMU for scoring
            bmu_r, bmu_c, _ = state.model._bmu(x)
            # Score is the area of the BMU neighborhood
            score = state.model.area_score(bmu_r, bmu_c, NEIGHBORHOOD_RADIUS)
            is_anomaly = bool(score > state.threshold)

            if not sample.chaos_on:
                state.model.train_step(x, radius=NEIGHBORHOOD_RADIUS)

            SOM_LAST_SCORE.set(score)
            SOM_LAST_ANOMALY.set(1 if is_anomaly else 0)
            SOM_THRESHOLD.set(state.threshold)

            state.last = {
                "ts": sample.ts,
                "trained": True,
                "chaos_on": sample.chaos_on,
                "score": score,
                "threshold": state.threshold,
                "is_anomaly": is_anomaly,
                "features": {
                    name: float(val) for name, val in zip(state.feature_names, sample.values)
                },
            }

            if is_anomaly:
                _log_anomaly(
                    {
                        "ts": sample.ts,
                        "type": "som_anomaly",
                        "score": score,
                        "threshold": state.threshold,
                        "chaos_on": sample.chaos_on,
                        "features": state.last["features"],
                    }
                )

            if state.total_samples % 30 == 0:
                _persist_model(state.model, state.threshold, scale_min, scale_span)

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
