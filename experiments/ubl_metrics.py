from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Literal, Sequence

AlarmTimeFilter = Literal["all", "before_any_future_fault_start"]
PredictionTargetSource = Literal["auto", "injection_onset", "slo_proxy"]


@dataclass(frozen=True)
class Alarm:
    ts: float
    score: float
    threshold: float
    fault_id: str | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class FaultWindow:
    fault_id: str
    start_ts: float
    end_ts: float
    run_id: str | None = None


@dataclass(frozen=True)
class PredictionSummary:
    """UBL-style prediction metrics.

    Legacy ``tn`` / ``fpr``: the historical proxy forces ``tn == tp`` (each alarm is TP or FP),
    so ``fpr == fp / (fp + tp) == alarm_fp_fraction`` (not Equation 5 AF from the paper).

    Paper-style rates (Section 3, Eq. 5) use ``paper_ntn`` tick opportunities during the
    pre-fault normal window and ``paper_af`` = fp / (fp + paper_ntn).
    """

    tp: int
    fp: int
    fn: int
    tn: int
    tpr: float
    fpr: float
    precision: float
    recall: float
    f1: float
    mean_lead_time_s: float
    median_lead_time_s: float
    num_scored_alarms: int
    pending_window_s: float
    alarm_fp_fraction: float
    paper_ntn: int
    paper_nfp: int
    paper_af: float
    paper_at: float
    normal_window_ticks: int
    num_alarms_before_first_target: int
    prediction_target_source: str


def _safe_div(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return a / b


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    n = len(ordered)
    m = n // 2
    if n % 2 == 1:
        return float(ordered[m])
    return float((ordered[m - 1] + ordered[m]) / 2.0)


def filter_alarms_by_time(
    alarms: Sequence[Alarm],
    fault_start_ts: Sequence[float],
    mode: AlarmTimeFilter = "before_any_future_fault_start",
) -> List[Alarm]:
    """
    Drop alarms that cannot precede any unevaluated fault start (streaming dedupe).

    For a single fault, removes all post-onset alarms so they are not counted as FP
    while recall still uses the full alarm list semantics inside ``evaluate_predictions``
    (caller passes filtered list for alarm-level TP/FP only — see evaluate_predictions).
    """
    if mode == "all":
        return list(alarms)
    starts = sorted(float(s) for s in fault_start_ts)
    if not starts:
        return list(alarms)
    out: List[Alarm] = []
    for a in alarms:
        if any(a.ts < s for s in starts):
            out.append(a)
    return out


def _paper_ntn_ticks(
    *,
    post_bootstrap_ts: float | None,
    first_target_ts: float | None,
    poll_sec: float,
    num_alarms_before_target: int,
) -> tuple[int, int]:
    """
    Approximate Ntn for AF = Nfp / (Nfp + Ntn) (UBL paper Eq. 5).

    Counts discrete poll-sized slots in [post_bootstrap, first_target) minus alarms
    logged before the target (each alarm ~ one slot consumed). This matches the
    paper's idea of normal-operation trials where a false alarm did not occur.
    """
    if (
        post_bootstrap_ts is None
        or first_target_ts is None
        or first_target_ts <= post_bootstrap_ts
        or poll_sec <= 0
    ):
        return 0, 0
    ticks = int(max(0.0, (first_target_ts - post_bootstrap_ts) / poll_sec))
    ntn = max(0, ticks - int(num_alarms_before_target))
    return ticks, ntn


def evaluate_predictions(
    alarms: Iterable[Alarm],
    fault_windows: Iterable[FaultWindow],
    pending_window_s: float,
    matching_mode: str = "many_to_many",
    alarm_time_filter: AlarmTimeFilter = "before_any_future_fault_start",
    *,
    post_bootstrap_ts: float | None = None,
    normal_window_end_ts: float | None = None,
    poll_sec: float = 1.0,
    prediction_target_source: str = "injection_onset",
) -> PredictionSummary:
    """
    Evaluate UBL-style prediction quality.

    TP (per alarm): alarm at t1 where a target time t2 satisfies t1 < t2 < t1 + W.
    FP: alarm that does not predict any target start within W.
    FN: target time not predicted by any alarm in (t2-W, t2).

    Legacy TN proxy (see module docstring): with ``positives = len(starts)``,
    ``negatives = len(alarms)`` so ``tn = len(alarms) - fp = tp`` and
    ``fpr = fp / (fp + tp)``.

    ``alarm_time_filter="before_any_future_fault_start"`` removes alarms at or after
    all fault targets so streaming post-onset alarms are not counted as FP.

    Paper AF uses ``paper_ntn`` over the pre-injection normal window (see ``_paper_ntn_ticks``);
    ``normal_window_end_ts`` should be fault injection onset (``fault_window`` on).

    Matching targets (``fault_windows[].start_ts``) may use an SLO proxy time when provided.
    """
    windows: List[FaultWindow] = sorted(list(fault_windows), key=lambda x: x.start_ts)
    starts = [w.start_ts for w in windows]

    alarm_list: List[Alarm] = sorted(list(alarms), key=lambda x: x.ts)
    num_before_target = sum(
        1 for a in alarm_list if normal_window_end_ts is None or a.ts < normal_window_end_ts
    )
    alarm_list = filter_alarms_by_time(alarm_list, starts, mode=alarm_time_filter)

    tp = 0
    fp = 0
    lead_times: List[float] = []

    mode = str(matching_mode or "many_to_many").strip().lower()
    if mode == "one_to_one":
        unmatched_starts: List[float] = list(starts)
        for alarm in alarm_list:
            match_idx = None
            for idx, start in enumerate(unmatched_starts):
                if alarm.ts < start < (alarm.ts + pending_window_s):
                    match_idx = idx
                    break
            if match_idx is None:
                fp += 1
            else:
                matched_start = unmatched_starts.pop(match_idx)
                tp += 1
                lead_times.append(matched_start - alarm.ts)
        fn = len(unmatched_starts)
    else:
        for alarm in alarm_list:
            matched_start = None
            for start in starts:
                if alarm.ts < start < (alarm.ts + pending_window_s):
                    matched_start = start
                    break
            if matched_start is None:
                fp += 1
            else:
                tp += 1
                lead_times.append(matched_start - alarm.ts)

        fn = 0
        for start in starts:
            predicted = any((a.ts < start and a.ts + pending_window_s > start) for a in alarm_list)
            if not predicted:
                fn += 1

    # Legacy TN proxy: with positives=len(starts), negatives=len(alarms) => tn = |alarms| - fp = tp.
    positives = len(starts)
    negatives = max(0, len(alarm_list) + len(starts) - positives)
    tn = max(0, negatives - fp)

    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    f1 = _safe_div(2.0 * precision * recall, precision + recall)
    tpr = recall
    fpr = _safe_div(fp, fp + tn)
    alarm_fp_fraction = _safe_div(fp, fp + tp)

    normal_window_ticks, paper_ntn = _paper_ntn_ticks(
        post_bootstrap_ts=post_bootstrap_ts,
        first_target_ts=normal_window_end_ts,
        poll_sec=poll_sec,
        num_alarms_before_target=num_before_target,
    )
    paper_nfp = fp
    paper_af = _safe_div(float(paper_nfp), float(paper_nfp + paper_ntn))
    paper_at = tpr

    mean_lead = _safe_div(sum(lead_times), len(lead_times))
    median_lead = _median(lead_times)

    return PredictionSummary(
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        tpr=tpr,
        fpr=fpr,
        precision=precision,
        recall=recall,
        f1=f1,
        mean_lead_time_s=mean_lead,
        median_lead_time_s=median_lead,
        num_scored_alarms=len(alarm_list),
        pending_window_s=float(pending_window_s),
        alarm_fp_fraction=alarm_fp_fraction,
        paper_ntn=paper_ntn,
        paper_nfp=paper_nfp,
        paper_af=paper_af,
        paper_at=paper_at,
        normal_window_ticks=normal_window_ticks,
        num_alarms_before_first_target=num_before_target,
        prediction_target_source=prediction_target_source,
    )
