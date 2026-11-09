"""
app/tests/test_config.py

Unit tests for app/config.py — Config.from_env().

Covers:
- US-4.1: all four env vars are read (PORT, LOG_LEVEL, ENV_NAME, APP_VERSION).
- US-4.2: missing env vars fall back to defaults without raising.
- Invalid PORT (non-integer) raises ValueError at startup.

monkeypatch is used throughout so os.environ is never mutated directly.
"""

from __future__ import annotations

import pytest

from app.config import Config


# ---------------------------------------------------------------------------
# Default values (no env vars set)
# ---------------------------------------------------------------------------


class TestConfigDefaults:
    """When no env vars are present, from_env() must return all four defaults."""

    def test_default_port(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PORT", raising=False)
        config = Config.from_env()
        assert config.port == 8080

    def test_default_log_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        config = Config.from_env()
        assert config.log_level == "INFO"

    def test_default_env_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ENV_NAME", raising=False)
        config = Config.from_env()
        assert config.env_name == "local"

    def test_default_app_version(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("APP_VERSION", raising=False)
        config = Config.from_env()
        assert config.app_version == "1.0.0"

    def test_all_defaults_together(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify the full default Config in one shot."""
        for var in ("PORT", "LOG_LEVEL", "ENV_NAME", "APP_VERSION"):
            monkeypatch.delenv(var, raising=False)
        config = Config.from_env()
        assert config == Config(port=8080, log_level="INFO", env_name="local", app_version="1.0.0")


# ---------------------------------------------------------------------------
# Env-var overrides
# ---------------------------------------------------------------------------


class TestConfigOverrides:
    """Each env var, when set, must override its default."""

    def test_port_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PORT", "5000")
        config = Config.from_env()
        assert config.port == 5000

    def test_log_level_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        config = Config.from_env()
        assert config.log_level == "DEBUG"

    def test_env_name_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENV_NAME", "production")
        config = Config.from_env()
        assert config.env_name == "production"

    def test_app_version_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_VERSION", "2.3.4")
        config = Config.from_env()
        assert config.app_version == "2.3.4"

    def test_all_overrides_together(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PORT", "9090")
        monkeypatch.setenv("LOG_LEVEL", "WARNING")
        monkeypatch.setenv("ENV_NAME", "staging")
        monkeypatch.setenv("APP_VERSION", "3.0.0")
        config = Config.from_env()
        assert config == Config(port=9090, log_level="WARNING", env_name="staging", app_version="3.0.0")


# ---------------------------------------------------------------------------
# Invalid PORT — must raise ValueError
# ---------------------------------------------------------------------------


class TestConfigInvalidPort:
    """A non-integer PORT must raise ValueError so misconfiguration is caught early."""

    def test_non_integer_port_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PORT", "not-a-number")
        with pytest.raises(ValueError):
            Config.from_env()

    def test_float_string_port_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PORT", "80.5")
        with pytest.raises(ValueError):
            Config.from_env()

    def test_empty_string_port_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PORT", "")
        with pytest.raises(ValueError):
            Config.from_env()
