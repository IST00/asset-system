"""Configuration classes for Dev / Prod / Test profiles.

Profile selection
-----------------
The active profile is resolved in this order (highest wins):
  1. Explicit argv on `python manage.py run [dev|prod|test]`
     or `python manage.py run --env <profile>` (handled in manage.py).
  2. `FLASK_ENV` environment variable.
  3. Default: `dev`.

Profile -> .env file
--------------------
On first call to `bootstrap_env()` (from manage.py / wsgi.py / gunicorn.conf.py
/ load_config), we load variables from a profile-specific dotenv file:

  dev / development / test / testing  -> back/.env.dev
  prod / production                   -> back/.env.prod

System environment variables ALWAYS win over the file (override=False), so
real secrets injected via docker-compose / systemd EnvironmentFile / K8s
Secret will not be clobbered by placeholders in `.env.prod`.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

_BACK_DIR = Path(__file__).resolve().parent
_LOADED_FILES: set[str] = set()


def _resolve_env_file(profile: str) -> Path:
    """Return the dotenv file path for the given profile.

    `ENV_FILE` env var, if set, overrides the profile-based mapping.
    """
    explicit = os.getenv("ENV_FILE")
    if explicit:
        return Path(explicit).expanduser().resolve()
    if profile in {"prod", "production"}:
        return _BACK_DIR / ".env.prod"
    # dev / development / test / testing all share .env.dev
    return _BACK_DIR / ".env.dev"


def bootstrap_env(profile: str | None = None) -> str:
    """Load the matching .env file for `profile` (or `FLASK_ENV`).

    Idempotent — calling it again with the same file is a no-op.
    Returns the resolved profile name, lower-cased.
    """
    resolved = (profile or os.getenv("FLASK_ENV") or "dev").lower()
    # Ensure FLASK_ENV reflects what we just resolved, so downstream
    # `os.getenv("FLASK_ENV")` calls see a consistent value.
    os.environ.setdefault("FLASK_ENV", resolved)

    env_file = _resolve_env_file(resolved)
    key = str(env_file)
    if key in _LOADED_FILES:
        return resolved
    if env_file.is_file():
        # override=False: real env (docker / k8s / systemd) wins over the file.
        load_dotenv(env_file, override=False)
        _LOADED_FILES.add(key)
    return resolved


class BaseConfig:
    # --- Flask core ---
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-flask-secret")

    # --- SQLAlchemy ---
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    SQLALCHEMY_ENGINE_OPTIONS: dict = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }

    # --- JWT ---
    JWT_SECRET_KEY: str = os.getenv(
        "JWT_SECRET", "change-me-change-me-change-me-change-me"
    )
    JWT_ACCESS_TOKEN_EXPIRES: timedelta = timedelta(
        seconds=int(os.getenv("JWT_EXPIRE_SECONDS", "28800"))
    )
    JWT_TOKEN_LOCATION: list[str] = ["headers"]
    JWT_HEADER_NAME: str = "Authorization"
    JWT_HEADER_TYPE: str = "Bearer"

    # --- Local account security ---
    SESSION_IDLE_MINUTES: int = int(os.getenv("SESSION_IDLE_MINUTES", "120"))
    LOGIN_LOCK_THRESHOLD: int = int(os.getenv("LOGIN_LOCK_THRESHOLD", "5"))
    LOGIN_LOCK_MINUTES: int = int(os.getenv("LOGIN_LOCK_MINUTES", "15"))
    LOGIN_RATE_LIMIT_PER_MINUTE: int = int(
        os.getenv("LOGIN_RATE_LIMIT_PER_MINUTE", "10")
    )
    USER_RATE_LIMIT_PER_MINUTE: int = int(
        os.getenv("USER_RATE_LIMIT_PER_MINUTE", "120")
    )
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    # --- flask-smorest / OpenAPI ---
    API_TITLE: str = "Scaffold Python API"
    API_VERSION: str = "v1"
    OPENAPI_VERSION: str = "3.0.3"
    OPENAPI_URL_PREFIX: str = "/"
    OPENAPI_SWAGGER_UI_PATH: str = "/swagger-ui"
    OPENAPI_SWAGGER_UI_URL: str = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"
    OPENAPI_JSON_PATH: str = "openapi.json"

    # --- Celery ---
    CELERY_BROKER_URL: str | None = os.getenv("CELERY_BROKER_URL")
    CELERY_RESULT_BACKEND: str | None = os.getenv("CELERY_RESULT_BACKEND")

    # --- App ---
    APP_NAME: str = "scaffold-python"
    HEALTH_PORT: int = int(os.getenv("HEALTH_PORT", "8081"))
    HEALTH_BIND: str = os.getenv("HEALTH_BIND", "0.0.0.0")
    EXPORT_RETENTION_HOURS: int = int(os.getenv("EXPORT_RETENTION_HOURS", "24"))
    EXPORT_STORAGE_DIR: str | None = os.getenv("EXPORT_STORAGE_DIR")


class DevConfig(BaseConfig):
    DEBUG: bool = True
    SQLALCHEMY_DATABASE_URI: str = os.getenv("DB_URL", "sqlite:///instance/dev.db")
    # dev defaults: weaker secrets are OK, but keep the shape
    JWT_SECRET_KEY: str = os.getenv(
        "JWT_SECRET", "dev-jwt-secret-change-me-change-me-change-me"
    )


class ProdConfig(BaseConfig):
    DEBUG: bool = False
    SQLALCHEMY_DATABASE_URI: str = os.getenv(
        "DB_URL",
        # pymysql driver; env-driven credentials
        "mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}?charset=utf8mb4".format(
            user=os.getenv("DB_USER", "scaffold"),
            pwd=os.getenv("DB_PASSWORD", "scaffold"),
            host=os.getenv("DB_HOST", "mysql"),
            port=os.getenv("DB_PORT", "3306"),
            db=os.getenv("DB_NAME", "scaffold"),
        ),
    )


class TestConfig(BaseConfig):
    TESTING: bool = True
    DEBUG: bool = False
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///:memory:"
    JWT_SECRET_KEY: str = "test-jwt-secret-test-jwt-secret-test-jwt-secret"
    RATE_LIMIT_ENABLED: bool = False


_PROFILES: dict[str, type[BaseConfig]] = {
    "dev": DevConfig,
    "development": DevConfig,
    "prod": ProdConfig,
    "production": ProdConfig,
    "test": TestConfig,
    "testing": TestConfig,
}


def load_config() -> type[BaseConfig]:
    profile = bootstrap_env()
    return _PROFILES.get(profile, DevConfig)
