"""Deterministic preparation of one server-confirmed block, with live LMS ACLs.

Module membership is evidence of scope. Similar titles are never membership.
No LLM, embedding, cross-course loading, or cached permission decisions here.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import Settings
from src.persistence_models import LearnerMemory
from src.security import SessionContext
from src.services.lms_client import LMSClient
from src.services.lms_files import authorized_files, file_url, file_version
from src.services.planning_time import block_at


def confirmed_block(db: Session, session: SessionContext, settings: Settings, block_id: str) -> dict:
    if session.role != "student" or session.course_id not in session.course_ids:
        raise HTTPException(403, "Student enrollment required")
    rows = db.scalars(
        select(LearnerMemory).where(
            LearnerMemory.institution_id == settings.institution_id,
            LearnerMemory.user_id == session.user_id,
            LearnerMemory.course_id.in_(session.course_ids),
        )
    )
    for row in rows:
        plan = json.loads(row.profile_json or "{}").get("last_confirmed_plan") or {}
        for block in plan.get("blocks") or []:
            if block.get("id") == block_id and str(block.get("taskId", "")).startswith(f"{session.course_id}:"):
                if block.get("status") in {"tentative", "history"}:
                    break
                return dict(block)
    raise HTTPException(409, "Start from a server-confirmed study block")


def _url_key(url: str) -> str:
    parts = urlsplit(url)
    # Retain queries: distinct external documents can share a path.
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ""))


def _resource_rank(resource: dict) -> tuple:
    kind, title = resource["kind"].lower(), resource["title"].lower()
    priority = (
        3
        if "video" in kind
        else 0
        if kind in {"slides", "slide"}
        else 1
        if (kind in {"rubric", "assignment", "exercise", "practice"} or re.search(r"rubric|bài tập|luyện tập", title))
        else 2
    )
    return priority, title, resource["id"]


def resolve_scope(
    assignment: dict, modules: list[dict], files: list[dict], course_id: int, contents: list[dict] | None = None
) -> dict:
    assignment_id = str(assignment["id"])
    quiz_id = str(assignment.get("quiz_id") or "")
    explicit_ids = {str(value) for value in assignment.get("module_ids") or []}
    if assignment.get("module_id") is not None:
        explicit_ids.add(str(assignment["module_id"]))
    scoped_modules = []
    for module in modules:
        if module.get("published") is False:
            continue
        linked = str(module.get("id")) in explicit_ids
        for item in module.get("items") or []:
            if item.get("published") is False:
                continue
            kind = str(item.get("type") or item.get("item_type") or "").lower()
            linked |= kind == "assignment" and str(item.get("content_id")) == assignment_id
            linked |= bool(quiz_id and kind == "quiz" and str(item.get("content_id")) == quiz_id)
        if linked:
            scoped_modules.append(module)

    candidates = []
    file_modules: dict[str, str] = {}
    allowed = {str(file["id"]): file for file in files}
    urls = {_url_key(str(file.get("source_url") or "")): str(file["id"]) for file in files}
    pages = {
        str(item["id"]): item
        for item in contents or []
        if item.get("kind") == "page" and item.get("published") is not False
    }
    for module in scoped_modules:
        module_name = str(module.get("name") or module.get("title") or "Học liệu")
        for item in module.get("items") or []:
            if item.get("published") is False:
                continue
            kind = str(item.get("type") or item.get("item_type") or "").lower()
            source_url = str(item.get("external_url") or item.get("url") or item.get("html_url") or "")
            if kind in {"file", "resource"}:
                identifier = str(item.get("content_id") or "")
                # Legacy external file module items need an authorized file manifest match.
                identifier = identifier or urls.get(_url_key(source_url), "")
                if identifier in allowed:
                    file_modules[identifier] = module_name
            elif kind == "page" and str(item.get("content_id")) in pages:
                page = pages[str(item["content_id"])]
                text = re.sub(r"<[^>]+>", " ", str(page.get("body") or "")).strip()
                if text:
                    candidates.append(
                        {
                            "id": f"page:{course_id}:{page['id']}",
                            "title": page["title"],
                            "kind": "page",
                            "module": module_name,
                            "url": None,
                            "excerpt": text[:2000],
                            "content": text,
                            "citation": f"[{module_name} · {page['title']}]",
                            "version": hashlib.sha256(text.encode()).hexdigest(),
                        }
                    )
            elif kind in {"page", "externalurl", "external_url", "video", "lecture_video"} and source_url:
                if urlsplit(source_url).scheme.lower() not in {"http", "https", ""}:
                    continue
                candidates.append(
                    {
                        "id": f"module:{module['id']}:{item['id']}",
                        "title": item["title"],
                        "kind": kind,
                        "module": module_name,
                        "url": source_url,
                        "citation": f"[{module_name} · {item['title']}]",
                        "version": str(item.get("updated_at") or ""),
                    }
                )
    # Only linked files, never a title-based fallback into other modules.
    for identifier, module_name in file_modules.items():
        file = allowed[identifier]
        source_url = str(file.get("source_url") or "")
        candidates.append(
            {
                "id": f"file:{identifier}",
                "title": file["title"],
                "kind": file.get("kind") or "file",
                "module": module_name,
                "url": file_url(course_id, int(identifier))
                if source_url.startswith(("/api/files/", "/static/mock-files/"))
                else source_url,
                "source_url": source_url,
                "citation": f"[{module_name} · {file['title']}]",
                "version": file_version(file),
                "checksum": (file.get("latest_version") or {}).get("checksum_sha256"),
            }
        )

    resources, seen = [], set()
    for candidate in sorted(candidates, key=_resource_rank):
        identities = {f"id:{candidate['id']}"}
        if candidate.get("checksum"):
            identities.add(f"hash:{candidate['checksum']}")
        if candidate.get("source_url") or candidate.get("url"):
            identities.add(f"url:{_url_key(candidate.get('source_url') or candidate['url'])}")
        if not (identities & seen):
            resources.append(candidate)
            seen.update(identities)
    versions = {f"file:{identifier}": file_version(allowed[identifier]) for identifier in file_modules}
    scope = {
        "status": "mapped" if scoped_modules else "unmapped",
        "module_ids": sorted(str(module["id"]) for module in scoped_modules),
        "module_names": [str(module.get("name") or module.get("title") or "") for module in scoped_modules],
        "assignment_id": assignment_id,
    }
    fingerprint = hashlib.sha256(
        json.dumps({"scope": scope, "resources": resources}, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    # Videos supplement primary materials rather than occupy all three slots.
    primary = [resource for resource in resources if "video" not in resource["kind"].lower()]
    videos = [resource for resource in resources if "video" in resource["kind"].lower()]
    return {"scope": scope, "resources": primary + videos[:1], "versions": versions, "resource_version": fingerprint}


async def load_do_context(session: SessionContext, settings: Settings, block: dict) -> dict[str, Any]:
    client = LMSClient(settings)
    courses = await client.service_get("/api/pacewise/v1/courses", {"user_id": session.user_id})
    course = next(
        (
            course
            for course in courses
            if int(course["id"]) == session.course_id and course.get("enrollment_role", "student") == "student"
        ),
        None,
    )
    if not course:
        raise HTTPException(403, "LMS enrollment no longer grants this course")
    params = {"user_id": session.user_id}
    assignments, modules, files, contents = await asyncio.gather(
        client.service_get(f"/api/pacewise/v1/courses/{session.course_id}/assignments", params),
        client.service_get(f"/api/pacewise/v1/courses/{session.course_id}/modules", params),
        authorized_files(client, session.course_id, session.user_id),
        client.service_get(f"/api/pacewise/v1/courses/{session.course_id}/content", params),
    )
    assignment = next(
        (
            item
            for item in assignments
            if f"{session.course_id}:{item['id']}" == block["taskId"] and item.get("published") is not False
        ),
        None,
    )
    if not assignment:
        raise HTTPException(409, "Study assignment is no longer available")
    resolved = resolve_scope(assignment, modules, files, session.course_id, contents)
    end = block_at(block["date"], block["end"], settings.app_timezone)
    if assignment.get("due_at"):
        due = datetime.fromisoformat(str(assignment["due_at"]).replace("Z", "+00:00"))
        if due.tzinfo is None:
            due = due.replace(tzinfo=ZoneInfo(settings.app_timezone))
        if end > due:
            raise HTTPException(409, "Confirmed block exceeds the current assignment deadline")
    learning_resources = [
        {
            "resource_id": resource["id"],
            "course_code": str(course.get("code") or session.course_id),
            "content": resource["content"],
            "citation": resource["citation"],
            "document_title": resource["title"],
            "page": 1,
            "paragraph": 1,
        }
        for resource in resolved["resources"]
        if resource.get("content")
    ]
    if resolved["scope"]["status"] == "mapped":
        description = re.sub(r"<[^>]+>", " ", str(assignment.get("description") or "")).strip()
        rubric = assignment.get("rubric")
        for kind, content in [
            ("assignment", description),
            ("rubric", json.dumps(rubric, ensure_ascii=False) if rubric else ""),
        ]:
            if not content:
                continue
            identifier = f"{kind}:{session.course_id}:{assignment['id']}"
            title = f"{'Yêu cầu' if kind == 'assignment' else 'Rubric'}: {assignment['title']}"
            resource = {
                "id": identifier,
                "title": title,
                "kind": kind,
                "module": " · ".join(resolved["scope"]["module_names"]),
                "url": None,
                "excerpt": content[:2000],
                "citation": f"[{title}]",
                "version": hashlib.sha256(content.encode()).hexdigest(),
            }
            resolved["resources"].insert(1 if kind == "assignment" else 2, resource)
            learning_resources.append(
                {
                    "resource_id": identifier,
                    "course_code": str(course.get("code") or session.course_id),
                    "content": content,
                    "citation": resource["citation"],
                    "document_title": title,
                    "page": 1,
                    "paragraph": 1,
                }
            )
    resolved["resources"].sort(key=_resource_rank)
    objective = str(block.get("milestoneTitle") or "Ca tự học cho nhiệm vụ này")
    minutes = int(
        (
            block_at(block["date"], block["end"], settings.app_timezone)
            - block_at(block["date"], block["start"], settings.app_timezone)
        ).total_seconds()
        / 60
    )
    if minutes <= 0:
        raise HTTPException(409, "Invalid confirmed block duration")
    resource_version = hashlib.sha256(
        json.dumps(
            {"materials": resolved["resource_version"], "instructions": learning_resources},
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    prepared = {
        "action": "prepare",
        "status": "ready",
        "block_id": block["id"],
        "task_id": block["taskId"],
        "title": assignment["title"],
        "objective": objective,
        "planned_minutes": minutes,
        "scope": resolved["scope"],
        "resource_version": resource_version,
        "recommended_resources": [
            {key: value for key, value in resource.items() if key not in {"checksum", "source_url", "content"}}
            for resource in resolved["resources"][:3]
        ],
        "opening_prompt": f"Ca này: {objective}. Hãy gửi bước đang vướng để cùng kiểm tra lập luận.",
    }
    return {
        "institution_id": settings.institution_id,
        "student_id": str(session.user_id),
        "course_id": str(session.course_id),
        "course_code": str(course.get("code") or session.course_id),
        "role": "student",
        "assignments": [{**assignment, "id": block["taskId"]}],
        "modules": [],
        "learning_resources": learning_resources,
        "lms_files": prepared["recommended_resources"],
        # A Do support question may depend on an earlier/later chapter in the
        # same course. Keep the current chapter as the preferred retrieval
        # tier, while the course ACL remains the hard outer boundary.
        "authorized_file_versions": {
            f"file:{item['id']}": file_version(item) for item in files
        },
        "allowed_resource_ids": sorted([
            *(f"file:{item['id']}" for item in files),
            *(item["resource_id"] for item in learning_resources),
        ]),
        "preferred_resource_ids": sorted([
            *resolved["versions"],
            *(item["resource_id"] for item in learning_resources),
        ]),
        "do_scope": resolved["scope"],
        # Graph checkpoints can contain citations from a previous chapter/turn.
        "source_refs": [],
        "retrieved_passages": [],
        "do_session": prepared,
    }
