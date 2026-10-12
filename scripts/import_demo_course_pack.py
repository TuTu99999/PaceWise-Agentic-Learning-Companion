"""Preview or apply a trusted PaceWise demo workbook through the real importer."""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIMULATOR = ROOT / "lms-simulator"
for directory in (ROOT, SIMULATOR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from app.course_management import courses  # noqa: E402
from app.schedule_import import ConfirmInput, PreviewInput, confirm, preview  # noqa: E402

from src.course_source.db import SessionLocal  # noqa: E402
from src.services.teacher_workbook import parse_workbook  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--instructor-id", type=int, default=1)
    parser.add_argument("--apply", action="store_true", help="Confirm the preview transaction.")
    args = parser.parse_args()

    encoded = base64.b64encode(args.workbook.read_bytes()).decode("ascii")
    with SessionLocal() as db:
        owned_courses = courses(args.instructor_id, db)
        rows, parsing_errors, new_courses = parse_workbook(
            encoded,
            owned_courses,
            include_course_definitions=True,
        )
        if parsing_errors:
            result = {"applied": False, "stage": "parse", "errors": parsing_errors}
        else:
            payload = PreviewInput(
                mode="append",
                rows=rows,
                course_ids=sorted({row["course_id"] for row in rows if row["course_id"] > 0}),
                new_courses=new_courses,
            )
            result = preview(payload, args.instructor_id, db)
            if args.apply and not result["errors"]:
                result = confirm(ConfirmInput(ticket=result["ticket"]), args.instructor_id, db)
            result = {
                **result,
                "requestedApply": args.apply,
                "workbook": args.workbook.name,
            }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
