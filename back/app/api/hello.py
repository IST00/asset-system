"""GET /api/hello — public health/ping endpoint."""

from __future__ import annotations

from flask import Blueprint

from app.common import Result

bp = Blueprint("hello", __name__, url_prefix="/api")


@bp.get("/hello")
def hello() -> dict:
    return Result.success("Hello from Flask!").to_dict()
