"""
app/tests/test_logging.py

Unit tests for app/logging_config.py.

Covers:
- US-5.1: every log line is a valid JSON object emitted to stdout.
- US-5.2: request-scoped log lines include timestamp, level, message, path.
- US-5.3: RequestContextFilter returns empty path outside a request context.
"""

from __future__ import annotations

import io
import json
import logging
import sys
import os

import pytest
from flask import Flask

# Ensure the project root is on sys.path regardless of how pytest is invoked.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.logging_config import RequestContextFilter, _JsonFormatter, setup_logging  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_capturing_logger(name: str = "test_logger") -> tuple[logging.Logger, io.StringIO]:
    """Return a fresh logger + StringIO buffer wired together via a JSON handler.

    The logger is *not* the root logger, so it won't interfere with other tests.
    """
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    formatter = _JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(message)s %(path)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    # Clear handlers/filters from any previous test run that reused this name.
    logger.handlers.clear()
    logger.filters.clear()
    logger.propagate = False
    logger.addHandler(handler)
    logger.addFilter(RequestContextFilter())
    logger.setLevel(logging.DEBUG)
    return logger, buf


# ---------------------------------------------------------------------------
# US-5.1: log output is valid JSON
# ---------------------------------------------------------------------------


class TestLogOutputIsValidJSON:
    """Every log line emitted by the JSON formatter must be parseable as JSON."""

    def test_single_line_is_valid_json(self) -> None:
        logger, buf = _make_capturing_logger("test_json_1")
        logger.info("hello world")
        output = buf.getvalue().strip()
        assert output, "Expected at least one log line"
        # Must not raise
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_multiple_lines_are_each_valid_json(self) -> None:
        logger, buf = _make_capturing_logger("test_json_2")
        logger.info("first message")
        logger.warning("second message")
        logger.error("third message")
        lines = [line for line in buf.getvalue().splitlines() if line.strip()]
        assert len(lines) == 3
        for line in lines:
            parsed = json.loads(line)
            assert isinstance(parsed, dict)

    def test_log_output_is_not_plain_text(self) -> None:
        """US-5.3 forbids plain-text logging — output must be JSON, not raw strings."""
        logger, buf = _make_capturing_logger("test_json_3")
        logger.info("some message")
        output = buf.getvalue().strip()
        # Must start with '{' (JSON object), not a bare string
        assert output.startswith("{"), f"Expected JSON object, got: {output!r}"


# ---------------------------------------------------------------------------
# US-5.2: required keys are present in a request-scoped log line
# ---------------------------------------------------------------------------


class TestRequestScopedLogKeys:
    """Inside a Flask request context the log record must carry timestamp,
    level, message, and path."""

    @pytest.fixture()
    def flask_app(self) -> Flask:
        app = Flask(__name__)
        app.config["TESTING"] = True
        return app

    def test_required_keys_present_in_request_context(self, flask_app: Flask) -> None:
        logger, buf = _make_capturing_logger("test_reqkeys_1")
        with flask_app.test_request_context("/some-path"):
            logger.info("test log inside request")

        line = buf.getvalue().strip()
        assert line, "No log output captured"
        record = json.loads(line)

        assert "timestamp" in record, f"Missing 'timestamp' key; got keys: {list(record)}"
        assert "level" in record, f"Missing 'level' key; got keys: {list(record)}"
        assert "message" in record, f"Missing 'message' key; got keys: {list(record)}"
        assert "path" in record, f"Missing 'path' key; got keys: {list(record)}"

    def test_path_matches_request_path(self, flask_app: Flask) -> None:
        logger, buf = _make_capturing_logger("test_reqkeys_2")
        with flask_app.test_request_context("/api/v1/health"):
            logger.info("path check")

        record = json.loads(buf.getvalue().strip())
        assert record["path"] == "/api/v1/health"

    def test_level_reflects_log_severity(self, flask_app: Flask) -> None:
        logger, buf = _make_capturing_logger("test_reqkeys_3")
        with flask_app.test_request_context("/"):
            logger.warning("watch out")

        record = json.loads(buf.getvalue().strip())
        assert record["level"].upper() == "WARNING"

    def test_message_matches_logged_string(self, flask_app: Flask) -> None:
        logger, buf = _make_capturing_logger("test_reqkeys_4")
        with flask_app.test_request_context("/"):
            logger.info("exact message text")

        record = json.loads(buf.getvalue().strip())
        assert record["message"] == "exact message text"

    def test_timestamp_is_iso8601_format(self, flask_app: Flask) -> None:
        """timestamp must look like YYYY-MM-DDTHH:MM:SS[Z] (ISO 8601)."""
        import re
        logger, buf = _make_capturing_logger("test_reqkeys_5")
        with flask_app.test_request_context("/"):
            logger.info("ts check")

        record = json.loads(buf.getvalue().strip())
        ts = record["timestamp"]
        pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
        assert re.match(pattern, ts), f"timestamp {ts!r} does not match ISO 8601 pattern"


# ---------------------------------------------------------------------------
# US-5.3: RequestContextFilter behaviour outside a request context
# ---------------------------------------------------------------------------


class TestRequestContextFilterOutsideRequest:
    """When no Flask request context is active, RequestContextFilter must set
    path to an empty string and always return True (pass the record through)."""

    def test_path_is_empty_string_outside_request(self) -> None:
        fltr = RequestContextFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="no request here", args=(), exc_info=None,
        )
        result = fltr.filter(record)
        assert result is True, "filter() must return True (pass record through)"
        assert record.path == "", (
            f"Expected empty path outside request context, got {record.path!r}"
        )

    def test_filter_always_returns_true(self) -> None:
        """filter() must never swallow records — it always returns True."""
        fltr = RequestContextFilter()
        for level in (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR):
            record = logging.LogRecord(
                name="test", level=level, pathname="", lineno=0,
                msg="msg", args=(), exc_info=None,
            )
            assert fltr.filter(record) is True

    def test_path_key_present_in_captured_output_outside_request(self) -> None:
        """path key must exist even when no request context is active."""
        logger, buf = _make_capturing_logger("test_nocontext_1")
        logger.info("outside any request")

        record = json.loads(buf.getvalue().strip())
        assert "path" in record, f"'path' key missing outside request context; got: {list(record)}"
        assert record["path"] == "", (
            f"Expected empty path outside request context, got {record['path']!r}"
        )


# ---------------------------------------------------------------------------
# setup_logging integration smoke test
# ---------------------------------------------------------------------------


class TestSetupLoggingIntegration:
    """Verify that setup_logging wires up the root logger correctly."""

    def test_root_logger_emits_valid_json_after_setup(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """After setup_logging(), logging.info() must produce valid JSON on stdout."""
        setup_logging("INFO")
        logging.getLogger().info("integration smoke test")
        captured = capsys.readouterr()
        # Find the JSON line (there may be a trailing newline)
        lines = [l for l in captured.out.splitlines() if l.strip()]
        assert lines, "No output captured from root logger after setup_logging()"
        parsed = json.loads(lines[-1])
        assert "message" in parsed
        assert "level" in parsed
