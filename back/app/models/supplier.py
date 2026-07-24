"""Standalone supplier persistence."""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import RecordStatus
from app.extensions import db
from app.models.mixins import TimestampMixin


class SupplierCodeSequence(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "supplier_code_sequences"

    prefix: Mapped[str] = mapped_column(String(16), primary_key=True)
    current_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Supplier(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    unified_social_credit_code: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    contact_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    remark: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=RecordStatus.ENABLED.value, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


__all__ = ["Supplier", "SupplierCodeSequence"]
