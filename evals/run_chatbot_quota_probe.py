"""Synthetic quota traffic in an owned disposable PostgreSQL schema, no LLM calls."""

import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from starlette.requests import Request

from src.agents.telemetry import ModelUsage
from src.config import get_settings
from src.db import engine
from src.persistence_models import AiUsageBucket, AiUsageReservation
from src.services.ai_rate_limit import finalize_ai_request, reserve_ai_request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert engine.dialect.name == "postgresql"
    schema = "chatbot_quota_eval_" + uuid4().hex
    assert re.fullmatch(r"chatbot_quota_eval_[a-f0-9]{32}", schema)
    # This name is generated here, never accepted from a CLI/user/database row.
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    test_engine = engine.execution_options(schema_translate_map={None: schema})
    report = {"synthetic_requests": 1000, "client_workers": 32, "real_llm_calls": 0, "active": 0, "peak": 0}
    lock = Lock()
    settings = get_settings().model_copy(
        update={
            "ai_rate_limit_enabled": True,
            "ai_ip_requests_per_minute": 10000,
            "ai_burst_requests": 1000,
            "ai_requests_per_minute": 10000,
            "ai_requests_per_hour": 100000,
            "ai_daily_token_limit_per_user": 100000,
            "ai_max_concurrent_global": 10,
            "ai_max_concurrent_per_user": 1,
            "ai_daily_budget_usd": 0,
            "ai_institution_daily_budget_usd": 0,
        }
    )
    try:
        AiUsageBucket.__table__.create(test_engine)
        AiUsageReservation.__table__.create(test_engine)

        def attempt(index):
            request = Request(
                {"type": "http", "method": "POST", "path": "/api/v1/chat", "headers": [], "client": ("127.0.0.1", 1234)}
            )
            with Session(test_engine, expire_on_commit=False) as db:
                try:
                    reservation = reserve_ai_request(
                        db,
                        request,
                        SimpleNamespace(user_id=1000000 + index),
                        settings,
                        workflow="qa",
                        payload_context={},
                    )
                except HTTPException as exc:
                    return exc.status_code
                with lock:
                    report["active"] += 1
                    report["peak"] = max(report["peak"], report["active"])
                try:
                    time.sleep(0.02)  # Stand-in provider latency, not a real model.
                finally:
                    with lock:
                        report["active"] -= 1
                    finalize_ai_request(
                        db, reservation, ModelUsage(input_tokens=10, output_tokens=10), settings, succeeded=True
                    )
                return 200

        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=32) as executor:
            outcomes = list(executor.map(attempt, range(1000)))
        with Session(test_engine) as db:
            counters = list(db.scalars(select(AiUsageBucket).where(AiUsageBucket.limit_type == "concurrent")))
            report["slots_released"] = all(row.used == 0 for row in counters)
            report["nonnegative_counters"] = all(row.used >= 0 for row in db.scalars(select(AiUsageBucket)))
        report.update(
            accepted=outcomes.count(200),
            capacity_rejected=outcomes.count(503),
            rate_rejected=outcomes.count(429),
            elapsed_seconds=round(time.perf_counter() - started, 3),
        )
        report["passed"] = (
            report["peak"] <= 10
            and report["slots_released"]
            and report["nonnegative_counters"]
            and report["active"] == 0
        )
        report["limitations"] = [
            "1000 synthetic quota calls with 32 workers; not 1000 simultaneous real student sessions or a full API load test."
        ]
    finally:
        with engine.begin() as connection:
            tables = set(
                connection.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema=:schema"),
                    {"schema": schema},
                ).scalars()
            )
            assert tables <= {"pacewise_ai_usage_buckets", "pacewise_ai_usage_reservations"}
            # Remove ONLY the generated schema and these two owned test tables.
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        report["temporary_schema_removed"] = True
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
