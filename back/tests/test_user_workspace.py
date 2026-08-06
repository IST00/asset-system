from __future__ import annotations

from app.extensions import db
from app.models import User, UserPreference, UserSession
from app.security.passwords import hash_password

_PASSWORD = "Workspace-Password-2026!"


def _login(client, username: str) -> tuple[User, dict[str, str]]:
    user = User(username=username, password=hash_password(_PASSWORD), enabled=True)
    db.session.add(user)
    db.session.commit()
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": _PASSWORD},
        headers={"User-Agent": "Workspace Browser/1.0"},
        environ_base={"REMOTE_ADDR": "10.20.30.40"},
    )
    token = response.get_json()["data"]["token"]
    return user, {"Authorization": f"Bearer {token}"}


def test_preferences_have_defaults_and_persist_valid_updates(client) -> None:
    user, headers = _login(client, "preference-user")

    defaults = client.get("/api/v1/users/me/preferences", headers=headers).get_json()[
        "data"
    ]
    assert defaults["asset_list_page_size"] == 50
    assert defaults["task_notice"] is True
    assert "purchase_amount" not in defaults["asset_list_columns"]

    response = client.post(
        "/api/v1/users/me/preferences/update",
        headers=headers,
        json={
            "asset_list_columns": ["asset_code", "asset_name", "purchase_amount"],
            "asset_list_page_size": 100,
            "task_notice": False,
            "approval_notice": True,
            "weekly_digest": True,
        },
    )
    payload = response.get_json()["data"]
    assert payload["asset_list_columns"] == [
        "asset_code",
        "asset_name",
        "purchase_amount",
    ]
    assert payload["asset_list_page_size"] == 100
    assert payload["weekly_digest"] is True

    preference = db.session.get(UserPreference, user.id)
    assert preference is not None
    assert preference.task_notice is False


def test_preferences_reject_unknown_columns(client) -> None:
    _, headers = _login(client, "invalid-preference-user")
    response = client.post(
        "/api/v1/users/me/preferences/update",
        headers=headers,
        json={"asset_list_columns": ["asset_code", "private_secret"]},
    )
    assert response.get_json()["code"] == 400


def test_session_list_marks_current_and_can_revoke_another_session(client) -> None:
    user, first_headers = _login(client, "multi-session-user")
    second = client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": _PASSWORD},
        headers={"User-Agent": "Second Browser/2.0"},
        environ_base={"REMOTE_ADDR": "172.16.10.20"},
    ).get_json()["data"]
    second_headers = {"Authorization": f"Bearer {second['token']}"}

    sessions = client.get(
        "/api/v1/users/me/sessions", headers=second_headers
    ).get_json()["data"]
    assert len(sessions) == 2
    assert sum(1 for item in sessions if item["current"]) == 1
    assert {item["ip_address"] for item in sessions} == {"10.20.*.*", "172.16.*.*"}
    other = next(item for item in sessions if not item["current"])

    revoked = client.post(
        f"/api/v1/users/me/sessions/{other['session_id']}/revoke",
        headers=second_headers,
    ).get_json()
    assert revoked["code"] == 200
    rejected = client.get("/api/v1/users/me", headers=first_headers)
    assert rejected.status_code == 401
    row = db.session.get(UserSession, other["session_id"])
    assert row is not None and row.revoke_reason == "user_revoked"


def test_current_session_requires_logout_instead_of_remote_revoke(client) -> None:
    _, headers = _login(client, "current-session-user")
    sessions = client.get("/api/v1/users/me/sessions", headers=headers).get_json()[
        "data"
    ]
    current = next(item for item in sessions if item["current"])
    response = client.post(
        f"/api/v1/users/me/sessions/{current['session_id']}/revoke",
        headers=headers,
    )
    assert response.get_json()["code"] == 400
