"""Evidence-backed, immutable-plan KPIs. No timer, self-report or mastery guesses."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from src.persistence_models import DelayedAssessmentProbe, LearningEvent, LearningEvidenceRecord
from src.services.adoption_metrics import instant
from src.services.assessment_review_policy import planning_evidence_usable
from src.services.learning_evidence import LEVELS

CONTRACT_VERSION = "plan-measurement-v1"


def freeze_plan_measurement(plan: dict, confirmed_at: datetime, timezone_name: str) -> dict:
    """Freeze target IDs, time and criteria only from the server-owned draft.

    The explicit conservative fallback is application, not an LLM-invented
    mastery target. Unmapped/provisional KC goals cannot pass this criterion.
    """
    grouped = {}
    milestones = {(str(m.get("taskId")), str(m.get("milestoneId"))): m for m in plan.get("milestones") or []}
    for block in plan.get("blocks") or []:
        if block.get("status", "confirmed") != "confirmed":
            continue
        task, milestone = str(block.get("taskId") or ""), str(block.get("milestoneId") or "")
        if not task or not milestone:
            continue  # A timer block without an objective is not a milestone.
        try:
            end = instant(
                datetime.fromisoformat(f"{block['date']}T{block['end']}").replace(tzinfo=ZoneInfo(timezone_name))
            )
        except (KeyError, TypeError, ValueError):
            continue
        key = (task, milestone)
        if key not in grouped:
            metadata = milestones.get(key, {})
            components = metadata.get("knowledgeComponents") or []
            mapped = bool(components) and all(
                isinstance(kc, dict) and kc.get("status") == "approved" and kc.get("componentId") for kc in components
            )
            level = metadata.get("requiredLevel")
            explicit = level in LEVELS[1:]
            grouped[key] = {
                "taskId": task,
                "milestoneId": milestone,
                "blockIds": [],
                "requiredLevel": level if explicit else "application",
                "requirementSource": "explicit_plan" if explicit else "conservative_application_policy_v1",
                "knowledgeComponentIds": sorted({str(kc["componentId"]) for kc in components}) if mapped else [],
                "mappingConfirmed": mapped,
                "targetAt": end.isoformat(),
                "committedAt": instant(confirmed_at).isoformat(),
            }
        item = grouped[key]
        item["blockIds"] = sorted(set([*item["blockIds"], str(block["id"])]))
        item["targetAt"] = max(instant(item["targetAt"]), end).isoformat()
    # No retrospective commitments: confirming after a target cannot improve
    # historical adherence. Each subsequent confirmation gets its own snapshot.
    objectives = [item for item in grouped.values() if instant(item["targetAt"]) > instant(confirmed_at)]
    return {"version": CONTRACT_VERSION, "confirmedAt": instant(confirmed_at).isoformat(), "objectives": objectives}


def _goals(event, start, end):
    measurement = event["plan"].get("measurement") or {}
    if measurement.get("version") != CONTRACT_VERSION:
        return {}  # Do not backfill client history as measured commitments.
    return {
        (str(item["taskId"]), str(item["milestoneId"])): item
        for item in measurement.get("objectives") or []
        if start <= instant(item["targetAt"]) < end
    }


def _evidence_time(goal, user, evidence, cutoff=None):
    if not goal["mappingConfirmed"]:
        return None, "unmapped"
    latest = {}
    for row in evidence:
        payload = row["payload"]
        if row["user"] != user or row["block"] not in goal["blockIds"]:
            continue
        if row["at"] < instant(goal["committedAt"]) or (cutoff and row["at"] > cutoff):
            continue
        if not row["valid"] or not planning_evidence_usable(payload) or payload.get("kc_provisional"):
            continue
        for kc in payload.get("knowledge_component_ids") or []:
            if kc in goal["knowledgeComponentIds"] and (kc not in latest or row["at"] > latest[kc]["at"]):
                latest[kc] = row
    if not set(goal["knowledgeComponentIds"]) <= latest.keys():
        return None, "missing"
    for row in latest.values():
        payload = row["payload"]
        level = payload.get("demonstrated_level", "no_evidence")
        dimensions = ("conceptual", "reasoning", "application", "transfer", "retention")
        required = {
            "recognition": ("recall",),
            "conceptual": dimensions[:1],
            "application": dimensions[:3],
            "transfer": dimensions[:4],
            "retained": dimensions,
        }[goal["requiredLevel"]]
        if (
            level not in LEVELS
            or LEVELS.index(level) < LEVELS.index(goal["requiredLevel"])
            or any((payload.get("dimensions") or {}).get(dimension) == "failed" for dimension in required)
        ):
            return None, "below_requirement"
    return max(row["at"] for row in latest.values()), "satisfied"


def _submission_times(assignments, submissions, student_ids, as_of):
    published = {str(item["id"]) for item in assignments if item.get("published", True)}
    times, excused = defaultdict(list), set()
    for item in submissions:
        key = (int(item.get("user_id") or 0), str(item.get("assignment_id")))
        if key[0] not in student_ids or key[1] not in published:
            continue
        if item.get("workflow_state") == "excused":
            excused.add(key)
        at = instant(item.get("first_submitted_at") or item.get("submitted_at"))
        if item.get("workflow_state", "submitted") in {"submitted", "graded", "pending_review"} and at and at <= as_of:
            times[key].append(at)
    return {key: min(values) for key, values in times.items()}, excused


def cycle_metrics(
    events,
    evidence,
    probes,
    assignments,
    submissions,
    student_ids,
    *,
    as_of,
    minimum_group_size=5,
    timezone_name="Asia/Ho_Chi_Minh",
    course_id=None,
):
    def assignment_id(task_id):
        # Planner IDs are course-qualified; LMS submission IDs are bare.
        if course_id is not None and ":" in task_id:
            prefix, identifier = task_id.split(":", 1)
            return identifier if prefix == str(course_id) else None
        return task_id

    now = instant(as_of)
    local = now.astimezone(ZoneInfo(timezone_name))
    monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    start, end = instant(monday), instant(monday + timedelta(days=7))
    by_user = defaultdict(list)
    for event in sorted(events, key=lambda item: (item["at"], item.get("id", ""))):
        if event["user"] in student_ids and event["at"] <= now:
            by_user[event["user"]].append(event)
    evidence = [row for row in evidence if row["user"] in student_ids and row["at"] <= now]
    evidence_by_block = defaultdict(list)
    for row in evidence:
        evidence_by_block[(row["user"], row["block"])].append(row)
    submitted, excused = _submission_times(assignments, submissions, student_ids, now)
    published = {str(item["id"]) for item in assignments if item.get("published", True)}
    sections = {
        name: {"count": 0, "total": 0, "removedCount": 0, "unverifiedCount": 0} for name in ("original", "current")
    }
    quality = {"satisfied": 0, "missing": 0, "belowRequirement": 0, "unmapped": 0, "total": 0}
    participants = {name: set() for name in sections}
    quality_users = set()
    for user, revisions in by_user.items():
        candidates = [
            (
                event,
                {
                    key: goal
                    for key, goal in _goals(event, start, end).items()
                    if assignment_id(goal["taskId"]) is not None
                },
            )
            for event in revisions
        ]
        candidates = [
            (event, goals)
            for event, goals in candidates
            if goals or event["plan"].get("weekStart") == monday.date().isoformat()
        ]
        # First confirmation with goals in the week is immutable. Latest empty
        # revision is retained so removing every goal cannot reset the baseline.
        first = next((index for index, (_, goals) in enumerate(candidates) if goals), None)
        if first is None:
            continue
        original = candidates[first][1]
        current = candidates[-1][1]
        aliases = defaultdict(set)
        for _, goals in candidates[first:]:
            for key, goal in goals.items():
                aliases[key].update(goal["blockIds"])
        for name, goals in (("original", original), ("current", current)):
            for key, source in goals.items():
                goal = {**source, "blockIds": sorted(aliases[key])}
                task_id = assignment_id(goal["taskId"])
                task_key = (user, task_id)
                due = instant(goal["targetAt"])
                if due > now or task_key in excused or task_id not in published:
                    continue
                participants[name].add(user)
                stats = sections[name]
                stats["total"] += 1
                goal_evidence = [row for block in goal["blockIds"] for row in evidence_by_block[(user, block)]]
                achieved, state = _evidence_time(goal, user, goal_evidence)
                on_time_evidence, _ = _evidence_time(goal, user, goal_evidence, cutoff=due)
                # Authoritative LMS submission proves task delivery, not learning.
                delivered = submitted.get(task_key)
                if delivered and delivered < instant(goal["committedAt"]):
                    delivered = None
                completed = min([at for at in (on_time_evidence, delivered) if at is not None], default=None)
                stats["count"] += int(completed is not None and completed <= due)
                stats["unverifiedCount"] += int(achieved is None and delivered is None)
                if name == "original":
                    stats["removedCount"] += int(key not in current)
                    quality_users.add(user)
                    quality["total"] += 1
                    quality[
                        {
                            "satisfied": "satisfied",
                            "missing": "missing",
                            "below_requirement": "belowRequirement",
                            "unmapped": "unmapped",
                        }[state]
                    ] += 1
    minimum = max(5, minimum_group_size)
    for name, stats in sections.items():
        available = len(participants[name]) >= minimum and stats["total"] > 0
        sections[name] = {
            "status": "available" if available else "insufficient_data",
            "n": len(participants[name]),
            **(stats if available else {key: None for key in stats}),
            "rate": stats["count"] / stats["total"] if available else None,
        }
    available = len(quality_users) >= minimum and quality["total"] > 0
    retention = [row for row in probes if row["user"] in quality_users and start <= row["due"] <= now]
    quality = {
        "status": "available" if available else "insufficient_data",
        "n": len(quality_users),
        **(quality if available else {key: None for key in quality}),
        "rate": quality["satisfied"] / quality["total"] if available else None,
        "retention": {
            "due": len(retention),
            "checked": sum(row["status"] in {"passed", "failed"} for row in retention),
            "passed": sum(row["status"] == "passed" for row in retention),
        }
        if available
        else None,
    }
    return {
        "version": CONTRACT_VERSION,
        "periodStart": monday.isoformat(),
        "periodEnd": (monday + timedelta(days=7)).isoformat(),
        "originalPlan": sections["original"],
        "currentPlan": sections["current"],
        "learningEvidence": quality,
        "causalClaim": False,
        "progressBeforePaceWise": None,
        "completionPolicy": "accepted_assessment_or_lms_submission_not_timer_v1",
    }


def load_cycle_data(db, institution_id, course_id, student_ids, as_of):
    """Project only scoped server records; never parse a student workspace PUT."""

    def scopes(model):
        return (
            model.institution_id == institution_id,
            model.course_id == course_id,
            model.student_user_id.in_(student_ids),
        )

    # Current planner uses a 14-day rolling horizon. Keep that history plus the
    # current week; first-ever adoption is a separate indexed SQL aggregate.
    cutoff = instant(as_of) - timedelta(days=21)
    events = db.scalars(
        select(LearningEvent).where(
            *scopes(LearningEvent),
            LearningEvent.event_type == "PLAN_CONFIRMED",
            LearningEvent.occurred_at <= as_of,
            LearningEvent.occurred_at >= cutoff,
        )
    ).all()
    records = db.scalars(
        select(LearningEvidenceRecord).where(
            *scopes(LearningEvidenceRecord),
            LearningEvidenceRecord.created_at <= as_of,
            LearningEvidenceRecord.created_at >= cutoff,
        )
    ).all()
    probes = db.scalars(
        select(DelayedAssessmentProbe).where(
            *scopes(DelayedAssessmentProbe),
            DelayedAssessmentProbe.due_at <= as_of,
            DelayedAssessmentProbe.due_at >= cutoff,
        )
    ).all()
    return (
        [
            {
                "id": row.id,
                "user": row.student_user_id,
                "at": instant(row.occurred_at),
                "plan": json.loads(row.payload_json).get("confirmed_plan") or {},
            }
            for row in events
        ],
        [
            {
                "user": row.student_user_id,
                "at": instant(row.created_at),
                "block": row.block_id,
                "valid": bool(row.valid),
                "payload": json.loads(row.payload_json),
            }
            for row in records
        ],
        [{"user": row.student_user_id, "due": instant(row.due_at), "status": row.status} for row in probes],
    )


def first_plan_confirmations(db, institution_id, course_id, student_ids):
    return dict(
        db.execute(
            select(LearningEvent.student_user_id, func.min(LearningEvent.occurred_at))
            .where(
                LearningEvent.institution_id == institution_id,
                LearningEvent.course_id == course_id,
                LearningEvent.student_user_id.in_(student_ids),
                LearningEvent.event_type == "PLAN_CONFIRMED",
            )
            .group_by(LearningEvent.student_user_id)
        ).all()
    )
