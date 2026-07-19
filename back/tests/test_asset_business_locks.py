"""Atomic operation submission and current asset-lock contracts."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier

import app.services as services
from app import create_app
from app.common import BusinessException
from app.enums import ApprovalChannel, ApprovalStatus, AssetStatus, ExecutionStatus
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
            manager_id=users[0].id,
            source_id=source.id,
            location_id=location.id,
        )
        for index in range(2)
    ]
    db.session.add_all(assets)
    db.session.flush()
    return organization, users, assets


def test_create_request_snapshots_and_locks_assets_in_stable_order(app) -> None:
    organization, users, assets = _seed_assets()
    service = _operation_service()
    operation = service.create_request(
        operation_type="TRANSFER",
        applicant_id=users[0].id,
        approval_channel=ApprovalChannel.INTERNAL.value,
        organization_id=organization.id,
        assets=list(reversed(assets)),
        idempotency_key="transfer-once",
    )

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
    locks = db.session.query(AssetBusinessLock).order_by(AssetBusinessLock.id).all()
    assert [lock.asset_id for lock in locks] == [assets[0].id, assets[1].id]
    assert all(lock.operation_request_id == operation.id for lock in locks)

    replay = service.create_request(
        operation_type="TRANSFER",
        applicant_id=users[0].id,
        approval_channel=ApprovalChannel.INTERNAL.value,
        organization_id=organization.id,
        assets=assets,
        idempotency_key="transfer-once",
    )
    assert replay.id == operation.id
    assert db.session.query(OperationRequest).count() == 1
    assert db.session.query(AssetBusinessLock).count() == 2


def test_create_request_validates_whole_batch_before_persisting(app) -> None:
    organization, users, assets = _seed_assets("ATOMIC")
    other = Organization(code="ATOMIC-OTHER", name="其它组织")
    db.session.add(other)
    db.session.flush()
    assets[1].organization_id = other.id
    db.session.flush()

    try:
        _operation_service().create_request(
            operation_type="TRANSFER",
            applicant_id=users[0].id,
            approval_channel=ApprovalChannel.INTERNAL.value,
            organization_id=organization.id,
            assets=assets,
            idempotency_key=None,
        )
    except BusinessException as error:
        assert "组织" in error.message
    else:
        raise AssertionError("mixed-organization request should fail")
    assert db.session.query(OperationRequest).count() == 0
    assert db.session.query(OperationRequestAsset).count() == 0
    assert db.session.query(AssetBusinessLock).count() == 0


def test_lock_conflict_rolls_back_new_request_and_returns_safe_context(app) -> None:
    organization, users, assets = _seed_assets("CONFLICT")
    service = _operation_service()
    first = service.create_request(
        operation_type="TRANSFER",
        applicant_id=users[0].id,
        approval_channel=ApprovalChannel.INTERNAL.value,
        organization_id=organization.id,
        assets=[assets[0]],
        idempotency_key="first",
    )
    db.session.commit()

    try:
        service.create_request(
            operation_type="REPAIR",
            applicant_id=users[1].id,
            approval_channel=ApprovalChannel.INTERNAL.value,
            organization_id=organization.id,
            assets=[assets[0]],
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
        organization, users, assets = _seed_assets("RACE")
        db.session.commit()
        organization_id = organization.id
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
                    organization_id=organization_id,
                    assets=[asset],
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
        organization, users, assets = _seed_assets("IDEMPOTENT")
        db.session.commit()
        organization_id = organization.id
        applicant_id = users[0].id
        asset_id = assets[0].id

    barrier = Barrier(2)

    def submit() -> int:
        with concurrent_app.app_context():
            asset = db.session.get(Asset, asset_id)
            assert asset is not None
            barrier.wait()
            operation = _operation_service().create_request(
                operation_type="TRANSFER",
                applicant_id=applicant_id,
                approval_channel=ApprovalChannel.INTERNAL.value,
                organization_id=organization_id,
                assets=[asset],
                idempotency_key="same-request",
            )
            db.session.commit()
            return operation.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        operation_ids = list(executor.map(lambda _index: submit(), range(2)))

    assert operation_ids[0] == operation_ids[1]
    with concurrent_app.app_context():
        assert db.session.query(OperationRequest).count() == 1
        assert db.session.query(OperationRequestAsset).count() == 1
        assert db.session.query(AssetBusinessLock).count() == 1
        db.drop_all()
