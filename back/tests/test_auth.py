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
