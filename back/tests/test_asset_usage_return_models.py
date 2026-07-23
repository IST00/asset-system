"""Persistence contracts for asset usage and return requests."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import get_type_hints

import pytest
from sqlalchemy import JSON, DateTime, String, Text, func, select
from sqlalchemy.exc import IntegrityError

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
    OperationRequest,
    OperationRequestAsset,
    Organization,
    PublicUsageObject,
    Unit,
    User,
)
from app.models.asset_usage_return import (
    AssetReturnItem,
    AssetReturnRequest,
    AssetUsageRequest,
)
from app.models.mixins import TimestampMixin
from app.repositories.asset_usage_return_repository import (
    AssetReturnItemRepository,
    AssetReturnRequestRepository,
    AssetUsageRequestRepository,
    asset_return_item_repository,
    asset_return_request_repository,
    asset_usage_request_repository,
)


def _foreign_key(model, column_name: str):
    foreign_keys = list(model.__table__.columns[column_name].foreign_keys)
    assert len(foreign_keys) == 1
    return foreign_keys[0]


def _assert_foreign_key(
    model,
    column_name: str,
    target: str,
    ondelete: str,
) -> None:
    foreign_key = _foreign_key(model, column_name)
    assert foreign_key.target_fullname == target
    assert foreign_key.ondelete == ondelete


def _enable_sqlite_foreign_keys() -> None:
    connection = db.session.connection()
    connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    enabled = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()
    assert enabled == 1


def _seed_operation_assets() -> (
    tuple[
        OperationRequest,
        OperationRequest,
        list[OperationRequestAsset],
    ]
):
    organization = Organization(code="USE-ORG", name="领用测试组织")
    unit = Unit(code="USE-UNIT", name="领用测试单位")
    source = AssetSource(code="USE-SOURCE", name="领用测试来源")
    location = AssetLocation(
        code="USE-LOCATION", name="领用测试地点", is_selectable=True
    )
    applicant = User(username="usage-repository-user", password="x", enabled=True)
    db.session.add_all([organization, unit, source, location, applicant])
    db.session.flush()

    category = AssetCategory(
        code="USE-CATEGORY",
        name="领用测试分类",
        service_life_months=12,
        default_unit_id=unit.id,
    )
    db.session.add(category)
    db.session.flush()

    assets = [
        Asset(
            asset_code=f"USE-ASSET-{index}",
            asset_name=f"领用测试资产{index}",
            status=AssetStatus.IDLE.value,
            organization_id=organization.id,
            category_id=category.id,
            unit_id=unit.id,
            original_amount=Decimal("1.00"),
            purchase_date=date(2026, 7, 21),
            service_life_months=36,
            expected_expiry_date=date(2029, 1, 1),
            manager_id=applicant.id,
            source_id=source.id,
            location_id=location.id,
            custom_attributes={},
            data_completeness=AssetDataCompleteness.COMPLETE.value,
        )
        for index in (1, 2, 3)
    ]
    operations = [
        OperationRequest(
            request_no=f"USE-REQUEST-{index}",
            operation_type="PERSONAL_RETURN",
            applicant_id=applicant.id,
            approval_status=ApprovalStatus.PENDING.value,
            execution_status=ExecutionStatus.NOT_STARTED.value,
        )
        for index in (1, 2)
    ]
    db.session.add_all([*assets, *operations])
    db.session.flush()

    request_assets = [
        OperationRequestAsset(
            operation_request_id=(operations[0] if index < 3 else operations[1]).id,
            asset_id=asset.id,
            asset_code_snapshot=asset.asset_code,
            asset_name_snapshot=asset.asset_name,
            asset_status_snapshot=asset.status,
            asset_version_snapshot=asset.version,
            organization_id_snapshot=asset.organization_id,
        )
        for index, asset in enumerate(assets, start=1)
    ]
    db.session.add_all(request_assets)
    db.session.flush()
    return operations[0], operations[1], request_assets


def test_models_use_expected_table_names_and_timestamp_mixin() -> None:
    expected_tables = {
        AssetUsageRequest: "asset_usage_requests",
        AssetReturnRequest: "asset_return_requests",
        AssetReturnItem: "asset_return_items",
    }

    for model, table_name in expected_tables.items():
        assert model.__tablename__ == table_name
        assert issubclass(model, TimestampMixin)
        assert {"created_at", "updated_at"} <= set(model.__table__.columns.keys())


def test_usage_request_columns_define_nullable_restricted_targets() -> None:
    columns = AssetUsageRequest.__table__.columns

    assert columns.operation_request_id.nullable is False
    assert columns.operation_request_id.unique is True
    assert columns.operation_request_id.index is True
    _assert_foreign_key(
        AssetUsageRequest,
        "operation_request_id",
        "operation_requests.id",
        "CASCADE",
    )

    expected_targets = {
        "target_user_id": "users.id",
        "target_public_object_id": "public_usage_objects.id",
        "usage_department_id": "organizations.id",
        "target_location_id": "asset_locations.id",
    }
    for column_name, target in expected_targets.items():
        assert columns[column_name].nullable is True
        assert columns[column_name].index is True
        _assert_foreign_key(AssetUsageRequest, column_name, target, "RESTRICT")


def test_return_request_columns_define_confirmation_contract() -> None:
    columns = AssetReturnRequest.__table__.columns

    assert columns.operation_request_id.nullable is False
    assert columns.operation_request_id.unique is True
    assert columns.operation_request_id.index is True
    _assert_foreign_key(
        AssetReturnRequest,
        "operation_request_id",
        "operation_requests.id",
        "CASCADE",
    )

    for column_name, target in {
        "return_location_id": "asset_locations.id",
        "confirmed_by": "users.id",
    }.items():
        assert columns[column_name].nullable is True
        assert columns[column_name].index is True
        _assert_foreign_key(AssetReturnRequest, column_name, target, "RESTRICT")

    assert columns.confirmed_at.nullable is True
    assert isinstance(columns.confirmed_at.type, DateTime)
    assert columns.confirmed_at.type.timezone is True


def test_feature_snapshot_columns_are_nullable_json() -> None:
    usage_columns = AssetUsageRequest.__table__.columns
    usage_snapshot_columns = {
        "target_user_snapshot",
        "usage_department_snapshot",
        "target_public_object_snapshot",
        "target_location_snapshot",
    }
    assert usage_snapshot_columns <= set(usage_columns.keys())
    for column_name in usage_snapshot_columns:
        assert usage_columns[column_name].nullable is True
        assert isinstance(usage_columns[column_name].type, JSON)
        assert usage_columns[column_name].type.none_as_null is True

    return_columns = AssetReturnRequest.__table__.columns
    return_snapshot_columns = {
        "return_location_snapshot",
        "confirmed_by_snapshot",
    }
    assert return_snapshot_columns <= set(return_columns.keys())
    for column_name in return_snapshot_columns:
        assert return_columns[column_name].nullable is True
        assert isinstance(return_columns[column_name].type, JSON)
        assert return_columns[column_name].type.none_as_null is True


def test_return_item_columns_define_condition_contract() -> None:
    columns = AssetReturnItem.__table__.columns

    assert columns.operation_request_asset_id.nullable is False
    assert columns.operation_request_asset_id.unique is True
    assert columns.operation_request_asset_id.index is True
    _assert_foreign_key(
        AssetReturnItem,
        "operation_request_asset_id",
        "operation_request_assets.id",
        "CASCADE",
    )
    assert columns.condition.nullable is True
    assert isinstance(columns.condition.type, String)
    assert columns.condition.type.length == 16
    assert columns.condition_description.nullable is True
    assert isinstance(columns.condition_description.type, Text)


def test_usage_request_operation_uniqueness_is_database_enforced(app) -> None:
    _enable_sqlite_foreign_keys()
    operation, _, _ = _seed_operation_assets()
    operation_id = operation.id
    db.session.add(AssetUsageRequest(operation_request_id=operation_id))
    db.session.commit()

    db.session.add(AssetUsageRequest(operation_request_id=operation_id))
    with pytest.raises(IntegrityError):
        db.session.flush()
    db.session.rollback()

    count = db.session.scalar(
        select(func.count())
        .select_from(AssetUsageRequest)
        .where(AssetUsageRequest.operation_request_id == operation_id)
    )
    assert count == 1


def test_return_request_operation_uniqueness_is_database_enforced(app) -> None:
    _enable_sqlite_foreign_keys()
    operation, _, _ = _seed_operation_assets()
    operation_id = operation.id
    db.session.add(AssetReturnRequest(operation_request_id=operation_id))
    db.session.commit()

    db.session.add(AssetReturnRequest(operation_request_id=operation_id))
    with pytest.raises(IntegrityError):
        db.session.flush()
    db.session.rollback()

    count = db.session.scalar(
        select(func.count())
        .select_from(AssetReturnRequest)
        .where(AssetReturnRequest.operation_request_id == operation_id)
    )
    assert count == 1


def test_return_item_request_asset_uniqueness_is_database_enforced(app) -> None:
    _enable_sqlite_foreign_keys()
    _, _, request_assets = _seed_operation_assets()
    request_asset_id = request_assets[0].id
    db.session.add(AssetReturnItem(operation_request_asset_id=request_asset_id))
    db.session.commit()

    db.session.add(AssetReturnItem(operation_request_asset_id=request_asset_id))
    with pytest.raises(IntegrityError):
        db.session.flush()
    db.session.rollback()

    count = db.session.scalar(
        select(func.count())
        .select_from(AssetReturnItem)
        .where(AssetReturnItem.operation_request_asset_id == request_asset_id)
    )
    assert count == 1


def test_parent_foreign_keys_reject_nonexistent_rows(app) -> None:
    _enable_sqlite_foreign_keys()
    invalid_rows = (
        AssetUsageRequest(operation_request_id=999_991),
        AssetReturnRequest(operation_request_id=999_992),
        AssetReturnItem(operation_request_asset_id=999_993),
    )

    for invalid_row in invalid_rows:
        db.session.add(invalid_row)
        with pytest.raises(IntegrityError):
            db.session.flush()
        db.session.rollback()


def test_deleting_operation_cascades_usage_return_and_item_rows(app) -> None:
    _enable_sqlite_foreign_keys()
    operation, other_operation, request_assets = _seed_operation_assets()
    operation_id = operation.id
    target_request_asset_ids = [request_assets[0].id, request_assets[1].id]
    unrelated_item = AssetReturnItem(operation_request_asset_id=request_assets[2].id)
    db.session.add_all(
        [
            AssetUsageRequest(operation_request_id=operation_id),
            AssetReturnRequest(operation_request_id=operation_id),
            AssetReturnItem(operation_request_asset_id=request_assets[0].id),
            AssetReturnItem(operation_request_asset_id=request_assets[1].id),
            unrelated_item,
        ]
    )
    db.session.flush()
    unrelated_item_id = unrelated_item.id

    db.session.delete(operation)
    db.session.flush()

    usage_count = db.session.scalar(
        select(func.count())
        .select_from(AssetUsageRequest)
        .where(AssetUsageRequest.operation_request_id == operation_id)
    )
    return_count = db.session.scalar(
        select(func.count())
        .select_from(AssetReturnRequest)
        .where(AssetReturnRequest.operation_request_id == operation_id)
    )
    request_asset_count = db.session.scalar(
        select(func.count())
        .select_from(OperationRequestAsset)
        .where(OperationRequestAsset.operation_request_id == operation_id)
    )
    return_item_count = db.session.scalar(
        select(func.count())
        .select_from(AssetReturnItem)
        .where(AssetReturnItem.operation_request_asset_id.in_(target_request_asset_ids))
    )
    assert usage_count == 0
    assert return_count == 0
    assert request_asset_count == 0
    assert return_item_count == 0
    assert db.session.get(OperationRequest, other_operation.id) is other_operation
    assert db.session.get(AssetReturnItem, unrelated_item_id) is unrelated_item


def test_usage_and_return_requests_restrict_referenced_target_deletes(app) -> None:
    _enable_sqlite_foreign_keys()
    operation, other_operation, _ = _seed_operation_assets()
    target_user = User(username="usage-target-user", password="x", enabled=True)
    confirmed_by = User(username="return-confirmer", password="x", enabled=True)
    target_location = AssetLocation(
        code="TARGET-LOCATION", name="领用目标地点", is_selectable=True
    )
    return_location = AssetLocation(
        code="RETURN-LOCATION", name="退库目标地点", is_selectable=True
    )
    usage_department = Organization(code="TARGET-ORG", name="领用目标组织")
    public_object = PublicUsageObject(code="TARGET-PUBLIC", name="公共领用对象")
    db.session.add_all(
        [
            target_user,
            confirmed_by,
            target_location,
            return_location,
            usage_department,
            public_object,
        ]
    )
    db.session.flush()
    db.session.add_all(
        [
            AssetUsageRequest(
                operation_request_id=operation.id,
                target_user_id=target_user.id,
                target_public_object_id=public_object.id,
                usage_department_id=usage_department.id,
                target_location_id=target_location.id,
            ),
            AssetReturnRequest(
                operation_request_id=other_operation.id,
                return_location_id=return_location.id,
                confirmed_by=confirmed_by.id,
            ),
        ]
    )
    db.session.commit()

    protected_references = (
        (User, target_user.id),
        (User, confirmed_by.id),
        (AssetLocation, target_location.id),
        (AssetLocation, return_location.id),
        (Organization, usage_department.id),
        (PublicUsageObject, public_object.id),
    )
    for model, entity_id in protected_references:
        entity = db.session.get(model, entity_id)
        assert entity is not None
        db.session.delete(entity)
        with pytest.raises(IntegrityError):
            db.session.flush()
        db.session.rollback()
        assert db.session.get(model, entity_id) is not None


def test_leaf_repository_singletons_match_repository_types() -> None:
    assert isinstance(asset_usage_request_repository, AssetUsageRequestRepository)
    assert isinstance(asset_return_request_repository, AssetReturnRequestRepository)
    assert isinstance(asset_return_item_repository, AssetReturnItemRepository)


def test_usage_request_repository_finds_row_by_operation(app) -> None:
    operation, other_operation, _ = _seed_operation_assets()
    expected = AssetUsageRequest(operation_request_id=operation.id)
    db.session.add(expected)
    db.session.flush()

    assert asset_usage_request_repository.find_by_operation(operation.id) is expected
    assert asset_usage_request_repository.find_by_operation(other_operation.id) is None


def test_return_request_repository_finds_row_by_operation(app) -> None:
    operation, other_operation, _ = _seed_operation_assets()
    expected = AssetReturnRequest(operation_request_id=operation.id)
    db.session.add(expected)
    db.session.flush()

    assert asset_return_request_repository.find_by_operation(operation.id) is expected
    assert asset_return_request_repository.find_by_operation(other_operation.id) is None


def test_return_item_repository_finds_operation_items_in_request_asset_order(
    app,
) -> None:
    operation, _, request_assets = _seed_operation_assets()
    first = AssetReturnItem(operation_request_asset_id=request_assets[0].id)
    second = AssetReturnItem(operation_request_asset_id=request_assets[1].id)
    unrelated = AssetReturnItem(operation_request_asset_id=request_assets[2].id)
    db.session.add_all([second, unrelated, first])
    db.session.flush()

    loaded = asset_return_item_repository.find_by_operation(operation.id)

    assert loaded == [first, second]
    assert [item.operation_request_asset_id for item in loaded] == sorted(
        item.operation_request_asset_id for item in loaded
    )


def test_return_item_repository_dedupes_and_sorts_request_asset_ids(app) -> None:
    _, _, request_assets = _seed_operation_assets()
    first = AssetReturnItem(operation_request_asset_id=request_assets[0].id)
    second = AssetReturnItem(operation_request_asset_id=request_assets[1].id)
    db.session.add_all([second, first])
    db.session.flush()

    loaded = asset_return_item_repository.find_by_request_asset_ids(
        (request_assets[1].id, request_assets[0].id, request_assets[1].id)
    )

    assert loaded == [first, second]
    assert asset_return_item_repository.find_by_request_asset_ids(()) == []


def test_return_item_repository_declares_sequence_input() -> None:
    type_hints = get_type_hints(AssetReturnItemRepository.find_by_request_asset_ids)

    assert type_hints["ids"] == Sequence[int]
