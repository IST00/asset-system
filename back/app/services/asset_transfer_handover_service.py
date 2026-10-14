"""Two-party confirmation workflow for direct asset transfers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.common import BusinessException, ResultCode
from app.enums import AssetStatus
from app.extensions import db
from app.models import Asset, AssetTransferHandover, User
from app.models.mixins import utc_now
from app.repositories import asset_repository
from app.services import (
    asset_access_service,
    audit_service,
    master_data_service,
    organization_service,
    permission_service,
)

_MANAGE_PERMISSION = "asset:usage:manage"


def _user(user_id: int) -> User:
    user = db.session.get(User, user_id)
    if user is None or not user.enabled:
        raise BusinessException(
            "用户不存在或已停用", result_code=ResultCode.BAD_REQUEST
        )
    return user


def _user_summary(user_id: int | None) -> dict[str, Any] | None:
    if user_id is None:
        return None
    user = _user(user_id)
    return {"id": user.id, "name": user.nickname or user.username}


def _serialize(row: AssetTransferHandover) -> dict[str, Any]:
    return {
        "id": row.id,
        "handover_no": row.handover_no,
        "initiated_by": row.initiated_by,
        "initiated_by_user": _user_summary(row.initiated_by),
        "outgoing_user_id": row.outgoing_user_id,
        "outgoing_user": _user_summary(row.outgoing_user_id),
        "receiver_user_id": row.receiver_user_id,
        "receiver_user": _user_summary(row.receiver_user_id),
        "organization_id": row.organization_id,
        "location_id": row.location_id,
        "manager_id": row.manager_id,
        "manager_user": _user_summary(row.manager_id),
        "reason": row.reason,
        "items": row.items,
        "status": row.status,
        "outgoing_confirmed_by": row.outgoing_confirmed_by,
        "outgoing_confirmed_at": row.outgoing_confirmed_at.isoformat()
        if row.outgoing_confirmed_at
        else None,
        "received_confirmed_by": row.received_confirmed_by,
        "received_confirmed_at": row.received_confirmed_at.isoformat()
        if row.received_confirmed_at
        else None,
        "rejected_by": row.rejected_by,
        "rejected_at": row.rejected_at.isoformat() if row.rejected_at else None,
        "reject_reason": row.reject_reason,
        "version": row.version,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _load_assets(items: list[dict[str, Any]], actor_id: int) -> list[Asset]:
    ids = [int(item["asset_id"]) for item in items]
    if len(set(ids)) != len(ids):
        raise BusinessException("资产不能重复选择", result_code=ResultCode.BAD_REQUEST)
    assets = asset_repository.find_many_accessible_for_update(
        ids, asset_access_service.access_filter(actor_id)
    )
    if len(assets) != len(ids):
        raise BusinessException(
            "资产不存在或无权操作", result_code=ResultCode.NOT_FOUND
        )
    by_id = {asset.id: asset for asset in assets}
    for item in items:
        asset = by_id[int(item["asset_id"])]
        if asset.version != int(item["version"]):
            raise BusinessException(f"资产 {asset.asset_code} 已被修改，请刷新后重试")
        if asset.status not in {AssetStatus.IDLE.value, AssetStatus.IN_USE.value}:
            raise BusinessException(f"资产 {asset.asset_code} 当前状态不允许交接")
    return [by_id[asset_id] for asset_id in ids]


def create(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, _MANAGE_PERMISSION)
    receiver = _user(payload["receiver_user_id"])
    if payload.get("outgoing_user_id") is not None:
        _user(payload["outgoing_user_id"])
    if payload.get("organization_id") is not None:
        organization_service.require_enabled(payload["organization_id"])
        permission_service.require_organization_scope(
            actor_id, payload["organization_id"]
        )
    if payload.get("location_id") is not None:
        master_data_service.require_selectable_location(payload["location_id"])
    if payload.get("manager_id") is not None:
        _user(payload["manager_id"])
    assets = _load_assets(payload["items"], actor_id)
    snapshots = []
    for asset in assets:
        snapshots.append(
            {
                "asset_id": asset.id,
                "asset_code": asset.asset_code,
                "asset_name": asset.asset_name,
                "version": asset.version,
            }
        )
    row = AssetTransferHandover(
        handover_no=f"JH{datetime.now(timezone.utc):%Y%m%d}{uuid4().hex[:12].upper()}",
        initiated_by=actor_id,
        outgoing_user_id=payload.get("outgoing_user_id"),
        receiver_user_id=receiver.id,
        organization_id=payload.get("organization_id"),
        location_id=payload.get("location_id"),
        manager_id=payload.get("manager_id"),
        reason=payload["reason"].strip(),
        items=snapshots,
    )
    db.session.add(row)
    db.session.flush()
    audit_service.record_resource_change(
        action="ASSET_TRANSFER_HANDOVER_CREATED",
        resource_type="asset_transfer_handover",
        resource_id=row.id,
        actor_id=actor_id,
        before_data=None,
        after_data=_serialize(row),
        reason=row.reason,
    )
    db.session.commit()
    return _serialize(row)


def page(actor_id: int, *, received: bool) -> list[dict[str, Any]]:
    if received:
        statement = select(AssetTransferHandover).where(
            AssetTransferHandover.receiver_user_id == actor_id,
            AssetTransferHandover.status == "PENDING_RECEIPT",
        )
    else:
        permission_service.require_permission(actor_id, _MANAGE_PERMISSION)
        statement = select(AssetTransferHandover).where(
            AssetTransferHandover.status.in_(("PENDING_OUTGOING", "PENDING_RECEIPT"))
        )
    rows = db.session.scalars(
        statement.order_by(
            AssetTransferHandover.created_at.asc(), AssetTransferHandover.id.asc()
        )
    ).all()
    return [_serialize(row) for row in rows]


def _get(row_id: int) -> AssetTransferHandover:
    row = db.session.get(AssetTransferHandover, row_id)
    if row is None:
        raise BusinessException("交接单不存在", result_code=ResultCode.NOT_FOUND)
    return row


def confirm_outgoing(
    row_id: int, actor_id: int, remark: str | None = None
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, _MANAGE_PERMISSION)
    row = _get(row_id)
    if row.status != "PENDING_OUTGOING":
        raise BusinessException("当前交接单不在转出确认阶段")
    row.status = "PENDING_RECEIPT"
    row.outgoing_confirmed_by = actor_id
    row.outgoing_confirmed_at = utc_now()
    row.version += 1
    audit_service.record_resource_change(
        action="ASSET_TRANSFER_OUTGOING_CONFIRMED",
        resource_type="asset_transfer_handover",
        resource_id=row.id,
        actor_id=actor_id,
        before_data={"status": "PENDING_OUTGOING"},
        after_data={"status": row.status, "remark": remark},
        reason=remark or "管理员确认转出",
    )
    db.session.commit()
    return _serialize(row)


def confirm_receipt(
    row_id: int, actor_id: int, remark: str | None = None
) -> dict[str, Any]:
    row = _get(row_id)
    if row.receiver_user_id != actor_id:
        raise BusinessException(
            "只有接收员工可以确认收取", result_code=ResultCode.FORBIDDEN
        )
    if row.status != "PENDING_RECEIPT":
        raise BusinessException("当前交接单不在接收确认阶段")
    assets = _load_assets(row.items, actor_id)
    receiver = _user(row.receiver_user_id)
    target_fields: dict[str, Any] = {
        "status": AssetStatus.IN_USE.value,
        "usage_type": "PERSONAL",
        "holder_user_id": receiver.id,
        "public_object_id": None,
        "usage_department_id": receiver.organization_id,
    }
    if row.organization_id is not None:
        target_fields["organization_id"] = row.organization_id
    if row.location_id is not None:
        target_fields["location_id"] = row.location_id
    if row.manager_id is not None:
        target_fields["manager_id"] = row.manager_id
    now = utc_now()
    for asset in assets:
        before = {
            "status": asset.status,
            "holder_user_id": asset.holder_user_id,
            "organization_id": asset.organization_id,
            "location_id": asset.location_id,
            "manager_id": asset.manager_id,
        }
        for key, value in target_fields.items():
            setattr(asset, key, value)
        asset.version += 1
        audit_service.record_asset_lifecycle(
            asset_id=asset.id,
            operation_type="TRANSFER",
            request_no=row.handover_no,
            actor_id=actor_id,
            before_data=before,
            after_data={
                "status": asset.status,
                "holder_user_id": asset.holder_user_id,
                "organization_id": asset.organization_id,
                "location_id": asset.location_id,
                "manager_id": asset.manager_id,
            },
            remark=remark or row.reason,
        )
    row.status = "COMPLETED"
    row.received_confirmed_by = actor_id
    row.received_confirmed_at = now
    row.version += 1
    audit_service.record_resource_change(
        action="ASSET_TRANSFER_RECEIVED_CONFIRMED",
        resource_type="asset_transfer_handover",
        resource_id=row.id,
        actor_id=actor_id,
        before_data={"status": "PENDING_RECEIPT"},
        after_data={"status": row.status},
        reason=remark or "员工确认接收",
    )
    db.session.commit()
    return _serialize(row)


def reject(row_id: int, actor_id: int, reason: str) -> dict[str, Any]:
    row = _get(row_id)
    if actor_id != row.receiver_user_id:
        permission_service.require_permission(actor_id, _MANAGE_PERMISSION)
    text = reason.strip()
    if not text:
        raise BusinessException(
            "拒绝交接必须填写原因", result_code=ResultCode.BAD_REQUEST
        )
    if row.status not in {"PENDING_OUTGOING", "PENDING_RECEIPT"}:
        raise BusinessException("当前交接单不可拒绝")
    row.status = "REJECTED"
    row.rejected_by = actor_id
    row.rejected_at = utc_now()
    row.reject_reason = text
    row.version += 1
    audit_service.record_resource_change(
        action="ASSET_TRANSFER_REJECTED",
        resource_type="asset_transfer_handover",
        resource_id=row.id,
        actor_id=actor_id,
        before_data=None,
        after_data={"status": row.status, "reason": text},
        reason=text,
    )
    db.session.commit()
    return _serialize(row)


__all__ = ["confirm_outgoing", "confirm_receipt", "create", "page", "reject"]
