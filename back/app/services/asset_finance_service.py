"""Financial views for assets, including a transparent straight-line trial."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.common import BusinessException, ResultCode
from app.services import asset_access_service, permission_service

_CURRENCY = "CNY"
_ZERO = Decimal("0.00")
_CENT = Decimal("0.01")


def _money(value: Decimal) -> str:
    return str(value.quantize(_CENT, rounding=ROUND_HALF_UP))


def _elapsed_months(purchase_date: date, as_of: date) -> int:
    if as_of < purchase_date:
        return 0
    return max(
        0, (as_of.year - purchase_date.year) * 12 + as_of.month - purchase_date.month
    )


def calculate_straight_line_trial(
    *,
    original_amount: Decimal,
    purchase_date: date,
    service_life_months: int,
    as_of: date,
    expected_expiry_date: date,
) -> dict[str, Any]:
    """Calculate a non-mutating, zero-residual straight-line depreciation trial.

    Depreciation is measured by complete calendar months after the purchase month.
    This is intentionally a view calculation and does not change the asset's
    original amount or create accounting vouchers.
    """
    if original_amount < _ZERO:
        raise BusinessException("金额不能为负数", result_code=ResultCode.BAD_REQUEST)
    if service_life_months <= 0:
        raise BusinessException(
            "资产使用期限必须大于零", result_code=ResultCode.BAD_REQUEST
        )
    if as_of > date.today():
        raise BusinessException(
            "折旧查询日期不能晚于当前日期", result_code=ResultCode.BAD_REQUEST
        )

    elapsed_months = min(_elapsed_months(purchase_date, as_of), service_life_months)
    monthly = original_amount / Decimal(service_life_months)
    accumulated = (
        original_amount * Decimal(elapsed_months) / Decimal(service_life_months)
    )
    accumulated = min(original_amount, accumulated)
    net_book_value = max(_ZERO, original_amount - accumulated)
    remaining_months = service_life_months - elapsed_months

    return {
        "method": "STRAIGHT_LINE",
        "method_name": "直线法（试算）",
        "currency": _CURRENCY,
        "original_amount": _money(original_amount),
        "residual_value": _money(_ZERO),
        "depreciable_amount": _money(original_amount),
        "monthly_depreciation": _money(monthly),
        "accumulated_depreciation": _money(accumulated),
        "net_book_value": _money(net_book_value),
        "purchase_date": purchase_date.isoformat(),
        "as_of": as_of.isoformat(),
        "service_life_months": service_life_months,
        "elapsed_months": elapsed_months,
        "remaining_months": remaining_months,
        "expected_expiry_date": expected_expiry_date.isoformat(),
        "is_fully_depreciated": remaining_months == 0,
    }


def get_summary(
    asset_id: int, actor_id: int, as_of: date | None = None
) -> dict[str, Any]:
    """Return an authorized financial summary for one asset."""
    permission_service.require_permission(actor_id, "asset:amount:view")
    asset = asset_access_service.get_accessible(
        asset_id,
        actor_id,
        permission_code="asset:amount:view",
    )
    summary = calculate_straight_line_trial(
        original_amount=Decimal(asset.original_amount),
        purchase_date=asset.purchase_date,
        service_life_months=asset.service_life_months,
        as_of=as_of or date.today(),
        expected_expiry_date=asset.expected_expiry_date,
    )
    return {
        "asset_id": asset.id,
        "asset_code": asset.asset_code,
        "asset_name": asset.asset_name,
        "status": asset.status,
        "zero_amount_reason": asset.zero_amount_reason,
        **summary,
    }


__all__ = ["calculate_straight_line_trial", "get_summary"]
