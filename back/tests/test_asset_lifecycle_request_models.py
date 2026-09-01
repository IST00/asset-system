"""Persistence contracts for asset transfer and scrap requests."""

from sqlalchemy import UniqueConstraint

from app.enums import OperationType
from app.models import (
    AssetScrapRequest,
    AssetScrapRequestItem,
    AssetTransferRequest,
)
from app.repositories import (
    asset_scrap_request_item_repository,
    asset_scrap_request_repository,
    asset_transfer_request_repository,
)


def _unique_columns(model: type) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def test_lifecycle_request_model_contracts() -> None:
    assert OperationType.SCRAP.value == "SCRAP"
    assert ("operation_request_id",) in _unique_columns(AssetTransferRequest)
    assert ("operation_request_id",) in _unique_columns(AssetScrapRequest)
    assert ("operation_request_asset_id",) in _unique_columns(AssetScrapRequestItem)
    assert AssetScrapRequest.__table__.c.scrap_date.nullable is False
    assert AssetScrapRequestItem.__table__.c.disposition.nullable is False
    assert AssetScrapRequestItem.__table__.c.scrap_amount.nullable is True


def test_lifecycle_request_repositories_are_registered() -> None:
    assert asset_transfer_request_repository.model is AssetTransferRequest
    assert asset_scrap_request_repository.model is AssetScrapRequest
    assert asset_scrap_request_item_repository.model is AssetScrapRequestItem
