"""Versioned internal approval-flow persistence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import FlowStatus
from app.extensions import db
from app.models.mixins import TimestampMixin


class ApprovalFlowDefinition(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "approval_flow_definitions"
    __table_args__ = (
        UniqueConstraint(
            "operation_type", name="uq_approval_flow_definition_operation_type"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=FlowStatus.DRAFT.value, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ApprovalFlowVersion(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "approval_flow_versions"
    __table_args__ = (
        UniqueConstraint(
            "flow_definition_id",
            "version_no",
            name="uq_approval_flow_version_number",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    flow_definition_id: Mapped[int] = mapped_column(
        ForeignKey("approval_flow_definitions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=FlowStatus.DRAFT.value, index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    layers: Mapped[list[ApprovalFlowLayer]] = relationship(
        order_by="ApprovalFlowLayer.level_no",
        cascade="all, delete-orphan",
    )


class ApprovalFlowLayer(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "approval_flow_layers"
    __table_args__ = (
        UniqueConstraint(
            "flow_version_id", "level_no", name="uq_approval_flow_layer_level"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    flow_version_id: Mapped[int] = mapped_column(
        ForeignKey("approval_flow_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    level_no: Mapped[int] = mapped_column(Integer, nullable=False)
    sign_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    allow_self_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    assignee_rules: Mapped[list[ApprovalFlowAssigneeRule]] = relationship(
        order_by="ApprovalFlowAssigneeRule.id",
        cascade="all, delete-orphan",
    )


class ApprovalFlowAssigneeRule(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "approval_flow_assignee_rules"
    __table_args__ = (
        UniqueConstraint(
            "layer_id",
            "assignee_type",
            "assignee_id",
            name="uq_approval_flow_assignee_rule",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    layer_id: Mapped[int] = mapped_column(
        ForeignKey("approval_flow_layers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    assignee_type: Mapped[str] = mapped_column(String(32), nullable=False)
    assignee_id: Mapped[int] = mapped_column(Integer, nullable=False)


__all__ = [
    "ApprovalFlowAssigneeRule",
    "ApprovalFlowDefinition",
    "ApprovalFlowLayer",
    "ApprovalFlowVersion",
]
