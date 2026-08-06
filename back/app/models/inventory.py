"""Inventory task, snapshot item, photo, and scan-event persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import (
    InventoryItemStatus,
    InventoryPhotoSourceMode,
    InventoryReviewStatus,
    InventoryTaskStatus,
)
from app.extensions import db
from app.models.mixins import TimestampMixin


class InventoryTask(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "inventory_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_no: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=InventoryTaskStatus.DRAFT.value, index=True
    )
    deadline_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    photo_source_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=InventoryPhotoSourceMode.CAMERA_OR_ALBUM.value,
    )
    min_photo_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    scope_filters: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    collection_ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class InventoryTaskAdmin(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "inventory_task_admins"
    __table_args__ = (
        UniqueConstraint("task_id", "user_id", name="uq_inventory_task_admin_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )


class InventoryItem(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "inventory_items"
    __table_args__ = (
        UniqueConstraint("task_id", "asset_id", name="uq_inventory_task_asset"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    responsible_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    asset_code: Mapped[str] = mapped_column(String(191), nullable=False, index=True)
    asset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_status_snapshot: Mapped[str] = mapped_column(String(32), nullable=False)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    organization_name: Mapped[str] = mapped_column(String(128), nullable=False)
    category_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    category_name: Mapped[str] = mapped_column(String(128), nullable=False)
    holder_user_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    holder_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ledger_location_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    ledger_location_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parent_asset_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    parent_asset_code: Mapped[str | None] = mapped_column(String(191), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=InventoryItemStatus.PENDING.value,
        index=True,
    )
    physical_result: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    location_result: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    actual_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("asset_locations.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    actual_location_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    loss_reason: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    loss_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    borrowed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    submission_method: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    submitted_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_late: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=InventoryReviewStatus.NONE.value, index=True
    )
    resolution: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    admin_mark_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class InventoryPhoto(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "inventory_photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    uploaded_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    storage_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)


class InventoryScanEvent(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "inventory_scan_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scanned_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    scanned_value: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_asset_code: Mapped[str | None] = mapped_column(
        String(191), nullable=True, index=True
    )
    asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    resolution: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class InventoryResultVersion(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "inventory_result_versions"
    __table_args__ = (
        UniqueConstraint("item_id", "version_no", name="uq_inventory_result_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class InventoryReminder(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "inventory_reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipient_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sent_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    batch_no: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(
        String(32), nullable=False, default="LOCAL_FEISHU"
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="QUEUED")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


__all__ = [
    "InventoryItem",
    "InventoryPhoto",
    "InventoryReminder",
    "InventoryResultVersion",
    "InventoryScanEvent",
    "InventoryTask",
    "InventoryTaskAdmin",
]
