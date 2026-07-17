"""Operation request, stock-in, and approval persistence."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
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


class OperationRequest(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "operation_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_no: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    operation_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    applicant_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    approval_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    execution_status: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )
    flow_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    execution_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class StockInRequest(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "stock_in_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_request_id: Mapped[int] = mapped_column(
        ForeignKey("operation_requests.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class StockInItem(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "stock_in_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_in_request_id: Mapped[int] = mapped_column(
        ForeignKey("stock_in_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_code: Mapped[str] = mapped_column(
        String(191), nullable=False, unique=True, index=True
    )
    asset_name: Mapped[str] = mapped_column(String(255), nullable=False)
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
        String(191), nullable=True, index=True
    )
    serial_reservation_key: Mapped[str | None] = mapped_column(
        String(191), nullable=True, unique=True, index=True
    )
    receipt_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class ApprovalStep(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "approval_steps"
    __table_args__ = (
        UniqueConstraint(
            "operation_request_id", "level_no", name="uq_approval_step_level"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_request_id: Mapped[int] = mapped_column(
        ForeignKey("operation_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    level_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)


class ApprovalTask(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "approval_tasks"
    __table_args__ = (
        UniqueConstraint(
            "approval_step_id", "approver_id", name="uq_approval_task_approver"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    approval_step_id: Mapped[int] = mapped_column(
        ForeignKey("approval_steps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    approver_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    opinion: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ApprovalRecord(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "approval_records"
    __table_args__ = (
        UniqueConstraint("approval_step_id", name="uq_approval_record_step"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_request_id: Mapped[int] = mapped_column(
        ForeignKey("operation_requests.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    approval_step_id: Mapped[int] = mapped_column(
        ForeignKey("approval_steps.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    approval_task_id: Mapped[int] = mapped_column(
        ForeignKey("approval_tasks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    actor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    opinion: Mapped[str | None] = mapped_column(Text, nullable=True)


__all__ = [
    "ApprovalRecord",
    "ApprovalStep",
    "ApprovalTask",
    "OperationRequest",
    "StockInItem",
    "StockInRequest",
]
