"""Asset usage and return persistence models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import FulfillmentStatus
from app.extensions import db
from app.models.mixins import TimestampMixin


class AssetUsageRequest(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "asset_usage_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_request_id: Mapped[int] = mapped_column(
        ForeignKey("operation_requests.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    target_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    target_public_object_id: Mapped[int | None] = mapped_column(
        ForeignKey("public_usage_objects.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    usage_department_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    target_region_id: Mapped[int | None] = mapped_column(
        ForeignKey("asset_locations.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    target_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("asset_locations.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    requested_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("asset_categories.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    requested_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="USE", server_default="USE", index=True
    )
    expected_return_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    target_user_snapshot: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    usage_department_snapshot: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    target_public_object_snapshot: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    target_location_snapshot: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    requested_category_snapshot: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    fulfillment_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=FulfillmentStatus.COMPLETED.value,
        server_default=FulfillmentStatus.COMPLETED.value,
        index=True,
    )
    issued_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    issued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    issue_remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    signed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    signed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sign_remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    return_requested_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    return_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    return_request_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class AssetReturnRequest(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "asset_return_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_request_id: Mapped[int] = mapped_column(
        ForeignKey("operation_requests.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    return_company_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    return_usage_company_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    return_region_id: Mapped[int | None] = mapped_column(
        ForeignKey("asset_locations.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    return_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("asset_locations.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    handed_over_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    handed_over_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    handover_remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    handed_over_by_snapshot: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    confirmed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    return_location_snapshot: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    confirmed_by_snapshot: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )


class AssetReturnItem(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "asset_return_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_request_asset_id: Mapped[int] = mapped_column(
        ForeignKey("operation_request_assets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    condition: Mapped[str | None] = mapped_column(String(16), nullable=True)
    condition_description: Mapped[str | None] = mapped_column(Text, nullable=True)


__all__ = ["AssetReturnItem", "AssetReturnRequest", "AssetUsageRequest"]
