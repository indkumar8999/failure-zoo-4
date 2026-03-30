"""
Offline UBL-style ROC: sweep neighborhood-area (or BMU) score quantiles like §3.2.1
without re-running Docker, using persisted training scores + per-tick score_stream.jsonl.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List, Sequence

import numpy as np

try:
    from experiments.ubl_metrics import Alarm, AlarmTimeFilter, FaultWindow, evaluate_predictions
except ModuleNotFoundError:
    from ubl_metrics import Alarm, AlarmTimeFilter, FaultWindow, evaluate_predictions


def read_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    out: List[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def load_ubl_train_scores(npz_path: Path) -> np.ndarray | None:
    if not npz_path.exists():
        return None
    try:
        data = np.load(npz_path, allow_pickle=True)
        if "ubl_train_scores" not in data:
            return None
        arr = np.asarray(data["ubl_train_scores"], dtype=np.float64)
        return arr if arr.size > 0 else None
    except Exception:
        return None


def _train_scores_fallback(stream: Sequence[dict], post_bootstrap_ts: float | None, fault_on_ts: float | None) -> np.ndarray | None:
    if post_bootstrap_ts is None or fault_on_ts is None:
        return None
    vals: List[float] = []
    for row in stream:
        if str(row.get("type", "")) != "som_score":
            continue
        ts = float(row.get("ts", 0.0))
        if ts < post_bootstrap_ts or ts >= fault_on_ts:
            continue
        if bool(row.get("chaos_on", False)):
            continue
        vals.append(float(row.get("score", 0.0)))
    arr = np.asarray(vals, dtype=np.float64)
    return arr if arr.size >= 12 else None


def quantile_grid(start: float, end: float, step: float) -> List[float]:
    if step <= 0 or end < start:
        return []
    out: List[float] = []
    q = start
    while q <= end + 1e-9:
        out.append(round(float(q), 4))
        q += step
    return out


def synthesize_alarms_from_stream(
    stream: Sequence[dict],
    threshold: float,
    streak_need: int,
    log_min_interval_s: float,
    run_id: str,
    fault_id: str,
) -> List[Alarm]:
    rows = sorted(stream, key=lambda r: float(r.get("ts", 0.0)))
    streak = 0
    alarms: List[Alarm] = []
    last_log_ts = 0.0
    for row in rows:
        if str(row.get("type", "")) != "som_score":
            continue
        ts = float(row.get("ts", 0.0))
        score = float(row.get("score", 0.0))
        if score >= threshold:
            streak += 1
        else:
            streak = 0
        if streak < max(1, streak_need):
            continue
        if log_min_interval_s > 0.0 and last_log_ts > 0.0 and (ts - last_log_ts) < log_min_interval_s:
            continue
        alarms.append(
            Alarm(ts=ts, score=score, threshold=threshold, run_id=run_id, fault_id=fault_id),
        )
        last_log_ts = ts
    return alarms


def replay_run_quantiles(
    *,
    run_dir: Path,
    run_row: dict,
    fault_windows: List[FaultWindow],
    pred_src_label: str,
    timeline: dict,
    poll_sec: float,
    quantiles: Sequence[float],
    matching_mode: str,
    pending_window_s: float,
    alarm_time_filter: AlarmTimeFilter,
) -> List[dict]:
    run_id = str(run_row.get("run_id", ""))
    fault_id = str(run_row.get("fault_id", ""))
    variant = str(run_row.get("variant", ""))
    learner_env = run_row.get("learner_env", {}) if isinstance(run_row.get("learner_env"), dict) else {}
    streak_need = int(float(str(learner_env.get("ANOMALY_STREAK", "3"))))
    log_min = float(str(learner_env.get("ALARM_LOG_MIN_INTERVAL_S", "0") or "0"))

    stream_path = run_dir / "artifacts" / "score_stream.jsonl"
    stream = read_jsonl(stream_path)
    npz_path = run_dir / "artifacts" / "som_model.npz"
    train_scores = load_ubl_train_scores(npz_path)
    if train_scores is None:
        train_scores = _train_scores_fallback(
            stream,
            timeline.get("post_bootstrap_ts"),
            timeline.get("fault_on_ts"),
        )
    if train_scores is None or train_scores.size == 0:
        return [
            {
                "run_id": run_id,
                "variant": variant,
                "fault_id": fault_id,
                "threshold_quantile": q,
                "threshold_value": 0.0,
                "replay_ok": False,
                "replay_note": "missing ubl_train_scores in som_model.npz and insufficient score_stream fallback",
            }
            for q in quantiles
        ]

    post_bootstrap_ts = timeline.get("post_bootstrap_ts")
    fault_on_ts = timeline.get("fault_on_ts")
    out: List[dict] = []
    for q in quantiles:
        thr = float(np.quantile(train_scores, min(0.9999, max(0.0001, float(q)))))
        alarms = synthesize_alarms_from_stream(
            stream,
            threshold=thr,
            streak_need=streak_need,
            log_min_interval_s=log_min,
            run_id=run_id,
            fault_id=fault_id,
        )
        summary = evaluate_predictions(
            alarms=alarms,
            fault_windows=fault_windows,
            pending_window_s=pending_window_s,
            matching_mode=matching_mode,
            alarm_time_filter=alarm_time_filter,
            post_bootstrap_ts=post_bootstrap_ts,
            normal_window_end_ts=fault_on_ts,
            poll_sec=poll_sec,
            prediction_target_source=pred_src_label,
        )
        out.append(
            {
                "run_id": run_id,
                "variant": variant,
                "fault_id": fault_id,
                "threshold_quantile": q,
                "threshold_value": thr,
                "replay_ok": True,
                "replay_note": "",
                "tp": summary.tp,
                "fp": summary.fp,
                "fn": summary.fn,
                "tpr": summary.tpr,
                "fpr": summary.fpr,
                "precision": summary.precision,
                "recall": summary.recall,
                "f1": summary.f1,
                "mean_lead_time_s": summary.mean_lead_time_s,
                "paper_at": summary.paper_at,
                "paper_af": summary.paper_af,
                "paper_ntn": summary.paper_ntn,
                "num_scored_alarms": summary.num_scored_alarms,
                "pending_window_s": pending_window_s,
                "prediction_target_eval": pred_src_label,
            }
        )
    return out


def aggregate_replay_rollup(replay_rows: Iterable[dict]) -> List[dict]:
    """Mean paper AT/AF and TPR/FPR across runs for each (fault_id, variant, quantile)."""
    buckets: dict[tuple[str, str, float], List[dict]] = {}
    for row in replay_rows:
        if not row.get("replay_ok"):
            continue
        key = (
            str(row.get("fault_id", "")),
            str(row.get("variant", "")),
            float(row.get("threshold_quantile", 0.0)),
        )
        buckets.setdefault(key, []).append(row)
    out: List[dict] = []
    for (fault_id, variant, q), rows in sorted(buckets.items()):
        n = len(rows)
        def mean(k: str) -> float:
            return float(sum(float(r.get(k, 0.0)) for r in rows) / max(1, n))

        out.append(
            {
                "fault_id": fault_id,
                "variant": variant,
                "threshold_quantile": q,
                "n_runs": n,
                "mean_paper_at": mean("paper_at"),
                "mean_paper_af": mean("paper_af"),
                "mean_tpr": mean("tpr"),
                "mean_fpr": mean("fpr"),
                "mean_f1": mean("f1"),
                "mean_lead_time_s": mean("mean_lead_time_s"),
            }
        )
    return out
