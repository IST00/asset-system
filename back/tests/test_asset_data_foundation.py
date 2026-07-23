from datetime import date

from app.enums import AssetDataCompleteness
from app.models import Asset, StockInItem
from app.services.asset_data_service import calculate_expected_expiry


def test_expected_expiry_clamps_end_of_month() -> None:
    assert calculate_expected_expiry(date(2024, 2, 29), 12) == date(2025, 2, 28)
    assert calculate_expected_expiry(date(2026, 1, 31), 1) == date(2026, 2, 28)


def test_asset_data_contract_is_import_compatible_and_life_is_required(app) -> None:
    assert {item.value for item in AssetDataCompleteness} == {
        "COMPLETE",
        "INCOMPLETE",
    }
    for name in ("unit_id", "source_id", "location_id"):
        assert Asset.__table__.c[name].nullable is True
        assert StockInItem.__table__.c[name].nullable is False
    for table in (Asset.__table__, StockInItem.__table__):
        assert table.c.service_life_months.nullable is False
        assert table.c.expected_expiry_date.nullable is False
        assert table.c.custom_attributes.nullable is False
    assert Asset.__table__.c.data_completeness.nullable is False
