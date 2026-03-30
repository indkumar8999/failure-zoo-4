from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import urlopen

import yaml


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DEFAULT_MATRIX = ROOT / "experiments" / "fault_matrix.yaml"
DEFAULT_OUT = ROOT / "data" / "experiments"


@dataclass
class RunConfig:
    run_id: str
    variant_name: str
    fault_id: str
    fault_family: str
    study_scope: str
    ablation_block: str
    hypothesis_id: str
    interpretation_note: str
    faithfulness_label: str
    repeat_idx: int
    seed_idx: int
    run_seed: int
    warmup_s: int
    bootstrap_s: int
    inject_s: int
    cooldown_s: int
    fault_window_on_delay_s: int
    pending_window_s: int
    pending_level: str
    intensity_level: str
    duration_level: str
    train_mode: str
    fault_on: List[str]
    fault_off: List[str]
    fault_intensity: float
    learner_env: Dict[str, str]
    loadgen_seed: int
    anomaly_quantile_level: str


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, separators=(",", ":")) + "\n")


def run_cmd(cmd: List[str], cwd: Path, env: Dict[str, str], dry_run: bool) -> None:
    print("$", " ".join(cmd))
    if dry_run:
        return
    subprocess.run(cmd, cwd=str(cwd), env=env, check=True)


def _safe_cmd_output(cmd: List[str]) -> str:
    try:
        out = subprocess.check_output(cmd, cwd=str(ROOT), stderr=subprocess.DEVNULL, text=True)
        return out.strip()
    except Exception:
        return ""


def _git_sha() -> str:
    return _safe_cmd_output(["git", "rev-parse", "HEAD"])


def _git_branch() -> str:
    return _safe_cmd_output(["git", "rev-parse", "--abbrev-ref", "HEAD"])


def _compose_config_text(env: Dict[str, str]) -> str:
    try:
        out = subprocess.check_output(
            ["docker", "compose", "config"],
            cwd=str(ROOT),
            env=env,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out
    except Exception:
        return ""


def _compose_config_sha256(env: Dict[str, str]) -> str:
    text = _compose_config_text(env)
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _docker_compose_images_json(env: Dict[str, str]) -> List[dict]:
    try:
        raw = subprocess.check_output(
            ["docker", "compose", "images", "--format", "json"],
            cwd=str(ROOT),
            env=env,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if not raw:
            return []
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [x for x in parsed if isinstance(x, dict)]
        return []
    except Exception:
        return []


def _bool_from_meta(meta: dict, key: str, default: bool = False) -> bool:
    raw = meta.get(key, default)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _collect_matrix_seeds(meta: dict) -> List[int]:
    explicit = meta.get("seeds")
    if isinstance(explicit, list) and explicit:
        out: List[int] = []
        for item in explicit:
            try:
                out.append(int(item))
            except Exception:
                continue
        if out:
            return out
    try:
        return [int(meta.get("seed", 42))]
    except Exception:
        return [42]


def _is_paper_faithful_variant(variant: dict, meta: dict) -> bool:
    return _pick_tag_value(variant, {}, meta, "study_scope", "extended").strip().lower() == "paper_faithful"


def _paper_fidelity_violations(variant: dict, meta: dict) -> List[str]:
    env = {str(k): str(v) for k, v in variant.get("env", {}).items()} if isinstance(variant.get("env"), dict) else {}
    out: List[str] = []
    expected = {
        "SOM_SCORING_MODE": "ubl_area",
        "SOM_SMOOTH_K": "5",
        "ANOMALY_STREAK": "3",
        "ANOMALY_QUANTILE": "0.85",
        "SOM_ROWS": "32",
        "SOM_COLS": "32",
        "SOM_KFOLD": "3",
        "SOM_INIT_TRIALS": "3",
        "SOM_NORMALIZATION_MODE": "train_max_100",
        "SOM_ONLINE_CLIP_MODE": "none",
        "POLL_SEC": "1.0",
    }
    for key, want in expected.items():
        got = str(env.get(key, "")).strip()
        if got != want:
            out.append(f"{key}={got or '<unset>'} (expected {want})")
    train_mode = str(variant.get("train_mode", meta.get("train_mode", "warm_start"))).strip().lower()
    if train_mode != "fresh_bootstrap":
        out.append(f"train_mode={train_mode} (expected fresh_bootstrap)")
    return out

def _faithfulness_label(study_scope: str, fault_family: str, proxy_mapping: bool) -> str:
    scope = (study_scope or "").strip().lower()
    family = (fault_family or "").strip().lower()
    if scope == "paper_faithful":
        if proxy_mapping:
            return "paper-faithful-with-proxy"
        if family == "paper_aligned":
            return "paper-faithful"
    return "extended-beyond-paper"


def _pick_tag_value(variant: dict, fault: dict, meta: dict, key: str, default: str) -> str:
    for source in (variant, fault, meta):
        if isinstance(source, dict) and key in source:
            return str(source[key])
    return default


def _parse_ladder(value: Any, default_level: str, default_value: float) -> List[Dict[str, Any]]:
    if value is None:
        return [{"level": default_level, "value": default_value}]
    if isinstance(value, list):
        out = []
        for idx, item in enumerate(value):
            if isinstance(item, dict):
                out.append({"level": str(item.get("level", f"l{idx+1}")), "value": item.get("value", default_value)})
            else:
                out.append({"level": f"l{idx+1}", "value": item})
        return out or [{"level": default_level, "value": default_value}]
    return [{"level": default_level, "value": value}]


def _format_intensity_cli(value: float) -> str:
    """Avoid '20.0' in argv; chaosctl and shell-friendly integer tokens for whole values."""
    v = float(value)
    if v.is_integer():
        return str(int(v))
    return str(v)


def _render_command(cmd: List[str], intensity: float) -> List[str]:
    rendered: List[str] = []
    has_token = any("{intensity}" in part for part in cmd)
    token = _format_intensity_cli(intensity)
    for part in cmd:
        rendered.append(str(part).replace("{intensity}", token))
    if has_token:
        return rendered
    return [str(x) for x in cmd]


def _derive_run_seed(base_seed: int, labels: List[str]) -> int:
    payload = "|".join([str(base_seed)] + labels)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def compose(cmd: List[str], env: Dict[str, str], dry_run: bool) -> None:
    run_cmd(["docker", "compose"] + cmd, cwd=ROOT, env=env, dry_run=dry_run)


def compose_retry(cmd: List[str], env: Dict[str, str], dry_run: bool, retries: int = 5, sleep_s: float = 2.0) -> None:
    if dry_run:
        compose(cmd, env=env, dry_run=True)
        return
    last_err = None
    for i in range(retries):
        try:
            compose(cmd, env=env, dry_run=False)
            return
        except subprocess.CalledProcessError as exc:
            last_err = exc
            if i == retries - 1:
                raise
            time.sleep(sleep_s)
    if last_err:
        raise last_err


def validate_matrix(matrix: dict, allow_paper_fidelity_drift: bool = False) -> None:
    faults = matrix.get("faults", [])
    learner = matrix.get("learner", {})
    variants = learner.get("variants", []) if isinstance(learner, dict) else []
    meta = matrix.get("meta", {}) if isinstance(matrix.get("meta"), dict) else {}
    allowed_families = {"paper_aligned", "extended"}
    if not faults:
        raise ValueError("Matrix contains no faults.")
    if not variants:
        raise ValueError("Matrix contains no learner variants.")
    matrix_seeds = _collect_matrix_seeds(meta)
    if not matrix_seeds:
        raise ValueError("Matrix seed list resolved to empty.")
    for fault in faults:
        if "id" not in fault:
            raise ValueError("Fault entry missing id.")
        family = str(fault.get("family", "")).strip()
        if family not in allowed_families:
            raise ValueError(f"Fault {fault.get('id')} has invalid family: {family}")
        if "command_on" not in fault or "command_off" not in fault:
            raise ValueError(f"Fault {fault.get('id')} missing command_on/command_off.")
    paper_violations: List[str] = []
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        if _is_paper_faithful_variant(variant, meta):
            issues = _paper_fidelity_violations(variant, meta)
            if issues:
                paper_violations.append(
                    f"variant={variant.get('name', '<unnamed>')}: " + "; ".join(issues)
                )
    if paper_violations and not allow_paper_fidelity_drift:
        raise ValueError(
            "Paper-faithful drift detected in matrix. Pass --allow-paper-fidelity-drift to override. "
            + " | ".join(paper_violations)
        )


def wait_for_app_ready(timeout_s: int = 90, interval_s: float = 1.0, dry_run: bool = False) -> None:
    if dry_run:
        return
    start = time.time()
    last_err: Optional[Exception] = None
    last_log = 0.0
    while time.time() - start < timeout_s:
        try:
            with urlopen("http://localhost:8000/health", timeout=2.0) as resp:
                if resp.status == 200:
                    elapsed = time.time() - start
                    if elapsed > 1.0:
                        print(f"# app health OK after {elapsed:.1f}s", flush=True)
                    return
        except Exception as exc:
            # Uvicorn can reset the TCP connection while binding during startup; urllib only
            # wraps some failures as URLError. Treat any transient error as not-ready-yet.
            last_err = exc
        now = time.time()
        if now - last_log >= 10.0:
            print(f"# waiting for app /health ... ({int(now - start)}s / {timeout_s}s)", flush=True)
            last_log = now
        time.sleep(interval_s)
    raise RuntimeError(f"App did not become healthy within {timeout_s}s. Last error: {last_err}")


def wait_for_learner_trained(
    model_path: Path,
    timeout_s: int = 300,
    interval_s: float = 1.0,
    dry_run: bool = False,
) -> None:
    """
    Fail-fast guard: do not inject faults until learner reports trained=true and model file exists.
    """
    if dry_run:
        return
    start = time.time()
    last_err: Optional[Exception] = None
    last_status: dict = {}
    last_log = 0.0
    while time.time() - start < timeout_s:
        try:
            with urlopen("http://localhost:8100/status", timeout=2.0) as resp:
                if resp.status == 200:
                    raw = resp.read().decode("utf-8", errors="replace")
                    status = json.loads(raw) if raw else {}
                    if isinstance(status, dict):
                        last_status = status
                        trained = bool(status.get("trained", False))
                        if trained and model_path.exists():
                            elapsed = time.time() - start
                            if elapsed > 1.0:
                                print(
                                    f"# learner trained/model-ready after {elapsed:.1f}s",
                                    flush=True,
                                )
                            return
        except Exception as exc:
            last_err = exc
        now = time.time()
        if now - last_log >= 10.0:
            print(
                "# waiting for learner trained/model ... "
                f"({int(now - start)}s / {timeout_s}s; "
                f"trained={bool(last_status.get('trained', False))}; "
                f"bootstrap={last_status.get('bootstrap_samples', '?')}/{last_status.get('bootstrap_target', '?')}; "
                f"model_exists={model_path.exists()})",
                flush=True,
            )
            last_log = now
        time.sleep(interval_s)
    raise RuntimeError(
        "Learner did not become trained+model-ready within "
        f"{timeout_s}s. model_exists={model_path.exists()} "
        f"last_status={last_status} last_error={last_err}"
    )


def fetch_learner_status(dry_run: bool = False) -> Optional[dict]:
    """Best-effort snapshot of GET /status after training gate (for manifest + evaluation)."""
    if dry_run:
        return None
    try:
        with urlopen("http://localhost:8100/status", timeout=2.0) as resp:
            if resp.status != 200:
                return None
            raw = resp.read().decode("utf-8", errors="replace")
            out = json.loads(raw) if raw else {}
            return out if isinstance(out, dict) else None
    except Exception:
        return None


def configure_loadgen(meta: dict, env: Dict[str, str], seed: int) -> Dict[str, str]:
    out = dict(env)
    out["LOADGEN_PROFILE"] = str(meta.get("loadgen_profile", "steady"))
    out["LOADGEN_RPS"] = str(meta.get("loadgen_rps", 5.0))
    out["LOADGEN_WORK_MS"] = str(meta.get("loadgen_ms", 20))
    out["LOADGEN_JITTER"] = str(meta.get("loadgen_jitter", 0.1))
    out["LOADGEN_PATHS"] = str(meta.get("loadgen_paths", "/work"))
    out["LOADGEN_SEED"] = str(int(seed))
    return out


def snapshot_artifacts(
    run_dir: Path,
    *,
    run_status: str = "",
    train_mode: str = "",
    dry_run: bool = False,
    strict: bool = False,
) -> List[str]:
    """
    Copy host bind-mount artifacts into run_dir/artifacts. Returns warning strings for manifest.
    If strict and a completed fresh_bootstrap run lacks som_model.npz, raises RuntimeError.
    """
    mapping = {
        "chaos_events.jsonl": DATA_DIR / "app" / "events" / "chaos_events.jsonl",
        "anomaly_events.jsonl": DATA_DIR / "learner" / "events" / "anomaly_events.jsonl",
        "som_model.npz": DATA_DIR / "learner" / "model" / "som_model.npz",
    }
    out = run_dir / "artifacts"
    out.mkdir(parents=True, exist_ok=True)
    copied: List[str] = []
    missing: List[str] = []
    for name, src in mapping.items():
        if src.exists():
            shutil.copy2(src, out / name)
            copied.append(name)
        else:
            missing.append(name)
    warnings: List[str] = []
    host_model = DATA_DIR / "learner" / "model" / "som_model.npz"
    host_anomaly = DATA_DIR / "learner" / "events" / "anomaly_events.jsonl"
    if not dry_run:
        print(
            f"# artifact snapshot {run_dir.name}: copied {', '.join(copied) if copied else '(none)'}",
            flush=True,
        )
        if missing:
            print(f"# artifact snapshot: missing sources (skipped): {', '.join(missing)}", flush=True)
        print(
            "# verify host bind-mount (before tearing down Docker): "
            f"som_model.npz -> {host_model} (exists={host_model.exists()}); "
            f"anomaly_events.jsonl -> {host_anomaly} (exists={host_anomaly.exists()})",
            flush=True,
        )
    if (
        run_status == "completed"
        and train_mode == "fresh_bootstrap"
        and not dry_run
        and "som_model.npz" not in copied
    ):
        msg = (
            "completed fresh_bootstrap run but som_model.npz was not snapshotted "
            f"(source missing at {host_model}). Check compose file location and ./data/learner bind mount. "
            "If you used --mode smoke, paper+fresh_bootstrap runs are often too short—use --mode full for real "
            "campaigns, and confirm nothing else is bound to localhost:8100."
        )
        warnings.append(msg)
        print(f"WARNING: {msg}", flush=True)
        if strict:
            raise RuntimeError(msg)
    return warnings


def maybe_trim_for_smoke(matrix: dict) -> dict:
    m = json.loads(json.dumps(matrix))
    m["meta"]["repeats"] = 1
    # Tight caps for quick sanity runs (wall-clock dominates on large ablations).
    m["meta"]["warmup_s"] = min(10, int(m["meta"]["warmup_s"]))
    m["meta"]["bootstrap_s"] = min(15, int(m["meta"]["bootstrap_s"]))
    m["meta"]["inject_s"] = min(10, int(m["meta"]["inject_s"]))
    m["meta"]["cooldown_s"] = min(10, int(m["meta"]["cooldown_s"]))
    if isinstance(m["meta"].get("pending_window_s_ladder"), list) and m["meta"]["pending_window_s_ladder"]:
        m["meta"]["pending_window_s_ladder"] = [m["meta"]["pending_window_s_ladder"][0]]
    if isinstance(m["meta"].get("anomaly_quantile_ladder"), list) and m["meta"]["anomaly_quantile_ladder"]:
        m["meta"]["anomaly_quantile_ladder"] = m["meta"]["anomaly_quantile_ladder"][:3]
    m["faults"] = m["faults"][:3]
    for fault in m["faults"]:
        if isinstance(fault.get("intensity_ladder"), list) and fault["intensity_ladder"]:
            fault["intensity_ladder"] = [fault["intensity_ladder"][0]]
        if isinstance(fault.get("duration_ladder_s"), list) and fault["duration_ladder_s"]:
            fault["duration_ladder_s"] = [fault["duration_ladder_s"][0]]
    # Default BOOTSTRAP_SAMPLES=180 cannot finish before inject. Force 1s polling for smoke so every
    # variant shares the same budget, and cap BOOTSTRAP_SAMPLES to satisfy both the learner (warmup +
    # bootstrap wall time) and the evaluator (expected vectors use bootstrap_s only, not warmup).
    w_s = int(m["meta"]["warmup_s"])
    b_s = int(m["meta"]["bootstrap_s"])
    poll = 1.0
    learner_m = m.setdefault("learner", {})
    be = learner_m.setdefault("baseline_env", {})
    if not isinstance(be, dict):
        learner_m["baseline_env"] = {}
        be = learner_m["baseline_env"]
    be["POLL_SEC"] = "1.0"
    cap_eval = max(1, int(b_s / poll))
    cap_time = max(1, int((w_s + b_s) / poll) - 1)
    cap = min(cap_eval, cap_time)
    existing_bs = int(float(str(be["BOOTSTRAP_SAMPLES"]))) if "BOOTSTRAP_SAMPLES" in be else 180
    be["BOOTSTRAP_SAMPLES"] = str(min(existing_bs, cap))

    # Variants may override BOOTSTRAP_SAMPLES; cap them too or smoke runs will never train.
    variants = learner_m.get("variants", [])
    if isinstance(variants, list):
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            venv = variant.get("env", {})
            if not isinstance(venv, dict):
                continue
            if "BOOTSTRAP_SAMPLES" in venv:
                try:
                    v_existing = int(float(str(venv.get("BOOTSTRAP_SAMPLES"))))
                except Exception:
                    v_existing = cap
                venv["BOOTSTRAP_SAMPLES"] = str(min(v_existing, cap))
    return m


def log_phase(run_events: Path, run_cfg: RunConfig, phase: str, extra: dict | None = None) -> None:
    payload = {
        "type": "phase",
        "ts": time.time(),
        "run_id": run_cfg.run_id,
        "variant": run_cfg.variant_name,
        "fault_id": run_cfg.fault_id,
        "repeat_idx": run_cfg.repeat_idx,
        "phase": phase,
    }
    if extra:
        payload.update(extra)
    write_jsonl(run_events, payload)


def fault_event(run_events: Path, run_cfg: RunConfig, state: str) -> None:
    write_jsonl(
        run_events,
        {
            "type": "fault_window",
            "ts": time.time(),
            "run_id": run_cfg.run_id,
            "variant": run_cfg.variant_name,
            "fault_id": run_cfg.fault_id,
            "fault_family": run_cfg.fault_family,
            "study_scope": run_cfg.study_scope,
            "ablation_block": run_cfg.ablation_block,
            "hypothesis_id": run_cfg.hypothesis_id,
            "faithfulness_label": run_cfg.faithfulness_label,
            "repeat_idx": run_cfg.repeat_idx,
            "state": state,
            "pending_window_s": run_cfg.pending_window_s,
            "pending_level": run_cfg.pending_level,
            "intensity": run_cfg.fault_intensity,
            "intensity_level": run_cfg.intensity_level,
            "duration_level": run_cfg.duration_level,
            "duration_s": run_cfg.inject_s,
            "fault_window_on_delay_s": int(run_cfg.fault_window_on_delay_s),
        },
    )


def prediction_target_event(run_events: Path, run_cfg: RunConfig, target_kind: str) -> None:
    """Log proxy time t2 for UBL-style prediction (e.g. SLO violation) for the evaluator."""
    write_jsonl(
        run_events,
        {
            "type": "prediction_target",
            "ts": time.time(),
            "run_id": run_cfg.run_id,
            "variant": run_cfg.variant_name,
            "fault_id": run_cfg.fault_id,
            "repeat_idx": run_cfg.repeat_idx,
            "target_kind": target_kind,
        },
    )


def apply_learner_env(learner_env: Dict[str, str], dry_run: bool) -> None:
    env = os.environ.copy()
    env.update(learner_env)
    # Recreate learner so compose picks up environment substitutions.
    compose(["stop", "learner"], env=env, dry_run=dry_run)
    compose(["rm", "-f", "learner"], env=env, dry_run=dry_run)
    # --force-recreate avoids a stale container keeping old env (seen as wrong bootstrap_target / clip mode vs matrix).
    compose(["up", "-d", "--build", "--force-recreate", "learner"], env=env, dry_run=dry_run)


def _learner_reuse_signature(run_cfg: RunConfig) -> tuple[str, str]:
    return json.dumps(run_cfg.learner_env, sort_keys=True), run_cfg.train_mode


def ensure_learner_running(learner_env: Dict[str, str], dry_run: bool) -> None:
    """No rebuild; start learner if stopped (same image/env as last recreate)."""
    env = os.environ.copy()
    env.update(learner_env)
    compose(["up", "-d", "learner"], env=env, dry_run=dry_run)


def apply_loadgen_env(loadgen_env: Dict[str, str], dry_run: bool) -> None:
    compose(["stop", "loadgen"], env=loadgen_env, dry_run=dry_run)
    compose(["rm", "-f", "loadgen"], env=loadgen_env, dry_run=dry_run)
    compose(["up", "-d", "loadgen"], env=loadgen_env, dry_run=dry_run)


def load_matrix(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_run_configs(matrix: dict, campaign_id: str) -> List[RunConfig]:
    meta = matrix["meta"]
    fault_window_on_delay_s = int(float(meta.get("fault_window_on_delay_s", 0)))
    if fault_window_on_delay_s < 0:
        raise ValueError("meta.fault_window_on_delay_s must be >= 0")
    repeats = int(meta["repeats"])
    matrix_seeds = _collect_matrix_seeds(meta)
    use_ladders = bool(meta.get("use_ladders", False))
    out: List[RunConfig] = []
    for variant in matrix["learner"]["variants"]:
        variant_name = str(variant["name"])
        baseline_env = matrix.get("learner", {}).get("baseline_env", {})
        env = {k: str(v) for k, v in baseline_env.items()} if isinstance(baseline_env, dict) else {}
        env.update({k: str(v) for k, v in variant["env"].items()})
        pending_ladder = (
            _parse_ladder(meta.get("pending_window_s_ladder"), "base", float(meta["pending_window_s"]))
            if use_ladders
            else [{"level": "base", "value": float(meta["pending_window_s"])}]
        )
        baseline_q = float(str(env.get("ANOMALY_QUANTILE", "0.85")))
        quantile_ladder: List[Dict[str, Any]] = (
            _parse_ladder(meta.get("anomaly_quantile_ladder"), "base", baseline_q)
            if meta.get("anomaly_quantile_ladder")
            else [{"level": "base", "value": baseline_q}]
        )
        for fault in matrix["faults"]:
            base_intensity = float(fault.get("intensity", 1))
            intensity_ladder = (
                _parse_ladder(fault.get("intensity_ladder"), "base", base_intensity)
                if use_ladders
                else [{"level": "base", "value": base_intensity}]
            )
            duration_ladder = (
                _parse_ladder(fault.get("duration_ladder_s"), "base", float(fault.get("inject_s", meta["inject_s"])))
                if use_ladders
                else [{"level": "base", "value": float(fault.get("inject_s", meta["inject_s"]))}]
            )
            for intensity_cfg in intensity_ladder:
                intensity_value = float(intensity_cfg.get("value", base_intensity))
                intensity_level = str(intensity_cfg.get("level", "base"))
                fault_on_cmd = _render_command([str(x) for x in fault["command_on"]], intensity_value)
                fault_off_cmd = [str(x) for x in fault["command_off"]]
                for duration_cfg in duration_ladder:
                    duration_value = int(float(duration_cfg.get("value", meta["inject_s"])))
                    duration_level = str(duration_cfg.get("level", "base"))
                    for pending_cfg in pending_ladder:
                        pending_value = int(float(pending_cfg.get("value", meta["pending_window_s"])))
                        pending_level = str(pending_cfg.get("level", "base"))
                        for quantile_cfg in quantile_ladder:
                            q_value = float(quantile_cfg.get("value", baseline_q))
                            q_level = str(quantile_cfg.get("level", "base"))
                            q_suffix = f"-{q_level}" if len(quantile_ladder) > 1 else ""
                            for seed_idx, matrix_seed in enumerate(matrix_seeds, start=1):
                                for r in range(repeats):
                                    study_scope = _pick_tag_value(variant, fault, meta, "study_scope", "extended")
                                    ablation_block = _pick_tag_value(variant, fault, meta, "ablation_block", "fault")
                                    hypothesis_id = _pick_tag_value(variant, fault, meta, "hypothesis_id", "H0")
                                    interpretation_note = _pick_tag_value(variant, fault, meta, "interpretation_note", "")
                                    proxy_mapping = bool(fault.get("proxy_mapping", True))
                                    train_mode = str(variant.get("train_mode", meta.get("train_mode", "warm_start"))).strip().lower()
                                    run_seed = _derive_run_seed(
                                        int(matrix_seed),
                                        [
                                            variant_name,
                                            str(fault["id"]),
                                            intensity_level,
                                            duration_level,
                                            pending_level,
                                            q_level,
                                            str(seed_idx),
                                            str(r + 1),
                                        ],
                                    )
                                    run_id = (
                                        f"{campaign_id}-{variant_name}-{fault['id']}"
                                        f"-i{intensity_level}-d{duration_level}-w{pending_level}{q_suffix}"
                                        f"-s{seed_idx:02d}-r{r + 1:02d}"
                                    )
                                    learner_env = dict(env)
                                    learner_env["ANOMALY_QUANTILE"] = str(q_value)
                                    learner_env["UBL_RANDOM_SEED"] = str(run_seed)
                                    fe = fault.get("learner_env")
                                    if isinstance(fe, dict):
                                        learner_env.update({str(k): str(v) for k, v in fe.items()})
                                    out.append(
                                        RunConfig(
                                            run_id=run_id,
                                            variant_name=variant_name,
                                            fault_id=str(fault["id"]),
                                            fault_family=str(fault["family"]),
                                            study_scope=study_scope,
                                            ablation_block=ablation_block,
                                            hypothesis_id=hypothesis_id,
                                            interpretation_note=interpretation_note,
                                            faithfulness_label=_faithfulness_label(study_scope, str(fault["family"]), proxy_mapping),
                                            repeat_idx=r + 1,
                                            seed_idx=seed_idx,
                                            run_seed=run_seed,
                                            warmup_s=int(meta["warmup_s"]),
                                            bootstrap_s=int(meta["bootstrap_s"]),
                                            inject_s=duration_value,
                                            cooldown_s=int(meta["cooldown_s"]),
                                            fault_window_on_delay_s=fault_window_on_delay_s,
                                            pending_window_s=pending_value,
                                            pending_level=pending_level,
                                            intensity_level=intensity_level,
                                            duration_level=duration_level,
                                            train_mode=train_mode,
                                            fault_on=fault_on_cmd,
                                            fault_off=fault_off_cmd,
                                            fault_intensity=intensity_value,
                                            learner_env=learner_env,
                                            loadgen_seed=run_seed,
                                            anomaly_quantile_level=q_level,
                                        )
                                    )
    return out


def sleep_and_log(run_events: Path, run_cfg: RunConfig, phase: str, seconds: int, dry_run: bool) -> None:
    log_phase(run_events, run_cfg, phase, {"duration_s": int(seconds)})
    if not dry_run and seconds > 0:
        print(
            f"# {run_cfg.run_id} — {phase}: sleeping {seconds}s (no docker output during this window)",
            flush=True,
        )
        time.sleep(seconds)


def run_chaos(cmd: List[str], env: Dict[str, str], dry_run: bool) -> None:
    compose_retry(["--profile", "tools", "run", "--rm", "chaos"] + cmd, env=env, dry_run=dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run UBL fault-injection campaigns")
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--mode", choices=["full", "smoke"], default="smoke")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--override-repeats",
        type=int,
        default=None,
        help="Override matrix meta.repeats (useful for quick validation runs).",
    )
    parser.add_argument(
        "--allow-paper-fidelity-drift",
        action="store_true",
        help="Allow paper_faithful variants to run even when required paper-profile settings drift.",
    )
    parser.add_argument(
        "--resume-campaign-dir",
        type=Path,
        default=None,
        help="Resume an existing campaign directory and skip runs already marked completed.",
    )
    parser.add_argument(
        "--reuse-learner-if-env-unchanged",
        action="store_true",
        help=(
            "If learner env + train_mode match the previous run and train_mode is not fresh_bootstrap, "
            "skip stop/rm/up --build learner (large time saver). Consecutive faults share one SOM state."
        ),
    )
    parser.add_argument(
        "--allow-reuse-cross-fault",
        action="store_true",
        help="Allow learner reuse across runs for comparative studies (can confound independence).",
    )
    parser.add_argument(
        "--strict-artifact-snapshot",
        action="store_true",
        help=(
            "Fail the run if a completed fresh_bootstrap campaign finishes without copying "
            "som_model.npz into run artifacts (surfaces bind-mount / path issues)."
        ),
    )
    args = parser.parse_args()

    matrix = load_matrix(args.matrix)
    if args.override_repeats is not None:
        meta = matrix.get("meta", {})
        if not isinstance(meta, dict):
            meta = {}
            matrix["meta"] = meta
        meta["repeats"] = int(args.override_repeats)
    validate_matrix(matrix, allow_paper_fidelity_drift=bool(args.allow_paper_fidelity_drift))
    if args.mode == "smoke":
        matrix = maybe_trim_for_smoke(matrix)
    if args.resume_campaign_dir:
        resume_name = args.resume_campaign_dir.name
        if resume_name.startswith("campaign-"):
            campaign_id = resume_name.split("campaign-", 1)[1]
        else:
            campaign_id = resume_name
    else:
        campaign_id = now_iso()
    run_cfgs = build_run_configs(matrix, campaign_id=campaign_id)
    if args.reuse_learner_if_env_unchanged and not args.allow_reuse_cross_fault:
        raise ValueError(
            "--reuse-learner-if-env-unchanged requires --allow-reuse-cross-fault due to potential cross-fault state confounds."
        )
    if run_cfgs:
        paper_cfgs = [r for r in run_cfgs if str(r.study_scope).strip().lower() == "paper_faithful"]
        repeats = int(matrix.get("meta", {}).get("repeats", 1))
        if paper_cfgs and repeats < 30:
            print(
                f"# warning: paper-faithful protocol usually expects >=30 repeats; matrix has repeats={repeats}",
                flush=True,
            )
        min_sleep_s = sum(
            r.warmup_s
            + r.bootstrap_s
            + r.fault_window_on_delay_s
            + r.inject_s
            + r.cooldown_s
            for r in run_cfgs
        )
        print(
            f"# Planned runs: {len(run_cfgs)}; sum of phase sleeps "
            f"(warmup+bootstrap+fault_window_on_delay+inject+cooldown): "
            f"{min_sleep_s}s (~{min_sleep_s / 60:.1f} min). Docker/chaos/learner recreate adds more.\n",
            flush=True,
        )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if args.resume_campaign_dir:
        campaign_dir = args.resume_campaign_dir
        campaign_dir.mkdir(parents=True, exist_ok=True)
    else:
        campaign_dir = args.out_dir / f"campaign-{campaign_id}"
        campaign_dir.mkdir(parents=True, exist_ok=True)

    with (campaign_dir / "matrix.resolved.json").open("w", encoding="utf-8") as f:
        json.dump(matrix, f, indent=2, sort_keys=True)

    # Ensure latest app/chaos code is available before runs.
    bootstrap_env = os.environ.copy()
    compose(["build", "app", "chaos", "learner"], env=bootstrap_env, dry_run=args.dry_run)
    compose(
        ["up", "-d", "postgres", "downstream", "toxiproxy", "app", "prometheus", "cadvisor", "grafana"],
        env=bootstrap_env,
        dry_run=args.dry_run,
    )
    wait_for_app_ready(dry_run=args.dry_run)
    loadgen_enabled = bool(matrix.get("meta", {}).get("loadgen_enabled", True))
    base_seed = int(matrix.get("meta", {}).get("seed", 42))
    loadgen_env = configure_loadgen(matrix.get("meta", {}), bootstrap_env, seed=base_seed)
    if loadgen_enabled:
        compose(["up", "-d", "--build", "loadgen"], env=loadgen_env, dry_run=args.dry_run)

    compose_config_hash = _compose_config_sha256(bootstrap_env)
    compose_images = _docker_compose_images_json(bootstrap_env)
    campaign_meta = {
        "campaign_id": campaign_id,
        "campaign_dir": str(campaign_dir),
        "matrix_path": str(args.matrix),
        "mode": args.mode,
        "dry_run": bool(args.dry_run),
        "generated_at": time.time(),
        "matrix_name": str(matrix.get("meta", {}).get("name", "")),
        "matrix_description": str(matrix.get("meta", {}).get("description", "")),
        "comparator_scope": str(matrix.get("meta", {}).get("comparator_scope", "")),
        "matrix_seed": matrix.get("meta", {}).get("seed"),
        "matrix_seeds": _collect_matrix_seeds(matrix.get("meta", {})),
        "loadgen_enabled": loadgen_enabled,
        "loadgen_profile": str(matrix.get("meta", {}).get("loadgen_profile", "steady")),
        "loadgen_rps": float(matrix.get("meta", {}).get("loadgen_rps", 5.0)),
        "loadgen_ms": int(matrix.get("meta", {}).get("loadgen_ms", 20)),
        "loadgen_seed": base_seed,
        "git_sha": _git_sha(),
        "git_branch": _git_branch(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "run_count": len(run_cfgs),
        "reuse_learner_if_env_unchanged": bool(getattr(args, "reuse_learner_if_env_unchanged", False)),
        "allow_reuse_cross_fault": bool(getattr(args, "allow_reuse_cross_fault", False)),
        "allow_paper_fidelity_drift": bool(getattr(args, "allow_paper_fidelity_drift", False)),
        "compose_config_sha256": compose_config_hash,
        "compose_images": compose_images,
        "resumed_campaign_dir": str(args.resume_campaign_dir) if args.resume_campaign_dir else "",
    }
    with (campaign_dir / "campaign_meta.json").open("w", encoding="utf-8") as f:
        json.dump(campaign_meta, f, indent=2, sort_keys=True)

    run_index: List[dict[str, Any]] = []
    completed_run_ids: set[str] = set()
    run_index_path = campaign_dir / "run_index.json"
    if args.resume_campaign_dir and run_index_path.exists():
        try:
            run_index = json.loads(run_index_path.read_text(encoding="utf-8"))
            for row in run_index:
                if str(row.get("run_status", "")) == "completed":
                    completed_run_ids.add(str(row.get("run_id", "")))
            print(f"# resume mode: found {len(completed_run_ids)} completed runs to skip", flush=True)
        except Exception:
            run_index = []
            completed_run_ids = set()
    total_runs = len(run_cfgs)
    run_index_by_id: Dict[str, dict] = {}
    for row in run_index:
        rid = str(row.get("run_id", ""))
        if rid:
            run_index_by_id[rid] = row
    last_learner_sig: Optional[tuple[str, str]] = None
    for run_idx, run_cfg in enumerate(run_cfgs, start=1):
        if run_cfg.run_id in completed_run_ids:
            print(f"# skipping completed run {run_cfg.run_id}", flush=True)
            continue
        print(
            f"\n# --- Campaign run {run_idx}/{total_runs}: {run_cfg.run_id} "
            f"(variant={run_cfg.variant_name}, fault={run_cfg.fault_id}) ---\n",
            flush=True,
        )
        run_dir = campaign_dir / run_cfg.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        run_events = run_dir / "run_events.jsonl"
        run_meta = {
            "run_id": run_cfg.run_id,
            "variant": run_cfg.variant_name,
            "fault_id": run_cfg.fault_id,
            "fault_family": run_cfg.fault_family,
            "study_scope": run_cfg.study_scope,
            "ablation_block": run_cfg.ablation_block,
            "hypothesis_id": run_cfg.hypothesis_id,
            "interpretation_note": run_cfg.interpretation_note,
            "faithfulness_label": run_cfg.faithfulness_label,
            "repeat_idx": run_cfg.repeat_idx,
            "seed_idx": run_cfg.seed_idx,
            "run_seed": run_cfg.run_seed,
            "intensity_level": run_cfg.intensity_level,
            "duration_level": run_cfg.duration_level,
            "pending_level": run_cfg.pending_level,
            "train_mode": run_cfg.train_mode,
            "pending_window_s": run_cfg.pending_window_s,
            "durations_s": {
                "warmup": run_cfg.warmup_s,
                "bootstrap": run_cfg.bootstrap_s,
                "fault_window_on_delay": run_cfg.fault_window_on_delay_s,
                "inject": run_cfg.inject_s,
                "cooldown": run_cfg.cooldown_s,
            },
            "fault_window_on_delay_s": run_cfg.fault_window_on_delay_s,
            "fault_on": run_cfg.fault_on,
            "fault_off": run_cfg.fault_off,
            "fault_intensity": run_cfg.fault_intensity,
            "learner_env": run_cfg.learner_env,
            "loadgen_seed": run_cfg.loadgen_seed,
            "anomaly_quantile_level": run_cfg.anomaly_quantile_level,
            "load_profile": {
                "enabled": loadgen_enabled,
                "profile": str(matrix.get("meta", {}).get("loadgen_profile", "steady")),
                "rps": float(matrix.get("meta", {}).get("loadgen_rps", 5.0)),
                "work_ms": int(matrix.get("meta", {}).get("loadgen_ms", 20)),
            },
            "started_at": time.time(),
            "campaign_id": campaign_id,
            "matrix_seed": matrix.get("meta", {}).get("seed"),
            "run_status": "running",
            "failed_phase": "",
            "failure_reason": "",
            "learner_recreated": True,
        }
        run_index_by_id[run_cfg.run_id] = run_meta

        env = os.environ.copy()
        env.update(run_cfg.learner_env)
        run_loadgen_env = configure_loadgen(matrix.get("meta", {}), bootstrap_env, seed=run_cfg.loadgen_seed)
        sig = _learner_reuse_signature(run_cfg)
        reuse_learner = (
            bool(args.reuse_learner_if_env_unchanged)
            and last_learner_sig is not None
            and last_learner_sig == sig
            and run_cfg.train_mode != "fresh_bootstrap"
        )
        try:
            if loadgen_enabled:
                apply_loadgen_env(run_loadgen_env, dry_run=args.dry_run)
            # Always reset per-run alarm stream so evaluation isn't contaminated by prior runs.
            # Warm-start keeps the model weights, but alarm logs must be run-scoped.
            if not args.dry_run:
                anomaly_file = DATA_DIR / "learner" / "events" / "anomaly_events.jsonl"
                if anomaly_file.exists():
                    anomaly_file.unlink()
                score_stream_file = DATA_DIR / "learner" / "events" / "score_stream.jsonl"
                if score_stream_file.exists():
                    score_stream_file.unlink()

            if run_cfg.train_mode == "fresh_bootstrap" and not args.dry_run:
                model_file = DATA_DIR / "learner" / "model" / "som_model.npz"
                if model_file.exists():
                    model_file.unlink()
            if reuse_learner:
                print(
                    "# skipping learner stop/rm/up --build (same env as previous run; "
                    "see --reuse-learner-if-env-unchanged)",
                    flush=True,
                )
                run_meta["learner_recreated"] = False
                ensure_learner_running(run_cfg.learner_env, dry_run=args.dry_run)
            else:
                run_meta["learner_recreated"] = True
                apply_learner_env(run_cfg.learner_env, dry_run=args.dry_run)
            wait_for_app_ready(dry_run=args.dry_run)
            last_learner_sig = sig
            run_chaos(["reset"], env=env, dry_run=args.dry_run)
            sleep_and_log(run_events, run_cfg, "warmup", run_cfg.warmup_s, args.dry_run)
            sleep_and_log(run_events, run_cfg, "bootstrap", run_cfg.bootstrap_s, args.dry_run)
            learner_model_path = DATA_DIR / "learner" / "model" / "som_model.npz"
            learner_wait_s = max(60, int(run_cfg.warmup_s + run_cfg.bootstrap_s + 60))
            wait_for_learner_trained(
                model_path=learner_model_path,
                timeout_s=learner_wait_s,
                dry_run=args.dry_run,
            )
            st = fetch_learner_status(dry_run=args.dry_run)
            if isinstance(st, dict):
                run_meta["learner_status_post_bootstrap"] = {
                    "trained": st.get("trained"),
                    "bootstrap_samples": st.get("bootstrap_samples"),
                    "bootstrap_target": st.get("bootstrap_target"),
                    "total_samples": st.get("total_samples"),
                    "threshold": st.get("threshold"),
                    "model_path": st.get("model_path"),
                }

            log_phase(run_events, run_cfg, "inject_start")
            run_chaos(run_cfg.fault_on, env=env, dry_run=args.dry_run)
            if run_cfg.fault_window_on_delay_s > 0:
                sleep_and_log(
                    run_events,
                    run_cfg,
                    "fault_window_on_delay",
                    run_cfg.fault_window_on_delay_s,
                    args.dry_run,
                )
            fault_event(run_events, run_cfg, "on")

            meta_block = matrix.get("meta", {})
            pred_mode = str(meta_block.get("prediction_target_mode", "injection_onset")).strip().lower()
            slo_delay = int(float(meta_block.get("slo_violation_proxy_delay_s", 0) or 0))
            if pred_mode == "slo_violation_proxy" and slo_delay <= 0:
                slo_delay = int(float(meta_block.get("baseline_slo_window_s", 30) or 30))
            inject_total = int(run_cfg.inject_s)
            if pred_mode == "slo_violation_proxy" and slo_delay > 0:
                first = min(slo_delay, inject_total)
                sleep_and_log(run_events, run_cfg, "inject_hold", first, args.dry_run)
                prediction_target_event(run_events, run_cfg, "slo_violation_proxy")
                rest = inject_total - first
                if rest > 0:
                    sleep_and_log(run_events, run_cfg, "inject_hold", rest, args.dry_run)
            else:
                sleep_and_log(run_events, run_cfg, "inject_hold", inject_total, args.dry_run)

            log_phase(run_events, run_cfg, "inject_stop")
            run_chaos(run_cfg.fault_off, env=env, dry_run=args.dry_run)
            fault_event(run_events, run_cfg, "off")

            sleep_and_log(run_events, run_cfg, "cooldown", run_cfg.cooldown_s, args.dry_run)
            run_chaos(["reset"], env=env, dry_run=args.dry_run)
            run_meta["run_status"] = "completed"
        except Exception as exc:
            run_meta["run_status"] = "failed"
            run_meta["failure_reason"] = str(exc)
            run_meta["failed_phase"] = "execution"
            log_phase(run_events, run_cfg, "failed", {"error": str(exc)})
            try:
                run_chaos(["reset"], env=env, dry_run=args.dry_run)
            except Exception:
                pass
        snap_warnings = snapshot_artifacts(
            run_dir,
            run_status=str(run_meta.get("run_status", "")),
            train_mode=str(run_cfg.train_mode),
            dry_run=args.dry_run,
            strict=bool(args.strict_artifact_snapshot),
        )
        if snap_warnings:
            run_meta["artifact_snapshot_warnings"] = snap_warnings
        if run_meta["run_status"] == "completed":
            log_phase(run_events, run_cfg, "completed")

        with (run_dir / "manifest.json").open("w", encoding="utf-8") as f:
            json.dump(run_meta, f, indent=2, sort_keys=True)

    with (campaign_dir / "run_index.json").open("w", encoding="utf-8") as f:
        json.dump(sorted(run_index_by_id.values(), key=lambda x: str(x.get("run_id", ""))), f, indent=2, sort_keys=True)

    print(f"Campaign written to: {campaign_dir}")


if __name__ == "__main__":
    main()
