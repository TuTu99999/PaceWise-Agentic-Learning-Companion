"""Deterministic intelligence used around the Plan LLM.

The language model may interpret an assignment and propose milestones.  This
module owns the parts that must be reproducible and auditable: rubric parsing,
knowledge-component provenance, learner evidence adaptation, uncertainty, and
draft quality checks.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date, datetime
from math import ceil, isfinite
from statistics import median
from typing import Any

from src.services.planning_signals import normalize_planning_signal
from src.services.planning_time import assignment_available_at, block_at, deadline_at

LOW_MASTERY_THRESHOLD = 0.50
DEVELOPING_MASTERY_THRESHOLD = 0.75
MIN_REVIEW_MINUTES = 30
MAX_PERSONAL_FACTOR = 1.75
MIN_PERSONAL_FACTOR = 0.75


@dataclass(frozen=True)
class WorkloadEstimate:
    p50_minutes: int
    p80_minutes: int
    confidence: float
    evidence_count: int
    personal_factor: float
    source: str
    source_refs: tuple[str, ...] = ()
    data_status: str = "insufficient_evidence"


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _tokens(value: Any) -> set[str]:
    ignored = {
        "and",
        "the",
        "for",
        "with",
        "from",
        "this",
        "that",
        "va",
        "cho",
        "cua",
        "cac",
        "mot",
        "nhung",
        "phan",
        "bai",
        "assignment",
        "task",
        "milestone",
    }
    return {token for token in _fold(value).split() if len(token) > 2 and token not in ignored}


def _round_up(value: float, increment: int = 15) -> int:
    integer = max(1, int(round(value)))
    return ((integer + increment - 1) // increment) * increment


def _as_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def normalize_rubric_criteria(assignment: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize supported Canvas/custom rubric shapes without inventing criteria."""
    rubric = assignment.get("rubric")
    if not rubric:
        return []

    rubric_id = None
    raw_criteria: list[Any]
    if isinstance(rubric, list):
        raw_criteria = rubric
    elif isinstance(rubric, str):
        raw_criteria = [rubric]
    elif isinstance(rubric, dict):
        rubric_id = rubric.get("id")
        for key in ("criteria", "items", "rubric"):
            if isinstance(rubric.get(key), list):
                raw_criteria = rubric[key]
                break
        else:
            metadata_keys = {"id", "title", "version", "points_possible"}
            raw_criteria = [
                {
                    "id": str(key),
                    "description": str(key),
                    "points": value if isinstance(value, (int, float)) else None,
                    "levels": value if isinstance(value, (list, dict)) else [],
                }
                for key, value in rubric.items()
                if key not in metadata_keys
            ]
    else:
        return []

    assignment_id = str(assignment.get("id") or "unknown")
    source_prefix = f"rubric:{rubric_id}" if rubric_id is not None else f"rubric:{assignment_id}"
    criteria: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_criteria):
        if isinstance(raw, str):
            raw = {"description": raw}
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("description") or raw.get("name") or raw.get("title") or "").strip()
        if not name:
            continue
        criterion_id = str(raw.get("id") or raw.get("criterion_id") or f"criterion-{index + 1}")
        points = raw.get("points", raw.get("max_points"))
        try:
            weight = float(points) if points is not None else None
        except (TypeError, ValueError):
            weight = None
        knowledge_components = [
            str(item.get("id") or item.get("name") or "").strip() if isinstance(item, dict) else str(item).strip()
            for item in _as_sequence(raw.get("knowledge_components") or raw.get("knowledgeComponents"))
        ]
        criteria.append(
            {
                "criterionId": criterion_id,
                "name": name,
                "description": str(raw.get("long_description") or raw.get("details") or name),
                "weight": weight,
                "knowledgeComponents": [item for item in knowledge_components if item],
                "sourceRef": f"{source_prefix}#criterion={criterion_id}",
            }
        )
    return criteria


def assignment_structure(assignment: dict[str, Any]) -> dict[str, Any]:
    """Return an explainable routing score for template/hybrid/LLM decomposition."""
    checks = {
        "task_type": bool(assignment.get("task_type") or assignment.get("grading_type")),
        "deadline": bool(assignment.get("deadline") or assignment.get("due_at")),
        "description": len(str(assignment.get("description") or "").strip()) >= 40,
        "deliverable": bool(assignment.get("deliverable") or assignment.get("submission_types")),
        "rubric": bool(normalize_rubric_criteria(assignment)),
        "estimate": bool(assignment.get("estimated_hours") or assignment.get("estimated_minutes")),
        "knowledge_components": bool(extract_knowledge_components(assignment, [])),
        "dependencies": bool(assignment.get("dependencies") or assignment.get("prerequisites")),
    }
    score = sum(1 for present in checks.values() if present)
    assignment_parts = [
        item for item in assignment.get("assignment_parts") or []
        if isinstance(item, dict) and item.get("partId") and item.get("content")
    ]
    # A multi-question brief is exactly where semantic decomposition adds
    # value: the model may group related sub-questions and name useful outputs,
    # while the server verifies that every extracted question is covered.
    if len(assignment_parts) >= 2:
        return {
            "score": score,
            "maximum": len(checks),
            "route": "llm" if len(assignment_parts) <= 12 else "template",
            "signals": {**checks, "assignment_parts": True},
            "partCount": len(assignment_parts),
        }
    # A real rubric plus a usable brief is stronger planning evidence than a
    # free-form model decomposition.  Use the deterministic rubric allocator;
    # reserve the LLM for genuinely unstructured assignments.
    has_evidence_breakdown = checks["rubric"] and checks["description"] and checks["estimate"]
    route = "template" if score >= 7 or has_evidence_breakdown else "hybrid" if score >= 4 else "llm"
    return {"score": score, "maximum": len(checks), "route": route, "signals": checks}


def build_template_milestones(
    assignment: dict[str, Any],
    *,
    target_minutes: int,
) -> list[dict[str, Any]]:
    """Create an evidence-based, provenance-preserving task decomposition.

    Rubric points describe importance, not difficulty.  We therefore combine
    the explicit rubric weight with a small, bounded complexity heuristic and
    let the deterministic allocator own the minutes.  The result always keeps
    the assignment's confirmed total instead of letting an LLM silently grow
    or shrink the workload.
    """
    task_id = str(assignment.get("id") or "")
    title = str(assignment.get("title") or "Assignment")
    criteria = normalize_rubric_criteria(assignment)

    def complexity_factor(value: str) -> tuple[float, str]:
        folded = _fold(value)
        hard = {
            "phan tich", "thiet ke", "cai dat", "lap trinh", "kiem thu", "debug",
            "chung minh", "toi uu", "tich hop", "ngoai le", "thuat toan", "mo hinh",
            "analyze", "design", "implement", "test", "debug", "prove", "optimize",
            "integration", "algorithm",
        }
        easy = {
            "trinh bay", "dinh dang", "dat ten", "readme", "nop bai",
            "presentation", "format", "naming", "submit",
        }
        hard_hits = sum(token in folded for token in hard)
        easy_hits = sum(token in folded for token in easy)
        factor = min(1.45, 1.0 + hard_hits * 0.12)
        if easy_hits and not hard_hits:
            factor = 0.75
        level = "khó" if factor >= 1.24 else "dễ" if factor <= 0.85 else "vừa"
        return factor, level

    def assignment_part_effort_factor(part: dict[str, Any]) -> float:
        """Weight observable assignment labels without inventing task content.

        A short conceptual question and a project component should not receive
        identical time merely because their paragraphs have similar lengths.
        The public label supplies a bounded effort signal; total assignment
        time remains the learner/teacher-confirmed budget.
        """
        label = _fold(part.get("label"))
        if any(token in label for token in ("thanh phan", "component", "phase", "milestone")):
            return 1.80
        if any(token in label for token in ("yeu cau", "requirement", "feature", "deliverable")):
            return 1.30
        if any(token in label for token in ("cau", "question")):
            return 0.75
        return 1.00

    def summarize_part_labels(parts: list[dict[str, Any]]) -> str:
        labels = list(dict.fromkeys(
            str(item.get("label") or item.get("partId") or "Phần việc").strip()
            for item in parts
        ))
        if len(labels) <= 4:
            return "; ".join(labels)
        counts = {"câu": 0, "yêu cầu": 0, "thành phần": 0, "phần": 0}
        for label in labels:
            folded = _fold(label)
            if folded.startswith(("cau", "question")):
                counts["câu"] += 1
            elif folded.startswith(("yeu cau", "requirement")):
                counts["yêu cầu"] += 1
            elif folded.startswith(("thanh phan", "component")):
                counts["thành phần"] += 1
            else:
                counts["phần"] += 1
        return " · ".join(f"{count} {name}" for name, count in counts.items() if count)

    def group_criteria(values: list[dict[str, Any]], limit: int) -> list[list[dict[str, Any]]]:
        if len(values) <= limit:
            return [[value] for value in values]
        groups: list[list[dict[str, Any]]] = [[] for _ in range(limit)]
        totals = [0.0] * limit
        for criterion in sorted(values, key=lambda item: float(item.get("weight") or 1), reverse=True):
            target = min(range(limit), key=lambda index: totals[index])
            groups[target].append(criterion)
            totals[target] += float(criterion.get("weight") or 1)
        return [group for group in groups if group]

    def allocate(total: int, weights: list[float]) -> list[int]:
        if not weights:
            return []
        total = max(15, int(total))
        count = min(len(weights), max(1, total // 15))
        weights = weights[:count]
        result = [15] * count
        remaining = total - 15 * count
        if remaining <= 0:
            result[-1] += remaining
            return result
        weight_sum = sum(weights) or float(count)
        # Allocate against each part's share of the *whole* confirmed budget.
        # Weighting only the time left after a 15-minute floor made medium-size
        # assignments collapse to identical 30-minute sessions even when a
        # project component was observably harder than a concept question.
        targets = [total * weight / weight_sum for weight in weights]
        while remaining >= 15:
            target = max(range(count), key=lambda index: targets[index] - result[index])
            result[target] += 15
            remaining -= 15
        if remaining:
            target = max(range(count), key=lambda index: targets[index] - result[index])
            result[target] += remaining
        return result

    assignment_parts = [
        item for item in assignment.get("assignment_parts") or []
        if isinstance(item, dict) and item.get("partId") and item.get("content")
    ]
    if len(assignment_parts) >= 2:
        # Keep sessions useful (normally 30-90 minutes) by grouping adjacent
        # short questions when the user's total estimate cannot support one
        # session per question.  Ordering is preserved for prerequisites.
        group_count = min(len(assignment_parts), 12, max(1, int(target_minutes) // 30))
        groups: list[list[dict[str, Any]]] = [[] for _ in range(group_count)]
        for index, part in enumerate(assignment_parts):
            bucket = min(group_count - 1, index * group_count // len(assignment_parts))
            groups[bucket].append(part)
        group_facts = []
        for group in groups:
            combined = " ".join(str(item.get("content") or "") for item in group)
            factor, level = complexity_factor(combined)
            # Longer prompts need more reading/implementation time, but keep
            # that heuristic bounded so wording alone cannot dominate a plan.
            length_factor = min(1.5, max(0.75, len(combined) / 500))
            part_effort_factor = sum(assignment_part_effort_factor(item) for item in group) / len(group)
            group_facts.append(
                {
                    "parts": group,
                    "score": factor * length_factor * part_effort_factor,
                    "difficulty": level,
                    "complexityFactor": factor,
                    "partEffortFactor": part_effort_factor,
                }
            )
        minutes = allocate(target_minutes, [item["score"] for item in group_facts])
        result: list[dict[str, Any]] = []
        for index, (facts, allocated) in enumerate(zip(group_facts, minutes), start=1):
            parts = facts["parts"]
            label_summary = summarize_part_labels(parts)
            part_ids = [str(item["partId"]) for item in parts]
            source_refs = [
                f"assignment:{task_id}",
                *[str(item.get("sourceRef")) for item in parts if item.get("sourceRef")],
            ]
            milestone_id = f"{task_id}:questions-{index}"
            result.append(
                {
                    "milestone_id": milestone_id,
                    "task_id": task_id,
                    "title": f"Làm {label_summary} — {title}",
                    "deliverable": f"Lời giải có thể kiểm tra cho {label_summary}",
                    "estimated_minutes": allocated,
                    "depends_on": [result[-1]["milestone_id"]] if result else [],
                    "assignment_part_ids": part_ids,
                    "source_refs": list(dict.fromkeys(source_refs)),
                    "decomposition_source": "assignment_question_evidence",
                    "difficulty": facts["difficulty"],
                    "allocation_basis": {
                        "method": "question_complexity_x_bounded_length",
                        "complexityFactor": round(facts["complexityFactor"], 2),
                        "partEffortFactor": round(facts["partEffortFactor"], 2),
                        "confidence": "document_grounded_heuristic",
                    },
                }
            )
        return result

    if criteria:
        max_parts = min(5, max(1, int(target_minutes) // 15))
        groups = group_criteria(criteria, max_parts)
        group_facts: list[dict[str, Any]] = []
        for group in groups:
            combined = " ".join(f"{item['name']} {item['description']}" for item in group)
            factor, level = complexity_factor(combined)
            rubric_weight = sum(float(item.get("weight") or 1) for item in group)
            group_facts.append(
                {
                    "criteria": group,
                    "rubricWeight": rubric_weight,
                    "complexityFactor": factor,
                    "difficulty": level,
                    "score": rubric_weight * factor,
                }
            )
        minutes = allocate(target_minutes, [item["score"] for item in group_facts])
        result: list[dict[str, Any]] = []
        for index, (facts, allocated) in enumerate(zip(group_facts, minutes)):
            names = [item["name"] for item in facts["criteria"]]
            criterion_ids = [item["criterionId"] for item in facts["criteria"]]
            source_refs = [f"assignment:{task_id}", *[item["sourceRef"] for item in facts["criteria"]]]
            milestone_id = f"{task_id}:rubric-{index + 1}"
            result.append(
                {
                    "milestone_id": milestone_id,
                    "task_id": task_id,
                    "title": f"{'; '.join(names)} — {title}",
                    "deliverable": "Hoàn thành và tự kiểm tra: " + "; ".join(names),
                    "estimated_minutes": allocated,
                    "depends_on": [result[-1]["milestone_id"]] if result else [],
                    "rubric_criteria": criterion_ids,
                    "source_refs": list(dict.fromkeys(source_refs)),
                    "decomposition_source": "rubric_evidence",
                    "difficulty": facts["difficulty"],
                    "allocation_basis": {
                        "method": "rubric_weight_x_bounded_complexity",
                        "rubricWeight": facts["rubricWeight"],
                        "complexityFactor": round(facts["complexityFactor"], 2),
                        "confidence": "supported_heuristic",
                    },
                }
            )
        return result

    kind = _fold(f"{assignment.get('task_type', '')} {assignment.get('grading_type', '')} {title}")
    if any(token in kind for token in ("quiz", "exam", "kiem tra")):
        steps = (
            ("Review assessed concepts", "A concise retrieval sheet", 0.35),
            ("Complete practice check", "Checked attempts and remaining gaps", 0.40),
            ("Final readiness review", "Submission/readiness checklist", 0.25),
        )
    elif any(token in kind for token in ("project", "code", "lap trinh", "essay", "report")):
        steps = (
            ("Extract requirements and rubric", "Verified requirement checklist", 0.20),
            ("Produce the main draft", "Reviewable draft deliverable", 0.45),
            ("Test against the rubric", "Evidence for each rubric criterion", 0.25),
            ("Finalize submission", "Submission-ready artifact", 0.10),
        )
    else:
        steps = (
            ("Đọc đề và xác định yêu cầu", "Checklist yêu cầu cần hoàn thành", 0.25),
            ("Thực hiện nội dung chính", "Kết quả có thể tự kiểm tra", 0.50),
            ("Rà soát và chuẩn bị nộp", "Sản phẩm sẵn sàng nộp", 0.25),
        )

    remaining = max(30, int(target_minutes))
    result: list[dict[str, Any]] = []
    # Do not emit a five-minute tail milestone for short demo assignments.
    # Keep at least 15 minutes per stage and merge later stages when the
    # confirmed budget is small (e.g. 40 minutes -> 15 + 25).
    usable_steps = steps[: min(len(steps), max(1, remaining // 15))]
    for index, (step_title, deliverable, share) in enumerate(usable_steps):
        if remaining <= 0:
            break
        minutes = (
            remaining
            if index == len(usable_steps) - 1
            else min(remaining - 15 * (len(usable_steps) - index - 1), max(15, _round_up(target_minutes * share)))
        )
        milestone_id = f"{task_id}:template-{index + 1}"
        result.append(
            {
                "milestone_id": milestone_id,
                "task_id": task_id,
                "title": f"{step_title}: {title}",
                "deliverable": deliverable,
                "estimated_minutes": minutes,
                "depends_on": [result[-1]["milestone_id"]] if result else [],
                "source_refs": [f"assignment:{task_id}"],
                "decomposition_source": "template",
            }
        )
        remaining -= minutes
    return result


def extract_knowledge_components(
    assignment: dict[str, Any],
    criteria: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Read only explicit KC metadata from LMS/rubric data."""
    raw_values: list[Any] = []
    for key in ("knowledge_components", "knowledgeComponents", "topics"):
        raw_values.extend(_as_sequence(assignment.get(key)))
    raw_values.extend(_as_sequence(assignment.get("prerequisites")))
    for criterion in criteria:
        raw_values.extend(criterion.get("knowledgeComponents") or [])

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    assignment_id = str(assignment.get("id") or "unknown")
    for raw in raw_values:
        if isinstance(raw, dict):
            component_id = str(raw.get("id") or raw.get("code") or raw.get("name") or "").strip()
            name = str(raw.get("name") or raw.get("title") or component_id).strip()
        else:
            component_id = str(raw).strip()
            name = component_id
        key = _fold(component_id)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "componentId": component_id,
                "name": name,
                "status": "approved",
                "sourceRef": f"assignment:{assignment_id}#knowledge-component={component_id}",
            }
        )
    return result


def _numeric_mastery(value: Any) -> float | None:
    if isinstance(value, dict) and (value.get("provisional") or value.get("review_status") in {"verifying", "pending_review", "abstained"}):
        return None
    if isinstance(value, (int, float)):
        score = float(value)
        return min(1.0, max(0.0, score / 100 if score > 1 else score))
    if not isinstance(value, dict):
        return None
    if "level" in value:
        # Scheduling readiness weights are policy constants, not estimated
        # mastery probabilities. Unknown knowledge is not evidence of weakness.
        if set(value.get("unresolved_dimensions") or []) & {
            "recall",
            "conceptual",
            "reasoning",
            "application",
            "transfer",
        }:
            return 0.25
        level = value.get("level")
        if level == "retained":
            level = value.get("retained_level") or "application"
        return {"recognition": 0.3, "conceptual": 0.5, "application": 0.75, "transfer": 0.9}.get(level)
    for key in ("score", "probability", "mastery", "value"):
        if key in value:
            return _numeric_mastery(value[key])
    status = _fold(value.get("status"))
    if any(term in status for term in ("da the hien", "mastered", "understood")):
        return 0.85
    if any(term in status for term in ("dang hinh thanh", "developing")):
        return 0.65
    if any(term in status for term in ("nham lan", "misconception")):
        return 0.30
    if any(term in status for term in ("chua du", "insufficient", "not understood")):
        return 0.35
    return None


def mastery_for_component(mastery_profile: dict[str, Any], component: str) -> float | None:
    target = _fold(component)
    if not target:
        return None
    for key, value in (mastery_profile or {}).items():
        folded_key = _fold(key)
        if folded_key == target:
            # A legacy decimal/label without evidence cannot imply weakness or
            # justify extra minutes. Current Knowledge State carries source IDs.
            if not isinstance(value, dict) or not value.get("source_evidence_ids"):
                return None
            return _numeric_mastery(value)
    return None


def normalize_reflection_feedback(
    learner_profile: dict[str, Any] | None,
    *,
    task_id: str | None = None,
    activity_type: str | None = None,
) -> dict[str, Any]:
    """Convert persisted Do/Reflect evidence to bounded scheduling parameters."""
    profile = learner_profile or {}
    sessions = [item for item in profile.get("do_history") or [] if isinstance(item, dict)]
    scoped = [item for item in sessions if not task_id or str(item.get("task_id") or "") == task_id]
    if activity_type is not None:
        scoped = [item for item in scoped if item.get("activity_type", "unknown") == activity_type]
    # No cross-task fallback: longer sessions in another course are not a
    # demonstrated workload multiplier for this assignment.
    # Use only the most recent homogeneous context, not pooled task stages or
    # different study rhythms. Legacy elapsed/self-reported data lacks this
    # provenance and cannot calibrate a duration multiplier.
    contexts: dict[tuple, list[dict]] = {}
    latest_context = None
    for item in scoped:
        rhythm = item.get("rhythm") or {}
        if (item.get("time_source") != "timer" or not item.get("readiness_key")
                or not rhythm.get("sessionMinutes") or not rhythm.get("breakMinutes")
                or item.get("checkpoint_minutes", 0)):
            continue
        key = (item.get("task_id"), item.get("activity_type", "unknown"), item["readiness_key"], rhythm["sessionMinutes"], rhythm["breakMinutes"])
        contexts.setdefault(key, []).append(item)
        latest_context = key
    evidence = contexts.get(latest_context, [])
    ratios: list[float] = []
    source_refs: list[str] = []
    seen_refs: set[str] = set()
    blockers: dict[str, int] = {}
    # Preserve reported causes even when their timing is not calibration data.
    for item in scoped:
        blocker = _fold(item.get("blocker"))
        if blocker:
            blockers[blocker] = blockers.get(blocker, 0) + 1
    for item in evidence:
        try:
            planned = float(item.get("planned_minutes") or 0)
            actual = float(item.get("actual_minutes") or 0)
        except (TypeError, ValueError):
            planned = actual = 0
        reference = str(item.get("session_id") or item.get("block_id") or item.get("source_ref") or "")
        interrupted = item.get("interruption_reason") not in {None, "none"} or item.get("blocker") in {"interruption", "time", "other"}
        reliable = (
            not interrupted and item.get("completion_percent") == 100 and item.get("blocker", "none") == "none"
            and item.get("time_source") == "timer"
            and not item.get("unobserved_gap") and bool(reference)
        )
        if reliable and reference not in seen_refs and isfinite(planned) and isfinite(actual) and planned > 0 and actual > 0:
            ratios.append(actual / planned)
            source_refs.append(f"do:{reference}")
            seen_refs.add(reference)
    personal_factor = median(ratios) if len(ratios) >= 3 else 1.0
    personal_factor = min(MAX_PERSONAL_FACTOR, max(MIN_PERSONAL_FACTOR, personal_factor))
    last_reflection = profile.get("last_reflection") or {}
    activity_reflections = profile.get("activity_reflections") or []
    raw_signals = [
        reflection.get("planning_signal") or reflection.get("planningSignal")
        for reflection in [*activity_reflections[-10:], last_reflection]
        if isinstance(reflection, dict)
    ]
    signals = [
        signal
        for signal in raw_signals
        if isinstance(signal, dict)
        and (
            not task_id
            or str(signal.get("task_id", signal.get("taskId"))) == task_id
        )
    ]
    latest_signal = signals[-1] if signals else {}
    normalized_signal = normalize_planning_signal(latest_signal)
    if len(ratios) < 3:
        normalized_signal["duration_factor"] = 1.0
    # Interruption changes capacity, not the amount of knowledge work needed.
    if normalized_signal["cause"] in {"interruption", "insufficient_time", "capacity_changed", "schedule_conflict", "missed_block", "unknown"}:
        normalized_signal["duration_factor"] = 1.0
        normalized_signal["follow_up_minutes"] = 0
    return {
        "personalFactor": round(personal_factor, 3),
        "evidenceCount": len(ratios),
        "sourceRefs": source_refs,
        "signalSourceRefs": ["reflect-signal:" + hashlib.sha256(json.dumps(latest_signal, sort_keys=True).encode()).hexdigest()[:16]] if latest_signal else [],
        "blockers": blockers,
        "lastAdjustment": str(last_reflection.get("adjustment") or ""),
        "activityReflectionCount": len(activity_reflections),
        "cause": normalized_signal["cause"],
        "durationFactor": normalized_signal["duration_factor"],
        "followUpMinutes": normalized_signal["follow_up_minutes"],
        "affectedKnowledgeComponents": normalized_signal["affected_kcs"],
        "unrecognizedCause": normalized_signal.get("unrecognized_cause"),
        "signalCount": len(signals),
    }


def estimate_workload(
    base_minutes: int,
    *,
    learner_profile: dict[str, Any] | None = None,
    task_id: str | None = None,
    activity_type: str | None = None,
    mastery_scores: Iterable[float | None] = (),
) -> WorkloadEstimate:
    """Produce heuristic P50/P80 targets with explicit, uncalibrated uncertainty."""
    feedback = normalize_reflection_feedback(learner_profile, task_id=task_id, activity_type=activity_type)
    scores = [score for score in mastery_scores if score is not None]
    mastery_factor = 1.0
    if scores:
        weakest = min(scores)
        mastery_factor = (
            1.15 if weakest < LOW_MASTERY_THRESHOLD else 1.05 if weakest < DEVELOPING_MASTERY_THRESHOLD else 1.0
        )

    # Do not manufacture extra work by rounding every small milestone to 15m.
    # P50/P80 are engineering heuristics, not calibrated learner probabilities.
    duration_factor = max(feedback["personalFactor"], feedback["durationFactor"])
    p50 = ceil(max(1, base_minutes) * duration_factor * mastery_factor)
    evidence_count = int(feedback["evidenceCount"])
    uncertainty = 0.15 if evidence_count >= 8 else 0.22 if evidence_count >= 3 else 0.30
    if not scores:
        uncertainty += 0.05
    p80 = _round_up(p50 * (1 + uncertainty))
    confidence = min(0.90, 0.35 + min(evidence_count, 8) * 0.06 + (0.12 if scores else 0.0))
    source = (
        "learner_history_and_mastery"
        if evidence_count and scores
        else "learner_history"
        if evidence_count
        else "task_baseline"
    )
    return WorkloadEstimate(
        p50_minutes=p50,
        p80_minutes=max(p50, p80),
        confidence=round(confidence, 2),
        evidence_count=evidence_count,
        personal_factor=float(feedback["personalFactor"]),
        source=source,
        source_refs=tuple([*feedback["sourceRefs"], *feedback["signalSourceRefs"]]),
        data_status="supported_heuristic" if evidence_count >= 3 or scores else "insufficient_evidence",
    )


def enrich_task_milestones(
    *,
    task_id: str,
    assignment: dict[str, Any],
    milestones: list[dict[str, Any]],
    learner_profile: dict[str, Any] | None = None,
    mastery_profile: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Attach rubric/KC provenance and add bounded prerequisite review."""
    criteria = normalize_rubric_criteria(assignment)
    approved_components = extract_knowledge_components(assignment, criteria)
    approved_by_fold = {_fold(item["componentId"]): item for item in approved_components}
    rubric_by_id = {item["criterionId"]: item for item in criteria}
    enriched: list[dict[str, Any]] = []

    for raw in milestones:
        item = dict(raw)
        text_tokens = _tokens(f"{item.get('title', '')} {item.get('deliverable', '')}")
        requested_rubric = [str(value) for value in item.get("rubricCriteria") or item.get("rubric_criteria") or []]
        mapped_rubric = [value for value in requested_rubric if value in rubric_by_id]
        if not mapped_rubric:
            mapped_rubric = [
                criterion["criterionId"]
                for criterion in criteria
                if text_tokens & _tokens(f"{criterion['name']} {criterion['description']}")
            ]

        raw_components = item.get("knowledgeComponents") or item.get("knowledge_components") or []
        mapped_components: list[dict[str, Any]] = []
        for raw_component in raw_components:
            component_id = str(
                raw_component.get("id") or raw_component.get("componentId") or raw_component.get("name")
                if isinstance(raw_component, dict)
                else raw_component
            ).strip()
            if not component_id:
                continue
            approved = approved_by_fold.get(_fold(component_id))
            mapped_components.append(
                approved
                or {
                    "componentId": component_id,
                    "name": component_id,
                    "status": "provisional",
                    "sourceRef": f"assignment:{task_id}#ai-proposed-kc",
                }
            )
        if not mapped_components:
            for component in approved_components:
                if text_tokens & _tokens(component["name"]):
                    mapped_components.append(component)
            if len(approved_components) == 1 and not mapped_components:
                mapped_components = [approved_components[0]]

        source_refs = [
            str(value) for value in item.get("sourceRefs") or item.get("source_refs") or [] if str(value).strip()
        ]
        assignment_ref = f"assignment:{task_id}"
        if assignment_ref not in source_refs:
            source_refs.insert(0, assignment_ref)
        for criterion_id in mapped_rubric:
            reference = rubric_by_id[criterion_id]["sourceRef"]
            if reference not in source_refs:
                source_refs.append(reference)

        scores = [
            mastery_for_component(mastery_profile or {}, component["componentId"]) for component in mapped_components
        ]
        has_provisional_component = any(component["status"] == "provisional" for component in mapped_components)
        mapping_confidence = 0.45 if has_provisional_component else 0.9 if mapped_rubric or mapped_components else 0.45
        item.update(
            {
                "rubricCriteria": mapped_rubric,
                "knowledgeComponents": mapped_components,
                "sourceRefs": source_refs,
                "mappingConfidence": mapping_confidence,
                "decompositionSource": str(
                    item.get("decompositionSource") or item.get("decomposition_source") or "llm"
                ),
                "masteryScores": {
                    component["componentId"]: score
                    for component, score in zip(mapped_components, scores)
                    if score is not None
                },
                "masteryEvidenceRefs": sorted({str(ref) for component in mapped_components
                    for ref in ((mastery_profile or {}).get(component["componentId"], {}).get("source_evidence_ids", [])
                                if isinstance((mastery_profile or {}).get(component["componentId"]), dict) else [])}),
            }
        )
        enriched.append(item)

    # A final review/check milestone is the safest deterministic owner of any
    # rubric criterion the LLM/template did not explicitly map.
    covered = {criterion_id for item in enriched for criterion_id in item["rubricCriteria"]}
    missing = [criterion["criterionId"] for criterion in criteria if criterion["criterionId"] not in covered]
    if missing and enriched:
        enriched[-1]["rubricCriteria"] = [*enriched[-1]["rubricCriteria"], *missing]
        for criterion_id in missing:
            reference = rubric_by_id[criterion_id]["sourceRef"]
            if reference not in enriched[-1]["sourceRefs"]:
                enriched[-1]["sourceRefs"].append(reference)
        covered.update(missing)

    weak_components: list[tuple[dict[str, Any], float]] = []
    unique_components = {
        component["componentId"]: component
        for item in enriched
        for component in item["knowledgeComponents"]
        if component["status"] == "approved"
    }
    for component in unique_components.values():
        score = mastery_for_component(mastery_profile or {}, component["componentId"])
        if score is not None and score < LOW_MASTERY_THRESHOLD:
            weak_components.append((component, score))

    reflection_signals = normalize_reflection_feedback(learner_profile, task_id=task_id)
    if weak_components:
        component, score = min(weak_components, key=lambda value: value[1])
        review_id = f"{task_id}:prerequisite-review"
        review = {
            "milestoneId": review_id,
            "title": f"Review prerequisite: {component['name']}",
            "deliverable": "Short retrieval check before the main assignment work",
            "estimatedMin": max(MIN_REVIEW_MINUTES, reflection_signals["followUpMinutes"]),
            "dependsOn": [],
            "sourceRefs": [f"assignment:{task_id}", component["sourceRef"]],
            "rubricCriteria": [],
            "knowledgeComponents": [component],
            "mappingConfidence": 1.0,
            "decompositionSource": "mastery_rule",
            "masteryScores": {component["componentId"]: score},
            "masteryEvidenceRefs": list((mastery_profile or {})[component["componentId"]]["source_evidence_ids"]),
        }
        for item in enriched:
            if not item.get("dependsOn"):
                item["dependsOn"] = [review_id]
        enriched.insert(0, review)
    elif reflection_signals["followUpMinutes"] > 0:
        affected = {_fold(value) for value in reflection_signals["affectedKnowledgeComponents"]}
        follow_up_components = [
            component for component in approved_components if _fold(component["componentId"]) in affected
        ]
        follow_up_id = f"{task_id}:reflect-follow-up"
        follow_up = {
            "milestoneId": follow_up_id,
            "title": "Follow up on confirmed reflection",
            "deliverable": "A short retrieval check addressing the recorded blocker",
            "estimatedMin": reflection_signals["followUpMinutes"],
            "dependsOn": [],
            "sourceRefs": [f"assignment:{task_id}", "reflect:confirmed"],
            "rubricCriteria": [],
            "knowledgeComponents": follow_up_components,
            "mappingConfidence": 1.0 if follow_up_components else 0.7,
            "decompositionSource": "reflect_rule",
            "masteryScores": {},
        }
        for item in enriched:
            if not item.get("dependsOn"):
                item["dependsOn"] = [follow_up_id]
        enriched.insert(0, follow_up)

    report = {
        "taskId": task_id,
        "structure": assignment_structure(assignment),
        "criteria": criteria,
        "coveredCriterionIds": sorted(covered),
        "missingCriterionIds": sorted({item["criterionId"] for item in criteria} - covered),
        "knowledgeComponents": approved_components,
        "weakKnowledgeComponents": [
            {"componentId": component["componentId"], "score": score} for component, score in weak_components
        ],
        "reflectionSignals": reflection_signals,
    }
    return enriched, report


def apply_estimate(
    milestone: dict[str, Any],
    *,
    allocated_minutes: int,
    learner_profile: dict[str, Any] | None,
    task_id: str,
) -> dict[str, Any]:
    scores = list((milestone.get("masteryScores") or {}).values())
    estimate = estimate_workload(
        allocated_minutes,
        learner_profile=learner_profile,
        task_id=task_id,
        activity_type=milestone.get("activityType"),
        mastery_scores=scores,
    )
    fields = asdict(estimate)
    fields["source_refs"] = sorted({*fields["source_refs"], *(milestone.get("masteryEvidenceRefs") or [])})
    return {**milestone, "estimate": fields}


def planning_mastery_risk(assignment: dict[str, Any], mastery_profile: dict[str, Any] | None) -> float:
    criteria = normalize_rubric_criteria(assignment)
    components = extract_knowledge_components(assignment, criteria)
    scores = [mastery_for_component(mastery_profile or {}, item["componentId"]) for item in components]
    known = [score for score in scores if score is not None]
    return round(1.0 - min(known), 3) if known else 0.0


def evaluate_plan_quality(
    draft: dict[str, Any], assignments: list[dict[str, Any]], *, now: datetime | None = None,
    include_partial: bool = True,
) -> dict[str, Any]:
    """Evaluate a completed draft independently from the generation path."""
    violations: list[dict[str, Any]] = []
    timezone_name = draft.get("timezone") or "Asia/Ho_Chi_Minh"
    fallback = date.fromisoformat(str(draft.get("horizonEnd") or draft.get("scheduleStart") or "9999-12-30")[:10])
    deadlines = {
        str(item.get("id")): deadline_at(item.get("deadline") or item.get("due_at"), fallback, timezone_name)
        for item in assignments
    }
    earliest_starts = {
        str(item.get("id")): assignment_available_at(item, timezone_name)
        for item in assignments
    }
    checked_at = now
    if checked_at is None and draft.get("enforceCurrentTime") and draft.get("createdAt"):
        checked_at = datetime.fromisoformat(draft["createdAt"])
    executable = [item for item in draft.get("blocks") or [] if item.get("status") != "history"]
    unavailable = (draft.get("input") or {}).get("unavailable") or []
    availability = (draft.get("input") or {}).get("availability") or []
    completed_tasks = {str(a.get("id")) for a in assignments
                       if (a.get("submission") or {}).get("workflow_state") in {"submitted", "graded", "pending_review", "excused"}}
    by_day: dict[str, list[dict[str, Any]]] = {}
    schedule_start = str(draft.get("scheduleStart") or "")[:10]
    for block in executable:
        day = str(block.get("date") or "")[:10]
        by_day.setdefault(day, []).append(block)
        try:
            start_at = block_at(day, str(block.get("start")), timezone_name)
            end_at = block_at(day, str(block.get("end")), timezone_name)
        except (ValueError, TypeError):
            violations.append({"code": "INVALID_BLOCK_TIME", "blockId": block.get("id")})
            continue
        if end_at <= start_at:
            violations.append({"code": "INVALID_BLOCK_DURATION", "blockId": block.get("id")})
        if (
            checked_at is not None
            and start_at < checked_at
            and not (block.get("lockedOngoing") and end_at > checked_at)
        ):
            violations.append({"code": "PAST_BLOCK", "blockId": block.get("id")})
        if schedule_start and day < schedule_start:
            violations.append({"code": "PAST_BLOCK", "blockId": block.get("id")})
        deadline = deadlines.get(str(block.get("taskId") or ""))
        if deadline is None:
            violations.append({"code": "UNKNOWN_TASK", "blockId": block.get("id")})
        if deadline and end_at > deadline:
            violations.append({"code": "AFTER_DEADLINE", "blockId": block.get("id")})
        earliest_start = earliest_starts.get(str(block.get("taskId") or ""))
        if earliest_start is not None and start_at < earliest_start:
            violations.append({
                "code": "BEFORE_PREREQUISITE",
                "blockId": block.get("id"),
                "earliestStartAt": earliest_start.isoformat(),
            })
        if str(block.get("taskId")) in completed_tasks:
            violations.append({"code": "TASK_COMPLETED", "blockId": block.get("id")})
        if availability and not block.get("lockedOngoing"):
            windows = [s for s in availability if s.get("weekday") == start_at.weekday() and s.get("enabled", True)]
            windows += [s for s in unavailable if s.get("category") == "self_study"
                        and (str(s.get("date"))[:10] == day if s.get("date") else s.get("weekday") == start_at.weekday())]
            if not any(str(s.get("start")) <= str(block.get("start")) and str(block.get("end")) <= str(s.get("end")) for s in windows):
                violations.append({"code": "OUTSIDE_AVAILABILITY", "blockId": block.get("id")})
        for slot in unavailable:
            if slot.get("category") == "self_study":
                continue
            if slot.get("date"):
                matches = str(slot["date"])[:10] == day
            else:
                matches = slot.get("weekday") == start_at.weekday()
            if matches and str(block.get("start")) < str(slot.get("end")) and str(slot.get("start")) < str(block.get("end")):
                violations.append({"code": "UNAVAILABLE_OVERLAP", "blockId": block.get("id")})
                break
    for day, blocks in by_day.items():
        ordered = sorted(blocks, key=lambda item: str(item.get("start") or ""))
        for previous, current in zip(ordered, ordered[1:]):
            if str(current.get("start") or "") < str(previous.get("end") or ""):
                violations.append(
                    {
                        "code": "BLOCK_OVERLAP",
                        "date": day,
                        "blockIds": [previous.get("id"), current.get("id")],
                    }
                )

    milestones = draft.get("milestones") or []
    milestone_ids = {str(item.get("milestoneId") or "") for item in milestones}
    by_milestone = {str(m.get("milestoneId") or ""): m for m in milestones}
    visiting, visited, cyclic = set(), set(), set()
    def visit(identifier: str, trail: list[str]) -> None:
        if identifier in visiting:
            cyclic.update(trail[trail.index(identifier):])
            return
        if identifier in visited or identifier not in by_milestone:
            return
        visiting.add(identifier)
        for dependency in by_milestone[identifier].get("dependsOn") or []:
            visit(str(dependency), [*trail, identifier])
        visiting.remove(identifier)
        visited.add(identifier)
    for identifier in by_milestone:
        visit(identifier, [])
    violations.extend({"code": "DEPENDENCY_CYCLE", "milestoneId": identifier} for identifier in sorted(cyclic))
    first_block, last_block = {}, {}
    from src.services.plan_confirmation import work_minutes
    scheduled_work: dict[str, int] = {}
    for item in executable:
        identifier = str(item.get("milestoneId") or "")
        if identifier:
            start, end = f"{item.get('date')}T{item.get('start')}", f"{item.get('date')}T{item.get('end')}"
            first_block[identifier] = min(first_block.get(identifier, start), start)
            last_block[identifier] = max(last_block.get(identifier, end), end)
            scheduled_work[identifier] = scheduled_work.get(identifier, 0) + work_minutes(item, timezone_name)
    for milestone in milestones:
        milestone_id = str(milestone.get("milestoneId") or "")
        for dependency in milestone.get("dependsOn") or []:
            if str(dependency) not in milestone_ids:
                violations.append({"code": "UNKNOWN_DEPENDENCY", "milestoneId": milestone_id, "dependency": dependency})
            elif milestone_id in first_block and str(dependency) not in last_block:
                violations.append({"code": "DEPENDENCY_UNSCHEDULED", "milestoneId": milestone_id, "dependency": dependency})
            elif milestone_id in first_block and scheduled_work.get(str(dependency), 0) < int(by_milestone[str(dependency)].get("targetMin") or 0):
                violations.append({"code": "DEPENDENCY_INCOMPLETE", "milestoneId": milestone_id, "dependency": dependency})
            elif (
                milestone_id in first_block
                and str(dependency) in last_block
                and last_block[str(dependency)] > first_block[milestone_id]
            ):
                violations.append({"code": "DEPENDENCY_ORDER", "milestoneId": milestone_id, "dependency": dependency})

    coverage_reports = draft.get("rubricCoverage") or []
    criterion_count = sum(len(item.get("criteria") or []) for item in coverage_reports)
    covered_count = sum(len(item.get("coveredCriterionIds") or []) for item in coverage_reports)
    missing_criteria = [
        {"taskId": item.get("taskId"), "criterionId": criterion_id}
        for item in coverage_reports
        for criterion_id in item.get("missingCriterionIds") or []
    ]
    provenance_count = sum(bool(item.get("sourceRefs")) for item in milestones)
    provenance_coverage = provenance_count / len(milestones) if milestones else 0.0
    rubric_coverage = covered_count / criterion_count if criterion_count else 1.0
    robust_feasible = bool((draft.get("feasibility") or {}).get("robustFeasible", True))
    hard_ok = not violations and bool((draft.get("feasibility") or {}).get("feasible", False))
    blocking_errors = [*violations]
    if not (draft.get("feasibility") or {}).get("feasible", False):
        blocking_errors.append({"code": "DEADLINE_CAPACITY_SHORTFALL"})
    warnings = []
    if not robust_feasible:
        warnings.append({"code": "ROBUST_CAPACITY_RISK"})
    if missing_criteria:
        warnings.append({"code": "RUBRIC_COVERAGE_GAP", "criteria": missing_criteria})
    if provenance_coverage < 1.0:
        warnings.append({"code": "PROVENANCE_GAP"})
    checks = {
        "hardConstraints": hard_ok,
        "rubricCoverage": not missing_criteria,
        "provenance": provenance_coverage == 1.0,
        "robustCapacity": robust_feasible,
    }
    score = max(
        0,
        round(
            100
            - min(60, len(violations) * 20)
            - round((1 - rubric_coverage) * 20)
            - round((1 - provenance_coverage) * 10)
            - (10 if not robust_feasible else 0)
        ),
    )
    report = {
        "releaseReady": all(checks.values()),
        "canConfirm": hard_ok,
        "blockingErrors": blocking_errors,
        "warnings": warnings,
        "score": score,
        "checks": checks,
        "metrics": {
            "hardViolationCount": len(violations),
            "rubricCoverage": round(rubric_coverage, 4),
            "provenanceCoverage": round(provenance_coverage, 4),
            "robustCapacity": robust_feasible,
        },
        "violations": violations,
        "missingRubricCriteria": missing_criteria,
        "limitations": [
            "This report validates planning behavior, not causal learning outcomes.",
            "Educational impact still requires a longitudinal pilot against a baseline.",
        ],
    }
    if include_partial:
        from src.services.plan_confirmation import partial_confirmation_preview
        report["partialConfirmation"] = partial_confirmation_preview(draft, assignments, report, now=now)
    return report
