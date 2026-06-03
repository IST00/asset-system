"""Event SQLAlchemy model — H5 analytics events.

Backs `POST /api/keke/track` and the implicit `generate_start` emitted by
`POST /api/keke/story/generate`. Mirrors the five events the original SCF
function emitted to CLS logs (visit / generate_start / generate_success /
save_open / save_success).

Column name `source` is used instead of `from` to avoid clashing with the
Python keyword; the API layer maps `from` <-> `source`.
"""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.mixins import TimestampMixin


class Event(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_name: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    ua: Mapped[str | None] = mapped_column(String(32), nullable=True)
    keyword: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<Event id={self.id} name={self.event_name!r} did={self.device_id!r}>"
