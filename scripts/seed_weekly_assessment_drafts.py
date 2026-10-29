"""Create private Assessment drafts for the four-course 12/10 and 19/10 demo weeks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.course_source.assessment_blueprint_seed import seed_assessment_blueprints  # noqa: E402
from src.course_source.db import SessionLocal  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write missing private quiz anchors. Without this flag the command is a dry run.",
    )
    args = parser.parse_args()
    with SessionLocal() as db:
        report = seed_assessment_blueprints(db, apply=args.apply)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
