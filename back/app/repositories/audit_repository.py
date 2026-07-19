"""Audit and asset lifecycle persistence."""

from sqlalchemy import select

from app.extensions import db

from app.models import AssetLifecycleRecord, OperationLog
from app.repositories.base import BaseRepository


class AssetLifecycleRepository(BaseRepository[AssetLifecycleRecord]):
    def __init__(self) -> None:
        super().__init__(AssetLifecycleRecord)

    def find_by_asset(self, asset_id: int) -> list[AssetLifecycleRecord]:
        stmt = (
            select(AssetLifecycleRecord)
            .where(AssetLifecycleRecord.asset_id == asset_id)
            .order_by(AssetLifecycleRecord.id.asc())
        )
        return list(db.session.scalars(stmt).all())


class OperationLogRepository(BaseRepository[OperationLog]):
    def __init__(self) -> None:
        super().__init__(OperationLog)

    def list_recent(self, limit: int = 200) -> list[OperationLog]:
        stmt = select(OperationLog).order_by(OperationLog.id.desc()).limit(limit)
        return list(db.session.scalars(stmt).all())


asset_lifecycle_repository = AssetLifecycleRepository()
operation_log_repository = OperationLogRepository()

__all__ = [
    "AssetLifecycleRepository",
    "OperationLogRepository",
    "asset_lifecycle_repository",
    "operation_log_repository",
]
