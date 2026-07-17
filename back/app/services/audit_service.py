"""Record immutable operation facts without owning business decisions."""

from __future__ import annotations

from typing import Any

from app.models import AssetLifecycleRecord, OperationLog
from app.repositories.audit_repository import (
    asset_lifecycle_repository,
    operation_log_repository,
)


def record_asset_stock_in(
    *, asset_id: int, request_no: str, actor_id: int, after_data: dict[str, Any]
) -> None:
    asset_lifecycle_repository.add(
        AssetLifecycleRecord(
            asset_id=asset_id,
            operation_type="STOCK_IN",
            operation_no=request_no,
            operator_id=actor_id,
            before_data=None,
            after_data=after_data,
        )
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


__all__ = ["record_asset_stock_in"]
