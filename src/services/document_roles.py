"""Visibility policy for teacher-authored assignment documents.

The model never decides access control.  Teachers declare the document role;
for a mixed Word package this module deterministically removes answer-key
sections before student-facing indexing or planning evidence is produced.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

PUBLIC_DOCUMENT_ROLES = {
    "learning_material",
    "student_assignment_brief",
    "student_rubric",
    "mixed_assignment_package",
}
DOCUMENT_ROLES = PUBLIC_DOCUMENT_ROLES | {"teacher_solution"}


def fold_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value).replace("Đ", "D").replace("đ", "d"))
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", normalized.casefold()).strip()


def _subject_tokens(value: str) -> set[str]:
    ignored = {"bai", "tap", "mon", "course", "nhap", "hoc", "he", "va", "lap", "trinh"}
    return {
        token
        for token in fold_text(value).split()
        if len(token) >= 2 and token not in ignored
    }


def declared_course_subject(items: list[dict[str, Any]]) -> str:
    """Return an explicit ``Bài tập môn ...`` label without inferring one."""
    for item in items[:6]:
        values = [
            item.get("section_title"), item.get("heading"), item.get("title"),
            *((item.get("body") or [])[:2] if isinstance(item.get("body"), list) else []),
            item.get("content"),
        ]
        for value in values:
            for line in str(value or "").splitlines():
                match = re.match(r"^bai\s+tap\s+mon\s+(.+)$", fold_text(line))
                if match:
                    return match.group(1).strip()
    return ""


def document_matches_course(items: list[dict[str, Any]], course_name: str) -> bool:
    """Reject only a declared course subject that conflicts with the target."""
    declared = _subject_tokens(declared_course_subject(items))
    expected = _subject_tokens(course_name)
    if not declared or not expected:
        return True
    required = 1 if min(len(declared), len(expected)) == 1 else 2
    return len(declared & expected) >= required


_PRIVATE_MARKERS = (
    "dap an",
    "loi giai",
    "answer key",
    "model answer",
    "huong dan cham",
    "goi y dap an",
    "teacher solution",
    "teacher note",
    "danh cho giang vien",
)
_PUBLIC_RESET_MARKERS = (
    "bai tap",
    "de bai",
    "assignment",
    "kiem tra",
    "de giua ky",
    "de cuoi ky",
    "rubric chung",
    "tieu chi cham",
    "yeu cau",
)


def section_visibility(section_title: str, current: str = "student") -> str:
    """Return student/teacher, carrying the prior state for neutral headings."""
    title = fold_text(section_title)
    if any(marker in title for marker in _PRIVATE_MARKERS):
        return "teacher"
    if any(marker in title for marker in _PUBLIC_RESET_MARKERS):
        return "student"
    return current


def filter_student_chunks(chunks: list[dict[str, Any]], declared_role: str) -> tuple[list[dict[str, Any]], int]:
    """Apply declared role and fail closed for mixed packages.

    A teacher-only document produces no student chunks.  A mixed package is
    split at deterministic section boundaries; private chunks are never sent
    to the embedding model.
    """
    if declared_role not in DOCUMENT_ROLES:
        raise ValueError("unsupported_document_role")
    if declared_role == "teacher_solution":
        return [], len(chunks)

    visible: list[dict[str, Any]] = []
    excluded = 0
    visibility = "student"
    for raw in chunks:
        item = dict(raw)
        if declared_role == "mixed_assignment_package":
            visibility = section_visibility(str(item.get("section_title") or ""), visibility)
        if visibility == "teacher":
            excluded += 1
            continue
        item["content_role"] = (
            "student_rubric" if declared_role == "student_rubric" else
            "student_assignment_brief" if declared_role in {"student_assignment_brief", "mixed_assignment_package"} else
            "learning_material"
        )
        item["student_visible"] = True
        visible.append(item)
    return visible, excluded


def public_markdown(chunks: list[dict[str, Any]], title: str) -> bytes:
    """Build a citation-friendly student derivative without answer content."""
    lines = [f"# {title}", ""]
    previous = ""
    for chunk in chunks:
        section = str(chunk.get("section_title") or "Nội dung").strip()
        if section and section != previous:
            lines.extend((f"## {section}", ""))
            previous = section
        content = str(chunk.get("content") or "").strip()
        if content:
            lines.extend((content, ""))
    return "\n".join(lines).encode("utf-8")
