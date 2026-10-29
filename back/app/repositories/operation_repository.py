"""Operation-kernel persistence queries."""

from __future__ import annotations

from sqlalchemy import delete, func, select

from app.extensions import db
from app.models import (
    AssetBusinessLock,
    ExternalApprovalEvent,
    OperationExecutionAttempt,
    OperationActionIdempotency,
    OperationRequestAsset,
)
from app.repositories.base import BaseRepository


def _lock_asset_id(row: AssetBusinessLock) -> int:
    return row.asset_id


class OperationRequestAssetRepository(BaseRepository[OperationRequestAsset]):
    def __init__(self) -> None:
        super().__init__(OperationRequestAsset)

    def find_by_request(self, request_id: int) -> list[OperationRequestAsset]:
        statement = (
            select(OperationRequestAsset)
            .where(OperationRequestAsset.operation_request_id == request_id)
            .order_by(OperationRequestAsset.asset_id.asc())
        )
        return list(db.session.scalars(statement).all())

    def delete_for_request(self, request_id: int) -> None:
        db.session.execute(
            delete(OperationRequestAsset).where(
                OperationRequestAsset.operation_request_id == request_id
            )
        )


class AssetBusinessLockRepository(BaseRepository[AssetBusinessLock]):
    def __init__(self) -> None:
        super().__init__(AssetBusinessLock)

    def acquire_rows(self, rows: list[AssetBusinessLock]) -> None:
        rows.sort(key=_lock_asset_id)
        db.session.add_all(rows)
        db.session.flush()

    def release_for_request(self, request_id: int) -> None:
        db.session.execute(
            delete(AssetBusinessLock).where(
                AssetBusinessLock.operation_request_id == request_id
            )
        )

    def find_by_assets(self, asset_ids: list[int]) -> list[AssetBusinessLock]:
        if not asset_ids:
            return []
        statement = (
            select(AssetBusinessLock)
            .where(AssetBusinessLock.asset_id.in_(asset_ids))
            .order_by(AssetBusinessLock.asset_id.asc())
        )
        return list(db.session.scalars(statement).all())

    def find_by_assets_for_update(
        self, asset_ids: list[int]
    ) -> list[AssetBusinessLock]:
        ids = sorted(set(asset_ids))
        if not ids:
            return []
        statement = (
            select(AssetBusinessLock)
            .where(AssetBusinessLock.asset_id.in_(ids))
            .order_by(AssetBusinessLock.asset_id.asc())
            .with_for_update()
        )
        return list(db.session.scalars(statement).all())


class ExecutionAttemptRepository(BaseRepository[OperationExecutionAttempt]):
    def __init__(self) -> None:
        super().__init__(OperationExecutionAttempt)

    def next_attempt_no(self, request_id: int) -> int:
        latest = db.session.scalar(
            select(func.max(OperationExecutionAttempt.attempt_no)).where(
                OperationExecutionAttempt.operation_request_id == request_id
            )
        )
        return int(latest or 0) + 1


class ExternalApprovalEventRepository(BaseRepository[ExternalApprovalEvent]):
    def __init__(self) -> None:
        super().__init__(ExternalApprovalEvent)

    def find_by_event(
        self, provider: str, external_event_id: str
    ) -> ExternalApprovalEvent | None:
        statement = select(ExternalApprovalEvent).where(
            ExternalApprovalEvent.provider == provider,
            ExternalApprovalEvent.external_event_id == external_event_id,
        )
        return db.session.scalar(statement)


class OperationActionIdempotencyRepository(BaseRepository[OperationActionIdempotency]):
    def __init__(self) -> None:
        super().__init__(OperationActionIdempotency)

    def find_by_key(
        self,
        operation_request_id: int,
        actor_id: int,
        action: str,
        idempotency_key: str,
    ) -> OperationActionIdempotency | None:
        statement = select(OperationActionIdempotency).where(
            OperationActionIdempotency.operation_request_id == operation_request_id,
            OperationActionIdempotency.actor_id == actor_id,
            OperationActionIdempotency.action == action,
            OperationActionIdempotency.idempotency_key == idempotency_key,
        )
        return db.session.scalar(statement)


operation_request_asset_repository = OperationRequestAssetRepository()
asset_business_lock_repository = AssetBusinessLockRepository()
execution_attempt_repository = ExecutionAttemptRepository()
external_approval_event_repository = ExternalApprovalEventRepository()
operation_action_idempotency_repository = OperationActionIdempotencyRepository()

__all__ = [
    "AssetBusinessLockRepository",
    "ExecutionAttemptRepository",
    "ExternalApprovalEventRepository",
    "OperationRequestAssetRepository",
    "OperationActionIdempotencyRepository",
    "asset_business_lock_repository",
    "execution_attempt_repository",
    "external_approval_event_repository",
    "operation_request_asset_repository",
    "operation_action_idempotency_repository",
]
