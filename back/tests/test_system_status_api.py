from __future__ import annotations

from app.extensions import db
from app.models import User
from app.security.passwords import hash_password


def _headers(client) -> dict[str, str]:
    user = User(
        username="status-user",
        password=hash_password("admin123"),
        enabled=True,
    )
    db.session.add(user)
    db.session.flush()
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "status-user", "password": "admin123"},
    ).get_json()["data"]
    return {"Authorization": f"Bearer {login['token']}"}


def test_system_status_requires_authentication(client) -> None:
    response = client.get("/api/v1/system/status")
    assert response.status_code == 401


def test_system_status_reports_real_non_sensitive_test_capabilities(
    client, monkeypatch
) -> None:
    for name in (
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        "FILE_STORAGE_PATH",
        "FILE_STORAGE_BUCKET",
        "OBJECT_STORAGE_BUCKET",
        "BACKUP_TARGET",
        "BACKUP_COMMAND",
        "BACKUP_STORAGE_PATH",
    ):
        monkeypatch.delenv(name, raising=False)

    response = client.get("/api/v1/system/status", headers=_headers(client))
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["application"]["healthy"] is True
    assert data["database"] == {
        "connected": True,
        "dialect": "sqlite",
        "label": "SQLite",
    }
    assert data["feishu"]["mode"] == "LOCAL_SIMULATION"
    assert data["file_storage"]["configured"] is False
    assert data["backup"]["configured"] is False
    serialized = str(data).lower()
    assert "secret" not in serialized
    assert "database_uri" not in serialized
    assert "sqlite://" not in serialized
