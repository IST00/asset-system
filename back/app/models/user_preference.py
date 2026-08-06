"""Per-user interface preferences persisted across browsers."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.mixins import TimestampMixin


class UserPreference(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "user_preferences"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    asset_list_columns: Mapped[str | None] = mapped_column(Text, nullable=True)
    asset_list_page_size: Mapped[int] = mapped_column(
        Integer, nullable=False, default=50
    )
    task_notice: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    approval_notice: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    weekly_digest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


__all__ = ["UserPreference"]
