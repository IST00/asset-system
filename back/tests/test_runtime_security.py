"""Runtime security contracts for non-development deployments."""

from __future__ import annotations

import io
import logging
import subprocess
import runpy
import sys
from pathlib import Path

import pytest
from flask import Flask

from app import create_app
from app.observability import MdcFilter, SensitiveFormatter
from app.security.runtime_config import validate_runtime_security
from config import TestConfig


def _configured_app(**overrides: object) -> Flask:
    app = Flask(__name__)
    app.config.update(
        DEPLOYMENT_STAGE="pilot",
        SECRET_KEY="f" * 48,
        JWT_SECRET_KEY="j" * 48,
        SQLALCHEMY_DATABASE_URI=(
            "mysql+pymysql://asset_pilot_app:encoded-password@db:3306/"
            "asset_system_pilot?charset=utf8mb4"
        ),
        CORS_ALLOWED_ORIGINS="https://asset-pilot.example.com",
    )
    app.config.update(overrides)
    return app


@pytest.mark.parametrize("stage", ["pilot", "production"])
def test_secure_deployment_configuration_is_accepted(stage: str) -> None:
    validate_runtime_security(_configured_app(DEPLOYMENT_STAGE=stage))


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("SECRET_KEY", "CHANGE_ME_IN_DEPLOYMENT", "SECRET_KEY"),
        ("JWT_SECRET_KEY", "change-me", "JWT_SECRET"),
        ("CORS_ALLOWED_ORIGINS", "*", "CORS"),
        (
            "CORS_ALLOWED_ORIGINS",
            "https://CHANGE_ME_PILOT_HOST",
            "CORS",
        ),
        ("CORS_ALLOWED_ORIGINS", "https://placeholder.invalid", "CORS"),
        (
            "SQLALCHEMY_DATABASE_URI",
            "mysql+pymysql://CHANGE_ME:CHANGE_ME@db:3306/CHANGE_ME",
            "database",
        ),
        ("SQLALCHEMY_DATABASE_URI", "sqlite:///pilot.db", "database"),
    ],
)
def test_unsafe_deployment_configuration_is_rejected(
    key: str, value: str, message: str
) -> None:
    with pytest.raises(RuntimeError, match=message):
        validate_runtime_security(_configured_app(**{key: value}))


def test_unknown_deployment_stage_is_rejected() -> None:
    with pytest.raises(RuntimeError, match="DEPLOYMENT_STAGE"):
        validate_runtime_security(_configured_app(DEPLOYMENT_STAGE="prod-like"))


def test_development_and_testing_skip_deployment_secret_gate() -> None:
    for stage in ("development", "testing"):
        validate_runtime_security(
            _configured_app(
                DEPLOYMENT_STAGE=stage,
                SECRET_KEY="dev",
                JWT_SECRET_KEY="dev",
                SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
                CORS_ALLOWED_ORIGINS="*",
            )
        )


class ExplicitCorsTestConfig(TestConfig):
    CORS_ALLOWED_ORIGINS = "https://pilot.example.com,https://review.example.com"


def test_allowed_cors_origin_is_echoed() -> None:
    client = create_app(ExplicitCorsTestConfig).test_client()
    response = client.get("/api/hello", headers={"Origin": "https://pilot.example.com"})
    assert response.headers["Access-Control-Allow-Origin"] == (
        "https://pilot.example.com"
    )


def test_unknown_cors_origin_is_not_echoed() -> None:
    client = create_app(ExplicitCorsTestConfig).test_client()
    response = client.get(
        "/api/hello", headers={"Origin": "https://attacker.example.com"}
    )
    assert "Access-Control-Allow-Origin" not in response.headers


def test_log_formatter_redacts_credentials_and_database_passwords() -> None:
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.addFilter(MdcFilter())
    handler.setFormatter(SensitiveFormatter("%(message)s"))
    logger = logging.getLogger("test.runtime-security.redaction")
    logger.addHandler(handler)
    logger.propagate = False
    logger.setLevel(logging.INFO)
    try:
        logger.warning(
            "Authorization: Bearer never-log-this-token "
            "DB_PASSWORD=never-log-this-db-password "
            "database=mysql+pymysql://asset_app:never-log-this-uri-password@db/x "
            'payload={"password":"never-log-this-login-password"}'
        )
        try:
            raise RuntimeError("JWT_SECRET=never-log-this-exception-secret")
        except RuntimeError:
            logger.exception("simulated database failure")
    finally:
        logger.removeHandler(handler)
        logger.propagate = True

    text = output.getvalue()
    for secret in (
        "never-log-this-token",
        "never-log-this-db-password",
        "never-log-this-uri-password",
        "never-log-this-login-password",
        "never-log-this-exception-secret",
    ):
        assert secret not in text
    assert "[REDACTED]" in text


def test_access_log_excludes_headers_bodies_queries_and_attachments(client) -> None:
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.addFilter(MdcFilter())
    handler.setFormatter(SensitiveFormatter("%(message)s"))
    logger = logging.getLogger("app.access")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        client.post(
            "/api/v1/auth/login",
            headers={"Authorization": "Bearer never-log-this-request-token"},
            json={
                "username": "never-log-this-username",
                "password": "never-log-this-request-password",
            },
        )
        client.get("/api/hello?token=never-log-this-query-token")
        client.post(
            "/api/v1/assets/1/attachments",
            headers={"Authorization": "Bearer invalid-token"},
            data={
                "business_type": "DOCUMENT",
                "file": (
                    io.BytesIO(b"never-log-this-attachment-content"),
                    "private.txt",
                ),
            },
            content_type="multipart/form-data",
        )
    finally:
        logger.removeHandler(handler)

    text = output.getvalue()
    assert "POST /api/v1/auth/login" in text
    assert "GET /api/hello" in text
    assert "POST /api/v1/assets/1/attachments" in text
    for sensitive_text in (
        "never-log-this-request-token",
        "never-log-this-username",
        "never-log-this-request-password",
        "never-log-this-query-token",
        "never-log-this-attachment-content",
        "private.txt",
        '"username"',
        '"password"',
    ):
        assert sensitive_text not in text


def test_gunicorn_access_log_format_excludes_query_and_headers() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    config = runpy.run_path(str(backend_root / "gunicorn.conf.py"))
    access_format = str(config["access_log_format"])
    assert "%(m)s" in access_format
    assert "%(U)s" in access_format
    assert "%(s)s" in access_format
    assert "%(r)s" not in access_format
    assert "%(q)s" not in access_format
    assert "authorization" not in access_format.lower()


def test_explicit_env_file_is_loaded_before_config_classes(tmp_path: Path) -> None:
    env_file = tmp_path / "pilot.env"
    env_file.write_text(
        "DEPLOYMENT_STAGE=pilot\n"
        f"SECRET_KEY={'s' * 48}\n"
        f"JWT_SECRET={'j' * 48}\n"
        "DB_HOST=pilot-db.invalid\n"
        "DB_PORT=3306\n"
        "DB_USER=asset_pilot_app\n"
        "DB_PASSWORD=synthetic-pilot-db-password\n"
        "DB_NAME=asset_system_pilot\n"
        "CORS_ALLOWED_ORIGINS=https://pilot.example.com\n",
        encoding="utf-8",
    )
    backend_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app import create_app; "
                "app = create_app(); "
                "assert app.config['DEPLOYMENT_STAGE'] == 'pilot'; "
                "assert app.config['CORS_ALLOWED_ORIGINS'] == "
                "'https://pilot.example.com'"
            ),
        ],
        cwd=backend_root,
        env={"FLASK_ENV": "prod", "ENV_FILE": str(env_file)},
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stderr
