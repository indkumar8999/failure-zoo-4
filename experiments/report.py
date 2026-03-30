from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def to_float(row: dict, key: str) -> float:
    try:
        return float(row.get(key, 0.0))
    except Exception:
        return 0.0


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def top_items(rows: list[dict], key: str, n: int = 5, reverse: bool = True) -> list[dict]:
    return sorted(rows, key=lambda r: to_float(r, key), reverse=reverse)[:n]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate markdown summary from evaluation CSV")
    parser.add_argument("--evaluation-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    summary = read_json(args.evaluation_dir / "summary.json")
    rollup = read_csv(args.evaluation_dir / "rollup_metrics.csv")
    deltas = read_csv(args.evaluation_dir / "delta_vs_paper_fidelity.csv")
    stratified = read_csv(args.evaluation_dir / "stratified_rollup_metrics.csv")
    failed = read_csv(args.evaluation_dir / "failed_runs.csv")
    paired = read_csv(args.evaluation_dir / "paired_significance.csv")
    fidelity = read_json(args.evaluation_dir / "fidelity_checks.json")
    som_rollup = read_csv(args.evaluation_dir / "som_rollup_metrics.csv")
    if not som_rollup and isinstance(summary.get("som_rollup_metrics"), list):
        som_rollup = summary["som_rollup_metrics"]
    if not rollup:
        raise SystemExit("No rollup metrics found.")

    rows = sorted(rollup, key=lambda r: (r["fault_id"], r["variant"]))
    lines = []
    lines.append("# UBL Fault Injection Report")
    lines.append("")
    lines.append("## Mean Metrics by Variant and Fault")
    lines.append("")
    lines.append(
        "| Fault | Variant | n | paper_AT | paper_AF | TPR | FPR (alarm stream) | Alarm FP frac | "
        "Precision | Recall | F1 (95% CI) | Lead Time (s, 95% CI) |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in rows:
        f1_lo = to_float(r, "ci95_low_f1")
        f1_hi = to_float(r, "ci95_high_f1")
        lead_lo = to_float(r, "ci95_low_lead_time_s")
        lead_hi = to_float(r, "ci95_high_lead_time_s")
        lines.append(
            "| {fault} | {variant} | {n} | {pat:.3f} | {paf:.3f} | {tpr:.3f} | {fpr:.3f} | {afp:.3f} | "
            "{p:.3f} | {rec:.3f} | {f1:.3f} [{f1_lo:.3f}, {f1_hi:.3f}] | {lead:.2f} [{lead_lo:.2f}, {lead_hi:.2f}] |".format(
                fault=r["fault_id"],
                variant=r["variant"],
                n=r["n_runs"],
                pat=to_float(r, "mean_paper_at"),
                paf=to_float(r, "mean_paper_af"),
                tpr=to_float(r, "mean_tpr"),
                fpr=to_float(r, "mean_fpr"),
                afp=to_float(r, "mean_alarm_fp_fraction"),
                p=to_float(r, "mean_precision"),
                rec=to_float(r, "mean_recall"),
                f1=to_float(r, "mean_f1"),
                lead=to_float(r, "mean_lead_time_s"),
                f1_lo=f1_lo,
                f1_hi=f1_hi,
                lead_lo=lead_lo,
                lead_hi=lead_hi,
            )
        )

    lines.append("")
    lines.append("## Paper-Faithful Findings")
    lines.append("")
    paper_rows = [r for r in rows if r.get("study_scope", "") == "paper_faithful"]
    if not paper_rows:
        lines.append("- No rows tagged as paper-faithful scope in this campaign.")
    else:
        for r in top_items(paper_rows, "mean_f1", n=6):
            lines.append(
                "- `{fault}` / `{variant}`: F1={f1:.3f}, precision={precision:.3f}, recall={recall:.3f}, "
                "paper_AT={pat:.3f}, paper_AF={paf:.3f}, FPR_alarm={fpr:.3f}, faithfulness={label}".format(
                    fault=r.get("fault_id", ""),
                    variant=r.get("variant", ""),
                    f1=to_float(r, "mean_f1"),
                    precision=to_float(r, "mean_precision"),
                    recall=to_float(r, "mean_recall"),
                    pat=to_float(r, "mean_paper_at"),
                    paf=to_float(r, "mean_paper_af"),
                    fpr=to_float(r, "mean_fpr"),
                    label=r.get("faithfulness_label", ""),
                )
            )

    lines.append("")
    lines.append("## Extended Findings")
    lines.append("")
    ext_rows = [r for r in rows if r.get("study_scope", "") != "paper_faithful"]
    if not ext_rows:
        lines.append("- No extended rows in this campaign.")
    else:
        for r in top_items(ext_rows, "mean_f1", n=6):
            lines.append(
                "- `{fault}` / `{variant}`: F1={f1:.3f}, precision={precision:.3f}, recall={recall:.3f}, lead={lead:.2f}s, ablation_block={block}".format(
                    fault=r.get("fault_id", ""),
                    variant=r.get("variant", ""),
                    f1=to_float(r, "mean_f1"),
                    precision=to_float(r, "mean_precision"),
                    recall=to_float(r, "mean_recall"),
                    lead=to_float(r, "mean_lead_time_s"),
                    block=r.get("ablation_block", ""),
                )
            )

    lines.append("")
    lines.append("## Interaction Effects and Deltas vs Paper Fidelity")
    lines.append("")
    if not deltas:
        lines.append("- No delta rows (paper_fidelity anchor missing or no comparator variants).")
    else:
        for d in top_items(deltas, "delta_mean_f1", n=8):
            lines.append(
                "- `{fault}` / `{variant}` vs `paper_fidelity`: ΔF1={df1:+.3f}, ΔTPR={dtpr:+.3f}, ΔFPR={dfpr:+.3f}, ΔLead={dlead:+.2f}s".format(
                    fault=d.get("fault_id", ""),
                    variant=d.get("variant", ""),
                    df1=to_float(d, "delta_mean_f1"),
                    dtpr=to_float(d, "delta_mean_tpr"),
                    dfpr=to_float(d, "delta_mean_fpr"),
                    dlead=to_float(d, "delta_mean_lead_time_s"),
                )
            )

    lines.append("")
    lines.append("## Key Negative Results and Caveats")
    lines.append("")
    # With one rollup row, "lowest F1" is not meaningful; only flag genuinely weak pairs.
    low_f1_threshold = 0.5
    low_f1_candidates = top_items(rows, "mean_f1", n=5, reverse=False)
    low_f1 = [r for r in low_f1_candidates if to_float(r, "mean_f1") < low_f1_threshold]
    if not low_f1:
        lines.append(
            f"- No variant/fault pairs with mean F1 below {low_f1_threshold:g} in this campaign "
            "(single-run or high-F1 matrices may only appear in the rollup table above)."
        )
    else:
        for r in low_f1:
            lines.append(
                "- Low-F1 case `{fault}` / `{variant}`: F1={f1:.3f}, precision={precision:.3f}, recall={recall:.3f}, "
                "paper_AF={paf:.3f}, FPR_alarm={fpr:.3f}".format(
                    fault=r.get("fault_id", ""),
                    variant=r.get("variant", ""),
                    f1=to_float(r, "mean_f1"),
                    precision=to_float(r, "mean_precision"),
                    recall=to_float(r, "mean_recall"),
                    paf=to_float(r, "mean_paper_af"),
                    fpr=to_float(r, "mean_fpr"),
                )
            )

    lines.append("")
    lines.append("## Stratified Rollups")
    lines.append("")
    if not stratified:
        lines.append("- No stratified rollups generated.")
    else:
        lines.append(
            "| Group Type | Group Name | n | Mean F1 | Mean Precision | Mean Recall | Mean TPR | Mean paper_AF | Mean FPR (alarm) |"
        )
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
        for r in sorted(stratified, key=lambda x: (x.get("group_type", ""), x.get("group_name", ""))):
            lines.append(
                "| {gt} | {gn} | {n} | {f1:.3f} | {precision:.3f} | {recall:.3f} | {tpr:.3f} | {paf:.3f} | {fpr:.3f} |".format(
                    gt=r.get("group_type", ""),
                    gn=r.get("group_name", ""),
                    n=r.get("n_runs", ""),
                    f1=to_float(r, "mean_f1"),
                    precision=to_float(r, "mean_precision"),
                    recall=to_float(r, "mean_recall"),
                    tpr=to_float(r, "mean_tpr"),
                    paf=to_float(r, "mean_paper_af"),
                    fpr=to_float(r, "mean_fpr"),
                )
            )

    lines.append("")
    lines.append("## SOM checkpoint summary")
    lines.append("")
    lines.append(
        "Per-run SOM fields are merged into `run_metrics.csv` (prefix `som_`). "
        "Topology uses mean L2 distance between adjacent map units (U-matrix proxy); "
        "quantization proxy is mean BMU distance on feature vectors sampled from `anomaly_events.jsonl` when available."
    )
    lines.append("")
    if not som_rollup:
        lines.append(
            "- No SOM rollup rows (no `som_model.npz` snapshots in completed runs, or re-run `evaluate.py` to refresh). "
            "If runs completed but snapshots are missing, check per-run `manifest.json` for `artifact_snapshot_warnings` "
            "and confirm `docker compose` used this repo’s `docker-compose.yml` so `./data/learner` bind-mounts correctly."
        )
    else:
        lines.append("| Variant | Fault | n (SOM) | mean val acc | mean U-matrix | mean QE proxy |")
        lines.append("|---|---|---:|---:|---:|---:|")
        for r in sorted(som_rollup, key=lambda x: (x.get("fault_id", ""), x.get("variant", ""))):
            qe = r.get("mean_som_quantization_mean_bmu_dist", "")
            qe_s = f"{to_float(r, 'mean_som_quantization_mean_bmu_dist'):.4f}" if str(qe).strip() != "" else "—"
            lines.append(
                "| {v} | {f} | {n} | {acc:.4f} | {u:.4f} | {qe} |".format(
                    v=r.get("variant", ""),
                    f=r.get("fault_id", ""),
                    n=r.get("n_runs_with_som", ""),
                    acc=to_float(r, "mean_som_validation_accuracy"),
                    u=to_float(r, "mean_som_umatrix_mean"),
                    qe=qe_s,
                )
            )

    lines.append("")
    lines.append("## Reproducibility Artifacts")
    lines.append("")
    lines.append(
        "- Source metrics: `run_metrics.csv`, `rollup_metrics.csv`, `stratified_rollup_metrics.csv`, "
        "`delta_vs_paper_fidelity.csv`, `som_rollup_metrics.csv` (SOM lattice / checkpoint aggregates)."
    )
    if (args.evaluation_dir / "roc_points.csv").exists():
        lines.append("- ROC-style threshold points: `roc_points.csv`.")
    if (args.evaluation_dir / "paper_roc_replay_rollup.csv").exists():
        lines.append(
            "- Paper-style offline ROC (quantile sweep on persisted scores): "
            "`paper_roc_replay_by_run.csv`, `paper_roc_replay_rollup.csv`."
        )
    if (args.evaluation_dir / "pending_window_sensitivity.csv").exists():
        lines.append("- Pending-window sensitivity on logged alarms: `pending_window_sensitivity.csv`.")
    if summary.get("matching_mode"):
        lines.append(f"- Matching mode: `{summary.get('matching_mode')}`.")
    lines.append("- Validity ledger: `validity_ledger.json`.")
    if summary.get("campaign_meta"):
        lines.append("- Campaign metadata: captured in `summary.json` under `campaign_meta`.")
    if failed:
        lines.append("- Failed runs captured in `failed_runs.csv` (included in `summary.json`).")
    if paired:
        lines.append("- Paired significance results captured in `paired_significance.csv`.")
    if fidelity:
        lines.append("- UBL fidelity checks captured in `fidelity_checks.json`.")

    lines.append("")
    lines.append("## UBL Fidelity Checks")
    lines.append("")
    checks = fidelity.get("checks", {}) if isinstance(fidelity, dict) else {}
    if not checks:
        lines.append("- Fidelity checks unavailable.")
    else:
        lines.append(f"- Sampling interval includes 1s: `{checks.get('sampling_interval_has_1s', False)}`.")
        lines.append(f"- Percentile threshold sweep present: `{checks.get('threshold_percentile_sweep_present', False)}`.")
        lines.append(f"- Paper-style offline threshold replay ran: `{checks.get('paper_style_threshold_replay_ran', False)}`.")
        lines.append(f"- Pending-window sweep present: `{checks.get('pending_window_sweep_present', False)}`.")
        lines.append(f"- PCA/kNN comparator present: `{checks.get('pca_or_knn_comparator_present', False)}`.")

    lines.append("")
    lines.append("## Failure Accounting")
    lines.append("")
    if not failed:
        lines.append("- No failed runs recorded.")
    else:
        lines.append("| Run ID | Fault | Variant | Failed Phase | Reason |")
        lines.append("|---|---|---|---|---|")
        for r in failed[:20]:
            lines.append(
                "| {run} | {fault} | {variant} | {phase} | {reason} |".format(
                    run=r.get("run_id", ""),
                    fault=r.get("fault_id", ""),
                    variant=r.get("variant", ""),
                    phase=r.get("failed_phase", ""),
                    reason=str(r.get("failure_reason", "")).replace("|", "/"),
                )
            )

    lines.append("")
    lines.append("## Paired Significance")
    lines.append("")
    if not paired:
        lines.append("- No paired significance rows generated.")
    else:
        lines.append("| Fault | Variant | n Pairs | Mean ΔF1 | p(F1) | p(F1,BH) | Mean ΔTPR | Mean ΔFPR | Mean ΔLead(s) |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
        for r in paired:
            lines.append(
                "| {fault} | {variant} | {n} | {d:+.3f} | {p:.4f} | {p_bh:.4f} | {dtpr:+.3f} | {dfpr:+.3f} | {dlead:+.2f} |".format(
                    fault=r.get("fault_id", ""),
                    variant=r.get("variant", ""),
                    n=r.get("n_pairs", ""),
                    d=to_float(r, "mean_delta_f1"),
                    p=to_float(r, "sign_test_pvalue_f1"),
                    p_bh=to_float(r, "sign_test_pvalue_f1_bh"),
                    dtpr=to_float(r, "mean_delta_tpr"),
                    dfpr=to_float(r, "mean_delta_fpr"),
                    dlead=to_float(r, "mean_delta_lead_time_s"),
                )
            )
    lines.append("")
    lines.append("## Validity Notes")
    lines.append("")
    lines.append("- Pending-window scoring (`W`) approximates prediction quality and should be stress-tested per workload.")
    lines.append(
        "- **paper_AT** / **paper_AF** follow UBL Eq. 5 style on this lab’s labels; **FPR (alarm stream)** is "
        "`fp/(fp+tp)` (same as alarm FP fraction), not paper AF. See `validity_ledger.json` and `run_metrics.csv`."
    )
    lines.append("- Toxiproxy-based `net_hog_like` is a proxy for paper NetHog, not a byte-for-byte replica.")
    lines.append("- If the learner runs in `bmu` mode, results are baseline comparisons and not strict UBL replication.")
    lines.append(
        "- **`bootstrap_vectors_ok`** matches **`schedule_bootstrap_polls_ok`**: matrix poll budget during the bootstrap phase, "
        "not learner-collected sample counts. Use **`manifest_bootstrap_samples`** / **`learner_bootstrap_collected_ok`** "
        "(from run `manifest.json` → `learner_status_post_bootstrap`) when auditing training readiness."
    )

    out_path = args.out or (args.evaluation_dir / "report.md")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote report: {out_path}")


if __name__ == "__main__":
    main()
