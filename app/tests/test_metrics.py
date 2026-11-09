"""
app/tests/test_metrics.py

Unit tests for GET /metrics and the Prometheus counters/histogram.

Covers:
- US-3.1: GET /metrics returns 200 with correct Content-Type
- US-3.2: http_requests_total counter incremented by N after N requests
- US-3.3: http_errors_total incremented only for 5xx
- US-3.4/3.5: http_request_duration_seconds_count incremented after each request
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry
from prometheus_client.exposition import generate_latest

from app.config import Config
from app.main import create_app


CONTENT_TYPE_METRICS = "text/plain; version=0.0.4; charset=utf-8"


def _make_client(app_version: str = "1.0.0"):
    """Return (test_client, isolated_registry) for a fresh app."""
    registry = CollectorRegistry()
    cfg = Config(app_version=app_version, log_level="WARNING")
    app = create_app(config=cfg, registry=registry)
    app.config["TESTING"] = True
    return app.test_client(), registry


def _get_metric_value(registry: CollectorRegistry, name: str, labels: dict) -> float:
    """Parse generate_latest output to find a specific metric line's value."""
    output = generate_latest(registry).decode()
    label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    for line in output.splitlines():
        if line.startswith(f"{name}{{") and all(
            f'{k}="{v}"' in line for k, v in labels.items()
        ):
            return float(line.split()[-1])
    return 0.0


class TestMetricsEndpoint:
    """Tests for GET /metrics exposition."""

    def test_returns_200(self, client) -> None:
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_content_type(self, client) -> None:
        response = client.get("/metrics")
        assert response.content_type == CONTENT_TYPE_METRICS

    def test_body_is_non_empty(self, client) -> None:
        # Make one request first so the registry has at least one metric registered.
        client.get("/health")
        response = client.get("/metrics")
        assert len(response.data) > 0


class TestRequestCounter:
    """http_requests_total must increment by N after N requests (US-3.2, US-3.5)."""

    def test_counter_increments_after_requests(self) -> None:
        c, reg = _make_client()
        n = 5
        for _ in range(n):
            c.get("/health")
        value = _get_metric_value(reg, "http_requests_total", {"method": "GET", "route": "/health", "status": "200"})
        assert value == float(n), f"Expected counter={n}, got {value}"

    def test_counter_zero_before_any_request(self) -> None:
        _, reg = _make_client()
        value = _get_metric_value(reg, "http_requests_total", {"method": "GET", "route": "/health", "status": "200"})
        assert value == 0.0


class TestErrorCounter:
    """http_errors_total must increment only on 5xx (US-3.3)."""

    def test_error_counter_not_incremented_on_200(self) -> None:
        c, reg = _make_client()
        c.get("/health")  # 200 OK
        value = _get_metric_value(reg, "http_errors_total", {"method": "GET", "route": "/health"})
        assert value == 0.0, f"Expected 0 errors for 200, got {value}"

    def test_error_counter_not_incremented_on_404(self) -> None:
        c, reg = _make_client()
        c.get("/nonexistent")  # 404
        value = _get_metric_value(reg, "http_errors_total", {"method": "GET", "route": "/nonexistent"})
        assert value == 0.0, f"Expected 0 errors for 404, got {value}"


class TestLatencyHistogram:
    """http_request_duration_seconds_count must increment by 1 per request (US-3.4, US-3.5)."""

    def test_histogram_count_increments(self) -> None:
        c, reg = _make_client()
        c.get("/")
        value = _get_metric_value(reg, "http_request_duration_seconds_count", {"method": "GET", "route": "/"})
        assert value == 1.0, f"Expected histogram count=1, got {value}"

    def test_histogram_count_matches_request_count(self) -> None:
        c, reg = _make_client()
        n = 4
        for _ in range(n):
            c.get("/")
        value = _get_metric_value(reg, "http_request_duration_seconds_count", {"method": "GET", "route": "/"})
        assert value == float(n), f"Expected histogram count={n}, got {value}"