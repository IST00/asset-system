from app.models import Supplier, SupplierCodeSequence


def test_supplier_contract_uses_independent_persistent_sequence(app) -> None:
    assert SupplierCodeSequence.__table__.primary_key.columns.keys() == ["prefix"]
    assert SupplierCodeSequence.__table__.c.current_value.nullable is False
    assert Supplier.__table__.c.code.unique is True
    assert Supplier.__table__.c.name.unique is True
    assert Supplier.__table__.c.unified_social_credit_code.unique is True
