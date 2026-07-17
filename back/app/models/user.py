"""User SQLAlchemy model.

Table `users` — mirrors com.soybean.quick.entity.User on the Java side.
Role is a plain string (USER / ADMIN), matching the Spring Security convention.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.mixins import TimestampMixin


class User(TimestampMixin, db.Model):  # type: ignore[misc,name-defined]
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"
