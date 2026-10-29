"""Run the 100 labeled questions through the real scoped PaceWise RAG path."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import select

from src.agents.workflows.qa import qa_node
from src.config import get_settings
from src.course_source.db import SessionLocal
from src.course_source.models import Course, Enrollment
from src.services.lms_client import LMSClient
from src.services.lms_files import authorized_files, file_version


def _load(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != 100:
        raise ValueError(f"Expected exactly 100 labeled questions, received {len(rows)}")
    return rows


async def _course_states(course_codes: set[str]) -> dict[str, dict]:
    settings = get_settings()
    states = {}
    with SessionLocal() as db:
        courses = {
            row.code: row
            for row in db.scalars(select(Course).where(Course.code.in_(course_codes), Course.published.is_(True))).all()
        }
        if set(courses) != course_codes:
            raise RuntimeError(f"Missing published courses: {sorted(course_codes - set(courses))}")
        enrollments = {}
        for code, course in courses.items():
            enrollment = db.scalar(
                select(Enrollment)
                .where(Enrollment.course_id == course.id, Enrollment.role == "student")
                .order_by(Enrollment.id)
            )
            if enrollment is None:
                raise RuntimeError(f"No student enrollment available for {code}")
            enrollments[code] = enrollment
    client = LMSClient(settings)
    for code, course in courses.items():
        enrollment = enrollments[code]
        files = await authorized_files(client, course.id, enrollment.user_id)
        if not files:
            raise RuntimeError(f"No authorized files available for {code}")
        states[code] = {
            "institution_id": settings.institution_id,
            "student_id": str(enrollment.user_id),
            "course_id": str(course.id),
            "course_code": code,
            "authorized_file_versions": {f"file:{item['id']}": file_version(item) for item in files},
            "allowed_resource_ids": None,
            "learning_resources": [],
        }
    return states


async def run(questions: list[dict], output: Path, report_path: Path, *, limit: int | None = None) -> None:
    states = await _course_states({row["course_code"] for row in questions})
    selected = questions[:limit] if limit else questions
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("", encoding="utf-8")
    cases = []
    for index, source in enumerate(selected, 1):
        started = time.perf_counter()
        result = await asyncio.to_thread(qa_node, {**states[source["course_code"]], "query": source["user_input"]})
        passages = result.get("retrieved_passages") or []
        contexts = [str(item.get("content") or "").strip() for item in passages if str(item.get("content") or "").strip()]
        citation = (result.get("output") or {}).get("citation_validation") or {}
        row = {
            "case_id": source["case_id"],
            "course_code": source["course_code"],
            "topic": source["topic"],
            "level": source["level"],
            "user_input": source["user_input"],
            "response": str(result.get("response") or "").strip() or "[NO_RESPONSE]",
            "retrieved_contexts": contexts or ["[NO_CONTEXT_RETRIEVED]"],
            "reference": source["reference"],
        }
        with output.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        case = {
            "sample": index,
            "case_id": source["case_id"],
            "course_code": source["course_code"],
            "grounded": bool(contexts and result.get("source_refs")),
            "citation_valid": bool(citation.get("valid")),
            "retrieved_context_count": len(contexts),
            "mode": result.get("mode") or result.get("analysis"),
            "latency_seconds": round(time.perf_counter() - started, 3),
        }
        cases.append(case)
        print(json.dumps(case, ensure_ascii=False), flush=True)
    by_course = defaultdict(list)
    for case in cases:
        by_course[case["course_code"]].append(case)
    report = {
        "mode": "live_scoped_four_course_rag",
        "sample_count": len(cases),
        "course_counts": Counter(case["course_code"] for case in cases),
        "grounded_count": sum(case["grounded"] for case in cases),
        "citation_valid_count": sum(case["citation_valid"] for case in cases),
        "average_latency_seconds": round(sum(case["latency_seconds"] for case in cases) / len(cases), 3),
        "by_course": {
            code: {
                "count": len(rows),
                "grounded": sum(row["grounded"] for row in rows),
                "citation_valid": sum(row["citation_valid"] for row in rows),
                "average_latency_seconds": round(sum(row["latency_seconds"] for row in rows) / len(rows), 3),
            }
            for code, rows in sorted(by_course.items())
        },
        "cases": cases,
        "limitations": [
            "RAGAS judge scoring is executed separately from this live retrieval run.",
            "A missing retrieval is retained as [NO_CONTEXT_RETRIEVED] and is not dropped from the 100-sample set.",
        ],
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("questions", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    asyncio.run(run(_load(args.questions), args.output, args.report, limit=args.limit))


if __name__ == "__main__":
    main()
