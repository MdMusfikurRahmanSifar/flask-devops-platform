"""
app/tests/test_index.py

Unit tests for GET /.

Covers:
- US-1.1: response body has exactly keys message, status, version
- US-1.2: message == "Hello from DevOps Task!", status == "running"
- US-1.3: version reflects APP_VERSION / falls back to "1.0.0"
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry

from app.config import Config
from app.main import create_app


class TestIndexEndpoint:
    """Tests for GET /."""

    def test_returns_200(self, client) -> None:
        response = client.get("/")
        assert response.status_code == 200

    def test_content_type_is_json(self, client) -> None:
        response = client.get("/")
        assert response.content_type.startswith("application/json")

    def test_body_has_exactly_three_keys(self, client) -> None:
        data = client.get("/").get_json()
        assert set(data.keys()) == {"message", "status", "version"}

    def test_message_value(self, client) -> None:
        data = client.get("/").get_json()
        assert data["message"] == "Hello from DevOps Task!"

    def test_status_value(self, client) -> None:
        data = client.get("/").get_json()
        assert data["status"] == "running"

    def test_version_default(self, client) -> None:
        """With the default test config (app_version="1.0.0") version must be "1.0.0"."""
        data = client.get("/").get_json()
        assert data["version"] == "1.0.0"

    def test_version_reflects_config(self) -> None:
        """When app_version is set to "2.3.4" in Config, version must be "2.3.4"."""
        cfg = Config(app_version="2.3.4")
        app = create_app(config=cfg, registry=CollectorRegistry())
        app.config["TESTING"] = True
        with app.test_client() as c:
            data = c.get("/").get_json()
        assert data["version"] == "2.3.4"