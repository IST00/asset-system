"""Persistence queries for asset transfer and scrap approval requests."""

from __future__ import annotations

from sqlalchemy import select

from app.extensions import db
from app.models.asset_lifecycle_request import (
    AssetScrapRequest,
    AssetScrapRequestItem,
    AssetTransferRequest,
)
from app.models.operation import OperationRequestAsset
from app.repositories.base import BaseRepository


class AssetTransferRequestRepository(BaseRepository[AssetTransferRequest]):
    def __init__(self) -> None:
        super().__init__(AssetTransferRequest)

    def find_by_operation(
        self, operation_request_id: int
    ) -> AssetTransferRequest | None:
        statement = select(AssetTransferRequest).where(
            AssetTransferRequest.operation_request_id == operation_request_id
        )
        return db.session.scalar(statement)


class AssetScrapRequestRepository(BaseRepository[AssetScrapRequest]):
    def __init__(self) -> None:
        super().__init__(AssetScrapRequest)

    def find_by_operation(self, operation_request_id: int) -> AssetScrapRequest | None:
        statement = select(AssetScrapRequest).where(
            AssetScrapRequest.operation_request_id == operation_request_id
        )
        return db.session.scalar(statement)


class AssetScrapRequestItemRepository(BaseRepository[AssetScrapRequestItem]):
    def __init__(self) -> None:
        super().__init__(AssetScrapRequestItem)

    def find_by_operation(
        self, operation_request_id: int
    ) -> list[AssetScrapRequestItem]:
        statement = (
            select(AssetScrapRequestItem)
            .join(
                OperationRequestAsset,
                OperationRequestAsset.id
                == AssetScrapRequestItem.operation_request_asset_id,
            )
            .where(OperationRequestAsset.operation_request_id == operation_request_id)
            .order_by(OperationRequestAsset.asset_id.asc())
        )
        return list(db.session.scalars(statement).all())


asset_transfer_request_repository = AssetTransferRequestRepository()
asset_scrap_request_repository = AssetScrapRequestRepository()
asset_scrap_request_item_repository = AssetScrapRequestItemRepository()


__all__ = [
    "AssetScrapRequestItemRepository",
    "AssetScrapRequestRepository",
    "AssetTransferRequestRepository",
    "asset_scrap_request_item_repository",
    "asset_scrap_request_repository",
    "asset_transfer_request_repository",
]
