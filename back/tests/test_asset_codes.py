from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier

from app import create_app
from app.enums import ApprovalStatus, AssetCodeStatus, ExecutionStatus, OperationType
from app.extensions import db
from app.models import (
    AssetCategory,
    AssetCodeSequence,
    AssetLocation,
    AssetSource,
    OperationRequest,
    Organization,
    StockInItem,
    StockInRequest,
    Unit,
    User,
)
from app.services import asset_code_service
from config import TestConfig


def _stock_in_context():
    organization = Organization(code="358466", name="公司")
    other_organization = Organization(code="358465", name="其他公司")
    unit = Unit(code="UNIT", name="台")
    source = AssetSource(code="PURCHASE", name="采购")
    location = AssetLocation(code="LOC", name="仓库", is_selectable=True)
    user = User(username="code-user", password="x", enabled=True)
    db.session.add_all([organization, other_organization, unit, source, location, user])
    db.session.flush()
    category = AssetCategory(
        code="10100", name="电脑", service_life_months=36, default_unit_id=unit.id
    )
    other_category = AssetCategory(
        code="10200", name="显示器", service_life_months=36, default_unit_id=unit.id
    )
    db.session.add_all([category, other_category])
    db.session.flush()
    operation = OperationRequest(
        request_no="CODE-REQUEST",
        operation_type=OperationType.STOCK_IN.value,
        applicant_id=user.id,
        approval_status=ApprovalStatus.PENDING.value,
        execution_status=ExecutionStatus.NOT_STARTED.value,
        flow_version=1,
    )
    db.session.add(operation)
    db.session.flush()
    stock_in = StockInRequest(
        operation_request_id=operation.id, organization_id=organization.id
    )
    db.session.add(stock_in)
    db.session.flush()
    return (
        organization,
        other_organization,
        category,
        other_category,
        unit,
        source,
        location,
        user,
        operation,
        stock_in,
    )


def _item(stock_in, code, category, unit, source, location, user):
    item = StockInItem(
        stock_in_request_id=stock_in.id,
        asset_code=code,
        asset_name="测试资产",
        category_id=category.id,
        unit_id=unit.id,
        original_amount=Decimal("1.00"),
        purchase_date=date(2026, 7, 17),
        manager_id=user.id,
        source_id=source.id,
        location_id=location.id,
    )
    db.session.add(item)
    db.session.flush()
    return item


def test_sequences_are_isolated_by_top_organization_and_category(app) -> None:
    (
        organization,
        other_organization,
        category,
        other_category,
        *_rest,
    ) = _stock_in_context()

    first = asset_code_service.allocate(organization, category)
    second = asset_code_service.allocate(organization, category)
    other_cat = asset_code_service.allocate(organization, other_category)
    other_org = asset_code_service.allocate(other_organization, category)

    assert first.asset_code == "358466-10100-0001"
    assert second.asset_code == "358466-10100-0002"
    assert other_cat.asset_code == "358466-10200-0001"
    assert other_org.asset_code == "358465-10100-0001"


def test_sequence_expands_and_void_codes_are_never_reused(app) -> None:
    (
        organization,
        _other_organization,
        category,
        _other_category,
        unit,
        source,
        location,
        user,
        operation,
        stock_in,
    ) = _stock_in_context()
    db.session.add(
        AssetCodeSequence(
            top_organization_id=organization.id,
            category_id=category.id,
            current_value=9999,
        )
    )
    db.session.flush()

    allocated = asset_code_service.allocate(organization, category)
    item = _item(stock_in, allocated.asset_code, category, unit, source, location, user)
    reservation = asset_code_service.reserve(operation.id, item.id, allocated)
    asset_code_service.void_for_request(operation.id)
    next_code = asset_code_service.allocate(organization, category)

    assert allocated.asset_code == "358466-10100-10000"
    assert reservation.status == AssetCodeStatus.VOID.value
    assert next_code.asset_code == "358466-10100-10001"


def test_first_sequence_allocation_is_safe_across_independent_transactions(
    tmp_path,
) -> None:
    database = tmp_path / "asset-code-concurrency.db"

    class ConcurrentConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{database}"

    concurrent_app = create_app(config=ConcurrentConfig)
    with concurrent_app.app_context():
        db.create_all()
        organization = Organization(code="CONCURRENT", name="并发公司")
        unit = Unit(code="CONCURRENT-UNIT", name="并发单位")
        db.session.add_all([organization, unit])
        db.session.flush()
        category = AssetCategory(
            code="CONCURRENT-CATEGORY",
            name="并发分类",
            service_life_months=12,
            default_unit_id=unit.id,
        )
        db.session.add(category)
        db.session.commit()
        organization_id = organization.id
        category_id = category.id

    barrier = Barrier(2)

    def allocate_once() -> str:
        with concurrent_app.app_context():
            organization = db.session.get(Organization, organization_id)
            category = db.session.get(AssetCategory, category_id)
            assert organization is not None and category is not None
            barrier.wait()
            allocated = asset_code_service.allocate(organization, category)
            db.session.commit()
            return allocated.asset_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        codes = list(executor.map(lambda _index: allocate_once(), range(2)))

    assert sorted(codes) == [
        "CONCURRENT-CONCURRENT-CATEGORY-0001",
        "CONCURRENT-CONCURRENT-CATEGORY-0002",
    ]

    with concurrent_app.app_context():
        assert db.session.query(AssetCodeSequence).one().current_value == 2
        db.drop_all()
