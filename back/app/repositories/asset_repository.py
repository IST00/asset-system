"""Asset and asset-code persistence queries."""

from __future__ import annotations

from sqlalchemy import ColumnElement, select

from app.extensions import db
from app.models import Asset, AssetCodeReservation, AssetCodeSequence
from app.repositories.base import BaseRepository


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

    def find_accessible(
        self, asset_id: int, access_filter: ColumnElement[bool]
    ) -> Asset | None:
        return self.find_one(Asset.id == asset_id, access_filter)


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
