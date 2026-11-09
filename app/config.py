"""
app/config.py

Environment-based configuration for the Flask DevOps platform.
All settings are read from environment variables at startup; missing
vars fall back to safe defaults (US-4.1, US-4.2).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """Immutable application configuration.

    Fields
    ------
    port        : TCP port the server listens on (env: PORT, default 8080).
    log_level   : Python logging level string  (env: LOG_LEVEL, default "INFO").
    env_name    : Deployment environment name  (env: ENV_NAME, default "local").
    app_version : Running application version  (env: APP_VERSION, default "1.0.0").
    """

    port: int = 8080
    log_level: str = "INFO"
    env_name: str = "local"
    app_version: str = "1.0.0"

    @classmethod
    def from_env(cls) -> "Config":
        """Build a Config by reading the four supported environment variables.

        Rules
        -----
        - Missing variables are silently replaced with the field's default value.
        - A non-integer value for ``PORT`` raises :class:`ValueError` immediately
          so misconfiguration is caught at startup rather than silently ignored.
        """
        raw_port = os.getenv("PORT")
        if raw_port is not None:
            # Let int() raise ValueError naturally; callers / startup code should
            # surface this to the operator — an invalid PORT is a config error.
            port: int = int(raw_port)
        else:
            port = 8080

        return cls(
            port=port,
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            env_name=os.getenv("ENV_NAME", "local"),
            app_version=os.getenv("APP_VERSION", "1.0.0"),
        )
