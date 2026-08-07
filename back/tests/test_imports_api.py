from __future__ import annotations

from io import BytesIO

from app.enums import DataScope
from app.extensions import db
from app.models import (
    Asset,
    AssetCategory,
    AssetLifecycleRecord,
    AssetLocation,
    AssetSource,
    ImportJob,
    Organization,
    Permission,
    Role,
    RolePermission,
    Unit,
    User,
    UserRole,
)
from app.security.passwords import hash_password

_PASSWORD = "Import-Password-2026!"


def _actor(client, permissions: list[str]) -> tuple[User, dict[str, str]]:
    actor = User(
        username="import-admin", password=hash_password(_PASSWORD), enabled=True
    )
    role = Role(code="IMPORT_ADMIN", name="导入管理员", data_scope=DataScope.ALL.value)
    permission_rows = [
        Permission(code=code, name=code, module="import") for code in permissions
    ]
    db.session.add_all([actor, role, *permission_rows])
    db.session.flush()
    db.session.add(UserRole(user_id=actor.id, role_id=role.id))
    db.session.add_all(
        [
            RolePermission(role_id=role.id, permission_id=row.id)
            for row in permission_rows
        ]
    )
    db.session.commit()
    token = client.post(
        "/api/v1/auth/login",
        json={"username": actor.username, "password": _PASSWORD},
    ).get_json()["data"]["token"]
    return actor, {"Authorization": f"Bearer {token}"}


def _upload(
    client, headers: dict[str, str], import_type: str, content: bytes, name: str
):
    return client.post(
        "/api/v1/imports/preview",
        headers=headers,
        data={"import_type": import_type, "file": (BytesIO(content), name)},
        content_type="multipart/form-data",
    )


def test_organization_import_previews_differences_and_confirms_atomically(
    client,
) -> None:
    _, headers = _actor(client, ["organization:import"])
    existing = Organization(code="ROOT", name="原公司", status="ENABLED")
    db.session.add(existing)
    db.session.commit()
    content = "编码,名称,上级编码,状态\nROOT,集团总部,,启用\nCHILD,研发中心,ROOT,启用\n".encode()

    response = _upload(client, headers, "ORGANIZATION", content, "organizations.csv")
    assert response.status_code == 200
    preview = response.get_json()["data"]
    assert preview["status"] == "PREVIEW_READY"
    assert preview["create_count"] == 1
    assert preview["update_count"] == 1

    confirmed = client.post(
        f"/api/v1/imports/{preview['id']}/confirm",
        headers=headers,
        json={"confirmed": True, "version": preview["version"]},
    ).get_json()["data"]
    assert confirmed["status"] == "CONFIRMED"
    root = db.session.scalar(db.select(Organization).where(Organization.code == "ROOT"))
    child = db.session.scalar(
        db.select(Organization).where(Organization.code == "CHILD")
    )
    assert root is not None and root.name == "集团总部"
    assert child is not None and child.parent_id == root.id


def test_category_xlsx_template_accepts_seeded_default_unit(client) -> None:
    _, headers = _actor(client, ["asset-category:import"])
    db.session.add(Unit(code="TAI", name="台", status="ENABLED"))
    db.session.commit()

    template = client.get("/api/v1/imports/templates/CATEGORY", headers=headers)
    assert template.status_code == 200
    assert template.data.startswith(b"PK")

    response = _upload(client, headers, "CATEGORY", template.data, "category.xlsx")
    assert response.status_code == 200
    preview = response.get_json()["data"]
    assert preview["status"] == "PREVIEW_READY"
    assert preview["error_count"] == 0
    assert preview["create_count"] == 1
    assert preview["rows"][0]["normalized"]["default_unit_id"] is not None


def test_asset_import_keeps_unmatched_optional_master_text_and_creates_assets(
    client,
) -> None:
    actor, headers = _actor(client, ["asset:import"])
    organization = Organization(code="COMP01", name="资产公司", status="ENABLED")
    unit = Unit(code="TAI", name="台", status="ENABLED")
    source = AssetSource(code="PURCHASE", name="采购", status="ENABLED")
    location = AssetLocation(
        code="LOC01", name="总部仓库", status="ENABLED", is_selectable=True
    )
    db.session.add_all([organization, unit, source, location])
    db.session.flush()
    category = AssetCategory(
        code="NOTEBOOK",
        name="笔记本电脑",
        service_life_months=36,
        default_unit_id=unit.id,
        status="ENABLED",
    )
    db.session.add(category)
    db.session.commit()

    content = (
        "资产编码,所属公司编码,资产名称,资产分类编码,计量单位编码,原值,零金额原因,采购日期,"
        "供应商编码或名称,责任管理员账号,资产来源编码,存放地点编码,规格型号,序列号,RFID,备注\n"
        f"HIS-0001,COMP01,历史笔记本,NOTEBOOK,UNKNOWN,6999,,2026-08-03,,{actor.username},PURCHASE,,M4,SN-HIS-1,RFID-HIS-1,历史迁移\n"
    ).encode()
    response = _upload(client, headers, "ASSET", content, "assets.csv")
    preview = response.get_json()["data"]
    assert preview["status"] == "PREVIEW_READY"
    assert preview["warning_count"] == 2

    confirmed = client.post(
        f"/api/v1/imports/{preview['id']}/confirm",
        headers=headers,
        json={"confirmed": True, "version": preview["version"]},
    ).get_json()["data"]
    assert confirmed["status"] == "CONFIRMED"
    asset = db.session.scalar(db.select(Asset).where(Asset.asset_code == "HIS-0001"))
    assert asset is not None
    assert asset.unit_id is None
    assert asset.location_id is None
    assert asset.data_completeness == "INCOMPLETE"
    assert asset.custom_attributes["import_originals"]["unit"] == "UNKNOWN"
    assert (
        db.session.scalar(
            db.select(AssetLifecycleRecord).where(
                AssetLifecycleRecord.asset_id == asset.id,
                AssetLifecycleRecord.operation_type == "STOCK_IN",
            )
        )
        is not None
    )
    assert (
        db.session.scalar(db.select(ImportJob).where(ImportJob.id == preview["id"]))
        is not None
    )


def test_import_rejects_duplicate_codes_and_other_users_jobs(client) -> None:
    _, headers = _actor(client, ["organization:import"])
    content = "编码,名称,上级编码,状态\nDUP,公司一,,启用\nDUP,公司二,,启用\n".encode()
    preview = _upload(
        client, headers, "ORGANIZATION", content, "duplicate.csv"
    ).get_json()["data"]
    assert preview["status"] == "VALIDATION_FAILED"
    denied = client.post(
        f"/api/v1/imports/{preview['id']}/confirm",
        headers=headers,
        json={"confirmed": True, "version": preview["version"]},
    )
    assert denied.get_json()["code"] == 1000


def test_organization_master_data_export_preserves_tree_and_can_be_reimported(
    client,
) -> None:
    _, headers = _actor(
        client,
        ["organization:export", "organization:import"],
    )
    root = Organization(code="EXPORT-ROOT", name="导出集团", status="ENABLED")
    db.session.add(root)
    db.session.flush()
    db.session.add(
        Organization(
            code="EXPORT-CHILD",
            name="导出子公司",
            parent_id=root.id,
            status="DISABLED",
        )
    )
    db.session.commit()

    exported = client.get(
        "/api/v1/imports/master-data/ORGANIZATION/export",
        headers=headers,
    )
    assert exported.status_code == 200
    assert exported.data.startswith(b"PK")

    preview_response = _upload(
        client,
        headers,
        "ORGANIZATION",
        exported.data,
        "organizations-export.xlsx",
    )
    assert preview_response.status_code == 200
    preview = preview_response.get_json()["data"]
    assert preview["status"] == "PREVIEW_READY"
    assert preview["unchanged_count"] == 2
    rows = {row["values"]["编码"]: row for row in preview["rows"]}
    assert rows["EXPORT-ROOT"]["values"]["上级编码"] == ""
    assert rows["EXPORT-CHILD"]["values"]["上级编码"] == "EXPORT-ROOT"
    assert rows["EXPORT-CHILD"]["values"]["状态"] == "停用"


def test_category_master_data_export_preserves_tree_and_unit_code(
    client,
) -> None:
    _, headers = _actor(
        client,
        ["asset-category:export", "asset-category:import"],
    )
    unit = Unit(code="EXPORT-UNIT", name="台", status="ENABLED")
    db.session.add(unit)
    db.session.flush()
    root = AssetCategory(
        code="EXPORT-CATEGORY",
        name="导出分类",
        service_life_months=60,
        default_unit_id=unit.id,
        status="ENABLED",
    )
    db.session.add(root)
    db.session.flush()
    db.session.add(
        AssetCategory(
            code="EXPORT-CATEGORY-CHILD",
            name="导出子分类",
            parent_id=root.id,
            service_life_months=36,
            default_unit_id=unit.id,
            status="DISABLED",
        )
    )
    db.session.commit()

    exported = client.get(
        "/api/v1/imports/master-data/CATEGORY/export",
        headers=headers,
    )
    assert exported.status_code == 200
    assert exported.data.startswith(b"PK")

    preview_response = _upload(
        client,
        headers,
        "CATEGORY",
        exported.data,
        "categories-export.xlsx",
    )
    assert preview_response.status_code == 200
    preview = preview_response.get_json()["data"]
    assert preview["status"] == "PREVIEW_READY"
    assert preview["unchanged_count"] == 2
    rows = {row["values"]["编码"]: row for row in preview["rows"]}
    child = rows["EXPORT-CATEGORY-CHILD"]["values"]
    assert child["上级编码"] == "EXPORT-CATEGORY"
    assert child["默认计量单位编码"] == "EXPORT-UNIT"
    assert child["使用期限（月）"] == "36"
    assert child["状态"] == "停用"


def test_master_data_export_permission_is_independent_from_import(client) -> None:
    _, headers = _actor(client, ["organization:import", "asset-category:import"])

    organization_response = client.get(
        "/api/v1/imports/master-data/ORGANIZATION/export",
        headers=headers,
    )
    category_response = client.get(
        "/api/v1/imports/master-data/CATEGORY/export",
        headers=headers,
    )

    assert organization_response.status_code == 200
    assert category_response.status_code == 200
    assert organization_response.get_json()["code"] == 403
    assert category_response.get_json()["code"] == 403
