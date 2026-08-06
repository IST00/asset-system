"""Authenticated system capability status endpoint."""

from __future__ import annotations

from flask import Blueprint
from flask_jwt_extended import jwt_required

from app.common import Result
from app.services import system_status_service

bp = Blueprint("system_status", __name__, url_prefix="/api/v1/system")


@bp.get("/status")
@jwt_required()
def status() -> dict:
    return Result.success(system_status_service.get_status()).to_dict()


__all__ = ["bp"]
