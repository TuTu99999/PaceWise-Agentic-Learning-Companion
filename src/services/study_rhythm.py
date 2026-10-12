"""Conservative rhythm proposals, not inferred attention spans/mastery scores.

Thresholds are versioned engineering policy pending a real learner pilot.
No cross-course/task transfer or synthetic claim of educational improvement.
"""
import hashlib
import json
from collections import defaultdict
from math import isfinite
from statistics import median

from src.services.assessment_review_policy import planning_evidence_usable
from src.services.study_activity import ACTIVITY_TYPES, effective_rhythm

POLICY = "rhythm-rule-v2-course-activity"
MIN_SESSIONS = 3
INTERRUPTIONS = {"none", "unexpected", "fatigue", "difficulty", "outside", "unknown"}
LENGTH_FEELINGS = {"not_reported", "comfortable", "long", "too_long"}


def observed_minutes(value) -> float:
    return float(value) if isinstance(value, (int, float)) and isfinite(value) and value >= 0 else 0.0


def summarize_independent_assessment(evidence: list[dict]) -> tuple[dict, list[str]]:
    """Latest accepted attempt per KC; another KC cannot conceal a failure.

    Caller supplies chronological, server-owned evidence. Assisted or pending
    review observations remain auditable but do not establish independence.
    """
    by_component: dict[str, dict] = defaultdict(dict)
    refs = []
    for item in evidence:
        if not planning_evidence_usable(item) or item.get("hint_level", 0):
            continue
        components = item.get("knowledge_component_ids") or []
        if not components or not item.get("id"):
            continue
        tested = {name: outcome for name, outcome in item.get("dimensions", {}).items()
                  if outcome in {"passed", "failed"}}
        if tested:
            refs.append(item["id"])
            for component in components:
                by_component[component].update(tested)
    summary = {}
    for dimensions in by_component.values():
        for dimension, outcome in dimensions.items():
            summary[dimension] = "failed" if outcome == "failed" or summary.get(dimension) == "failed" else "passed"
    return summary, refs


def propose_rhythm(observations: list[dict], preferences: dict) -> dict:
    current = {"sessionMinutes": preferences.get("sessionMinutes", 90), "breakMinutes": preferences.get("breakMinutes", 10)}
    result = {"policy": POLICY, "current": current, "proposal": None,
              "status": "insufficient_evidence", "excludedCount": 0,
              "limitations": ["Engineering policy; not an optimal attention span or a calibrated learning effect.",
                             "Assessment absent means learning quality is unknown."]}
    if not preferences.get("adaptiveSuggestionsEnabled", True):
        return {**result, "status": "disabled"}
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for observation in observations:
        activity = observation.get("activity_type")
        scoped_current = effective_rhythm(preferences, observation.get("course_id"), activity)
        # Repeated fatigue halfway through a session may justify a small trial;
        # unexpected work interruptions and a single difficult session never do.
        exposure = 0.5 if observation.get("interruption_reason") == "fatigue" else 0.75
        if (observation.get("interruption_reason") not in {"none", "fatigue"}
                or observation.get("unobserved_gap")
                or observation.get("time_source") != "timer"
                or activity not in ACTIVITY_TYPES
                or observation.get("rhythm") != scoped_current
                or observation.get("checkpoint_minutes", 0) != preferences.get("checkpointMinutes", 0)
                or not observation.get("session_id")
                or not observation.get("course_id") or not observation.get("task_id")
                or not observation.get("readiness_key")
                or observation.get("length_feeling") not in {"long", "too_long"}
                # Already-short milestone blocks are not evidence that the
                # larger preferred cap itself needs shortening.
                or observed_minutes(observation.get("planned_minutes")) < scoped_current["sessionMinutes"]
                or observed_minutes(observation.get("actual_minutes")) < max(20, scoped_current["sessionMinutes"] * exposure)
                or scoped_current["sessionMinutes"] <= 20):
            result["excludedCount"] += 1
            continue
        # Require same task AND baseline readiness, not merely the same learner.
        groups[(observation.get("course_id"), activity, observation.get("task_id"), observation.get("readiness_key"))].append(observation)
    eligible = [items for items in groups.values() if len({item["session_id"] for item in items}) >= MIN_SESSIONS]
    if not eligible:
        return result
    chosen = max(eligible, key=lambda items: max(item.get("recorded_at", "") for item in items))
    distinct = {item["session_id"]: item for item in chosen}
    selected = sorted(distinct.values(), key=lambda item: item.get("recorded_at", ""))[-5:]
    current = effective_rhythm(preferences, selected[0]["course_id"], selected[0]["activity_type"])
    proposed = {**current, "sessionMinutes": max(20, current["sessionMinutes"] - 15)}
    refs = [f"do:{item['session_id']}" for item in selected]
    assessment_refs = sorted({ref for item in selected for ref in item.get("assessment_evidence_ids", [])})
    proposal = {"preferences": proposed, "sourceRefs": refs, "assessmentEvidenceIds": assessment_refs,
                "learningQuality": "not_comparatively_validated", "requiresConfirmation": True,
                "taskId": selected[0]["task_id"], "courseId": selected[0]["course_id"],
                "activityType": selected[0]["activity_type"],
                "reason": "Repeated reports of long sessions on the same task at the same baseline readiness; try a shorter session, keeping total work unchanged."}
    fingerprint = json.dumps({"policy": POLICY, "current": current, "checkpointMinutes": preferences.get("checkpointMinutes", 0), "proposal": proposal}, sort_keys=True)
    proposal["id"] = hashlib.sha256(fingerprint.encode()).hexdigest()[:32]
    return {**result, "current": current, "status": "trial_proposed", "proposal": proposal}


def compare_rhythm_trial(observations: list[dict], trial: dict | None) -> dict:
    """Within-learner descriptive comparison; never a causal learning claim."""
    result = {"status": "no_trial", "before": None, "after": None,
              "limitations": ["Observational comparison; task stages/difficulty can differ.",
                             "No synthetic or real samples imply educational effectiveness on their own."]}
    if not trial:
        return result
    refs = set(trial.get("sourceRefs") or [])
    baseline = [item for item in observations if f"do:{item.get('session_id')}" in refs]
    if not baseline:
        return {**result, "status": "baseline_unavailable"}
    readiness = baseline[0].get("readiness_key")
    comparable = [item for item in observations
                  if item.get("task_id") == trial.get("taskId") and item.get("course_id") == trial.get("courseId")
                  and item.get("activity_type") == trial.get("activityType")
                  and item.get("checkpoint_minutes", 0) == baseline[0].get("checkpoint_minutes", 0)
                  and item.get("readiness_key") == readiness
                  and not item.get("unobserved_gap") and item.get("interruption_reason") in {"none", "fatigue"}
                  and item.get("time_source") == "timer"]
    comparable = list({item.get("session_id"): item for item in comparable if item.get("session_id")}.values())
    before = [item for item in comparable if f"do:{item.get('session_id')}" in refs]
    after = [item for item in comparable if f"do:{item.get('session_id')}" not in refs and item.get("rhythm") == trial.get("preferences")
             and item.get("recorded_at", "") >= trial.get("accepted_at", "")]
    def summarize(items):
        if not items:
            return {"sessions": 0, "completionRate": None, "longSessionRate": None, "assistedAssessmentRate": None, "medianRecordedMinutes": None, "assessment": {}}
        dimensions = {}
        for dimension in ("conceptual", "application", "transfer", "retention"):
            tested = [item["assessment_summary"][dimension] for item in items
                      if item.get("assessment_summary", {}).get(dimension) in {"passed", "failed"}]
            dimensions[dimension] = {"testedSessions": len(tested), "passRate": tested.count("passed") / len(tested) if tested else None}
        reported = [item for item in items if item.get("length_feeling") in {"comfortable", "long", "too_long"}]
        hint_observed = [item for item in items if isinstance(item.get("hint_count"), int)]
        return {"sessions": len(items), "completionRate": sum(item.get("completion_percent") == 100 for item in items) / len(items),
                "longSessionRate": sum(item["length_feeling"] in {"long", "too_long"} for item in reported) / len(reported) if reported else None,
                "assistedAssessmentRate": sum(item["hint_count"] > 0 for item in hint_observed) / len(hint_observed) if hint_observed else None,
                "medianRecordedMinutes": median(item["actual_minutes"] for item in items), "assessment": dimensions}
    return {**result, "status": "descriptive_not_causal" if min(len(before), len(after)) >= MIN_SESSIONS else "collecting",
            "before": summarize(before), "after": summarize(after)}
