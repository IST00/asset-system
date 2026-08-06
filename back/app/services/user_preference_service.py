"""Persistence and validation for personal UI preferences."""

from __future__ import annotations

import json
from typing import Any

from app.common import BusinessException, ResultCode
from app.extensions import db
from app.models import User, UserPreference

_ALLOWED_COLUMNS = {
    "asset_code",
    "asset_name",
    "category_name",
    "status",
    "model",
    "serial_number",
    "receipt_number",
    "user_name",
    "department_name",
    "location_name",
    "manager_name",
    "company_name",
    "supplier_name",
    "source_name",
    "unit_name",
    "purchase_date",
    "purchase_amount",
    "information_complete",
}
_DEFAULT_COLUMNS = [
    "asset_code",
    "asset_name",
    "category_name",
    "status",
    "user_name",
    "department_name",
    "location_name",
    "manager_name",
    "company_name",
    "purchase_date",
]


def _require_user(user_id: int) -> None:
    if db.session.get(User, user_id) is None:
        raise BusinessException("用户不存在", result_code=ResultCode.NOT_FOUND)


def _get_or_create(user_id: int) -> UserPreference:
    _require_user(user_id)
    preference = db.session.get(UserPreference, user_id)
    if preference is None:
        preference = UserPreference(user_id=user_id)
        db.session.add(preference)
        db.session.flush()
    return preference


def _columns(preference: UserPreference) -> list[str]:
    if not preference.asset_list_columns:
        return list(_DEFAULT_COLUMNS)
    try:
        parsed = json.loads(preference.asset_list_columns)
    except (TypeError, json.JSONDecodeError):
        return list(_DEFAULT_COLUMNS)
    if not isinstance(parsed, list):
        return list(_DEFAULT_COLUMNS)
    columns = [
        value
        for value in parsed
        if isinstance(value, str) and value in _ALLOWED_COLUMNS
    ]
    return columns or list(_DEFAULT_COLUMNS)


def _serialize(preference: UserPreference) -> dict[str, Any]:
    return {
        "asset_list_columns": _columns(preference),
        "asset_list_page_size": preference.asset_list_page_size,
        "task_notice": preference.task_notice,
        "approval_notice": preference.approval_notice,
        "weekly_digest": preference.weekly_digest,
        "updated_at": preference.updated_at,
    }


def get(user_id: int) -> dict[str, Any]:
    preference = _get_or_create(user_id)
    db.session.commit()
    return _serialize(preference)


def update(user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    preference = _get_or_create(user_id)
    columns = payload.get("asset_list_columns")
    if columns is not None:
        unique_columns = list(dict.fromkeys(columns))
        unknown = set(unique_columns) - _ALLOWED_COLUMNS
        if unknown:
            raise BusinessException(
                "列显示设置包含不支持的字段",
                result_code=ResultCode.BAD_REQUEST,
            )
        if not unique_columns:
            raise BusinessException(
                "至少保留一个资产列表字段",
                result_code=ResultCode.BAD_REQUEST,
            )
        preference.asset_list_columns = json.dumps(
            unique_columns, ensure_ascii=False, separators=(",", ":")
        )
    for field in (
        "asset_list_page_size",
        "task_notice",
        "approval_notice",
        "weekly_digest",
    ):
        if field in payload:
            setattr(preference, field, payload[field])
    db.session.commit()
    return _serialize(preference)
