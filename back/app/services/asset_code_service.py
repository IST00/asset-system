"""Concurrency-safe asset-code allocation and reservation state."""

from __future__ import annotations

from dataclasses import dataclass

from app.enums import AssetCodeStatus
from app.extensions import db
from app.models import (
    AssetCategory,
    AssetCodeReservation,
    Organization,
)
from app.repositories.asset_repository import (
    asset_code_reservation_repository,
    asset_code_sequence_repository,
)


@dataclass(frozen=True)
class AllocatedCode:
    asset_code: str
    sequence_value: int


def allocate(top_organization: Organization, category: AssetCategory) -> AllocatedCode:
    asset_code_sequence_repository.ensure_exists(top_organization.id, category.id)
    sequence = asset_code_sequence_repository.find_for_update(
        top_organization.id, category.id
    )
    if sequence is None:
        raise RuntimeError("asset code sequence was not initialized")
    sequence.current_value += 1
    value = sequence.current_value
    suffix = str(value).zfill(4)
    return AllocatedCode(
        asset_code=f"{top_organization.code}-{category.code}-{suffix}",
        sequence_value=value,
    )


def reserve(
    operation_request_id: int, stock_in_item_id: int, allocated: AllocatedCode
) -> AssetCodeReservation:
    reservation = AssetCodeReservation(
        operation_request_id=operation_request_id,
        stock_in_item_id=stock_in_item_id,
        asset_code=allocated.asset_code,
        sequence_value=allocated.sequence_value,
        status=AssetCodeStatus.PENDING_STOCK_IN.value,
    )
    asset_code_reservation_repository.add(reservation)
    return reservation


def void_for_request(operation_request_id: int) -> None:
    for reservation in asset_code_reservation_repository.find_by_request(
        operation_request_id
    ):
        if reservation.status == AssetCodeStatus.PENDING_STOCK_IN.value:
            reservation.status = AssetCodeStatus.VOID.value
    db.session.flush()


def activate(reservation_id: int, asset_id: int) -> None:
    reservation = asset_code_reservation_repository.get(reservation_id)
    if reservation is None:
        raise RuntimeError("asset code reservation not found")
    reservation.status = AssetCodeStatus.ACTIVE.value
    reservation.asset_id = asset_id
    db.session.flush()


__all__ = ["AllocatedCode", "activate", "allocate", "reserve", "void_for_request"]
