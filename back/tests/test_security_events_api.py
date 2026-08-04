from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.enums import DataScope
from app.extensions import db
from app.models import (
    Permission,
    RateLimitBucket,
    Role,
    RolePermission,
    SecurityEventLog,
    User,
    UserRole,
    UserSession,
)
from app.security.passwords import hash_password
from app.services import security_service


def _audit_user(username: str = "security-auditor") -> tuple[User, str]:
    user = User(
        username=username,
        password=hash_password("Audit-Password-2026!"),
        enabled=True,
    )
    role = Role(
        code=f"AUDITOR_{username}",
        name="安全审计员",
        data_scope=DataScope.ALL.value,
    )
    permission = Permission(code="audit:view", name="查看审计日志", module="audit")
    db.session.add_all([user, role, permission])
    db.session.flush()
    db.session.add_all(
        [
            UserRole(user_id=user.id, role_id=role.id),
            RolePermission(role_id=role.id, permission_id=permission.id),
        ]
    )
    db.session.commit()
    return user, "Audit-Password-2026!"


def _headers(client, user: User, password: str) -> dict[str, str]:
    token = client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": password},
    ).get_json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def test_security_event_page_requires_audit_permission_and_filters(client, app) -> None:
    app.config["RATE_LIMIT_ENABLED"] = False
    user, password = _audit_user()
    db.session.add_all(
        [
            SecurityEventLog(
                event_type="LOGIN_FAILURE",
                username="alice",
                ip_address="10.0.0.8",
                detail="invalid_credentials",
            ),
            SecurityEventLog(
                event_type="PASSWORD_CHANGED",
                user_id=user.id,
                username=user.username,
                detail="self_service",
            ),
        ]
    )
    db.session.commit()

    response = client.get(
        "/api/v1/security-events?event_type=LOGIN_FAILURE&keyword=alice",
        headers=_headers(client, user, password),
    )
    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["total"] == 1
    assert payload["items"][0]["event_type"] == "LOGIN_FAILURE"
    assert payload["items"][0]["username"] == "alice"
    assert payload["page"] == 0


def test_security_cleanup_applies_retention_windows(app) -> None:
    now = datetime.now(tz=timezone.utc)
    user, _ = _audit_user("cleanup-auditor")
    db.session.add_all(
        [
            SecurityEventLog(
                event_type="LOGIN_FAILURE",
                username="old",
                created_at=now - timedelta(days=366),
            ),
            SecurityEventLog(
                event_type="LOGIN_SUCCESS",
                username="recent",
                created_at=now - timedelta(days=10),
            ),
            RateLimitBucket(
                scope="login_ip",
                subject="127.0.0.1",
                window_start=now - timedelta(minutes=10),
                count=1,
                expires_at=now - timedelta(minutes=8),
            ),
            UserSession(
                session_id="00000000-0000-0000-0000-000000000001",
                user_id=user.id,
                issued_at=now - timedelta(days=60),
                last_seen_at=now - timedelta(days=60),
                expires_at=now - timedelta(days=40),
                revoked_at=now - timedelta(days=40),
            ),
        ]
    )
    db.session.commit()

    result = security_service.cleanup_security_data(now=now)

    assert result == {
        "security_events": 1,
        "rate_limit_buckets": 1,
        "user_sessions": 1,
    }
    assert db.session.scalar(db.select(db.func.count(SecurityEventLog.id))) == 1
