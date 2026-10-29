import asyncio
import json
import logging
import re
from asyncio import gather
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import get_ident
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.agents.graph import agent
from src.agents.guardrails import normalize_text
from src.agents.safety import enforce_output_policy
from src.agents.workflows.qa import stream_qa_tokens
from src.config import Settings, get_settings
from src.db import get_db
from src.models.schemas import ChatRequest, ChatResponse
from src.persistence_models import LmsCourseContextProjection, LmsFileIndex, StudyTimerSession, UserWorkspace
from src.security import SessionContext, require_csrf
from src.services.agent_memory import (
    load_approved_assessment,
    load_learner_memory,
    load_plan_confirmation,
    load_planning_memory,
    persist_agent_outcome,
)
from src.services.ai_rate_limit import ai_request_slot
from src.services.demo_course_materials import matching_exercise_sections
from src.services.do_chat_memory import agent_history, append_turn, find_do_session, is_open
from src.services.do_preparation import confirmed_block, load_do_context
from src.services.document_roles import document_matches_course
from src.services.learning_events import audit
from src.services.lms_client import LMSClient
from src.services.lms_files import authorized_files, file_url, file_version
from src.services.notification_policy import StudyPreferences
from src.services.plan_confirmation import confirm_partial_plan, confirmation_constraints, effective_availability
from src.services.plan_intelligence import evaluate_plan_quality
from src.services.planning import build_plan_draft
from src.services.planning_time import instant_at, partition_open_assignments
from src.services.reflection_observations import load_reflection_observations, reflection_context
from src.services.replan_policy import plan_diff


async def _ai_admission(
    payload: ChatRequest,
    request: Request,
    session: SessionContext = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
):
    async with ai_request_slot(payload, request, session, settings):
        yield


router = APIRouter()
logger = logging.getLogger("pacewise.api.agent")
_CLIENT_CONTEXT_FIELDS = {
    "availability",
    "unavailable_slots",
    "current_plan",
    "progress_metrics",
    "proposed_milestones",
    "goals",
    "assessment_id",
    "plan_input",
    "planning_stage",
    "plan_confirmation_id",
    "accept_partial_plan",
    "partial_block_ids",
}


def _learning_thread_id(
    session: SessionContext,
    settings: Settings,
    now: datetime | None = None,
) -> str:
    """Return a login-independent memory key for one weekly course cycle."""
    current = now or datetime.now(ZoneInfo(settings.app_timezone))
    calendar = current.isocalendar()
    learning_cycle = f"{calendar.year}-week-{calendar.week:02d}"
    return ":".join(
        (
            settings.institution_id,
            str(session.user_id),
            str(session.course_id),
            learning_cycle,
        )
    )


def _plain_text(value: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(value or ""))).strip()


def _planning_sections_from_chunks(chunks_json: str) -> list[dict[str, Any]]:
    """Build Plan evidence from already student-filtered indexed chunks.

    Upload-time document roles decide visibility. This function only groups
    the resulting public chunks; it never re-opens the teacher original.
    """
    try:
        chunks = json.loads(chunks_json or "[]")
    except json.JSONDecodeError:
        return []
    grouped: dict[str, dict[str, Any]] = {}
    for index, chunk in enumerate(chunks, start=1):
        if not isinstance(chunk, dict) or chunk.get("student_visible") is False:
            continue
        title = _plain_text(chunk.get("section_title") or chunk.get("heading") or "")
        content = _plain_text(chunk.get("content"))
        if not content:
            continue
        title = title or f"Phần {index}"
        key = title.casefold()
        section = grouped.setdefault(
            key,
            {
                "number": len(grouped) + 1,
                "title": title,
                "body": [],
                "criteria": [],
            },
        )
        if content not in section["body"]:
            section["body"].append(content)
    return list(grouped.values())


_EXERCISE_HEADING = re.compile(r"(?i)^(?:buổi|chương)\s+(\d+)\s*[.:)\-–—]?\s*(.*)$")
_RUBRIC_HEADING = re.compile(r"(?i)^rubric\s+\d+(?:[.,]\d+)?\s*điểm\s*:\s*(.+)$")


def _rubric_criteria(value: str) -> list[dict[str, Any]]:
    match = _RUBRIC_HEADING.match(_plain_text(value))
    if not match:
        return []
    result: list[dict[str, Any]] = []
    for raw in match.group(1).split(";"):
        raw = raw.strip().rstrip(".")
        weighted = re.match(r"(.+?)\s+(\d+(?:[.,]\d+)?)$", raw)
        if weighted:
            result.append(
                {
                    "name": weighted.group(1).strip(),
                    "points": float(weighted.group(2).replace(",", ".")),
                }
            )
        elif raw:
            result.append({"name": raw, "points": 1.0})
    return result


def _planning_exercise_sections_from_chunks(chunks_json: str) -> list[dict[str, Any]]:
    """Recover numbered exercise sessions from a normally uploaded Word file.

    The generic indexer emits a separate chunk for a ``Buổi N`` heading and
    its following rubric. Reassembling those chunks preserves the author's
    session number, so an assignment in ``Chương N`` cannot accidentally use
    the Nth arbitrary paragraph in the document.
    """
    try:
        chunks = json.loads(chunks_json or "[]")
    except json.JSONDecodeError:
        return []
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for chunk in chunks:
        if not isinstance(chunk, dict) or chunk.get("student_visible") is False:
            continue
        raw_content = str(chunk.get("content") or "")
        lines = [_plain_text(line) for line in raw_content.splitlines() if _plain_text(line)]
        title = _plain_text(chunk.get("section_title") or chunk.get("heading") or "")
        heading_text = title or (lines[0] if lines else "")
        heading = _EXERCISE_HEADING.match(heading_text)
        if heading:
            if current:
                sections.append(current)
            number = int(heading.group(1))
            section_title = heading.group(2).strip() or f"Buổi {number}"
            current = {"number": number, "title": section_title, "body": [], "criteria": []}
            for line in lines:
                if _EXERCISE_HEADING.match(line):
                    continue
                criteria = _rubric_criteria(line)
                if criteria:
                    current["criteria"].extend(criteria)
                elif line not in current["body"]:
                    current["body"].append(line)
            continue
        if current is None:
            continue
        criteria = _rubric_criteria(title) or _rubric_criteria(raw_content)
        if criteria:
            current["criteria"].extend(criteria)
            continue
        content = _plain_text(raw_content)
        if content and content not in current["body"]:
            current["body"].append(content)
    if current:
        sections.append(current)
    return sections


def _brief_matches_course(sections: list[dict[str, Any]], course_name: str) -> bool:
    """Reject only an explicit, observable subject mismatch."""
    return document_matches_course(sections, course_name)


_QUESTION_MARKER = re.compile(
    r"(?i)(?:^|(?<=[.!?;])\s+)(?P<marker>"
    r"câu|bài|phần|yêu\s+cầu|hạng\s+mục|thành\s+phần|giai\s+đoạn|"
    r"question|exercise|task|requirement|feature|deliverable|component|phase|milestone"
    r")\s+"
    r"(?P<named>\d+(?:\.\d+)*|[ivxlcdm]+)\s*[.:)\-–—]?\s*"
    r"|(?:^|(?<=[.!?;])\s+)(?P<numbered>\d+(?:\.\d+)*)\s*[.)]\s+"
)


def _assignment_parts_from_section(section: dict[str, Any], source_ref: str) -> list[dict[str, Any]]:
    """Extract independently schedulable questions from public assignment text.

    The parser deliberately recognizes only visible numbering/labels.  It does
    not infer questions from course knowledge, so a weak document structure
    degrades to one section-level part instead of fabricated task content.
    """
    raw_blocks = [
        _plain_text(value)
        for value in section.get("body") or []
        if _plain_text(value)
    ]
    explicit: list[tuple[str, str]] = []
    for block in raw_blocks:
        matches = list(_QUESTION_MARKER.finditer(block))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(block)
            content = block[match.start():end].strip(" \t\r\n;,")
            if len(content) < 4:
                continue
            number = match.group("named") or match.group("numbered") or str(len(explicit) + 1)
            marker = " ".join(str(match.group("marker") or "Câu").split()).capitalize()
            explicit.append((f"{marker} {number}", content))

    candidates = explicit
    if not explicit:
        # Indexed DOCX/PDF chunks often preserve one question per paragraph but
        # omit a visible "Câu N" prefix.  Multiple substantial public blocks
        # are still safe, observable units; short headers/instructions are not.
        paragraph_parts = []
        section_title = str(section.get("title") or "Yêu cầu").strip()
        for index, value in enumerate(raw_blocks, start=1):
            if len(value) < 16:
                continue
            folded = value.casefold()
            label = (
                f"Sản phẩm nộp · {section_title}"
                if folded.startswith(("sản phẩm nộp", "deliverable", "submission"))
                else f"{section_title} · Phần {index}"
            )
            paragraph_parts.append((label, value))
        candidates = paragraph_parts if len(paragraph_parts) >= 2 else explicit

    if not candidates:
        combined = " ".join(raw_blocks).strip()
        if not combined:
            return []
        candidates = [(f"Phần {section.get('number') or 1}", combined)]

    result: list[dict[str, Any]] = []
    section_number = str(section.get("number") or 1)
    source_key = re.sub(r"[^A-Za-z0-9]+", "-", source_ref.split("#", 1)[0]).strip("-")[-24:] or "file"
    for index, (label, content) in enumerate(candidates, start=1):
        part_id = f"{source_key}-S{section_number}-P{index}"
        result.append(
            {
                "partId": part_id,
                "label": str(label).strip() or f"Phần {index}",
                "title": content[:180],
                "content": content[:2400],
                "sourceRef": f"{source_ref}&part={part_id}",
                "order": index,
            }
        )
    return result


def _deduplicate_assignment_parts(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one observable assignment part when duplicate files repeat it.

    A teacher may upload or re-index the same brief more than once.  Those
    copies have different source-based part ids, but they must not turn one
    question into several milestones.  Include content in the identity so two
    genuinely different sections that both use a label such as "Câu 1" remain
    separate.
    """
    result: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_content: set[tuple[str, str]] = set()
    for part in parts:
        part_id = str(part.get("partId") or "").strip()
        label = " ".join(str(part.get("label") or "").split()).casefold()
        content = " ".join(str(part.get("content") or "").split()).casefold()
        identity = (label, content)
        if (part_id and part_id in seen_ids) or identity in seen_content:
            continue
        if part_id:
            seen_ids.add(part_id)
        seen_content.add(identity)
        result.append(part)
    return result


def _assignment_planning_candidates(
    chapter: str,
    course_id: str,
    briefs_by_course: dict[str, list[tuple[str, str, list[dict[str, Any]]]]],
    slides_by_course: dict[str, list[tuple[str, str, list[dict[str, Any]]]]],
) -> tuple[list[tuple[str, dict[str, Any]]], str]:
    requested_chapter = normalize_text(chapter)
    course_briefs = briefs_by_course.get(course_id, [])
    exact_briefs = [
        item for item in course_briefs
        if item[1] and normalize_text(item[1]) == requested_chapter
    ]
    # A chapter-specific upload is authoritative. Combining it with a generic
    # exercise book or another chapter duplicates work and can attach entirely
    # unrelated questions to the assignment.
    selected_briefs = exact_briefs or [item for item in course_briefs if not item[1]]
    candidates: list[tuple[str, dict[str, Any]]] = []
    for resource_id, _, sections in selected_briefs:
        candidates.extend((resource_id, section) for section in matching_exercise_sections(chapter, sections))
    if candidates:
        return candidates, "assignment_brief"
    for resource_id, mapped_chapter, sections in slides_by_course.get(course_id, []):
        if mapped_chapter.casefold() == chapter.casefold():
            candidates.extend((resource_id, section) for section in sections[:6])
    return candidates, "chapter_material"


def _attach_assignment_briefs(
    assignments: list[dict[str, Any]],
    *,
    db: Session | None,
    institution_id: str,
    course_ids: tuple[int, ...],
) -> None:
    """Add request-local exercise evidence; never overwrite source records."""
    if db is None or not course_ids:
        return
    rows = db.scalars(
        select(LmsFileIndex).where(
            LmsFileIndex.institution_id == institution_id,
            LmsFileIndex.course_id.in_(course_ids),
            LmsFileIndex.status.not_in(("delete_pending", "unavailable", "failed")),
        )
    ).all()
    course_names = {
        str(item.get("course_id")): str(item.get("course_name") or "")
        for item in assignments
        if item.get("course_id") is not None and item.get("course_name")
    }
    briefs_by_course: dict[str, list[tuple[str, str, list[dict[str, Any]]]]] = {}
    slides_by_course: dict[str, list[tuple[str, str, list[dict[str, Any]]]]] = {}
    for row in rows:
        try:
            metadata = json.loads(row.metadata_json or "{}")
        except json.JSONDecodeError:
            continue
        role = metadata.get("content_role")
        if role == "student_assignment_brief":
            indexed_sections = _planning_sections_from_chunks(row.chunks_json)
            sections = (
                metadata.get("planning_sections")
                or _planning_exercise_sections_from_chunks(row.chunks_json)
                or indexed_sections
            )
            if not sections or not _brief_matches_course(
                indexed_sections or sections,
                str(metadata.get("course_name") or course_names.get(str(row.course_id)) or ""),
            ):
                continue
            mapped_chapter = str(metadata.get("planning_chapter") or "").strip()
            # Generic workbooks remain a fallback. A named chapter is selected
            # only for that exact assignment chapter.
            if normalize_text(mapped_chapter) in {"bai tap theo chuong", "exercise by chapter"}:
                mapped_chapter = ""
            briefs_by_course.setdefault(str(row.course_id), []).append(
                (f"file:{row.file_id}", mapped_chapter, sections)
            )
        elif role == "learning_material" and metadata.get("planning_chapter"):
            sections = metadata.get("planning_sections") or _planning_sections_from_chunks(row.chunks_json)
            if not sections:
                continue
            slides_by_course.setdefault(str(row.course_id), []).append(
                (f"file:{row.file_id}", str(metadata["planning_chapter"]), sections)
            )

    for assignment in assignments:
        chapter = str(assignment.get("chapter") or "").strip()
        if not chapter:
            continue
        course_id = str(assignment.get("course_id"))
        # A missing exercise brief must not make Plan invent task content. Use
        # only the slide already mapped to the exact assignment chapter.
        candidates, evidence_type = _assignment_planning_candidates(
            chapter, course_id, briefs_by_course, slides_by_course
        )
        if not candidates:
            continue
        evidence = []
        assignment_parts = []
        criteria = []
        for resource_id, section in candidates:
            body = "\n".join(str(value) for value in section.get("body") or [])
            section_ref = f"{resource_id}#{'exercise' if evidence_type == 'assignment_brief' else 'section'}={section.get('number')}"
            evidence.append(
                {
                    "resourceId": resource_id,
                    "section": section.get("title"),
                    "content": body,
                    "sourceRef": section_ref,
                }
            )
            if evidence_type == "assignment_brief":
                assignment_parts.extend(_assignment_parts_from_section(section, section_ref))
            # A section/question is planning evidence, not a teacher-approved
            # rubric.  Only preserve criteria explicitly present in the file.
            raw_criteria = section.get("criteria") or []
            for index, criterion in enumerate(raw_criteria, start=1):
                criteria.append(
                    {
                        "id": f"exercise-{section.get('number')}-{index}",
                        "description": f"{section.get('title')}: {criterion.get('name')}",
                        "long_description": body,
                        "points": float(criterion.get("points") or 1),
                    }
                )
        assignment["planning_evidence"] = evidence
        assignment["planning_evidence_type"] = evidence_type
        if assignment_parts:
            assignment["assignment_parts"] = _deduplicate_assignment_parts(assignment_parts)
        if not assignment.get("description"):
            assignment["description"] = "\n\n".join(
                f"{item['section']}\n{item['content']}" for item in evidence
            )
        if evidence_type == "assignment_brief" and criteria and not assignment.get("rubric"):
            assignment["rubric"] = {
                "id": f"exercise-brief:{assignment.get('id')}",
                "title": "Tiêu chí từ tài liệu bài tập",
                "criteria": criteria,
            }


async def _load_lms_agent_context(
    session: SessionContext,
    settings: Settings,
    db: Session | None = None,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Load only LMS data authorized by the server-side PaceWise session."""
    client = LMSClient(settings)
    projections = {
        item.course_id: item
        for item in (
            db.query(LmsCourseContextProjection)
            .filter(
                LmsCourseContextProjection.institution_id == settings.institution_id,
                LmsCourseContextProjection.course_id.in_(session.course_ids),
            )
            .all()
            if db
            else []
        )
    }
    freshness_cutoff = datetime.now(UTC) - timedelta(seconds=max(60, settings.lms_sync_interval_seconds * 3))
    projection_ready = (
        not force_refresh
        and session.role != "student"
        and len(projections) == len(session.course_ids)
        and all(
            (item.updated_at.replace(tzinfo=UTC) if item.updated_at.tzinfo is None else item.updated_at.astimezone(UTC))
            >= freshness_cutoff
            for item in projections.values()
        )
    )
    # Shared projections are not authorization or per-student override caches.
    if db:
        db.commit()  # Native source dispatch shares the same underlying DB pool.
    courses = await client.service_get(
        "/api/pacewise/v1/courses", {"user_id": session.user_id},
    )
    allowed_courses = [item for item in courses if int(item["id"]) in session.course_ids
                       and item.get("enrollment_role", session.role) == session.role]
    course = next((item for item in allowed_courses if int(item["id"]) == session.course_id), None)
    if not course:
        raise HTTPException(status_code=403, detail="LMS enrollment no longer grants this course")

    normalized_assignments = []
    active_modules: list[dict[str, Any]] = []
    planner_items: list[dict[str, Any]] = []
    calendar_items: list[dict[str, Any]] = []
    if session.role == "student":
        try:
            planner_items = await client.service_get(f"/api/pacewise/v1/users/{session.user_id}/planner")
        except Exception as exc:
            # Course projections remain useful when the user-specific planner
            # endpoint is temporarily unavailable. Do not fail the whole chat.
            logger.warning(
                "lms_planner_unavailable user_id=%s error=%s",
                session.user_id,
                type(exc).__name__,
            )
        try:
            calendar_items = await client.service_get(f"/api/pacewise/v1/users/{session.user_id}/calendar")
        except Exception as exc:
            logger.warning(
                "lms_calendar_unavailable user_id=%s error=%s",
                session.user_id,
                type(exc).__name__,
            )
    for enrolled_course in allowed_courses:
        course_id = int(enrolled_course["id"])
        projection = projections.get(course_id) if projection_ready else None
        if projection:
            assignments = json.loads(projection.assignments_json or "[]")
            modules = json.loads(projection.modules_json or "[]")
            submissions = []
        else:
            scoped_params = {"user_id": session.user_id} if session.role == "student" else None
            if db:
                db.commit()  # Persist only per-course projection cache; release before the next source read.
            assignments, submissions, modules = await gather(
                client.service_get(
                    f"/api/pacewise/v1/courses/{course_id}/assignments",
                    scoped_params,
                ),
                client.service_get(
                    f"/api/pacewise/v1/courses/{course_id}/submissions",
                    scoped_params,
                ),
                client.service_get(
                    f"/api/pacewise/v1/courses/{course_id}/modules",
                    scoped_params,
                ),
            )
            if db and session.role != "student":
                context_id = f"{settings.institution_id}:{course_id}"
                cached = db.get(LmsCourseContextProjection, context_id) or LmsCourseContextProjection(
                    id=context_id,
                    institution_id=settings.institution_id,
                    course_id=course_id,
                )
                cached.course_json = json.dumps(enrolled_course, ensure_ascii=False)
                cached.assignments_json = json.dumps(assignments, ensure_ascii=False)
                cached.modules_json = json.dumps(modules, ensure_ascii=False)
                db.add(cached)
        if course_id == session.course_id:
            active_modules = modules
        chapter_by_assignment = {
            str(module_item.get("content_id")): str(module.get("name") or "")
            for module in modules
            for module_item in module.get("items", [])
            if str(module_item.get("item_type") or module_item.get("type") or "").lower() == "assignment"
            and module_item.get("content_id") is not None
        }
        submissions_by_assignment = {int(item["assignment_id"]): item for item in submissions}
        for item in assignments:
            if session.role == "student" and not item.get("published", True):
                continue
            points = float(item.get("points_possible") or 5)
            normalized = {
                    "id": f"{course_id}:{item['id']}",
                    "lms_assignment_id": str(item["id"]),
                    "course_id": str(course_id),
                    "course_code": str(enrolled_course.get("code") or course_id),
                    "course_name": str(enrolled_course.get("name") or ""),
                    "chapter": chapter_by_assignment.get(str(item["id"]), ""),
                    "title": item["title"],
                    "description": _plain_text(item.get("description")),
                    "deadline": item.get("due_at"),
                    "unlock_at": item.get("unlock_at"),
                    "lock_at": item.get("lock_at"),
                    "override_target": item.get("override_target"),
                    "estimated_hours": round(max(0.5, min(4.0, points * 0.2)), 2),
                    "points_possible": points,
                    "assignment_group": item.get("assignment_group"),
                    "grading_type": item.get("grading_type"),
                    "peer_reviews": bool(item.get("peer_reviews")),
                    "rubric": item.get("rubric"),
                    "resource_ids": item.get("resource_ids") or [],
                    "submission": submissions_by_assignment.get(int(item["id"])),
                }
            _attach_learning_availability(normalized, calendar_items, settings.app_timezone)
            normalized_assignments.append(normalized)

    if db and not projection_ready:
        db.commit()

    course_code = str(course.get("code") or session.course_id)
    # Files and permissions are always read live, even when other LMS context is cached.
    # An unavailable authorization service fails the request closed.
    files = await authorized_files(client, session.course_id, session.user_id)
    _attach_assignment_briefs(
        normalized_assignments,
        db=db,
        institution_id=settings.institution_id,
        course_ids=tuple(session.course_ids),
    )
    allowed_ids = {str(item["id"]) for item in files}
    active_modules = [dict(module, items=[item for item in module.get("items", [])
                                        if str(item.get("item_type") or item.get("type") or "").lower() not in {"resource", "file"}
                                        or str(item.get("content_id")) in allowed_ids]) for module in active_modules]
    resources = [{"id": f"file:{item['id']}", "title": item["title"], "kind": item.get("kind", "file"),
                  "module": course_code, "citation": f"[{item['title']}]",
                  "url": file_url(session.course_id, int(item["id"]))
                  if str(item.get("source_url") or "").startswith("/api/files/") else item.get("source_url")}
                 for item in files]
    return {
        "institution_id": settings.institution_id,
        "student_id": str(session.user_id) if session.role == "student" else "",
        "course_id": str(session.course_id),
        "course_code": course_code,
        "role": session.role,
        "assignments": normalized_assignments,
        "modules": active_modules,
        "planner_items": planner_items,
        "calendar_items": calendar_items,
        # The request path performs retrieval only. Raw LMS content is ingested
        # asynchronously by the dedicated worker and never embedded here.
        "learning_resources": [],
        "authorized_file_versions": {f"file:{item['id']}": file_version(item) for item in files},
        "lms_files": resources,
        "allowed_resource_ids": None,
        "do_scope": {},
    }


def _attach_learning_availability(
    assignment: dict[str, Any], calendar_items: list[dict[str, Any]], timezone_name: str
) -> None:
    """Gate planning until the explicitly related teaching session has ended."""

    course_id = str(assignment.get("course_id") or "")
    lessons = [
        item
        for item in calendar_items
        if str(item.get("course_id") or "") == course_id
        and str(item.get("event_kind") or "") in {"class", "class_session"}
        and instant_at(item.get("ends_at"), timezone_name) is not None
    ]
    resource_ids = {str(value) for value in assignment.get("resource_ids") or [] if str(value)}
    release_points: list[datetime] = []
    for resource_id in resource_ids:
        linked = [
            instant_at(item.get("ends_at"), timezone_name)
            for item in lessons
            if resource_id in {str(value) for value in item.get("resource_ids") or []}
        ]
        linked = [value for value in linked if value is not None]
        if linked:
            release_points.append(min(linked))

    # Chapter-title matching supports existing data created before explicit
    # material links were introduced. It is deliberately exact after text
    # normalization so unrelated lessons cannot delay an assignment.
    if not release_points:
        chapter = normalize_text(str(assignment.get("chapter") or ""))
        if chapter:
            linked = [
                instant_at(item.get("ends_at"), timezone_name)
                for item in lessons
                if normalize_text(str(item.get("title") or "")) == chapter
            ]
            linked = [value for value in linked if value is not None]
            if linked:
                release_points.append(min(linked))
    if release_points:
        assignment["learning_available_at"] = max(release_points).isoformat()


async def _load_qa_context(session: SessionContext, settings: Settings) -> dict[str, Any]:
    """Retrieval needs the selected course and live ACL, not every enrolled course."""
    client = LMSClient(settings)
    courses, files = await gather(
        client.service_get("/api/pacewise/v1/courses", {"user_id": session.user_id}),
        authorized_files(client, session.course_id, session.user_id),
    )
    course = next((item for item in courses if int(item["id"]) == session.course_id
                   and int(item["id"]) in session.course_ids
                   and item.get("enrollment_role", session.role) == session.role), None)
    if not course:
        raise HTTPException(status_code=403, detail="Course access is no longer available")
    return {"institution_id": settings.institution_id, "student_id": str(session.user_id),
            "course_id": str(session.course_id), "course_code": str(course.get("code") or session.course_id),
            "role": session.role, "authorized_file_versions": {f"file:{item['id']}": file_version(item) for item in files},
            "learning_resources": [], "lms_files": [], "assignments": [], "modules": [], "planner_items": [],
            "allowed_resource_ids": None, "do_scope": {}}


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(_ai_admission)])
async def chat(
    payload: ChatRequest,
    request: Request,
    session: SessionContext = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Run one agent turn with authenticated user, role, course and LMS context."""
    scoped_session = session
    requested_course_id = payload.context.get("do_course_id")
    do_block_id = str(payload.context.get("do_block_id") or "").strip()
    if requested_course_id is not None and do_block_id and payload.workflow in {"do", "qa"}:
        try:
            course_id = int(requested_course_id)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="Invalid course_id") from exc
        if course_id not in session.course_ids:
            raise HTTPException(status_code=403, detail="Course is outside the authenticated LMS enrollment")
        scoped_session = replace(session, course_id=course_id)
    if payload.workflow == "reflect" and payload.context.get("reflection_course_id"):
        try:
            reflection_course_id = int(payload.context["reflection_course_id"])
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="Invalid reflection course") from exc
        if reflection_course_id not in session.course_ids:
            raise HTTPException(status_code=403, detail="Reflection course is outside enrollment")
        scoped_session = replace(session, course_id=reflection_course_id)

    confirming_plan = (
        payload.workflow == "plan"
        and not payload.context.get("plan_input")
        and any(word in normalize_text(payload.message) for word in ("xac nhan", "dong y", "chap nhan", "confirm"))
    )
    if do_block_id and payload.workflow in {"do", "qa"}:
        block = confirmed_block(db, scoped_session, settings, do_block_id)
        db.rollback()
        lms_context = await load_do_context(scoped_session, settings, block)
    elif payload.workflow == "qa":
        db.rollback()
        lms_context = await _load_qa_context(scoped_session, settings)
    else:
        lms_context = await _load_lms_agent_context(scoped_session, settings, db, force_refresh=confirming_plan)
    safe_context = {key: value for key, value in payload.context.items() if key in _CLIENT_CONTEXT_FIELDS}
    if payload.workflow == "qa":
        safe_context["qa_history"] = [turn.model_dump() for turn in payload.qa_history]
        if do_block_id and requested_course_id is not None:
            transcript = find_do_session(
                db,
                institution_id=settings.institution_id,
                user_id=scoped_session.user_id,
                course_id=scoped_session.course_id,
                block_id=do_block_id,
            )
            if transcript is not None and is_open(transcript):
                # A Do transcript is server-owned. Never let a client mix turns
                # from another block or another learner into model context.
                safe_context["qa_history"] = agent_history(transcript)
    if payload.workflow == "plan" and isinstance(safe_context.get("plan_input"), dict):
        workspace = db.get(UserWorkspace, scoped_session.user_id)
        saved = json.loads(workspace.state_json) if workspace else {}
        plan_input = dict(safe_context["plan_input"])
        plan_input["availability"] = effective_availability(
            saved,
            list(plan_input.get("availability") or []),
        )
        try:
            plan_input["studyPreferences"] = StudyPreferences.model_validate(
                plan_input.get("studyPreferences", saved.get("studyPreferences")) or {}
            ).model_dump(by_alias=True)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="Invalid study rhythm preferences") from exc
        safe_context["plan_input"] = plan_input
    assessment_id = str(safe_context.pop("assessment_id", "")).strip() or None
    do_event = (safe_context.get("progress_metrics") or {}).get("do_session") or {}
    is_do_assessment = payload.workflow == "do" and do_event.get("action") == "assess"
    trusted_assessment: dict[str, Any] = {}
    if payload.workflow == "understanding" or is_do_assessment:
        if not assessment_id:
            raise HTTPException(status_code=422, detail="assessment_id is required for understanding checks")
        trusted_assessment = await load_approved_assessment(
            db,
            scoped_session,
            settings,
            assessment_id,
        )
    learner_memory = load_learner_memory(db, scoped_session, settings)
    planning_memory = (
        load_planning_memory(db, scoped_session, settings)
        if payload.workflow == "plan" and payload.context.get("plan_input")
        else learner_memory
    )
    if payload.workflow == "reflect":
        requested_metrics = safe_context.get("progress_metrics") or {}
        try:
            observed = load_reflection_observations(db, scoped_session, settings, requested_metrics)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail="Invalid reflection week") from exc
        safe_context["progress_metrics"] = reflection_context(observed, requested_metrics)
    thread_id = _learning_thread_id(scoped_session, settings)
    config = {"configurable": {"thread_id": thread_id}}
    is_plan_confirmation = (
        payload.workflow == "plan"
        and not safe_context.get("plan_input")
        and any(word in normalize_text(payload.message) for word in ("xac nhan", "dong y", "chap nhan", "confirm"))
    )
    canonical_confirmation = None
    replaying_confirmation = False
    if is_plan_confirmation:
        confirmation_id = str(safe_context.get("plan_confirmation_id") or "")
        canonical_confirmation, replaying_confirmation = load_plan_confirmation(
            db, scoped_session, settings, confirmation_id
        )
        if not canonical_confirmation:
            raise HTTPException(
                status_code=409,
                detail="Bản kế hoạch chờ xác nhận không còn trên máy chủ. Hãy phân tích lại để tạo bản mới.",
            )
        if confirmation_id and canonical_confirmation.get("createdAt") != confirmation_id:
            raise HTTPException(status_code=409, detail="Bản kế hoạch đã thay đổi. Hãy tải lại bản xem trước.")
        partial_requested = safe_context.get("accept_partial_plan") is True
        if replaying_confirmation and partial_requested != ((canonical_confirmation.get("confirmation") or {}).get("mode") == "partial"):
            raise HTTPException(status_code=409, detail="Confirmation mode changed; refresh the plan")
        if not replaying_confirmation:
            workspace = db.get(UserWorkspace, scoped_session.user_id)
            saved = json.loads(workspace.state_json or "{}") if workspace else {}
            calendar = await LMSClient(settings).service_get(f"/api/pacewise/v1/users/{scoped_session.user_id}/calendar")
            canonical_confirmation = confirmation_constraints(canonical_confirmation, saved, calendar)
        quality = (
            canonical_confirmation.get("qualityEvaluation")
            if replaying_confirmation
            else evaluate_plan_quality(canonical_confirmation, lms_context["assignments"], now=datetime.now(UTC))
        )
        partial = quality.get("partialConfirmation") or {}
        if not replaying_confirmation and partial_requested:
            expected_ids = safe_context.get("partial_block_ids")
            if not isinstance(expected_ids, list) or not expected_ids or any(not isinstance(v, str) for v in expected_ids):
                raise HTTPException(status_code=422, detail="Explicit partial plan preview is required")
            if not partial.get("canConfirm") or set(expected_ids) != set(partial.get("blockIds") or []):
                raise HTTPException(status_code=409, detail="Safe plan subset changed; re-analyze and review it again")
            canonical_confirmation = confirm_partial_plan(canonical_confirmation, partial)
        elif not replaying_confirmation and not quality["canConfirm"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Plan has blocking constraints; re-analyze before confirmation",
                    "errors": quality["blockingErrors"],
                },
            )
        canonical_confirmation = {**canonical_confirmation, "qualityEvaluation": quality}
    # All context above is detached plain data. Release the read transaction
    # before waiting for model admission/provider calls.
    db.rollback()
    try:
        active_agent = getattr(request.app.state, "agent", agent)
        if canonical_confirmation is not None:
            result = {
                "workflow": "plan",
                "status": "completed",
                "response": "Đã xác nhận bản kế hoạch được server kiểm tra.",
                "student_decision": {"action": "confirmed", "workflow": "plan"},
                "pending_action": None,
                "output": {"confirmed_plan": canonical_confirmation},
            }
            update_state = getattr(active_agent, "aupdate_state", None)
            if callable(update_state) and not replaying_confirmation:
                await update_state(config, {"pending_action": None, "output": result["output"]}, as_node="plan")
        else:
            agent_context = lms_context
            agent_goals = safe_context.get("goals")
            if payload.workflow == "plan":
                planning_now = datetime.now(ZoneInfo(settings.app_timezone))
                active_assignments, _ = partition_open_assignments(
                    lms_context["assignments"], now=planning_now, timezone_name=settings.app_timezone,
                    fallback=planning_now.date() + timedelta(days=14))
                agent_context = {**lms_context, "assignments": active_assignments}
                active_ids = {str(a.get("id")) for a in active_assignments}
                if isinstance(agent_goals, list):
                    agent_goals = [g for g in agent_goals if isinstance(g, dict) and str(g.get("task_id") or g.get("taskId")) in active_ids]
            result = await active_agent.ainvoke(
                {
                    **safe_context,
                    **agent_context,
                    **({"goals": agent_goals} if agent_goals is not None else {}),
                    **({"approved_rubric": trusted_assessment["approved_rubric"]} if trusted_assessment else {}),
                    "learner_profile": {
                        key: value for key, value in planning_memory["profile"].items() if key != "pending_plan_draft"
                    },
                    "mastery_profile": planning_memory["mastery"],
                    "misconceptions": planning_memory["misconceptions"],
                    "query": payload.message,
                    "request": {
                        "channel": "pacewise_web",
                        "workflow_hint": payload.workflow,
                        "locale": payload.locale,
                        **(
                            {
                                "assessment_id": assessment_id,
                                "question": trusted_assessment["question"],
                                "question_type": trusted_assessment["question_type"],
                                "answer_type": trusted_assessment["answer_type"],
                                "correct_answer": trusted_assessment["correct_answer"],
                                "topic": trusted_assessment["topic"],
                                "block_id": str(do_event.get("block_id") or ""),
                                "assessment_attempt": do_event.get("assessment_attempt") or {},
                            }
                            if trusted_assessment
                            else {}
                        ),
                    },
                },
                config=config,
            )
        if trusted_assessment and isinstance(result.get("assessment_result"), dict):
            result["assessment_result"]["rubric_version"] = trusted_assessment["rubric_version"]
            result["assessment_result"]["assessment_id"] = assessment_id
            result["_trusted_assessment"] = trusted_assessment
            result["request"] = {
                **(result.get("request") or {}),
                "assessment_id": assessment_id,
                "topic": trusted_assessment["topic"],
                "assessment_attempt": do_event.get("assessment_attempt")
                or {
                    "response": payload.message,
                    "first_attempt": True,
                    "hint_level": 0,
                    "block_id": str(do_event.get("block_id") or ""),
                },
            }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Agent request failed") from exc

    security_flags = result.get("security_flags") or {}
    security_action = str(security_flags.get("action") or "")
    result_workflow = str(result.get("workflow") or payload.workflow or "qa")
    source_refs = (result.get("source_refs") or []) if result_workflow in {"qa", "do"} else []
    explicit_mode = str(result.get("mode") or "")
    if security_action == "guided_help":
        mode = "integrity"
    elif explicit_mode in {"conversation", "out_of_scope", "abstained", "grounded"}:
        mode = explicit_mode
    elif source_refs:
        mode = "grounded"
    elif result_workflow == "qa":
        mode = "abstained"
    else:
        mode = result.get("workflow", payload.workflow)

    output = dict(result.get("output") or {})
    plan_input = safe_context.get("plan_input")
    if payload.workflow == "plan" and isinstance(plan_input, dict):
        workspace = db.get(UserWorkspace, scoped_session.user_id)
        workspace_state = json.loads(workspace.state_json) if workspace else {}
        existing_plan = workspace_state.get("plan") or {}
        # Protect only observed completion or a genuinely active durable timer.
        # Merely reaching a planned block's end time is not proof of learning.
        completed_ids = {
            str(item.get("blockId") or "")
            for item in workspace_state.get("sessions") or []
            if item.get("blockId")
        }
        active_ids: set[str] = set()
        timer_rows = db.scalars(
            select(StudyTimerSession).where(
                StudyTimerSession.institution_id == settings.institution_id,
                StudyTimerSession.user_id == scoped_session.user_id,
            )
        ).all()
        for timer in timer_rows:
            timer_state = json.loads(timer.state_json or "{}")
            if timer_state.get("status") == "completed":
                completed_ids.add(str(timer.block_id))
            elif timer_state.get("status") in {"running", "paused"}:
                active_ids.add(str(timer.block_id))
        old_blocks = existing_plan.get("blocks") or []
        saved_pins = [
            (
                dict(block, status="history")
                if str(block.get("id")) in completed_ids
                else dict(block, status="active")
                if str(block.get("id")) in active_ids
                else block
            )
            for block in old_blocks
        ]
        plan_input = {**plan_input, "pinnedBlocks": [*saved_pins, *(plan_input.get("pinnedBlocks") or [])]}
        unique_pins = {str(block.get("id")): block for block in plan_input["pinnedBlocks"] if block.get("id")}
        # A submitted duplicate must not erase server-protected evidence/state.
        for block in saved_pins:
            if block.get("status") in {"history", "active"}:
                unique_pins[str(block["id"])] = block
        plan_input["pinnedBlocks"] = list(unique_pins.values())
        draft = build_plan_draft(
            plan_input,
            lms_context["assignments"],
            proposed_milestones=result.get("proposed_milestones") or [],
            learner_profile=planning_memory["profile"],
            mastery_profile=planning_memory["mastery"],
            timezone_name=settings.app_timezone,
        )
        draft["decompositionAnalysis"] = {
            "modelOutput": output.get("model_output_validation") or {},
            "routes": output.get("decomposition_routes") or {},
            "agentAnalysis": str(result.get("analysis") or ""),
        }
        milestone_validation = output.get("plan_validation")
        if milestone_validation:
            output["milestone_validation"] = milestone_validation
        shortfalls = draft["feasibility"]["shortfalls"]
        quality = draft["qualityEvaluation"]
        output["plan_validation"] = {
            "valid": quality["canConfirm"],
            "errors": [
                {
                    "code": "DEADLINE_CAPACITY_SHORTFALL",
                    "task_id": item["taskId"],
                    "missing_minutes": item["missingMin"],
                }
                for item in shortfalls
            ]
            + [error for error in quality["blockingErrors"] if error["code"] != "DEADLINE_CAPACITY_SHORTFALL"],
            "warnings": quality["warnings"],
        }
        output["plan_draft"] = draft
        diff = plan_diff(
            existing_plan.get("blocks") or [],
            draft["blocks"],
            previous_risks=(existing_plan.get("feasibility") or {}).get("deadlineRisks") or [],
            proposed_risks=(draft.get("feasibility") or {}).get("deadlineRisks") or [],
        )
        draft["diff"] = diff
        output["plan_diff"] = diff
        audit(
            db,
            scoped_session,
            settings,
            "REPLAN_PROPOSED",
            str(draft.get("createdAt") or thread_id),
            str(draft.get("createdAt") or thread_id),
            {"diff": diff, "requires_confirmation": True},
        )
        result["output"] = output
        result["pending_action"] = (
            {"workflow": "plan", "type": "confirm_plan", "payload": {"draft_created_at": draft["createdAt"]}}
            if quality["canConfirm"] or quality["partialConfirmation"]["canConfirm"]
            else None
        )
        result["status"] = "awaiting_student"

    review_case_id = (
        None if replaying_confirmation else persist_agent_outcome(db, scoped_session, settings, result, assessment_id)
    )
    output = dict(result.get("output") or output)

    safe_response, output_policy = enforce_output_policy(
        str(result.get("response") or ""),
        input_decision=security_flags,
    )
    output["safety"] = {
        "input": security_flags,
        "output": output_policy,
    }

    if payload.workflow == "qa" and do_block_id and requested_course_id is not None:
        transcript = find_do_session(
            db,
            institution_id=settings.institution_id,
            user_id=scoped_session.user_id,
            course_id=scoped_session.course_id,
            block_id=do_block_id,
        )
        if transcript is not None and is_open(transcript):
            append_turn(
                transcript,
                question=payload.message,
                response=safe_response,
                kind=mode,
                source_refs=[item for item in source_refs if isinstance(item, dict)],
            )
            db.commit()

    return ChatResponse(
        response=safe_response,
        workflow=result_workflow,
        mode=mode,
        status=result.get("status", "completed"),
        pending_action=result.get("pending_action"),
        output=output or None,
        proposed_milestones=(result.get("proposed_milestones") or []) if result_workflow == "plan" else [],
        recovery_options=(result.get("recovery_options") or []) if result_workflow == "recover" else [],
        reflection_draft=result.get("reflection_draft") if result_workflow == "reflect" else None,
        assessment_result=result.get("assessment_result"),
        review_case_id=review_case_id,
        progress_metrics=result.get("progress_metrics") or {},
        risk_signals=(result.get("risk_signals") or []) if result_workflow == "tracking" else [],
        source_refs=source_refs,
    )


def _stream_line(event: dict[str, Any]) -> bytes:
    return (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


@router.post("/chat/stream", dependencies=[Depends(_ai_admission)], include_in_schema=False)
async def stream_chat(
    payload: ChatRequest,
    request: Request,
    session: SessionContext = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream QA model deltas over TLS; persist and trust only the final validated turn."""
    if payload.workflow != "qa":
        raise HTTPException(status_code=422, detail="Streaming is available only for course Q&A")

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    loop_thread = get_ident()
    accepting = True

    def emit(delta: str) -> None:
        if not accepting or not delta:
            return
        event = {"type": "delta", "text": delta}
        if get_ident() == loop_thread:
            queue.put_nowait(event)
            return
        # QA graph nodes may run in a worker thread. Wait until the owning
        # event loop has accepted this delta so the final event can never
        # overtake model output that was already produced.
        asyncio.run_coroutine_threadsafe(queue.put(event), loop).result()

    async def run_turn() -> None:
        try:
            with stream_qa_tokens(emit):
                result = await chat(
                    payload=payload,
                    request=request,
                    session=session,
                    settings=settings,
                    db=db,
                )
            await queue.put({"type": "final", "result": result.model_dump(mode="json")})
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else "Yêu cầu chatbot không hợp lệ."
            await queue.put({"type": "error", "status": exc.status_code, "detail": detail})
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("chat_stream_failed")
            await queue.put({"type": "error", "status": 500, "detail": "Dịch vụ AI tạm thời chưa sẵn sàng."})

    async def events():
        nonlocal accepting
        task = asyncio.create_task(run_turn())
        try:
            yield _stream_line({"type": "status", "stage": "retrieval", "message": "Đang tìm trong học liệu của môn…"})
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=10)
                except TimeoutError:
                    yield _stream_line({"type": "status", "stage": "working", "message": "Đang tổng hợp câu trả lời…"})
                    continue
                yield _stream_line(event)
                if event["type"] in {"final", "error"}:
                    break
        finally:
            accepting = False
            if not task.done():
                task.cancel()

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-store, no-transform",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/status")
async def agent_status() -> dict:
    return {"status": "ready", "agent": "PaceWise LangGraph Agent v1.0"}
