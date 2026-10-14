"""Shared asset transition, relation, and audit contracts."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

import app.services as services
from app.common import BusinessException
from app.enums import (
    ApprovalStatus,
    AssetDataCompleteness,
    AssetStatus,
    ExecutionStatus,
)
from app.extensions import db
from app.models import (
    Asset,
    AssetCategory,
    AssetLocation,
    AssetSource,
    AssetLifecycleRecord,
    OperationLog,
    OperationRequest,
    Organization,
    Unit,
    User,
)
from app.repositories.asset_repository import asset_repository


def _seed_transition_assets() -> list[Asset]:
    organization = Organization(code="TRANSITION-ORG", name="转换组织")
    unit = Unit(code="TRANSITION-UNIT", name="转换单位")
    source = AssetSource(code="TRANSITION-SOURCE", name="转换来源")
    location = AssetLocation(
        code="TRANSITION-LOCATION", name="转换地点", is_selectable=True
    )
    manager = User(username="transition-manager", password="x", enabled=True)
    db.session.add_all([organization, unit, source, location, manager])
    db.session.flush()
    category = AssetCategory(
        code="TRANSITION-CATEGORY",
        name="转换分类",
        service_life_months=12,
        default_unit_id=unit.id,
    )
    db.session.add(category)
    db.session.flush()
    assets = [
        Asset(
            asset_code=f"TRANSITION-ASSET-{index}",
            asset_name=f"转换资产{index}",
            status=AssetStatus.IDLE.value,
            organization_id=organization.id,
            category_id=category.id,
            unit_id=unit.id,
            original_amount=Decimal("1.00"),
            purchase_date=date(2026, 7, 21),
            service_life_months=36,
            expected_expiry_date=date(2029, 1, 1),
            manager_id=manager.id,
            source_id=source.id,
            location_id=location.id,
            custom_attributes={},
            data_completeness=AssetDataCompleteness.COMPLETE.value,
        )
        for index in (1, 2, 3, 4)
    ]
    db.session.add_all(assets)
    db.session.flush()
    return assets


def test_asset_repository_locks_in_id_order_and_updates_with_cas(app) -> None:
    assets = _seed_transition_assets()
    locked = asset_repository.find_many_for_update([assets[1].id, assets[0].id])

    assert [asset.id for asset in locked] == [assets[0].id, assets[1].id]
    assert (
        asset_repository.cas_update(
            assets[0].id,
            assets[0].version,
            {
                "status": AssetStatus.IN_USE.value,
                "holder_user_id": assets[0].manager_id,
            },
        )
        is True
    )
    db.session.flush()
    db.session.expire_all()
    updated = db.session.get(Asset, assets[0].id)
    assert updated is not None
    assert updated.status == AssetStatus.IN_USE.value
    assert updated.version == 2
    assert (
        asset_repository.cas_update(
            updated.id,
            1,
            {"status": AssetStatus.REPAIRING.value},
        )
        is False
    )


def test_asset_repository_rejects_empty_or_unsafe_cas_changes(app) -> None:
    asset = _seed_transition_assets()[0]

    with pytest.raises(BusinessException, match="不能为空"):
        asset_repository.cas_update(asset.id, asset.version, {})
    with pytest.raises(BusinessException, match="不允许更新"):
        asset_repository.cas_update(
            asset.id,
            asset.version,
            {"custom_attributes": {"unsafe": True}},
        )


def _relation_service():
    service = getattr(services, "asset_relation_service", None)
    assert service is not None, "missing asset_relation_service"
    return service


def test_asset_relation_expands_direct_children_once_in_stable_order(app) -> None:
    main, child_a, child_b, standalone = _seed_transition_assets()
    child_a.parent_asset_id = main.id
    child_b.parent_asset_id = main.id
    db.session.flush()

    expanded = _relation_service().expand_with_direct_children(
        [standalone.id, main.id, main.id]
    )

    assert [asset.id for asset in expanded] == sorted(
        [main.id, child_a.id, child_b.id, standalone.id]
    )


def test_asset_relation_exposes_direct_children_in_stable_order(app) -> None:
    main, child_a, child_b, _standalone = _seed_transition_assets()
    child_a.parent_asset_id = main.id
    child_b.parent_asset_id = main.id
    db.session.flush()
    service = _relation_service()

    assert hasattr(service, "find_direct_children")
    children = service.find_direct_children([main.id, main.id])
    assert [asset.id for asset in children] == [child_a.id, child_b.id]


def test_asset_relation_rejects_missing_or_multi_level_assets(app) -> None:
    main, child, grandchild, _standalone = _seed_transition_assets()
    child.parent_asset_id = main.id
    grandchild.parent_asset_id = child.id
    db.session.flush()

    with pytest.raises(BusinessException, match="只允许一层"):
        _relation_service().expand_with_direct_children([main.id])
    with pytest.raises(BusinessException, match="只允许一层"):
        _relation_service().expand_with_direct_children([child.id])
    with pytest.raises(BusinessException, match="不存在"):
        _relation_service().expand_with_direct_children([999999])


def test_audit_service_records_asset_lifecycle_and_request_log(app) -> None:
    asset = _seed_transition_assets()[0]
    operation = OperationRequest(
        request_no="TRANSITION-AUDIT",
        operation_type="TRANSFER",
        applicant_id=asset.manager_id,
        approval_status=ApprovalStatus.APPROVED.value,
        execution_status=ExecutionStatus.SUCCESS.value,
    )
    db.session.add(operation)
    db.session.flush()

    services.audit_service.record_asset_lifecycle(
        asset_id=asset.id,
        operation_type="TRANSFER",
        request_no=operation.request_no,
        actor_id=asset.manager_id,
        before_data={"location_id": 1},
        after_data={"location_id": 2},
    )
    services.audit_service.record_operation(
        operation_request_id=operation.id,
        operation_type="TRANSFER",
        actor_id=asset.manager_id,
        before_data={"asset_ids": [asset.id]},
        after_data={"result": "SUCCESS"},
    )

    lifecycle = db.session.query(AssetLifecycleRecord).one()
    log = db.session.query(OperationLog).one()
    assert lifecycle.operation_type == "TRANSFER"
    assert lifecycle.before_data == {"location_id": 1}
    assert lifecycle.after_data == {"location_id": 2}
    assert log.action == "TRANSFER"
    assert log.resource_type == "operation_request"
    assert log.resource_id == str(operation.id)


def test_stock_in_audit_wrapper_keeps_asset_scoped_log(app) -> None:
    asset = _seed_transition_assets()[0]

    services.audit_service.record_asset_stock_in(
        asset_id=asset.id,
        request_no="STOCK-IN-AUDIT",
        actor_id=asset.manager_id,
        after_data={"status": AssetStatus.IDLE.value},
    )

    lifecycle = db.session.query(AssetLifecycleRecord).one()
    log = db.session.query(OperationLog).one()
    assert lifecycle.operation_type == "STOCK_IN"
    assert log.action == "STOCK_IN"
    assert log.resource_type == "asset"
    assert log.resource_id == str(asset.id)
