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
