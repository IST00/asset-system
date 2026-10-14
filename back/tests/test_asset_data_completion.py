"""Null-only single and batch asset data-completion contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import inspect

from marshmallow import ValidationError
import pytest
from sqlalchemy import select
from sqlalchemy.dialects import mysql

import app.schemas as schemas
import app.schemas.asset as asset_schemas
import app.services as services
from app.api import assets as assets_api
from app.common import BusinessException, ResultCode
from app.enums import (
    AssetDataCompleteness,
    AssetStatus,
    DataScope,
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
from app.repositories import asset_business_lock_repository, asset_repository
from app.repositories.asset_repository import _CAS_FIELDS
from app.security.passwords import hash_password


@dataclass(frozen=True)
class CompletionContext:
    organization: Organization
    manager: User
    unit: Unit
    disabled_unit: Unit
    source: AssetSource
    disabled_source: AssetSource
    location: AssetLocation
    disabled_location: AssetLocation
    unselectable_location: AssetLocation
    assets: tuple[Asset, Asset]


def _seed_completion_context() -> CompletionContext:
    organization = Organization(code="ADC-ORG", name="资料补齐组织")
    manager = User(username="adc-manager", password="x", enabled=True)
    unit = Unit(code="ADC-UNIT", name="补齐单位")
    disabled_unit = Unit(
        code="ADC-UNIT-OFF",
        name="停用单位",
        status=RecordStatus.DISABLED.value,
    )
    source = AssetSource(code="ADC-SOURCE", name="补齐来源")
    disabled_source = AssetSource(
        code="ADC-SOURCE-OFF",
        name="停用来源",
        status=RecordStatus.DISABLED.value,
    )
    location = AssetLocation(
        code="ADC-LOCATION",
        name="可选地点",
        is_selectable=True,
    )
    disabled_location = AssetLocation(
        code="ADC-LOCATION-OFF",
        name="停用地点",
        status=RecordStatus.DISABLED.value,
        is_selectable=True,
    )
    unselectable_location = AssetLocation(
        code="ADC-LOCATION-NO",
        name="不可选地点",
        is_selectable=False,
    )
    db.session.add_all(
        [
            organization,
            manager,
            unit,
            disabled_unit,
            source,
            disabled_source,
            location,
            disabled_location,
            unselectable_location,
        ]
    )
    db.session.flush()
    manager.organization_id = organization.id
    category = AssetCategory(
        code="ADC-CATEGORY",
        name="资料补齐分类",
        service_life_months=36,
        default_unit_id=unit.id,
    )
    db.session.add(category)
    db.session.flush()
    assets = tuple(
        Asset(
            asset_code=f"ADC-ASSET-{index}",
            asset_name=f"待补齐资产{index}",
            status=AssetStatus.IDLE.value,
            organization_id=organization.id,
            category_id=category.id,
            unit_id=None,
            original_amount=Decimal("100.00"),
            purchase_date=date(2026, 7, 23),
            service_life_months=36,
            expected_expiry_date=date(2029, 7, 23),
            manager_id=manager.id,
            source_id=None,
            location_id=None,
            custom_attributes={},
            data_completeness=AssetDataCompleteness.INCOMPLETE.value,
        )
        for index in (1, 2)
    )
    db.session.add_all(assets)
    db.session.commit()
    return CompletionContext(
        organization=organization,
        manager=manager,
        unit=unit,
        disabled_unit=disabled_unit,
        source=source,
        disabled_source=disabled_source,
        location=location,
        disabled_location=disabled_location,
        unselectable_location=unselectable_location,
        assets=assets,
    )


def _create_actor(
    client,
    context: CompletionContext,
    *,
    username: str,
    scope: str = DataScope.ALL.value,
    grant_permission: bool = True,
) -> tuple[User, dict[str, str]]:
    actor = User(
        username=username,
        password=hash_password("admin123"),
        enabled=True,
        organization_id=context.organization.id,
    )
    role = Role(
        code=f"{username.upper()}-ROLE",
        name=f"{username} role",
        data_scope=scope,
    )
    db.session.add_all([actor, role])
    db.session.flush()
    db.session.add(UserRole(user_id=actor.id, role_id=role.id))
    if grant_permission:
        permission = db.session.scalar(
            select(Permission).where(Permission.code == "asset:data:complete")
        )
        if permission is None:
            permission = Permission(
                code="asset:data:complete",
                name="补充资产资料",
                module="asset",
            )
            db.session.add(permission)
            db.session.flush()
        db.session.add(RolePermission(role_id=role.id, permission_id=permission.id))
    db.session.commit()
    login = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "admin123"},
    )
    assert login.status_code == 200
    token = login.get_json()["data"]["token"]
    return actor, {"Authorization": f"Bearer {token}"}


def _completion_service():
    service = getattr(services, "asset_data_completion_service", None)
    assert service is not None, "missing asset_data_completion_service"
    return service


def _completion_schemas():
    single = getattr(asset_schemas, "CompleteAssetDataRequestSchema", None)
    target = getattr(asset_schemas, "AssetVersionTargetSchema", None)
    batch = getattr(asset_schemas, "BatchCompleteAssetDataRequestSchema", None)
    assert single is not None, "missing CompleteAssetDataRequestSchema"
    assert target is not None, "missing AssetVersionTargetSchema"
    assert batch is not None, "missing BatchCompleteAssetDataRequestSchema"
    return single, target, batch


def test_completion_schema_contract_is_strict_and_exported() -> None:
    single_type, target_type, batch_type = _completion_schemas()
    expected_exports = {
        "CompleteAssetDataRequestSchema": single_type,
        "AssetVersionTargetSchema": target_type,
        "BatchCompleteAssetDataRequestSchema": batch_type,
    }
    for name, schema_type in expected_exports.items():
        assert name in asset_schemas.__all__
        assert getattr(schemas, name, None) is schema_type

    single = single_type()
    batch = batch_type()
    assert single.load({"version": 1, "unit_id": 9}) == {
        "version": 1,
        "unit_id": 9,
    }
    assert batch.load(
        {
            "items": [{"asset_id": 1, "version": 1}],
            "source_id": 7,
        }
    ) == {
        "items": [{"asset_id": 1, "version": 1}],
        "source_id": 7,
    }

    invalid_single_payloads = (
        {"version": 1},
        {"version": 1, "unit_id": None},
        {"version": "1", "unit_id": 1},
        {"version": 1, "unit_id": "1"},
        {"version": True, "unit_id": 1},
        {"version": 1, "unit_id": 1.0},
        {"version": 0, "unit_id": 1},
        {"version": 1, "unit_id": 1, "unexpected": True},
    )
    for payload in invalid_single_payloads:
        with pytest.raises(ValidationError):
            single.load(payload)

    invalid_batch_payloads = (
        {"items": [], "unit_id": 1},
        {
            "items": [
                {"asset_id": asset_id, "version": 1} for asset_id in range(1, 102)
            ],
            "unit_id": 1,
        },
        {"items": [{"asset_id": "1", "version": 1}], "unit_id": 1},
        {"items": [{"asset_id": 1, "version": "1"}], "unit_id": 1},
        {"items": [{"asset_id": 1, "version": 1}]},
        {"items": [{"asset_id": 1, "version": 1}], "location_id": None},
    )
    for payload in invalid_batch_payloads:
        with pytest.raises(ValidationError):
            batch.load(payload)


def test_repository_completion_cas_is_narrow_and_null_guarded(app) -> None:
    context = _seed_completion_context()
    asset = context.assets[0]
    complete_missing = getattr(asset_repository, "complete_missing_fields", None)
    assert complete_missing is not None, "missing complete_missing_fields"
    assert _CAS_FIELDS == {
        "status",
        "usage_type",
        "holder_user_id",
        "public_object_id",
        "usage_department_id",
        "organization_id",
        "usage_company_id",
        "location_id",
    }

    assert (
        complete_missing(
            asset.id,
            asset.version,
            {"unit_id": context.unit.id},
            AssetDataCompleteness.INCOMPLETE.value,
        )
        is True
    )
    db.session.expire_all()
    updated = db.session.get(Asset, asset.id)
    assert updated is not None
    assert updated.unit_id == context.unit.id
    assert updated.version == 2
    assert updated.data_completeness == AssetDataCompleteness.INCOMPLETE.value
    assert (
        complete_missing(
            updated.id,
            updated.version,
            {"unit_id": context.disabled_unit.id},
            AssetDataCompleteness.INCOMPLETE.value,
        )
        is False
    )
    assert (
        complete_missing(
            updated.id,
            1,
            {"source_id": context.source.id},
            AssetDataCompleteness.INCOMPLETE.value,
        )
        is False
    )
    with pytest.raises(BusinessException, match="^待补充字段无效$"):
        complete_missing(
            updated.id,
            updated.version,
            {},
            AssetDataCompleteness.INCOMPLETE.value,
        )
    with pytest.raises(BusinessException, match="^待补充字段无效$"):
        complete_missing(
            updated.id,
            updated.version,
            {"status": 1},
            AssetDataCompleteness.INCOMPLETE.value,
        )


def test_repository_completion_cas_rejects_active_business_lock(
    app,
    monkeypatch,
) -> None:
    context = _seed_completion_context()
    asset = context.assets[0]
    operation = OperationRequest(
        request_no="ADC-CAS-LOCK",
        operation_type="TRANSFER",
        applicant_id=context.manager.id,
        approval_status="PENDING",
        execution_status="NOT_STARTED",
    )
    db.session.add(operation)
    db.session.flush()
    db.session.add(
        AssetBusinessLock(
            asset_id=asset.id,
            operation_request_id=operation.id,
            operation_type=operation.operation_type,
            applicant_id=context.manager.id,
        )
    )
    db.session.commit()

    statements = []
    session = db.session()
    original_execute = session.execute

    def recording_execute(statement, *args, **kwargs):
        statements.append(statement)
        return original_execute(statement, *args, **kwargs)

    monkeypatch.setattr(session, "execute", recording_execute)
    assert (
        asset_repository.complete_missing_fields(
            asset.id,
            asset.version,
            {"unit_id": context.unit.id},
            AssetDataCompleteness.INCOMPLETE.value,
        )
        is False
    )
    update_statement = statements[-1]
    compiled = " ".join(
        str(
            update_statement.compile(
                dialect=mysql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        ).split()
    )
    assert "NOT (EXISTS (SELECT 1 FROM asset_business_locks" in compiled
    assert "asset_business_locks.asset_id = assets.id" in compiled
    db.session.rollback()
    db.session.expire_all()
    persisted = db.session.get(Asset, asset.id)
    assert persisted is not None
    assert persisted.unit_id is None
    assert persisted.version == 1


def test_business_lock_current_read_compiles_for_mysql(app, monkeypatch) -> None:
    find_for_update = getattr(
        asset_business_lock_repository,
        "find_by_assets_for_update",
        None,
    )
    assert find_for_update is not None, "missing find_by_assets_for_update"
    statements = []
    session = db.session()
    original_scalars = session.scalars

    def recording_scalars(statement, *args, **kwargs):
        statements.append(statement)
        return original_scalars(statement, *args, **kwargs)

    monkeypatch.setattr(session, "scalars", recording_scalars)
    assert find_for_update([3, 1, 3, 2]) == []
    assert len(statements) == 1
    compiled = " ".join(
        str(
            statements[0].compile(
                dialect=mysql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        ).split()
    )
    assert "asset_business_locks.asset_id IN (1, 2, 3)" in compiled
    assert "ORDER BY asset_business_locks.asset_id ASC" in compiled
    assert compiled.endswith("FOR UPDATE")


def test_single_http_completion_fills_only_null_field_and_becomes_complete(
    client,
) -> None:
    context = _seed_completion_context()
    asset = context.assets[0]
    asset.source_id = context.source.id
    asset.location_id = context.location.id
    db.session.commit()
    actor, headers = _create_actor(
        client,
        context,
        username="single-completer",
    )

    response = client.post(
        f"/api/v1/assets/{asset.id}/complete-data",
        headers=headers,
        json={"version": 1, "unit_id": context.unit.id},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["code"] == ResultCode.SUCCESS.code
    assert body["data"] == {
        "id": asset.id,
        "unit_id": context.unit.id,
        "source_id": context.source.id,
        "location_id": context.location.id,
        "data_completeness": AssetDataCompleteness.COMPLETE.value,
        "version": 2,
    }
    db.session.expire_all()
    persisted = db.session.get(Asset, asset.id)
    assert persisted is not None
    assert persisted.unit_id == context.unit.id
    assert persisted.data_completeness == AssetDataCompleteness.COMPLETE.value
    assert persisted.version == 2
    lifecycle = db.session.query(AssetLifecycleRecord).one()
    assert lifecycle.operator_id == actor.id


def test_single_partial_completion_remains_incomplete(client) -> None:
    context = _seed_completion_context()
    asset = context.assets[0]
    _actor, headers = _create_actor(
        client,
        context,
        username="partial-completer",
    )

    response = client.post(
        f"/api/v1/assets/{asset.id}/complete-data",
        headers=headers,
        json={"version": asset.version, "unit_id": context.unit.id},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["unit_id"] == context.unit.id
    assert data["source_id"] is None
    assert data["location_id"] is None
    assert data["data_completeness"] == AssetDataCompleteness.INCOMPLETE.value
    assert data["version"] == 2


def test_batch_stale_version_fails_before_any_update_and_persists_nothing(
    client,
    monkeypatch,
) -> None:
    context = _seed_completion_context()
    first, second = context.assets
    for asset in context.assets:
        asset.source_id = context.source.id
        asset.location_id = context.location.id
    db.session.commit()
    _actor, headers = _create_actor(
        client,
        context,
        username="batch-stale-completer",
    )
    complete_missing = getattr(asset_repository, "complete_missing_fields", None)
    assert complete_missing is not None, "missing complete_missing_fields"
    calls: list[int] = []

    def record_completion(
        asset_id: int,
        expected_version: int,
        changes,
        resulting_completeness: str,
    ) -> bool:
        calls.append(asset_id)
        return complete_missing(
            asset_id,
            expected_version,
            changes,
            resulting_completeness,
        )

    monkeypatch.setattr(asset_repository, "complete_missing_fields", record_completion)
    response = client.post(
        "/api/v1/assets/complete-data",
        headers=headers,
        json={
            "items": [
                {"asset_id": first.id, "version": first.version},
                {"asset_id": second.id, "version": second.version + 1},
            ],
            "unit_id": context.unit.id,
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["code"] == ResultCode.BUSINESS_ERROR.code
    assert body["message"] == (f"资产 {second.asset_code} 已被修改，请刷新后重试")
    assert calls == []
    db.session.expire_all()
    persisted = [db.session.get(Asset, asset.id) for asset in context.assets]
    assert all(asset is not None for asset in persisted)
    assert [asset.unit_id for asset in persisted if asset is not None] == [None, None]
    assert [asset.version for asset in persisted if asset is not None] == [1, 1]
    assert db.session.query(AssetLifecycleRecord).count() == 0
    assert db.session.query(OperationLog).count() == 0


@pytest.mark.parametrize(
    ("field_name", "context_name", "message"),
    [
        ("unit_id", "disabled_unit", "计量单位不存在或已停用"),
        ("source_id", "disabled_source", "资产来源不存在或已停用"),
        ("location_id", "disabled_location", "存放地点不存在或已停用"),
        ("location_id", "unselectable_location", "该地点不允许存放资产"),
    ],
)
def test_completion_rejects_disabled_or_unselectable_master_data(
    client,
    field_name: str,
    context_name: str,
    message: str,
) -> None:
    context = _seed_completion_context()
    asset = context.assets[0]
    actor, _headers = _create_actor(
        client,
        context,
        username=f"invalid-{context_name}",
    )
    reference = getattr(context, context_name)

    with pytest.raises(BusinessException, match=f"^{message}$"):
        _completion_service().complete_data(
            asset.id,
            {"version": asset.version, field_name: reference.id},
            actor.id,
        )

    assert db.session().in_transaction() is False
    db.session.expire_all()
    persisted = db.session.get(Asset, asset.id)
    assert persisted is not None
    assert getattr(persisted, field_name) is None
    assert persisted.version == 1


@pytest.mark.parametrize(
    ("field_name", "context_name"),
    [
        ("unit_id", "unit"),
        ("source_id", "source"),
        ("location_id", "location"),
    ],
)
def test_completion_never_overwrites_existing_values(
    client,
    field_name: str,
    context_name: str,
) -> None:
    context = _seed_completion_context()
    asset = context.assets[0]
    asset_code = asset.asset_code
    reference = getattr(context, context_name)
    setattr(asset, field_name, reference.id)
    db.session.commit()
    actor, _headers = _create_actor(
        client,
        context,
        username=f"overwrite-{field_name}",
    )

    with pytest.raises(BusinessException) as error:
        _completion_service().complete_data(
            asset.id,
            {"version": asset.version, field_name: reference.id},
            actor.id,
        )

    assert error.value.message == (
        f"资产 {asset_code} 的 {field_name} 已有值，不能通过补齐覆盖"
    )
    assert db.session().in_transaction() is False
    db.session.expire_all()
    persisted = db.session.get(Asset, asset.id)
    assert persisted is not None
    assert getattr(persisted, field_name) == reference.id
    assert persisted.version == 1
    assert db.session.query(AssetLifecycleRecord).count() == 0
    assert db.session.query(OperationLog).count() == 0


def test_completion_requires_jwt_and_exact_functional_permission(client) -> None:
    context = _seed_completion_context()
    asset = context.assets[0]
    path = f"/api/v1/assets/{asset.id}/complete-data"

    unauthorized = client.post(
        path,
        json={"version": asset.version, "unit_id": context.unit.id},
    )
    assert unauthorized.status_code == 401
    assert unauthorized.get_json()["code"] == ResultCode.UNAUTHORIZED.code

    _actor, headers = _create_actor(
        client,
        context,
        username="no-completion-permission",
        grant_permission=False,
    )
    forbidden = client.post(
        path,
        headers=headers,
        json={"version": asset.version, "unit_id": context.unit.id},
    )
    assert forbidden.status_code == 200
    forbidden_body = forbidden.get_json()
    assert forbidden_body["code"] == ResultCode.FORBIDDEN.code
    assert forbidden_body["message"] == "无操作权限"
    assert forbidden_body["request_id"]


def test_self_scope_holder_can_complete_data(client) -> None:
    context = _seed_completion_context()
    asset = context.assets[0]
    actor, headers = _create_actor(
        client,
        context,
        username="self-holder-completer",
        scope=DataScope.SELF.value,
    )
    asset.holder_user_id = actor.id
    asset.source_id = context.source.id
    asset.location_id = context.location.id
    db.session.commit()

    response = client.post(
        f"/api/v1/assets/{asset.id}/complete-data",
        headers=headers,
        json={"version": asset.version, "unit_id": context.unit.id},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["id"] == asset.id
    db.session.expire_all()
    persisted = db.session.get(Asset, asset.id)
    assert persisted is not None
    assert persisted.unit_id == context.unit.id


def test_out_of_scope_and_absent_assets_share_not_found_response(client) -> None:
    context = _seed_completion_context()
    asset = context.assets[0]
    _actor, headers = _create_actor(
        client,
        context,
        username="out-of-scope-completer",
        scope=DataScope.SELF.value,
    )
    payload = {"version": asset.version, "unit_id": context.unit.id}

    hidden = client.post(
        f"/api/v1/assets/{asset.id}/complete-data",
        headers=headers,
        json=payload,
    )
    absent = client.post(
        f"/api/v1/assets/{asset.id + 10_000}/complete-data",
        headers=headers,
        json=payload,
    )

    assert hidden.status_code == absent.status_code == 200
    hidden_body = hidden.get_json()
    absent_body = absent.get_json()
    for body in (hidden_body, absent_body):
        assert body["code"] == ResultCode.NOT_FOUND.code
        assert body["message"] == "资产不存在"
        assert body["request_id"]
    assert hidden_body["request_id"] != absent_body["request_id"]


def test_active_business_lock_is_actionable_and_leaves_no_transaction(
    client,
    monkeypatch,
) -> None:
    context = _seed_completion_context()
    asset = context.assets[0]
    asset_code = asset.asset_code
    actor, _headers = _create_actor(
        client,
        context,
        username="locked-completer",
    )
    operation = OperationRequest(
        request_no="ADC-LOCKED-REQUEST",
        operation_type="TRANSFER",
        applicant_id=actor.id,
        approval_status="PENDING",
        execution_status="NOT_STARTED",
    )
    db.session.add(operation)
    db.session.flush()
    db.session.add(
        AssetBusinessLock(
            asset_id=asset.id,
            operation_request_id=operation.id,
            operation_type=operation.operation_type,
            applicant_id=actor.id,
        )
    )
    db.session.commit()

    def reject_snapshot_read(_asset_ids):
        raise AssertionError("completion must use a current locking read")

    monkeypatch.setattr(
        asset_business_lock_repository,
        "find_by_assets",
        reject_snapshot_read,
    )

    with pytest.raises(BusinessException) as error:
        _completion_service().complete_data(
            asset.id,
            {"version": asset.version, "unit_id": context.unit.id},
            actor.id,
        )

    assert error.value.message == f"资产 {asset_code} 正在处理其它业务"
    assert db.session().in_transaction() is False
    db.session.expire_all()
    persisted = db.session.get(Asset, asset.id)
    assert persisted is not None
    assert persisted.unit_id is None
    assert persisted.version == 1
    assert db.session.query(AssetLifecycleRecord).count() == 0
    assert db.session.query(OperationLog).count() == 0


def test_stale_direct_service_error_leaves_no_transaction(client) -> None:
    context = _seed_completion_context()
    asset = context.assets[0]
    asset_code = asset.asset_code
    actor, _headers = _create_actor(
        client,
        context,
        username="direct-stale-completer",
    )

    with pytest.raises(BusinessException) as error:
        _completion_service().complete_data(
            asset.id,
            {"version": asset.version + 1, "unit_id": context.unit.id},
            actor.id,
        )

    assert error.value.message == (f"资产 {asset_code} 已被修改，请刷新后重试")
    assert db.session().in_transaction() is False
    db.session.expire_all()
    persisted = db.session.get(Asset, asset.id)
    assert persisted is not None
    assert persisted.unit_id is None
    assert persisted.version == 1


def test_batch_duplicate_targets_and_empty_changes_are_rejected(client) -> None:
    context = _seed_completion_context()
    asset = context.assets[0]
    actor, _headers = _create_actor(
        client,
        context,
        username="duplicate-target-completer",
    )
    service = _completion_service()

    with pytest.raises(BusinessException, match="^资产不能重复选择$"):
        service.complete_data_batch(
            {
                "items": [
                    {"asset_id": asset.id, "version": asset.version},
                    {"asset_id": asset.id, "version": asset.version},
                ],
                "unit_id": context.unit.id,
            },
            actor.id,
        )
    assert db.session().in_transaction() is False

    with pytest.raises(BusinessException, match="^至少填写一个待补充字段$"):
        service.complete_data_batch(
            {"items": [{"asset_id": asset.id, "version": asset.version}]},
            actor.id,
        )
    assert db.session().in_transaction() is False
    assert db.session.query(AssetLifecycleRecord).count() == 0
    assert db.session.query(OperationLog).count() == 0


@pytest.mark.parametrize("pending_kind", ["new", "dirty", "deleted"])
def test_completion_rejects_pending_caller_writes_without_mutating_them(
    client,
    pending_kind: str,
) -> None:
    context = _seed_completion_context()
    asset_id = context.assets[0].id
    asset_version = context.assets[0].version
    unit_id = context.unit.id
    actor, _headers = _create_actor(
        client,
        context,
        username=f"pending-{pending_kind}-completer",
    )
    actor_id = actor.id
    sentinel = Organization(
        code=f"ADC-PENDING-SENTINEL-{pending_kind}",
        name=f"Pending sentinel {pending_kind}",
    )
    db.session.add(sentinel)
    db.session.commit()

    if pending_kind == "new":
        pending = Organization(
            code="ADC-PENDING-NEW",
            name="Pending new",
        )
        db.session.add(pending)
    elif pending_kind == "dirty":
        sentinel.name = "Pending dirty"
        pending = sentinel
    else:
        db.session.delete(sentinel)
        pending = sentinel

    with pytest.raises(RuntimeError, match="pending business writes"):
        _completion_service().complete_data_batch(
            {
                "items": [{"asset_id": asset_id, "version": asset_version}],
                "unit_id": unit_id,
            },
            actor_id,
        )

    session = db.session()
    if pending_kind == "new":
        assert pending in session.new
        assert pending.id is None
    elif pending_kind == "dirty":
        assert pending in session.dirty
    else:
        assert pending in session.deleted
    db.session.rollback()


def test_direct_batch_size_is_rejected_before_audit(client) -> None:
    context = _seed_completion_context()
    actor, _headers = _create_actor(
        client,
        context,
        username="direct-size-completer",
    )
    service = _completion_service()

    for items in (
        [],
        [{"asset_id": asset_id, "version": 1} for asset_id in range(1, 102)],
    ):
        with pytest.raises(BusinessException) as error:
            service.complete_data_batch(
                {"items": items, "unit_id": context.unit.id},
                actor.id,
            )
        assert error.value.code == ResultCode.BAD_REQUEST.code
        assert error.value.message == "资产补齐数量必须在1到100之间"
        assert db.session().in_transaction() is False

    assert db.session.query(AssetLifecycleRecord).count() == 0
    assert db.session.query(OperationLog).count() == 0


@pytest.mark.parametrize("failure_point", ["audit", "commit"])
def test_audit_or_commit_failure_rolls_back_assets_and_audit(
    client,
    monkeypatch,
    failure_point: str,
) -> None:
    context = _seed_completion_context()
    asset_id = context.assets[0].id
    asset_version = context.assets[0].version
    actor, _headers = _create_actor(
        client,
        context,
        username=f"{failure_point}-failure-completer",
    )

    def fail() -> None:
        raise RuntimeError(f"{failure_point} failed")

    if failure_point == "audit":

        def fail_audit(**_kwargs) -> None:
            fail()

        monkeypatch.setattr(
            services.audit_service, "record_resource_change", fail_audit
        )
    else:
        monkeypatch.setattr(db.session, "commit", fail)

    with pytest.raises(RuntimeError, match=f"^{failure_point} failed$"):
        _completion_service().complete_data_batch(
            {
                "items": [{"asset_id": asset_id, "version": asset_version}],
                "unit_id": context.unit.id,
                "source_id": context.source.id,
                "location_id": context.location.id,
            },
            actor.id,
        )

    assert db.session().in_transaction() is False
    persisted = db.session.get(Asset, asset_id)
    assert persisted is not None
    assert persisted.unit_id is None
    assert persisted.source_id is None
    assert persisted.location_id is None
    assert persisted.version == asset_version
    assert db.session.query(AssetLifecycleRecord).count() == 0
    assert db.session.query(OperationLog).count() == 0


def test_second_cas_failure_rolls_back_assets_and_lifecycle(
    client,
    monkeypatch,
) -> None:
    context = _seed_completion_context()
    for asset in context.assets:
        asset.source_id = context.source.id
        asset.location_id = context.location.id
    db.session.commit()
    actor, _headers = _create_actor(
        client,
        context,
        username="cas-race-completer",
    )
    original = getattr(asset_repository, "complete_missing_fields", None)
    assert original is not None, "missing complete_missing_fields"
    calls: list[int] = []

    def fail_second(
        asset_id: int,
        expected_version: int,
        changes,
        resulting_completeness: str,
    ) -> bool:
        calls.append(asset_id)
        if len(calls) == 2:
            return False
        return original(
            asset_id,
            expected_version,
            changes,
            resulting_completeness,
        )

    monkeypatch.setattr(asset_repository, "complete_missing_fields", fail_second)
    asset_ids = [asset.id for asset in context.assets]
    second = context.assets[1]
    second_asset_code = second.asset_code
    with pytest.raises(BusinessException) as error:
        _completion_service().complete_data_batch(
            {
                "items": [
                    {"asset_id": asset.id, "version": asset.version}
                    for asset in reversed(context.assets)
                ],
                "unit_id": context.unit.id,
            },
            actor.id,
        )

    assert calls == asset_ids
    assert error.value.message == (f"资产 {second_asset_code} 已被修改，请刷新后重试")
    assert db.session().in_transaction() is False
    db.session.expire_all()
    persisted = [db.session.get(Asset, asset_id) for asset_id in asset_ids]
    assert all(asset is not None for asset in persisted)
    assert [asset.unit_id for asset in persisted if asset is not None] == [None, None]
    assert [asset.version for asset in persisted if asset is not None] == [1, 1]
    assert db.session.query(AssetLifecycleRecord).count() == 0
    assert db.session.query(OperationLog).count() == 0


def test_successful_batch_has_one_lifecycle_per_asset_and_one_audit(client) -> None:
    context = _seed_completion_context()
    actor, headers = _create_actor(
        client,
        context,
        username="audited-batch-completer",
    )
    response = client.post(
        "/api/v1/assets/complete-data",
        headers=headers,
        json={
            "items": [
                {"asset_id": asset.id, "version": asset.version}
                for asset in reversed(context.assets)
            ],
            "unit_id": context.unit.id,
            "source_id": context.source.id,
            "location_id": context.location.id,
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["code"] == ResultCode.SUCCESS.code
    result = body["data"]
    batch_no = result["batch_no"]
    assert batch_no.startswith("ADC")
    assert result["updated_count"] == 2
    assert [item["id"] for item in result["items"]] == [
        asset.id for asset in context.assets
    ]
    assert all(
        item["data_completeness"] == AssetDataCompleteness.COMPLETE.value
        and item["version"] == 2
        for item in result["items"]
    )

    lifecycle = db.session.scalars(
        select(AssetLifecycleRecord).order_by(AssetLifecycleRecord.asset_id.asc())
    ).all()
    assert len(lifecycle) == 2
    assert [item.asset_id for item in lifecycle] == [
        asset.id for asset in context.assets
    ]
    assert all(item.operation_type == "ASSET_DATA_COMPLETE" for item in lifecycle)
    assert all(item.operation_no == batch_no for item in lifecycle)
    assert all(item.operator_id == actor.id for item in lifecycle)
    for item in lifecycle:
        assert item.before_data == {
            "unit_id": None,
            "source_id": None,
            "location_id": None,
            "data_completeness": AssetDataCompleteness.INCOMPLETE.value,
            "version": 1,
        }
        assert item.after_data == {
            "unit_id": context.unit.id,
            "source_id": context.source.id,
            "location_id": context.location.id,
            "data_completeness": AssetDataCompleteness.COMPLETE.value,
            "version": 2,
        }

    audit = db.session.query(OperationLog).one()
    assert audit.action == "ASSET_DATA_COMPLETE"
    assert audit.resource_type == "asset_data_completion_batch"
    assert audit.resource_id == batch_no
    assert audit.operator_id == actor.id
    assert audit.before_data == {
        "asset_ids": [asset.id for asset in context.assets],
        "fields": ["location_id", "source_id", "unit_id"],
    }
    assert audit.after_data == {"updated_count": 2}


def test_completion_routes_are_post_only_and_blueprint_stays_thin(app, client) -> None:
    expected_rules = {
        "/api/v1/assets/<int:asset_id>/complete-data",
        "/api/v1/assets/complete-data",
    }
    rules = {rule.rule: rule for rule in app.url_map.iter_rules()}
    assert expected_rules <= rules.keys()
    for path in expected_rules:
        assert rules[path].methods == {"OPTIONS", "POST"}

    for method in ("GET", "PUT", "PATCH", "DELETE"):
        single = client.open(
            "/api/v1/assets/1/complete-data",
            method=method,
        )
        batch = client.open("/api/v1/assets/complete-data", method=method)
        assert single.status_code == batch.status_code == 405

    source = inspect.getsource(assets_api)
    assert "app.models" not in source
    assert "app.extensions" not in source
