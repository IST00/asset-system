"""Current asset business-lock acquisition and release."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.common import BusinessException
from app.extensions import db
from app.models import Asset, AssetBusinessLock, OperationRequest
from app.repositories import asset_business_lock_repository
from app.repositories.workflow_repository import operation_request_repository


def _is_asset_lock_conflict(error: IntegrityError) -> bool:
    message = str(error.orig).lower()
    return (
        "uq_asset_business_lock_asset" in message
        or "asset_business_locks.asset_id" in message
    )


def acquire(operation: OperationRequest, assets: list[Asset]) -> None:
    asset_codes = {asset.id: asset.asset_code for asset in assets}
    rows = [
        AssetBusinessLock(
            asset_id=asset.id,
            operation_request_id=operation.id,
            operation_type=operation.operation_type,
            applicant_id=operation.applicant_id,
        )
        for asset in sorted(assets, key=lambda item: item.id)
    ]
    try:
        asset_business_lock_repository.acquire_rows(rows)
    except IntegrityError as error:
        if not _is_asset_lock_conflict(error):
            raise
        db.session.rollback()
        conflicts = asset_business_lock_repository.find_by_assets(sorted(asset_codes))
        if conflicts:
            conflict = conflicts[0]
            existing = operation_request_repository.get(conflict.operation_request_id)
            request_no = existing.request_no if existing is not None else "未知申请"
            asset_code = asset_codes.get(conflict.asset_id, "未知资产")
            raise BusinessException(
                f"资产 {asset_code} 正在处理申请 {request_no}"
            ) from None
        raise BusinessException("资产正在处理其它申请，请稍后重试") from None


def release(operation_request_id: int) -> None:
    asset_business_lock_repository.release_for_request(operation_request_id)


__all__ = ["acquire", "release"]
