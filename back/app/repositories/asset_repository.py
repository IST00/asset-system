"""Asset and asset-code persistence queries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from sqlalchemy import ColumnElement, select, update

from app.common import BusinessException
from app.extensions import db
from app.models import Asset, AssetCodeReservation, AssetCodeSequence
from app.repositories.base import BaseRepository


_CAS_FIELDS = {
    "status",
    "usage_type",
    "holder_user_id",
    "public_object_id",
    "usage_department_id",
    "location_id",
}


class AssetCodeSequenceRepository(BaseRepository[AssetCodeSequence]):
    def __init__(self) -> None:
        super().__init__(AssetCodeSequence)

    def find_for_update(
        self, top_organization_id: int, category_id: int
    ) -> AssetCodeSequence | None:
        stmt = (
            select(AssetCodeSequence)
            .where(
                AssetCodeSequence.top_organization_id == top_organization_id,
                AssetCodeSequence.category_id == category_id,
            )
            .with_for_update()
        )
        return db.session.scalar(stmt)

    def ensure_exists(self, top_organization_id: int, category_id: int) -> None:
        values = {
            "top_organization_id": top_organization_id,
            "category_id": category_id,
            "current_value": 0,
        }
        dialect = db.session.get_bind().dialect.name
        if dialect == "mysql":
            from sqlalchemy.dialects.mysql import insert as mysql_insert

            mysql_statement = mysql_insert(AssetCodeSequence).values(**values)
            mysql_statement = mysql_statement.on_duplicate_key_update(
                current_value=AssetCodeSequence.current_value
            )
            db.session.execute(mysql_statement)
        elif dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert

            sqlite_statement = sqlite_insert(AssetCodeSequence).values(**values)
            sqlite_statement = sqlite_statement.on_conflict_do_nothing(
                index_elements=["top_organization_id", "category_id"]
            )
            db.session.execute(sqlite_statement)
        else:
            raise RuntimeError(f"unsupported database dialect: {dialect}")


class AssetCodeReservationRepository(BaseRepository[AssetCodeReservation]):
    def __init__(self) -> None:
        super().__init__(AssetCodeReservation)

    def find_by_request(self, operation_request_id: int) -> list[AssetCodeReservation]:
        stmt = select(AssetCodeReservation).where(
            AssetCodeReservation.operation_request_id == operation_request_id
        )
        return list(db.session.scalars(stmt).all())


class AssetRepository(BaseRepository[Asset]):
    def __init__(self) -> None:
        super().__init__(Asset)

    def find_by_code(self, asset_code: str) -> Asset | None:
        return self.find_one(Asset.asset_code == asset_code)

    def find_by_normalized_serial(self, normalized_serial: str) -> Asset | None:
        return self.find_one(Asset.normalized_serial == normalized_serial)

    def has_supplier_reference(self, supplier_id: int) -> bool:
        statement = select(Asset.id).where(Asset.supplier_id == supplier_id).limit(1)
        return db.session.scalar(statement) is not None

    def find_accessible(
        self, asset_id: int, access_filter: ColumnElement[bool]
    ) -> Asset | None:
        return self.find_one(Asset.id == asset_id, access_filter)

    def find_many_ordered(self, asset_ids: Sequence[int]) -> list[Asset]:
        ids = sorted(set(asset_ids))
        if not ids:
            return []
        statement = select(Asset).where(Asset.id.in_(ids)).order_by(Asset.id.asc())
        return list(db.session.scalars(statement).all())

    def find_direct_children(self, parent_ids: Sequence[int]) -> list[Asset]:
        ids = sorted(set(parent_ids))
        if not ids:
            return []
        statement = (
            select(Asset).where(Asset.parent_asset_id.in_(ids)).order_by(Asset.id.asc())
        )
        return list(db.session.scalars(statement).all())

    def find_many_for_update(self, asset_ids: Sequence[int]) -> list[Asset]:
        ids = sorted(set(asset_ids))
        if not ids:
            return []
        statement = (
            select(Asset)
            .where(Asset.id.in_(ids))
            .order_by(Asset.id.asc())
            .with_for_update()
        )
        return list(db.session.scalars(statement).all())

    def cas_update(
        self,
        asset_id: int,
        expected_version: int,
        changes: Mapping[str, object],
    ) -> bool:
        invalid = set(changes) - _CAS_FIELDS
        if invalid:
            raise BusinessException(f"资产字段不允许更新: {', '.join(sorted(invalid))}")
        if not changes:
            raise BusinessException("资产更新内容不能为空")
        statement = (
            update(Asset)
            .where(Asset.id == asset_id, Asset.version == expected_version)
            .values(**dict(changes), version=Asset.version + 1)
            .execution_options(synchronize_session=False)
        )
        result = db.session.execute(statement)
        return result.rowcount == 1


asset_code_sequence_repository = AssetCodeSequenceRepository()
asset_code_reservation_repository = AssetCodeReservationRepository()
asset_repository = AssetRepository()

__all__ = [
    "AssetCodeReservationRepository",
    "AssetCodeSequenceRepository",
    "AssetRepository",
    "asset_code_reservation_repository",
    "asset_code_sequence_repository",
    "asset_repository",
]
