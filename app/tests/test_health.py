"""
app/tests/test_health.py

Unit tests for GET /health.

Covers:
- US-2.1: returns 200 with {"status": "ok"}
"""

from __future__ import annotations


class TestHealthEndpoint:
    """Tests for GET /health."""

    def test_returns_200(self, client) -> None:
        response = client.get("/health")
        assert response.status_code == 200

    def test_body_is_status_ok(self, client) -> None:
        data = client.get("/health").get_json()
        assert data == {"status": "ok"}

    def test_content_type_is_json(self, client) -> None:
        response = client.get("/health")
        assert response.content_type.startswith("application/json")