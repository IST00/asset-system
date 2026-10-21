"""Open-receiver QR transfer handover regression tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.enums import AssetStatus, DataScope
from app.extensions import db
from app.models import (
    Asset,
    AssetCategory,
    AssetLifecycleRecord,
    AssetLocation,
    AssetSource,
    Organization,
    Permission,
    Role,
    RolePermission,
    Unit,
    User,
    UserRole,
)
from app.security.passwords import hash_password
from app.services import asset_transfer_handover_service


def _user(username: str, *, organization_id: int | None = None, manage=False) -> User:
    user = User(
        username=username,
        password=hash_password("admin123"),
        enabled=True,
        organization_id=organization_id,
    )
    db.session.add(user)
    db.session.flush()
    if manage:
        role = Role(
            code=f"{username.upper()}_ROLE",
            name=f"{username}角色",
            data_scope=DataScope.ALL.value,
        )
        db.session.add(role)
        db.session.flush()
        permission = db.session.scalar(
            db.select(Permission).where(Permission.code == "asset:usage:manage")
        )
        if permission is None:
            permission = Permission(
                code="asset:usage:manage", name="资产管理", module="asset"
            )
            db.session.add(permission)
            db.session.flush()
        db.session.add_all(
            [
                UserRole(user_id=user.id, role_id=role.id),
                RolePermission(role_id=role.id, permission_id=permission.id),
            ]
        )
    return user


def _seed():
    organization = Organization(code="QR-ORG", name="交接公司")
    department = Organization(
        code="QR-DEPT", name="交接部门", parent_id=organization.id
    )
    unit = Unit(code="QR-UNIT", name="台")
    source = AssetSource(code="QR-SOURCE", name="采购")
    location = AssetLocation(code="QR-LOC", name="办公区", is_selectable=True)
    db.session.add_all([organization, department, unit, source, location])
    db.session.flush()
    category = AssetCategory(
        code="QR-CATEGORY",
        name="电脑",
        service_life_months=36,
        default_unit_id=unit.id,
    )
    db.session.add(category)
    db.session.flush()
    manager = _user("qr-manager", organization_id=organization.id, manage=True)
    receiver = _user("qr-receiver", organization_id=department.id)
    asset = Asset(
        asset_code="QR-ASSET-001",
        asset_name="扫码交接资产",
        status=AssetStatus.IDLE.value,
        organization_id=organization.id,
        category_id=category.id,
        unit_id=unit.id,
        original_amount=Decimal("100.00"),
        purchase_date=date(2026, 1, 1),
        service_life_months=36,
        expected_expiry_date=date(2029, 1, 1),
        manager_id=manager.id,
        source_id=source.id,
        location_id=location.id,
        custom_attributes={},
    )
    db.session.add(asset)
    db.session.commit()
    return manager, receiver, asset


def test_open_qr_handover_creates_and_completes_transfer(app):  # noqa: ANN001
    with app.app_context():
        manager, receiver, asset = _seed()
        created = asset_transfer_handover_service.create(
            {
                "items": [{"asset_id": asset.id, "version": asset.version}],
                "receiver_user_id": None,
                "reason": "责任人调整",
            },
            manager.id,
        )
        assert created["handover_token"]
        assert created["status"] == "PENDING_RECEIPT"

        completed = asset_transfer_handover_service.claim_by_token(
            receiver.id, created["handover_token"], "扫码接收"
        )
        assert completed["status"] == "COMPLETED"
        assert completed["receiver_user_id"] == receiver.id
        assert asset.holder_user_id == receiver.id
        assert asset.status == AssetStatus.IN_USE.value
        assert asset.usage_department_id == receiver.organization_id
        lifecycle = db.session.scalar(
            db.select(AssetLifecycleRecord).where(
                AssetLifecycleRecord.asset_id == asset.id
            )
        )
        assert lifecycle is not None
        assert lifecycle.operation_type == "TRANSFER"


def test_processed_qr_cannot_be_reused(app):  # noqa: ANN001
    with app.app_context():
        manager, receiver, asset = _seed()
        created = asset_transfer_handover_service.create(
            {
                "items": [{"asset_id": asset.id, "version": asset.version}],
                "receiver_user_id": None,
                "reason": "离职交接",
            },
            manager.id,
        )
        token = created["handover_token"]
        asset_transfer_handover_service.claim_by_token(receiver.id, token)
        from app.common import BusinessException

        try:
            asset_transfer_handover_service.claim_by_token(manager.id, token)
        except BusinessException:
            pass
        else:
            raise AssertionError("processed handover token should be rejected")


def test_open_qr_handover_api_flow(app, client):  # noqa: ANN001
    with app.app_context():
        manager, receiver, asset = _seed()
        manager_token = client.post(
            "/api/v1/auth/login",
            json={"username": "qr-manager", "password": "admin123"},
        ).get_json()["data"]["token"]
        receiver_token = client.post(
            "/api/v1/auth/login",
            json={"username": "qr-receiver", "password": "admin123"},
        ).get_json()["data"]["token"]

        created = client.post(
            "/api/v1/asset-actions/transfer-handover",
            json={
                "items": [{"asset_id": asset.id, "version": asset.version}],
                "receiver_user_id": None,
                "reason": "接口回归",
            },
            headers={"Authorization": f"Bearer {manager_token}"},
        ).get_json()["data"]
        assert created["handover_token"]

        detail = client.get(
            f"/api/v1/asset-actions/transfer-handovers/by-token/{created['handover_token']}",
            headers={"Authorization": f"Bearer {receiver_token}"},
        ).get_json()["data"]
        assert detail["handover_no"] == created["handover_no"]

        completed = client.post(
            "/api/v1/asset-actions/transfer-handovers/claim-by-token",
            json={"handover_token": created["handover_token"], "remark": "扫码接收"},
            headers={"Authorization": f"Bearer {receiver_token}"},
        ).get_json()["data"]
        assert completed["status"] == "COMPLETED"
        assert asset.holder_user_id == receiver.id
