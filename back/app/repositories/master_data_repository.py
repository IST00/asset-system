"""Persistence queries for organization and asset master data."""

from __future__ import annotations

from sqlalchemy import select

from app.extensions import db
from app.models import AssetCategory, AssetLocation, AssetSource, Organization, Unit
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
asset_location_repository = AssetLocationRepository()
asset_category_repository = AssetCategoryRepository()

__all__ = [
    "AssetCategoryRepository",
    "AssetLocationRepository",
    "AssetSourceRepository",
    "OrganizationRepository",
    "UnitRepository",
    "asset_category_repository",
    "asset_location_repository",
    "asset_source_repository",
    "organization_repository",
    "unit_repository",
]
