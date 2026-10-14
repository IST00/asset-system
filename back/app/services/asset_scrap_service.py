"""Structured asset scrap history queries and serialization."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select

from app.extensions import db
from app.models import Asset, AssetLifecycleRecord, AssetScrapRecord
from app.services import asset_access_service, permission_service


def _date_value(value: Any) -> Any:
    """Serialize date-only values consistently across current and legacy rows."""
    return value.isoformat() if isinstance(value, date) else value


def _serialize(record: AssetScrapRecord, *, include_amount: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": record.id,
        "asset_id": record.asset_id,
        "scrap_no": record.scrap_no,
        "scrap_date": record.scrap_date.isoformat(),
        "reason": record.reason,
        "disposition": record.disposition,
        "disposition_remark": record.disposition_remark,
        "disposal_date": (record.disposal_date or record.scrap_date).isoformat(),
        "confirmed_by": record.confirmed_by,
        "confirmed_at": record.confirmed_at,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }
    if include_amount:
        result["scrap_amount"] = str(record.scrap_amount)
    return result


def list_for_asset(asset_id: int, actor_id: int) -> list[dict[str, Any]]:
    """Return structured scrap history while enforcing asset and amount access."""
    asset_access_service.get_accessible(asset_id, actor_id)
    include_amount = permission_service.has_permission(actor_id, "asset:amount:view")
    records = list(
        db.session.scalars(
            select(AssetScrapRecord)
            .where(AssetScrapRecord.asset_id == asset_id)
            .order_by(
                AssetScrapRecord.scrap_date.desc(),
                AssetScrapRecord.id.desc(),
            )
        ).all()
    )
    if records:
        return [_serialize(record, include_amount=include_amount) for record in records]

    # Preserve visibility for assets scrapped before the structured table was
    # introduced. The lifecycle row contains the same immutable audit evidence.
    legacy_rows = list(
        db.session.scalars(
            select(AssetLifecycleRecord)
            .where(
                AssetLifecycleRecord.asset_id == asset_id,
                AssetLifecycleRecord.operation_type == "SCRAP",
            )
            .order_by(
                AssetLifecycleRecord.created_at.desc(), AssetLifecycleRecord.id.desc()
            )
        ).all()
    )
    asset = db.session.get(Asset, asset_id)
    result: list[dict[str, Any]] = []
    for row in legacy_rows:
        after_data = row.after_data if isinstance(row.after_data, dict) else {}
        custom = after_data.get("custom_attributes")
        scrap = custom.get("scrap") if isinstance(custom, dict) else None
        scrap_data = scrap if isinstance(scrap, dict) else {}
        result.append(
            {
                "id": -row.id,
                "asset_id": asset_id,
                "scrap_no": row.operation_no,
                "scrap_date": _date_value(
                    scrap_data.get("scrap_date") or row.created_at.date()
                ),
                "reason": row.remark or "历史报废记录",
                "disposition": scrap_data.get("disposition"),
                "disposition_remark": scrap_data.get("disposition_remark"),
                "disposal_date": _date_value(
                    scrap_data.get("disposal_date")
                    or scrap_data.get("scrap_date")
                    or row.created_at.date()
                ),
                "confirmed_by": row.operator_id,
                "confirmed_at": row.created_at,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                **(
                    {"scrap_amount": scrap_data.get("scrap_amount")}
                    if include_amount
                    else {}
                ),
            }
        )
    if not legacy_rows and asset is not None:
        scrap = asset.custom_attributes.get("scrap")
        if isinstance(scrap, dict):
            result.append(
                {
                    "id": -asset.id,
                    "asset_id": asset_id,
                    "scrap_no": "",
                    "scrap_date": _date_value(scrap.get("scrap_date")),
                    "reason": "历史报废记录",
                    "disposition": scrap.get("disposition"),
                    "disposition_remark": scrap.get("disposition_remark"),
                    "disposal_date": _date_value(
                        scrap.get("disposal_date")
                        or scrap.get("scrap_date")
                        or asset.updated_at.date()
                    ),
                    "confirmed_by": 0,
                    "confirmed_at": asset.updated_at,
                    "created_at": asset.updated_at,
                    "updated_at": asset.updated_at,
                    **(
                        {"scrap_amount": scrap.get("scrap_amount")}
                        if include_amount
                        else {}
                    ),
                }
            )
    return result


__all__ = ["list_for_asset"]
