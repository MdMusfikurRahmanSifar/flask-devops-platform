"""
app/main.py

Flask application factory and route handlers for the DevOps platform.

Usage
-----
Gunicorn entry point::

    gunicorn --bind 0.0.0.0:8080 app.main:app

Factory usage in tests::

    from app.main import create_app
    from app.config import Config
    from prometheus_client import CollectorRegistry

    app = create_app(config=Config(port=8080), registry=CollectorRegistry())

Requirements: US-1, US-2, US-3, US-6
"""

from __future__ import annotations

import logging
import signal
import time
from typing import TYPE_CHECKING

from flask import Flask, g, request, jsonify
import prometheus_client
from prometheus_client import CollectorRegistry

from app.config import Config
from app.logging_config import setup_logging
from app.metrics import record_metrics

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SIGTERM handler
# ---------------------------------------------------------------------------

def register_shutdown_handler() -> None:
    """Install a SIGTERM handler that logs a shutdown message.

    When Gunicorn sends SIGTERM the worker will log
    ``{"message": "shutting down"}`` before the process exits.
    This satisfies US-6.2.
    """

    def _handle_sigterm(signum, frame):  # noqa: ANN001, ANN202
        logger.info("shutting down")

    signal.signal(signal.SIGTERM, _handle_sigterm)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app(
    config: Config | None = None,
    registry: CollectorRegistry | None = None,
) -> Flask:
    """Create and configure a Flask application instance.

    Parameters
    ----------
    config:
        Application configuration.  If ``None``, ``Config.from_env()`` is
        called so that the production entry point reads from env vars.
    registry:
        Prometheus ``CollectorRegistry`` to use.  Defaults to
        ``prometheus_client.REGISTRY`` (the global registry).  Pass a fresh
        ``CollectorRegistry()`` in tests to get isolated counters.

    Returns
    -------
    Flask
        A fully configured Flask application ready to serve requests.
    """
    if config is None:
        config = Config.from_env()

    if registry is None:
        registry = prometheus_client.REGISTRY

    # Set up structured JSON logging before anything else logs.
    setup_logging(config.log_level)

    app = Flask(__name__)

    # Store config and registry on the app so route handlers can access them.
    app.config["APP_CONFIG"] = config
    app.config["METRICS_REGISTRY"] = registry

    # ------------------------------------------------------------------
    # Request lifecycle hooks
    # ------------------------------------------------------------------

    @app.before_request
    def _start_timer() -> None:
        """Record the request start time on flask.g."""
        g.start_time = time.time()

    @app.after_request
    def _record_request_metrics(response):
        """Emit Prometheus metrics and a JSON log line after every request."""
        reg: CollectorRegistry = app.config["METRICS_REGISTRY"]

        duration = time.time() - getattr(g, "start_time", time.time())
        # Use the matched URL rule when available, else the raw path.
        route = request.url_rule.rule if request.url_rule else request.path
        record_metrics(
            method=request.method,
            route=route,
            status_code=response.status_code,
            duration=duration,
            registry=reg,
        )
        logger.info(
            "%s %s %s",
            request.method,
            route,
            response.status_code,
        )
        return response

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @app.route("/")
    def index():  # noqa: ANN202
        """GET /  — service information endpoint (US-1)."""
        cfg: Config = app.config["APP_CONFIG"]
        return jsonify(
            message="Hello from DevOps Task!",
            status="running",
            version=cfg.app_version,
        ), 200

    @app.route("/health")
    def health():  # noqa: ANN202
        """GET /health  — liveness / readiness probe (US-2)."""
        return jsonify(status="ok"), 200

    @app.route("/metrics")
    def metrics_view():  # noqa: ANN202
        """GET /metrics  — Prometheus exposition endpoint (US-3.1)."""
        reg: CollectorRegistry = app.config["METRICS_REGISTRY"]
        data = prometheus_client.exposition.generate_latest(reg)
        return data, 200, {
            "Content-Type": "text/plain; version=0.0.4; charset=utf-8"
        }

    # ------------------------------------------------------------------
    # Graceful shutdown
    # ------------------------------------------------------------------
    register_shutdown_handler()

    return app


# ---------------------------------------------------------------------------
# Production entry point (Gunicorn)
# ---------------------------------------------------------------------------

app: Flask = create_app()