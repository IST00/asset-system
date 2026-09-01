"""Regression contract: this application has no Redis integration."""

from __future__ import annotations

from pathlib import Path

from config import BaseConfig


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent


def test_base_config_has_no_redis_settings():
    assert not hasattr(BaseConfig, "REDIS_HOST")
    assert not hasattr(BaseConfig, "REDIS_PORT")


def test_project_files_have_no_redis_integration():
    paths = (
        REPOSITORY_ROOT / "README.md",
        REPOSITORY_ROOT / "CLAUDE.md",
        BACKEND_ROOT / "app" / "health" / "__init__.py",
        BACKEND_ROOT / "config.py",
        BACKEND_ROOT / ".env.dev",
        BACKEND_ROOT / ".env.prod",
        BACKEND_ROOT / ".env.test",
        BACKEND_ROOT / "requirements.txt",
        REPOSITORY_ROOT / "docker-compose.yml",
        REPOSITORY_ROOT / "docs" / "conventions" / "README.md",
        REPOSITORY_ROOT / "docs" / "conventions" / "backend.md",
        REPOSITORY_ROOT / "docs" / "conventions" / "middleware.md",
        REPOSITORY_ROOT / "docs" / "conventions" / "workflow.md",
    )

    redis_references = [
        str(path.relative_to(REPOSITORY_ROOT))
        for path in paths
        if "redis" in path.read_text(encoding="utf-8").lower()
    ]

    assert redis_references == []


def test_compose_uses_external_database_configuration():
    compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "\n  mysql:" not in compose
    assert "\n  redis:" not in compose
    assert "mysql_data" not in compose
    for key in (
        "DB_URL:",
        "DB_HOST:",
        "DB_PORT:",
        "DB_NAME:",
        "DB_USER:",
        "DB_PASSWORD:",
        "JWT_SECRET:",
        "SECRET_KEY:",
    ):
        assert key not in compose
    assert "env_file:" in compose
    assert "${BACK_ENV_FILE:-./back/.env.deploy}" in compose
    assert "FLASK_ENV: ${APP_ENV:-prod}" in compose
    assert "depends_on:\n      back:\n        condition: service_healthy" in compose


def test_deployment_secrets_are_not_tracked_or_copied_into_image():
    gitignore = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")
    dockerignore = (BACKEND_ROOT / ".dockerignore").read_text(encoding="utf-8")
    production_env = (BACKEND_ROOT / ".env.prod").read_text(encoding="utf-8")

    assert "back/.env.deploy" in gitignore
    assert ".env*" in dockerignore
    sensitive_keys = {
        "SECRET_KEY",
        "JWT_SECRET",
        "DB_URL",
        "DB_HOST",
        "DB_USER",
        "DB_PASSWORD",
        "DB_NAME",
    }
    unsafe_keys = []
    for line in production_env.splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in sensitive_keys and "CHANGE_ME_IN_DEPLOYMENT" not in value:
            unsafe_keys.append(key)
    assert unsafe_keys == []


def _active_env_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def test_committed_env_files_do_not_contain_remote_credentials() -> None:
    development = _active_env_values(BACKEND_ROOT / ".env.dev")
    assert "DB_HOST" not in development
    assert "DB_USER" not in development
    assert "DB_PASSWORD" not in development
    assert "DB_NAME" not in development
    assert "DB_URL" not in development

    for filename in (".env.prod", ".env.pilot.example", ".env.deploy.example"):
        values = _active_env_values(BACKEND_ROOT / filename)
        for key in (
            "SECRET_KEY",
            "JWT_SECRET",
            "DB_HOST",
            "DB_USER",
            "DB_PASSWORD",
            "DB_NAME",
        ):
            assert "CHANGE_ME" in values[key]

    legacy_test_template = _active_env_values(BACKEND_ROOT / ".env.test")
    for key in ("SECRET_KEY", "JWT_SECRET", "DB_PASSWORD", "DB_URL"):
        if key in legacy_test_template:
            assert "CHANGE_ME" in legacy_test_template[key]
