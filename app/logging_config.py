"""
app/logging_config.py

Structured JSON logging setup for the Flask DevOps platform.

Every log line is emitted as a single JSON object to stdout (US-5.1).
The JSON record always contains ``timestamp`` (ISO 8601), ``level``,
``message``, and ``path`` keys (US-5.2).  Within a Flask request context,
``RequestContextFilter`` overwrites ``path`` with the actual request path;
outside a request context it stays as ``""`` so the filter never raises
(US-5.3).
"""

from __future__ import annotations

import datetime
import logging
import sys
from logging import LogRecord

from flask import has_request_context, request
from pythonjsonlogger.jsonlogger import JsonFormatter


# ---------------------------------------------------------------------------
# LogRecord factory — pre-populates ``path`` so it is always a string
# ---------------------------------------------------------------------------

_original_factory = logging.getLogRecordFactory()


def _record_factory(*args, **kwargs) -> LogRecord:
    """Create a ``LogRecord`` with ``path`` pre-set to an empty string.

    This ensures ``record.path`` is always a ``str`` before
    :class:`RequestContextFilter` (or the formatter) touches it, preventing
    ``None`` from leaking into JSON output.
    """
    record = _original_factory(*args, **kwargs)
    record.path = ""  # type: ignore[attr-defined]
    return record


# ---------------------------------------------------------------------------
# Request-context filter
# ---------------------------------------------------------------------------

class RequestContextFilter(logging.Filter):
    """Logging filter that injects ``record.path`` from the active Flask request.

    Behaviour
    ---------
    - Inside a Flask request context : ``record.path = flask.request.path``
    - Outside a Flask request context: ``record.path = ""``  (default from factory)
    - Never raises regardless of context state.
    """

    def filter(self, record: LogRecord) -> bool:  # noqa: A003
        try:
            record.path = request.path if has_request_context() else ""  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover — defensive, should never fire
            record.path = ""  # type: ignore[attr-defined]
        return True


# ---------------------------------------------------------------------------
# JSON formatter — renames ``asctime``→``timestamp`` and ``levelname``→``level``
# ---------------------------------------------------------------------------

class _JsonFormatter(JsonFormatter):
    """JsonFormatter subclass that renames keys to the spec's required names.

    ``python-json-logger`` uses ``asctime`` and ``levelname`` by default.
    This subclass renames them in :py:meth:`add_fields` so the emitted JSON
    always contains ``timestamp``, ``level``, and ``message`` as required by
    US-5.2.
    """

    def add_fields(
        self,
        log_record: dict,
        record: LogRecord,
        message_dict: dict,
    ) -> None:
        super().add_fields(log_record, record, message_dict)

        # Rename asctime → timestamp
        if "asctime" in log_record:
            log_record["timestamp"] = log_record.pop("asctime")

        # Rename levelname → level
        if "levelname" in log_record:
            log_record["level"] = log_record.pop("levelname")

        # Guarantee timestamp is always present
        if "timestamp" not in log_record:
            log_record["timestamp"] = (
                datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S") + "Z"
            )

        # Guarantee level is always present
        if "level" not in log_record:
            log_record["level"] = record.levelname


# ---------------------------------------------------------------------------
# Public setup function
# ---------------------------------------------------------------------------

def setup_logging(log_level: str) -> None:
    """Configure the root logger for structured JSON output.

    Steps performed
    ---------------
    1. Install a custom ``LogRecord`` factory that pre-populates ``path = ""``.
    2. Create a :class:`logging.StreamHandler` writing to ``stdout``.
    3. Attach a :class:`_JsonFormatter` that emits ``timestamp``, ``level``,
       ``message``, and ``path`` keys.
    4. Attach :class:`RequestContextFilter` to the root logger so every record
       carries the Flask request path (or ``""`` outside a request).
    5. Set the root logger's level from *log_level*.

    Parameters
    ----------
    log_level:
        A Python logging level string — ``"DEBUG"``, ``"INFO"``,
        ``"WARNING"``, ``"ERROR"``, or ``"CRITICAL"``.
    """
    # Install factory so all records get path="" by default
    logging.setLogRecordFactory(_record_factory)

    root_logger = logging.getLogger()

    # Clear existing handlers (makes setup_logging idempotent)
    root_logger.handlers.clear()
    root_logger.filters.clear()

    # JSON stream handler → stdout
    handler = logging.StreamHandler(sys.stdout)
    formatter = _JsonFormatter(
        # Format string declares which LogRecord attributes to include.
        # %(asctime)s   → renamed to "timestamp" in add_fields
        # %(levelname)s → renamed to "level"     in add_fields
        # %(message)s   → kept as "message"
        # %(path)s      → set by RequestContextFilter (default "" from factory)
        fmt="%(asctime)s %(levelname)s %(message)s %(path)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Inject Flask request path into every log record
    root_logger.addFilter(RequestContextFilter())

    # Apply caller-specified level
    root_logger.setLevel(log_level.upper())
