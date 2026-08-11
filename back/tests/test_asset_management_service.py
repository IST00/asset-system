"""Focused regression tests for asset maintenance commands."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest
from marshmallow import ValidationError
from sqlalchemy import select

from app.common import BusinessException, ResultCode
from app.enums import (
    ApprovalChannel,
    ApprovalExecutionMode,
    ApprovalStatus,
    AssetDataCompleteness,
    AssetStatus,
    DataScope,
    ExecutionStatus,
    RecordStatus,
)
from app.extensions import db
from app.models import (
    Asset,
    AssetBusinessLock,
    AssetCategory,
    AssetLifecycleRecord,
    AssetLocation,
    AssetSource,
    OperationLog,
    OperationRequest,
    Organization,
    Permission,
    Role,
    RolePermission,
    Unit,
    User,
    UserRole,
)
from app.schemas.asset_management import (
    RepairCompleteSchema,
    RepairStartSchema,
    ScrapAssetsSchema,
)
from app.security.passwords import hash_password
from app.services import asset_management_service


def _actor_with_permissions(
    *permission_codes: str,
    username: str = "asset-manager",
    data_scope: str = DataScope.ALL.value,
    organization_id: int | None = None,
) -> User:
    user = User(
        username=username,
        password=hash_password("admin123"),
        enabled=True,
        organization_id=organization_id,
    )
    role = Role(
        code=f"{username.upper()}_ROLE",
        name=f"{username}角色",
        data_scope=data_scope,
    )
    db.session.add_all([user, role])
    db.session.flush()
    db.session.add(UserRole(user_id=user.id, role_id=role.id))
    for code in permission_codes:
        permission = db.session.scalar(
            select(Permission).where(Permission.code == code)
        )
        if permission is None:
            permission = Permission(code=code, name=code, module=code.split(":")[0])
            db.session.add(permission)
            db.session.flush()
        db.session.add(RolePermission(role_id=role.id, permission_id=permission.id))
    db.session.commit()
    return user


@dataclass(frozen=True)
class AssetManagementContext:
    actor: User
    holder: User
    organization: Organization
    other_organization: Organization
    location: AssetLocation
    other_location: AssetLocation
    assets: tuple[Asset, Asset, Asset]


def _seed_context() -> AssetManagementContext:
    actor = _actor_with_permissions(
        "asset:view",
        "asset:amount:view",
        "asset:edit",
        "asset:relation:manage",
        "public-object:manage",
        "asset:transfer",
        "asset:repair",
        "asset:scrap",
    )
    organization = Organization(code="AM-ORG", name="资产公司")
    other_organization = Organization(code="AM-OTHER", name="其它公司")
    unit = Unit(code="AM-UNIT", name="台")
    source = AssetSource(code="AM-SOURCE", name="采购")
    location = AssetLocation(code="AM-LOC-1", name="一号仓", is_selectable=True)
    other_location = AssetLocation(code="AM-LOC-2", name="二号仓", is_selectable=True)
    holder = User(username="asset-holder", password="x", enabled=True)
    db.session.add_all(
        [
            organization,
            other_organization,
            unit,
            source,
            location,
            other_location,
            holder,
        ]
    )
    db.session.flush()
    actor.organization_id = organization.id
    holder.organization_id = other_organization.id
    category = AssetCategory(
        code="AM-CATEGORY",
        name="电脑",
        service_life_months=36,
        default_unit_id=unit.id,
    )
    db.session.add(category)
    db.session.flush()
    assets = tuple(
        Asset(
            asset_code=f"AM-ASSET-{index}",
            asset_name=f"测试资产 {index}",
            status=AssetStatus.IDLE.value,
            organization_id=organization.id,
            category_id=category.id,
            unit_id=unit.id,
            original_amount=Decimal("1000.00"),
            purchase_date=date(2026, 1, 1),
            service_life_months=36,
            expected_expiry_date=date(2029, 1, 1),
            manager_id=actor.id,
            source_id=source.id,
            location_id=location.id,
            custom_attributes={},
            data_completeness=AssetDataCompleteness.COMPLETE.value,
        )
        for index in range(1, 4)
    )
    db.session.add_all(assets)
    db.session.commit()
    return AssetManagementContext(
        actor=actor,
        holder=holder,
        organization=organization,
        other_organization=other_organization,
        location=location,
        other_location=other_location,
        assets=assets,
    )


def _headers(client, actor: User) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": actor.username, "password": "admin123"},
    )
    token = response.get_json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def test_public_object_code_uses_six_digit_sequence(app) -> None:
    actor = _actor_with_permissions("public-object:manage")

    result = asset_management_service.create_public_object(
        {"name": "一号会议室"}, actor.id
    )

    assert result["code"] == "PUB000001"


def test_public_object_rejects_blank_name(app) -> None:
    actor = _actor_with_permissions("public-object:manage")

    with pytest.raises(BusinessException, match="公共使用对象名称不能为空"):
        asset_management_service.create_public_object({"name": "   "}, actor.id)


def test_public_object_update_rejects_blank_name(app) -> None:
    actor = _actor_with_permissions("public-object:manage")
    created = asset_management_service.create_public_object(
        {"name": "二号会议室"}, actor.id
    )

    with pytest.raises(BusinessException, match="公共使用对象名称不能为空"):
        asset_management_service.update_public_object(
            created["id"], {"name": "   "}, actor.id
        )


@pytest.mark.parametrize(
    ("schema", "payload"),
    [
        (
            RepairStartSchema(),
            {
                "items": [{"asset_id": 1, "version": 1}],
                "estimated_cost": "-0.01",
                "reason": "设备故障",
            },
        ),
        (
            RepairCompleteSchema(),
            {
                "items": [{"asset_id": 1, "version": 1}],
                "actual_cost": "-0.01",
                "result": "维修完成",
            },
        ),
        (
            ScrapAssetsSchema(),
            {
                "items": [{"asset_id": 1, "version": 1}],
                "scrap_date": "2026-08-11",
                "scrap_amount": "-0.01",
                "child_action": "BLOCK",
                "reason": "无维修价值",
            },
        ),
    ],
)
def test_lifecycle_schemas_reject_negative_amounts(schema, payload: dict) -> None:
    with pytest.raises(ValidationError):
        schema.load(payload)


def test_scrap_schema_requires_recovery_amount() -> None:
    with pytest.raises(ValidationError):
        ScrapAssetsSchema().load(
            {
                "items": [{"asset_id": 1, "version": 1}],
                "scrap_date": "2026-08-11",
                "child_action": "BLOCK",
                "reason": "无维修价值",
            }
        )


def test_batch_update_recomputes_expiry_completeness_and_audit(app) -> None:
    context = _seed_context()
    first, second, _third = context.assets

    result = asset_management_service.update_batch(
        {
            "items": [
                {"asset_id": first.id, "version": first.version},
                {"asset_id": second.id, "version": second.version},
            ],
            "changes": {
                "purchase_date": date(2026, 1, 31),
                "service_life_months": 1,
                "location_id": None,
                "remark": "  批量核对完成  ",
            },
            "reason": "批量修正资料",
        },
        context.actor.id,
    )

    assert result["updated_count"] == 2
    assert result["batch_no"].startswith("AED")
    db.session.expire_all()
    updated = [db.session.get(Asset, item.id) for item in (first, second)]
    assert all(item is not None for item in updated)
    assert [item.expected_expiry_date for item in updated if item is not None] == [
        date(2026, 2, 28),
        date(2026, 2, 28),
    ]
    assert [item.data_completeness for item in updated if item is not None] == [
        AssetDataCompleteness.INCOMPLETE.value,
        AssetDataCompleteness.INCOMPLETE.value,
    ]
    assert [item.remark for item in updated if item is not None] == [
        "批量核对完成",
        "批量核对完成",
    ]
    assert (
        db.session.scalar(
            select(OperationLog).where(OperationLog.action == "ASSET_BATCH_EDIT")
        ).reason
        == "批量修正资料"
    )
    lifecycle = db.session.scalars(
        select(AssetLifecycleRecord).where(
            AssetLifecycleRecord.operation_type == "ASSET_EDIT"
        )
    ).all()
    assert {item.asset_id for item in lifecycle} == {first.id, second.id}


def test_batch_update_rejects_stale_version_without_partial_mutation(app) -> None:
    context = _seed_context()
    first, second, _third = context.assets

    with pytest.raises(BusinessException, match="已被修改"):
        asset_management_service.update_batch(
            {
                "items": [
                    {"asset_id": first.id, "version": first.version},
                    {"asset_id": second.id, "version": second.version + 1},
                ],
                "changes": {"remark": "不应保存"},
                "reason": "并发版本测试",
            },
            context.actor.id,
        )

    db.session.expire_all()
    assert db.session.get(Asset, first.id).remark is None
    assert db.session.get(Asset, second.id).remark is None
    assert db.session.scalar(select(OperationLog.id)) is None


def test_batch_update_rejects_duplicate_targets(app) -> None:
    context = _seed_context()
    asset = context.assets[0]

    with pytest.raises(BusinessException, match="资产不能重复选择"):
        asset_management_service.update_batch(
            {
                "items": [
                    {"asset_id": asset.id, "version": asset.version},
                    {"asset_id": asset.id, "version": asset.version},
                ],
                "changes": {"remark": "不应保存"},
                "reason": "重复资产测试",
            },
            context.actor.id,
        )


def test_batch_update_respects_business_lock(app) -> None:
    context = _seed_context()
    asset = context.assets[0]
    operation = OperationRequest(
        request_no="AM-LOCK-001",
        operation_type="TRANSFER",
        applicant_id=context.actor.id,
        approval_channel=ApprovalChannel.INTERNAL.value,
        approval_execution_mode=ApprovalExecutionMode.AUTO_ON_APPROVAL.value,
        approval_status=ApprovalStatus.PENDING.value,
        execution_status=ExecutionStatus.NOT_STARTED.value,
    )
    db.session.add(operation)
    db.session.flush()
    db.session.add(
        AssetBusinessLock(
            asset_id=asset.id,
            operation_request_id=operation.id,
            operation_type=operation.operation_type,
            applicant_id=context.actor.id,
        )
    )
    db.session.commit()

    with pytest.raises(BusinessException, match="正在处理其它业务"):
        asset_management_service.update_one(
            asset.id,
            {"version": asset.version, "remark": "不应保存", "reason": "锁定测试"},
            context.actor.id,
        )

    db.session.expire_all()
    assert db.session.get(Asset, asset.id).remark is None


def test_batch_update_hides_cross_scope_asset_as_not_found(app) -> None:
    context = _seed_context()
    asset = context.assets[0]
    asset.organization_id = context.other_organization.id
    db.session.commit()
    scoped_actor = _actor_with_permissions(
        "asset:view",
        "asset:edit",
        username="scoped-manager",
        data_scope=DataScope.DEPARTMENT.value,
        organization_id=context.organization.id,
    )

    with pytest.raises(BusinessException) as raised:
        asset_management_service.update_one(
            asset.id,
            {"version": asset.version, "remark": "越权修改", "reason": "范围测试"},
            scoped_actor.id,
        )

    assert raised.value.code == ResultCode.NOT_FOUND.code
    db.session.expire_all()
    assert db.session.get(Asset, asset.id).remark is None


def test_relation_attach_and_detach_syncs_then_preserves_usage_state(app) -> None:
    context = _seed_context()
    main, child, _third = context.assets
    main.status = AssetStatus.IN_USE.value
    main.usage_type = "PERSONAL"
    main.holder_user_id = context.holder.id
    main.usage_department_id = context.holder.organization_id
    main.location_id = context.other_location.id
    db.session.commit()

    attached = asset_management_service.attach(
        main.id,
        {"child_ids": [child.id], "reason": "组成办公套装"},
        context.actor.id,
    )

    assert [item["id"] for item in attached["attachments"]] == [child.id]
    db.session.expire_all()
    attached_child = db.session.get(Asset, child.id)
    assert attached_child.parent_asset_id == main.id
    assert attached_child.status == AssetStatus.IN_USE.value
    assert attached_child.usage_type == "PERSONAL"
    assert attached_child.holder_user_id == context.holder.id
    assert attached_child.usage_department_id == context.holder.organization_id
    assert attached_child.location_id == context.other_location.id

    detached = asset_management_service.detach(
        main.id,
        {"child_ids": [child.id], "reason": "拆分办公套装"},
        context.actor.id,
    )

    assert detached["attachments"] == []
    db.session.expire_all()
    detached_child = db.session.get(Asset, child.id)
    assert detached_child.parent_asset_id is None
    assert detached_child.status == AssetStatus.IN_USE.value
    assert detached_child.holder_user_id == context.holder.id
    lifecycle = db.session.scalars(
        select(AssetLifecycleRecord).where(
            AssetLifecycleRecord.operation_type.in_(
                ["ASSET_RELATION_ATTACH", "ASSET_RELATION_DETACH"]
            )
        )
    ).all()
    assert len(lifecycle) == 4


def test_relation_rejects_nested_and_scrapped_assets(app) -> None:
    context = _seed_context()
    main, child, nested = context.assets
    nested.parent_asset_id = child.id
    db.session.commit()

    with pytest.raises(BusinessException, match="已有附属资产"):
        asset_management_service.attach(
            main.id,
            {"child_ids": [child.id], "reason": "禁止多层关系"},
            context.actor.id,
        )

    nested.parent_asset_id = None
    child.status = AssetStatus.SCRAPPED.value
    db.session.commit()
    with pytest.raises(BusinessException, match="已报废资产"):
        asset_management_service.attach(
            main.id,
            {"child_ids": [child.id], "reason": "禁止报废资产"},
            context.actor.id,
        )


def test_public_object_list_update_duplicate_and_usage_count(app) -> None:
    context = _seed_context()
    first = asset_management_service.create_public_object(
        {"name": "三号会议室"}, context.actor.id
    )
    second = asset_management_service.create_public_object(
        {"name": "四号会议室"}, context.actor.id
    )
    asset_management_service.update_public_object(
        second["id"], {"status": RecordStatus.DISABLED.value}, context.actor.id
    )
    asset = context.assets[0]
    asset.status = AssetStatus.IN_USE.value
    asset.usage_type = "PUBLIC"
    asset.public_object_id = first["id"]
    db.session.commit()

    enabled = asset_management_service.list_public_objects(context.actor.id)
    all_items = asset_management_service.list_public_objects(
        context.actor.id, include_disabled=True
    )

    assert [(item["name"], item["usage_count"]) for item in enabled] == [
        ("三号会议室", 1)
    ]
    assert [item["status"] for item in all_items] == [
        RecordStatus.ENABLED.value,
        RecordStatus.DISABLED.value,
    ]
    with pytest.raises(BusinessException, match="名称已存在"):
        asset_management_service.update_public_object(
            second["id"], {"name": "三号会议室"}, context.actor.id
        )


def test_transfer_execution_expands_direct_children(app) -> None:
    context = _seed_context()
    main, child, _third = context.assets
    child.parent_asset_id = main.id
    db.session.commit()

    result = asset_management_service.transfer(
        {
            "items": [{"asset_id": main.id, "version": main.version}],
            "holder_user_id": context.holder.id,
            "location_id": context.other_location.id,
            "reason": "审批通过后执行调拨",
        },
        context.actor.id,
    )

    assert result["updated_count"] == 2
    db.session.expire_all()
    transferred = [db.session.get(Asset, item.id) for item in (main, child)]
    assert [item.status for item in transferred if item is not None] == [
        AssetStatus.IN_USE.value,
        AssetStatus.IN_USE.value,
    ]
    assert [item.holder_user_id for item in transferred if item is not None] == [
        context.holder.id,
        context.holder.id,
    ]
    assert [item.location_id for item in transferred if item is not None] == [
        context.other_location.id,
        context.other_location.id,
    ]
    assert [item.organization_id for item in transferred if item is not None] == [
        context.organization.id,
        context.organization.id,
    ]


def test_repair_execution_restores_each_assets_previous_status(app) -> None:
    context = _seed_context()
    idle, in_use, _third = context.assets
    in_use.status = AssetStatus.IN_USE.value
    in_use.usage_type = "PERSONAL"
    in_use.holder_user_id = context.holder.id
    db.session.commit()

    started = asset_management_service.repair_start(
        {
            "items": [
                {"asset_id": idle.id, "version": idle.version},
                {"asset_id": in_use.id, "version": in_use.version},
            ],
            "vendor": "授权维修中心",
            "estimated_cost": Decimal("500.00"),
            "reason": "设备故障送修",
        },
        context.actor.id,
    )
    completed = asset_management_service.repair_complete(
        {
            "items": [
                {"asset_id": item["id"], "version": item["version"]}
                for item in started["items"]
            ],
            "actual_cost": Decimal("450.00"),
            "result": "维修后测试通过",
        },
        context.actor.id,
    )

    assert [item["status"] for item in completed["items"]] == [
        AssetStatus.IDLE.value,
        AssetStatus.IN_USE.value,
    ]
    db.session.expire_all()
    repaired = [db.session.get(Asset, item.id) for item in (idle, in_use)]
    assert all("repair_context" not in item.custom_attributes for item in repaired)
    assert all(
        item.custom_attributes["last_repair"]["actual_cost"] == "450.00"
        for item in repaired
    )


def test_repair_execution_rejects_invalid_status_without_audit(app) -> None:
    context = _seed_context()
    asset = context.assets[0]
    asset.status = AssetStatus.SCRAPPED.value
    db.session.commit()

    with pytest.raises(BusinessException, match="当前状态不允许"):
        asset_management_service.repair_start(
            {
                "items": [{"asset_id": asset.id, "version": asset.version}],
                "reason": "不应送修",
            },
            context.actor.id,
        )

    db.session.expire_all()
    assert db.session.get(Asset, asset.id).status == AssetStatus.SCRAPPED.value
    assert db.session.scalar(select(AssetLifecycleRecord.id)) is None
    assert db.session.scalar(select(OperationLog.id)) is None


def test_scrap_execution_blocks_or_detaches_direct_children(app) -> None:
    context = _seed_context()
    main, child, _third = context.assets
    child.parent_asset_id = main.id
    db.session.commit()
    base_payload = {
        "items": [{"asset_id": main.id, "version": main.version}],
        "scrap_date": date(2026, 8, 11),
        "scrap_amount": Decimal("100.00"),
        "reason": "审批通过后执行报废",
    }

    with pytest.raises(BusinessException, match="仍有关联附属资产"):
        asset_management_service.scrap(
            {**base_payload, "child_action": "BLOCK"}, context.actor.id
        )

    result = asset_management_service.scrap(
        {**base_payload, "child_action": "DETACH"}, context.actor.id
    )

    assert result["updated_count"] == 1
    db.session.expire_all()
    scrapped_main = db.session.get(Asset, main.id)
    detached_child = db.session.get(Asset, child.id)
    assert scrapped_main.status == AssetStatus.SCRAPPED.value
    assert scrapped_main.custom_attributes["scrap"] == {
        "scrap_date": "2026-08-11",
        "scrap_amount": "100.00",
    }
    assert detached_child.parent_asset_id is None
    assert detached_child.status == AssetStatus.IDLE.value


def test_scrap_execution_can_include_direct_children(app) -> None:
    context = _seed_context()
    main, child, _third = context.assets
    child.parent_asset_id = main.id
    db.session.commit()

    result = asset_management_service.scrap(
        {
            "items": [{"asset_id": main.id, "version": main.version}],
            "scrap_date": date(2026, 8, 11),
            "scrap_amount": Decimal("0.00"),
            "child_action": "SCRAP",
            "reason": "整套设备完成审批后报废",
        },
        context.actor.id,
    )

    assert result["updated_count"] == 2
    db.session.expire_all()
    assert [db.session.get(Asset, item.id).status for item in (main, child)] == [
        AssetStatus.SCRAPPED.value,
        AssetStatus.SCRAPPED.value,
    ]


def test_asset_update_http_boundary_validates_and_persists(client) -> None:
    context = _seed_context()
    asset = context.assets[0]
    headers = _headers(client, context.actor)

    invalid = client.post(
        f"/api/v1/assets/{asset.id}/update",
        headers=headers,
        json={"version": asset.version, "reason": "没有修改字段"},
    ).get_json()
    updated = client.post(
        f"/api/v1/assets/{asset.id}/update",
        headers=headers,
        json={"version": asset.version, "remark": "HTTP 更新", "reason": "接口测试"},
    ).get_json()

    assert invalid["code"] == ResultCode.BAD_REQUEST.code
    assert updated["code"] == 200
    assert updated["data"]["remark"] == "HTTP 更新"


def test_relation_and_public_object_http_boundaries(client) -> None:
    context = _seed_context()
    main, child, _third = context.assets
    headers = _headers(client, context.actor)

    created = client.post(
        "/api/v1/public-usage-objects",
        headers=headers,
        json={"name": "五号会议室"},
    ).get_json()
    attached = client.post(
        f"/api/v1/assets/{main.id}/relations/attach",
        headers=headers,
        json={"child_ids": [child.id], "reason": "HTTP 挂接测试"},
    ).get_json()
    relations = client.get(
        f"/api/v1/assets/{child.id}/relations", headers=headers
    ).get_json()
    detached = client.post(
        f"/api/v1/assets/{main.id}/relations/detach",
        headers=headers,
        json={"child_ids": [child.id], "reason": "HTTP 解除测试"},
    ).get_json()

    assert created["code"] == 200
    assert created["data"]["code"] == "PUB000001"
    assert attached["code"] == 200
    assert relations["data"]["main"]["id"] == main.id
    assert detached["data"]["attachments"] == []
