"""Asset information change request details backed by the operation kernel."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.mixins import TimestampMixin


class AssetInformationChangeRequest(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "asset_information_change_requests"
    __table_args__ = (
        UniqueConstraint(
            "operation_request_id",
            name="uq_asset_information_change_operation",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_request_id: Mapped[int] = mapped_column(
        ForeignKey("operation_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    change_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)


__all__ = ["AssetInformationChangeRequest"]
