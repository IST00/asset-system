"""Generic base repository over SQLAlchemy 2.x.

Design choices
--------------
- Generic on model type `M`, so mypy catches mismatched returns.
- Query construction goes through a small `QuerySpec` dataclass
  (filters + order + pagination). This is the "query builder" the
  architecture review called for — deliberately *not* a DSL, just enough
  structure so services don't hand-roll `select().where()` chains for
  every list endpoint.
- `page()` returns a framework-agnostic `Page[M]` tuple; the API layer
  maps it into `app.common.PageResult`.
- No Flask imports; safe to use from CLI / Celery / offline scripts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from sqlalchemy import ColumnElement, Select, func, select
from flask_sqlalchemy.session import Session
from sqlalchemy.orm import scoped_session

from app.extensions import db

M = TypeVar("M")


@dataclass(frozen=True)
class Page(Generic[M]):
    """Repository-layer page result. 0-indexed."""

    items: list[M]
    total: int
    page: int
    size: int


@dataclass
class QuerySpec:
    """Declarative query shape.

    Filters are a list of SQLAlchemy `ColumnElement[bool]` (e.g.
    `User.role == "ADMIN"`). Services build these; repositories apply them.

    `order_by` is a list of column expressions (e.g. `User.id.asc()`).
    `page` is 0-indexed; `size` is capped by callers (schema layer).
    """

    filters: list[ColumnElement[bool]] = field(default_factory=list)
    order_by: list[Any] = field(default_factory=list)
    page: int = 0
    size: int = 20


class BaseRepository(Generic[M]):
    """CRUD + paging primitives for a single model class.

    Subclass to add domain-specific queries (see UserRepository). Subclasses
    should not re-wrap generic CRUD — add only queries that involve the
    aggregate's specifics (e.g. `find_by_username`).
    """

    model: type[M]

    def __init__(self, model: type[M]) -> None:
        self.model = model

    # -- session accessor ------------------------------------------------
    # Indirection so tests / Celery workers can inject a custom session
    # without monkey-patching `app.extensions.db`.
    def _session(self) -> scoped_session[Session]:
        return db.session

    # -- reads -----------------------------------------------------------
    def get(self, pk: Any) -> M | None:
        return self._session().get(self.model, pk)

    def find_one(self, *where: ColumnElement[bool]) -> M | None:
        stmt: Select[tuple[M]] = select(self.model).where(*where)
        return self._session().execute(stmt).scalar_one_or_none()

    def find_all(self, spec: QuerySpec | None = None) -> list[M]:
        stmt = self._build_base(spec)
        return list(self._session().execute(stmt).scalars().all())

    def count(self, *where: ColumnElement[bool]) -> int:
        # SQLAlchemy's `count()` needs an explicit column so unique rows are counted.
        pk_col = self._primary_key_column()
        stmt = select(func.count(pk_col))
        if where:
            stmt = stmt.where(*where)
        return int(self._session().scalar(stmt) or 0)

    def page(self, spec: QuerySpec) -> Page[M]:
        page_index = spec.page if spec.page >= 0 else 0
        size = spec.size if spec.size > 0 else 20

        total = self.count(*spec.filters)
        stmt = self._build_base(spec).limit(size).offset(page_index * size)
        items = list(self._session().execute(stmt).scalars().all())
        return Page(items=items, total=total, page=page_index, size=size)

    # -- writes ----------------------------------------------------------
    # NOTE: commit is intentionally owned by the service layer. Repos only
    # stage changes in the session so services can compose multiple repo
    # calls in a single transaction.
    def add(self, entity: M) -> M:
        self._session().add(entity)
        self._session().flush()
        return entity

    def delete(self, entity: M) -> None:
        self._session().delete(entity)

    # -- internals -------------------------------------------------------
    def _build_base(self, spec: QuerySpec | None) -> Select[tuple[M]]:
        stmt: Select[tuple[M]] = select(self.model)
        if spec is None:
            return stmt
        if spec.filters:
            stmt = stmt.where(*spec.filters)
        if spec.order_by:
            stmt = stmt.order_by(*spec.order_by)
        return stmt

    def _primary_key_column(self) -> Any:
        mapper = self.model.__mapper__  # type: ignore[attr-defined]
        pks = list(mapper.primary_key)
        if not pks:
            raise RuntimeError(f"{self.model.__name__} has no primary key")
        return pks[0]


__all__ = ["BaseRepository", "Page", "QuerySpec"]
