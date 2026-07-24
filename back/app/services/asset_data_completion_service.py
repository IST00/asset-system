"""Null-only asset master-data completion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.common import BusinessException, ResultCode
from app.extensions import db
from app.models import Asset
from app.repositories import asset_business_lock_repository, asset_repository
from app.services import (
    asset_access_service,
    asset_data_service,
    audit_service,
    master_data_service,
    permission_service,
)


_FIELDS = ("unit_id", "source_id", "location_id")


@dataclass(frozen=True)
class _CompletionPlan:
    asset: Asset
    expected_version: int
    resulting_values: dict[str, int | None]
    resulting_completeness: str
    before_data: dict[str, Any]
    after_data: dict[str, Any]


def _batch_no() -> str:
    day = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    return f"ADC{day}{uuid4().hex[:12].upper()}"


def _require_clean_entry_unit_of_work() -> None:
    """This top-level commit owner cannot compose with pending ORM writes."""
    session = db.session()
    if session.new or session.dirty or session.deleted:
        raise RuntimeError(
            "asset data completion transaction boundary rejected pending business writes"
        )


def _stale(asset: Asset) -> BusinessException:
    return BusinessException(f"资产 {asset.asset_code} 已被修改，请刷新后重试")


def _completion_item(plan: _CompletionPlan) -> dict[str, Any]:
    return {
        "id": plan.asset.id,
        **plan.resulting_values,
        "data_completeness": plan.resulting_completeness,
        "version": plan.expected_version + 1,
    }


def complete_data(
    asset_id: int,
    payload: dict[str, Any],
    actor_id: int,
) -> dict[str, Any]:
    batch_payload: dict[str, Any] = {
        "items": [{"asset_id": asset_id, "version": payload["version"]}],
    }
    batch_payload.update(
        {field: payload[field] for field in _FIELDS if field in payload}
    )
    result = complete_data_batch(batch_payload, actor_id)
    return result["items"][0]


def complete_data_batch(
    payload: dict[str, Any],
    actor_id: int,
) -> dict[str, Any]:
    _require_clean_entry_unit_of_work()
    try:
        permission_service.require_permission(actor_id, "asset:data:complete")
        items = payload.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 100:
            raise BusinessException(
                "资产补齐数量必须在1到100之间",
                result_code=ResultCode.BAD_REQUEST,
            )
        changes = {field: payload[field] for field in _FIELDS if field in payload}
        if not changes:
            raise BusinessException("至少填写一个待补充字段")

        targets: dict[int, int] = {}
        for item in items:
            asset_id = item["asset_id"]
            if asset_id in targets:
                raise BusinessException("资产不能重复选择")
            targets[asset_id] = item["version"]

        if "unit_id" in changes:
            master_data_service.require_enabled_unit(changes["unit_id"])
        if "source_id" in changes:
            master_data_service.require_enabled_source(changes["source_id"])
        if "location_id" in changes:
            master_data_service.require_selectable_location(changes["location_id"])

        asset_ids = sorted(targets)
        assets = asset_repository.find_many_accessible_for_update(
            asset_ids,
            asset_access_service.access_filter(actor_id),
        )
        if [asset.id for asset in assets] != asset_ids:
            raise BusinessException(
                "资产不存在",
                result_code=ResultCode.NOT_FOUND,
            )

        locks = asset_business_lock_repository.find_by_assets_for_update(asset_ids)
        if locks:
            assets_by_id = {asset.id: asset for asset in assets}
            locked_asset = assets_by_id[locks[0].asset_id]
            raise BusinessException(f"资产 {locked_asset.asset_code} 正在处理其它业务")

        plans: list[_CompletionPlan] = []
        for asset in assets:
            expected_version = targets[asset.id]
            if asset.version != expected_version:
                raise _stale(asset)
            for field in changes:
                if getattr(asset, field) is not None:
                    raise BusinessException(
                        f"资产 {asset.asset_code} 的 {field} 已有值，不能通过补齐覆盖"
                    )

            resulting_values = {
                "unit_id": changes.get("unit_id", asset.unit_id),
                "source_id": changes.get("source_id", asset.source_id),
                "location_id": changes.get("location_id", asset.location_id),
            }
            resulting_completeness = asset_data_service.calculate_completeness_values(
                resulting_values["unit_id"],
                resulting_values["source_id"],
                resulting_values["location_id"],
            )
            before_data: dict[str, Any] = {
                field: getattr(asset, field) for field in changes
            }
            before_data.update(
                {
                    "data_completeness": asset.data_completeness,
                    "version": asset.version,
                }
            )
            after_data: dict[str, Any] = {
                field: resulting_values[field] for field in changes
            }
            after_data.update(
                {
                    "data_completeness": resulting_completeness,
                    "version": expected_version + 1,
                }
            )
            plans.append(
                _CompletionPlan(
                    asset=asset,
                    expected_version=expected_version,
                    resulting_values=resulting_values,
                    resulting_completeness=resulting_completeness,
                    before_data=before_data,
                    after_data=after_data,
                )
            )

        batch_no = _batch_no()
        result_items: list[dict[str, Any]] = []
        for plan in plans:
            if not asset_repository.complete_missing_fields(
                plan.asset.id,
                plan.expected_version,
                changes,
                plan.resulting_completeness,
            ):
                raise _stale(plan.asset)
            audit_service.record_asset_lifecycle(
                asset_id=plan.asset.id,
                operation_type="ASSET_DATA_COMPLETE",
                request_no=batch_no,
                actor_id=actor_id,
                before_data=plan.before_data,
                after_data=plan.after_data,
            )
            result_items.append(_completion_item(plan))

        audit_service.record_resource_change(
            action="ASSET_DATA_COMPLETE",
            resource_type="asset_data_completion_batch",
            resource_id=batch_no,
            actor_id=actor_id,
            before_data={
                "asset_ids": asset_ids,
                "fields": sorted(changes),
            },
            after_data={"updated_count": len(result_items)},
        )
        db.session.commit()
        return {
            "batch_no": batch_no,
            "updated_count": len(result_items),
            "items": result_items,
        }
    except Exception:
        db.session.rollback()
        raise


__all__ = ["complete_data", "complete_data_batch"]
