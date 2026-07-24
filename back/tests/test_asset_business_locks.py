"""Atomic operation submission and current asset-lock contracts."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier

import app.services as services
import pytest
from app import create_app
from app.common import BusinessException
from app.enums import (
    ApprovalChannel,
    ApprovalExecutionMode,
    ApprovalStatus,
    AssetDataCompleteness,
    AssetStatus,
    ExecutionStatus,
    OperationType,
)
from app.extensions import db
from app.models import (
    Asset,
    AssetBusinessLock,
    AssetCategory,
    AssetLocation,
    AssetSource,
    OperationRequest,
    OperationRequestAsset,
    Organization,
    Unit,
    User,
)
from config import TestConfig


def _operation_service():
    service = getattr(services, "operation_service", None)
    assert service is not None, "missing operation_service"
    return service


def _target_data(assets: list[Asset]) -> dict[int, dict[str, int]]:
    return {asset.id: {"location_id": asset.location_id} for asset in assets}


def _seed_assets(prefix: str = "LOCK") -> tuple[Organization, list[User], list[Asset]]:
    organization = Organization(code=f"{prefix}-ORG", name=f"{prefix}组织")
    unit = Unit(code=f"{prefix}-UNIT", name=f"{prefix}单位")
    source = AssetSource(code=f"{prefix}-SOURCE", name=f"{prefix}来源")
    location = AssetLocation(
        code=f"{prefix}-LOCATION", name=f"{prefix}地点", is_selectable=True
    )
    users = [
        User(username=f"{prefix.lower()}-user-{index}", password="x", enabled=True)
        for index in range(2)
    ]
    db.session.add_all([organization, unit, source, location, *users])
    db.session.flush()
    category = AssetCategory(
        code=f"{prefix}-CATEGORY",
        name=f"{prefix}分类",
        service_life_months=12,
        default_unit_id=unit.id,
    )
    db.session.add(category)
    db.session.flush()
    assets = [
        Asset(
            asset_code=f"{prefix}-ASSET-{index}",
            asset_name=f"{prefix}资产{index}",
            status=AssetStatus.IDLE.value,
            organization_id=organization.id,
            category_id=category.id,
            unit_id=unit.id,
            original_amount=Decimal("1.00"),
            purchase_date=date(2026, 7, 17),
            service_life_months=36,
            expected_expiry_date=date(2029, 1, 1),
            manager_id=users[0].id,
            source_id=source.id,
            location_id=location.id,
            custom_attributes={},
            data_completeness=AssetDataCompleteness.COMPLETE.value,
        )
        for index in range(2)
    ]
    db.session.add_all(assets)
    db.session.flush()
    return organization, users, assets


def test_create_request_snapshots_and_locks_assets_in_stable_order(app) -> None:
    _organization, users, assets = _seed_assets()
    service = _operation_service()
    result = service.create_request(
        operation_type="TRANSFER",
        applicant_id=users[0].id,
        approval_channel=ApprovalChannel.INTERNAL.value,
        approval_execution_mode=ApprovalExecutionMode.AUTO_ON_APPROVAL.value,
        assets=list(reversed(assets)),
        target_data_by_asset_id=_target_data(assets),
        idempotency_key="transfer-once",
    )
    assert result.created is True
    operation = result.operation

    assert operation.approval_status == ApprovalStatus.PENDING.value
    assert operation.execution_status == ExecutionStatus.NOT_STARTED.value
    snapshots = (
        db.session.query(OperationRequestAsset).order_by(OperationRequestAsset.id).all()
    )
    assert [snapshot.asset_id for snapshot in snapshots] == [
        assets[0].id,
        assets[1].id,
    ]
    assert snapshots[0].asset_code_snapshot == assets[0].asset_code
    assert snapshots[0].asset_status_snapshot == AssetStatus.IDLE.value
    assert snapshots[0].asset_version_snapshot == assets[0].version
    assert snapshots[0].before_data["location_id"] == assets[0].location_id
    assert snapshots[0].target_data == {"location_id": assets[0].location_id}
    locks = db.session.query(AssetBusinessLock).order_by(AssetBusinessLock.id).all()
    assert [lock.asset_id for lock in locks] == [assets[0].id, assets[1].id]
    assert all(lock.operation_request_id == operation.id for lock in locks)

    replay = service.create_request(
        operation_type="TRANSFER",
        applicant_id=users[0].id,
        approval_channel=ApprovalChannel.INTERNAL.value,
        approval_execution_mode=ApprovalExecutionMode.AUTO_ON_APPROVAL.value,
        assets=assets,
        target_data_by_asset_id=_target_data(assets),
        idempotency_key="transfer-once",
    )
    assert replay.created is False
    assert replay.operation.id == operation.id
    assert db.session.query(OperationRequest).count() == 1
    assert db.session.query(AssetBusinessLock).count() == 2


def test_create_request_accepts_mixed_organizations_after_feature_validation(
    app,
) -> None:
    _organization, users, assets = _seed_assets("ATOMIC")
    other = Organization(code="ATOMIC-OTHER", name="其它组织")
    db.session.add(other)
    db.session.flush()
    assets[1].organization_id = other.id
    db.session.flush()

    result = _operation_service().create_request(
        operation_type="TRANSFER",
        applicant_id=users[0].id,
        approval_channel=ApprovalChannel.INTERNAL.value,
        approval_execution_mode=ApprovalExecutionMode.AUTO_ON_APPROVAL.value,
        assets=assets,
        target_data_by_asset_id=_target_data(assets),
        idempotency_key=None,
    )

    assert result.created is True
    assert {
        item.organization_id_snapshot
        for item in db.session.query(OperationRequestAsset).all()
    } == {asset.organization_id for asset in assets}


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("data_completeness", AssetDataCompleteness.INCOMPLETE.value),
        ("unit_id", None),
        ("source_id", None),
        ("location_id", None),
    ],
)
def test_return_create_request_rejects_incomplete_assets_before_snapshot_and_lock(
    app,
    field_name: str,
    invalid_value: str | None,
) -> None:
    _organization, users, assets = _seed_assets(f"INCOMPLETE-{field_name.upper()}")
    asset = assets[0]
    setattr(asset, field_name, invalid_value)
    db.session.flush()

    with pytest.raises(BusinessException, match="^资产数据不完整，请先补齐$"):
        _operation_service().create_request(
            operation_type=OperationType.PERSONAL_RETURN.value,
            applicant_id=users[0].id,
            approval_channel=ApprovalChannel.INTERNAL.value,
            approval_execution_mode=ApprovalExecutionMode.AUTO_ON_APPROVAL.value,
            assets=[asset],
            target_data_by_asset_id={asset.id: {"location_id": assets[1].location_id}},
            idempotency_key=None,
        )

    assert db.session.query(OperationRequest).count() == 0
    assert db.session.query(OperationRequestAsset).count() == 0
    assert db.session.query(AssetBusinessLock).count() == 0


@pytest.mark.parametrize("case", ["missing", "extra", "not-json"])
def test_create_request_rejects_invalid_target_snapshots(app, case: str) -> None:
    _organization, users, assets = _seed_assets(f"TARGET-{case.upper()}")
    asset = assets[0]
    if case == "missing":
        target_data: dict[int, dict] = {}
    elif case == "extra":
        target_data = {asset.id: {}, assets[1].id: {}}
    else:
        target_data = {asset.id: {"bad": object()}}

    with pytest.raises(BusinessException):
        _operation_service().create_request(
            operation_type="TRANSFER",
            applicant_id=users[0].id,
            approval_channel=ApprovalChannel.INTERNAL.value,
            approval_execution_mode=ApprovalExecutionMode.AUTO_ON_APPROVAL.value,
            assets=[asset],
            target_data_by_asset_id=target_data,
            idempotency_key=None,
        )


def test_create_request_rejects_transient_asset_with_existing_database_id(
    app,
) -> None:
    _organization, users, assets = _seed_assets("SPOOF")
    real = assets[0]
    spoof = Asset(
        id=real.id,
        asset_code="SPOOF-CODE",
        asset_name="伪造资产",
        status=AssetStatus.REPAIRING.value,
        organization_id=real.organization_id,
        category_id=real.category_id,
        unit_id=real.unit_id,
        original_amount=real.original_amount,
        purchase_date=real.purchase_date,
        service_life_months=36,
        expected_expiry_date=date(2029, 1, 1),
        manager_id=real.manager_id,
        source_id=real.source_id,
        location_id=real.location_id,
        custom_attributes={},
        data_completeness=AssetDataCompleteness.COMPLETE.value,
        version=77,
    )

    with pytest.raises(BusinessException, match="持久化"):
        _operation_service().create_request(
            operation_type="TRANSFER",
            applicant_id=users[0].id,
            approval_channel=ApprovalChannel.INTERNAL.value,
            approval_execution_mode=ApprovalExecutionMode.AUTO_ON_APPROVAL.value,
            assets=[spoof],
            target_data_by_asset_id={real.id: {"location_id": real.location_id}},
            idempotency_key="spoof-request",
        )


def test_lock_conflict_rolls_back_new_request_and_returns_safe_context(app) -> None:
    _organization, users, assets = _seed_assets("CONFLICT")
    service = _operation_service()
    first = service.create_request(
        operation_type="TRANSFER",
        applicant_id=users[0].id,
        approval_channel=ApprovalChannel.INTERNAL.value,
        approval_execution_mode=ApprovalExecutionMode.AUTO_ON_APPROVAL.value,
        assets=[assets[0]],
        target_data_by_asset_id=_target_data([assets[0]]),
        idempotency_key="first",
    ).operation
    db.session.commit()

    try:
        service.create_request(
            operation_type="REPAIR",
            applicant_id=users[1].id,
            approval_channel=ApprovalChannel.INTERNAL.value,
            approval_execution_mode=ApprovalExecutionMode.AUTO_ON_APPROVAL.value,
            assets=[assets[0]],
            target_data_by_asset_id=_target_data([assets[0]]),
            idempotency_key="second",
        )
    except BusinessException as error:
        assert assets[0].asset_code in error.message
        assert first.request_no in error.message
        assert "SQL" not in error.message
    else:
        raise AssertionError("current asset lock should reject another request")
    assert db.session.query(OperationRequest).count() == 1
    assert db.session.query(AssetBusinessLock).count() == 1

    service.release_locks(first.id)
    db.session.flush()
    assert db.session.query(AssetBusinessLock).count() == 0


def test_concurrent_requests_for_same_asset_have_one_winner(tmp_path) -> None:
    database = tmp_path / "asset-lock-concurrency.db"

    class ConcurrentConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{database}"

    concurrent_app = create_app(config=ConcurrentConfig)
    with concurrent_app.app_context():
        db.create_all()
        _organization, users, assets = _seed_assets("RACE")
        db.session.commit()
        user_ids = [user.id for user in users]
        asset_id = assets[0].id

    barrier = Barrier(2)

    def submit(index: int) -> str:
        with concurrent_app.app_context():
            barrier.wait()
            asset = db.session.get(Asset, asset_id)
            assert asset is not None
            try:
                _operation_service().create_request(
                    operation_type=f"RACE_{index}",
                    applicant_id=user_ids[index],
                    approval_channel=ApprovalChannel.INTERNAL.value,
                    approval_execution_mode=(
                        ApprovalExecutionMode.AUTO_ON_APPROVAL.value
                    ),
                    assets=[asset],
                    target_data_by_asset_id=_target_data([asset]),
                    idempotency_key=f"race-{index}",
                )
                db.session.commit()
                return "SUCCESS"
            except BusinessException:
                db.session.rollback()
                return "CONFLICT"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(submit, range(2)))
    assert sorted(results) == ["CONFLICT", "SUCCESS"]
    with concurrent_app.app_context():
        assert db.session.query(OperationRequest).count() == 1
        assert db.session.query(AssetBusinessLock).count() == 1
        db.drop_all()


def test_concurrent_same_idempotency_key_replays_one_request(tmp_path) -> None:
    database = tmp_path / "request-idempotency-concurrency.db"

    class ConcurrentConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{database}"

    concurrent_app = create_app(config=ConcurrentConfig)
    with concurrent_app.app_context():
        db.create_all()
        _organization, users, assets = _seed_assets("IDEMPOTENT")
        db.session.commit()
        applicant_id = users[0].id
        asset_id = assets[0].id

    barrier = Barrier(2)

    def submit() -> int:
        with concurrent_app.app_context():
            asset = db.session.get(Asset, asset_id)
            assert asset is not None
            barrier.wait()
            result = _operation_service().create_request(
                operation_type="TRANSFER",
                applicant_id=applicant_id,
                approval_channel=ApprovalChannel.INTERNAL.value,
                approval_execution_mode=(ApprovalExecutionMode.AUTO_ON_APPROVAL.value),
                assets=[asset],
                target_data_by_asset_id=_target_data([asset]),
                idempotency_key="same-request",
            )
            db.session.commit()
            return result.operation.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        operation_ids = list(executor.map(lambda _index: submit(), range(2)))

    assert operation_ids[0] == operation_ids[1]
    with concurrent_app.app_context():
        assert db.session.query(OperationRequest).count() == 1
        assert db.session.query(OperationRequestAsset).count() == 1
        assert db.session.query(AssetBusinessLock).count() == 1
        db.drop_all()
