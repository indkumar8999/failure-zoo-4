from __future__ import annotations

import argparse
import csv
import json
import math
import random
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

try:
    from experiments.ubl_metrics import (
        Alarm,
        AlarmTimeFilter,
        FaultWindow,
        PredictionSummary,
        evaluate_predictions,
    )
except ModuleNotFoundError:
    from ubl_metrics import (
        Alarm,
        AlarmTimeFilter,
        FaultWindow,
        PredictionSummary,
        evaluate_predictions,
    )

try:
    from experiments.som_model_metrics import build_som_rollup, summarize_som_npz
except ModuleNotFoundError:
    from som_model_metrics import build_som_rollup, summarize_som_npz

try:
    from experiments import ubl_roc_replay
except ModuleNotFoundError:
    import ubl_roc_replay  # type: ignore


def read_jsonl(path: Path) -> Iterable[dict]:
    if not path.exists():
        return []
    items = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return items


def build_windows(run_events: Path, fallback_fault_id: str, run_id: str) -> List[FaultWindow]:
    rows = [x for x in read_jsonl(run_events) if x.get("type") == "fault_window"]
    rows.sort(key=lambda x: float(x.get("ts", 0.0)))
    out: List[FaultWindow] = []
    start_ts = None
    fault_id = fallback_fault_id
    for row in rows:
        state = row.get("state")
        if state == "on":
            start_ts = float(row.get("ts", 0.0))
            fault_id = str(row.get("fault_id", fallback_fault_id))
        elif state == "off" and start_ts is not None:
            out.append(FaultWindow(fault_id=fault_id, start_ts=start_ts, end_ts=float(row.get("ts", start_ts)), run_id=run_id))
            start_ts = None
    return out


def parse_run_events_timeline(run_events: Path) -> dict:
    """Phase / fault / prediction_target timestamps for paper-style AF and t2 selection."""
    rows = list(read_jsonl(run_events))
    post_bootstrap_ts = None
    for row in rows:
        if row.get("type") != "phase":
            continue
        if str(row.get("phase", "")) == "bootstrap":
            t0 = float(row.get("ts", 0.0))
            d = float(row.get("duration_s", 0.0))
            post_bootstrap_ts = t0 + d
            break
    fault_on_ts = None
    for row in rows:
        if row.get("type") != "fault_window" or row.get("state") != "on":
            continue
        fault_on_ts = float(row.get("ts", 0.0))
        break
    slo_proxy_ts = None
    for row in rows:
        if row.get("type") != "prediction_target":
            continue
        kind = str(row.get("target_kind", ""))
        if kind != "slo_violation_proxy":
            continue
        ts = float(row.get("ts", 0.0))
        slo_proxy_ts = ts if slo_proxy_ts is None else min(slo_proxy_ts, ts)
    return {
        "post_bootstrap_ts": post_bootstrap_ts,
        "fault_on_ts": fault_on_ts,
        "slo_proxy_ts": slo_proxy_ts,
    }


def build_evaluation_fault_windows(
    run_events: Path,
    fallback_fault_id: str,
    run_id: str,
    target_source: str = "auto",
) -> tuple[List[FaultWindow], str, dict]:
    """
    Fault windows for scoring: use SLO proxy t2 when events exist and source requests it,
    else fault_window injection onset (legacy).
    """
    base_windows = build_windows(run_events, fallback_fault_id, run_id)
    tl = parse_run_events_timeline(run_events)
    src = (target_source or "auto").strip().lower()
    if src == "auto":
        src = "slo_proxy" if tl.get("slo_proxy_ts") is not None else "injection_onset"
    if src == "slo_proxy" and tl.get("slo_proxy_ts") is not None:
        t2 = float(tl["slo_proxy_ts"])
        fid = base_windows[0].fault_id if base_windows else fallback_fault_id
        end_ts = base_windows[-1].end_ts if base_windows else t2
        windows = [FaultWindow(fault_id=fid, start_ts=t2, end_ts=end_ts, run_id=run_id)]
        return windows, "slo_violation_proxy", tl
    return base_windows, "injection_onset", tl


def build_alarms(anomaly_events: Path, run_id: str, fault_id: str) -> List[Alarm]:
    rows = list(read_jsonl(anomaly_events))
    out: List[Alarm] = []
    for row in rows:
        ts = float(row.get("ts", 0.0))
        score = float(row.get("score", 0.0))
        threshold = float(row.get("threshold", 0.0))
        out.append(Alarm(ts=ts, score=score, threshold=threshold, run_id=run_id, fault_id=fault_id))
    return out


def infer_faithfulness_label(run: dict) -> str:
    explicit = str(run.get("faithfulness_label", "")).strip()
    if explicit:
        return explicit
    scope = str(run.get("study_scope", "extended")).strip().lower()
    family = str(run.get("fault_family", "extended")).strip().lower()
    if scope == "paper_faithful" and family == "paper_aligned":
        return "paper-faithful-with-proxy"
    return "extended-beyond-paper"


def _safe_float(v: object, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


EXPECTED_FEATURES_BY_FAMILY = {
    "paper_aligned": {"proc_mem_bytes", "retry_rate", "latency_p95", "req_rate"},
    "extended": {"open_fds_sim", "disk_fill_mb", "db_inflight", "retry_rate", "latency_p95", "req_rate"},
}


def analyze_feature_coverage(anomaly_events_path: Path, fault_family: str) -> dict:
    rows = [x for x in read_jsonl(anomaly_events_path) if isinstance(x.get("features"), dict)]
    if not rows:
        return {
            "coverage_ok": False,
            "observability_limited": True,
            "top_feature": "",
            "top_effect_size": 0.0,
            "degenerate_features": [],
            "normal_variance_score": 0.0,
        }
    normal = [r["features"] for r in rows if not bool(r.get("chaos_on", False))]
    chaos = [r["features"] for r in rows if bool(r.get("chaos_on", False))]
    feature_names = sorted({k for r in rows for k in r["features"].keys()})
    deltas: Dict[str, float] = {}
    variances: Dict[str, float] = {}
    for name in feature_names:
        normal_vals = [_safe_float(f.get(name, 0.0)) for f in normal]
        chaos_vals = [_safe_float(f.get(name, 0.0)) for f in chaos]
        n_mean = _mean(normal_vals) if normal_vals else 0.0
        c_mean = _mean(chaos_vals) if chaos_vals else 0.0
        deltas[name] = abs(c_mean - n_mean)
        variances[name] = _std(normal_vals) if len(normal_vals) > 1 else 0.0
    top_feature = max(deltas.keys(), key=lambda k: deltas[k]) if deltas else ""
    top_effect = float(deltas.get(top_feature, 0.0))
    degenerate = sorted([k for k, v in variances.items() if v < 1e-9])
    normal_variance_score = float(_mean(list(variances.values())) if variances else 0.0)
    expected = EXPECTED_FEATURES_BY_FAMILY.get(str(fault_family).strip().lower(), set())
    expected_hit = max((deltas.get(k, 0.0) for k in expected), default=0.0)
    coverage_ok = bool(top_effect > 1e-6 and (expected_hit > 1e-8 or not expected))
    return {
        "coverage_ok": coverage_ok,
        "observability_limited": not coverage_ok,
        "top_feature": top_feature,
        "top_effect_size": top_effect,
        "degenerate_features": degenerate,
        "normal_variance_score": normal_variance_score,
    }


def _mean(vals: Sequence[float]) -> float:
    return float(sum(vals) / max(1, len(vals)))


def _std(vals: Sequence[float]) -> float:
    if len(vals) <= 1:
        return 0.0
    m = _mean(vals)
    return float(math.sqrt(sum((x - m) ** 2 for x in vals) / (len(vals) - 1)))


def _stderr(vals: Sequence[float]) -> float:
    if len(vals) <= 1:
        return 0.0
    return float(_std(vals) / math.sqrt(len(vals)))


def _ci95_normal(vals: Sequence[float]) -> Tuple[float, float]:
    if not vals:
        return 0.0, 0.0
    m = _mean(vals)
    se = _stderr(vals)
    margin = 1.96 * se
    return float(m - margin), float(m + margin)


def _ci95_bootstrap(vals: Sequence[float], n_boot: int = 1000, seed: int = 42) -> Tuple[float, float]:
    if not vals:
        return 0.0, 0.0
    if len(vals) == 1:
        return float(vals[0]), float(vals[0])
    rng = random.Random(seed)
    samples: List[float] = []
    n = len(vals)
    for _ in range(n_boot):
        draw = [vals[rng.randrange(n)] for _ in range(n)]
        samples.append(_mean(draw))
    samples.sort()
    lo_idx = max(0, int(0.025 * (len(samples) - 1)))
    hi_idx = min(len(samples) - 1, int(0.975 * (len(samples) - 1)))
    return float(samples[lo_idx]), float(samples[hi_idx])


def _aggregate_numeric(metric_summaries: Sequence[PredictionSummary]) -> dict:
    metric_values: Dict[str, List[float]] = {
        "tpr": [x.tpr for x in metric_summaries],
        "fpr": [x.fpr for x in metric_summaries],
        "precision": [x.precision for x in metric_summaries],
        "recall": [x.recall for x in metric_summaries],
        "f1": [x.f1 for x in metric_summaries],
        "lead_time_s": [x.mean_lead_time_s for x in metric_summaries],
        "median_lead_time_s": [x.median_lead_time_s for x in metric_summaries],
        "alarm_fp_fraction": [x.alarm_fp_fraction for x in metric_summaries],
        "paper_af": [x.paper_af for x in metric_summaries],
        "paper_at": [x.paper_at for x in metric_summaries],
        "paper_ntn": [float(x.paper_ntn) for x in metric_summaries],
    }
    out: Dict[str, float] = {}
    for name, vals in metric_values.items():
        mean_val = _mean(vals)
        std_val = _std(vals)
        stderr_val = _stderr(vals)
        ci95_lo, ci95_hi = _ci95_normal(vals)
        b_lo, b_hi = _ci95_bootstrap(vals)
        out[f"mean_{name}"] = mean_val
        out[f"std_{name}"] = std_val
        out[f"stderr_{name}"] = stderr_val
        out[f"ci95_low_{name}"] = ci95_lo
        out[f"ci95_high_{name}"] = ci95_hi
        out[f"bootstrap_ci95_low_{name}"] = b_lo
        out[f"bootstrap_ci95_high_{name}"] = b_hi
    return out


def summarize_campaign(
    campaign_dir: Path,
    matching_mode: str = "many_to_many",
    alarm_time_filter: AlarmTimeFilter = "before_any_future_fault_start",
    prediction_target_source: str = "auto",
) -> tuple[List[dict], List[dict], List[dict], List[dict], List[dict], dict]:
    run_index_path = campaign_dir / "run_index.json"
    if run_index_path.exists():
        run_index = json.loads(run_index_path.read_text(encoding="utf-8"))
    else:
        run_index = []
        for manifest in sorted(campaign_dir.glob("*/manifest.json")):
            run_index.append(json.loads(manifest.read_text(encoding="utf-8")))
    rows: List[dict] = []
    rollups: dict[tuple[str, str], list[PredictionSummary]] = {}
    rollup_meta: dict[tuple[str, str], dict] = {}
    stratified: dict[tuple[str, str], list[PredictionSummary]] = {}
    stratified_meta: dict[tuple[str, str], dict] = {}
    failed_runs: List[dict] = []

    for run in run_index:
        run_id = str(run["run_id"])
        run_dir = campaign_dir / run_id
        fault_id = str(run["fault_id"])
        variant = str(run["variant"])
        pending_window_s = float(run["pending_window_s"])
        run_status = str(run.get("run_status", "completed"))
        if run_status != "completed":
            failed_runs.append(
                {
                    "run_id": run_id,
                    "variant": variant,
                    "fault_id": fault_id,
                    "fault_family": str(run.get("fault_family", "")),
                    "run_status": run_status,
                    "failed_phase": str(run.get("failed_phase", "")),
                    "failure_reason": str(run.get("failure_reason", "")),
                }
            )
            continue
        learner_env = run.get("learner_env", {}) if isinstance(run.get("learner_env", {}), dict) else {}
        poll_sec = _safe_float(learner_env.get("POLL_SEC", 2.0), 2.0)
        run_events_path = run_dir / "run_events.jsonl"
        windows, pred_src_label, timeline = build_evaluation_fault_windows(
            run_events_path,
            fallback_fault_id=fault_id,
            run_id=run_id,
            target_source=prediction_target_source,
        )
        alarms = build_alarms(run_dir / "artifacts" / "anomaly_events.jsonl", run_id=run_id, fault_id=fault_id)
        summary = evaluate_predictions(
            alarms=alarms,
            fault_windows=windows,
            pending_window_s=pending_window_s,
            matching_mode=matching_mode,
            alarm_time_filter=alarm_time_filter,
            post_bootstrap_ts=timeline.get("post_bootstrap_ts"),
            normal_window_end_ts=timeline.get("fault_on_ts"),
            poll_sec=poll_sec,
            prediction_target_source=pred_src_label,
        )
        artifacts_dir = run_dir / "artifacts"
        anomaly_path = artifacts_dir / "anomaly_events.jsonl"
        coverage = analyze_feature_coverage(anomaly_path, str(run.get("fault_family", "")))
        som_stats = summarize_som_npz(artifacts_dir / "som_model.npz", anomaly_events_path=anomaly_path)
        bootstrap_s = _safe_float(run.get("durations_s", {}).get("bootstrap", 0), 0.0) if isinstance(run.get("durations_s"), dict) else 0.0
        # Poll slots available during the logged bootstrap phase only (matrix schedule), not learner-reported counts.
        expected_bootstrap_vectors = int(max(0.0, bootstrap_s / max(0.01, poll_sec)))
        train_mode = str(run.get("train_mode", "warm_start"))
        bootstrap_target = int(_safe_float(learner_env.get("BOOTSTRAP_SAMPLES", 180), 180))
        effective_bootstrap_vectors = expected_bootstrap_vectors if train_mode == "fresh_bootstrap" else max(0, expected_bootstrap_vectors)
        study_scope = str(run.get("study_scope", "extended"))
        hypothesis_id = str(run.get("hypothesis_id", "")).lower()
        is_focused = "focused" in hypothesis_id
        required_vectors = max(bootstrap_target, 300) if is_focused else bootstrap_target
        schedule_bootstrap_polls_ok = bool(
            effective_bootstrap_vectors >= required_vectors if train_mode == "fresh_bootstrap" else effective_bootstrap_vectors >= 1
        )
        lb_m = run.get("learner_status_post_bootstrap")
        lb_m = lb_m if isinstance(lb_m, dict) else {}
        m_bs = lb_m.get("bootstrap_samples")
        m_bt = lb_m.get("bootstrap_target")
        manifest_bootstrap_samples = ""
        if m_bs is not None:
            try:
                manifest_bootstrap_samples = int(float(m_bs))
            except (TypeError, ValueError):
                manifest_bootstrap_samples = ""
        manifest_bootstrap_target = ""
        if m_bt is not None:
            try:
                manifest_bootstrap_target = int(float(m_bt))
            except (TypeError, ValueError):
                manifest_bootstrap_target = ""
        if manifest_bootstrap_samples != "" and manifest_bootstrap_target != "":
            learner_bootstrap_collected_ok = bool(manifest_bootstrap_samples >= manifest_bootstrap_target)
        else:
            learner_bootstrap_collected_ok = ""
        record = {
            "run_id": run_id,
            "variant": variant,
            "fault_id": fault_id,
            "fault_family": run["fault_family"],
            "study_scope": str(run.get("study_scope", "extended")),
            "ablation_block": str(run.get("ablation_block", "fault")),
            "hypothesis_id": str(run.get("hypothesis_id", "H0")),
            "interpretation_note": str(run.get("interpretation_note", "")),
            "faithfulness_label": infer_faithfulness_label(run),
            "intensity_level": str(run.get("intensity_level", "base")),
            "duration_level": str(run.get("duration_level", "base")),
            "pending_level": str(run.get("pending_level", "base")),
            "train_mode": train_mode,
            "repeat_idx": run["repeat_idx"],
            "seed_idx": int(_safe_float(run.get("seed_idx", 1), 1)),
            "run_seed": int(_safe_float(run.get("run_seed", 0), 0)),
            "loadgen_seed": int(_safe_float(run.get("loadgen_seed", 0), 0)),
            "tp": summary.tp,
            "fp": summary.fp,
            "fn": summary.fn,
            "tn": summary.tn,
            "tpr": summary.tpr,
            "fpr": summary.fpr,
            "precision": summary.precision,
            "recall": summary.recall,
            "f1": summary.f1,
            "mean_lead_time_s": summary.mean_lead_time_s,
            "median_lead_time_s": summary.median_lead_time_s,
            "num_scored_alarms": summary.num_scored_alarms,
            "pending_window_s": summary.pending_window_s,
            "alarm_fp_fraction": summary.alarm_fp_fraction,
            "paper_af": summary.paper_af,
            "paper_at": summary.paper_at,
            "paper_ntn": summary.paper_ntn,
            "paper_nfp": summary.paper_nfp,
            "normal_window_ticks": summary.normal_window_ticks,
            "num_alarms_before_fault_on": summary.num_alarms_before_first_target,
            "prediction_target_eval": pred_src_label,
            "alarm_time_filter": str(alarm_time_filter),
            "post_bootstrap_ts": timeline.get("post_bootstrap_ts"),
            "fault_on_ts": timeline.get("fault_on_ts"),
            "slo_proxy_ts": timeline.get("slo_proxy_ts"),
            "anomaly_quantile_level": str(run.get("anomaly_quantile_level", "base")),
            "som_smooth_k": str(learner_env.get("SOM_SMOOTH_K", "")),
            "anomaly_streak": str(learner_env.get("ANOMALY_STREAK", "")),
            "anomaly_quantile": str(learner_env.get("ANOMALY_QUANTILE", "")),
            "som_kfold": str(learner_env.get("SOM_KFOLD", "")),
            "som_rows": str(learner_env.get("SOM_ROWS", "")),
            "som_cols": str(learner_env.get("SOM_COLS", "")),
            "som_lr": str(learner_env.get("SOM_LR", "")),
            "som_sigma": str(learner_env.get("SOM_SIGMA", "")),
            "poll_sec": poll_sec,
            "bootstrap_target": bootstrap_target,
            "expected_bootstrap_vectors": expected_bootstrap_vectors,
            "effective_bootstrap_vectors": effective_bootstrap_vectors,
            "required_bootstrap_vectors": required_vectors,
            # bootstrap_vectors_ok: legacy name = schedule-only check (poll budget vs BOOTSTRAP_SAMPLES).
            "bootstrap_vectors_ok": schedule_bootstrap_polls_ok,
            "schedule_bootstrap_polls_ok": schedule_bootstrap_polls_ok,
            "manifest_bootstrap_samples": manifest_bootstrap_samples,
            "manifest_bootstrap_target": manifest_bootstrap_target,
            "learner_bootstrap_collected_ok": learner_bootstrap_collected_ok,
            "coverage_ok": bool(coverage["coverage_ok"]),
            "observability_limited": bool(coverage["observability_limited"]),
            "top_feature": str(coverage["top_feature"]),
            "top_effect_size": float(coverage["top_effect_size"]),
            "degenerate_features": ",".join(coverage["degenerate_features"]),
            "normal_variance_score": float(coverage["normal_variance_score"]),
            "matching_mode": str(matching_mode),
        }
        record.update(som_stats)
        rows.append(record)
        rollup_key = (variant, fault_id)
        rollups.setdefault(rollup_key, []).append(summary)
        rollup_meta.setdefault(
            rollup_key,
            {
                "fault_family": str(run.get("fault_family", "")),
                "study_scope": str(run.get("study_scope", "extended")),
                "ablation_block": str(run.get("ablation_block", "fault")),
                "hypothesis_id": str(run.get("hypothesis_id", "H0")),
                "faithfulness_label": infer_faithfulness_label(run),
            },
        )

        strat_groups = [
            ("fault_family", str(run.get("fault_family", "unknown"))),
            ("study_scope", str(run.get("study_scope", "extended"))),
            ("ablation_block", str(run.get("ablation_block", "fault"))),
            ("variant_fault_family", f"{variant}|{str(run.get('fault_family', 'unknown'))}"),
        ]
        for gtype, gname in strat_groups:
            k = (gtype, gname)
            stratified.setdefault(k, []).append(summary)
            stratified_meta.setdefault(k, {"group_type": gtype, "group_name": gname})

    rollup_rows: List[dict] = []
    for (variant, fault_id), metrics in sorted(rollups.items()):
        n = len(metrics)
        merged = {
            "variant": variant,
            "fault_id": fault_id,
            "n_runs": n,
        }
        merged.update(rollup_meta[(variant, fault_id)])
        merged.update(_aggregate_numeric(metrics))
        rollup_rows.append(merged)

    strat_rows: List[dict] = []
    for key, metrics in sorted(stratified.items()):
        gmeta = stratified_meta[key]
        row = {
            "group_type": gmeta["group_type"],
            "group_name": gmeta["group_name"],
            "n_runs": len(metrics),
        }
        row.update(_aggregate_numeric(metrics))
        strat_rows.append(row)

    deltas: List[dict] = []
    keyed_rollups = {(r["variant"], r["fault_id"]): r for r in rollup_rows}
    all_faults = sorted({r["fault_id"] for r in rollup_rows})
    anchor_candidates = ("paper_fidelity", "paper_fidelity_anchor")
    for fault in all_faults:
        anchor = None
        anchor_name = ""
        for candidate in anchor_candidates:
            anchor = keyed_rollups.get((candidate, fault))
            if anchor:
                anchor_name = candidate
                break
        if not anchor:
            continue
        for row in rollup_rows:
            if row["fault_id"] != fault:
                continue
            if row["variant"] == anchor_name:
                continue
            deltas.append(
                {
                    "fault_id": fault,
                    "variant": row["variant"],
                    "anchor_variant": anchor_name,
                    "delta_mean_tpr": float(row["mean_tpr"] - anchor["mean_tpr"]),
                    "delta_mean_fpr": float(row["mean_fpr"] - anchor["mean_fpr"]),
                    "delta_mean_precision": float(row["mean_precision"] - anchor["mean_precision"]),
                    "delta_mean_recall": float(row["mean_recall"] - anchor["mean_recall"]),
                    "delta_mean_f1": float(row["mean_f1"] - anchor["mean_f1"]),
                    "delta_mean_lead_time_s": float(row["mean_lead_time_s"] - anchor["mean_lead_time_s"]),
                }
            )

    campaign_meta_path = campaign_dir / "campaign_meta.json"
    if campaign_meta_path.exists():
        campaign_meta = json.loads(campaign_meta_path.read_text(encoding="utf-8"))
    else:
        campaign_meta = {}
    return rows, rollup_rows, strat_rows, deltas, failed_runs, campaign_meta


def write_csv(path: Path, rows: List[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _binom_two_sided_sign_pvalue(n: int, k_pos: int) -> float:
    if n <= 0:
        return 1.0
    k = min(k_pos, n - k_pos)
    p = 0.0
    for i in range(0, k + 1):
        p += math.comb(n, i) * (0.5 ** n)
    return float(min(1.0, 2.0 * p))


def _bh_adjust(rows: List[dict], pvalue_key: str, out_key: str) -> None:
    indexed: List[Tuple[int, float]] = []
    for idx, row in enumerate(rows):
        p = _safe_float(row.get(pvalue_key, 1.0), 1.0)
        indexed.append((idx, max(0.0, min(1.0, p))))
    if not indexed:
        return
    indexed.sort(key=lambda item: item[1])
    m = len(indexed)
    adjusted_sorted: List[float] = [1.0] * m
    running = 1.0
    for rank in range(m - 1, -1, -1):
        _idx, p = indexed[rank]
        q = min(1.0, (p * m) / (rank + 1))
        running = min(running, q)
        adjusted_sorted[rank] = running
    for rank, (row_idx, _p) in enumerate(indexed):
        rows[row_idx][out_key] = adjusted_sorted[rank]


def build_paired_significance(run_rows: List[dict], anchor_variant: str = "paper_fidelity") -> List[dict]:
    variants_present = {str(r.get("variant", "")) for r in run_rows}
    if anchor_variant not in variants_present and "paper_fidelity_anchor" in variants_present:
        anchor_variant = "paper_fidelity_anchor"
    grouped: Dict[Tuple[str, str], Dict[str, dict]] = {}
    for row in run_rows:
        key = (str(row.get("fault_id", "")), str(row.get("repeat_idx", "")))
        grouped.setdefault(key, {})[str(row.get("variant", ""))] = row

    metric_keys = (
        ("f1", "delta_f1"),
        ("tpr", "delta_tpr"),
        ("fpr", "delta_fpr"),
        ("mean_lead_time_s", "delta_lead_time_s"),
    )
    deltas: Dict[Tuple[str, str], Dict[str, List[float]]] = {}
    for (fault_id, _repeat), variants in grouped.items():
        anchor = variants.get(anchor_variant)
        if not anchor:
            continue
        for variant, row in variants.items():
            if variant == anchor_variant:
                continue
            bucket = deltas.setdefault((fault_id, variant), {dst: [] for _, dst in metric_keys})
            for src, dst in metric_keys:
                d = float(_safe_float(row.get(src, 0.0)) - _safe_float(anchor.get(src, 0.0)))
                bucket.setdefault(dst, []).append(d)

    out: List[dict] = []
    for (fault_id, variant), metric_deltas in sorted(deltas.items()):
        vals_f1 = metric_deltas.get("delta_f1", [])
        n = len(vals_f1)
        k_pos_f1 = sum(1 for x in vals_f1 if x > 0)
        p_sign_f1 = _binom_two_sided_sign_pvalue(n, k_pos_f1)
        ci_lo_f1, ci_hi_f1 = _ci95_bootstrap(vals_f1, n_boot=2000, seed=42)
        vals_tpr = metric_deltas.get("delta_tpr", [])
        vals_fpr = metric_deltas.get("delta_fpr", [])
        vals_lead = metric_deltas.get("delta_lead_time_s", [])
        p_sign_tpr = _binom_two_sided_sign_pvalue(len(vals_tpr), sum(1 for x in vals_tpr if x > 0))
        p_sign_fpr = _binom_two_sided_sign_pvalue(len(vals_fpr), sum(1 for x in vals_fpr if x < 0))
        p_sign_lead = _binom_two_sided_sign_pvalue(len(vals_lead), sum(1 for x in vals_lead if x > 0))
        ci_lo_tpr, ci_hi_tpr = _ci95_bootstrap(vals_tpr, n_boot=2000, seed=42)
        ci_lo_fpr, ci_hi_fpr = _ci95_bootstrap(vals_fpr, n_boot=2000, seed=42)
        ci_lo_lead, ci_hi_lead = _ci95_bootstrap(vals_lead, n_boot=2000, seed=42)
        out.append(
            {
                "fault_id": fault_id,
                "variant": variant,
                "anchor_variant": anchor_variant,
                "n_pairs": n,
                "mean_delta_f1": _mean(vals_f1),
                "ci95_low_delta_f1": ci_lo_f1,
                "ci95_high_delta_f1": ci_hi_f1,
                "sign_test_pvalue_f1": p_sign_f1,
                "n_positive_delta_f1": k_pos_f1,
                "mean_delta_tpr": _mean(vals_tpr),
                "ci95_low_delta_tpr": ci_lo_tpr,
                "ci95_high_delta_tpr": ci_hi_tpr,
                "sign_test_pvalue_tpr": p_sign_tpr,
                "n_positive_delta_tpr": sum(1 for x in vals_tpr if x > 0),
                "mean_delta_fpr": _mean(vals_fpr),
                "ci95_low_delta_fpr": ci_lo_fpr,
                "ci95_high_delta_fpr": ci_hi_fpr,
                "sign_test_pvalue_fpr": p_sign_fpr,
                "n_negative_delta_fpr": sum(1 for x in vals_fpr if x < 0),
                "mean_delta_lead_time_s": _mean(vals_lead),
                "ci95_low_delta_lead_time_s": ci_lo_lead,
                "ci95_high_delta_lead_time_s": ci_hi_lead,
                "sign_test_pvalue_lead_time_s": p_sign_lead,
                "n_positive_delta_lead_time_s": sum(1 for x in vals_lead if x > 0),
            }
        )
    _bh_adjust(out, "sign_test_pvalue_f1", "sign_test_pvalue_f1_bh")
    _bh_adjust(out, "sign_test_pvalue_tpr", "sign_test_pvalue_tpr_bh")
    _bh_adjust(out, "sign_test_pvalue_fpr", "sign_test_pvalue_fpr_bh")
    _bh_adjust(out, "sign_test_pvalue_lead_time_s", "sign_test_pvalue_lead_time_s_bh")
    return out


def build_fidelity_checks(
    campaign_meta: dict,
    run_rows: List[dict],
    rollup_rows: List[dict],
    *,
    paper_style_replay_row_count: int = 0,
    paper_pending_windows_evaluated: Sequence[float] | None = None,
) -> dict:
    poll_values = sorted({float(_safe_float(r.get("poll_sec", 2.0), 2.0)) for r in run_rows})
    quantile_values = sorted({str(r.get("anomaly_quantile", "")) for r in run_rows if str(r.get("anomaly_quantile", ""))})
    pending_values = sorted({float(_safe_float(r.get("pending_window_s", 0.0), 0.0)) for r in run_rows})
    extra_pw = sorted({float(x) for x in (paper_pending_windows_evaluated or [])})
    variants = sorted({str(r.get("variant", "")) for r in run_rows})
    fault_families = sorted({str(r.get("fault_family", "")) for r in run_rows if str(r.get("fault_family", ""))})
    intensity_levels = sorted({str(r.get("intensity_level", "")) for r in run_rows if str(r.get("intensity_level", ""))})
    duration_levels = sorted({str(r.get("duration_level", "")) for r in run_rows if str(r.get("duration_level", ""))})
    matching_modes = sorted({str(r.get("matching_mode", "")) for r in run_rows if str(r.get("matching_mode", ""))})
    has_pca_knn = any(v.lower().startswith("pca") or v.lower().startswith("knn") for v in variants)
    comparator_scope = str(campaign_meta.get("comparator_scope", "")).strip()
    return {
        "campaign_id": campaign_meta.get("campaign_id", ""),
        "checks": {
            "sampling_interval_has_1s": any(abs(v - 1.0) < 1e-6 for v in poll_values),
            "sampling_intervals_seen": poll_values,
            "som_param_variants_present": bool(any(str(r.get("som_lr", "")) or str(r.get("som_sigma", "")) for r in run_rows)),
            "threshold_percentile_sweep_present": len(quantile_values) > 1 or paper_style_replay_row_count > 0,
            "threshold_percentiles_seen": quantile_values,
            "pending_window_sweep_present": len(pending_values) > 1 or len(set(extra_pw)) > 1,
            "pending_windows_seen": pending_values,
            "paper_pending_windows_evaluated": extra_pw,
            "paper_style_threshold_replay_rows": int(paper_style_replay_row_count),
            "paper_style_threshold_replay_ran": paper_style_replay_row_count > 0,
            "pca_or_knn_comparator_present": has_pca_knn,
            "comparator_scope_declared": comparator_scope,
            "fault_family_coverage": fault_families,
            "fault_family_core_present": all(x in fault_families for x in ("paper_aligned", "extended")),
            "intensity_ladder_levels_seen": intensity_levels,
            "duration_ladder_levels_seen": duration_levels,
            "matching_modes_seen": matching_modes,
        },
        "notes": [
            "If pca_or_knn_comparator_present is false, mark comparator scope as not included.",
            "If sampling_interval_has_1s is false, include explicit sensitivity statement in paper-fidelity section.",
        ],
        "faithfulness_label_distribution": {
            "paper-faithful": sum(1 for r in rollup_rows if str(r.get("faithfulness_label", "")) == "paper-faithful"),
            "paper-faithful-with-proxy": sum(1 for r in rollup_rows if str(r.get("faithfulness_label", "")) == "paper-faithful-with-proxy"),
            "extended-beyond-paper": sum(1 for r in rollup_rows if str(r.get("faithfulness_label", "")) == "extended-beyond-paper"),
        },
    }


def build_validity_ledger(campaign_meta: dict, run_rows: List[dict]) -> dict:
    labels = sorted({str(r.get("faithfulness_label", "")) for r in run_rows if str(r.get("faithfulness_label", ""))})
    scopes = sorted({str(r.get("study_scope", "")) for r in run_rows if str(r.get("study_scope", ""))})
    families = sorted({str(r.get("fault_family", "")) for r in run_rows if str(r.get("fault_family", ""))})
    return {
        "campaign_id": campaign_meta.get("campaign_id", ""),
        "faithfulness_labels_present": labels,
        "study_scopes_present": scopes,
        "fault_families_present": families,
        "construct_validity": [
            "Network and system faults are proxy implementations in a Docker lab (for example Toxiproxy latency/bandwidth/reset for net-hog-like behaviors).",
            "Fault injections represent causal stressors but are not byte-for-byte reproductions of Xen/VCL paper infrastructure.",
        ],
        "internal_validity": [
            "SOM initialization and runtime behavior can vary by random state; repeat counts and confidence intervals should be used for claims.",
            "Campaign reproducibility depends on fixed matrix settings, recorded learner env, and consistent host/container runtime.",
        ],
        "external_validity": [
            "Results generalize to this containerized proxy environment first; portability to production cloud stacks requires re-validation.",
            "Workload shape and resource constraints in this lab may differ from real deployments.",
        ],
        "metric_validity": [
            "Pending-window scoring (W) is an operational proxy for prediction success and should be sensitivity-tested.",
            "Legacy column fpr equals alarm_fp_fraction = fp/(fp+tp) from the old TN proxy (not UBL Eq.5 AF); compare to the paper using paper_af and paper_at.",
            "paper_af uses Nfp/(Nfp+Ntn) with Ntn approximated from pre-injection poll ticks minus pre-injection alarms (see ubl_metrics._paper_ntn_ticks).",
            "prediction_target_eval selects t2 as slo_violation_proxy when prediction_target events exist, else fault injection onset.",
            "Offline --paper-roc-replay uses ubl_train_scores in som_model.npz plus artifacts/score_stream.jsonl (new runs); legacy campaigns lack these and replay_ok will be false.",
            "Feature observability may differ by fault family; consult coverage_ok and observability_limited fields.",
            "bootstrap_vectors_ok and schedule_bootstrap_polls_ok are identical: they compare floor(bootstrap_s/poll_sec) to BOOTSTRAP_SAMPLES (matrix schedule), not learner-collected normal samples. Use manifest_bootstrap_samples and learner_bootstrap_collected_ok from the run manifest when present.",
        ],
        "paper_faithfulness_policy": {
            "paper-faithful": "Only when both configuration and environment are direct paper matches (rare in this repo).",
            "paper-faithful-with-proxy": "Paper-aligned learner settings with practical proxy fault mappings.",
            "extended-beyond-paper": "Any non-paper learner mode, fault set, or ablation beyond replication scope.",
        },
    }


def build_roc_points(run_rows: List[dict]) -> List[dict]:
    grouped: Dict[Tuple[str, str, str], List[dict]] = {}
    for row in run_rows:
        fault_id = str(row.get("fault_id", ""))
        variant = str(row.get("variant", ""))
        quantile = str(row.get("anomaly_quantile", ""))
        if not fault_id or not variant or not quantile:
            continue
        grouped.setdefault((fault_id, variant, quantile), []).append(row)
    out: List[dict] = []
    for (fault_id, variant, quantile), rows in sorted(grouped.items()):
        out.append(
            {
                "fault_id": fault_id,
                "variant": variant,
                "anomaly_quantile": quantile,
                "n_runs": len(rows),
                "mean_tpr": _mean([_safe_float(r.get("tpr", 0.0), 0.0) for r in rows]),
                "mean_fpr": _mean([_safe_float(r.get("fpr", 0.0), 0.0) for r in rows]),
                "mean_alarm_fp_fraction": _mean([_safe_float(r.get("alarm_fp_fraction", 0.0), 0.0) for r in rows]),
                "mean_paper_af": _mean([_safe_float(r.get("paper_af", 0.0), 0.0) for r in rows]),
                "mean_paper_at": _mean([_safe_float(r.get("paper_at", 0.0), 0.0) for r in rows]),
                "mean_precision": _mean([_safe_float(r.get("precision", 0.0), 0.0) for r in rows]),
                "mean_recall": _mean([_safe_float(r.get("recall", 0.0), 0.0) for r in rows]),
                "mean_f1": _mean([_safe_float(r.get("f1", 0.0), 0.0) for r in rows]),
            }
        )
    return out


def load_run_index(campaign_dir: Path) -> List[dict]:
    p = campaign_dir / "run_index.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def build_pending_window_sensitivity_rows(
    campaign_dir: Path,
    run_index: List[dict],
    pending_windows: Sequence[float],
    prediction_target_source: str,
    matching_mode: str,
    alarm_time_filter: AlarmTimeFilter,
) -> List[dict]:
    rows_out: List[dict] = []
    for run in run_index:
        if str(run.get("run_status", "")) != "completed":
            continue
        run_id = str(run["run_id"])
        run_dir = campaign_dir / run_id
        fault_id = str(run["fault_id"])
        variant = str(run.get("variant", ""))
        learner_env = run.get("learner_env", {}) if isinstance(run.get("learner_env"), dict) else {}
        poll_sec = _safe_float(learner_env.get("POLL_SEC", 2.0), 2.0)
        run_events_path = run_dir / "run_events.jsonl"
        windows, pred_src_label, timeline = build_evaluation_fault_windows(
            run_events_path,
            fallback_fault_id=fault_id,
            run_id=run_id,
            target_source=prediction_target_source,
        )
        alarms = build_alarms(run_dir / "artifacts" / "anomaly_events.jsonl", run_id=run_id, fault_id=fault_id)
        for w in pending_windows:
            summary = evaluate_predictions(
                alarms=alarms,
                fault_windows=windows,
                pending_window_s=float(w),
                matching_mode=matching_mode,
                alarm_time_filter=alarm_time_filter,
                post_bootstrap_ts=timeline.get("post_bootstrap_ts"),
                normal_window_end_ts=timeline.get("fault_on_ts"),
                poll_sec=poll_sec,
                prediction_target_source=pred_src_label,
            )
            rows_out.append(
                {
                    "run_id": run_id,
                    "variant": variant,
                    "fault_id": fault_id,
                    "pending_window_s": float(w),
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
                    "prediction_target_eval": pred_src_label,
                    "num_alarms_before_fault_on": summary.num_alarms_before_first_target,
                }
            )
    return rows_out


def build_paper_roc_replay_rows(
    campaign_dir: Path,
    run_index: List[dict],
    quantiles: Sequence[float],
    matching_mode: str,
    alarm_time_filter: AlarmTimeFilter,
    prediction_target_source: str,
) -> List[dict]:
    out: List[dict] = []
    for run in run_index:
        if str(run.get("run_status", "")) != "completed":
            continue
        run_id = str(run["run_id"])
        run_dir = campaign_dir / run_id
        if not run_dir.is_dir():
            continue
        fault_id = str(run["fault_id"])
        learner_env = run.get("learner_env", {}) if isinstance(run.get("learner_env"), dict) else {}
        poll_sec = _safe_float(learner_env.get("POLL_SEC", 2.0), 2.0)
        run_events_path = run_dir / "run_events.jsonl"
        windows, pred_src_label, timeline = build_evaluation_fault_windows(
            run_events_path,
            fallback_fault_id=fault_id,
            run_id=run_id,
            target_source=prediction_target_source,
        )
        pending_window_s = float(run.get("pending_window_s", 60.0))
        out.extend(
            ubl_roc_replay.replay_run_quantiles(
                run_dir=run_dir,
                run_row=run,
                fault_windows=windows,
                pred_src_label=pred_src_label,
                timeline=timeline,
                poll_sec=poll_sec,
                quantiles=quantiles,
                matching_mode=matching_mode,
                pending_window_s=pending_window_s,
                alarm_time_filter=alarm_time_filter,
            )
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate fault-injection campaign outputs")
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument(
        "--matching-mode",
        choices=["many_to_many", "one_to_one"],
        default="many_to_many",
        help="Alarm/fault matching semantics for TP/FP/FN accounting.",
    )
    parser.add_argument(
        "--alarm-time-filter",
        choices=["all", "before_any_future_fault_start"],
        default="before_any_future_fault_start",
        help="Drop post-onset streaming alarms before alarm-level TP/FP (paper-style prediction events).",
    )
    parser.add_argument(
        "--prediction-target-source",
        choices=["auto", "injection_onset", "slo_proxy"],
        default="auto",
        help="Which timestamp to use as t2 for pending-window matching (auto uses SLO proxy events when present).",
    )
    parser.add_argument(
        "--paper-roc-replay",
        action="store_true",
        help="Sweep score quantiles using score_stream.jsonl + ubl_train_scores (paper §3.2.1 style; no extra Docker runs).",
    )
    parser.add_argument("--paper-roc-q-start", type=float, default=0.70)
    parser.add_argument("--paper-roc-q-end", type=float, default=0.98)
    parser.add_argument("--paper-roc-q-step", type=float, default=0.02)
    parser.add_argument(
        "--paper-pending-windows",
        type=str,
        default="",
        help="Comma-separated W values in seconds for sensitivity analysis on logged alarms (e.g. 45,60,90,120).",
    )
    args = parser.parse_args()

    out_dir = args.out_dir or (args.campaign_dir / "evaluation")
    out_dir.mkdir(parents=True, exist_ok=True)
    alarm_tf: AlarmTimeFilter = "before_any_future_fault_start"
    if str(args.alarm_time_filter) == "all":
        alarm_tf = "all"
    run_rows, rollup_rows, strat_rows, delta_rows, failed_rows, campaign_meta = summarize_campaign(
        args.campaign_dir,
        matching_mode=str(args.matching_mode),
        alarm_time_filter=alarm_tf,
        prediction_target_source=str(args.prediction_target_source),
    )

    write_csv(out_dir / "run_metrics.csv", run_rows)
    write_csv(out_dir / "rollup_metrics.csv", rollup_rows)
    write_csv(out_dir / "stratified_rollup_metrics.csv", strat_rows)
    write_csv(out_dir / "delta_vs_paper_fidelity.csv", delta_rows)
    write_csv(out_dir / "failed_runs.csv", failed_rows)
    som_rollup = build_som_rollup(run_rows)
    write_csv(out_dir / "som_rollup_metrics.csv", som_rollup)
    paired = build_paired_significance(run_rows, anchor_variant="paper_fidelity")
    write_csv(out_dir / "paired_significance.csv", paired)
    roc_points = build_roc_points(run_rows)
    write_csv(out_dir / "roc_points.csv", roc_points)

    run_index_full = load_run_index(args.campaign_dir)
    pending_ws_parsed: List[float] = []
    for part in str(args.paper_pending_windows).split(","):
        part = part.strip()
        if not part:
            continue
        pending_ws_parsed.append(float(part))

    pend_sens_rows: List[dict] = []
    if pending_ws_parsed:
        pend_sens_rows = build_pending_window_sensitivity_rows(
            args.campaign_dir,
            run_index_full,
            pending_ws_parsed,
            str(args.prediction_target_source),
            str(args.matching_mode),
            alarm_tf,
        )
        write_csv(out_dir / "pending_window_sensitivity.csv", pend_sens_rows)

    replay_rows: List[dict] = []
    replay_rollup: List[dict] = []
    if args.paper_roc_replay:
        qgrid = ubl_roc_replay.quantile_grid(
            float(args.paper_roc_q_start),
            float(args.paper_roc_q_end),
            float(args.paper_roc_q_step),
        )
        replay_rows = build_paper_roc_replay_rows(
            args.campaign_dir,
            run_index_full,
            qgrid,
            str(args.matching_mode),
            alarm_tf,
            str(args.prediction_target_source),
        )
        write_csv(out_dir / "paper_roc_replay_by_run.csv", replay_rows)
        replay_rollup = ubl_roc_replay.aggregate_replay_rollup(replay_rows)
        write_csv(out_dir / "paper_roc_replay_rollup.csv", replay_rollup)

    replay_ok_count = sum(1 for r in replay_rows if r.get("replay_ok"))
    fidelity_checks = build_fidelity_checks(
        campaign_meta,
        run_rows,
        rollup_rows,
        paper_style_replay_row_count=replay_ok_count,
        paper_pending_windows_evaluated=pending_ws_parsed,
    )
    with (out_dir / "fidelity_checks.json").open("w", encoding="utf-8") as f:
        json.dump(fidelity_checks, f, indent=2, sort_keys=True)
    validity = build_validity_ledger(campaign_meta, run_rows)
    with (out_dir / "validity_ledger.json").open("w", encoding="utf-8") as f:
        json.dump(validity, f, indent=2, sort_keys=True)
    with (out_dir / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(
            {
                "campaign_meta": campaign_meta,
                "run_metrics": run_rows,
                "rollup_metrics": rollup_rows,
                "stratified_rollup_metrics": strat_rows,
                "delta_vs_paper_fidelity": delta_rows,
                "paired_significance": paired,
                "roc_points": roc_points,
                "paper_roc_replay_by_run": replay_rows,
                "paper_roc_replay_rollup": replay_rollup,
                "pending_window_sensitivity": pend_sens_rows,
                "failed_runs": failed_rows,
                "som_rollup_metrics": som_rollup,
                "fidelity_checks": fidelity_checks,
                "validity_ledger": validity,
                "matching_mode": str(args.matching_mode),
            },
            f,
            indent=2,
            sort_keys=True,
        )

    if args.matching_mode == "many_to_many":
        alt_run_rows, alt_rollup_rows, _alt_strat, _alt_delta, _alt_failed, _alt_meta = summarize_campaign(
            args.campaign_dir,
            matching_mode="one_to_one",
            alarm_time_filter=alarm_tf,
            prediction_target_source=str(args.prediction_target_source),
        )
        write_csv(out_dir / "run_metrics_one_to_one.csv", alt_run_rows)
        write_csv(out_dir / "rollup_metrics_one_to_one.csv", alt_rollup_rows)

    print(f"Wrote evaluation artifacts to: {out_dir}")


if __name__ == "__main__":
    main()
