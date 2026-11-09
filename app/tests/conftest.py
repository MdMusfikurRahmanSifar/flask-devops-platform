"""
app/tests/conftest.py

Shared pytest fixtures for the Flask DevOps platform test suite.

Fixtures
--------
test_config
    A Config instance with known test values.  No os.environ reads.
isolated_registry
    A fresh CollectorRegistry per test so metrics never leak between tests.
client
    A Flask test client built from create_app(config, registry).

Requirements: US-7.1, US-7.3
"""

from __future__ import annotations

import pytest
from prometheus_client import CollectorRegistry

from app.config import Config
from app.main import create_app


@pytest.fixture()
def test_config() -> Config:
    """Return a Config with known test values (no os.environ reads)."""
    return Config(
        port=8080,
        log_level="WARNING",   # suppress INFO noise during tests
        env_name="test",
        app_version="1.0.0",
    )


@pytest.fixture()
def isolated_registry() -> CollectorRegistry:
    """Return a fresh CollectorRegistry so metrics do not leak between tests."""
    return CollectorRegistry()


@pytest.fixture()
def client(test_config: Config, isolated_registry: CollectorRegistry):
    """Return a Flask test client backed by an isolated app instance."""
    application = create_app(config=test_config, registry=isolated_registry)
    application.config["TESTING"] = True
    with application.test_client() as c:
        yield c