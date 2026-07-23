"""Pure calculations for persisted asset data."""

from calendar import monthrange
from datetime import date

from app.enums import AssetDataCompleteness


def calculate_expected_expiry(purchase_date: date, service_life_months: int) -> date:
    month_index = (
        purchase_date.year * 12 + purchase_date.month - 1 + service_life_months
    )
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    return date(year, month, min(purchase_date.day, monthrange(year, month)[1]))


def calculate_completeness_values(
    unit_id: int | None,
    source_id: int | None,
    location_id: int | None,
) -> str:
    if unit_id is not None and source_id is not None and location_id is not None:
        return AssetDataCompleteness.COMPLETE.value
    return AssetDataCompleteness.INCOMPLETE.value


def missing_fields(
    unit_id: int | None,
    source_id: int | None,
    location_id: int | None,
) -> list[str]:
    values = {
        "unit_id": unit_id,
        "source_id": source_id,
        "location_id": location_id,
    }
    return [name for name, value in values.items() if value is None]


__all__ = [
    "calculate_completeness_values",
    "calculate_expected_expiry",
    "missing_fields",
]
