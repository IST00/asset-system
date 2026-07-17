"""POST /api/auth/register  and  POST /api/auth/login.

Blueprints load requests via marshmallow schemas and delegate to
`app.services.auth_service` — no direct model/db touch here.
"""

from __future__ import annotations

from flask import Blueprint, request

from app.common import Result
from app.schemas import LoginRequestSchema
from app.services import auth_service

bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")

_login_schema = LoginRequestSchema()


@bp.post("/login")
def login() -> dict:
    payload = _login_schema.load(request.get_json(silent=True) or {})
    login_data = auth_service.login(
        username=payload["username"],
        password=payload["password"],
    )
    return Result.success(login_data).to_dict()
