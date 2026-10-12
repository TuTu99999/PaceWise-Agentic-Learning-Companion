import re

from src.observability import gauge_delta, increment, observe, render_prometheus


def test_prometheus_types_are_valid_and_declared_once():
    increment("test_format_requests_total", route="/one")
    increment("test_format_requests_total", route="/two")
    gauge_delta("test_format_active", 1)
    observe("test_format_seconds", 0.02, task="qa")
    observe("test_format_seconds", 0.2, task="qa")
    rendered = render_prometheus()
    declarations = [line for line in rendered.splitlines() if line.startswith("# TYPE")]
    assert all(
        re.fullmatch(r"# TYPE [a-zA-Z_:][a-zA-Z0-9_:]* (counter|histogram|gauge)", line) for line in declarations
    )
    assert len(declarations) == len(set(declarations))
    assert "# TYPE test_format_requests_total counter" in declarations
    assert 'test_format_seconds_bucket{le="0.05",task="qa"} 1' in rendered
    assert 'test_format_seconds_bucket{le="0.25",task="qa"} 2' in rendered
    assert 'test_format_seconds_bucket{le="+Inf",task="qa"} 2' in rendered
