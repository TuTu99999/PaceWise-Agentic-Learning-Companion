"""Verify metadata-only traces by reading them back from LangSmith.

Run inside either container without copying credentials into arguments:
  Get-Content scripts/evaluate_langsmith_connection.py -Raw |
    docker compose exec -T backend python - --service backend

This creates synthetic connectivity spans, not a learner/LLM evaluation.
"""

import argparse
import json
import logging
import sys
import time
import warnings
from pathlib import Path

# Support both a script on disk and stdin execution in /app.
sys.path.insert(0, str(Path.cwd()))

from src.config import get_settings
from src.services import private_tracing


def verify(result, client, runs):
    root = runs[0].id
    by_name = {run.name: run for run in runs}
    privacy_ok = all(not run.inputs and run.outputs == {"outcome": "ok"} and not run.error for run in runs)
    hierarchy_ok = (
        len(runs) == 5
        and set(by_name) == {"coordinator", "plan", "do", "assessment", "reflect"}
        and runs[0].parent_run_id is None
        and all(run.trace_id == root for run in runs)
        and all(by_name[name].parent_run_id == root for name in ("plan", "do", "reflect"))
        and by_name["assessment"].parent_run_id == by_name["do"].id
    )
    project = client.read_project(project_name=result["project"])
    project_ok = all(run.session_id == project.id for run in runs)
    completed = all(run.end_time is not None for run in runs)
    return {
        **result,
        "status": "passed" if privacy_ok and hierarchy_ok and project_ok and completed else "validation_failed",
        "cloud_spans_read": len(runs),
        "span_names": [run.name for run in runs],
        "empty_inputs_and_metadata_only_outputs": privacy_ok,
        "parent_child_relationships": hierarchy_ok,
        "expected_project": project_ok,
        "all_spans_completed": completed,
        "root_run_id": str(root),
    }


def check(service, existing_root=None):
    settings = get_settings()
    result = {
        "service": service,
        "enabled": settings.langsmith_enabled,
        "key_present": bool(settings.langsmith_api_key),
        "project": settings.langsmith_project,
        "synthetic_connectivity_only": True,
    }
    if not result["enabled"] or not result["key_present"]:
        return {**result, "status": "configuration_missing"}

    client = private_tracing._client()
    if existing_root:
        root = client.read_run(existing_root, load_child_runs=True)
        runs = []

        def collect(run):
            runs.append(run)
            for child in run.child_runs or []:
                collect(child)

        collect(root)
        return verify(result, client, runs)

    ids = []
    with private_tracing.trace_span("coordinator") as root:
        ids.append(root)
        with private_tracing.trace_span("plan") as plan:
            ids.append(plan)
        with private_tracing.trace_span("do") as do:
            ids.append(do)
            with private_tracing.trace_span("assessment") as assessment:
                ids.append(assessment)
        with private_tracing.trace_span("reflect") as reflect:
            ids.append(reflect)
    result["root_run_id"] = str(root)

    deadline = time.monotonic() + 30
    while private_tracing._queue.unfinished_tasks and time.monotonic() < deadline:
        time.sleep(0.1)
    if private_tracing._queue.unfinished_tasks:
        return {**result, "status": "delivery_timeout"}

    runs = []
    for run_id in ids:
        # Cloud indexing can lag successful HTTP ingestion. Bounded backoff is
        # preferable to treating an accepted span as a failed connection.
        read_deadline = time.monotonic() + 45
        backoff = 0.5
        while True:
            try:
                run = client.read_run(run_id)
                if run.end_time is not None:
                    runs.append(run)
                    break
            except Exception as exc:
                # Only retry eventual-consistency 404s. Auth/quota failures are
                # not fixed by hammering the provider's read API.
                if type(exc).__name__ != "LangSmithNotFoundError" or time.monotonic() >= read_deadline:
                    return {**result, "status": "readback_failed", "error_type": type(exc).__name__}
            if time.monotonic() >= read_deadline:
                return {**result, "status": "incomplete_span"}
            time.sleep(backoff)
            backoff = min(3, backoff * 1.5)

    return verify(result, client, runs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", choices=("backend", "worker", "local"), default="local")
    parser.add_argument("--root-run-id", help="Read back an existing synthetic smoke trace without creating another.")
    args = parser.parse_args()
    # Never emit SDK exception messages/headers, which can contain credentials.
    logging.disable(logging.CRITICAL)
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    try:
        result = check(args.service, args.root_run_id)
    except Exception as exc:
        result = {"service": args.service, "status": "failed", "error_type": type(exc).__name__}
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
