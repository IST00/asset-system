"""Repository layer — the thin seam between services and SQLAlchemy.

A Repository owns *how to query/persist* a single aggregate. Services own
*business rules + transaction boundaries*. Keep the seam narrow: a repo
method should map to at most a few SQL statements and never raise
BusinessException.
"""

from app.repositories.base import BaseRepository, Page, QuerySpec
from app.repositories.user_repository import UserRepository, user_repository

__all__ = ["BaseRepository", "Page", "QuerySpec", "UserRepository", "user_repository"]
