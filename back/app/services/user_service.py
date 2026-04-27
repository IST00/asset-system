"""User service — queries for the current user and admin-scoped paging."""

from __future__ import annotations

from typing import Any

from app.common import BusinessException, PageResult
from app.models import User
from app.repositories import QuerySpec, user_repository


def _user_to_dict(u: User) -> dict[str, Any]:
    return {
        "id": u.id,
        "username": u.username,
        "nickname": u.nickname,
        "role": u.role,
        "enabled": u.enabled,
        "created_at": u.created_at,
        "updated_at": u.updated_at,
    }


def get_current(username: str) -> dict[str, Any]:
    user = user_repository.find_by_username(username)
    if user is None:
        raise BusinessException("user not found")
    return _user_to_dict(user)


def page(page_index: int, size: int) -> PageResult:
    # page_index is 0-based (matches the Java side's controller contract)
    spec = QuerySpec(
        order_by=[User.id.asc()],
        page=page_index if page_index >= 0 else 0,
        size=size if size > 0 else 10,
    )
    result = user_repository.page(spec)
    return PageResult(
        items=[_user_to_dict(u) for u in result.items],
        total=result.total,
        page=result.page,
        size=result.size,
    )
