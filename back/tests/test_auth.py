from __future__ import annotations

from app.enums import DataScope
from app.extensions import db
from app.models import Permission, Role, RolePermission, User, UserRole
from app.security.passwords import hash_password


def _create_login_user(username: str = "admin", password: str = "admin123") -> User:
    user = User(
        username=username,
        password=hash_password(password),
        nickname="Admin",
        enabled=True,
    )
    role = Role(
        code=f"{username.upper()}_ROLE", name="管理员", data_scope=DataScope.ALL.value
    )
    permission = Permission(code="asset:view", name="查看资产", module="asset")
    db.session.add_all([user, role, permission])
    db.session.flush()
    db.session.add_all(
        [
            UserRole(user_id=user.id, role_id=role.id),
            RolePermission(role_id=role.id, permission_id=permission.id),
        ]
    )
    db.session.flush()
    return user


def test_login_and_current_user_use_v1_api(client) -> None:
    user = _create_login_user()
    user_id = user.id

    response = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["code"] == 200
    assert body["data"]["user"]["id"] == user_id
    assert body["data"]["user"]["roles"] == ["ADMIN_ROLE"]
    assert body["data"]["user"]["permissions"] == ["asset:view"]

    current = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {body['data']['token']}"},
    )
    assert current.status_code == 200
    assert current.get_json()["data"]["id"] == user_id


def test_public_registration_is_not_available(client) -> None:
    response = client.post(
        "/api/v1/auth/register", json={"username": "new-user", "password": "test1234"}
    )
    assert response.status_code == 404


def test_login_wrong_password(client) -> None:
    _create_login_user(username="wrongpw")

    response = client.post(
        "/api/v1/auth/login", json={"username": "wrongpw", "password": "badpassword"}
    )
    assert response.get_json()["code"] == 401


def test_login_validation_error(client) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"username": "ab", "password": "12345"}
    )
    assert response.status_code == 400


def test_current_user_can_change_password_and_change_is_audited(client) -> None:
    from app.models import OperationLog

    _create_login_user(username="password-user", password="old-password")
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "password-user", "password": "old-password"},
    ).get_json()["data"]

    updated = client.post(
        "/api/v1/users/me/password/update",
        headers={"Authorization": f"Bearer {login['token']}"},
        json={
            "current_password": "old-password",
            "new_password": "New-Password-2026!",
        },
    )
    assert updated.status_code == 200
    assert updated.get_json()["code"] == 200

    old_login = client.post(
        "/api/v1/auth/login",
        json={"username": "password-user", "password": "old-password"},
    )
    assert old_login.get_json()["code"] == 401

    new_login = client.post(
        "/api/v1/auth/login",
        json={"username": "password-user", "password": "New-Password-2026!"},
    )
    assert new_login.get_json()["code"] == 200
    audit = db.session.query(OperationLog).filter_by(action="PASSWORD_UPDATE").one()
    assert audit.reason == "用户主动修改密码"
    assert audit.before_data == {"password_changed": False}
    assert audit.after_data == {"password_changed": True}


def test_change_password_rejects_wrong_current_or_weak_new_password(client) -> None:
    _create_login_user(username="password-policy", password="old-password")
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "password-policy", "password": "old-password"},
    ).get_json()["data"]
    headers = {"Authorization": f"Bearer {login['token']}"}

    wrong_current = client.post(
        "/api/v1/users/me/password/update",
        headers=headers,
        json={
            "current_password": "wrong-password",
            "new_password": "New-Password-2026!",
        },
    )
    assert wrong_current.get_json()["code"] == 400

    weak = client.post(
        "/api/v1/users/me/password/update",
        headers=headers,
        json={"current_password": "old-password", "new_password": "weakpassword12"},
    )
    assert weak.get_json()["code"] == 400
