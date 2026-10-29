"""Outbound Feishu notification fan-out for actionable workflow events."""

from __future__ import annotations

from typing import Any


from app.extensions import db
from app.models import User
from app.services import feishu_service


def send_to_user(user_id: int, title: str, content: str) -> dict[str, Any]:
    if not feishu_service.notifications_enabled():
        return {"sent": False, "reason": "DISABLED"}
    user = db.session.get(User, user_id)
    if user is None or not user.enabled:
        return {"sent": False, "reason": "USER_NOT_FOUND"}
    open_id = getattr(user, "feishu_open_id", None)
    if not open_id:
        return {"sent": False, "reason": "NO_FEISHU_ID"}
    message_id = feishu_service.send_text(open_id, f"{title}\n{content}")
    return {"sent": True, "message_id": message_id}


def send_to_open_id(open_id: str, title: str, content: str) -> dict[str, Any]:
    if not feishu_service.notifications_enabled():
        return {"sent": False, "reason": "DISABLED"}
    message_id = feishu_service.send_text(open_id, f"{title}\n{content}")
    return {"sent": True, "message_id": message_id}


def send_to_feishu_department(
    department_id: str, title: str, content: str
) -> dict[str, Any]:
    if not feishu_service.notifications_enabled():
        return {"sent": False, "reason": "DISABLED"}
    del department_id
    del title
    del content
    return {"sent": False, "reason": "DEPARTMENT_CHAT_NOT_CONFIGURED"}


def notify_users(user_ids: list[int], title: str, content: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for user_id in sorted(set(user_ids)):
        results.append({"user_id": user_id, **send_to_user(user_id, title, content)})
    return results


__all__ = [
    "notify_users",
    "send_to_feishu_department",
    "send_to_open_id",
    "send_to_user",
]
