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
from app.common.json_provider import UTCJSONProvider
from app.extensions import db, jwt, migrate
from app.observability import init_observability
from app.security import (
    register_jwt_callbacks,
    register_request_security,
    validate_runtime_security,
)
from config import BaseConfig, load_config


def _enable_cors(app: Flask) -> None:
    """Single place for CORS rules — mirrors CorsConfig on the Java side.

    ``CORS_ALLOWED_ORIGINS`` is a comma-separated list.
    - ``*`` (default for dev) 回显请求的 Origin，方便本地调试；不建议用于 prod。
    - 具体域名列表：只对命中的 Origin 回写 Allow-Origin 头，未命中则不回写
      （浏览器会拦住，等同于拒绝）。
    """
    raw = str(app.config.get("CORS_ALLOWED_ORIGINS") or "").strip()
    allow_any = raw == "*" and app.config.get("DEPLOYMENT_STAGE") in {
        "development",
        "testing",
    }
    whitelist = {
        origin.strip()
        for origin in raw.split(",")
        if origin.strip() and origin.strip() != "*"
    }

    @app.after_request
    def _set_cors_headers(resp: Any) -> Any:
        from flask import request

        origin = request.headers.get("Origin", "")
        if allow_any and origin:
            resp.headers.setdefault("Access-Control-Allow-Origin", origin)
            resp.headers.setdefault("Vary", "Origin")
        elif origin in whitelist:
            resp.headers.setdefault("Access-Control-Allow-Origin", origin)
            resp.headers.setdefault("Vary", "Origin")
        # else: 不命中则完全不写 Allow-Origin，浏览器自然拦截
        resp.headers.setdefault("Access-Control-Allow-Credentials", "true")
        resp.headers.setdefault(
            "Access-Control-Allow-Headers",
            "Authorization, Content-Type, X-Requested-With",
        )
        resp.headers.setdefault("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        resp.headers.setdefault("Access-Control-Max-Age", "3600")
        return resp


def create_app(config: type[BaseConfig] | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.json_provider_class = UTCJSONProvider
    app.json = app.json_provider_class(app)
    app.config.from_object(config or load_config())
    validate_runtime_security(app)

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
    register_request_security(app)

    # --- blueprints ---
    from app.api import register_blueprints  # import here to avoid circular imports

    register_blueprints(app)

    from app.operations import operation_handler_registry
    from app.operations.asset_usage_return_handlers import (
        PersonalReturnHandler,
        PersonalUsageHandler,
        PublicReturnHandler,
        PublicUsageHandler,
    )
    from app.operations.stock_in_handler import StockInHandler

    handler_types = (
        StockInHandler,
        PersonalUsageHandler,
        PublicUsageHandler,
        PersonalReturnHandler,
        PublicReturnHandler,
    )
    for handler_type in handler_types:
        if not operation_handler_registry.contains(handler_type.operation_type):
            operation_handler_registry.register(handler_type())

    # --- global error handlers ---
    register_error_handlers(app)

    # --- CORS ---
    _enable_cors(app)

    return app
