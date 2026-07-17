"""Formal asset and asset-code persistence."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.mixins import TimestampMixin


class AssetCodeSequence(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "asset_code_sequences"
    __table_args__ = (
        UniqueConstraint(
            "top_organization_id", "category_id", name="uq_asset_code_sequence_scope"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    top_organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("asset_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    current_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AssetCodeReservation(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "asset_code_reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_request_id: Mapped[int] = mapped_column(
        ForeignKey("operation_requests.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    stock_in_item_id: Mapped[int] = mapped_column(
        ForeignKey("stock_in_items.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    asset_code: Mapped[str] = mapped_column(
        String(191), nullable=False, unique=True, index=True
    )
    sequence_value: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), nullable=True, unique=True
    )


class Asset(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_code: Mapped[str] = mapped_column(
        String(191), nullable=False, unique=True, index=True
    )
    asset_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("asset_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    unit_id: Mapped[int] = mapped_column(
        ForeignKey("units.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    original_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    zero_amount_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    manager_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("asset_sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    location_id: Mapped[int] = mapped_column(
        ForeignKey("asset_locations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    specification_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(191), nullable=True)
    normalized_serial: Mapped[str | None] = mapped_column(
        String(191), nullable=True, unique=True, index=True
    )
    receipt_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_from_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("operation_requests.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


__all__ = ["Asset", "AssetCodeReservation", "AssetCodeSequence"]
