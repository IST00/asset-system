"""Configuration classes for Dev / Prod / Test profiles.

Selected via the FLASK_ENV env var (default: dev).
Secrets must come from environment variables in prod.
"""

from __future__ import annotations

import os
from datetime import timedelta


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
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET", "change-me-change-me-change-me-change-me")
    JWT_ACCESS_TOKEN_EXPIRES: timedelta = timedelta(
        seconds=int(os.getenv("JWT_EXPIRE_SECONDS", "86400"))
    )
    JWT_TOKEN_LOCATION: list[str] = ["headers"]
    JWT_HEADER_NAME: str = "Authorization"
    JWT_HEADER_TYPE: str = "Bearer"

    # --- flask-smorest / OpenAPI ---
    API_TITLE: str = "Scaffold Python API"
    API_VERSION: str = "v1"
    OPENAPI_VERSION: str = "3.0.3"
    OPENAPI_URL_PREFIX: str = "/"
    OPENAPI_SWAGGER_UI_PATH: str = "/swagger-ui"
    OPENAPI_SWAGGER_UI_URL: str = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"
    OPENAPI_JSON_PATH: str = "openapi.json"

    # --- Redis / Celery ---
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    CELERY_BROKER_URL: str = os.getenv(
        "CELERY_BROKER_URL",
        f"redis://{os.getenv('REDIS_HOST', 'localhost')}:{os.getenv('REDIS_PORT', '6379')}/0",
    )
    CELERY_RESULT_BACKEND: str = os.getenv(
        "CELERY_RESULT_BACKEND",
        f"redis://{os.getenv('REDIS_HOST', 'localhost')}:{os.getenv('REDIS_PORT', '6379')}/1",
    )

    # --- App ---
    APP_NAME: str = "scaffold-python"
    HEALTH_PORT: int = int(os.getenv("HEALTH_PORT", "8081"))
    HEALTH_BIND: str = os.getenv("HEALTH_BIND", "127.0.0.1")


class DevConfig(BaseConfig):
    DEBUG: bool = True
    SQLALCHEMY_DATABASE_URI: str = os.getenv("DB_URL", "sqlite:///instance/dev.db")
    # dev defaults: weaker secrets are OK, but keep the shape
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET", "dev-jwt-secret-change-me-change-me-change-me")


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


_PROFILES: dict[str, type[BaseConfig]] = {
    "dev": DevConfig,
    "development": DevConfig,
    "prod": ProdConfig,
    "production": ProdConfig,
    "test": TestConfig,
    "testing": TestConfig,
}


def load_config() -> type[BaseConfig]:
    env = os.getenv("FLASK_ENV", "dev").lower()
    return _PROFILES.get(env, DevConfig)
