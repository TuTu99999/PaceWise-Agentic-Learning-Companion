"""Micro-benchmark the deterministic half of hybrid Reflect.

This intentionally excludes provider latency.  It measures the code that must
remain fast regardless of whether Luna/Sol succeeds, times out or is busy.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.reflection_policy import (
    recommend_reflection,
    route_reflection,
    validate_hypothesis,
)


def main(iterations: int = 10_000) -> None:
    metrics = {
        "reflection_scope": "weekly",
        "session_count": 3,
        "sessions": [
            {
                "course_code": "DB201",
                "task_id": "DB201:1",
                "planned_minutes": 60,
                "actual_minutes": 85,
                "completion_percent": 100,
            },
            {
                "course_code": "WEB201",
                "task_id": "WEB201:1",
                "planned_minutes": 60,
                "actual_minutes": 90,
                "completion_percent": 100,
            },
            {
                "course_code": "DB201",
                "task_id": "DB201:1",
                "planned_minutes": 60,
                "actual_minutes": 80,
                "completion_percent": 100,
            },
        ],
    }
    raw = {
        "effective": "đã duy trì việc học",
        "difficulty": "thời lượng còn lệch",
        "cause": "estimate_error",
        "confidence": 0.72,
        "recommended_action": "split_task",
        "task_id": "DB201:1",
        "affected_kcs": [],
    }
    timings = []
    route_counts = {"luna": 0, "sol": 0}
    for _ in range(iterations):
        started = time.perf_counter_ns()
        route = route_reflection("weekly", metrics, "Tuần này em học hai môn và thường mất lâu hơn.")
        hypothesis, _warnings = validate_hypothesis(
            raw,
            metrics=metrics,
            trusted_task_ids={"DB201:1", "WEB201:1"},
            trusted_kcs=set(),
        )
        recommend_reflection(
            hypothesis,
            metrics=metrics,
            calibration_count=3,
            calibration_factor=1.25,
            trusted_task_ids={"DB201:1", "WEB201:1"},
        )
        timings.append((time.perf_counter_ns() - started) / 1_000_000)
        route_counts[route["model_tier"]] += 1
    ordered = sorted(timings)
    report = {
        "iterations": iterations,
        "median_ms": round(statistics.median(timings), 4),
        "p95_ms": round(ordered[int(iterations * 0.95) - 1], 4),
        "max_ms": round(max(timings), 4),
        "routes": route_counts,
        "provider_latency_included": False,
    }
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
