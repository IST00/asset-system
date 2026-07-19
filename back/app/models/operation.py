"""Shared operation-kernel persistence models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.mixins import TimestampMixin, utc_now


class OperationRequestAsset(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "operation_request_assets"
    __table_args__ = (
        UniqueConstraint(
            "operation_request_id",
            "asset_id",
            name="uq_operation_request_asset",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_request_id: Mapped[int] = mapped_column(
        ForeignKey("operation_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    asset_code_snapshot: Mapped[str] = mapped_column(String(191), nullable=False)
    asset_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_status_snapshot: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_version_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    organization_id_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    holder_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    location_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    before_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    target_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class AssetBusinessLock(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "asset_business_locks"
    __table_args__ = (
        UniqueConstraint("asset_id", name="uq_asset_business_lock_asset"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    operation_request_id: Mapped[int] = mapped_column(
        ForeignKey("operation_requests.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    operation_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    applicant_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    locked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class OperationExecutionAttempt(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "operation_execution_attempts"
    __table_args__ = (
        UniqueConstraint(
            "operation_request_id",
            "attempt_no",
            name="uq_operation_execution_attempt_no",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_request_id: Mapped[int] = mapped_column(
        ForeignKey("operation_requests.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    triggered_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    safe_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ExternalApprovalEvent(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "external_approval_events"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "external_event_id",
            name="uq_external_approval_event_provider_event",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_request_id: Mapped[int] = mapped_column(
        ForeignKey("operation_requests.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    external_event_id: Mapped[str] = mapped_column(String(191), nullable=False)
    external_instance_id: Mapped[str] = mapped_column(
        String(191), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False)
    safe_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class OperationActionIdempotency(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "operation_action_idempotencies"
    __table_args__ = (
        UniqueConstraint(
            "operation_request_id",
            "actor_id",
            "action",
            "idempotency_key",
            name="uq_operation_action_idempotency",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_request_id: Mapped[int] = mapped_column(
        ForeignKey("operation_requests.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(191), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


__all__ = [
    "AssetBusinessLock",
    "ExternalApprovalEvent",
    "OperationActionIdempotency",
    "OperationExecutionAttempt",
    "OperationRequestAsset",
]
