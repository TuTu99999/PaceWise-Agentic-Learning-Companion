"""Small dependency-free Prometheus registry for PaceWise runtime signals."""

from __future__ import annotations

import re
from collections import defaultdict
from threading import Lock

_lock = Lock()
_counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
_sums: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
_counts: dict[tuple[str, tuple[tuple[str, str], ...]], int] = defaultdict(int)
_buckets: dict[tuple[str, tuple[tuple[str, str], ...], float], int] = defaultdict(int)
_gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
LATENCY_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, float("inf"))


def _labels(**labels: object) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((key, str(value)) for key, value in labels.items()))


def normalize_path(path: str) -> str:
    """Avoid unbounded metric labels from numeric and UUID resource identifiers."""
    value = re.sub(r"/[0-9]+(?=/|$)", "/:id", path)
    return re.sub(r"/[0-9a-f]{8}-[0-9a-f-]{27,}(?=/|$)", "/:id", value, flags=re.I)


def increment(name: str, amount: float = 1.0, **labels: object) -> None:
    with _lock:
        _counters[(name, _labels(**labels))] += amount


def observe(name: str, value: float, **labels: object) -> None:
    key = (name, _labels(**labels))
    with _lock:
        _sums[key] += value
        _counts[key] += 1
        for upper in LATENCY_BUCKETS:
            if value <= upper:
                _buckets[(name, key[1], upper)] += 1


def gauge_delta(name: str, value: float, **labels: object) -> None:
    with _lock:
        _gauges[(name, _labels(**labels))] += value


def observe_http(method: str, path: str, status: int, duration_seconds: float) -> None:
    labels = {"method": method, "path": normalize_path(path), "status": status}
    increment("pacewise_http_requests_total", **labels)
    observe("pacewise_http_request_duration_seconds", duration_seconds, **labels)


def observe_agent_node(node: str, outcome: str, duration_seconds: float) -> None:
    increment("pacewise_agent_node_runs_total", node=node, outcome=outcome)
    observe("pacewise_agent_node_duration_seconds", duration_seconds, node=node, outcome=outcome)


def observe_rag(stage: str, outcome: str, duration_seconds: float) -> None:
    increment("pacewise_rag_operations_total", stage=stage, outcome=outcome)
    observe("pacewise_rag_operation_duration_seconds", duration_seconds, stage=stage, outcome=outcome)


def _format_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    encoded = ",".join(
        f'{key}="{value.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"' for key, value in labels
    )
    return "{" + encoded + "}"


def render_prometheus() -> str:
    lines = [
        "# PaceWise application metrics",
        "# Values are process-local; use a Prometheus scraper for durable aggregation.",
    ]
    with _lock:
        counters = sorted(_counters.items())
        sums = sorted(_sums.items())
        counts = dict(_counts)
        buckets = dict(_buckets)
        gauges = sorted(_gauges.items())
    for name in sorted({name for (name, _), _value in counters}):
        lines.append(f"# TYPE {name} counter")
    for (name, labels), value in counters:
        lines.append(f"{name}{_format_labels(labels)} {value:g}")
    for name in sorted({name for (name, _), _value in sums}):
        lines.append(f"# TYPE {name} histogram")
    for (name, labels), value in sums:
        for upper in LATENCY_BUCKETS:
            bucket_labels = tuple(sorted((*labels, ("le", "+Inf" if upper == float("inf") else f"{upper:g}"))))
            lines.append(f"{name}_bucket{_format_labels(bucket_labels)} {buckets.get((name, labels, upper), 0)}")
        lines.append(f"{name}_sum{_format_labels(labels)} {value:g}")
        lines.append(f"{name}_count{_format_labels(labels)} {counts[(name, labels)]}")
    for name in sorted({name for (name, _), _value in gauges}):
        lines.append(f"# TYPE {name} gauge")
    for (name, labels), value in gauges:
        lines.append(f"{name}{_format_labels(labels)} {value:g}")
    return "\n".join(lines) + "\n"
