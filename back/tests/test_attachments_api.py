from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO

from app.enums import AssetDataCompleteness, AssetStatus, DataScope
from app.extensions import db
from app.models import (
    Asset,
    AssetAttachment,
    AssetCategory,
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
        permissions.append(
            Permission(
                code="asset:attachment:manage", name="管理资产附件", module="asset"
            )
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
