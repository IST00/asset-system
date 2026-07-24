"""Record immutable operation facts without owning business decisions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.models import AssetLifecycleRecord, OperationLog
from app.repositories.audit_repository import (
    asset_lifecycle_repository,
    operation_log_repository,
)


def _add_asset_lifecycle(
    *,
    asset_id: int,
    operation_type: str,
    request_no: str,
    actor_id: int,
    before_data: Mapping[str, Any] | None,
    after_data: Mapping[str, Any],
) -> None:
    asset_lifecycle_repository.add(
        AssetLifecycleRecord(
            asset_id=asset_id,
            operation_type=operation_type,
            operation_no=request_no,
            operator_id=actor_id,
            before_data=dict(before_data) if before_data is not None else None,
            after_data=dict(after_data),
        )
    )


def record_asset_lifecycle(
    *,
    asset_id: int,
    operation_type: str,
    request_no: str,
    actor_id: int,
    before_data: Mapping[str, Any],
    after_data: Mapping[str, Any],
) -> None:
    _add_asset_lifecycle(
        asset_id=asset_id,
        operation_type=operation_type,
        request_no=request_no,
        actor_id=actor_id,
        before_data=before_data,
        after_data=after_data,
    )


def record_operation(
    *,
    operation_request_id: int,
    operation_type: str,
    actor_id: int,
    before_data: Mapping[str, Any] | None,
    after_data: Mapping[str, Any] | None,
) -> None:
    operation_log_repository.add(
        OperationLog(
            action=operation_type,
            resource_type="operation_request",
            resource_id=str(operation_request_id),
            operator_id=actor_id,
            before_data=dict(before_data) if before_data is not None else None,
            after_data=dict(after_data) if after_data is not None else None,
        )
    )


def record_resource_change(
    *,
    action: str,
    resource_type: str,
    resource_id: str | int,
    actor_id: int,
    before_data: Mapping[str, Any] | None,
    after_data: Mapping[str, Any] | None,
    reason: str | None = None,
) -> None:
    operation_log_repository.add(
        OperationLog(
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            operator_id=actor_id,
            before_data=dict(before_data) if before_data is not None else None,
            after_data=dict(after_data) if after_data is not None else None,
            reason=reason,
        )
    )


def record_asset_stock_in(
    *, asset_id: int, request_no: str, actor_id: int, after_data: dict[str, Any]
) -> None:
    _add_asset_lifecycle(
        asset_id=asset_id,
        operation_type="STOCK_IN",
        request_no=request_no,
        actor_id=actor_id,
        before_data=None,
        after_data=after_data,
    )
    operation_log_repository.add(
        OperationLog(
            action="STOCK_IN",
            resource_type="asset",
            resource_id=str(asset_id),
            operator_id=actor_id,
            before_data=None,
            after_data=after_data,
        )
    )


__all__ = [
    "record_asset_lifecycle",
    "record_asset_stock_in",
    "record_operation",
    "record_resource_change",
]
