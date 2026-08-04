"""Approval task transfer and reminder audit events."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.mixins import TimestampMixin


class ApprovalTaskEvent(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "approval_task_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_request_id: Mapped[int] = mapped_column(
        ForeignKey("operation_requests.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    approval_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("approval_tasks.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    actor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    from_approver_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    to_approver_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)


__all__ = ["ApprovalTaskEvent"]
