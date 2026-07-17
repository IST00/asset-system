"""System operation audit and per-asset lifecycle records."""

from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.mixins import TimestampMixin


class AssetLifecycleRecord(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "asset_lifecycle_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    operation_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    operation_no: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    operator_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    before_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class OperationLog(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "operation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_id: Mapped[str] = mapped_column(String(191), nullable=False, index=True)
    operator_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    before_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


__all__ = ["AssetLifecycleRecord", "OperationLog"]
