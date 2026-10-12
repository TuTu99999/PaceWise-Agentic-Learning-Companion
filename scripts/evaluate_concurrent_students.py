"""Small live concurrency check for the PaceWise MVP.

The script signs in three distinct demo students and runs the deterministic
Tracking workflow at the same time. It reports end-to-end latency, errors and
the change in LLM token/cost counters. It is deliberately not a 1,000-user
load test; that belongs to the production-capacity phase.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import statistics
import time
from dataclasses import asdict, dataclass

import httpx

ORIGIN = os.getenv("PACEWISE_ORIGIN", "http://localhost:8000").rstrip("/")
API_URL = f"{ORIGIN}/api/v1"
PASSWORD = os.getenv("PACEWISE_EVAL_PASSWORD", "demo123")
STUDENTS = tuple(
    value.strip()
    for value in os.getenv(
        "PACEWISE_EVAL_STUDENTS",
        "student@canvas.local,minh@canvas.local,linh@canvas.local",
    ).split(",")
    if value.strip()
)[:3]


@dataclass(frozen=True)
class StudentResult:
    email: str
    ok: bool
    latency_ms: float
    workflow: str | None = None
    risk_count: int = 0
    error: str | None = None


def _metric_total(text: str, name: str, *, required_label: str | None = None) -> float:
    pattern = re.compile(rf"^{re.escape(name)}(?:\{{[^}}]*\}})?\s+([0-9.eE+-]+)$")
    return sum(
        float(match.group(1))
        for line in text.splitlines()
        if (required_label is None or required_label in line)
        and (match := pattern.match(line.strip()))
    )


async def _run_student(email: str) -> StudentResult:
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(base_url=API_URL, timeout=90) as client:
            login = await client.post(
                "/auth/lms-login",
                json={"email": email, "password": PASSWORD},
            )
            login.raise_for_status()
            csrf = client.cookies.get("pacewise_csrf")
            if not csrf:
                raise RuntimeError("Login did not issue a CSRF cookie")
            response = await client.post(
                "/chat",
                headers={"X-CSRF-Token": csrf},
                json={
                    "message": "Kiểm tra tiến độ và deadline gần nhất của tôi.",
                    "workflow": "tracking",
                    "context": {"progress_metrics": {}},
                },
            )
            response.raise_for_status()
            payload = response.json()
            return StudentResult(
                email=email,
                ok=True,
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
                workflow=payload.get("workflow"),
                risk_count=len(payload.get("risk_signals") or []),
            )
    except Exception as exc:  # The report must include every failed virtual student.
        return StudentResult(
            email=email,
            ok=False,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            error=str(exc),
        )


async def main() -> None:
    if len(STUDENTS) < 2:
        raise SystemExit("Configure at least two demo students in PACEWISE_EVAL_STUDENTS")
    async with httpx.AsyncClient(base_url=ORIGIN, timeout=10) as client:
        before = (await client.get("/metrics")).text
    results = await asyncio.gather(*(_run_student(email) for email in STUDENTS))
    async with httpx.AsyncClient(base_url=ORIGIN, timeout=10) as client:
        after = (await client.get("/metrics")).text

    latencies = sorted(result.latency_ms for result in results)
    report = {
        "scope": f"{len(results)} concurrent demo students (not a capacity test)",
        "passed": sum(result.ok for result in results),
        "failed": sum(not result.ok for result in results),
        "latency_ms": {
            "median": round(statistics.median(latencies), 1),
            "p95_demo": round(max(latencies), 1),
        },
        "llm_usage_delta": {
            "successful_calls": _metric_total(
                after,
                "pacewise_llm_calls_total",
                required_label='outcome="ok"',
            )
            - _metric_total(
                before,
                "pacewise_llm_calls_total",
                required_label='outcome="ok"',
            ),
            "failed_calls": _metric_total(
                after,
                "pacewise_llm_calls_total",
                required_label='outcome="error"',
            )
            - _metric_total(
                before,
                "pacewise_llm_calls_total",
                required_label='outcome="error"',
            ),
            "tokens": _metric_total(
                after,
                "pacewise_llm_tokens_total",
                required_label='token_type="total"',
            )
            - _metric_total(
                before,
                "pacewise_llm_tokens_total",
                required_label='token_type="total"',
            ),
            "estimated_cost_usd": _metric_total(after, "pacewise_llm_estimated_cost_usd_total")
            - _metric_total(before, "pacewise_llm_estimated_cost_usd_total"),
            "calls_without_usage_metadata": _metric_total(
                after,
                "pacewise_llm_usage_missing_total",
            )
            - _metric_total(before, "pacewise_llm_usage_missing_total"),
        },
        "students": [asdict(result) for result in results],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(1 if report["failed"] else 0)


if __name__ == "__main__":
    asyncio.run(main())
