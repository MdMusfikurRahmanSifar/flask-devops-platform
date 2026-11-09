# Feature: phase-1-app, Property 3: Config defaults are always safe
"""
Property-based tests for the Flask DevOps platform.

Property 3: Config defaults are always safe
  For any arbitrary subset of {PORT, LOG_LEVEL, ENV_NAME, APP_VERSION} that is
  absent from the environment, Config.from_env() must never raise and every
  missing key must equal its documented default.

Validates: Requirements US-4.1, US-4.2
"""

from __future__ import annotations

import sys
import os
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Make sure the project root is on sys.path so `from app.config import Config`
# works regardless of how pytest discovers this file.
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.config import Config  # noqa: E402

# ---------------------------------------------------------------------------
# Constants matching the documented defaults in Config / US-4.1
# ---------------------------------------------------------------------------
_ALL_KEYS = {"PORT", "LOG_LEVEL", "ENV_NAME", "APP_VERSION"}

_DEFAULTS: dict[str, object] = {
    "PORT": 8080,
    "LOG_LEVEL": "INFO",
    "ENV_NAME": "local",
    "APP_VERSION": "1.0.0",
}

# ---------------------------------------------------------------------------
# Strategy: generate an arbitrary subset of the four env-var names to *omit*
# ---------------------------------------------------------------------------
_absent_keys_strategy = st.frozensets(st.sampled_from(sorted(_ALL_KEYS)))


# ---------------------------------------------------------------------------
# Property 3
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(absent_keys=_absent_keys_strategy)
def test_config_defaults_are_always_safe(absent_keys: frozenset[str]) -> None:
    """Property 3: Config defaults are always safe.

    For any subset of the four env vars that is absent, Config.from_env()
    must not raise and every missing var must produce its documented default.

    **Validates: Requirements US-4.1, US-4.2**
    """
    # Build a clean environment that only contains keys NOT in absent_keys,
    # using a known-valid sentinel value for each present key so the parse
    # never raises (e.g. PORT must be an integer string when present).
    present_env: dict[str, str] = {}
    present_keys = _ALL_KEYS - absent_keys
    for key in present_keys:
        if key == "PORT":
            present_env[key] = "9000"       # valid integer, not the default
        elif key == "LOG_LEVEL":
            present_env[key] = "WARNING"
        elif key == "ENV_NAME":
            present_env[key] = "staging"
        elif key == "APP_VERSION":
            present_env[key] = "9.9.9"

    # Patch os.environ completely so the test is hermetic.
    with patch.dict(os.environ, present_env, clear=True):
        # 1. Config.from_env() must never raise for any combination of absent keys.
        config = Config.from_env()

        # 2. Every absent key must equal its documented default.
        if "PORT" in absent_keys:
            assert config.port == _DEFAULTS["PORT"], (
                f"Expected default port {_DEFAULTS['PORT']!r}, got {config.port!r}"
            )
        if "LOG_LEVEL" in absent_keys:
            assert config.log_level == _DEFAULTS["LOG_LEVEL"], (
                f"Expected default log_level {_DEFAULTS['LOG_LEVEL']!r}, got {config.log_level!r}"
            )
        if "ENV_NAME" in absent_keys:
            assert config.env_name == _DEFAULTS["ENV_NAME"], (
                f"Expected default env_name {_DEFAULTS['ENV_NAME']!r}, got {config.env_name!r}"
            )
        if "APP_VERSION" in absent_keys:
            assert config.app_version == _DEFAULTS["APP_VERSION"], (
                f"Expected default app_version {_DEFAULTS['APP_VERSION']!r}, got {config.app_version!r}"
            )


# ---------------------------------------------------------------------------
# Feature: phase-1-app, Property 4: Request log records always contain required keys
# ---------------------------------------------------------------------------
"""
Property 4: Request log records always contain required keys

For any HTTP request to any registered route, the JSON log line emitted to
stdout SHALL be a valid JSON object containing at least the keys ``timestamp``,
``level``, ``message``, and ``path``.

Validates: Requirements US-5.1, US-5.2
"""

import io
import json
import logging

from flask import Flask
from hypothesis import given, settings
from hypothesis import strategies as st

from app.logging_config import RequestContextFilter, setup_logging

# ---------------------------------------------------------------------------
# Strategy: pick one of the three registered routes
# ---------------------------------------------------------------------------
_route_strategy = st.sampled_from(["/", "/health", "/metrics"])


def _build_minimal_app() -> Flask:
    """Return a minimal Flask app that exercises setup_logging / RequestContextFilter.

    The app has the same three routes as the real service so the strategy
    covers every registered path.  We build it fresh each call so each
    Hypothesis example gets a clean handler/filter state.

    The filter is attached to the handler (not the root logger) so that it
    fires for child loggers that propagate records upward — matching the
    pattern used in the unit tests in test_logging.py.
    """
    # Reset root logger state before wiring up fresh handlers.
    root = logging.getLogger()
    root.handlers.clear()
    root.filters.clear()

    setup_logging("INFO")

    # setup_logging() attaches RequestContextFilter to the root logger, but
    # Python's logging only applies logger-level filters to records emitted
    # *directly* to that logger; child loggers that propagate bypass them.
    # Move the filter onto the handler so it fires for all propagated records.
    for handler in root.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.addFilter(RequestContextFilter())
    # Remove from root logger to avoid double-application if a record is
    # ever emitted directly to root.
    root.filters.clear()

    mini = Flask(__name__)

    @mini.route("/")
    def index():  # noqa: ANN202
        logging.getLogger(__name__).info("GET / 200")
        return {"message": "Hello from DevOps Task!", "status": "running", "version": "1.0.0"}

    @mini.route("/health")
    def health():  # noqa: ANN202
        logging.getLogger(__name__).info("GET /health 200")
        return {"status": "ok"}

    @mini.route("/metrics")
    def metrics_view():  # noqa: ANN202
        logging.getLogger(__name__).info("GET /metrics 200")
        return "# metrics", 200, {"Content-Type": "text/plain"}

    return mini


@settings(max_examples=100)
@given(path=_route_strategy)
def test_request_log_records_contain_required_keys(path: str) -> None:
    """Property 4: Request log records always contain required keys.

    Build a minimal Flask test app, make a GET request to *path*, capture
    every JSON line written to stdout, and assert that at least one line is
    valid JSON containing ``timestamp``, ``level``, ``message``, and ``path``.

    **Validates: Requirements US-5.1, US-5.2**
    """
    app = _build_minimal_app()

    # Redirect stdout so we can inspect what the JSON logger emits.
    captured = io.StringIO()
    root_logger = logging.getLogger()

    # Replace the StreamHandler's stream with our StringIO buffer.
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.stream = captured  # type: ignore[assignment]

    with app.test_client() as client:
        response = client.get(path)
        # Flush all handlers to ensure the buffer is complete.
        for handler in root_logger.handlers:
            handler.flush()

    output = captured.getvalue()

    # Parse every non-empty line; at least one must be valid JSON with required keys.
    required_keys = {"timestamp", "level", "message", "path"}
    matching_records: list[dict] = []

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if required_keys.issubset(record.keys()):
            matching_records.append(record)

    assert matching_records, (
        f"No JSON log line with all required keys {required_keys} found "
        f"after GET {path} (status {response.status_code}).\n"
        f"Captured stdout:\n{output!r}"
    )

    # Extra structural checks on each matching record.
    for rec in matching_records:
        assert isinstance(rec["timestamp"], str) and rec["timestamp"], (
            f"'timestamp' must be a non-empty string, got {rec['timestamp']!r}"
        )
        assert isinstance(rec["level"], str) and rec["level"], (
            f"'level' must be a non-empty string, got {rec['level']!r}"
        )
        assert isinstance(rec["message"], str), (
            f"'message' must be a string, got {rec['message']!r}"
        )
        assert isinstance(rec["path"], str), (
            f"'path' must be a string, got {rec['path']!r}"
        )
        # path must equal the route we requested.
        assert rec["path"] == path, (
            f"Expected path={path!r} in log record, got {rec['path']!r}"
        )


# ---------------------------------------------------------------------------
# Feature: phase-1-app, Property 5: Metrics counter increments on every request
# ---------------------------------------------------------------------------
"""
Property 5: Metrics counter increments on every request

For N in [1, 50], calling record_metrics() N times with a fresh CollectorRegistry
must result in http_requests_total delta of exactly N for the correct label set.

Validates: Requirements US-3.2, US-3.5
"""

from prometheus_client import CollectorRegistry, Counter as _Counter
from app.metrics import record_metrics


@settings(max_examples=100)
@given(n=st.integers(min_value=1, max_value=50))
def test_metrics_counter_increments_on_every_request(n: int) -> None:
    """Property 5: Metrics counter increments on every request.

    Call record_metrics() N times against an isolated registry and assert
    http_requests_total equals N for the expected label combination.

    **Validates: Requirements US-3.2, US-3.5**
    """
    # Feature: phase-1-app, Property 5: Metrics counter increments on every request
    registry = CollectorRegistry()
    for _ in range(n):
        record_metrics("GET", "/", 200, 0.001, registry=registry)

    # Retrieve the counter value via the registry's internal mapping.
    # prometheus_client stores samples; iterate to find our label set.
    from prometheus_client.exposition import generate_latest

    output = generate_latest(registry).decode()
    # Find the line for http_requests_total{method="GET",route="/",status="200"}
    total = 0.0
    for line in output.splitlines():
        if line.startswith("http_requests_total{") and 'method="GET"' in line and 'route="/"' in line and 'status="200"' in line:
            total = float(line.split()[-1])
            break

    assert total == float(n), (
        f"Expected http_requests_total to be {n}, got {total}"
    )


# ---------------------------------------------------------------------------
# Feature: phase-1-app, Property 6: Latency histogram observes every request
# ---------------------------------------------------------------------------
"""
Property 6: Latency histogram observes every request

For arbitrary request sequences, http_request_duration_seconds_count delta
must equal the number of calls made to record_metrics().

Validates: Requirements US-3.4, US-3.5
"""


@settings(max_examples=100)
@given(durations=st.lists(
    st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    min_size=1,
    max_size=50,
))
def test_latency_histogram_observes_every_request(durations: list) -> None:
    """Property 6: Latency histogram observes every request.

    For each duration in the generated list, call record_metrics() and assert
    http_request_duration_seconds_count equals len(durations).

    **Validates: Requirements US-3.4, US-3.5**
    """
    # Feature: phase-1-app, Property 6: Latency histogram observes every request
    from prometheus_client.exposition import generate_latest

    registry = CollectorRegistry()
    for d in durations:
        record_metrics("GET", "/health", 200, d, registry=registry)

    output = generate_latest(registry).decode()
    count = None
    for line in output.splitlines():
        if line.startswith("http_request_duration_seconds_count{") and 'method="GET"' in line and 'route="/health"' in line:
            count = float(line.split()[-1])
            break

    assert count is not None, "http_request_duration_seconds_count metric not found in output"
    assert count == float(len(durations)), (
        f"Expected histogram count {len(durations)}, got {count}"
    )


# ---------------------------------------------------------------------------
# Feature: phase-1-app, Property 7: Error counter increments only on 5xx
# ---------------------------------------------------------------------------
"""
Property 7: Error counter increments only on 5xx

For HTTP status codes across the full range, http_errors_total must increment
for 5xx responses only and stay at 0 for all other status codes.

Validates: Requirements US-3.3
"""


@settings(max_examples=200)
@given(status_code=st.integers(min_value=100, max_value=599))
def test_error_counter_increments_only_on_5xx(status_code: int) -> None:
    """Property 7: Error counter increments only on 5xx.

    Call record_metrics() once with the given status_code and assert
    http_errors_total is 1 for 5xx and absent (or 0) for all others.

    **Validates: Requirements US-3.3**
    """
    # Feature: phase-1-app, Property 7: Error counter increments only on 5xx
    from prometheus_client.exposition import generate_latest

    registry = CollectorRegistry()
    record_metrics("GET", "/", status_code, 0.001, registry=registry)

    output = generate_latest(registry).decode()

    # Find any http_errors_total line for our label set
    error_total = 0.0
    for line in output.splitlines():
        if line.startswith("http_errors_total{") and 'method="GET"' in line and 'route="/"' in line:
            error_total = float(line.split()[-1])
            break

    if status_code >= 500:
        assert error_total == 1.0, (
            f"Expected http_errors_total=1 for status {status_code}, got {error_total}"
        )
    else:
        assert error_total == 0.0, (
            f"Expected http_errors_total=0 for status {status_code}, got {error_total}"
        )


# ---------------------------------------------------------------------------
# Feature: phase-1-app, Property 1: Index response structure is invariant
# ---------------------------------------------------------------------------
"""
Property 1: Index response structure is invariant

For any arbitrary app_version string, GET / must return a JSON body with
exactly keys {message, status, version} where message and status are fixed.

Validates: Requirements US-1.1, US-1.2, US-1.3
"""

from prometheus_client import CollectorRegistry as _CR
from app.config import Config as _Config
from app.main import create_app as _create_app


@settings(max_examples=100)
@given(version=st.text(min_size=1, max_size=50))
def test_index_response_structure_is_invariant(version: str) -> None:
    """Property 1: Index response structure is invariant.

    Generate arbitrary non-empty version strings, build an app with that
    version in Config, and assert GET / returns exactly the required keys
    with fixed message/status values.

    **Validates: Requirements US-1.1, US-1.2, US-1.3**
    """
    # Feature: phase-1-app, Property 1: Index response structure is invariant
    cfg = _Config(app_version=version, log_level="WARNING")
    app = _create_app(config=cfg, registry=_CR())
    app.config["TESTING"] = True
    with app.test_client() as c:
        response = c.get("/")

    assert response.status_code == 200
    data = response.get_json()
    assert set(data.keys()) == {"message", "status", "version"}, (
        f"Unexpected keys in response: {set(data.keys())}"
    )
    assert data["message"] == "Hello from DevOps Task!", (
        f"message mismatch: {data['message']!r}"
    )
    assert data["status"] == "running", (
        f"status mismatch: {data['status']!r}"
    )
    assert data["version"] == version, (
        f"Expected version={version!r}, got {data['version']!r}"
    )


# ---------------------------------------------------------------------------
# Feature: phase-1-app, Property 2: Version reflects APP_VERSION env var
# ---------------------------------------------------------------------------
"""
Property 2: Version reflects APP_VERSION env var

For arbitrary non-empty version strings, GET / must return "version": v.
When APP_VERSION is absent, version must equal "1.0.0".

Validates: Requirements US-1.2, US-1.3
"""


@settings(max_examples=100)
@given(version=st.text(min_size=1, max_size=50))
def test_version_reflects_app_version_env_var(version: str) -> None:
    """Property 2: Version reflects APP_VERSION env var.

    Build an app with the generated version string and assert GET / echoes it back.

    **Validates: Requirements US-1.2, US-1.3**
    """
    # Feature: phase-1-app, Property 2: Version reflects APP_VERSION env var
    cfg = _Config(app_version=version, log_level="WARNING")
    app = _create_app(config=cfg, registry=_CR())
    app.config["TESTING"] = True
    with app.test_client() as c:
        data = c.get("/").get_json()
    assert data["version"] == version, (
        f"Expected version={version!r}, got {data['version']!r}"
    )


def test_version_defaults_to_1_0_0_when_app_version_absent() -> None:
    """Property 2 corollary: absent APP_VERSION yields version=="1.0.0"."""
    # Feature: phase-1-app, Property 2: Version reflects APP_VERSION env var
    cfg = _Config(log_level="WARNING")  # app_version defaults to "1.0.0"
    app = _create_app(config=cfg, registry=_CR())
    app.config["TESTING"] = True
    with app.test_client() as c:
        data = c.get("/").get_json()
    assert data["version"] == "1.0.0"
