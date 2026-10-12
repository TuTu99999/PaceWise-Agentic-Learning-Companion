"""Load the eight-course PDF catalog into the shared PaceWise course store."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import get_settings  # noqa: E402
from src.services.demo_course_materials import (  # noqa: E402
    load_shared_catalog,
    validate_catalog,
    validate_exercise_catalog,
)


def main() -> int:
    # Windows may inherit a legacy console code page even though the report is
    # UTF-8. Keep Vietnamese titles printable without turning a successful,
    # already-committed load into a false process failure.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--material-root", type=Path, default=ROOT / "outputs" / "course_materials")
    parser.add_argument("--report", type=Path, default=ROOT / "outputs" / "course-material-load-report.json")
    parser.add_argument("--allow-missing-courses", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    errors = [*validate_catalog(args.material_root), *validate_exercise_catalog(args.material_root)]
    if args.validate_only:
        result = {"valid": not errors, "errors": errors}
    elif errors:
        result = {"valid": False, "errors": errors}
    else:
        result = load_shared_catalog(
            args.material_root,
            Path(settings.course_upload_dir),
            settings.institution_id,
            strict_courses=not args.allow_missing_courses,
        )
        result["valid"] = True
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
