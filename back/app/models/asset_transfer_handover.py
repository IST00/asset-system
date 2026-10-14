"""Two-party asset handover records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.mixins import TimestampMixin


class AssetTransferHandover(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "asset_transfer_handovers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    handover_no: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    initiated_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    outgoing_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    receiver_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
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
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    items: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="PENDING_OUTGOING", index=True
    )
    outgoing_confirmed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    outgoing_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    received_confirmed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    received_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejected_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


__all__ = ["AssetTransferHandover"]
