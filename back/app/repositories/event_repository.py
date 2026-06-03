"""Event-specific repository — write-only for the first version.

Funnel queries (counting visits / generate_success per day, computing save
rate, etc.) will be added once we actually need a dashboard. Until then
the repo stays narrow so SQL never silently fans out into hot paths.
"""

from __future__ import annotations

from app.models import Event
from app.repositories.base import BaseRepository


class EventRepository(BaseRepository[Event]):
    """Writes Keke H5 analytics rows. Reads are deferred to a later milestone."""

    def __init__(self) -> None:
        super().__init__(Event)


event_repository = EventRepository()

__all__ = ["EventRepository", "event_repository"]
