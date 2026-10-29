"""Independent physical, financial, and warranty information change requests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.enums import AssetDataCompleteness, AssetStatus, DataScope
from app.extensions import db
from app.models import (
    ApprovalTask,
    Asset,
    AssetCategory,
    AssetInformationChangeRequest,
    AssetLifecycleRecord,
    AssetLocation,
    AssetSource,
    OperationRequest,
    OperationRequestAsset,
    Organization,
    Permission,
    Role,
    RolePermission,
    Unit,
    User,
    UserRole,
)
from app.security.passwords import hash_password


def _seed(client) -> tuple[User, Asset, dict[str, str]]:
    organization = Organization(code="CHANGE-ORG", name="信息变更公司")
    unit = Unit(code="CHANGE-UNIT", name="台")
    source = AssetSource(code="CHANGE-SOURCE", name="采购")
    location = AssetLocation(code="CHANGE-LOC", name="旧地点", is_selectable=True)
    actor = User(
        username="change-admin",
        password=hash_password("admin123"),
        enabled=True,
    )
    role = Role(
        code="SUPER_ADMIN",
        name="超级管理员",
        data_scope=DataScope.ALL.value,
    )
    permission_codes = (
        "asset:view",
        "asset:edit",
        "asset:amount:view",
        "operation:request:view",
        "approval:task:view",
        "approval:task:approve",
    )
    permissions = [
        Permission(code=code, name=code, module=code.split(":")[0])
        for code in permission_codes
    ]
    db.session.add_all(
        [organization, unit, source, location, actor, role, *permissions]
    )
    db.session.flush()
    actor.organization_id = organization.id
    category = AssetCategory(
        code="CHANGE-CATEGORY",
        name="电脑",
        service_life_months=36,
        default_unit_id=unit.id,
    )
    db.session.add(category)
    db.session.flush()
    asset = Asset(
        asset_code="CHANGE-ASSET-001",
        asset_name="旧资产名称",
        status=AssetStatus.IDLE.value,
        organization_id=organization.id,
        category_id=category.id,
        unit_id=unit.id,
        original_amount=Decimal("1000.00"),
        purchase_date=date(2026, 1, 1),
        service_life_months=36,
        expected_expiry_date=date(2028, 12, 1),
        manager_id=actor.id,
        source_id=source.id,
        location_id=location.id,
        custom_attributes={},
        data_completeness=AssetDataCompleteness.COMPLETE.value,
    )
    db.session.add(asset)
    db.session.flush()
    db.session.add(UserRole(user_id=actor.id, role_id=role.id))
    db.session.add_all(
        [
            RolePermission(role_id=role.id, permission_id=permission.id)
            for permission in permissions
        ]
    )
    db.session.commit()
    token = client.post(
        "/api/v1/auth/login",
        json={"username": actor.username, "password": "admin123"},
    ).get_json()["data"]["token"]
    return actor, asset, {"Authorization": f"Bearer {token}"}


def _submit(
    client,
    headers: dict[str, str],
    asset: Asset,
    *,
    change_type: str,
    changes: dict,
):
    return client.post(
        "/api/v1/asset-information-change-requests",
        headers=headers,
        json={
            "change_type": change_type,
            "items": [
                {
                    "asset_id": asset.id,
                    "version": asset.version,
                    "changes": changes,
                }
            ],
            "reason": "业务资料核对后申请调整",
        },
    )


def test_internal_change_keeps_snapshots_executes_and_links_lifecycle(client) -> None:
    actor, asset, headers = _seed(client)
    original_version = asset.version

    submitted_response = _submit(
        client,
        headers,
        asset,
        change_type="PHYSICAL",
        changes={"asset_name": "新资产名称", "remark": "已完成实物核对"},
    )

    assert submitted_response.status_code == 200
    submitted = submitted_response.get_json()["data"]
    assert submitted["change_type"] == "PHYSICAL"
    assert submitted["requires_feishu_approval"] is False
    assert submitted["approval_status"] == "PENDING"
    assert submitted["assets"][0]["before_data"] == {
        "asset_name": "旧资产名称",
        "remark": None,
        "version": asset.version,
    }
    assert submitted["assets"][0]["target_data"] == {
        "asset_name": "新资产名称",
        "remark": "已完成实物核对",
    }
    assert len(submitted["approval_timeline"]) == 1
    task_id = submitted["approval_timeline"][0]["tasks"][0]["id"]
    assert db.session.get(ApprovalTask, task_id).approver_id == actor.id

    approved_response = client.post(
        f"/api/v1/approval-tasks/{task_id}/approve",
        headers=headers,
        json={"opinion": "核对无误，同意变更"},
    )
    assert approved_response.status_code == 200
    approved = approved_response.get_json()["data"]
    assert approved["approval_status"] == "APPROVED"
    assert approved["execution_status"] == "SUCCESS"

    db.session.expire_all()
    changed = db.session.get(Asset, asset.id)
    operation = db.session.get(OperationRequest, submitted["id"])
    detail = db.session.scalar(
        db.select(AssetInformationChangeRequest).where(
            AssetInformationChangeRequest.operation_request_id == submitted["id"]
        )
    )
    snapshot = db.session.scalar(
        db.select(OperationRequestAsset).where(
            OperationRequestAsset.operation_request_id == submitted["id"]
        )
    )
    lifecycle = db.session.scalar(
        db.select(AssetLifecycleRecord).where(
            AssetLifecycleRecord.asset_id == asset.id,
            AssetLifecycleRecord.operation_type == "PHYSICAL_INFO_CHANGE",
        )
    )
    assert changed.asset_name == "新资产名称"
    assert changed.remark == "已完成实物核对"
    assert changed.version == original_version + 1
    assert detail is not None and detail.reason == "业务资料核对后申请调整"
    assert snapshot is not None and snapshot.before_data["asset_name"] == "旧资产名称"
    assert operation is not None and operation.executed_at is not None
    assert lifecycle is not None
    assert lifecycle.operation_no == operation.request_no
    assert lifecycle.before_data == snapshot.before_data
    assert lifecycle.after_data["asset_name"] == "新资产名称"

    detail_response = client.get(
        f"/api/v1/asset-information-change-requests/{submitted['id']}",
        headers=headers,
    ).get_json()["data"]
    assert detail_response["executed_at"] is not None


def test_rejected_change_does_not_update_asset(client) -> None:
    _actor, asset, headers = _seed(client)
    original_version = asset.version
    submitted = _submit(
        client,
        headers,
        asset,
        change_type="FINANCIAL",
        changes={"original_amount": "1200.00"},
    ).get_json()["data"]
    task_id = submitted["approval_timeline"][0]["tasks"][0]["id"]

    rejected = client.post(
        f"/api/v1/approval-tasks/{task_id}/reject",
        headers=headers,
        json={"opinion": "缺少财务凭证"},
    ).get_json()["data"]

    assert rejected["approval_status"] == "REJECTED"
    assert rejected["execution_status"] == "NOT_STARTED"
    db.session.expire_all()
    unchanged = db.session.get(Asset, asset.id)
    assert unchanged.original_amount == Decimal("1000.00")
    assert unchanged.version == original_version


def test_information_change_always_uses_internal_approval(client) -> None:
    actor, asset, headers = _seed(client)
    submitted = _submit(
        client,
        headers,
        asset,
        change_type="WARRANTY",
        changes={
            "warranty_contact": "张工",
            "warranty_phone": "13800000000",
            "warranty_expiry_date": "2027-09-04",
            "warranty_description": "三年上门维保",
        },
    ).get_json()["data"]

    assert submitted["requires_feishu_approval"] is False
    assert submitted["approval_channel"] == "INTERNAL"
    assert submitted["external_instance_id"] is None
    assert len(submitted["approval_timeline"]) == 1
    task_id = submitted["approval_timeline"][0]["tasks"][0]["id"]

    approved_response = client.post(
        f"/api/v1/approval-tasks/{task_id}/approve",
        headers=headers,
        json={"opinion": "同意变更"},
    )
    assert approved_response.status_code == 200
    approved = approved_response.get_json()["data"]
    assert approved["approval_status"] == "APPROVED"
    assert approved["execution_status"] == "SUCCESS"

    db.session.expire_all()
    changed = db.session.get(Asset, asset.id)
    assert changed.warranty_contact == "张工"
    assert changed.warranty_phone == "13800000000"
    assert changed.warranty_expiry_date == date(2027, 9, 4)
    assert changed.warranty_description == "三年上门维保"


def test_change_request_list_and_detail_follow_operation_data_scope(client) -> None:
    _actor, asset, headers = _seed(client)
    submitted = _submit(
        client,
        headers,
        asset,
        change_type="PHYSICAL",
        changes={"asset_name": "数据范围内的新名称"},
    ).get_json()["data"]

    other_organization = Organization(code="CHANGE-OTHER", name="其他公司")
    viewer = User(
        username="change-scope-viewer",
        password=hash_password("admin123"),
        enabled=True,
    )
    viewer_role = Role(
        code="CHANGE_SCOPE_VIEWER",
        name="信息变更查看人",
        data_scope=DataScope.DEPARTMENT.value,
    )
    view_permission = db.session.scalar(
        db.select(Permission).where(Permission.code == "operation:request:view")
    )
    assert view_permission is not None
    db.session.add_all([other_organization, viewer, viewer_role])
    db.session.flush()
    viewer.organization_id = other_organization.id
    db.session.add(UserRole(user_id=viewer.id, role_id=viewer_role.id))
    db.session.add(
        RolePermission(role_id=viewer_role.id, permission_id=view_permission.id)
    )
    db.session.commit()
    viewer_token = client.post(
        "/api/v1/auth/login",
        json={"username": viewer.username, "password": "admin123"},
    ).get_json()["data"]["token"]
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

    visible = client.get(
        "/api/v1/asset-information-change-requests?page=0&size=10",
        headers=headers,
    ).get_json()
    hidden = client.get(
        "/api/v1/asset-information-change-requests?page=0&size=10",
        headers=viewer_headers,
    ).get_json()
    forbidden_detail = client.get(
        f"/api/v1/asset-information-change-requests/{submitted['id']}",
        headers=viewer_headers,
    ).get_json()

    assert visible["code"] == 200
    assert [item["request_no"] for item in visible["data"]["items"]] == [
        submitted["request_no"]
    ]
    assert hidden["code"] == 200
    assert hidden["data"]["items"] == []
    assert forbidden_detail["code"] == 404
