"""Reusable declarative mixins for SQLAlchemy models.

Keep these tiny and side-effect free. A model opts in by listing the mixin
before `db.Model` in the MRO, e.g.

    class User(TimestampMixin, db.Model):
        ...

Mixins must not import Flask/current_app — they run at class definition time
and need to stay usable in offline migrations.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column


def utc_now() -> datetime:
    """Single source of 'now' for audit columns. UTC, tz-aware."""
    return datetime.now(tz=timezone.utc)


class TimestampMixin:
    """Adds created_at / updated_at audit columns.

    onupdate fires on SQLAlchemy-managed UPDATE statements. Bulk updates
    via Core `update()` bypass it; use Session-level flush in services.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class SoftDeleteMixin:
    """Adds a boolean `deleted` column.

    Repositories/services are responsible for filtering `deleted=False` on
    queries; we deliberately avoid SQLAlchemy's session events so that
    admin/backfill jobs can still see soft-deleted rows.
    """

    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


__all__ = ["TimestampMixin", "SoftDeleteMixin", "utc_now"]
