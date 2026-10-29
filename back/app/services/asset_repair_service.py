"""Structured asset repair history queries and serialization."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.extensions import db
from app.models import AssetRepairRecord
from app.services import asset_access_service, permission_service


def _serialize(record: AssetRepairRecord, *, include_amount: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": record.id,
        "asset_id": record.asset_id,
        "repair_no": record.repair_no,
        "before_status": record.before_status,
        "fault_description": record.fault_description,
        "repair_supplier_id": record.repair_supplier_id,
        "repair_supplier_name": record.repair_supplier_name,
        "sent_at": record.sent_at,
        "completed_at": record.completed_at,
        "repair_result": record.repair_result,
        "confirmed_by": record.confirmed_by,
        "confirmed_at": record.confirmed_at,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }
    if include_amount:
        result["repair_cost"] = (
            str(record.repair_cost) if record.repair_cost is not None else None
        )
    return result


def list_for_asset(asset_id: int, actor_id: int) -> list[dict[str, Any]]:
    """Return structured repair history while enforcing asset and amount access."""
    asset_access_service.get_accessible(asset_id, actor_id)
    include_amount = permission_service.has_permission(actor_id, "asset:amount:view")
    records = list(
        db.session.scalars(
            select(AssetRepairRecord)
            .where(AssetRepairRecord.asset_id == asset_id)
            .order_by(AssetRepairRecord.sent_at.desc(), AssetRepairRecord.id.desc())
        ).all()
    )
    return [_serialize(record, include_amount=include_amount) for record in records]


__all__ = ["list_for_asset"]
