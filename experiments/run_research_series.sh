#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${MODE:-full}"
OUT_DIR="${OUT_DIR:-$ROOT/data/experiments}"

MATRICES=(
  "$ROOT/experiments/fault_matrix_research_stage1_paper_geometry.yaml"
  "$ROOT/experiments/fault_matrix_research_stage2_memleak_boundary.yaml"
  "$ROOT/experiments/fault_matrix_research_stage3_extended_transfer.yaml"
)

latest_campaign_dir() {
  ls -dt "$OUT_DIR"/campaign-* 2>/dev/null | head -n 1
}

echo "# Running research series in mode=$MODE"
echo "# Output root: $OUT_DIR"

for matrix in "${MATRICES[@]}"; do
  echo
  echo "============================================================"
  echo "# Matrix: $matrix"
  echo "============================================================"

  python3 "$ROOT/experiments/run_experiments.py" \
    --mode "$MODE" \
    --matrix "$matrix" \
    --out-dir "$OUT_DIR"

  campaign_dir="$(latest_campaign_dir)"
  if [[ -z "${campaign_dir:-}" || ! -d "$campaign_dir" ]]; then
    echo "ERROR: unable to locate latest campaign directory in $OUT_DIR" >&2
    exit 1
  fi

  echo "# Evaluating: $campaign_dir"
  python3 "$ROOT/experiments/evaluate.py" --campaign-dir "$campaign_dir"
  python3 "$ROOT/experiments/report.py" --evaluation-dir "$campaign_dir/evaluation"

  echo "# Completed stage for $matrix"
  echo "# Report: $campaign_dir/evaluation/report.md"
done

echo
echo "# Research series complete."
