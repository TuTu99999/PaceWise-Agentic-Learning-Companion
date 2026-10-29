"""Measure Luna/Sol Reflect latency with synthetic, de-identified inputs only."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# This benchmark measures only the model-provider path. Keep optional remote
# metadata tracing out of the measurement and never export even synthetic spans.
os.environ["LANGSMITH_ENABLED"] = "false"

from src.agents.workflows.reflect import reflect_node  # noqa: E402


def _state(complex_week: bool) -> dict:
    sessions = [
        {"planned_minutes": 60, "actual_minutes": 82, "completion_percent": 100},
        {"planned_minutes": 60, "actual_minutes": 88, "completion_percent": 100},
        {"planned_minutes": 60, "actual_minutes": 85, "completion_percent": 100},
    ]
    if complex_week:
        sessions[0]["course_code"] = "COURSE_A"
        sessions[1]["course_code"] = "COURSE_B"
        sessions[2]["course_code"] = "COURSE_A"
    return {
        "query": "Dữ liệu tổng hợp giả lập: việc học nhìn chung ổn nhưng thời lượng thường lệch.",
        "progress_metrics": {
            "reflection_scope": "weekly" if complex_week else "activity",
            "session_count": len(sessions) if complex_week else 1,
            "planned_minutes": 180 if complex_week else 60,
            "actual_minutes": 255 if complex_week else 82,
            "sessions": sessions if complex_week else sessions[:1],
            "activity": {"planned_minutes": 60, "actual_minutes": 82} if not complex_week else {},
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()
    report = {}
    for label, complex_week in (("luna", False), ("sol", True)):
        timings = []
        statuses = []
        warnings = []
        for _ in range(max(1, args.repeats)):
            started = time.perf_counter()
            result = reflect_node(_state(complex_week))
            timings.append((time.perf_counter() - started) * 1000)
            draft = result["reflection_draft"]
            statuses.append(draft["model_status"])
            warnings.extend(draft.get("validation_warnings") or [])
        report[label] = {
            "median_ms": round(statistics.median(timings), 2),
            "max_ms": round(max(timings), 2),
            "statuses": statuses,
            "validation_warnings": sorted(set(warnings)),
        }
    report["synthetic_deidentified_input"] = True
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
