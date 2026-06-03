"""Device SQLAlchemy model — one row per registered H5 device.

Populated lazily on the first `visit` event for a `device_id`. Used to
count unique users (devices), as a complement to the per-event `events`
table which counts traffic.

No DB-level UNIQUE on `device_id` by design — the frontend's localStorage
flag is the primary de-dupe, and a stray row after a cache wipe is
cheaper than handling IntegrityError on every visit.
"""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.mixins import TimestampMixin


class Device(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    ua: Mapped[str | None] = mapped_column(String(32), nullable=True)

    def __repr__(self) -> str:
        return f"<Device id={self.id} did={self.device_id!r}>"
