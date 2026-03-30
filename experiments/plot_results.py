from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def read_csv(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def to_float(row: dict, key: str) -> float:
    try:
        return float(row.get(key, 0.0))
    except Exception:
        return 0.0


def to_int(row: dict, key: str) -> int:
    try:
        return int(float(row.get(key, 0)))
    except Exception:
        return 0


def sanitize_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value.strip())


def write_sidecar(path: Path, rows: Iterable[dict]) -> None:
    rows = list(rows)
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def save_figure(fig: plt.Figure, stem: str, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg", "pdf"):
        fig.savefig(out_dir / f"{stem}.{ext}", bbox_inches="tight", dpi=180)
    plt.close(fig)


def grouped_bars(
    rows: List[dict],
    y_key: str,
    title: str,
    ylabel: str,
    stem: str,
    out_dir: Path,
    err_low_key: str = "",
    err_high_key: str = "",
) -> None:
    if not rows:
        return
    faults = sorted({r["fault_id"] for r in rows})
    variants = sorted({r["variant"] for r in rows})
    width = 0.8 / max(1, len(variants))
    x = list(range(len(faults)))
    fig, ax = plt.subplots(figsize=(max(8, len(faults) * 1.2), 5))
    for idx, variant in enumerate(variants):
        ys = []
        errs = []
        for fault in faults:
            row = next((r for r in rows if r["fault_id"] == fault and r["variant"] == variant), None)
            row = row or {}
            y = to_float(row, y_key)
            ys.append(y)
            if err_low_key and err_high_key:
                lo = to_float(row, err_low_key)
                hi = to_float(row, err_high_key)
                errs.append(max(0.0, max(y - lo, hi - y)))
        x_shifted = [v - 0.4 + width / 2 + idx * width for v in x]
        kwargs = {"width": width, "label": variant}
        if errs:
            kwargs["yerr"] = errs
            kwargs["capsize"] = 3
        ax.bar(x_shifted, ys, **kwargs)
    ax.set_xticks(x)
    ax.set_xticklabels(faults, rotation=30, ha="right")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.legend()
    save_figure(fig, stem, out_dir)


def line_sensitivity(
    rows: List[dict],
    x_key: str,
    y_key: str,
    title: str,
    xlabel: str,
    ylabel: str,
    stem: str,
    out_dir: Path,
) -> None:
    if not rows:
        return
    # Aggregate by x and variant.
    grouped: Dict[tuple[str, str], List[float]] = {}
    for r in rows:
        x_val = str(r.get(x_key, "")).strip()
        if not x_val:
            continue
        grouped.setdefault((x_val, r["variant"]), []).append(to_float(r, y_key))
    if not grouped:
        return
    variants = sorted({k[1] for k in grouped.keys()})
    x_vals_sorted = sorted({k[0] for k in grouped.keys()}, key=lambda x: float(x) if x.replace(".", "", 1).isdigit() else x)

    fig, ax = plt.subplots(figsize=(8, 5))
    for variant in variants:
        ys = []
        for x_val in x_vals_sorted:
            vals = grouped.get((x_val, variant), [])
            ys.append(sum(vals) / max(1, len(vals)) if vals else 0.0)
        ax.plot(x_vals_sorted, ys, marker="o", label=variant)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.legend()
    save_figure(fig, stem, out_dir)


def boxplot_variability(run_rows: List[dict], metric_key: str, title: str, ylabel: str, stem: str, out_dir: Path) -> None:
    if not run_rows:
        return
    variants = sorted({r["variant"] for r in run_rows})
    series = []
    labels = []
    for v in variants:
        vals = [to_float(r, metric_key) for r in run_rows if r["variant"] == v]
        if vals:
            labels.append(v)
            series.append(vals)
    if not series:
        return
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.boxplot(series, tick_labels=labels, showmeans=True)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xticklabels(labels, rotation=20, ha="right")
    save_figure(fig, stem, out_dir)


def faithfulness_split(rollup_rows: List[dict], out_dir: Path, stem: str) -> None:
    if not rollup_rows:
        return
    labels = sorted({r.get("faithfulness_label", "unknown") for r in rollup_rows})
    mean_f1s = []
    for label in labels:
        vals = [to_float(r, "mean_f1") for r in rollup_rows if r.get("faithfulness_label", "unknown") == label]
        mean_f1s.append(sum(vals) / max(1, len(vals)))
    fig, ax = plt.subplots(figsize=(7, 4))
    xs = list(range(len(labels)))
    ax.bar(xs, mean_f1s)
    ax.set_title("Mean F1 by Faithfulness Label")
    ax.set_ylabel("Mean F1")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=20, ha="right")
    save_figure(fig, stem, out_dir)


def plot_stratified(strat_rows: List[dict], out_dir: Path, stem: str) -> None:
    if not strat_rows:
        return
    rows = [r for r in strat_rows if r.get("group_type") in {"fault_family", "study_scope", "ablation_block"}]
    rows.sort(key=lambda r: (r.get("group_type", ""), r.get("group_name", "")))
    x_labels = [f"{r.get('group_type')}:{r.get('group_name')}" for r in rows]
    xs = list(range(len(rows)))
    y_vals = [to_float(r, "mean_f1") for r in rows]
    fig, ax = plt.subplots(figsize=(max(8, len(rows) * 0.9), 5))
    ax.bar(xs, y_vals)
    ax.set_title("Stratified Mean F1")
    ax.set_ylabel("Mean F1")
    ax.set_xticks(xs)
    ax.set_xticklabels(x_labels, rotation=35, ha="right")
    save_figure(fig, stem, out_dir)


def ladder_sensitivity(run_rows: List[dict], key: str, out_dir: Path, stem: str, title: str) -> None:
    if not run_rows:
        return
    grouped: Dict[tuple[str, str], List[float]] = {}
    levels = sorted({str(r.get(key, "")) for r in run_rows if str(r.get(key, ""))})
    variants = sorted({str(r.get("variant", "")) for r in run_rows})
    if not levels or not variants:
        return
    for row in run_rows:
        level = str(row.get(key, ""))
        variant = str(row.get("variant", ""))
        if not level or not variant:
            continue
        grouped.setdefault((variant, level), []).append(to_float(row, "f1"))
    fig, ax = plt.subplots(figsize=(8, 5))
    xs = list(range(len(levels)))
    width = 0.8 / max(1, len(variants))
    for i, variant in enumerate(variants):
        ys = []
        for level in levels:
            vals = grouped.get((variant, level), [])
            ys.append(sum(vals) / max(1, len(vals)) if vals else 0.0)
        x_shifted = [x - 0.4 + width / 2 + i * width for x in xs]
        ax.bar(x_shifted, ys, width=width, label=variant)
    ax.set_xticks(xs)
    ax.set_xticklabels(levels, rotation=20, ha="right")
    ax.set_ylabel("Mean F1")
    ax.set_title(title)
    ax.legend()
    save_figure(fig, stem, out_dir)


def plot_roc_points(roc_rows: List[dict], out_dir: Path, stem: str) -> None:
    if not roc_rows:
        return
    grouped: Dict[tuple[str, str], List[dict]] = {}
    for row in roc_rows:
        key = (str(row.get("fault_id", "")), str(row.get("variant", "")))
        grouped.setdefault(key, []).append(row)
    if not grouped:
        return
    fig, ax = plt.subplots(figsize=(7, 6))
    for (fault_id, variant), rows in sorted(grouped.items()):
        rows_sorted = sorted(rows, key=lambda r: to_float(r, "mean_fpr"))
        xs = [to_float(r, "mean_fpr") for r in rows_sorted]
        ys = [to_float(r, "mean_tpr") for r in rows_sorted]
        label = f"{fault_id}:{variant}"
        ax.plot(xs, ys, marker="o", label=label)
    ax.plot([0, 1], [0, 1], linestyle="--", linewidth=1)
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title("ROC-style Points by Fault and Variant")
    ax.legend(fontsize=8)
    save_figure(fig, stem, out_dir)


def plot_paper_roc_replay(rollup_rows: List[dict], out_dir: Path, stem: str) -> None:
    if not rollup_rows:
        return
    grouped: Dict[tuple[str, str], List[dict]] = {}
    for row in rollup_rows:
        key = (str(row.get("fault_id", "")), str(row.get("variant", "")))
        grouped.setdefault(key, []).append(row)
    if not grouped:
        return
    fig, ax = plt.subplots(figsize=(7, 6))
    for (fault_id, variant), rows in sorted(grouped.items()):
        rows_sorted = sorted(rows, key=lambda r: to_float(r, "mean_paper_af"))
        xs = [to_float(r, "mean_paper_af") for r in rows_sorted]
        ys = [to_float(r, "mean_paper_at") for r in rows_sorted]
        label = f"{fault_id}:{variant}"
        ax.plot(xs, ys, marker="o", label=label)
    ax.plot([0, 1], [0, 1], linestyle="--", linewidth=1)
    ax.set_xlabel("Paper AF (Eq. 5)")
    ax.set_ylabel("Paper AT / TPR")
    ax.set_title("Offline percentile replay (ubl_train_scores + score_stream)")
    ax.legend(fontsize=8)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    save_figure(fig, stem, out_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate figure-ready charts from evaluation outputs.")
    parser.add_argument("--evaluation-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()

    evaluation_dir = args.evaluation_dir
    out_dir = args.out_dir or (evaluation_dir / "figures")
    sidecar_dir = out_dir / "data"

    rollup_rows = read_csv(evaluation_dir / "rollup_metrics.csv")
    run_rows = read_csv(evaluation_dir / "run_metrics.csv")
    strat_rows = read_csv(evaluation_dir / "stratified_rollup_metrics.csv")
    delta_rows = read_csv(evaluation_dir / "delta_vs_paper_fidelity.csv")
    roc_rows = read_csv(evaluation_dir / "roc_points.csv")
    summary = read_json(evaluation_dir / "summary.json")
    campaign_id = str(summary.get("campaign_meta", {}).get("campaign_id", "campaign"))
    campaign_slug = sanitize_name(campaign_id)

    grouped_bars(
        rollup_rows,
        y_key="mean_f1",
        title="Detection Quality (Mean F1) by Fault and Variant",
        ylabel="Mean F1",
        stem=f"{campaign_slug}_detection_quality_mean_f1",
        out_dir=out_dir,
        err_low_key="ci95_low_f1",
        err_high_key="ci95_high_f1",
    )
    write_sidecar(sidecar_dir / f"{campaign_slug}_detection_quality_mean_f1.csv", rollup_rows)

    grouped_bars(
        rollup_rows,
        y_key="mean_tpr",
        title="True Positive Rate by Fault and Variant",
        ylabel="Mean TPR",
        stem=f"{campaign_slug}_detection_quality_mean_tpr",
        out_dir=out_dir,
    )
    write_sidecar(sidecar_dir / f"{campaign_slug}_detection_quality_mean_tpr.csv", rollup_rows)

    grouped_bars(
        rollup_rows,
        y_key="mean_fpr",
        title="False Positive Rate by Fault and Variant",
        ylabel="Mean FPR",
        stem=f"{campaign_slug}_detection_quality_mean_fpr",
        out_dir=out_dir,
    )
    write_sidecar(sidecar_dir / f"{campaign_slug}_detection_quality_mean_fpr.csv", rollup_rows)

    grouped_bars(
        rollup_rows,
        y_key="mean_precision",
        title="Precision by Fault and Variant",
        ylabel="Mean Precision",
        stem=f"{campaign_slug}_detection_quality_mean_precision",
        out_dir=out_dir,
    )
    write_sidecar(sidecar_dir / f"{campaign_slug}_detection_quality_mean_precision.csv", rollup_rows)

    grouped_bars(
        rollup_rows,
        y_key="mean_recall",
        title="Recall by Fault and Variant",
        ylabel="Mean Recall",
        stem=f"{campaign_slug}_detection_quality_mean_recall",
        out_dir=out_dir,
    )
    write_sidecar(sidecar_dir / f"{campaign_slug}_detection_quality_mean_recall.csv", rollup_rows)

    grouped_bars(
        rollup_rows,
        y_key="mean_lead_time_s",
        title="Timing Quality (Mean Lead Time) by Fault and Variant",
        ylabel="Mean Lead Time (s)",
        stem=f"{campaign_slug}_timing_quality_mean_lead_time",
        out_dir=out_dir,
    )
    write_sidecar(sidecar_dir / f"{campaign_slug}_timing_quality_mean_lead_time.csv", rollup_rows)

    boxplot_variability(
        run_rows,
        metric_key="f1",
        title="Run-Level Variability: F1 by Variant",
        ylabel="F1",
        stem=f"{campaign_slug}_robustness_f1_boxplot",
        out_dir=out_dir,
    )
    write_sidecar(sidecar_dir / f"{campaign_slug}_robustness_f1_boxplot.csv", run_rows)

    line_sensitivity(
        run_rows,
        x_key="anomaly_quantile",
        y_key="f1",
        title="Sensitivity: Quantile Threshold vs F1",
        xlabel="ANOMALY_QUANTILE",
        ylabel="F1",
        stem=f"{campaign_slug}_sensitivity_quantile_f1",
        out_dir=out_dir,
    )
    line_sensitivity(
        run_rows,
        x_key="som_smooth_k",
        y_key="f1",
        title="Sensitivity: Smoothing K vs F1",
        xlabel="SOM_SMOOTH_K",
        ylabel="F1",
        stem=f"{campaign_slug}_sensitivity_smoothing_k_f1",
        out_dir=out_dir,
    )
    line_sensitivity(
        run_rows,
        x_key="anomaly_streak",
        y_key="f1",
        title="Sensitivity: Anomaly Streak Rule vs F1",
        xlabel="ANOMALY_STREAK",
        ylabel="F1",
        stem=f"{campaign_slug}_sensitivity_streak_f1",
        out_dir=out_dir,
    )
    line_sensitivity(
        run_rows,
        x_key="som_kfold",
        y_key="f1",
        title="Sensitivity: K-Fold vs F1",
        xlabel="SOM_KFOLD",
        ylabel="F1",
        stem=f"{campaign_slug}_sensitivity_kfold_f1",
        out_dir=out_dir,
    )
    line_sensitivity(
        run_rows,
        x_key="som_rows",
        y_key="f1",
        title="Sensitivity: SOM Rows vs F1",
        xlabel="SOM_ROWS",
        ylabel="F1",
        stem=f"{campaign_slug}_sensitivity_som_rows_f1",
        out_dir=out_dir,
    )
    write_sidecar(sidecar_dir / f"{campaign_slug}_sensitivity_source_run_metrics.csv", run_rows)

    faithfulness_split(
        rollup_rows,
        out_dir=out_dir,
        stem=f"{campaign_slug}_faithfulness_split_mean_f1",
    )
    plot_stratified(
        strat_rows,
        out_dir=out_dir,
        stem=f"{campaign_slug}_stratified_mean_f1",
    )
    ladder_sensitivity(
        run_rows,
        key="intensity_level",
        out_dir=out_dir,
        stem=f"{campaign_slug}_intensity_ladder_mean_f1",
        title="Intensity Ladder Sensitivity (Mean F1)",
    )
    ladder_sensitivity(
        run_rows,
        key="duration_level",
        out_dir=out_dir,
        stem=f"{campaign_slug}_duration_ladder_mean_f1",
        title="Duration Ladder Sensitivity (Mean F1)",
    )
    write_sidecar(sidecar_dir / f"{campaign_slug}_stratified_rollup_metrics.csv", strat_rows)
    write_sidecar(sidecar_dir / f"{campaign_slug}_delta_vs_paper_fidelity.csv", delta_rows)
    write_sidecar(sidecar_dir / f"{campaign_slug}_roc_points.csv", roc_rows)

    plot_roc_points(
        roc_rows,
        out_dir=out_dir,
        stem=f"{campaign_slug}_roc_points",
    )

    paper_r = read_csv(evaluation_dir / "paper_roc_replay_rollup.csv")
    if paper_r:
        write_sidecar(sidecar_dir / f"{campaign_slug}_paper_roc_replay_rollup.csv", paper_r)
        plot_paper_roc_replay(
            paper_r,
            out_dir=out_dir,
            stem=f"{campaign_slug}_paper_roc_replay_rollup",
        )

    # Simple interaction chart: quantile by fault family.
    interaction_rows = []
    for row in run_rows:
        interaction_rows.append(
            {
                "fault_family": row.get("fault_family", "unknown"),
                "anomaly_quantile": row.get("anomaly_quantile", ""),
                "f1": to_float(row, "f1"),
            }
        )
    write_sidecar(sidecar_dir / f"{campaign_slug}_interaction_quantile_fault_family.csv", interaction_rows)

    print(f"Wrote figures to: {out_dir}")


if __name__ == "__main__":
    main()
