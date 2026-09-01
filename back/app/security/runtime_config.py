"""Fail-fast security checks for pilot and production profiles."""

from __future__ import annotations

from flask import Flask

_DEPLOYMENT_STAGES = {"pilot", "production"}
_NON_DEPLOYMENT_STAGES = {"development", "testing"}
_PLACEHOLDER_MARKERS = (
    "change_me",
    "change-me",
    "changeme",
    "replace_me",
    "replace-me",
    "placeholder",
)


def _unsafe_secret(value: object, *, minimum_length: int = 32) -> bool:
    text = str(value or "").strip()
    normalized = text.lower()
    return len(text) < minimum_length or any(
        marker in normalized for marker in _PLACEHOLDER_MARKERS
    )


def validate_runtime_security(app: Flask) -> None:
    """Reject unsafe pilot/production configuration before app side effects."""
    stage = str(app.config.get("DEPLOYMENT_STAGE") or "").strip().lower()
    if stage in _NON_DEPLOYMENT_STAGES:
        return
    if stage not in _DEPLOYMENT_STAGES:
        raise RuntimeError(
            "Unsafe runtime configuration: DEPLOYMENT_STAGE must be "
            "development, testing, pilot, or production"
        )

    failures: list[str] = []
    if _unsafe_secret(app.config.get("SECRET_KEY")):
        failures.append("SECRET_KEY is missing, short, or a placeholder")
    if _unsafe_secret(app.config.get("JWT_SECRET_KEY")):
        failures.append("JWT_SECRET is missing, short, or a placeholder")

    database_uri = str(app.config.get("SQLALCHEMY_DATABASE_URI") or "").strip()
    if not database_uri.startswith("mysql+pymysql://") or any(
        marker in database_uri.lower() for marker in _PLACEHOLDER_MARKERS
    ):
        failures.append(
            "database configuration must be a non-placeholder MySQL connection"
        )

    cors = str(app.config.get("CORS_ALLOWED_ORIGINS") or "").strip()
    origins = [origin.strip() for origin in cors.split(",") if origin.strip()]
    if (
        not origins
        or "*" in origins
        or any(
            not origin.startswith("https://")
            or any(marker in origin.lower() for marker in _PLACEHOLDER_MARKERS)
            for origin in origins
        )
    ):
        failures.append("CORS must contain explicit HTTPS origins")

    if failures:
        raise RuntimeError("Unsafe runtime configuration: " + "; ".join(failures))


__all__ = ["validate_runtime_security"]
