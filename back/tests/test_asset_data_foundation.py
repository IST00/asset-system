from datetime import date

from app.enums import AssetDataCompleteness
from app.models import Asset, StockInItem
from app.services import asset_data_service


def test_expected_expiry_clamps_end_of_month() -> None:
    assert asset_data_service.calculate_expected_expiry(date(2024, 2, 29), 12) == date(
        2025, 2, 28
    )
    assert asset_data_service.calculate_expected_expiry(date(2026, 1, 31), 1) == date(
        2026, 2, 28
    )


def test_asset_data_completeness_requires_all_reference_fields() -> None:
    calculate = getattr(asset_data_service, "calculate_completeness_values", None)
    assert calculate is not None, "missing calculate_completeness_values"

    assert calculate(1, 2, 3) == AssetDataCompleteness.COMPLETE.value
    for values in ((None, 2, 3), (1, None, 3), (1, 2, None), (None, None, None)):
        assert calculate(*values) == AssetDataCompleteness.INCOMPLETE.value


def test_missing_asset_data_fields_preserve_contract_order() -> None:
    find_missing = getattr(asset_data_service, "missing_fields", None)
    assert find_missing is not None, "missing missing_fields"

    assert find_missing(1, 2, 3) == []
    assert find_missing(None, 2, None) == ["unit_id", "location_id"]
    assert find_missing(None, None, None) == [
        "unit_id",
        "source_id",
        "location_id",
    ]


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
