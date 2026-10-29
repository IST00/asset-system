"""Read-only, non-sensitive runtime capability status."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import current_app
from sqlalchemy import text

from app.extensions import db


def _configured(*names: str) -> bool:
    return any(bool(os.getenv(name, "").strip()) for name in names)


def _database_label(dialect: str) -> str:
    return {
        "sqlite": "SQLite",
        "mysql": "MySQL",
        "postgresql": "PostgreSQL",
    }.get(dialect, dialect.upper())


def _session_hours(value: object) -> float | None:
    if isinstance(value, timedelta):
        return round(value.total_seconds() / 3600, 1)
    return None


def get_status() -> dict[str, Any]:
    db.session.execute(text("SELECT 1"))
    dialect = db.engine.dialect.name
    profile = str(os.getenv("FLASK_ENV") or "dev").lower()
    formal_feishu = bool(current_app.config.get("FEISHU_INTEGRATION_ENABLED")) and bool(
        current_app.config.get("FEISHU_APP_ID")
        and current_app.config.get("FEISHU_APP_SECRET")
    )
    local_feishu = bool(current_app.debug or current_app.testing)
    file_storage = _configured(
        "FILE_STORAGE_PATH", "FILE_STORAGE_BUCKET", "OBJECT_STORAGE_BUCKET"
    )
    backup = _configured("BACKUP_TARGET", "BACKUP_COMMAND", "BACKUP_STORAGE_PATH")

    if formal_feishu:
        feishu_mode = "FORMAL_CONFIGURED"
    elif local_feishu:
        feishu_mode = "LOCAL_SIMULATION"
    else:
        feishu_mode = "NOT_CONFIGURED"

    return {
        "profile": profile,
        "application": {
            "name": str(current_app.config.get("APP_NAME", "asset-system")),
            "healthy": True,
            "server_time": datetime.now(tz=timezone.utc).isoformat(),
        },
        "database": {
            "connected": True,
            "dialect": dialect,
            "label": _database_label(dialect),
        },
        "feishu": {
            "mode": feishu_mode,
            "formal_configured": formal_feishu,
            "local_simulation_available": local_feishu,
        },
        "file_storage": {
            "configured": file_storage,
            "mode": "CONFIGURED" if file_storage else "NOT_CONFIGURED",
        },
        "backup": {
            "configured": backup,
            "mode": "CONFIGURED" if backup else "NOT_CONFIGURED",
        },
        "security": {
            "session_hours": _session_hours(
                current_app.config.get("JWT_ACCESS_TOKEN_EXPIRES")
            ),
            "idle_timeout_minutes": int(current_app.config["SESSION_IDLE_MINUTES"]),
            "login_lock_threshold": int(current_app.config["LOGIN_LOCK_THRESHOLD"]),
            "login_lock_minutes": int(current_app.config["LOGIN_LOCK_MINUTES"]),
            "login_rate_limit_per_minute": int(
                current_app.config["LOGIN_RATE_LIMIT_PER_MINUTE"]
            ),
            "user_rate_limit_per_minute": int(
                current_app.config["USER_RATE_LIMIT_PER_MINUTE"]
            ),
            "login_failure_lock_configured": True,
            "rate_limit_configured": bool(
                current_app.config.get("RATE_LIMIT_ENABLED", True)
            ),
        },
    }


__all__ = ["get_status"]
