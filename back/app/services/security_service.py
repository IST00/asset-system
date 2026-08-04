"""Account security policies, server-side sessions, and database rate limits."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from flask import current_app
from flask_jwt_extended import create_access_token
from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.common import BusinessException, ResultCode
from app.extensions import db
from app.models import (
    PasswordHistory,
    RateLimitBucket,
    SecurityEventLog,
    User,
    UserSession,
)
from app.repositories import rbac_repository, user_repository
from app.security.passwords import hash_password, verify_password

_PASSWORD_HISTORY_LIMIT = 5
_SESSION_TOUCH_INTERVAL = timedelta(seconds=60)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _event(
    event_type: str,
    *,
    user: User | None = None,
    username: str | None = None,
    ip_address: str | None = None,
    detail: str | None = None,
) -> None:
    db.session.add(
        SecurityEventLog(
            event_type=event_type,
            user_id=user.id if user is not None else None,
            username=user.username if user is not None else username,
            ip_address=ip_address,
            detail=detail,
        )
    )


def record_event(
    event_type: str,
    *,
    user: User | None = None,
    username: str | None = None,
    ip_address: str | None = None,
    detail: str | None = None,
    commit: bool = False,
) -> None:
    _event(
        event_type,
        user=user,
        username=username,
        ip_address=ip_address,
        detail=detail,
    )
    if commit:
        db.session.commit()


def _increment_rate_limit_bucket(
    *, scope: str, subject: str, window_start: datetime, expires_at: datetime
) -> int:
    """Atomically create or increment one rate-limit bucket.

    Browsers issue several authenticated requests in parallel when a page opens.
    A read-then-insert implementation can make those requests race on the unique
    bucket key, especially with SQLite in local development. Both supported
    databases provide an atomic upsert, so the request burst remains reliable.
    """
    table = RateLimitBucket.__table__
    values = {
        "scope": scope,
        "subject": subject,
        "window_start": window_start,
        "count": 1,
        "expires_at": expires_at,
        "created_at": window_start,
        "updated_at": window_start,
    }
    dialect_name = db.session.get_bind().dialect.name
    if dialect_name == "mysql":
        mysql_statement = mysql_insert(table).values(**values)
        mysql_statement = mysql_statement.on_duplicate_key_update(
            count=table.c.count + 1,
            expires_at=expires_at,
            updated_at=window_start,
        )
        db.session.execute(mysql_statement)
    else:
        # Development and tests use SQLite. Keeping the SQLite branch as the
        # fallback also makes unsupported local profiles fail at execution time
        # instead of silently returning a wrong counter.
        sqlite_statement = sqlite_insert(table).values(**values)
        sqlite_statement = sqlite_statement.on_conflict_do_update(
            index_elements=[table.c.scope, table.c.subject, table.c.window_start],
            set_={
                "count": table.c.count + 1,
                "expires_at": expires_at,
                "updated_at": window_start,
            },
        )
        db.session.execute(sqlite_statement)
    count = db.session.scalar(
        select(RateLimitBucket.count).where(
            RateLimitBucket.scope == scope,
            RateLimitBucket.subject == subject,
            RateLimitBucket.window_start == window_start,
        )
    )
    return int(count or 0)


def consume_rate_limit(*, scope: str, subject: str, limit: int) -> int:
    if not current_app.config.get("RATE_LIMIT_ENABLED", True):
        return 0
    now = _now()
    window_start = now.replace(second=0, microsecond=0)
    count = _increment_rate_limit_bucket(
        scope=scope,
        subject=subject,
        window_start=window_start,
        expires_at=window_start + timedelta(minutes=2),
    )

    # Small bounded cleanup keeps this table self-maintaining without a scheduler.
    db.session.execute(
        delete(RateLimitBucket)
        .where(RateLimitBucket.expires_at < now - timedelta(minutes=5))
        .execution_options(synchronize_session=False)
    )
    db.session.commit()
    if count > limit:
        _event(
            "RATE_LIMITED",
            ip_address=subject if scope == "login_ip" else None,
            detail=f"scope={scope}; subject={subject}; limit={limit}",
        )
        db.session.commit()
        raise BusinessException("请求过于频繁，请稍后再试", code=429)
    return count


def enforce_login_rate_limit(ip_address: str) -> None:
    consume_rate_limit(
        scope="login_ip",
        subject=ip_address or "unknown",
        limit=int(current_app.config["LOGIN_RATE_LIMIT_PER_MINUTE"]),
    )


def enforce_user_rate_limit(user_id: int) -> None:
    consume_rate_limit(
        scope="user_api",
        subject=str(user_id),
        limit=int(current_app.config["USER_RATE_LIMIT_PER_MINUTE"]),
    )


def validate_password_policy(user: User, new_password: str) -> None:
    if len(new_password) < 12:
        raise BusinessException(
            "新密码至少需要 12 位", result_code=ResultCode.BAD_REQUEST
        )
    complexity_checks = (
        re.search(r"[a-z]", new_password),
        re.search(r"[A-Z]", new_password),
        re.search(r"[0-9]", new_password),
        re.search(r"[^A-Za-z0-9]", new_password),
    )
    if not all(complexity_checks):
        raise BusinessException(
            "新密码必须包含大写字母、小写字母、数字和特殊字符",
            result_code=ResultCode.BAD_REQUEST,
        )

    recent_hashes = list(
        db.session.scalars(
            select(PasswordHistory.password_hash)
            .where(PasswordHistory.user_id == user.id)
            .order_by(PasswordHistory.created_at.desc(), PasswordHistory.id.desc())
            .limit(_PASSWORD_HISTORY_LIMIT)
        ).all()
    )
    candidates = [user.password, *recent_hashes]
    if any(
        verify_password(new_password, password_hash) for password_hash in candidates
    ):
        raise BusinessException(
            "新密码不能与最近 5 次使用过的密码相同",
            result_code=ResultCode.BAD_REQUEST,
        )


def apply_new_password(user: User, new_password: str, *, must_change: bool) -> None:
    validate_password_policy(user, new_password)
    known_hash = db.session.scalar(
        select(PasswordHistory.id).where(
            PasswordHistory.user_id == user.id,
            PasswordHistory.password_hash == user.password,
        )
    )
    if known_hash is None:
        db.session.add(PasswordHistory(user_id=user.id, password_hash=user.password))
    new_hash = hash_password(new_password)
    user.password = new_hash
    user.password_changed_at = _now()
    user.must_change_password = must_change
    db.session.add(PasswordHistory(user_id=user.id, password_hash=new_hash))


def revoke_all_sessions(user_id: int, *, reason: str) -> int:
    now = _now()
    sessions = list(
        db.session.scalars(
            select(UserSession).where(
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
            )
        ).all()
    )
    for session in sessions:
        session.revoked_at = now
        session.revoke_reason = reason
    return len(sessions)


def issue_session(
    user: User,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> dict[str, Any]:
    now = _now()
    expires_delta: timedelta = current_app.config["JWT_ACCESS_TOKEN_EXPIRES"]
    session_id = str(uuid4())
    expires_at = now + expires_delta
    db.session.add(
        UserSession(
            session_id=session_id,
            user_id=user.id,
            issued_at=now,
            last_seen_at=now,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=(user_agent or "")[:255] or None,
        )
    )
    token = create_access_token(
        identity=str(user.id),
        expires_delta=expires_delta,
        additional_claims={"sid": session_id},
    )
    return {
        "token": token,
        "session_expires_at": expires_at.isoformat(),
        "idle_timeout_minutes": int(current_app.config["SESSION_IDLE_MINUTES"]),
    }


def revoke_session(session_id: str, *, user_id: int, reason: str) -> None:
    session = db.session.get(UserSession, session_id)
    if session is None or session.user_id != user_id:
        return
    if session.revoked_at is None:
        session.revoked_at = _now()
        session.revoke_reason = reason
        user = user_repository.get(user_id)
        _event("SESSION_REVOKED", user=user, detail=reason)
        db.session.commit()


def validate_session_for_jwt(session_id: str | None, identity: str | None) -> bool:
    if not session_id or not identity:
        return True
    try:
        user_id = int(identity)
    except (TypeError, ValueError):
        return True
    session = db.session.get(UserSession, session_id)
    user = user_repository.get(user_id)
    if (
        session is None
        or session.user_id != user_id
        or user is None
        or not user.enabled
    ):
        return True
    if session.revoked_at is not None:
        return True

    now = _now()
    expires_at = _as_utc(session.expires_at)
    last_seen_at = _as_utc(session.last_seen_at)
    idle_limit = timedelta(minutes=int(current_app.config["SESSION_IDLE_MINUTES"]))
    if expires_at is None or expires_at <= now:
        session.revoked_at = now
        session.revoke_reason = "absolute_timeout"
        _event("SESSION_REVOKED", user=user, detail="absolute_timeout")
        db.session.commit()
        return True
    if last_seen_at is None or last_seen_at + idle_limit <= now:
        session.revoked_at = now
        session.revoke_reason = "idle_timeout"
        _event("SESSION_REVOKED", user=user, detail="idle_timeout")
        db.session.commit()
        return True
    if now - last_seen_at >= _SESSION_TOUCH_INTERVAL:
        session.last_seen_at = now
        db.session.commit()
    return False


def user_requires_password_change(user_id: int) -> bool:
    user = user_repository.get(user_id)
    return bool(user is not None and user.must_change_password)


def list_events(
    *,
    actor_id: int,
    page: int = 0,
    size: int = 50,
    event_type: str | None = None,
    keyword: str | None = None,
) -> dict[str, Any]:
    """Return security events to full-scope audit users."""
    from app.services import permission_service

    permission_service.require_permission(actor_id, "audit:view")
    if permission_service.accessible_organization_ids(actor_id) is not None:
        raise BusinessException(
            "安全日志仅支持全量数据权限", result_code=ResultCode.FORBIDDEN
        )

    filters = []
    normalized_type = event_type.strip().upper() if event_type else None
    if normalized_type:
        filters.append(SecurityEventLog.event_type == normalized_type)
    normalized_keyword = keyword.strip() if keyword else None
    if normalized_keyword:
        pattern = f"%{normalized_keyword}%"
        filters.append(
            or_(
                SecurityEventLog.username.ilike(pattern),
                SecurityEventLog.ip_address.ilike(pattern),
                SecurityEventLog.detail.ilike(pattern),
                SecurityEventLog.event_type.ilike(pattern),
            )
        )

    total = (
        db.session.scalar(select(func.count(SecurityEventLog.id)).where(*filters)) or 0
    )
    events = list(
        db.session.scalars(
            select(SecurityEventLog)
            .where(*filters)
            .order_by(SecurityEventLog.id.desc())
            .limit(size)
            .offset(page * size)
        ).all()
    )
    return {
        "items": [
            {
                "id": event.id,
                "event_type": event.event_type,
                "user_id": event.user_id,
                "username": event.username,
                "ip_address": event.ip_address,
                "detail": event.detail,
                "created_at": event.created_at,
            }
            for event in events
        ],
        "total": int(total),
        "page": page,
        "size": size,
    }


def cleanup_security_data(
    *,
    now: datetime | None = None,
    event_retention_days: int = 365,
    session_retention_days: int = 30,
) -> dict[str, int]:
    """Delete expired rate buckets and old security/session records."""
    reference = _as_utc(now) or _now()
    event_cutoff = reference - timedelta(days=event_retention_days)
    session_cutoff = reference - timedelta(days=session_retention_days)

    event_result = db.session.execute(
        delete(SecurityEventLog)
        .where(SecurityEventLog.created_at < event_cutoff)
        .execution_options(synchronize_session=False)
    )
    bucket_result = db.session.execute(
        delete(RateLimitBucket)
        .where(RateLimitBucket.expires_at < reference)
        .execution_options(synchronize_session=False)
    )
    session_result = db.session.execute(
        delete(UserSession)
        .where(
            or_(
                UserSession.expires_at < session_cutoff,
                UserSession.revoked_at < session_cutoff,
            )
        )
        .execution_options(synchronize_session=False)
    )
    db.session.commit()
    return {
        "security_events": int(event_result.rowcount or 0),
        "rate_limit_buckets": int(bucket_result.rowcount or 0),
        "user_sessions": int(session_result.rowcount or 0),
    }


def reset_super_admin_password(*, username: str, new_password: str) -> None:
    user = user_repository.find_by_username(username)
    if user is None:
        raise BusinessException("用户不存在", result_code=ResultCode.NOT_FOUND)
    if "SUPER_ADMIN" not in rbac_repository.role_codes_for_user(user.id):
        raise BusinessException(
            "只能重置本地超级管理员密码", result_code=ResultCode.FORBIDDEN
        )
    apply_new_password(user, new_password, must_change=True)
    revoked = revoke_all_sessions(user.id, reason="admin_password_reset")
    _event(
        "PASSWORD_RESET",
        user=user,
        detail=f"server_cli; revoked_sessions={revoked}; must_change_password=true",
    )
    db.session.commit()


__all__ = [
    "apply_new_password",
    "cleanup_security_data",
    "consume_rate_limit",
    "enforce_login_rate_limit",
    "enforce_user_rate_limit",
    "issue_session",
    "list_sessions",
    "list_events",
    "record_event",
    "reset_super_admin_password",
    "revoke_all_sessions",
    "revoke_session",
    "revoke_user_session",
    "user_requires_password_change",
    "validate_password_policy",
    "validate_session_for_jwt",
]


def _masked_ip(value: str | None) -> str | None:
    if not value:
        return None
    if ":" in value:
        parts = value.split(":")
        return ":".join(parts[:2]) + ":****"
    parts = value.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.*.*"
    return "***"


def list_sessions(user_id: int, current_session_id: str | None) -> list[dict[str, Any]]:
    now = _now()
    rows = list(
        db.session.scalars(
            select(UserSession)
            .where(UserSession.user_id == user_id)
            .order_by(UserSession.last_seen_at.desc())
        ).all()
    )
    return [
        {
            "session_id": row.session_id,
            "current": row.session_id == current_session_id,
            "active": row.revoked_at is None and (_as_utc(row.expires_at) or now) > now,
            "issued_at": row.issued_at,
            "last_seen_at": row.last_seen_at,
            "expires_at": row.expires_at,
            "revoked_at": row.revoked_at,
            "revoke_reason": row.revoke_reason,
            "ip_address": _masked_ip(row.ip_address),
            "user_agent": row.user_agent,
        }
        for row in rows
    ]


def revoke_user_session(
    user_id: int, session_id: str, current_session_id: str | None
) -> dict[str, Any]:
    if session_id == current_session_id:
        raise BusinessException(
            "当前会话请使用退出登录结束",
            result_code=ResultCode.BAD_REQUEST,
        )
    session = db.session.get(UserSession, session_id)
    if session is None or session.user_id != user_id:
        raise BusinessException("会话不存在", result_code=ResultCode.NOT_FOUND)
    if session.revoked_at is None:
        session.revoked_at = _now()
        session.revoke_reason = "user_revoked"
        user = user_repository.get(user_id)
        _event("SESSION_REVOKED", user=user, detail="user_revoked")
        db.session.commit()
    return {"session_id": session.session_id, "revoked": True}
