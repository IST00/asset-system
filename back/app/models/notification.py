"""Persistent in-product notifications."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.mixins import TimestampMixin


class UserNotification(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "user_notifications"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "deduplication_key", name="uq_user_notification_dedup"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notification_type: Mapped[str] = mapped_column(
        String(48), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    related_operation_id: Mapped[int | None] = mapped_column(
        ForeignKey("operation_requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    related_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    deduplication_key: Mapped[str] = mapped_column(String(191), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
