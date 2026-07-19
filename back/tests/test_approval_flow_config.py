"""Approval-flow configuration, publication, and HTTP contracts."""

from __future__ import annotations

from app.enums import DataScope, FlowStatus
from app.extensions import db
from app.models import (
    ApprovalFlowVersion,
    OperationLog,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.security.passwords import hash_password


_FLOW_PERMISSIONS = (
    "approval:flow:view",
    "approval:flow:edit",
    "approval:flow:publish",
    "approval:flow:disable",
)


def _seed_actor(
    client, username: str, permission_codes: tuple[str, ...]
) -> tuple[User, dict[str, str]]:
    user = User(
        username=username,
        password=hash_password("admin123"),
        enabled=True,
    )
    role = Role(
        code=f"{username.upper()}-ROLE",
        name=f"{username}角色",
        data_scope=DataScope.ALL.value,
    )
    db.session.add_all([user, role])
    db.session.flush()
    permissions = []
    for code in permission_codes:
        permission = db.session.query(Permission).filter_by(code=code).one_or_none()
        if permission is None:
            permission = Permission(code=code, name=code, module="approval-flow")
            db.session.add(permission)
            db.session.flush()
        permissions.append(permission)
    db.session.add(UserRole(user_id=user.id, role_id=role.id))
    db.session.add_all(
        [
            RolePermission(role_id=role.id, permission_id=permission.id)
            for permission in permissions
        ]
    )
    db.session.commit()
    body = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "admin123"},
    ).get_json()
    return user, {"Authorization": f"Bearer {body['data']['token']}"}


def _draft_payload(user_id: int, role_id: int | None = None) -> dict:
    layers = [
        {
            "level_no": 1,
            "sign_mode": "OR_SIGN",
            "allow_self_approval": True,
            "assignees": [
                {"assignee_type": "USER", "assignee_id": user_id},
            ],
        }
    ]
    if role_id is not None:
        layers.append(
            {
                "level_no": 2,
                "sign_mode": "AND_SIGN",
                "allow_self_approval": False,
                "assignees": [
                    {"assignee_type": "ROLE", "assignee_id": role_id},
                ],
            }
        )
    return {"layers": layers}


def _data(response) -> dict | list:
    body = response.get_json()
    assert response.status_code == 200
    assert body["code"] == 200
    return body["data"]


def test_flow_configuration_publish_disable_restore_and_immutability(client) -> None:
    actor, headers = _seed_actor(client, "flow-admin", _FLOW_PERMISSIONS)
    approver_role = Role(
        code="FLOW-APPROVER",
        name="流程审批人",
        data_scope=DataScope.ALL.value,
        enabled=True,
    )
    db.session.add(approver_role)
    db.session.commit()

    created_response = client.post(
        "/api/v1/approval-flows",
        headers=headers,
        json={"operation_type": "TRANSFER", "name": "调拨审批"},
    )
    created = _data(created_response)
    assert isinstance(created, dict)
    assert created["status"] == FlowStatus.DRAFT.value

    draft_response = client.post(
        f"/api/v1/approval-flows/{created['id']}/drafts",
        headers=headers,
        json=_draft_payload(actor.id, approver_role.id),
    )
    draft = _data(draft_response)
    assert isinstance(draft, dict)
    assert draft["version_no"] == 1
    assert [layer["level_no"] for layer in draft["layers"]] == [1, 2]

    published_response = client.post(
        f"/api/v1/approval-flow-versions/{draft['id']}/publish",
        headers=headers,
        json={"confirmed": True},
    )
    published = _data(published_response)
    assert isinstance(published, dict)
    assert published["status"] == FlowStatus.PUBLISHED.value
    assert (
        db.session.query(OperationLog).filter_by(action="APPROVAL_FLOW_PUBLISH").count()
        == 1
    )

    next_draft = _data(
        client.post(
            f"/api/v1/approval-flows/{created['id']}/drafts",
            headers=headers,
            json=_draft_payload(actor.id),
        )
    )
    assert isinstance(next_draft, dict)
    assert next_draft["version_no"] == 2
    persisted_first = db.session.get(ApprovalFlowVersion, draft["id"])
    assert persisted_first is not None
    assert persisted_first.status == FlowStatus.PUBLISHED.value
    assert len(persisted_first.layers) == 2

    detail = _data(
        client.get(f"/api/v1/approval-flows/{created['id']}", headers=headers)
    )
    assert isinstance(detail, dict)
    assert [version["version_no"] for version in detail["versions"]] == [2, 1]
    listed = _data(client.get("/api/v1/approval-flows", headers=headers))
    assert isinstance(listed, list)
    assert [item["operation_type"] for item in listed] == ["TRANSFER"]

    disabled = _data(
        client.post(
            f"/api/v1/approval-flows/{created['id']}/disable",
            headers=headers,
            json={"confirmed": True},
        )
    )
    assert isinstance(disabled, dict)
    assert disabled["status"] == FlowStatus.DISABLED.value
    restored = _data(
        client.post(
            f"/api/v1/approval-flows/{created['id']}/enable",
            headers=headers,
            json={"confirmed": True},
        )
    )
    assert isinstance(restored, dict)
    assert restored["status"] == FlowStatus.PUBLISHED.value
    assert db.session.query(OperationLog).count() == 3


def test_flow_high_risk_actions_require_explicit_confirmation(client) -> None:
    actor, headers = _seed_actor(client, "flow-confirm", _FLOW_PERMISSIONS)
    created = _data(
        client.post(
            "/api/v1/approval-flows",
            headers=headers,
            json={"operation_type": "CONFIRM_TEST", "name": "确认测试"},
        )
    )
    assert isinstance(created, dict)
    draft = _data(
        client.post(
            f"/api/v1/approval-flows/{created['id']}/drafts",
            headers=headers,
            json=_draft_payload(actor.id),
        )
    )
    assert isinstance(draft, dict)
    for path in (
        f"/api/v1/approval-flow-versions/{draft['id']}/publish",
        f"/api/v1/approval-flows/{created['id']}/disable",
    ):
        response = client.post(path, headers=headers, json={"confirmed": False})
        assert response.status_code == 400


def test_flow_configuration_rejects_invalid_graphs_and_disabled_assignees(
    client,
) -> None:
    actor, headers = _seed_actor(client, "flow-validator", _FLOW_PERMISSIONS)
    disabled_user = User(username="disabled-flow-user", password="x", enabled=False)
    disabled_role = Role(
        code="DISABLED-FLOW-ROLE",
        name="停用审批角色",
        data_scope=DataScope.ALL.value,
        enabled=False,
    )
    db.session.add_all([disabled_user, disabled_role])
    db.session.commit()
    created = _data(
        client.post(
            "/api/v1/approval-flows",
            headers=headers,
            json={"operation_type": "REPAIR", "name": "维修审批"},
        )
    )
    assert isinstance(created, dict)

    non_contiguous = _draft_payload(actor.id)
    non_contiguous["layers"][0]["level_no"] = 2
    body = client.post(
        f"/api/v1/approval-flows/{created['id']}/drafts",
        headers=headers,
        json=non_contiguous,
    ).get_json()
    assert body["code"] == 1000
    assert "连续" in body["message"]

    empty = _draft_payload(actor.id)
    empty["layers"][0]["assignees"] = []
    response = client.post(
        f"/api/v1/approval-flows/{created['id']}/drafts",
        headers=headers,
        json=empty,
    )
    assert response.status_code == 400

    invalid_sign = _draft_payload(actor.id)
    invalid_sign["layers"][0]["sign_mode"] = "SCRIPT"
    response = client.post(
        f"/api/v1/approval-flows/{created['id']}/drafts",
        headers=headers,
        json=invalid_sign,
    )
    assert response.status_code == 400

    for assignee_type, assignee_id in (
        ("USER", disabled_user.id),
        ("ROLE", disabled_role.id),
    ):
        payload = _draft_payload(actor.id)
        payload["layers"][0]["assignees"] = [
            {"assignee_type": assignee_type, "assignee_id": assignee_id}
        ]
        body = client.post(
            f"/api/v1/approval-flows/{created['id']}/drafts",
            headers=headers,
            json=payload,
        ).get_json()
        assert body["code"] == 1000
        assert "停用" in body["message"]


def test_flow_definition_is_unique_and_permissions_are_enforced(client) -> None:
    _, admin_headers = _seed_actor(client, "flow-owner", _FLOW_PERMISSIONS)
    _, viewer_headers = _seed_actor(client, "flow-viewer", ("approval:flow:view",))
    payload = {"operation_type": "SCRAP", "name": "报废审批"}
    assert (
        client.post(
            "/api/v1/approval-flows", headers=admin_headers, json=payload
        ).get_json()["code"]
        == 200
    )

    duplicate = client.post(
        "/api/v1/approval-flows", headers=admin_headers, json=payload
    ).get_json()
    assert duplicate["code"] == 1000
    assert "已存在" in duplicate["message"]

    forbidden = client.post(
        "/api/v1/approval-flows",
        headers=viewer_headers,
        json={"operation_type": "INVENTORY", "name": "盘点审批"},
    ).get_json()
    assert forbidden["code"] == 403
    assert (
        client.get("/api/v1/approval-flows", headers=viewer_headers).get_json()["code"]
        == 200
    )


def test_approval_flow_routes_are_get_and_post_only(app) -> None:
    routes: dict[str, set[str]] = {}
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith("/api/v1/approval-flow"):
            routes.setdefault(rule.rule, set()).update(
                set(rule.methods) - {"HEAD", "OPTIONS"}
            )

    assert routes == {
        "/api/v1/approval-flows": {"GET", "POST"},
        "/api/v1/approval-flows/<int:flow_id>": {"GET"},
        "/api/v1/approval-flows/<int:flow_id>/drafts": {"POST"},
        "/api/v1/approval-flow-versions/<int:version_id>/publish": {"POST"},
        "/api/v1/approval-flows/<int:flow_id>/disable": {"POST"},
        "/api/v1/approval-flows/<int:flow_id>/enable": {"POST"},
    }
