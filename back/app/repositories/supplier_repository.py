"""Supplier and supplier-code-sequence persistence queries."""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import select, update

from app.common import BusinessException
from app.extensions import db
from app.models import Supplier, SupplierCodeSequence
from app.repositories.base import BaseRepository


_PREFIX = "SUP"
_CAS_FIELDS = {
    "name",
    "unified_social_credit_code",
    "contact_name",
    "contact_phone",
    "address",
    "remark",
    "status",
}


class SupplierCodeSequenceRepository(BaseRepository[SupplierCodeSequence]):
    def __init__(self) -> None:
        super().__init__(SupplierCodeSequence)

    def ensure_exists(self) -> None:
        values = {"prefix": _PREFIX, "current_value": 0}
        dialect = db.session.get_bind().dialect.name
        if dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert

            sqlite_statement = sqlite_insert(SupplierCodeSequence).values(**values)
            sqlite_statement = sqlite_statement.on_conflict_do_nothing(
                index_elements=["prefix"]
            )
            db.session.execute(sqlite_statement)
        elif dialect == "mysql":
            from sqlalchemy.dialects.mysql import insert as mysql_insert

            mysql_statement = mysql_insert(SupplierCodeSequence).values(**values)
            mysql_statement = mysql_statement.on_duplicate_key_update(
                current_value=SupplierCodeSequence.current_value
            )
            db.session.execute(mysql_statement)
        else:
            raise RuntimeError(f"unsupported database dialect: {dialect}")

    def find_for_update(self) -> SupplierCodeSequence | None:
        statement = (
            select(SupplierCodeSequence)
            .where(SupplierCodeSequence.prefix == _PREFIX)
            .with_for_update()
        )
        return db.session.scalar(statement)


class SupplierRepository(BaseRepository[Supplier]):
    def __init__(self) -> None:
        super().__init__(Supplier)

    def find_by_code(self, code: str) -> Supplier | None:
        return self.find_one(Supplier.code == code)

    def find_by_name(self, name: str) -> Supplier | None:
        return self.find_one(Supplier.name == name)

    def find_by_credit_code(self, unified_social_credit_code: str) -> Supplier | None:
        return self.find_one(
            Supplier.unified_social_credit_code == unified_social_credit_code
        )

    def list_all(self) -> list[Supplier]:
        statement = select(Supplier).order_by(Supplier.code.asc())
        return list(db.session.scalars(statement).all())

    def find_for_update(self, supplier_id: int) -> Supplier | None:
        statement = select(Supplier).where(Supplier.id == supplier_id).with_for_update()
        return db.session.scalar(statement)

    def cas_update(
        self,
        supplier_id: int,
        expected_version: int,
        changes: Mapping[str, object],
    ) -> bool:
        invalid = set(changes) - _CAS_FIELDS
        if invalid:
            raise BusinessException(
                f"供应商字段不允许更新: {', '.join(sorted(invalid))}"
            )
        if not changes:
            raise BusinessException("供应商更新内容不能为空")
        statement = (
            update(Supplier)
            .where(Supplier.id == supplier_id, Supplier.version == expected_version)
            .values(**dict(changes), version=Supplier.version + 1)
            .execution_options(synchronize_session=False)
        )
        result = db.session.execute(statement)
        return result.rowcount == 1


supplier_code_sequence_repository = SupplierCodeSequenceRepository()
supplier_repository = SupplierRepository()

__all__ = [
    "SupplierCodeSequenceRepository",
    "SupplierRepository",
    "supplier_code_sequence_repository",
    "supplier_repository",
]
