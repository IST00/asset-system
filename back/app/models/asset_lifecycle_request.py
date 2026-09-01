"""Asset transfer and scrap approval request persistence models."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
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


class AssetTransferRequest(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "asset_transfer_requests"
    __table_args__ = (
        UniqueConstraint(
            "operation_request_id",
            name="uq_asset_transfer_request_operation",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_request_id: Mapped[int] = mapped_column(
        ForeignKey("operation_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True
    )
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("asset_locations.id", ondelete="RESTRICT"), nullable=True
    )
    manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    holder_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    public_object_id: Mapped[int | None] = mapped_column(
        ForeignKey("public_usage_objects.id", ondelete="RESTRICT"), nullable=True
    )
    target_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    reason: Mapped[str] = mapped_column(Text, nullable=False)


class AssetScrapRequest(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "asset_scrap_requests"
    __table_args__ = (
        UniqueConstraint(
            "operation_request_id",
            name="uq_asset_scrap_request_operation",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_request_id: Mapped[int] = mapped_column(
        ForeignKey("operation_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    scrap_date: Mapped[date] = mapped_column(Date, nullable=False)


class AssetScrapRequestItem(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "asset_scrap_request_items"
    __table_args__ = (
        UniqueConstraint(
            "operation_request_asset_id",
            name="uq_asset_scrap_request_item_request_asset",
        ),
        CheckConstraint(
            "disposition IN ('SCRAP', 'DETACH')",
            name="ck_asset_scrap_item_disposition",
        ),
        CheckConstraint(
            "(disposition = 'SCRAP' AND scrap_amount IS NOT NULL "
            "AND scrap_amount >= 0) OR "
            "(disposition = 'DETACH' AND scrap_amount IS NULL)",
            name="ck_asset_scrap_item_amount",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_request_asset_id: Mapped[int] = mapped_column(
        ForeignKey("operation_request_assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    disposition: Mapped[str] = mapped_column(String(16), nullable=False)
    scrap_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)


__all__ = ["AssetScrapRequest", "AssetScrapRequestItem", "AssetTransferRequest"]
