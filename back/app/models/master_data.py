"""Master-data models shared by asset workflows."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import RecordStatus
from app.extensions import db
from app.models.mixins import TimestampMixin


class Organization(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=RecordStatus.ENABLED.value, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Unit(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=RecordStatus.ENABLED.value, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class AssetSource(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "asset_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=RecordStatus.ENABLED.value, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class LocationCodeSequence(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "location_code_sequences"

    prefix: Mapped[str] = mapped_column(String(16), primary_key=True)
    current_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AssetLocation(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "asset_locations"
    __table_args__ = (
        UniqueConstraint("parent_id", "name", name="uq_asset_locations_sibling_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("asset_locations.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=RecordStatus.ENABLED.value, index=True
    )
    is_selectable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class AssetCategory(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "asset_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("asset_categories.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    service_life_months: Mapped[int] = mapped_column(Integer, nullable=False)
    default_unit_id: Mapped[int] = mapped_column(
        ForeignKey("units.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=RecordStatus.ENABLED.value, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


__all__ = [
    "AssetCategory",
    "AssetLocation",
    "AssetSource",
    "LocationCodeSequence",
    "Organization",
    "Unit",
]
