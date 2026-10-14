"""Regression coverage for formal Feishu login and callback behavior."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.services import feishu_service
from sqlalchemy import select


@pytest.fixture
def native_config(app: Any) -> None:
    app.config.update(
        FEISHU_INTEGRATION_ENABLED=True,
        FEISHU_APP_ID="cli-test",
        FEISHU_APP_SECRET="secret",
        FEISHU_VERIFICATION_TOKEN="token",
        FEISHU_ENCRYPT_KEY="key",
        FEISHU_REDIRECT_URI="https://asset.example.com/feishu/callback",
    )


def test_authorize_url_uses_frontend_callback(native_config: None) -> None:
    url = feishu_service.authorize_url()
    assert "redirect_uri=https%3A%2F%2Fasset.example.com%2Ffeishu%2Fcallback" in url
    assert "app_id=cli-test" in url


def test_login_url_is_available_on_login_page(client: Any, native_config: None) -> None:
    response = client.get("/api/v1/feishu/login-url")

    assert response.status_code == 200
    assert response.get_json()["data"]["authorize_url"].startswith(
        "https://open.feishu.cn/open-apis/authen/v1/authorize?"
    )


def test_parse_callback_accepts_url_verification(native_config: None) -> None:
    body = b'{"type":"url_verification","challenge":"abc","token":"token"}'
    with pytest.raises(feishu_service.ChallengeRequired) as caught:
        feishu_service.parse_callback(body)
    assert caught.value.args[0] == "abc"


def test_post_preserves_top_level_response_fields(
    native_config: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json
    import urllib.request

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "code": 0,
                    "msg": "ok",
                    "tenant_access_token": "tenant-token",
                    "expire": 1800,
                }
            ).encode("utf-8")

    def fake_urlopen(request: object, timeout: float) -> FakeResponse:
        del request, timeout
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "Request", lambda *args, **kwargs: object())
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    assert feishu_service._post("/example", {}) == {
        "tenant_access_token": "tenant-token",
        "expire": 1800,
    }


def test_post_reports_feishu_business_error_from_http_error(
    native_config: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json
    import urllib.error
    import urllib.request

    payload = json.dumps({"code": 40003, "msg": "invalid app_id"}).encode("utf-8")

    class FakeHTTPError(urllib.error.HTTPError):
        def __init__(self) -> None:
            super().__init__("https://open.feishu.cn", 400, "Bad Request", None, None)

        def read(self) -> bytes:
            return payload

    error = FakeHTTPError()

    def fake_urlopen(request: object, timeout: float) -> Any:
        del request, timeout
        raise error

    monkeypatch.setattr(urllib.request, "Request", lambda *args, **kwargs: object())
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(Exception, match="飞书接口调用失败：invalid app_id"):
        feishu_service._post("/example", {})


def test_post_reports_transport_failure_reason(
    native_config: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket
    import urllib.error
    import urllib.request

    def fake_urlopen(request: object, timeout: float) -> Any:
        del request, timeout
        raise urllib.error.URLError(socket.gaierror("name or service not known"))

    monkeypatch.setattr(urllib.request, "Request", lambda *args, **kwargs: object())
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(Exception, match="无法连接飞书接口，请检查网络"):
        feishu_service._post("/example", {})


def test_verify_callback_signature_uses_official_sha256(
    native_config: None,
) -> None:
    import hashlib

    body = b'{"example":true}'
    signature = hashlib.sha256(b"1700000000nonce" + b"key" + body).hexdigest()
    feishu_service.verify_callback_signature(
        signature=signature,
        timestamp="1700000000",
        nonce="nonce",
        body=body,
    )


def test_exchange_code_fetches_user_info_with_user_access_token(
    native_config: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str | None]] = []

    def fake_post(
        path: str, payload: dict[str, Any], *, token: str | None = None
    ) -> dict[str, Any]:
        calls.append((path, token))
        if path == "/auth/v3/tenant_access_token/internal":
            return {"tenant_access_token": "tenant-token"}
        return {
            "access_token": "user-access-token",
            "token_type": "Bearer",
            "scope": "contact:user.base:readonly",
        }

    def fake_get(path: str, *, token: str) -> dict[str, Any]:
        calls.append((path, token))
        return {"open_id": "ou-test", "name": "Feishu User"}

    monkeypatch.setattr(feishu_service, "_post", fake_post)
    monkeypatch.setattr(feishu_service, "_get", fake_get)

    assert feishu_service.exchange_code("oauth-code") == {
        "access_token": "user-access-token",
        "token_type": "Bearer",
        "scope": "contact:user.base:readonly",
        "open_id": "ou-test",
        "name": "Feishu User",
    }
    assert calls == [
        ("/auth/v3/tenant_access_token/internal", None),
        ("/authen/v1/oidc/access_token", "tenant-token"),
        ("/authen/v1/user_info", "user-access-token"),
    ]


def test_login_by_code_issues_local_session(app: Any, native_config: None) -> None:
    from app.extensions import db
    from app.models import User

    user = User(
        username="feishu-user",
        password="not-loginable",
        nickname="Feishu User",
        feishu_open_id="ou-test",
    )
    db.session.add(user)
    db.session.commit()

    called: dict[str, Any] = {}

    def fake_exchange(code: str) -> dict[str, Any]:
        called["code"] = code
        return {"open_id": "ou-test"}

    original = feishu_service.exchange_code
    feishu_service.exchange_code = fake_exchange
    try:
        result = feishu_service.login_by_code(
            "oauth-code",
            ip_address="127.0.0.1",
            user_agent="pytest",
        )
    finally:
        feishu_service.exchange_code = original

    assert called["code"] == "oauth-code"
    assert result["token"]
    assert result["user"]["id"] == user.id


def test_decrypt_callback_uses_official_aes_envelope(
    app: Any, native_config: None
) -> None:
    import base64
    import hashlib
    import json

    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.padding import PKCS7

    payload = {"type": "url_verification", "challenge": "encrypted-abc"}
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    key = hashlib.sha256(b"key").digest()
    iv = b"0123456789abcdef"
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    padder = PKCS7(128).padder()
    padded = padder.update(raw) + padder.finalize()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    body = json.dumps(
        {"encrypt": base64.b64encode(iv + encrypted).decode("ascii")}
    ).encode("ascii")

    assert feishu_service.decrypt_callback(body) == raw


def test_webhook_returns_url_verification_challenge(
    client: Any, native_config: None
) -> None:
    response = client.post(
        "/api/v1/feishu/webhook",
        json={"type": "url_verification", "challenge": "abc", "token": "token"},
    )
    assert response.status_code == 200
    assert response.get_json() == {"challenge": "abc"}


def test_webhook_processes_plaintext_approval_event(
    app: Any,
    client: Any,
    native_config: None,
) -> None:
    from app.enums import ApprovalStatus, ExecutionStatus
    from app.extensions import db
    from app.services import approval_provider_service
    from app.models import OperationRequest, User

    user = User(username="approval-user", password="x", enabled=True)
    db.session.add(user)
    db.session.flush()
    operation = OperationRequest(
        request_no="WEBHOOK-REQUEST",
        operation_type="TRANSFER",
        applicant_id=user.id,
        approval_status=ApprovalStatus.PENDING.value,
        execution_status=ExecutionStatus.NOT_STARTED.value,
        external_instance_id="instance-1",
    )
    db.session.add(operation)
    db.session.commit()

    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_callback(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return operation

    original = approval_provider_service.handle_callback
    approval_provider_service.handle_callback = fake_callback
    try:
        response = client.post(
            "/api/v1/feishu/webhook",
            json={
                "header": {
                    "event_id": "event-1",
                    "event_type": "approval",
                    "token": "token",
                },
                "event": {"instance_code": "instance-1", "task_list": []},
            },
        )
    finally:
        approval_provider_service.handle_callback = original

    assert response.status_code == 200
    assert response.get_json()["data"] == {
        "event_id": "event-1",
        "ignored": "no_task",
    }
    assert calls == []


def test_webhook_decrypts_encrypted_approval_event(
    app: Any,
    client: Any,
    native_config: None,
) -> None:
    import base64
    import hashlib
    import json

    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.padding import PKCS7

    from app.extensions import db
    from app.services import approval_provider_service
    from app.models import OperationRequest, User

    user = User(username="encrypted-user", password="x", enabled=True)
    db.session.add(user)
    db.session.flush()
    operation = OperationRequest(
        request_no="ENCRYPTED-REQUEST",
        operation_type="TRANSFER",
        applicant_id=user.id,
        approval_status="PENDING",
        execution_status="NOT_STARTED",
        external_instance_id="encrypted-instance",
    )
    db.session.add(operation)
    db.session.commit()

    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_callback(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return operation

    payload = {
        "header": {
            "event_id": "encrypted-event",
            "event_type": "approval",
            "token": "token",
        },
        "event": {
            "instance_code": "encrypted-instance",
            "task_list": [],
        },
    }
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    key = hashlib.sha256(b"key").digest()
    iv = b"0123456789abcdef"
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    padder = PKCS7(128).padder()
    padded = padder.update(raw) + padder.finalize()
    encrypted = encryptor.update(padded) + encryptor.finalize()

    original = approval_provider_service.handle_callback
    approval_provider_service.handle_callback = fake_callback
    try:
        response = client.post(
            "/api/v1/feishu/webhook",
            json={"encrypt": base64.b64encode(iv + encrypted).decode("ascii")},
        )
    finally:
        approval_provider_service.handle_callback = original

    assert response.status_code == 200
    assert response.get_json()["data"] == {
        "event_id": "encrypted-event",
        "ignored": "no_task",
    }
    assert calls == []


def test_sync_approval_operations_reconciles_missed_remote_decision(
    app: Any,
    native_config: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.enums import ApprovalStatus, ExecutionStatus
    from app.extensions import db
    from app.models import ExternalApprovalEvent, OperationRequest, User
    from app.services import feishu_service

    user = User(username="approval-sync-user", password="x", enabled=True)
    db.session.add(user)
    db.session.flush()
    operation = OperationRequest(
        request_no="APPROVAL-SYNC-REQUEST",
        operation_type="PERSONAL_RETURN",
        applicant_id=user.id,
        approval_channel="FEISHU",
        approval_status=ApprovalStatus.PENDING.value,
        execution_status=ExecutionStatus.NOT_STARTED.value,
        external_instance_id="approval-sync-instance",
    )
    db.session.add(operation)
    db.session.commit()

    monkeypatch.setattr(feishu_service, "tenant_access_token", lambda: "tenant-token")
    monkeypatch.setattr(
        feishu_service,
        "_get",
        lambda path, *, token: {
            "status": "APPROVED",
            "task_list": [{"end_time": "1791782591254"}],
        },
    )

    result = feishu_service.sync_approval_operations()

    db.session.expire_all()
    persisted = db.session.get(OperationRequest, operation.id)
    event = db.session.query(ExternalApprovalEvent).one()
    assert result == {"synced": 1}
    assert persisted is not None and persisted.approval_status == "APPROVED"
    assert persisted.approved_at is not None
    assert event.external_event_id == (
        "SYNC-FEISHU-approval-sync-instance-APPROVED-1791782591254"
    )
    assert feishu_service.sync_approval_operations() == {"synced": 0}


def test_sync_all_requires_organization_and_user_management_permissions(
    app: Any,
    client: Any,
    native_config: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.enums import DataScope
    from app.extensions import db
    from app.models import Permission, Role, RolePermission, User, UserRole
    from app.security.passwords import hash_password

    actor = User(
        username="feishu-sync-admin",
        password=hash_password("admin123"),
        enabled=True,
    )
    role = Role(
        code="FEISHU_SYNC_ADMIN",
        name="飞书同步管理员",
        data_scope=DataScope.ALL.value,
    )
    permissions = [
        Permission(code="organization:manage", name="管理组织", module="organization"),
        Permission(code="user:manage", name="管理用户", module="system"),
    ]
    db.session.add_all([actor, role, *permissions])
    db.session.flush()
    db.session.add(UserRole(user_id=actor.id, role_id=role.id))
    db.session.add_all(
        [RolePermission(role_id=role.id, permission_id=item.id) for item in permissions]
    )
    db.session.commit()
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "feishu-sync-admin", "password": "admin123"},
    )
    headers = {"Authorization": f"Bearer {login.get_json()['data']['token']}"}

    monkeypatch.setattr(
        feishu_service,
        "sync_all",
        lambda: {"departments": 1, "users": 1},
    )
    response = client.post("/api/v1/feishu/sync", headers=headers)

    assert response.status_code == 200
    assert response.get_json()["data"] == {"departments": 1, "users": 1}


def test_contact_pagination_uses_feishu_page_size_limit(
    app: Any,
    native_config: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queries: list[str] = []

    def fake_get(path: str, *, token: str) -> dict[str, Any]:
        del token
        query = path.split("?", 1)[1]
        queries.append(query)
        return {"items": [], "has_more": False}

    monkeypatch.setattr(feishu_service, "_get", fake_get)
    monkeypatch.setattr(
        feishu_service,
        "tenant_access_token",
        lambda: "tenant-token",
    )

    feishu_service.sync_organization_tree()
    feishu_service.sync_users()

    assert queries == [
        "page_size=50",
        "page_size=50&user_id_type=open_id",
    ]


def test_sync_users_assigns_default_user_role_to_created_users(
    app: Any,
    native_config: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.enums import DataScope
    from app.extensions import db
    from app.models import Role, User, UserRole

    role = Role(
        code="USER",
        name="普通员工",
        data_scope=DataScope.SELF.value,
        built_in=True,
        enabled=True,
    )
    db.session.add(role)
    db.session.commit()
    open_id = "ou-default-role"

    def fake_get(path: str, *, token: str) -> dict[str, Any]:
        del token
        assert path.startswith("/contact/v3/users?")
        return {
            "items": [
                {
                    "open_id": open_id,
                    "name": "默认角色用户",
                    "active": True,
                    "department_ids": [],
                }
            ],
            "has_more": False,
        }

    monkeypatch.setattr(feishu_service, "_get", fake_get)
    monkeypatch.setattr(
        feishu_service,
        "tenant_access_token",
        lambda: "tenant-token",
    )

    result = feishu_service.sync_users()

    assert result == {"users": 1}
    user = db.session.scalar(select(User).where(User.feishu_open_id == open_id))
    assert user is not None
    assert (
        db.session.scalar(
            select(UserRole).where(
                UserRole.user_id == user.id,
                UserRole.role_id == role.id,
            )
        )
        is not None
    )


def test_sync_users_assigns_department_when_feishu_returns_multiple_departments(
    app: Any,
    native_config: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.extensions import db
    from app.models import Organization, User

    department = Organization(
        code="FEISHU-multiple-department",
        name="多部门",
        feishu_department_id="od-multiple",
    )
    db.session.add(department)
    db.session.commit()
    open_id = "ou-multiple-department"

    def fake_get(path: str, *, token: str) -> dict[str, Any]:
        del token
        if path.startswith("/contact/v3/users?"):
            return {
                "items": [
                    {
                        "open_id": open_id,
                        "name": "多部门用户",
                        "active": True,
                        "department_ids": ["od-unknown", "od-multiple"],
                    }
                ],
                "has_more": False,
            }
        raise AssertionError(path)

    monkeypatch.setattr(feishu_service, "_get", fake_get)
    monkeypatch.setattr(
        feishu_service,
        "tenant_access_token",
        lambda: "tenant-token",
    )

    result = feishu_service.sync_users()

    assert result == {"users": 1}
    user = db.session.scalar(select(User).where(User.feishu_open_id == open_id))
    assert user is not None
    assert user.organization_id == department.id


def test_sync_users_assigns_existing_feishu_root_department_when_user_has_none(
    app: Any,
    native_config: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.extensions import db
    from app.models import Organization, User

    root = Organization(
        code="FEISHU-default-root",
        name="默认根部门",
        feishu_department_id="od-default-root",
    )
    child = Organization(
        code="FEISHU-default-child",
        name="默认子部门",
        parent_id=root.id,
        feishu_department_id="od-default-child",
    )
    user = User(
        username="feishu-no-department",
        password="x",
        enabled=True,
        feishu_open_id="ou-no-department",
    )
    db.session.add_all([root, child, user])
    db.session.commit()

    def fake_get(path: str, *, token: str) -> dict[str, Any]:
        del token
        assert path.startswith("/contact/v3/users?")
        return {
            "items": [
                {
                    "open_id": "ou-no-department",
                    "name": "无部门用户",
                    "active": True,
                    "department_ids": [],
                }
            ],
            "has_more": False,
        }

    monkeypatch.setattr(feishu_service, "_get", fake_get)
    monkeypatch.setattr(
        feishu_service,
        "tenant_access_token",
        lambda: "tenant-token",
    )

    result = feishu_service.sync_users()

    assert result == {"users": 1}
    assert user.organization_id == root.id


def test_sync_users_disables_missing_feishu_users(
    app: Any,
    native_config: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.extensions import db
    from app.models import User

    remaining = User(
        username="feishu-remaining",
        password="x",
        enabled=True,
        feishu_open_id="ou-remaining",
    )
    missing = User(
        username="feishu-missing",
        password="x",
        enabled=True,
        feishu_open_id="ou-missing",
    )
    local = User(username="local-user", password="x", enabled=True)
    db.session.add_all([remaining, missing, local])
    db.session.commit()

    def fake_get(path: str, *, token: str) -> dict[str, Any]:
        del token
        assert path.startswith("/contact/v3/users?")
        return {
            "items": [
                {
                    "open_id": "ou-remaining",
                    "name": "保留用户",
                    "active": True,
                    "department_ids": [],
                }
            ],
            "has_more": False,
        }

    monkeypatch.setattr(feishu_service, "_get", fake_get)
    monkeypatch.setattr(
        feishu_service,
        "tenant_access_token",
        lambda: "tenant-token",
    )

    result = feishu_service.sync_users()

    assert result == {"users": 1}
    assert remaining.enabled is True
    assert remaining.feishu_sync_status == "SYNCED"
    assert missing.enabled is False
    assert missing.feishu_sync_status == "MISSING"
    assert local.enabled is True
    assert local.feishu_sync_status == "UNSYNCED"


def test_formal_feishu_approval_submit_matches_real_approval_contract(
    app: Any,
    native_config: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.enums import ApprovalChannel, ApprovalStatus, ExecutionStatus
    from app.extensions import db
    from app.models import OperationRequest, User
    from app.operations.providers import FormalFeishuApprovalProvider

    app.config.update(FEISHU_APPROVAL_CODE="approval-code")
    user = User(
        username="formal-approval-user",
        password="x",
        nickname="审批用户",
        feishu_user_id="user-id",
        feishu_open_id="open-id",
    )
    db.session.add(user)
    db.session.flush()
    operation = OperationRequest(
        request_no="FORMAL-APPROVAL-REQUEST",
        operation_type="PERSONAL_USE",
        applicant_id=user.id,
        approval_channel=ApprovalChannel.FEISHU.value,
        approval_status=ApprovalStatus.PENDING.value,
        execution_status=ExecutionStatus.NOT_STARTED.value,
    )
    db.session.add(operation)
    db.session.commit()

    calls: list[tuple[str, dict[str, Any], str | None]] = []

    def fake_post(
        path: str, payload: dict[str, Any], *, token: str | None = None
    ) -> dict[str, Any]:
        calls.append((path, payload, token))
        return {"instance_code": "instance-code"}

    monkeypatch.setattr(feishu_service, "_post", fake_post)
    monkeypatch.setattr(
        feishu_service,
        "tenant_access_token",
        lambda: "tenant-token",
    )

    result = FormalFeishuApprovalProvider().submit(operation.id)

    assert result == "instance-code"
    assert len(calls) == 1
    path, payload, token = calls[0]
    assert path == "/approval/v4/instances?user_id_type=user_id"
    assert token == "tenant-token"
    assert payload["approval_code"] == "approval-code"
    assert payload["user_id"] == "user-id"
    assert payload["form"] == json.dumps(
        FormalFeishuApprovalProvider()._form(operation),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def test_login_fallback_creates_department_user_with_default_role(
    app: Any,
    native_config: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.enums import DataScope
    from app.extensions import db
    from app.models import Organization, Role, User, UserRole

    role = Role(
        code="USER",
        name="普通员工",
        data_scope=DataScope.SELF.value,
        built_in=True,
    )
    department = Organization(
        code="FEISHU-login-fallback",
        name="登录兜底部门",
        feishu_department_id="od-login-fallback",
    )
    db.session.add_all([role, department])
    db.session.commit()

    def fake_sync_departments() -> dict[str, int]:
        return {"departments": 1}

    def fake_current_user(open_id: str) -> dict[str, Any]:
        assert open_id == "ou-login-fallback"
        return {
            "open_id": open_id,
            "user_id": "login-fallback-user-id",
            "name": "登录兜底员工",
            "active": True,
            "department_ids": ["od-login-fallback"],
        }

    monkeypatch.setattr(feishu_service, "sync_organization_tree", fake_sync_departments)
    monkeypatch.setattr(feishu_service, "current_user", fake_current_user)
    monkeypatch.setattr(
        feishu_service,
        "exchange_code",
        lambda _code: {"open_id": "ou-login-fallback"},
    )

    result = feishu_service.login_by_code(
        "oauth-code",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    user = db.session.scalar(
        select(User).where(User.feishu_open_id == "ou-login-fallback")
    )
    assert user is not None
    assert user.organization_id == department.id
    assert user.feishu_user_id == "login-fallback-user-id"
    assert user.feishu_sync_status == "SYNCED"
    assert (
        db.session.scalar(
            select(UserRole).where(
                UserRole.user_id == user.id, UserRole.role_id == role.id
            )
        )
        is not None
    )
    assert result["user"]["id"] == user.id


def test_scheduled_directory_task_is_disabled_by_config(
    app: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.tasks.feishu_contact_sync import feishu_sync_directory

    def fail_sync() -> dict[str, int]:
        raise AssertionError("sync must not run when disabled")

    monkeypatch.setattr(
        "app.services.feishu_service.sync_all",
        fail_sync,
    )
    app.config.update(FEISHU_DIRECTORY_SYNC_ENABLED=False)

    result = feishu_sync_directory()

    assert result == {"skipped": "disabled"}
