from __future__ import annotations

import json
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
REPOSITORY = WORKSPACE
sys.path.insert(0, str(REPOSITORY))

from src.api.routes import _assignment_parts_from_section  # noqa: E402
from src.services.demo_course_materials import _exercise_sections, matching_exercise_sections  # noqa: E402
from src.services.plan_intelligence import assignment_structure, build_template_milestones  # noqa: E402


def main() -> None:
    files = sorted((WORKSPACE / "outputs" / "course_materials").glob("*/exercises/by_chapter/*.docx"))
    if len(files) != 40:
        raise AssertionError(f"Expected 40 Word files, found {len(files)}")

    report = []
    for path in files:
        sections = _exercise_sections(path)
        if len(sections) != 1:
            raise AssertionError(f"{path.name}: expected one numbered section, found {len(sections)}")
        section = sections[0]
        chapter_label = f"Chương {section['number']} {section['title']}"
        matched = matching_exercise_sections(chapter_label, sections)
        if not matched or matched[0]["number"] != section["number"]:
            raise AssertionError(f"{path.name}: chapter label did not match its section")

        source_ref = f"file:{path.stem}#exercise={section['number']}"
        parts = _assignment_parts_from_section(section, source_ref)
        if len(parts) != 11:
            raise AssertionError(f"{path.name}: expected 11 schedulable parts, found {len(parts)}")
        assignment = {
            "id": f"test:{path.stem}",
            "title": path.stem,
            "chapter": chapter_label,
            "assignment_parts": parts,
        }
        route = assignment_structure(assignment)
        milestones = build_template_milestones(assignment, target_minutes=240)
        durations = [int(item["estimated_minutes"]) for item in milestones]
        if sum(durations) != 240:
            raise AssertionError(f"{path.name}: duration sum is {sum(durations)}, expected 240")
        if not all(15 <= value <= 90 for value in durations):
            raise AssertionError(f"{path.name}: invalid milestone duration {durations}")
        if len(set(durations)) < 2:
            raise AssertionError(f"{path.name}: duration allocation is still uniform {durations}")
        covered = {part_id for item in milestones for part_id in item.get("assignment_part_ids", [])}
        expected = {item["partId"] for item in parts}
        if covered != expected:
            raise AssertionError(f"{path.name}: not every assignment part is scheduled")
        report.append(
            {
                "file": str(path.relative_to(WORKSPACE)),
                "course": path.parents[2].name,
                "chapter": section["number"],
                "assignment_parts": len(parts),
                "route": route["route"],
                "milestones": len(milestones),
                "duration_minutes": durations,
                "total_minutes": sum(durations),
            }
        )

    report_path = WORKSPACE / "outputs" / "chapter-assignment-agent-validation.json"
    report_path.write_text(json.dumps({"documents": len(report), "results": report}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "documents": len(report),
        "parts": sum(item["assignment_parts"] for item in report),
        "milestones": sum(item["milestones"] for item in report),
        "all_totals": sorted({item["total_minutes"] for item in report}),
        "routes": sorted({item["route"] for item in report}),
        "report": str(report_path),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
