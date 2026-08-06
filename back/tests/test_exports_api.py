from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from app.enums import AssetDataCompleteness, AssetStatus, DataScope
from app.extensions import db
from app.models import (
    Asset,
    AssetCategory,
    AssetLifecycleRecord,
    AssetLocation,
    AssetSource,
    ExportJob,
    Organization,
    Permission,
    Role,
    RolePermission,
    Unit,
    User,
    UserRole,
)
from app.models.mixins import utc_now
from app.security.passwords import hash_password
from app.services import export_service

_PASSWORD = "Export-Password-2026!"


def _user(client, username: str, permissions: list[str]) -> tuple[User, dict[str, str]]:
    user = User(username=username, password=hash_password(_PASSWORD), enabled=True)
    role = Role(
        code=f"ROLE_{username.upper()}",
        name=f"{username} role",
        data_scope=DataScope.ALL.value,
    )
    permission_rows = []
    for code in permissions:
        permission = db.session.scalar(
            db.select(Permission).where(Permission.code == code)
        )
        if permission is None:
            permission = Permission(code=code, name=code, module="asset")
            db.session.add(permission)
        permission_rows.append(permission)
    db.session.add_all([user, role])
    db.session.flush()
    db.session.add(UserRole(user_id=user.id, role_id=role.id))
    db.session.add_all(
        [
            RolePermission(role_id=role.id, permission_id=permission.id)
            for permission in permission_rows
        ]
    )
    db.session.commit()
    token = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": _PASSWORD},
    ).get_json()["data"]["token"]
    return user, {"Authorization": f"Bearer {token}"}


def _asset() -> Asset:
    organization = Organization(code="EXP-ORG", name="读书资产公司")
    unit = Unit(code="EXP-UNIT", name="台")
    source = AssetSource(code="EXP-SOURCE", name="采购")
    location = AssetLocation(code="EXP-LOC", name="上海仓库", is_selectable=True)
    manager = User(
        username="export-manager",
        nickname="资产管理员",
        password=hash_password(_PASSWORD),
        enabled=True,
    )
    db.session.add_all([organization, unit, source, location, manager])
    db.session.flush()
    category = AssetCategory(
        code="EXP-CATEGORY",
        name="笔记本电脑",
        service_life_months=36,
        default_unit_id=unit.id,
    )
    db.session.add(category)
    db.session.flush()
    asset = Asset(
        asset_code="DS-IT-0001",
        asset_name="MacBook Pro",
        status=AssetStatus.IDLE.value,
        organization_id=organization.id,
        category_id=category.id,
        unit_id=unit.id,
        original_amount=Decimal("12999.00"),
        purchase_date=date(2026, 7, 31),
        service_life_months=36,
        expected_expiry_date=date(2029, 7, 31),
        manager_id=manager.id,
        source_id=source.id,
        location_id=location.id,
        serial_number="C02EXPORT",
        normalized_serial="c02export",
        rfid_tag="RFID-EXPORT-1",
        custom_attributes={},
        data_completeness=AssetDataCompleteness.COMPLETE.value,
    )
    db.session.add(asset)
    db.session.commit()
    return asset


def test_csv_export_uses_real_filters_amount_permission_and_audit(
    client, app, tmp_path
) -> None:
    app.config["EXPORT_STORAGE_DIR"] = str(tmp_path / "exports")
    asset = _asset()
    _, headers = _user(
        client,
        "export-admin",
        ["asset:view", "asset:export", "asset:amount:view"],
    )

    response = client.post(
        "/api/v1/exports",
        headers=headers,
        json={
            "job_type": "ASSET_CSV",
            "filters": {"company_name": "读书资产公司", "keyword": "MacBook"},
        },
    )
    payload = response.get_json()["data"]
    assert payload["status"] == "SUCCESS"
    assert payload["item_count"] == 1
    assert payload["original_name"].endswith(".csv")

    download = client.get(f"/api/v1/exports/{payload['id']}/download", headers=headers)
    assert download.status_code == 200
    assert download.data.startswith(b"\xef\xbb\xbf")
    text = download.data.decode("utf-8-sig")
    assert "资产编码,资产名称" in text
    assert "DS-IT-0001,MacBook Pro" in text
    assert "采购金额" in text
    assert "12999.00" in text

    lifecycle_types = set(
        db.session.scalars(
            db.select(AssetLifecycleRecord.operation_type).where(
                AssetLifecycleRecord.asset_id == asset.id
            )
        ).all()
    )
    assert "ASSET_EXPORT" in lifecycle_types


def test_csv_export_hides_amount_without_field_permission(
    client, app, tmp_path
) -> None:
    app.config["EXPORT_STORAGE_DIR"] = str(tmp_path / "exports")
    asset = _asset()
    _, headers = _user(client, "export-reader", ["asset:view", "asset:export"])

    created = client.post(
        "/api/v1/exports",
        headers=headers,
        json={"job_type": "ASSET_CSV", "asset_ids": [asset.id]},
    ).get_json()["data"]
    text = client.get(
        f"/api/v1/exports/{created['id']}/download", headers=headers
    ).data.decode("utf-8-sig")
    assert "采购金额" not in text
    assert "12999.00" not in text


def test_label_pdf_is_80_by_30_mm_and_contains_barcode_job(
    client, app, tmp_path
) -> None:
    app.config["EXPORT_STORAGE_DIR"] = str(tmp_path / "exports")
    asset = _asset()
    _, headers = _user(client, "label-admin", ["asset:view", "asset:label:print"])

    created = client.post(
        "/api/v1/exports",
        headers=headers,
        json={"job_type": "LABEL_PDF", "asset_ids": [asset.id]},
    ).get_json()["data"]
    response = client.get(f"/api/v1/exports/{created['id']}/download", headers=headers)
    assert response.status_code == 200
    assert response.content_type == "application/pdf"
    assert response.data.startswith(b"%PDF-1.4")
    assert b"/MediaBox [0 0 226.77 85.04]" in response.data
    assert b"/Count 1" in response.data
    assert b" re f" in response.data
    lifecycle = db.session.scalar(
        db.select(AssetLifecycleRecord).where(
            AssetLifecycleRecord.asset_id == asset.id,
            AssetLifecycleRecord.operation_type == "ASSET_LABEL_PRINT",
        )
    )
    assert lifecycle is not None


def test_exports_are_private_and_cleanup_expires_files(client, app, tmp_path) -> None:
    storage_root = tmp_path / "exports"
    app.config["EXPORT_STORAGE_DIR"] = str(storage_root)
    asset = _asset()
    owner, owner_headers = _user(client, "export-owner", ["asset:view", "asset:export"])
    _, other_headers = _user(client, "export-other", ["asset:view", "asset:export"])
    created = client.post(
        "/api/v1/exports",
        headers=owner_headers,
        json={"job_type": "ASSET_CSV", "asset_ids": [asset.id]},
    ).get_json()["data"]

    denied = client.get(
        f"/api/v1/exports/{created['id']}/download", headers=other_headers
    ).get_json()
    assert denied["code"] == 404

    job = db.session.get(ExportJob, created["id"])
    assert job is not None and job.created_by == owner.id
    file_path = Path(app.config["EXPORT_STORAGE_DIR"]) / job.storage_key
    assert file_path.is_file()
    job.expires_at = utc_now() - timedelta(minutes=1)
    db.session.commit()

    removed = export_service.cleanup_expired_files()
    assert removed == 1
    assert not file_path.exists()
    refreshed = db.session.get(ExportJob, created["id"])
    assert refreshed is not None and refreshed.status == "EXPIRED"
