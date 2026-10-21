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
    PublicUsageObject,
    Supplier,
    Organization,
    Permission,
    Role,
    RolePermission,
    Unit,
    User,
    UserNotification,
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
    unit = Unit(code="TAI", name="台", status="ENABLED")
    db.session.add(unit)
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
    row = preview["rows"][0]
    assert row["values"]["默认计量单位编码"] == "TAI"
    assert row["normalized"]["default_unit_id"] == unit.id


def test_category_xlsx_template_without_default_unit_provides_error_report(
    client,
) -> None:
    _, headers = _actor(client, ["asset-category:import"])
    template = client.get("/api/v1/imports/templates/CATEGORY", headers=headers)
    assert template.status_code == 200

    response = _upload(client, headers, "CATEGORY", template.data, "category.xlsx")
    assert response.status_code == 200
    preview = response.get_json()["data"]
    assert preview["status"] == "VALIDATION_FAILED"
    assert preview["error_count"] > 0

    report = client.get(
        f"/api/v1/imports/{preview['id']}/error-report", headers=headers
    )
    assert report.status_code == 200
    assert report.data.startswith(b"PK")


def test_asset_import_auto_handles_units(client) -> None:
    actor, headers = _actor(client, ["asset:import"])
    admin = User(
        username="admin",
        nickname="Admin",
        password=hash_password(_PASSWORD),
        enabled=True,
    )
    organization = Organization(code="UNIT-ORG", name="资产公司", status="ENABLED")
    unit = Unit(code="TAI", name="台", status="ENABLED")
    disabled_unit = Unit(code="DISABLED", name="旧单位", status="DISABLED")
    source = AssetSource(code="PURCHASE", name="采购", status="ENABLED")
    location = AssetLocation(
        code="UNIT-LOC", name="总部仓库", status="ENABLED", is_selectable=True
    )
    db.session.add_all([admin, organization, unit, disabled_unit, source, location])
    db.session.flush()
    default_category = AssetCategory(
        code="UNIT-DEFAULT",
        name="电脑",
        service_life_months=36,
        default_unit_id=unit.id,
        status="ENABLED",
    )
    no_default_category = AssetCategory(
        code="UNIT-NO-DEFAULT",
        name="其他设备",
        service_life_months=36,
        default_unit_id=disabled_unit.id,
        status="ENABLED",
    )
    db.session.add_all([default_category, no_default_category])
    db.session.commit()

    content = (
        "资产编码,所属公司,资产名称,资产分类,计量单位,金额,采购日期,"
        "供应商,责任管理员,资产来源,存放地点,使用公司,使用部门,使用人\n"
        "UNIT-ALIAS,资产公司,别名电脑,电脑,PCS,1000,2026-01-01,,admin,PURCHASE,总部仓库,资产公司,,\n"
        "UNIT-EMPTY,资产公司,空单位设备,其他设备,,1000,2026-01-01,,admin,PURCHASE,总部仓库,资产公司,,\n"
        "UNIT-CREATE,资产公司,新单位设备,其他设备,张,1000,2026-01-01,,admin,PURCHASE,总部仓库,资产公司,,\n"
        "UNIT-PENDING,资产公司,未知单位设备,其他设备,UNKNOWN,1000,2026-01-01,,admin,PURCHASE,总部仓库,资产公司,,\n"
    ).encode()
    preview = _upload(client, headers, "ASSET", content, "asset-units.csv").get_json()[
        "data"
    ]

    assert preview["status"] == "PREVIEW_READY"
    rows = preview["rows"]
    assert any("分类默认单位" in action for action in rows[0]["auto_actions"])
    assert rows[1]["warnings"] == ["计量单位待补充"]
    assert any("自动创建" in action for action in rows[2]["auto_actions"])
    assert rows[3]["warnings"] == ["计量单位未匹配，原文字已保留"]

    confirmed = client.post(
        f"/api/v1/imports/{preview['id']}/confirm",
        headers=headers,
        json={"confirmed": True, "version": preview["version"]},
    ).get_json()["data"]
    assert confirmed["status"] == "CONFIRMED"
    alias = db.session.scalar(db.select(Asset).where(Asset.asset_code == "UNIT-ALIAS"))
    empty = db.session.scalar(db.select(Asset).where(Asset.asset_code == "UNIT-EMPTY"))
    created = db.session.scalar(
        db.select(Asset).where(Asset.asset_code == "UNIT-CREATE")
    )
    pending = db.session.scalar(
        db.select(Asset).where(Asset.asset_code == "UNIT-PENDING")
    )
    assert alias is not None and alias.unit_id == unit.id
    assert empty is not None and empty.unit_id is None
    created_unit = db.session.scalar(db.select(Unit).where(Unit.name == "张"))
    assert created_unit is not None
    assert created is not None and created.unit_id == created_unit.id
    assert pending is not None and pending.unit_id is None
    assert pending.custom_attributes["pending_unit"] is True
    assert pending.data_completeness == "INCOMPLETE"
    assert {
        item["type"] for item in confirmed["result"]["auto_created_master_data"]
    } == {"UNIT"}
    notification = db.session.scalar(
        db.select(UserNotification).where(
            UserNotification.user_id == actor.id,
            UserNotification.deduplication_key
            == f"IMPORT_PENDING_LOCATION:{preview['id']}",
        )
    )
    assert notification is not None


def test_asset_import_auto_matches_and_creates_categories(client) -> None:
    _, headers = _actor(client, ["asset:import"])
    admin = User(
        username="admin",
        nickname="Admin",
        password=hash_password(_PASSWORD),
        enabled=True,
    )
    organization = Organization(code="CATEGORY-ORG", name="资产公司", status="ENABLED")
    unit = Unit(code="CATEGORY-UNIT", name="台", status="ENABLED")
    source = AssetSource(code="PURCHASE", name="采购", status="ENABLED")
    db.session.add_all([admin, organization, unit, source])
    db.session.flush()
    root = AssetCategory(
        code="CATEGORY-ROOT",
        name="电子设备",
        service_life_months=60,
        default_unit_id=unit.id,
        status="ENABLED",
    )
    db.session.add(root)
    db.session.flush()
    existing_leaf = AssetCategory(
        code="CATEGORY-LEAF",
        name="笔记本电脑",
        parent_id=root.id,
        service_life_months=48,
        default_unit_id=unit.id,
        status="ENABLED",
    )
    disabled = AssetCategory(
        code="CATEGORY-DISABLED",
        name="旧设备",
        service_life_months=36,
        default_unit_id=unit.id,
        status="DISABLED",
    )
    db.session.add_all([existing_leaf, disabled])
    db.session.commit()

    content = (
        "资产编码,所属公司,资产名称,资产分类,计量单位,金额,采购日期,"
        "供应商,责任管理员,资产来源,存放地点,使用公司,使用部门,使用人\n"
        "CATEGORY-LEAF,资产公司,员工电脑,笔记本电脑,台,6000,2026-01-01,,admin,PURCHASE,,资产公司,,\n"
        "CATEGORY-NORMALIZED,资产公司,路径电脑,电子设备 ／ 笔记本电脑,台,6000,2026-01-01,,admin,PURCHASE,,资产公司,,\n"
        "CATEGORY-CREATE,资产公司,新设备,电子设备/平板电脑,台,6000,2026-01-01,,admin,PURCHASE,,资产公司,,\n"
        "CATEGORY-PENDING,资产公司,待整理设备,AR 设备,台,6000,2026-01-01,,admin,PURCHASE,,资产公司,,\n"
        "CATEGORY-DISABLED,资产公司,旧设备,旧设备,台,6000,2026-01-01,,admin,PURCHASE,,资产公司,,\n"
    ).encode()
    response = _upload(client, headers, "ASSET", content, "asset-categories.csv")
    assert response.status_code == 200
    preview = response.get_json()["data"]
    assert preview["status"] == "VALIDATION_FAILED"
    rows = preview["rows"]
    assert rows[0]["normalized"]["category_id"] == existing_leaf.id
    assert rows[1]["normalized"]["category_id"] == existing_leaf.id
    assert any("电子设备/平板电脑" in action for action in rows[2]["auto_actions"])
    assert any(
        "资产分类「AR 设备」将在确认导入时自动创建"
        for action in rows[3]["auto_actions"]
    )
    assert rows[4]["errors"] == ["资产分类「旧设备」已停用，请先启用或更换分类"]

    # A disabled category must be repaired in basic data before import confirmation.
    valid_content = (
        "资产编码,所属公司,资产名称,资产分类,计量单位,金额,采购日期,"
        "供应商,责任管理员,资产来源,存放地点,使用公司,使用部门,使用人\n"
        "CATEGORY-LEAF,资产公司,员工电脑,笔记本电脑,台,6000,2026-01-01,,admin,PURCHASE,,资产公司,,\n"
        "CATEGORY-NORMALIZED,资产公司,路径电脑,电子设备 ／ 笔记本电脑,台,6000,2026-01-01,,admin,PURCHASE,,资产公司,,\n"
        "CATEGORY-CREATE,资产公司,新设备,电子设备/平板电脑,台,6000,2026-01-01,,admin,PURCHASE,,资产公司,,\n"
        "CATEGORY-PENDING,资产公司,待整理设备,AR 设备,台,6000,2026-01-01,,admin,PURCHASE,,资产公司,,\n"
    ).encode()
    valid_preview = _upload(
        client, headers, "ASSET", valid_content, "asset-categories-valid.csv"
    ).get_json()["data"]
    confirmed = client.post(
        f"/api/v1/imports/{valid_preview['id']}/confirm",
        headers=headers,
        json={"confirmed": True, "version": valid_preview["version"]},
    ).get_json()["data"]
    assert confirmed["status"] == "CONFIRMED"
    tablet = db.session.scalar(
        db.select(AssetCategory).where(AssetCategory.name == "平板电脑")
    )
    pending = db.session.scalar(
        db.select(AssetCategory).where(AssetCategory.name == "AR 设备")
    )
    assert tablet is not None
    assert tablet.parent_id == root.id
    assert tablet.service_life_months == 60
    assert tablet.default_unit_id == unit.id
    assert pending is not None
    assert pending.parent_id is None
    asset = db.session.scalar(
        db.select(Asset).where(Asset.asset_code == "CATEGORY-PENDING")
    )
    assert asset is not None and asset.category_id == pending.id
    created_types = {
        item["type"] for item in confirmed["result"]["auto_created_master_data"]
    }
    assert "ASSET_CATEGORY" in created_types


def test_asset_import_creates_default_unit_when_master_units_are_empty(client) -> None:
    _, headers = _actor(client, ["asset:import"])
    admin = User(
        username="admin",
        nickname="Admin",
        password=hash_password(_PASSWORD),
        enabled=True,
    )
    organization = Organization(
        code="EMPTY-UNIT-ORG", name="资产公司", status="ENABLED"
    )
    source = AssetSource(code="PURCHASE", name="采购", status="ENABLED")
    db.session.add_all([admin, organization, source])
    db.session.commit()

    content = (
        "资产编码,所属公司,资产名称,资产分类,计量单位,金额,采购日期,"
        "供应商,责任管理员,资产来源,存放地点,使用公司,使用部门,使用人\n"
        "EMPTY-UNIT-ASSET,资产公司,网络设备,电子产品及通信设备/网络设备/其他,台,"
        "1000,2026-01-01,,admin,PURCHASE,,资产公司,,\n"
    ).encode()
    preview = _upload(
        client, headers, "ASSET", content, "asset-empty-units.csv"
    ).get_json()["data"]
    assert preview["status"] == "PREVIEW_READY"
    row = preview["rows"][0]
    assert row["errors"] == []
    assert any("默认计量单位：台" in action for action in row["auto_actions"])
    assert row["normalized"]["category_default_unit_name"] == "台"

    confirmed = client.post(
        f"/api/v1/imports/{preview['id']}/confirm",
        headers=headers,
        json={"confirmed": True, "version": preview["version"]},
    ).get_json()["data"]
    assert confirmed["status"] == "CONFIRMED"
    unit = db.session.scalar(db.select(Unit).where(Unit.name == "台"))
    assert unit is not None and unit.status == "ENABLED"
    category = db.session.scalar(
        db.select(AssetCategory).where(AssetCategory.name == "其他")
    )
    assert category is not None and category.default_unit_id == unit.id
    asset = db.session.scalar(
        db.select(Asset).where(Asset.asset_code == "EMPTY-UNIT-ASSET")
    )
    assert asset is not None and asset.category_id == category.id
    assert asset.unit_id == unit.id


def test_asset_import_keeps_location_empty_when_holder_exists(client) -> None:
    _, headers = _actor(client, ["asset:import"])
    admin = User(
        username="admin",
        nickname="Admin",
        password=hash_password(_PASSWORD),
        enabled=True,
    )
    holder = User(
        username="holder01",
        nickname="张三",
        password=hash_password(_PASSWORD),
        enabled=True,
    )
    organization = Organization(code="EMPTY-LOC-ORG", name="资产公司", status="ENABLED")
    unit = Unit(code="EMPTY-LOC-UNIT", name="台", status="ENABLED")
    source = AssetSource(code="PURCHASE", name="采购", status="ENABLED")
    db.session.add_all([admin, holder, organization, unit, source])
    db.session.flush()
    category = AssetCategory(
        code="EMPTY-LOC-CAT",
        name="笔记本电脑",
        service_life_months=36,
        default_unit_id=unit.id,
        status="ENABLED",
    )
    db.session.add(category)
    db.session.commit()

    content = (
        "资产编码,所属公司,资产名称,资产分类,计量单位,金额,采购日期,"
        "供应商,责任管理员,资产来源,存放地点,使用公司,使用部门,使用人\n"
        "EMPTY-LOC-HOLDER,资产公司,员工电脑,笔记本电脑,台,6000,2026-01-01,,admin,PURCHASE,,资产公司,,张三\n"
        "EMPTY-LOC-IDLE,资产公司,库存电脑,笔记本电脑,台,6000,2026-01-01,,admin,PURCHASE,,资产公司,,\n"
    ).encode()
    preview = _upload(
        client, headers, "ASSET", content, "empty-location.csv"
    ).get_json()["data"]

    assert preview["status"] == "PREVIEW_READY"
    holder_row, idle_row = preview["rows"]
    assert any("存放地点将保持为空" in action for action in holder_row["auto_actions"])
    assert any("待补充存放地点" in action for action in idle_row["auto_actions"])
    assert holder_row["normalized"]["location_keep_empty"] is True
    assert idle_row["normalized"]["location_keep_empty"] is False

    confirmed = client.post(
        f"/api/v1/imports/{preview['id']}/confirm",
        headers=headers,
        json={"confirmed": True, "version": preview["version"]},
    ).get_json()["data"]
    assert confirmed["status"] == "CONFIRMED"
    holder_asset = db.session.scalar(
        db.select(Asset).where(Asset.asset_code == "EMPTY-LOC-HOLDER")
    )
    idle_asset = db.session.scalar(
        db.select(Asset).where(Asset.asset_code == "EMPTY-LOC-IDLE")
    )
    pending_location = db.session.scalar(
        db.select(AssetLocation).where(AssetLocation.name == "待补充存放地点")
    )
    assert holder_asset is not None
    assert holder_asset.holder_user_id == holder.id
    assert holder_asset.location_id is None
    assert holder_asset.custom_attributes["location_import_policy"] == (
        "HOLDER_EXISTS_KEEP_EMPTY"
    )
    assert holder_asset.data_completeness == "COMPLETE"
    assert idle_asset is not None
    assert pending_location is not None
    assert idle_asset.location_id == pending_location.id
    assert idle_asset.custom_attributes["pending_location"] is True
    assert idle_asset.data_completeness == "INCOMPLETE"


def test_asset_import_accepts_legacy_history_export(client) -> None:
    actor, headers = _actor(client, ["asset:import"])
    admin = User(
        username="admin",
        nickname="Admin",
        password=hash_password(_PASSWORD),
        enabled=True,
    )
    organization = Organization(
        code="LEGACY-ORG", name="上海黄豆网络科技有限公司", status="ENABLED"
    )
    public = Organization(code="LEGACY-PUBLIC", name="黄豆公共", status="ENABLED")
    department = Organization(
        code="LEGACY-DEPT",
        name="IP多元化事业部/增长组",
        parent_id=organization.id,
        status="ENABLED",
    )
    unit = Unit(code="GE", name="个", status="ENABLED")
    source = AssetSource(code="1", name="购入", status="ENABLED")
    db.session.add_all([admin, organization, public, department, unit, source])
    db.session.flush()
    root = AssetCategory(
        code="LEGACY-CAT-ROOT",
        name="电子产品及通信设备",
        service_life_months=36,
        default_unit_id=unit.id,
        status="ENABLED",
    )
    db.session.add(root)
    db.session.flush()
    parent = AssetCategory(
        code="LEGACY-CAT-PUBLIC",
        name="公共电子设备",
        parent_id=root.id,
        service_life_months=36,
        default_unit_id=unit.id,
        status="ENABLED",
    )
    db.session.add(parent)
    db.session.flush()
    category = AssetCategory(
        code="LEGACY-CAT-VIDEO",
        name="影音设备",
        parent_id=parent.id,
        service_life_months=36,
        default_unit_id=unit.id,
        status="ENABLED",
    )
    db.session.add(category)
    db.session.commit()

    headers_text = ",".join(
        [
            "状态",
            "签字状态",
            "资产编码",
            "使用人",
            "资产名称",
            "主资产编码",
            "主附状态",
            "RFID",
            "资产类别",
            "规格型号",
            "标签",
            "设备序列号",
            "计量单位",
            "金额",
            "使用公司",
            "使用部门",
            "区域名称(短)",
            "区域名称",
            "存放地点",
            "管理人",
            "所属公司",
            "购入日期",
            "供应商",
            "使用期限",
            "来源",
            "创建人",
            "创建时间",
            "修改时间",
            "入库 / 收货单号",
            "单据类型",
            "处理时间",
            "处理人",
            "处理内容",
        ]
    )
    common = [
        "在用",
        "已签字",
        "LEGACY-0001",
        "",
        "历史内存卡",
        "",
        "",
        "",
        "电子产品及通信设备/公共电子设备/影音设备",
        "256GB",
        "",
        "",
        "个",
        "229.00",
        "上海黄豆网络科技有限公司",
        "IP多元化事业部/增长组",
        "北京",
        "北京",
        "",
        "历史系统管理员",
        "上海黄豆网络科技有限公司",
        "2025-10-21",
        "",
        "36",
        "1",
        "Admin",
        "2025-10-21 10:36",
        "2026-08-04",
        "",
        "资产修改",
        "2026-01-30",
        "Admin",
        "【备注】字段由【<空>】变更为【测试】;",
    ]
    # Use a generated minimal XLSX through the service's template helper.
    from app.services.import_service import _xlsx_bytes

    rows = [["资产履历"], [], headers_text.split(","), common]
    content = _xlsx_bytes(rows, "资产履历")
    response = _upload(
        client, headers, "ASSET", content, "资产履历_20261014_172038.xlsx"
    )
    assert response.status_code == 200
    preview = response.get_json()["data"]
    assert preview["status"] == "PREVIEW_READY", preview["rows"][0]["errors"]
    assert preview["create_count"] == 1
    assert preview["rows"][0]["values"]["履历条数"] == "1"

    confirmed = client.post(
        f"/api/v1/imports/{preview['id']}/confirm",
        headers=headers,
        json={"confirmed": True, "version": preview["version"]},
    )
    assert confirmed.status_code == 200
    asset = db.session.scalar(db.select(Asset).where(Asset.asset_code == "LEGACY-0001"))
    assert asset is not None
    assert asset.status == "IN_USE"
    assert asset.usage_department_id == department.id
    assert asset.manager_id == admin.id
    assert asset.holder_user_id is None
    assert (
        db.session.scalar(
            db.select(AssetLifecycleRecord).where(
                AssetLifecycleRecord.asset_id == asset.id,
                AssetLifecycleRecord.operation_type == "资产修改",
            )
        )
        is not None
    )


def test_legacy_history_import_keeps_unmatched_department_and_holder_text(
    client,
) -> None:
    _, headers = _actor(client, ["asset:import"])
    admin = User(
        username="admin",
        nickname="Admin",
        password=hash_password(_PASSWORD),
        enabled=True,
    )
    organization = Organization(
        code="LEGACY-ORG-2", name="上海黄豆网络科技有限公司", status="ENABLED"
    )
    unit = Unit(code="TAI", name="台", status="ENABLED")
    db.session.add_all([admin, organization, unit])
    db.session.flush()
    category = AssetCategory(
        code="电子产品及通信设备/公共电子设备/影音设备",
        name="影音设备",
        service_life_months=36,
        default_unit_id=unit.id,
        status="ENABLED",
    )
    db.session.add(category)
    db.session.commit()

    headers_text = ",".join(
        [
            "状态",
            "资产编码",
            "使用人",
            "资产名称",
            "资产类别",
            "规格型号",
            "设备序列号",
            "计量单位",
            "金额",
            "使用公司",
            "使用部门",
            "区域名称",
            "存放地点",
            "管理人",
            "所属公司",
            "购入日期",
            "供应商",
            "使用期限",
            "来源",
            "入库 / 收货单号",
            "单据类型",
            "处理时间",
            "处理人",
            "处理内容",
        ]
    )
    row = [
        "在用",
        "LEGACY-0002",
        "历史离职员工",
        "历史显示器",
        "电子产品及通信设备/公共电子设备/影音设备",
        "27 寸",
        "",
        "台",
        "229.00",
        "上海黄豆网络科技有限公司",
        "历史组织/历史部门",
        "北京",
        "",
        "历史管理员",
        "上海黄豆网络科技有限公司",
        "2025-10-21",
        "",
        "36",
        "1",
        "",
        "资产修改",
        "2026-01-30",
        "历史处理人",
        "历史记录",
    ]
    from app.services.import_service import _xlsx_bytes

    content = _xlsx_bytes([["资产履历"], [], headers_text.split(","), row], "资产履历")
    response = _upload(
        client, headers, "ASSET", content, "资产履历_20261014_172038.xlsx"
    )
    preview = response.get_json()["data"]
    assert preview["status"] == "PREVIEW_READY", preview["rows"][0]
    assert preview["rows"][0]["errors"] == []
    assert preview["rows"][0]["warnings"] == ["资产来源待补充"]

    confirmed = client.post(
        f"/api/v1/imports/{preview['id']}/confirm",
        headers=headers,
        json={"confirmed": True, "version": preview["version"]},
    )
    assert confirmed.status_code == 200
    asset = db.session.scalar(db.select(Asset).where(Asset.asset_code == "LEGACY-0002"))
    holder = db.session.scalar(db.select(User).where(User.nickname == "历史离职员工"))
    assert asset is not None
    assert holder is not None
    assert holder.feishu_open_id is None
    assert holder.feishu_sync_status == "UNSYNCED"
    assert asset.usage_department_id is None
    assert asset.holder_user_id == holder.id
    assert asset.manager_id == admin.id
    originals = asset.custom_attributes["import_originals"]
    assert originals["usage_department"] == "历史组织/历史部门"
    assert originals["manager"] == "历史管理员"


def test_legacy_history_import_matches_department_path_and_holder_fallback(
    client,
) -> None:
    actor, headers = _actor(client, ["asset:import"])
    admin = User(
        username="admin",
        nickname="Admin",
        password=hash_password(_PASSWORD),
        enabled=True,
    )
    organization = Organization(
        code="LEGACY-PATH-ORG", name="上海黄豆网络科技有限公司", status="ENABLED"
    )
    db.session.add_all([admin, organization])
    db.session.flush()
    department = Organization(
        code="LEGACY-PATH-DEPT",
        name="IT&安全",
        parent_id=organization.id,
        status="ENABLED",
    )
    holder = User(
        username="legacy-holder",
        nickname="刘智愚",
        password=hash_password(_PASSWORD),
        enabled=True,
        organization_id=department.id,
    )
    unit = Unit(code="TAI", name="台", status="ENABLED")
    db.session.add_all([department, holder, unit])
    db.session.flush()
    holder.organization_id = department.id
    category = AssetCategory(
        code="LEGACY-PATH-CAT",
        name="影音设备",
        service_life_months=36,
        default_unit_id=unit.id,
        status="ENABLED",
    )
    db.session.add(category)
    db.session.commit()

    headers_text = ",".join(
        [
            "状态",
            "资产编码",
            "使用人",
            "资产名称",
            "资产类别",
            "规格型号",
            "设备序列号",
            "计量单位",
            "金额",
            "使用公司",
            "使用部门",
            "区域名称",
            "存放地点",
            "管理人",
            "所属公司",
            "购入日期",
            "供应商",
            "使用期限",
            "来源",
            "入库 / 收货单号",
            "单据类型",
            "处理时间",
            "处理人",
            "处理内容",
        ]
    )
    rows = [
        [
            "在用",
            "LEGACY-PATH-0001",
            "刘智愚",
            "员工电脑",
            "影音设备",
            "",
            "",
            "台",
            "6000.00",
            "上海黄豆网络科技有限公司",
            "上海黄豆网络科技有限公司/IT&安全",
            "",
            "",
            "Admin",
            "上海黄豆网络科技有限公司",
            "2025-10-21",
            "",
            "36",
            "1",
            "",
            "",
            "",
            "",
            "",
        ],
        [
            "在用",
            "LEGACY-PATH-0002",
            "刘智愚",
            "员工显示器",
            "影音设备",
            "",
            "",
            "台",
            "2000.00",
            "上海黄豆网络科技有限公司",
            "不存在的组织/不存在的部门",
            "",
            "",
            "Admin",
            "上海黄豆网络科技有限公司",
            "2025-10-21",
            "",
            "36",
            "1",
            "",
            "",
            "",
            "",
            "",
        ],
    ]
    from app.services.import_service import _xlsx_bytes

    content = _xlsx_bytes(
        [["资产履历"], [], headers_text.split(","), *rows], "资产履历"
    )
    assert holder.organization_id == department.id
    assert db.session.get(User, holder.id).organization_id == department.id
    preview = _upload(
        client, headers, "ASSET", content, "资产履历_20261014_172038.xlsx"
    ).get_json()["data"]
    assert preview["status"] == "PREVIEW_READY"
    assert all(row["errors"] == [] for row in preview["rows"])
    assert [row["normalized"]["usage_department_id"] for row in preview["rows"]] == [
        department.id,
        department.id,
    ]
    confirmed = client.post(
        f"/api/v1/imports/{preview['id']}/confirm",
        headers=headers,
        json={"confirmed": True, "version": preview["version"]},
    )
    assert confirmed.status_code == 200
    first = db.session.scalar(
        db.select(Asset).where(Asset.asset_code == "LEGACY-PATH-0001")
    )
    second = db.session.scalar(
        db.select(Asset).where(Asset.asset_code == "LEGACY-PATH-0002")
    )
    assert first is not None
    assert first.usage_department_id == department.id
    assert first.holder_user_id == holder.id
    assert second is not None
    assert second.usage_department_id == department.id
    assert second.holder_user_id == holder.id


def test_import_auto_creates_supplier_location_and_public_object(client) -> None:
    actor, headers = _actor(client, ["asset:import"])
    admin = User(
        username="admin",
        nickname="Admin",
        password=hash_password(_PASSWORD),
        enabled=True,
    )
    organization = Organization(code="AUTO-ORG", name="资产公司", status="ENABLED")
    public = Organization(code="AUTO-PUBLIC", name="黄豆公共", status="ENABLED")
    unit = Unit(code="TAI", name="台", status="ENABLED")
    db.session.add_all([admin, organization, public, unit])
    db.session.flush()
    category = AssetCategory(
        code="AUTO-CAT",
        name="影音设备",
        service_life_months=36,
        default_unit_id=unit.id,
        status="ENABLED",
    )
    db.session.add(category)
    db.session.commit()

    headers_text = ",".join(
        [
            "状态",
            "资产编码",
            "使用人",
            "资产名称",
            "资产类别",
            "规格型号",
            "设备序列号",
            "计量单位",
            "金额",
            "使用公司",
            "使用部门",
            "区域名称(短)",
            "区域名称",
            "存放地点",
            "管理人",
            "所属公司",
            "购入日期",
            "供应商",
            "使用期限",
            "来源",
            "创建人",
            "创建时间",
            "修改时间",
            "入库 / 收货单号",
            "单据类型",
            "处理时间",
            "处理人",
            "处理内容",
        ]
    )
    row = [
        "在用",
        "AUTO-0001",
        "IT设备组",
        "公共显示器",
        "影音设备",
        "",
        "",
        "台",
        "229.00",
        "黄豆公共",
        "",
        "上海",
        "上海",
        "海粟",
        "历史管理员",
        "资产公司",
        "2025-10-21",
        "京东",
        "36",
        "",
        "Admin",
        "2025-10-21 10:36",
        "2026-08-04",
        "",
        "",
        "",
        "",
    ]
    from app.services.import_service import _xlsx_bytes

    content = _xlsx_bytes([["资产履历"], [], headers_text.split(","), row], "资产履历")
    response = _upload(client, headers, "ASSET", content, "auto-history.xlsx")
    assert response.status_code == 200
    preview = response.get_json()["data"]
    assert preview["status"] == "PREVIEW_READY"
    assert any("供应商" in action for action in preview["rows"][0]["auto_actions"])
    assert any("存放地点" in action for action in preview["rows"][0]["auto_actions"])
    assert any(
        "公共使用对象" in action for action in preview["rows"][0]["auto_actions"]
    )

    confirmed = client.post(
        f"/api/v1/imports/{preview['id']}/confirm",
        headers=headers,
        json={"confirmed": True, "version": preview["version"]},
    ).get_json()["data"]
    assert confirmed["status"] == "CONFIRMED"
    supplier = db.session.scalar(db.select(Supplier).where(Supplier.name == "京东"))
    public_object = db.session.scalar(
        db.select(PublicUsageObject).where(PublicUsageObject.name == "IT设备组")
    )
    region = db.session.scalar(
        db.select(AssetLocation).where(
            AssetLocation.name == "上海", AssetLocation.parent_id.is_(None)
        )
    )
    location = db.session.scalar(
        db.select(AssetLocation).where(
            AssetLocation.name == "海粟", AssetLocation.parent_id == region.id
        )
    )
    asset = db.session.scalar(db.select(Asset).where(Asset.asset_code == "AUTO-0001"))
    assert supplier and asset and asset.supplier_id == supplier.id
    assert public_object and asset.public_object_id == public_object.id
    assert region and location and asset.location_id == location.id
    assert confirmed["result"]["auto_created_master_data"]


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
