#!/usr/bin/env python3
"""Generate slide charts for RQ1–RQ3 from campaign run_metrics.csv (no PPTX embedding)."""

from __future__ import annotations

import csv
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT.parent / "data" / "experiments"
OUT = ROOT / "figures" / "slides"

CAMPAIGNS = {
    "rq1": DATA / "campaign-20260329T235958Z" / "evaluation" / "run_metrics.csv",
    "rq2": DATA / "campaign-20260330T101857Z" / "evaluation" / "run_metrics.csv",
    "rq3": DATA / "campaign-20260330T165222Z" / "evaluation" / "run_metrics.csv",
}

FAULT_LABEL = {
    "mem_leak": "Memory leak",
    "cpu_hog_like": "CPU hog",
    "net_hog_like_latency": "Net latency",
    "lock_convoy": "Lock convoy",
    "disk_fill": "Disk fill",
}


def _mean(xs: list[float]) -> float:
    return float(statistics.mean(xs)) if xs else float("nan")


def load_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


_METRIC_KEYS = (
    "f1",
    "precision",
    "recall",
    "paper_at",
    "paper_af",
    "alarm_fp_fraction",
    "mean_lead_time_s",
    "median_lead_time_s",
)


def agg_by_fault(rows: list[dict[str, str]]) -> dict[str, dict[str, list[float]]]:
    """fault_id -> metric -> values."""
    out: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        fid = r["fault_id"]
        for key in _METRIC_KEYS:
            try:
                out[fid][key].append(float(r[key]))
            except (KeyError, ValueError):
                pass
    return dict(out)


def agg_by_family(rows: list[dict[str, str]]) -> dict[str, list[float]]:
    fam: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        try:
            fam[r["fault_family"]].append(float(r["f1"]))
        except (KeyError, ValueError):
            pass
    return dict(fam)


def agg_geometry(
    rows: list[dict[str, str]], fault_id: str
) -> dict[tuple[str, str], list[float]]:
    """(intensity_level, duration_level) -> f1 values."""
    g: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in rows:
        if r["fault_id"] != fault_id:
            continue
        try:
            g[(r["intensity_level"], r["duration_level"])].append(float(r["f1"]))
        except (KeyError, ValueError):
            pass
    return dict(g)


def setup_style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 120,
            "savefig.dpi": 220,
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.labelsize": 11,
            "legend.fontsize": 10,
            "figure.facecolor": "white",
            "axes.facecolor": "#fafafa",
            "axes.grid": True,
            "grid.alpha": 0.35,
        }
    )
    try:
        plt.style.use("seaborn-v0_8-whitegrid")
    except OSError:
        pass


def bar_fault_metrics(
    agg: dict[str, dict[str, list[float]]],
    fault_order: list[str],
    title: str,
    outfile: Path,
    metrics: tuple[tuple[str, str], ...] = (
        ("f1", "F1"),
        ("paper_at", "True alarm rate"),
    ),
    ylim01: bool = True,
) -> None:
    labels = [FAULT_LABEL.get(f, f) for f in fault_order]
    x = np.arange(len(labels))
    width = 0.35
    fig, ax = plt.subplots(figsize=(10, 5.2))
    for i, (m, leg) in enumerate(metrics):
        vals = [_mean(agg.get(f, {}).get(m, [])) for f in fault_order]
        offset = (i - len(metrics) / 2 + 0.5) * width
        ax.bar(x + offset, vals, width, label=leg)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_ylabel("Score")
    ax.set_title(title)
    ax.legend()
    if ylim01:
        ax.set_ylim(0, 1.05)
    fig.tight_layout()
    fig.savefig(outfile, bbox_inches="tight")
    plt.close(fig)


def heatmap_geometry(
    rows: list[dict[str, str]],
    faults: list[str],
    title: str,
    outfile: Path,
) -> None:
    """2x2 grid: rows = duration (short, long), cols = intensity (low, high)."""
    dur_order = ("short", "long")
    int_order = ("low", "high")
    fig, axes = plt.subplots(
        1,
        len(faults),
        figsize=(4 * len(faults), 3.8),
        squeeze=False,
        constrained_layout=True,
    )
    im = None
    for ax, fid in zip(axes[0], faults):
        g = agg_geometry(rows, fid)
        mat = np.zeros((2, 2))
        for ri, d in enumerate(dur_order):
            for ci, ins in enumerate(int_order):
                key = (ins, d)
                mat[ri, ci] = _mean(g.get(key, []))
        im = ax.imshow(mat, vmin=0, vmax=1, cmap="RdYlGn", aspect="auto")
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["Low I", "High I"])
        ax.set_yticks([0, 1])
        ax.set_yticklabels(["Short D", "Long D"])
        ax.set_title(FAULT_LABEL.get(fid, fid))
        for ri in range(2):
            for ci in range(2):
                v = mat[ri, ci]
                ax.text(ci, ri, f"{v:.2f}", ha="center", va="center", color="black", fontsize=11)
    fig.suptitle(title)
    if im is not None:
        fig.colorbar(im, ax=list(axes[0]), shrink=0.72, label="Mean F1")
    fig.savefig(outfile, bbox_inches="tight")
    plt.close(fig)


def bar_dual_f1_paper_af(
    agg: dict[str, dict[str, list[float]]],
    fault_order: list[str],
    title: str,
    outfile: Path,
) -> None:
    labels = [FAULT_LABEL.get(f, f) for f in fault_order]
    x = np.arange(len(labels))
    w = 0.36
    f1s = [_mean(agg.get(f, {}).get("f1", [])) for f in fault_order]
    afs = [_mean(agg.get(f, {}).get("paper_af", [])) for f in fault_order]
    fig, ax1 = plt.subplots(figsize=(10, 5.2))
    b1 = ax1.bar(x - w / 2, f1s, w, label="F1", color="#2c7fb8")
    ax1.set_ylabel("F1")
    ax1.set_ylim(0, 1.05)
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=20, ha="right")
    ax1.set_title(title)
    ax2 = ax1.twinx()
    b2 = ax2.bar(x + w / 2, afs, w, label="False alarm rate (normal)", color="#feb24c")
    ax2.set_ylabel("False alarm rate (normal)")
    ax2.set_ylim(0, max(0.25, max(afs, default=0) * 1.15))
    fig.legend(handles=[b1, b2], loc="upper right", bbox_to_anchor=(0.98, 0.98))
    fig.tight_layout()
    fig.savefig(outfile, bbox_inches="tight")
    plt.close(fig)


def bar_family_f1(fam: dict[str, list[float]], title: str, outfile: Path) -> None:
    order = ("paper_aligned", "extended")
    labels = ["Paper-aligned", "Extended"]
    vals = [_mean(fam.get(k, [])) for k in order]
    fig, ax = plt.subplots(figsize=(6, 4.5))
    colors = ["#74a9cf", "#238b45"]
    ax.bar(labels, vals, color=colors)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Mean F1 (per-run average)")
    ax.set_title(title)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.02, f"{v:.3f}", ha="center", fontsize=11)
    fig.tight_layout()
    fig.savefig(outfile, bbox_inches="tight")
    plt.close(fig)


def bar_lead_and_f1(
    agg: dict[str, dict[str, list[float]]],
    fault_order: list[str],
    title: str,
    outfile: Path,
) -> None:
    labels = [FAULT_LABEL.get(f, f) for f in fault_order]
    x = np.arange(len(labels))
    w = 0.36
    f1s = [_mean(agg.get(f, {}).get("f1", [])) for f in fault_order]
    leads = [_mean(agg.get(f, {}).get("mean_lead_time_s", [])) for f in fault_order]
    fig, ax1 = plt.subplots(figsize=(7, 4.8))
    b1 = ax1.bar(x - w / 2, f1s, w, label="F1", color="#3182bd")
    ax1.set_ylabel("F1")
    ax1.set_ylim(0, 1.05)
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels)
    ax1.set_title(title)
    ax2 = ax1.twinx()
    b2 = ax2.bar(x + w / 2, leads, w, label="Mean lead (s)", color="#9ecae1")
    ax2.set_ylabel("Mean lead time (s)")
    fig.legend(handles=[b1, b2], loc="upper center", ncol=2)
    fig.tight_layout()
    fig.savefig(outfile, bbox_inches="tight")
    plt.close(fig)


# (csv column, legend label) — all in [0, 1] for the top panel
# Legend labels are presentation-friendly; CSV column keys stay internal.
_RATE_METRICS: tuple[tuple[str, str], ...] = (
    ("f1", "F1"),
    ("precision", "Precision"),
    ("recall", "Recall"),
    ("paper_at", "True alarm rate"),
    ("paper_af", "False alarm rate (normal)"),
    ("alarm_fp_fraction", "FP share among alarms"),
)


def plot_rq_metrics_bundle(
    agg: dict[str, dict[str, list[float]]],
    fault_order: list[str],
    title: str,
    outfile: Path,
) -> None:
    """Two panels: rates in [0,1] (grouped bars); lead times in seconds."""
    labels = [FAULT_LABEL.get(f, f) for f in fault_order]
    n_f = len(labels)
    n_m = len(_RATE_METRICS)
    fig_w = max(10.0, 1.35 * n_f + 4.0)
    fig, (ax0, ax1) = plt.subplots(
        2,
        1,
        figsize=(fig_w, 7.8),
        height_ratios=[1.55, 1.0],
        sharex=False,
    )
    x = np.arange(n_f)
    bw = min(0.14, 0.8 / (n_m + 1))
    try:
        cmap = plt.colormaps["tab10"]
    except AttributeError:
        cmap = plt.cm.get_cmap("tab10")
    for i, (key, leg) in enumerate(_RATE_METRICS):
        vals = [_mean(agg.get(f, {}).get(key, [])) for f in fault_order]
        off = (i - (n_m - 1) / 2.0) * bw
        ax0.bar(
            x + off,
            vals,
            bw,
            label=leg,
            color=cmap(i % 10),
        )
    ax0.set_ylabel("Score (0–1)")
    ax0.set_title(title)
    ax0.set_xticks(x)
    ax0.set_xticklabels(labels, rotation=18, ha="right")
    ax0.set_ylim(0, 1.05)
    ax0.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, 1.28),
        ncol=2,
        fontsize=9,
        frameon=True,
    )

    w_lead = 0.32
    m_lead = [_mean(agg.get(f, {}).get("mean_lead_time_s", [])) for f in fault_order]
    med_lead = [_mean(agg.get(f, {}).get("median_lead_time_s", [])) for f in fault_order]
    ax1.bar(x - w_lead / 2, m_lead, w_lead, label="Mean lead (s)", color="#4292c6")
    ax1.bar(x + w_lead / 2, med_lead, w_lead, label="Median lead (s)", color="#9ecae1")
    ax1.set_ylabel("Lead time (s)")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=18, ha="right")
    ax1.legend(loc="upper right")
    ymax = max([*m_lead, *med_lead, 0.0], default=1.0)
    ax1.set_ylim(0, ymax * 1.15 if ymax > 0 else 1.0)

    fig.tight_layout()
    fig.savefig(outfile, bbox_inches="tight")
    plt.close(fig)


def heatmap_metric_geometry(
    rows: list[dict[str, str]],
    faults: list[str],
    metric_key: str,
    metric_label: str,
    title: str,
    outfile: Path,
) -> None:
    """Same 2×2 intensity×duration layout as F1 heatmap, for another metric."""
    dur_order = ("short", "long")
    int_order = ("low", "high")

    def cell_mean(fid: str, ins: str, dur: str) -> float:
        xs: list[float] = []
        for r in rows:
            if r["fault_id"] != fid:
                continue
            if r["intensity_level"] != ins or r["duration_level"] != dur:
                continue
            try:
                xs.append(float(r[metric_key]))
            except (KeyError, ValueError):
                pass
        return _mean(xs)

    fig, axes = plt.subplots(
        1,
        len(faults),
        figsize=(4 * len(faults), 3.8),
        squeeze=False,
        constrained_layout=True,
    )
    im = None
    for ax, fid in zip(axes[0], faults):
        mat = np.full((2, 2), np.nan)
        for ri, d in enumerate(dur_order):
            for ci, ins in enumerate(int_order):
                mat[ri, ci] = cell_mean(fid, ins, d)
        im = ax.imshow(
            np.ma.masked_invalid(mat),
            vmin=0,
            vmax=1,
            cmap="RdYlGn",
            aspect="auto",
        )
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["Low I", "High I"])
        ax.set_yticks([0, 1])
        ax.set_yticklabels(["Short D", "Long D"])
        ax.set_title(FAULT_LABEL.get(fid, fid))
        for ri in range(2):
            for ci in range(2):
                v = mat[ri, ci]
                txt = "—" if v != v else f"{v:.2f}"
                ax.text(
                    ci,
                    ri,
                    txt,
                    ha="center",
                    va="center",
                    color="black",
                    fontsize=10,
                )
    fig.suptitle(title)
    if im is not None:
        fig.colorbar(im, ax=list(axes[0]), shrink=0.72, label=f"Mean {metric_label}")
    fig.savefig(outfile, bbox_inches="tight")
    plt.close(fig)


def cross_stage_f1(
    path_a: Path,
    path_b: Path,
    fault_ids: list[str],
    title: str,
    outfile: Path,
) -> None:
    a = agg_by_fault(load_rows(path_a))
    b = agg_by_fault(load_rows(path_b))
    labels = [FAULT_LABEL.get(f, f) for f in fault_ids]
    x = np.arange(len(labels))
    w = 0.35
    s1 = [_mean(a.get(f, {}).get("f1", [])) for f in fault_ids]
    s2 = [_mean(b.get(f, {}).get("f1", [])) for f in fault_ids]
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    ax.bar(x - w / 2, s1, w, label="Stage 1 (RQ1)", color="#6baed6")
    ax.bar(x + w / 2, s2, w, label="Stage 2 (RQ2)", color="#fd8d3c")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Mean F1")
    ax.set_ylim(0, 1.05)
    ax.set_title(title)
    ax.legend()
    fig.tight_layout()
    fig.savefig(outfile, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    setup_style()
    OUT.mkdir(parents=True, exist_ok=True)

    r1 = load_rows(CAMPAIGNS["rq1"])
    r2 = load_rows(CAMPAIGNS["rq2"])
    r3 = load_rows(CAMPAIGNS["rq3"])

    a1 = agg_by_fault(r1)
    a2 = agg_by_fault(r2)
    a3 = agg_by_fault(r3)

    rq1_faults = ["mem_leak", "cpu_hog_like", "net_hog_like_latency"]
    rq2_faults = [
        "mem_leak",
        "cpu_hog_like",
        "net_hog_like_latency",
        "lock_convoy",
        "disk_fill",
    ]
    rq3_faults = ["lock_convoy", "disk_fill"]

    bar_fault_metrics(
        a1,
        rq1_faults,
        "RQ1 (Stage 1): F1 and true alarm rate by fault (paper-aligned families)",
        OUT / "rq1_f1_paper_at_by_fault.png",
    )
    heatmap_geometry(
        r1,
        rq1_faults,
        "RQ1: Mean F1 by intensity × duration (fixed detector)",
        OUT / "rq1_f1_intensity_duration_heatmaps.png",
    )
    plot_rq_metrics_bundle(
        a1,
        rq1_faults,
        "RQ1 (Stage 1): detection metrics by fault",
        OUT / "rq1_all_metrics_by_fault.png",
    )
    heatmap_metric_geometry(
        r1,
        rq1_faults,
        "precision",
        "precision",
        "RQ1: Mean precision by intensity × duration",
        OUT / "rq1_precision_intensity_duration_heatmaps.png",
    )
    heatmap_metric_geometry(
        r1,
        rq1_faults,
        "recall",
        "recall",
        "RQ1: Mean recall by intensity × duration",
        OUT / "rq1_recall_intensity_duration_heatmaps.png",
    )
    heatmap_metric_geometry(
        r1,
        rq1_faults,
        "paper_af",
        "false alarm rate (normal)",
        "RQ1: Mean false alarm rate (normal) by intensity × duration",
        OUT / "rq1_paper_af_intensity_duration_heatmaps.png",
    )

    bar_fault_metrics(
        a2,
        rq2_faults,
        "RQ2 (Stage 2): F1 and true alarm rate by fault (mixed families)",
        OUT / "rq2_f1_paper_at_by_fault.png",
    )
    bar_dual_f1_paper_af(
        a2,
        rq2_faults,
        "RQ2: F1 vs false alarm rate (normal)",
        OUT / "rq2_f1_vs_paper_af.png",
    )
    fam2 = agg_by_family(r2)
    bar_family_f1(
        fam2,
        "RQ2: Mean F1 by fault family (paper-aligned vs extended)",
        OUT / "rq2_mean_f1_by_fault_family.png",
    )
    plot_rq_metrics_bundle(
        a2,
        rq2_faults,
        "RQ2 (Stage 2): detection metrics by fault",
        OUT / "rq2_all_metrics_by_fault.png",
    )

    bar_fault_metrics(
        a3,
        rq3_faults,
        "RQ3 (Stage 3): F1 and true alarm rate — extended transfer",
        OUT / "rq3_f1_paper_at_by_fault.png",
    )
    bar_lead_and_f1(
        a3,
        rq3_faults,
        "RQ3: F1 and mean lead time (confirmatory)",
        OUT / "rq3_f1_and_lead_time.png",
    )
    plot_rq_metrics_bundle(
        a3,
        rq3_faults,
        "RQ3 (Stage 3): detection metrics by fault",
        OUT / "rq3_all_metrics_by_fault.png",
    )
    heatmap_metric_geometry(
        r3,
        rq3_faults,
        "precision",
        "precision",
        "RQ3: Mean precision by intensity × duration",
        OUT / "rq3_precision_intensity_duration_heatmaps.png",
    )
    heatmap_metric_geometry(
        r3,
        rq3_faults,
        "paper_af",
        "false alarm rate (normal)",
        "RQ3: Mean false alarm rate (normal) by intensity × duration",
        OUT / "rq3_paper_af_intensity_duration_heatmaps.png",
    )
    heatmap_metric_geometry(
        r3,
        rq3_faults,
        "alarm_fp_fraction",
        "FP share among alarms",
        "RQ3: Mean FP share among alarms by intensity × duration",
        OUT / "rq3_alarm_fp_frac_intensity_duration_heatmaps.png",
    )

    cross_stage_f1(
        CAMPAIGNS["rq1"],
        CAMPAIGNS["rq2"],
        ["net_hog_like_latency", "cpu_hog_like"],
        "Cross-stage: mean F1 (Stage 1 vs Stage 2)",
        OUT / "extra_stage1_vs_stage2_net_cpu_f1.png",
    )

    print(f"Wrote figures to {OUT.resolve()}")


if __name__ == "__main__":
    main()
