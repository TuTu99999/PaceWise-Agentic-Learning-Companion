"""Deterministic policy for routing, validating and applying Reflect hypotheses.

The model is an analyst only.  It may describe a plausible explanation, but it
cannot change duration factors, allocate minutes, edit the calendar or update
knowledge state.  Those decisions are derived here from server-owned evidence.
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any

from src.services.planning_signals import CAUSES, normalize_planning_signal

RECOMMENDED_ACTIONS = frozenset(
    {
        "none",
        "collect_more_evidence",
        "complete_remaining_work",
        "review_verified_kc",
        "split_task",
        "recover_schedule",
        "keep_current_plan",
    }
)

KNOWLEDGE_CAUSES = frozenset({"knowledge_gap", "misconception", "missing_prerequisite"})
TIMING_CAUSES = frozenset({"estimate_error", "task_harder_than_expected"})


def _normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value or "").casefold())
    return " ".join("".join(char for char in text if unicodedata.category(char) != "Mn").split())


def _number(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _sessions(metrics: dict) -> list[dict[str, Any]]:
    return [item for item in metrics.get("sessions") or [] if isinstance(item, dict)]


def _session_count(metrics: dict) -> int:
    return max(0, round(_number(metrics.get("session_count"), len(_sessions(metrics)))))


def _remaining_minutes(metrics: dict) -> int:
    rows = _sessions(metrics)
    if not rows and isinstance(metrics.get("activity"), dict):
        rows = [metrics["activity"]]
    return sum(max(0, min(1440, round(_number(item.get("remaining_minutes"))))) for item in rows)


def _observed_numbers(value: object, *, parent_key: str = "") -> set[str]:
    """Collect numbers from factual fields, excluding opaque identifiers."""
    if isinstance(value, dict):
        result: set[str] = set()
        for key, item in value.items():
            if any(token in str(key).casefold() for token in ("id", "ref", "hash")):
                continue
            result.update(_observed_numbers(item, parent_key=str(key)))
        return result
    if isinstance(value, list):
        result: set[str] = set()
        for item in value:
            result.update(_observed_numbers(item, parent_key=parent_key))
        return result
    if isinstance(value, bool) or value is None:
        return set()
    if isinstance(value, (int, float)):
        number = _number(value)
        return {str(int(number)) if number.is_integer() else str(number).rstrip("0").rstrip(".")}
    return set(re.findall(r"(?<![\w:-])\d+(?:[.,]\d+)?(?![\w:-])", str(value)))


def _safe_hypothesis_text(value: object, metrics: dict, warnings: list[str]) -> str:
    text = str(value or "").strip()[:700]
    claimed = {token.replace(",", ".") for token in re.findall(r"\d+(?:[.,]\d+)?", text)}
    observed = {token.replace(",", ".") for token in _observed_numbers(metrics)}
    if claimed - observed:
        warnings.append("UNSUPPORTED_NUMERIC_CLAIM")
        return ""
    return text


def verified_assessment_kcs(metrics: dict) -> set[str]:
    """Return only KCs with an observed gap or confirmed misconception."""
    result: set[str] = set()
    for item in metrics.get("assessment_evidence") or []:
        if not isinstance(item, dict):
            continue
        dimensions = item.get("dimensions") if isinstance(item.get("dimensions"), dict) else {}
        misconceptions = item.get("misconceptions") if isinstance(item.get("misconceptions"), list) else []
        gap_observed = any(value in {"failed", "developing"} for value in dimensions.values())
        misconception_confirmed = any(
            isinstance(value, dict) and value.get("status") == "confirmed" for value in misconceptions
        )
        if not (item.get("valid") is True and (gap_observed or misconception_confirmed)):
            continue
        values = item.get("knowledge_component_ids") or item.get("knowledge_components") or []
        if isinstance(values, str):
            values = [values]
        for value in values:
            text = str(value or "").strip()[:160]
            if text:
                result.add(text)
        for key in ("knowledge_component", "kc_id"):
            text = str(item.get(key) or "").strip()[:160]
            if text:
                result.add(text)
    return result


def _has_verified_assessment(metrics: dict) -> bool:
    for item in metrics.get("assessment_evidence") or []:
        if not isinstance(item, dict) or item.get("valid") is not True:
            continue
        dimensions = item.get("dimensions") if isinstance(item.get("dimensions"), dict) else {}
        if dimensions or item.get("score") is not None or item.get("level") is not None:
            return True
    return False


def route_reflection(scope: str, metrics: dict, student_report: str) -> dict[str, Any]:
    """Route activity/simple weekly summaries to Luna and complex weeks to Sol."""
    sessions = _sessions(metrics)
    count = _session_count(metrics)
    reasons: list[str] = []
    if scope == "weekly" and count >= 3:
        courses = {
            str(item.get("course_id") or item.get("course_code") or "").strip()
            for item in sessions
            if item.get("course_id") or item.get("course_code")
        }
        if len(courses) > 1:
            reasons.append("multiple_courses")
        if _has_verified_assessment(metrics):
            reasons.append("verified_assessment")
        if sum(bool(item.get("missed") or item.get("status") in {"missed", "late", "overdue"}) for item in sessions) >= 2:
            reasons.append("repeated_missed_or_late")
        deviations = 0
        for item in sessions:
            planned = _number(item.get("planned_minutes"))
            actual = _number(item.get("actual_minutes"))
            if planned > 0 and abs(actual - planned) / planned >= 0.25:
                deviations += 1
        if deviations >= 2:
            reasons.append("repeated_timing_deviation")
        normalized = _normalize_text(student_report)
        claims_done = any(term in normalized for term in ("hoan thanh het", "da xong het", "completed everything"))
        observed_incomplete = _remaining_minutes(metrics) > 0 or any(
            _number(item.get("completion_percent"), 100) < 100 for item in sessions
        )
        if claims_done and observed_incomplete:
            reasons.append("self_report_conflict")
        possible_causes = sum(
            any(term in normalized for term in terms)
            for terms in (
                ("khong hieu", "chua hieu", "confused"),
                ("thieu thoi gian", "khong du thoi gian"),
                ("xao nhang", "gian doan"),
                ("met", "fatigue"),
                ("trung lich", "xung dot lich"),
            )
        )
        if possible_causes >= 2:
            reasons.append("multiple_plausible_causes")
    complex_week = scope == "weekly" and count >= 3 and bool(reasons)
    return {
        "scope": scope,
        "complexity": "complex" if complex_week else "simple",
        "model_tier": "sol" if complex_week else "luna",
        "reasons": reasons,
        "session_count": count,
    }


def validate_hypothesis(
    raw: object,
    *,
    metrics: dict,
    trusted_task_ids: set[str],
    trusted_kcs: set[str],
) -> tuple[dict[str, Any], list[str]]:
    """Validate model analysis without granting it any planning authority."""
    value = raw if isinstance(raw, dict) else {}
    warnings: list[str] = []
    original_cause = str(value.get("cause") or "unknown").strip().casefold().replace(" ", "_")
    cause = original_cause if original_cause in CAUSES else "unknown"
    if cause != original_cause:
        warnings.append("UNRECOGNIZED_CAUSE")

    try:
        confidence = min(1.0, max(0.0, float(value.get("confidence", 0.0))))
    except (TypeError, ValueError, OverflowError):
        confidence = 0.0
        warnings.append("INVALID_CONFIDENCE")

    task_id = str(value.get("task_id") or "").strip()[:160]
    if task_id and task_id not in trusted_task_ids:
        task_id = ""
        warnings.append("UNKNOWN_TASK_ID")

    affected = value.get("affected_kcs") or []
    if isinstance(affected, str):
        affected = [affected]
    affected_kcs = [
        item for item in dict.fromkeys(str(item).strip()[:160] for item in affected) if item in trusted_kcs
    ] if isinstance(affected, list) else []
    if affected and not affected_kcs:
        warnings.append("UNVERIFIED_KC")

    count = _session_count(metrics)
    verified_kcs = verified_assessment_kcs(metrics)
    schedule_observed = bool(metrics.get("schedule_conflicts")) or any(
        item.get("blocker") == "schedule_conflict" for item in _sessions(metrics)
    )
    if count < 2 and cause not in {"none", "unknown"}:
        cause = "unknown"
        confidence = min(confidence, 0.49)
        warnings.append("INSUFFICIENT_CAUSAL_EVIDENCE")
    elif cause in KNOWLEDGE_CAUSES and not verified_kcs:
        cause = "unknown"
        confidence = min(confidence, 0.49)
        warnings.append("KNOWLEDGE_CAUSE_NOT_VERIFIED")
    elif cause == "schedule_conflict" and not schedule_observed:
        cause = "unknown"
        confidence = min(confidence, 0.49)
        warnings.append("SCHEDULE_CONFLICT_NOT_OBSERVED")

    action = str(value.get("recommended_action") or "none").strip().casefold().replace(" ", "_")
    if action not in RECOMMENDED_ACTIONS:
        action = "none"
        warnings.append("UNRECOGNIZED_ACTION")

    # Any planning fields returned by a model are deliberately ignored.
    if isinstance(value.get("planning_signal"), dict) or any(
        key in value for key in ("duration_factor", "follow_up_minutes", "scheduled_at", "deadline")
    ):
        warnings.append("MODEL_PLANNING_FIELDS_IGNORED")

    effective = _safe_hypothesis_text(value.get("effective"), metrics, warnings)
    difficulty = _safe_hypothesis_text(
        value.get("difficulty") or value.get("deviation_cause"), metrics, warnings
    )
    rationale = _safe_hypothesis_text(value.get("rationale"), metrics, warnings)

    return (
        {
            "effective": effective,
            "difficulty": difficulty,
            "cause": cause,
            "confidence": round(confidence, 2),
            "recommended_action": action,
            "rationale": rationale,
            "task_id": task_id,
            "affected_kcs": affected_kcs,
        },
        list(dict.fromkeys(warnings)),
    )


def recommend_reflection(
    hypothesis: dict,
    *,
    metrics: dict,
    calibration_count: int,
    calibration_factor: float,
    trusted_task_ids: set[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Convert a validated hypothesis into one deterministic recommendation."""
    cause = str(hypothesis.get("cause") or "unknown")
    verified_kcs = verified_assessment_kcs(metrics)
    remaining = _remaining_minutes(metrics)
    task_id = str(hypothesis.get("task_id") or "")
    if not task_id and len(trusted_task_ids) == 1:
        task_id = next(iter(trusted_task_ids))

    recommendation = {
        "action": "collect_more_evidence",
        "minutes": 0,
        "duration_factor": 1.0,
        "requires_recover": False,
        "reason": "insufficient_stable_evidence",
        "affected_kcs": [],
        "task_id": task_id,
    }
    if remaining > 0:
        recommendation.update(
            action="complete_remaining_work",
            minutes=remaining,
            requires_recover=True,
            reason="observed_remaining_work",
        )
    elif cause in KNOWLEDGE_CAUSES and verified_kcs:
        selected = sorted(verified_kcs & set(hypothesis.get("affected_kcs") or [])) or sorted(verified_kcs)
        recommendation.update(
            action="review_verified_kc",
            minutes=15,
            requires_recover=True,
            reason="verified_assessment_gap",
            affected_kcs=selected[:3],
        )
    elif cause == "schedule_conflict":
        recommendation.update(
            action="recover_schedule",
            requires_recover=True,
            reason="observed_schedule_conflict",
        )
    elif cause in TIMING_CAUSES and calibration_count >= 3:
        recommendation.update(
            action="split_task" if calibration_factor > 1.15 else "keep_current_plan",
            duration_factor=round(min(1.5, max(0.75, calibration_factor)), 2),
            reason="stable_homogeneous_timing_evidence",
        )

    signal = normalize_planning_signal(
        {
            "cause": cause,
            "duration_factor": recommendation["duration_factor"],
            "follow_up_minutes": recommendation["minutes"]
            if recommendation["action"] == "review_verified_kc"
            else 0,
            "affected_kcs": recommendation["affected_kcs"],
            "task_id": recommendation["task_id"],
        }
    )
    return recommendation, signal
