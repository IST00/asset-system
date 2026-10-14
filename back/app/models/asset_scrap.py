"""Structured disposal records for scrapped assets."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.mixins import TimestampMixin


class AssetScrapRecord(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "asset_scrap_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    scrap_no: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scrap_date: Mapped[date] = mapped_column(Date, nullable=False)
    scrap_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    disposition: Mapped[str | None] = mapped_column(String(255), nullable=True)
    disposition_remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    disposal_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    confirmed_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


__all__ = ["AssetScrapRecord"]
