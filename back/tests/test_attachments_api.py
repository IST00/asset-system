from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO

from app.enums import AssetDataCompleteness, AssetStatus, DataScope
from app.extensions import db
from app.models import (
    Asset,
    AssetAttachment,
    AssetCategory,
    AssetLocation,
    AssetRepairRecord,
    AssetScrapRecord,
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


def _login(client, username: str) -> dict[str, str]:
    token = client.post(
        "/api/v1/auth/login", json={"username": username, "password": "admin123"}
    ).get_json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def _seed(client, storage_dir, *, manage: bool = True):
    client.application.config["ASSET_STORAGE_DIR"] = str(storage_dir)
    organization = Organization(code="ATT-ORG", name="附件公司")
    unit = Unit(code="ATT-UNIT", name="台")
    source = AssetSource(code="ATT-SOURCE", name="采购")
    location = AssetLocation(code="ATT-LOC", name="仓库", is_selectable=True)
    actor = User(
        username="attachment-admin" if manage else "attachment-reader",
        password=hash_password("admin123"),
        organization_id=None,
        enabled=True,
    )
    role = Role(
        code="ATTACHMENT_ADMIN" if manage else "ATTACHMENT_READER",
        name="附件管理员" if manage else "附件查看人",
        data_scope=DataScope.ALL.value,
    )
    permissions = [Permission(code="asset:view", name="查看资产", module="asset")]
    if manage:
        permissions.extend(
            [
                Permission(
                    code="asset:attachment:manage",
                    name="管理资产附件",
                    module="asset",
                ),
                Permission(code="asset:repair", name="维修资产", module="asset"),
                Permission(code="asset:scrap", name="报废资产", module="asset"),
            ]
        )
    db.session.add_all(
        [organization, unit, source, location, actor, role, *permissions]
    )
    db.session.flush()
    actor.organization_id = organization.id
    category = AssetCategory(
        code="ATT-CATEGORY",
        name="电脑",
        service_life_months=36,
        default_unit_id=unit.id,
    )
    db.session.add(category)
    db.session.flush()
    asset = Asset(
        asset_code="ATT-0001",
        asset_name="附件测试资产",
        status=AssetStatus.IDLE.value,
        organization_id=organization.id,
        category_id=category.id,
        unit_id=unit.id,
        original_amount=Decimal("100.00"),
        purchase_date=date(2026, 8, 1),
        service_life_months=36,
        expected_expiry_date=date(2029, 8, 1),
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
        [RolePermission(role_id=role.id, permission_id=item.id) for item in permissions]
    )
    db.session.commit()
    return asset, _login(client, actor.username)


def _upload(client, asset_id: int, headers: dict[str, str], name: str):
    return client.post(
        f"/api/v1/assets/{asset_id}/attachments",
        headers=headers,
        data={
            "business_type": "PHOTO",
            "file": (BytesIO(b"not-a-real-image-but-valid-upload-by-mime"), name),
        },
        content_type="multipart/form-data",
    )


def test_asset_photos_upload_download_cover_and_void(client, tmp_path) -> None:
    asset, headers = _seed(client, tmp_path)
    first = _upload(client, asset.id, headers, "front.jpg")
    assert first.status_code == 200
    first_data = first.get_json()["data"]
    assert first_data["is_cover"] is True
    assert first_data["status"] == "ACTIVE"

    second_data = _upload(client, asset.id, headers, "back.jpg").get_json()["data"]
    assert second_data["is_cover"] is False

    covered = client.post(
        f"/api/v1/attachments/{second_data['id']}/cover",
        headers=headers,
        json={"version": second_data["version"]},
    ).get_json()["data"]
    assert covered["is_cover"] is True

    downloaded = client.get(
        f"/api/v1/attachments/{second_data['id']}/download", headers=headers
    )
    assert downloaded.status_code == 200
    assert downloaded.data == b"not-a-real-image-but-valid-upload-by-mime"

    voided = client.post(
        f"/api/v1/attachments/{second_data['id']}/void",
        headers=headers,
        json={"version": covered["version"], "reason": "背面照片已更新"},
    ).get_json()["data"]
    assert voided["status"] == "VOIDED"
    assert voided["void_reason"] == "背面照片已更新"

    rows = client.get(
        f"/api/v1/assets/{asset.id}/attachments", headers=headers
    ).get_json()["data"]
    active = next(item for item in rows if item["id"] == first_data["id"])
    assert active["is_cover"] is True
    assert db.session.get(AssetAttachment, second_data["id"]).storage_key


def test_attachment_upload_requires_manage_permission(client, tmp_path) -> None:
    asset, headers = _seed(client, tmp_path, manage=False)
    response = _upload(client, asset.id, headers, "denied.jpg")
    assert response.get_json()["code"] == 403


def test_attachment_rejects_unsupported_photo_and_stale_version(
    client, tmp_path
) -> None:
    asset, headers = _seed(client, tmp_path)
    invalid = client.post(
        f"/api/v1/assets/{asset.id}/attachments",
        headers=headers,
        data={
            "business_type": "PHOTO",
            "file": (BytesIO(b"plain"), "plain.txt"),
        },
        content_type="multipart/form-data",
    )
    assert invalid.get_json()["code"] == 1000

    uploaded = _upload(client, asset.id, headers, "valid.jpg").get_json()["data"]
    stale = client.post(
        f"/api/v1/attachments/{uploaded['id']}/void",
        headers=headers,
        json={"version": uploaded["version"] + 1, "reason": "测试版本冲突"},
    )
    assert stale.get_json()["code"] == 1000


def test_repair_and_scrap_attachments_link_records_and_protect_amount_files(
    client, tmp_path
) -> None:
    asset, headers = _seed(client, tmp_path)
    actor = db.session.query(User).filter_by(username="attachment-admin").one()
    repair = AssetRepairRecord(
        asset_id=asset.id,
        repair_no="REP-ATT-001",
        before_status=AssetStatus.IDLE.value,
        fault_description="屏幕损坏",
        sent_at=datetime(2026, 9, 4, 1, 0, tzinfo=timezone.utc),
    )
    scrap = AssetScrapRecord(
        asset_id=asset.id,
        scrap_no="SCR-ATT-001",
        scrap_date=date(2026, 9, 4),
        disposal_date=date(2026, 9, 4),
        scrap_amount=Decimal("80.00"),
        reason="无维修价值",
        disposition="回收",
        disposition_remark="交由合规回收商",
        confirmed_by=actor.id,
        confirmed_at=datetime(2026, 9, 4, 2, 0, tzinfo=timezone.utc),
    )
    db.session.add_all([repair, scrap])
    db.session.commit()

    repair_photo = client.post(
        f"/api/v1/assets/{asset.id}/attachments",
        headers=headers,
        data={
            "business_type": "REPAIR",
            "business_id": str(repair.id),
            "document_type": "REPAIR_PHOTO",
            "file": (BytesIO(b"repair-photo"), "repair.jpg"),
        },
        content_type="multipart/form-data",
    )
    assert repair_photo.status_code == 200
    repair_data = repair_photo.get_json()["data"]
    assert repair_data["business_type"] == "REPAIR"
    assert repair_data["business_id"] == repair.id
    assert repair_data["document_type"] == "REPAIR_PHOTO"

    quote = client.post(
        f"/api/v1/assets/{asset.id}/attachments",
        headers=headers,
        data={
            "business_type": "REPAIR",
            "business_id": str(repair.id),
            "document_type": "REPAIR_QUOTE",
            "file": (BytesIO(b"repair-quote"), "quote.pdf"),
        },
        content_type="multipart/form-data",
    ).get_json()["data"]
    voucher = client.post(
        f"/api/v1/assets/{asset.id}/attachments",
        headers=headers,
        data={
            "business_type": "SCRAP",
            "business_id": str(scrap.id),
            "document_type": "DISPOSAL_VOUCHER",
            "file": (BytesIO(b"disposal-voucher"), "voucher.pdf"),
        },
        content_type="multipart/form-data",
    ).get_json()["data"]
    assert voucher["business_id"] == scrap.id
    assert voucher["document_type"] == "DISPOSAL_VOUCHER"

    filtered = client.get(
        f"/api/v1/assets/{asset.id}/attachments",
        headers=headers,
        query_string={"business_type": "REPAIR", "business_id": repair.id},
    ).get_json()["data"]
    assert {item["id"] for item in filtered} == {repair_data["id"], quote["id"]}

    assert (
        client.get(
            f"/api/v1/attachments/{quote['id']}/download", headers=headers
        ).get_json()["code"]
        == 403
    )
    assert (
        client.get(
            f"/api/v1/attachments/{voucher['id']}/download", headers=headers
        ).get_json()["code"]
        == 403
    )

    amount_permission = Permission(
        code="asset:amount:view", name="查看资产金额", module="asset"
    )
    db.session.add(amount_permission)
    db.session.flush()
    role = db.session.query(Role).filter_by(code="ATTACHMENT_ADMIN").one()
    db.session.add(RolePermission(role_id=role.id, permission_id=amount_permission.id))
    db.session.commit()
    quote_download = client.get(
        f"/api/v1/attachments/{quote['id']}/download", headers=headers
    )
    voucher_download = client.get(
        f"/api/v1/attachments/{voucher['id']}/download", headers=headers
    )
    assert quote_download.status_code == 200
    assert quote_download.data == b"repair-quote"
    assert voucher_download.status_code == 200
    assert voucher_download.data == b"disposal-voucher"


def test_business_attachment_rejects_record_from_another_asset(
    client, tmp_path
) -> None:
    asset, headers = _seed(client, tmp_path)
    actor = db.session.query(User).filter_by(username="attachment-admin").one()
    other = Asset(
        asset_code="ATT-0002",
        asset_name="另一项资产",
        status=AssetStatus.IDLE.value,
        organization_id=asset.organization_id,
        category_id=asset.category_id,
        unit_id=asset.unit_id,
        original_amount=Decimal("200.00"),
        purchase_date=date(2026, 9, 4),
        service_life_months=36,
        expected_expiry_date=date(2029, 8, 4),
        manager_id=actor.id,
        source_id=asset.source_id,
        location_id=asset.location_id,
        custom_attributes={},
        data_completeness=AssetDataCompleteness.COMPLETE.value,
    )
    db.session.add(other)
    db.session.flush()
    repair = AssetRepairRecord(
        asset_id=other.id,
        repair_no="REP-OTHER-001",
        before_status=AssetStatus.IDLE.value,
        fault_description="其他资产维修",
        sent_at=datetime(2026, 9, 4, 3, 0, tzinfo=timezone.utc),
    )
    db.session.add(repair)
    db.session.commit()

    response = client.post(
        f"/api/v1/assets/{asset.id}/attachments",
        headers=headers,
        data={
            "business_type": "REPAIR",
            "business_id": str(repair.id),
            "document_type": "REPAIR_INVOICE",
            "file": (BytesIO(b"wrong-link"), "invoice.pdf"),
        },
        content_type="multipart/form-data",
    ).get_json()

    assert response["code"] == 1000
    assert "不属于该资产" in response["message"]
    assert db.session.query(AssetAttachment).count() == 0
