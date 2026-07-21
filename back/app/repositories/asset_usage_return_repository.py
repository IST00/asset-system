"""Persistence queries for asset usage and return requests."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select

from app.extensions import db
from app.models.asset_usage_return import (
    AssetReturnItem,
    AssetReturnRequest,
    AssetUsageRequest,
)
from app.models.operation import OperationRequestAsset
from app.repositories.base import BaseRepository


class AssetUsageRequestRepository(BaseRepository[AssetUsageRequest]):
    def __init__(self) -> None:
        super().__init__(AssetUsageRequest)

    def find_by_operation(self, operation_request_id: int) -> AssetUsageRequest | None:
        statement = select(AssetUsageRequest).where(
            AssetUsageRequest.operation_request_id == operation_request_id
        )
        return db.session.scalar(statement)


class AssetReturnRequestRepository(BaseRepository[AssetReturnRequest]):
    def __init__(self) -> None:
        super().__init__(AssetReturnRequest)

    def find_by_operation(self, operation_request_id: int) -> AssetReturnRequest | None:
        statement = select(AssetReturnRequest).where(
            AssetReturnRequest.operation_request_id == operation_request_id
        )
        return db.session.scalar(statement)


class AssetReturnItemRepository(BaseRepository[AssetReturnItem]):
    def __init__(self) -> None:
        super().__init__(AssetReturnItem)

    def find_by_operation(self, operation_request_id: int) -> list[AssetReturnItem]:
        statement = (
            select(AssetReturnItem)
            .join(
                OperationRequestAsset,
                AssetReturnItem.operation_request_asset_id == OperationRequestAsset.id,
            )
            .where(OperationRequestAsset.operation_request_id == operation_request_id)
            .order_by(AssetReturnItem.operation_request_asset_id.asc())
        )
        return list(db.session.scalars(statement).all())

    def find_by_request_asset_ids(self, ids: Sequence[int]) -> list[AssetReturnItem]:
        request_asset_ids = sorted(set(ids))
        if not request_asset_ids:
            return []
        statement = (
            select(AssetReturnItem)
            .where(AssetReturnItem.operation_request_asset_id.in_(request_asset_ids))
            .order_by(AssetReturnItem.operation_request_asset_id.asc())
        )
        return list(db.session.scalars(statement).all())


asset_usage_request_repository = AssetUsageRequestRepository()
asset_return_request_repository = AssetReturnRequestRepository()
asset_return_item_repository = AssetReturnItemRepository()


__all__ = [
    "AssetReturnItemRepository",
    "AssetReturnRequestRepository",
    "AssetUsageRequestRepository",
    "asset_return_item_repository",
    "asset_return_request_repository",
    "asset_usage_request_repository",
]
