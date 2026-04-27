"""Flask application factory.

create_app() wires config, extensions, blueprints, JWT callbacks, and error
handlers. A separate health Flask app lives in app.health and is started
by gunicorn `post_fork` on a private port.
"""

from __future__ import annotations

import os
from typing import Any

from flask import Flask

from app.common import register_error_handlers
from app.extensions import db, jwt, migrate
from app.observability import init_observability
from app.security import register_jwt_callbacks
from config import BaseConfig, load_config


def _enable_cors(app: Flask) -> None:
    """Single place for CORS rules — mirrors CorsConfig on the Java side."""
    allowed = os.getenv("CORS_ALLOWED_ORIGINS", "*")

    @app.after_request
    def _set_cors_headers(resp: Any) -> Any:
        resp.headers.setdefault("Access-Control-Allow-Origin", allowed)
        resp.headers.setdefault(
            "Access-Control-Allow-Headers", "Authorization, Content-Type, X-Requested-With"
        )
        resp.headers.setdefault(
            "Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        )
        resp.headers.setdefault("Access-Control-Max-Age", "3600")
        return resp


def create_app(config: type[BaseConfig] | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config or load_config())

    # Ensure SQLite instance dir exists for dev profile
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    # Observability must run before error handlers so request_id is in scope.
    init_observability(app)

    # --- extensions ---
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    # --- JWT callbacks translate errors into Result envelope ---
    register_jwt_callbacks(app, jwt)

    # --- blueprints ---
    from app.api import register_blueprints  # import here to avoid circular imports

    register_blueprints(app)

    # --- global error handlers ---
    register_error_handlers(app)

    # --- CORS ---
    _enable_cors(app)

    return app
