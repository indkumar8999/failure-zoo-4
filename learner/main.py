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
POLL_SEC = float(os.getenv("POLL_SEC", "2.0"))
BOOTSTRAP_SAMPLES = int(os.getenv("BOOTSTRAP_SAMPLES", "180"))
GRID_ROWS = int(os.getenv("SOM_ROWS", "20"))
GRID_COLS = int(os.getenv("SOM_COLS", "20"))
LR = float(os.getenv("SOM_LR", "0.25"))
SIGMA = float(os.getenv("SOM_SIGMA", "3.0"))
THRESHOLD_Q = float(os.getenv("ANOMALY_QUANTILE", "0.99"))
MODEL_PATH = Path(os.getenv("MODEL_PATH", "/data/model/som_model.npz"))
ANOMALY_LOG = Path(os.getenv("ANOMALY_LOG", "/data/events/anomaly_events.jsonl"))

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
        self.weights = np.random.random((rows, cols, dim)).astype(np.float64)
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


def _feature_scale(samples: np.ndarray) -> np.ndarray:
    maxv = np.max(samples, axis=0)
    maxv[maxv == 0.0] = 1.0
    return maxv


def _train_bootstrap(normal_samples: List[np.ndarray]) -> tuple[SOMModel, float, np.ndarray]:
    data = np.array(normal_samples, dtype=np.float64)
    scale = _feature_scale(data)
    norm = np.clip(data / scale, 0.0, 2.0)

    model = SOMModel(GRID_ROWS, GRID_COLS, norm.shape[1], LR, SIGMA)
    rng = np.random.default_rng(42)

    epochs = 8
    for _ in range(epochs):
        for idx in rng.permutation(norm.shape[0]):
            model.train_step(norm[idx])

    dists = np.array([model.score(v) for v in norm], dtype=np.float64)
    threshold = float(np.quantile(dists, THRESHOLD_Q))
    return model, threshold, scale


def _persist_model(model: SOMModel, threshold: float, scale: np.ndarray) -> None:
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        MODEL_PATH,
        rows=model.rows,
        cols=model.cols,
        dim=model.dim,
        lr=model.lr,
        sigma=model.sigma,
        steps=model.steps,
        threshold=threshold,
        scale=scale,
        weights=model.weights,
        feature_names=np.array(state.feature_names, dtype=object),
    )


def _load_model() -> tuple[Optional[SOMModel], float, Optional[np.ndarray]]:
    if not MODEL_PATH.exists():
        return None, 0.0, None
    try:
        data = np.load(MODEL_PATH, allow_pickle=True)
        names = list(data["feature_names"]) if "feature_names" in data else state.feature_names
        if list(names) != state.feature_names:
            return None, 0.0, None
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
        return model, threshold, scale
    except Exception:
        return None, 0.0, None


def _log_anomaly(event: dict) -> None:
    ANOMALY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(ANOMALY_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, separators=(",", ":")) + "\n")


def _worker_loop() -> None:
    model, threshold, scale = _load_model()
    with state.lock:
        state.model = model
        state.threshold = threshold
        state.trained = model is not None and scale is not None
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
                    trained_model, trained_threshold, trained_scale = _train_bootstrap(state.bootstrap_normal)
                    state.model = trained_model
                    state.threshold = trained_threshold
                    state.trained = True
                    scale = trained_scale
                    _persist_model(trained_model, trained_threshold, trained_scale)
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
            assert scale is not None
            x = np.clip(sample.values / scale, 0.0, 3.0)
            score = state.model.score(x)
            is_anomaly = bool(score > state.threshold)

            if not sample.chaos_on:
                state.model.train_step(x)

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
                _persist_model(state.model, state.threshold, scale)

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
