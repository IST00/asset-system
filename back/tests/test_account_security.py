from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from app import create_app
from app.enums import DataScope
from app.extensions import db
from app.models import (
    PasswordHistory,
    RateLimitBucket,
    Permission,
    Role,
    RolePermission,
    SecurityEventLog,
    User,
    UserRole,
    UserSession,
)
from app.security.passwords import hash_password
from config import TestConfig


def _create_user(
    username: str = "secure-user",
    password: str = "Initial-Password-2026!",
    *,
    must_change_password: bool = False,
    role_code: str = "SECURE_ROLE",
) -> User:
    user = User(
        username=username,
        password=hash_password(password),
        nickname="Secure User",
        enabled=True,
        must_change_password=must_change_password,
    )
    role = Role(code=role_code, name="安全角色", data_scope=DataScope.ALL.value)
    permission = Permission(
        code=f"asset:view:{username}", name="查看资产", module="asset"
    )
    db.session.add_all([user, role, permission])
    db.session.flush()
    db.session.add_all(
        [
            UserRole(user_id=user.id, role_id=role.id),
            RolePermission(role_id=role.id, permission_id=permission.id),
        ]
    )
    db.session.commit()
    return user


def _login(client, username: str, password: str, *, remote_addr: str = "127.0.0.1"):
    return client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
        environ_base={"REMOTE_ADDR": remote_addr},
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_five_failures_lock_account_and_security_events_are_written(
    client, app
) -> None:
    app.config["RATE_LIMIT_ENABLED"] = False
    user = _create_user(username="locked-user")

    for _ in range(5):
        response = _login(client, user.username, "wrong-password")
        assert response.get_json()["code"] == 401

    db.session.refresh(user)
    assert user.failed_login_count == 5
    assert user.locked_until is not None
    blocked = _login(client, user.username, "Initial-Password-2026!")
    assert blocked.get_json()["code"] == 423
    event_types = list(
        db.session.scalars(
            db.select(SecurityEventLog.event_type).where(
                SecurityEventLog.user_id == user.id
            )
        ).all()
    )
    assert event_types.count("LOGIN_FAILURE") == 5
    assert "ACCOUNT_LOCKED" in event_types
    assert "LOGIN_BLOCKED" in event_types


def test_expired_lock_is_automatically_cleared(client, app) -> None:
    app.config["RATE_LIMIT_ENABLED"] = False
    user = _create_user(username="unlock-user")
    user.failed_login_count = 5
    user.locked_until = datetime.now(tz=timezone.utc) - timedelta(seconds=1)
    db.session.commit()

    response = _login(client, user.username, "Initial-Password-2026!")
    assert response.get_json()["code"] == 200
    db.session.refresh(user)
    assert user.failed_login_count == 0
    assert user.locked_until is None
    assert (
        db.session.scalar(
            db.select(SecurityEventLog.id).where(
                SecurityEventLog.user_id == user.id,
                SecurityEventLog.event_type == "ACCOUNT_UNLOCKED",
            )
        )
        is not None
    )


def test_first_login_is_restricted_until_password_change(client, app) -> None:
    app.config["RATE_LIMIT_ENABLED"] = False
    user = _create_user(username="first-login", must_change_password=True)
    login = _login(client, user.username, "Initial-Password-2026!").get_json()["data"]
    assert login["user"]["must_change_password"] is True

    denied = client.get("/api/v1/system/status", headers=_auth(login["token"]))
    assert denied.get_json()["code"] == 403
    current = client.get("/api/v1/users/me", headers=_auth(login["token"]))
    assert current.get_json()["data"]["must_change_password"] is True

    changed = client.post(
        "/api/v1/users/me/password/update",
        headers=_auth(login["token"]),
        json={
            "current_password": "Initial-Password-2026!",
            "new_password": "First-Changed-Password-2026!",
        },
    )
    payload = changed.get_json()["data"]
    assert payload["user"]["must_change_password"] is False
    allowed = client.get("/api/v1/system/status", headers=_auth(payload["token"]))
    assert allowed.get_json()["code"] == 200


def test_recent_five_passwords_cannot_be_reused(client, app) -> None:
    app.config["RATE_LIMIT_ENABLED"] = False
    user = _create_user(username="history-user", password="Initial-Password-2026!")
    login = _login(client, user.username, "Initial-Password-2026!").get_json()["data"]
    token = login["token"]
    current = "Initial-Password-2026!"
    passwords = [
        "History-One-Password-2026!",
        "History-Two-Password-2026!",
        "History-Three-Password-2026!",
        "History-Four-Password-2026!",
        "History-Five-Password-2026!",
    ]
    for new_password in passwords:
        changed = client.post(
            "/api/v1/users/me/password/update",
            headers=_auth(token),
            json={"current_password": current, "new_password": new_password},
        ).get_json()["data"]
        token = changed["token"]
        current = new_password

    reused_recent = client.post(
        "/api/v1/users/me/password/update",
        headers=_auth(token),
        json={"current_password": current, "new_password": passwords[0]},
    )
    assert reused_recent.get_json()["code"] == 400

    reused_sixth = client.post(
        "/api/v1/users/me/password/update",
        headers=_auth(token),
        json={
            "current_password": current,
            "new_password": "Initial-Password-2026!",
        },
    )
    assert reused_sixth.get_json()["code"] == 200
    assert db.session.query(PasswordHistory).filter_by(user_id=user.id).count() >= 7


def test_logout_and_idle_timeout_revoke_server_session(client, app) -> None:
    app.config["RATE_LIMIT_ENABLED"] = False
    user = _create_user(username="session-user")
    login = _login(client, user.username, "Initial-Password-2026!").get_json()["data"]
    token = login["token"]

    logged_out = client.post("/api/v1/auth/logout", headers=_auth(token))
    assert logged_out.get_json()["code"] == 200
    rejected = client.get("/api/v1/users/me", headers=_auth(token))
    assert rejected.status_code == 401

    second = _login(client, user.username, "Initial-Password-2026!").get_json()["data"]
    session = db.session.scalar(
        db.select(UserSession).where(
            UserSession.user_id == user.id, UserSession.revoked_at.is_(None)
        )
    )
    assert session is not None
    session.last_seen_at = datetime.now(tz=timezone.utc) - timedelta(hours=13)
    db.session.commit()
    idle_rejected = client.get("/api/v1/users/me", headers=_auth(second["token"]))
    assert idle_rejected.status_code == 401
    db.session.refresh(session)
    assert session.revoke_reason == "idle_timeout"


def test_login_and_user_rate_limits_are_enforced(client, app) -> None:
    app.config["RATE_LIMIT_ENABLED"] = True
    app.config["LOGIN_RATE_LIMIT_PER_MINUTE"] = 2
    for _ in range(2):
        assert _login(client, "missing-user", "bad-password").get_json()["code"] == 401
    limited = _login(client, "missing-user", "bad-password")
    assert limited.get_json()["code"] == 429

    app.config["LOGIN_RATE_LIMIT_PER_MINUTE"] = 10
    app.config["USER_RATE_LIMIT_PER_MINUTE"] = 2
    user = _create_user(username="limited-user")
    login = _login(
        client, user.username, "Initial-Password-2026!", remote_addr="127.0.0.2"
    ).get_json()["data"]
    assert (
        client.get("/api/v1/users/me", headers=_auth(login["token"])).status_code == 200
    )
    assert (
        client.get("/api/v1/users/me", headers=_auth(login["token"])).status_code == 200
    )
    user_limited = client.get("/api/v1/users/me", headers=_auth(login["token"]))
    assert user_limited.get_json()["code"] == 429


def test_parallel_authenticated_requests_share_atomic_rate_bucket(tmp_path) -> None:
    class ConcurrentConfig(TestConfig):
        RATE_LIMIT_ENABLED = True
        USER_RATE_LIMIT_PER_MINUTE = 20

    ConcurrentConfig.SQLALCHEMY_DATABASE_URI = (
        f"sqlite:///{tmp_path / 'concurrent-rate-limit.db'}"
    )
    concurrent_app = create_app(config=ConcurrentConfig)
    with concurrent_app.app_context():
        db.create_all()
        user = _create_user(username="parallel-rate-user")
        user_id = user.id

    with concurrent_app.test_client() as login_client:
        token = _login(
            login_client, "parallel-rate-user", "Initial-Password-2026!"
        ).get_json()["data"]["token"]

    def request_me() -> int:
        with concurrent_app.test_client() as request_client:
            return request_client.get(
                "/api/v1/users/me", headers=_auth(token)
            ).status_code

    with ThreadPoolExecutor(max_workers=6) as executor:
        statuses = list(executor.map(lambda _index: request_me(), range(6)))

    assert statuses == [200] * 6
    with concurrent_app.app_context():
        bucket = db.session.scalar(
            db.select(RateLimitBucket).where(
                RateLimitBucket.scope == "user_api",
                RateLimitBucket.subject == str(user_id),
            )
        )
        assert bucket is not None
        assert bucket.count == 6
        db.session.remove()
        db.drop_all()


def test_all_response_envelopes_include_request_id(client) -> None:
    supplied = "asset-request-20260803"
    success = client.get("/api/v1/hello", headers={"X-Request-ID": supplied})
    assert success.get_json()["request_id"] == supplied
    assert success.headers["X-Request-ID"] == supplied

    missing = client.get("/api/v1/does-not-exist")
    body = missing.get_json()
    assert body["code"] == 404
    assert body["request_id"]
    assert missing.headers["X-Request-ID"] == body["request_id"]
