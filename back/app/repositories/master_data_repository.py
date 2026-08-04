"""Persistence queries for organization and asset master data."""

from __future__ import annotations

from sqlalchemy import select

from app.extensions import db
from app.models import (
    AssetCategory,
    AssetLocation,
    AssetSource,
    LocationCodeSequence,
    Organization,
    Unit,
)
from app.repositories.base import BaseRepository


class OrganizationRepository(BaseRepository[Organization]):
    def __init__(self) -> None:
        super().__init__(Organization)

    def find_by_code(self, code: str) -> Organization | None:
        return self.find_one(Organization.code == code)

    def list_all(self) -> list[Organization]:
        stmt = select(Organization).order_by(Organization.code.asc())
        return list(db.session.scalars(stmt).all())

    def find_children(self, parent_id: int) -> list[Organization]:
        stmt = (
            select(Organization)
            .where(Organization.parent_id == parent_id)
            .order_by(Organization.code.asc())
        )
        return list(db.session.scalars(stmt).all())


organization_repository = OrganizationRepository()


class UnitRepository(BaseRepository[Unit]):
    def __init__(self) -> None:
        super().__init__(Unit)

    def find_by_code(self, code: str) -> Unit | None:
        return self.find_one(Unit.code == code)

    def list_all(self) -> list[Unit]:
        return list(db.session.scalars(select(Unit).order_by(Unit.code.asc())).all())


class AssetSourceRepository(BaseRepository[AssetSource]):
    def __init__(self) -> None:
        super().__init__(AssetSource)

    def find_by_code(self, code: str) -> AssetSource | None:
        return self.find_one(AssetSource.code == code)

    def list_all(self) -> list[AssetSource]:
        return list(
            db.session.scalars(
                select(AssetSource).order_by(AssetSource.code.asc())
            ).all()
        )


class LocationCodeSequenceRepository(BaseRepository[LocationCodeSequence]):
    def __init__(self) -> None:
        super().__init__(LocationCodeSequence)

    def ensure_exists(self) -> None:
        values = {"prefix": "LOC", "current_value": 0}
        dialect = db.session.get_bind().dialect.name
        if dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert

            sqlite_statement = sqlite_insert(LocationCodeSequence).values(**values)
            db.session.execute(
                sqlite_statement.on_conflict_do_nothing(index_elements=["prefix"])
            )
        elif dialect == "mysql":
            from sqlalchemy.dialects.mysql import insert as mysql_insert

            mysql_statement = mysql_insert(LocationCodeSequence).values(**values)
            db.session.execute(
                mysql_statement.on_duplicate_key_update(
                    current_value=LocationCodeSequence.current_value
                )
            )
        else:
            raise RuntimeError(f"unsupported database dialect: {dialect}")

    def find_for_update(self) -> LocationCodeSequence | None:
        statement = (
            select(LocationCodeSequence)
            .where(LocationCodeSequence.prefix == "LOC")
            .with_for_update()
        )
        return db.session.scalar(statement)


class AssetLocationRepository(BaseRepository[AssetLocation]):
    def __init__(self) -> None:
        super().__init__(AssetLocation)

    def find_by_code(self, code: str) -> AssetLocation | None:
        return self.find_one(AssetLocation.code == code)

    def find_sibling(self, parent_id: int | None, name: str) -> AssetLocation | None:
        return self.find_one(
            AssetLocation.parent_id == parent_id,
            AssetLocation.name == name,
        )

    def list_all(self) -> list[AssetLocation]:
        return list(
            db.session.scalars(
                select(AssetLocation).order_by(AssetLocation.code.asc())
            ).all()
        )


class AssetCategoryRepository(BaseRepository[AssetCategory]):
    def __init__(self) -> None:
        super().__init__(AssetCategory)

    def find_by_code(self, code: str) -> AssetCategory | None:
        return self.find_one(AssetCategory.code == code)

    def list_all(self) -> list[AssetCategory]:
        return list(
            db.session.scalars(
                select(AssetCategory).order_by(AssetCategory.code.asc())
            ).all()
        )


unit_repository = UnitRepository()
asset_source_repository = AssetSourceRepository()
location_code_sequence_repository = LocationCodeSequenceRepository()
asset_location_repository = AssetLocationRepository()
asset_category_repository = AssetCategoryRepository()

__all__ = [
    "AssetCategoryRepository",
    "AssetLocationRepository",
    "LocationCodeSequenceRepository",
    "AssetSourceRepository",
    "OrganizationRepository",
    "UnitRepository",
    "asset_category_repository",
    "asset_location_repository",
    "location_code_sequence_repository",
    "asset_source_repository",
    "organization_repository",
    "unit_repository",
]
