from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.common import BusinessException, ResultCode
from app.enums import AssetDataCompleteness, AssetStatus, DataScope
from app.extensions import db
from app.models import (
    Asset,
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
from app.services import asset_finance_service


def _user_with_permissions(
    username: str,
    permission_codes: list[str],
    *,
    organization_id: int | None = None,
    data_scope: str = DataScope.ALL.value,
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


def _asset_fixture() -> tuple[User, Asset]:
    organization = Organization(code="FIN-ORG", name="财务测试公司")
    unit = Unit(code="FIN-UNIT", name="台")
    source = AssetSource(code="FIN-SOURCE", name="采购")
    location = AssetLocation(code="FIN-LOC", name="财务测试仓", is_selectable=True)
    db.session.add_all([organization, unit, source, location])
    db.session.flush()

    actor = _user_with_permissions(
        "finance-reader",
        ["asset:amount:view"],
        organization_id=organization.id,
    )
    category = AssetCategory(
        code="FIN-CATEGORY",
        name="财务测试设备",
        service_life_months=36,
        default_unit_id=unit.id,
    )
    db.session.add(category)
    db.session.flush()
    asset = Asset(
        asset_code="FIN-ASSET-0001",
        asset_name="财务测试设备",
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
    db.session.add(asset)
    db.session.commit()
    return actor, asset


def test_straight_line_trial_returns_expected_values() -> None:
    summary = asset_finance_service.calculate_straight_line_trial(
        original_amount=Decimal("1000.00"),
        purchase_date=date(2026, 1, 1),
        service_life_months=36,
        as_of=date(2026, 7, 1),
        expected_expiry_date=date(2029, 1, 1),
    )

    assert summary["elapsed_months"] == 6
    assert summary["remaining_months"] == 30
    assert summary["monthly_depreciation"] == "27.78"
    assert summary["accumulated_depreciation"] == "166.67"
    assert summary["net_book_value"] == "833.33"


def test_trial_before_purchase_date_has_no_depreciation() -> None:
    summary = asset_finance_service.calculate_straight_line_trial(
        original_amount=Decimal("1000.00"),
        purchase_date=date(2026, 6, 15),
        service_life_months=36,
        as_of=date(2026, 5, 31),
        expected_expiry_date=date(2029, 6, 15),
    )

    assert summary["elapsed_months"] == 0
    assert summary["accumulated_depreciation"] == "0.00"
    assert summary["net_book_value"] == "1000.00"


def test_trial_stops_at_service_life() -> None:
    summary = asset_finance_service.calculate_straight_line_trial(
        original_amount=Decimal("1000.00"),
        purchase_date=date(2020, 1, 1),
        service_life_months=36,
        as_of=date(2026, 9, 1),
        expected_expiry_date=date(2023, 1, 1),
    )

    assert summary["elapsed_months"] == 36
    assert summary["remaining_months"] == 0
    assert summary["accumulated_depreciation"] == "1000.00"
    assert summary["net_book_value"] == "0.00"
    assert summary["is_fully_depreciated"] is True


@pytest.mark.parametrize(
    ("original_amount", "service_life_months", "message"),
    [
        (Decimal("-1.00"), 36, "资产原值不能为负数"),
        (Decimal("1000.00"), 0, "资产使用期限必须大于零"),
    ],
)
def test_trial_rejects_invalid_financial_inputs(
    original_amount: Decimal, service_life_months: int, message: str
) -> None:
    with pytest.raises(BusinessException, match=message) as raised:
        asset_finance_service.calculate_straight_line_trial(
            original_amount=original_amount,
            purchase_date=date(2026, 1, 1),
            service_life_months=service_life_months,
            as_of=date(2026, 7, 1),
            expected_expiry_date=date(2029, 1, 1),
        )
    assert raised.value.code == ResultCode.BAD_REQUEST.code


def test_trial_allows_zero_amount() -> None:
    summary = asset_finance_service.calculate_straight_line_trial(
        original_amount=Decimal("0.00"),
        purchase_date=date(2026, 1, 1),
        service_life_months=36,
        as_of=date(2026, 7, 1),
        expected_expiry_date=date(2029, 1, 1),
    )

    assert summary["monthly_depreciation"] == "0.00"
    assert summary["accumulated_depreciation"] == "0.00"
    assert summary["net_book_value"] == "0.00"


def test_trial_rejects_future_as_of() -> None:
    with pytest.raises(BusinessException, match="折旧查询日期不能晚于当前日期"):
        asset_finance_service.calculate_straight_line_trial(
            original_amount=Decimal("1000.00"),
            purchase_date=date(2026, 1, 1),
            service_life_months=36,
            as_of=date(2099, 1, 1),
            expected_expiry_date=date(2029, 1, 1),
        )


def test_get_summary_checks_permission_and_data_scope(app) -> None:
    with app.app_context():
        actor, asset = _asset_fixture()
        summary = asset_finance_service.get_summary(
            asset.id, actor.id, date(2026, 7, 1)
        )
        assert summary["asset_id"] == asset.id
        assert summary["asset_code"] == "FIN-ASSET-0001"
        assert summary["original_amount"] == "1000.00"
        assert summary["net_book_value"] == "833.33"

        forbidden_actor = _user_with_permissions(
            "finance-no-amount", [], data_scope=DataScope.ALL.value
        )
        with pytest.raises(BusinessException) as forbidden:
            asset_finance_service.get_summary(asset.id, forbidden_actor.id)
        assert forbidden.value.code == ResultCode.FORBIDDEN.code

        other_org = Organization(code="FIN-OTHER", name="其它财务公司")
        db.session.add(other_org)
        db.session.flush()
        scoped_actor = _user_with_permissions(
            "finance-scoped",
            ["asset:amount:view"],
            organization_id=other_org.id,
            data_scope=DataScope.DEPARTMENT.value,
        )
        with pytest.raises(BusinessException) as out_of_scope:
            asset_finance_service.get_summary(asset.id, scoped_actor.id)
        assert out_of_scope.value.code == ResultCode.NOT_FOUND.code


def test_financial_summary_api_returns_unwrapped_payload(client) -> None:
    actor, asset = _asset_fixture()
    response = client.post(
        "/api/v1/auth/login",
        json={"username": actor.username, "password": "admin123"},
    )
    token = response.get_json()["data"]["token"]

    result = client.get(
        f"/api/v1/assets/{asset.id}/financial-summary?as_of=2026-07-01",
        headers={"Authorization": f"Bearer {token}"},
    )

    body = result.get_json()
    assert result.status_code == 200
    assert body["code"] == 200
    assert body["data"]["method"] == "STRAIGHT_LINE"
    assert body["data"]["accumulated_depreciation"] == "166.67"


def test_financial_summary_api_rejects_malformed_date(client) -> None:
    actor, asset = _asset_fixture()
    response = client.post(
        "/api/v1/auth/login",
        json={"username": actor.username, "password": "admin123"},
    )
    token = response.get_json()["data"]["token"]

    result = client.get(
        f"/api/v1/assets/{asset.id}/financial-summary?as_of=not-a-date",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert result.status_code == 400
    assert result.get_json()["code"] == ResultCode.BAD_REQUEST.code
