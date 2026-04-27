"""User-specific repository."""

from __future__ import annotations

from app.models import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Queries bound to the User aggregate."""

    def __init__(self) -> None:
        super().__init__(User)

    def find_by_username(self, username: str) -> User | None:
        return self.find_one(User.username == username)

    def username_exists(self, username: str) -> bool:
        return self.count(User.username == username) > 0


# Module-level singleton. Safe because the repo is stateless —
# it reads db.session lazily on every call.
user_repository = UserRepository()

__all__ = ["UserRepository", "user_repository"]
