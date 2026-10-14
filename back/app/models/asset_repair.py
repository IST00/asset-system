"""Structured repair records for asset maintenance history."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.mixins import TimestampMixin


class AssetRepairRecord(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "asset_repair_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    repair_no: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    before_status: Mapped[str] = mapped_column(String(32), nullable=False)
    fault_description: Mapped[str] = mapped_column(Text, nullable=False)
    repair_supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    repair_supplier_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    repair_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    repair_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


__all__ = ["AssetRepairRecord"]
