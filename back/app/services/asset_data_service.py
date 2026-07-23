"""Pure calculations for persisted asset data."""

from calendar import monthrange
from datetime import date


def calculate_expected_expiry(purchase_date: date, service_life_months: int) -> date:
    month_index = (
        purchase_date.year * 12 + purchase_date.month - 1 + service_life_months
    )
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    return date(year, month, min(purchase_date.day, monthrange(year, month)[1]))


__all__ = ["calculate_expected_expiry"]
