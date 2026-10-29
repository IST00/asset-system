"""Inventory task lifecycle, snapshot assignment, scanning, and exception handling."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse
from uuid import uuid4

from flask import current_app
from sqlalchemy import case, exists, func, or_, select
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.common import BusinessException, PageResult, ResultCode
from app.enums import (
    AssetStatus,
    InventoryItemStatus,
    InventoryLocationResult,
    InventoryReviewStatus,
    InventorySubmissionMethod,
    InventoryTaskStatus,
    RecordStatus,
)
from app.extensions import db
from app.models import (
    Asset,
    AssetCategory,
    AssetLocation,
    InventoryItem,
    InventoryPhoto,
    InventoryReminder,
    InventoryResultVersion,
    InventoryScanEvent,
    InventoryTask,
    InventoryTaskAdmin,
    Organization,
    User,
)
from app.repositories import rbac_repository
from app.services import audit_service, permission_service
from app.services.inventory_report import build_workbook

_ALLOWED_PHOTO_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/heic": ".heic",
    "image/heif": ".heif",
}
_MAX_PHOTO_BYTES = 10 * 1024 * 1024
_INVENTORY_LIFECYCLE_STATUS_LABELS = {
    InventoryItemStatus.FOUND.value: "正常",
    InventoryItemStatus.LOSS.value: "盘亏",
    InventoryItemStatus.EXEMPTED.value: "无需盘点",
    InventoryItemStatus.UNSUBMITTED.value: "未提交",
}


def _inventory_lifecycle_status(item: InventoryItem) -> str:
    return _INVENTORY_LIFECYCLE_STATUS_LABELS.get(item.status, item.status)


def _record_inventory_lifecycle_rows(task: InventoryTask, actor_id: int) -> None:
    items = list(
        db.session.scalars(
            select(InventoryItem).where(InventoryItem.task_id == task.id)
        ).all()
    )
    for item in items:
        status_label = _inventory_lifecycle_status(item)
        audit_service.record_asset_lifecycle(
            asset_id=item.asset_id,
            operation_type="INVENTORY_PROCESS",
            request_no=task.task_no,
            actor_id=actor_id,
            before_data={},
            after_data={
                "task_no": task.task_no,
                "task_name": task.name,
                "status": item.status,
                "physical_result": item.physical_result,
                "location_result": item.location_result,
                "actual_location_text": item.actual_location_text,
                "resolution": item.resolution,
            },
            remark=(
                f"盘点单号: {task.task_no}（{status_label}）; "
                f"盘点单名称: {task.name}"
            ),
        )


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return _aware(value).isoformat() if value is not None else None


def _user_name(user: User | None) -> str | None:
    if user is None:
        return None
    return user.nickname or user.username


def _is_super_admin(actor_id: int) -> bool:
    return "SUPER_ADMIN" in rbac_repository.role_codes_for_user(actor_id)


def _task_admin_ids(task_id: int) -> list[int]:
    statement = (
        select(InventoryTaskAdmin.user_id)
        .where(InventoryTaskAdmin.task_id == task_id)
        .order_by(InventoryTaskAdmin.id.asc())
    )
    return list(db.session.scalars(statement).all())


def _can_manage(task_id: int, actor_id: int) -> bool:
    if _is_super_admin(actor_id):
        return True
    statement = select(InventoryTaskAdmin.id).where(
        InventoryTaskAdmin.task_id == task_id,
        InventoryTaskAdmin.user_id == actor_id,
    )
    return db.session.scalar(statement) is not None


def _require_task(task_id: int) -> InventoryTask:
    task = db.session.get(InventoryTask, task_id)
    if task is None:
        raise BusinessException("盘点任务不存在", result_code=ResultCode.NOT_FOUND)
    return task


def _require_view(task: InventoryTask, actor_id: int) -> None:
    permission_service.require_permission(actor_id, "inventory:view")
    if _can_manage(task.id, actor_id):
        return
    statement = select(InventoryItem.id).where(
        InventoryItem.task_id == task.id,
        InventoryItem.responsible_user_id == actor_id,
    )
    if db.session.scalar(statement) is None:
        raise BusinessException("无权查看该盘点任务", result_code=ResultCode.FORBIDDEN)


def _require_manage(task: InventoryTask, actor_id: int) -> None:
    if not _can_manage(task.id, actor_id):
        raise BusinessException(
            "仅任务盘点管理员可执行此操作", result_code=ResultCode.FORBIDDEN
        )


def _effective_status(task: InventoryTask) -> str:
    if (
        task.status == InventoryTaskStatus.IN_PROGRESS.value
        and _aware(task.deadline_at) < _now()
    ):
        return "OVERDUE"
    return task.status


def _task_counts(task_id: int) -> dict[str, int]:
    row = db.session.execute(
        select(
            func.count(InventoryItem.id),
            func.sum(
                case(
                    (InventoryItem.status != InventoryItemStatus.PENDING.value, 1),
                    else_=0,
                )
            ),
            func.sum(
                case(
                    (InventoryItem.status == InventoryItemStatus.PENDING.value, 1),
                    else_=0,
                )
            ),
            func.sum(
                case(
                    (InventoryItem.status == InventoryItemStatus.FOUND.value, 1),
                    else_=0,
                )
            ),
            func.sum(
                case(
                    (InventoryItem.status == InventoryItemStatus.LOSS.value, 1), else_=0
                )
            ),
            func.sum(
                case(
                    (InventoryItem.status == InventoryItemStatus.UNSUBMITTED.value, 1),
                    else_=0,
                )
            ),
            func.sum(
                case(
                    (InventoryItem.status == InventoryItemStatus.EXEMPTED.value, 1),
                    else_=0,
                )
            ),
            func.sum(
                case(
                    (
                        or_(
                            InventoryItem.review_status.in_(
                                [
                                    InventoryReviewStatus.PENDING.value,
                                    InventoryReviewStatus.RETURNED.value,
                                ]
                            ),
                            InventoryItem.location_result.in_(
                                [
                                    InventoryLocationResult.DIFFERENT.value,
                                    InventoryLocationResult.TEMPORARY.value,
                                ]
                            ),
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            func.sum(
                case(
                    (
                        InventoryItem.submission_method
                        == InventorySubmissionMethod.ADMIN_MARKED.value,
                        1,
                    ),
                    else_=0,
                )
            ),
        ).where(InventoryItem.task_id == task_id)
    ).one()
    values = [int(value or 0) for value in row]
    return {
        "total": values[0],
        "checked": values[1],
        "pending": values[2],
        "found": values[3],
        "loss": values[4],
        "unsubmitted": values[5],
        "exempted": values[6],
        "exceptions": values[7],
        "admin_marked": values[8],
    }


def _task_to_dict(task: InventoryTask, actor_id: int) -> dict[str, Any]:
    admin_ids = _task_admin_ids(task.id)
    users = {
        user.id: user
        for user in db.session.scalars(select(User).where(User.id.in_(admin_ids))).all()
    }
    counts = _task_counts(task.id)
    completed = counts["checked"]
    progress = round(completed * 100 / counts["total"], 1) if counts["total"] else 0.0
    return {
        "id": task.id,
        "task_no": task.task_no,
        "name": task.name,
        "status": _effective_status(task),
        "stored_status": task.status,
        "deadline_at": _iso(task.deadline_at),
        "photo_source_mode": task.photo_source_mode,
        "min_photo_count": task.min_photo_count,
        "scope_filters": task.scope_filters,
        "created_by": task.created_by,
        "admin_user_ids": admin_ids,
        "admins": [
            {"id": user_id, "name": _user_name(users.get(user_id)) or f"用户 {user_id}"}
            for user_id in admin_ids
        ],
        "published_at": _iso(task.published_at),
        "collection_ended_at": _iso(task.collection_ended_at),
        "completed_at": _iso(task.completed_at),
        "cancelled_at": _iso(task.cancelled_at),
        "cancel_reason": task.cancel_reason,
        "counts": counts,
        "progress": progress,
        "can_manage": _can_manage(task.id, actor_id),
        "created_at": _iso(task.created_at),
        "updated_at": _iso(task.updated_at),
    }


def _photo_to_dict(photo: InventoryPhoto) -> dict[str, Any]:
    return {
        "id": photo.id,
        "original_name": photo.original_name,
        "mime_type": photo.mime_type,
        "size_bytes": photo.size_bytes,
        "uploaded_by": photo.uploaded_by,
        "created_at": _iso(photo.created_at),
        "url": f"/api/v1/inventory/photos/{photo.id}",
    }


def _item_to_dict(
    item: InventoryItem, task: InventoryTask, actor_id: int
) -> dict[str, Any]:
    photos = list(
        db.session.scalars(
            select(InventoryPhoto)
            .where(InventoryPhoto.item_id == item.id)
            .order_by(InventoryPhoto.id.asc())
        ).all()
    )
    accepting = task.status == InventoryTaskStatus.IN_PROGRESS.value
    owns_item = item.responsible_user_id == actor_id or _can_manage(task.id, actor_id)
    can_submit = (
        accepting
        and owns_item
        and (
            item.status == InventoryItemStatus.PENDING.value
            or item.review_status == InventoryReviewStatus.RETURNED.value
        )
    )
    return {
        "id": item.id,
        "task_id": item.task_id,
        "asset_id": item.asset_id,
        "asset_code": item.asset_code,
        "asset_name": item.asset_name,
        "asset_status_snapshot": item.asset_status_snapshot,
        "organization_id": item.organization_id,
        "organization_name": item.organization_name,
        "category_id": item.category_id,
        "category_name": item.category_name,
        "holder_user_id": item.holder_user_id,
        "holder_name": item.holder_name,
        "responsible_user_id": item.responsible_user_id,
        "ledger_location_id": item.ledger_location_id,
        "ledger_location_name": item.ledger_location_name,
        "parent_asset_id": item.parent_asset_id,
        "parent_asset_code": item.parent_asset_code,
        "status": item.status,
        "physical_result": item.physical_result,
        "location_result": item.location_result,
        "actual_location_id": item.actual_location_id,
        "actual_location_text": item.actual_location_text,
        "loss_reason": item.loss_reason,
        "loss_description": item.loss_description,
        "borrowed_by": item.borrowed_by,
        "submission_method": item.submission_method,
        "submitted_by": item.submitted_by,
        "submitted_at": _iso(item.submitted_at),
        "is_late": item.is_late,
        "review_status": item.review_status,
        "resolution": item.resolution,
        "resolution_reason": item.resolution_reason,
        "resolved_by": item.resolved_by,
        "resolved_at": _iso(item.resolved_at),
        "admin_mark_reason": item.admin_mark_reason,
        "photos": [_photo_to_dict(photo) for photo in photos],
        "can_submit": can_submit,
        "version": item.version,
        "result_version_count": int(
            db.session.scalar(
                select(func.count(InventoryResultVersion.id)).where(
                    InventoryResultVersion.item_id == item.id
                )
            )
            or 0
        ),
        "suite_progress": _suite_progress(item),
    }


def _suite_progress(item: InventoryItem) -> dict[str, int] | None:
    root_asset_id = item.parent_asset_id or item.asset_id
    siblings = list(
        db.session.scalars(
            select(InventoryItem).where(
                InventoryItem.task_id == item.task_id,
                or_(
                    InventoryItem.asset_id == root_asset_id,
                    InventoryItem.parent_asset_id == root_asset_id,
                ),
            )
        ).all()
    )
    if len(siblings) == 1:
        return None
    return {
        "total": len(siblings),
        "checked": sum(
            sibling.status != InventoryItemStatus.PENDING.value for sibling in siblings
        ),
    }


def _record_item_version(
    item: InventoryItem, *, action: str, actor_id: int, reason: str | None = None
) -> None:
    version_no = (
        int(
            db.session.scalar(
                select(func.max(InventoryResultVersion.version_no)).where(
                    InventoryResultVersion.item_id == item.id
                )
            )
            or 0
        )
        + 1
    )
    snapshot = {
        "status": item.status,
        "physical_result": item.physical_result,
        "location_result": item.location_result,
        "actual_location_id": item.actual_location_id,
        "actual_location_text": item.actual_location_text,
        "loss_reason": item.loss_reason,
        "loss_description": item.loss_description,
        "submission_method": item.submission_method,
        "submitted_by": item.submitted_by,
        "submitted_at": item.submitted_at.isoformat() if item.submitted_at else None,
        "review_status": item.review_status,
        "resolution": item.resolution,
        "responsible_user_id": item.responsible_user_id,
    }
    db.session.add(
        InventoryResultVersion(
            task_id=item.task_id,
            item_id=item.id,
            version_no=version_no,
            action=action,
            reason=reason,
            changed_by=actor_id,
            snapshot=snapshot,
        )
    )


def _next_task_no() -> str:
    prefix = _now().strftime("PD%Y%m%d")
    statement = select(func.count(InventoryTask.id)).where(
        InventoryTask.task_no.like(f"{prefix}%")
    )
    count = int(db.session.scalar(statement) or 0) + 1
    return f"{prefix}{count:04d}"


def _validate_enabled_users(user_ids: list[int]) -> dict[int, User]:
    users = list(db.session.scalars(select(User).where(User.id.in_(user_ids))).all())
    result = {user.id: user for user in users}
    if len(result) != len(set(user_ids)) or any(not user.enabled for user in users):
        raise BusinessException("盘点管理员或责任人不存在、重复或已停用")
    return result


def create_task(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "inventory:create")
    deadline = _aware(payload["deadline_at"])
    if deadline <= _now():
        raise BusinessException("盘点截止时间必须晚于当前时间")

    admin_ids = sorted(set(payload["admin_user_ids"]))
    public_responsible_id = payload.get("public_responsible_user_id") or actor_id
    _validate_enabled_users(sorted(set([*admin_ids, public_responsible_id])))

    filters = [Asset.status != AssetStatus.SCRAPPED.value]
    organization_ids = payload["organization_ids"]
    accessible_ids = permission_service.accessible_organization_ids(actor_id)
    if organization_ids:
        if accessible_ids is not None and not set(organization_ids).issubset(
            accessible_ids
        ):
            raise BusinessException(
                "盘点范围包含无权访问的组织", result_code=ResultCode.FORBIDDEN
            )
        filters.append(Asset.organization_id.in_(organization_ids))
    elif accessible_ids is not None:
        if not accessible_ids:
            raise BusinessException("当前账号没有可盘点的组织范围")
        filters.append(Asset.organization_id.in_(accessible_ids))
    if payload["location_ids"]:
        filters.append(Asset.location_id.in_(payload["location_ids"]))
    if payload["category_ids"]:
        filters.append(Asset.category_id.in_(payload["category_ids"]))
    if payload["holder_user_ids"]:
        filters.append(Asset.holder_user_id.in_(payload["holder_user_ids"]))
    if payload["manager_user_ids"]:
        filters.append(Asset.manager_id.in_(payload["manager_user_ids"]))
    if payload["asset_statuses"]:
        filters.append(Asset.status.in_(payload["asset_statuses"]))

    holder = User
    rows = db.session.execute(
        select(
            Asset,
            Organization.name,
            AssetCategory.name,
            AssetLocation.name,
            holder.nickname,
            holder.username,
        )
        .join(Organization, Organization.id == Asset.organization_id)
        .join(AssetCategory, AssetCategory.id == Asset.category_id)
        .outerjoin(AssetLocation, AssetLocation.id == Asset.location_id)
        .outerjoin(holder, holder.id == Asset.holder_user_id)
        .where(*filters)
        .order_by(Asset.id.asc())
    ).all()
    if not rows:
        raise BusinessException("当前筛选范围内没有可盘点资产")

    status = (
        InventoryTaskStatus.IN_PROGRESS.value
        if payload["publish"]
        else InventoryTaskStatus.DRAFT.value
    )
    task = InventoryTask(
        task_no=_next_task_no(),
        name=payload["name"],
        status=status,
        deadline_at=deadline,
        photo_source_mode=payload["photo_source_mode"],
        min_photo_count=payload["min_photo_count"],
        scope_filters={
            "organization_ids": organization_ids,
            "location_ids": payload["location_ids"],
            "category_ids": payload["category_ids"],
            "holder_user_ids": payload["holder_user_ids"],
            "manager_user_ids": payload["manager_user_ids"],
            "asset_statuses": payload["asset_statuses"],
        },
        created_by=actor_id,
        published_at=_now() if payload["publish"] else None,
    )
    db.session.add(task)
    db.session.flush()
    db.session.add_all(
        [InventoryTaskAdmin(task_id=task.id, user_id=user_id) for user_id in admin_ids]
    )
    for (
        asset,
        organization_name,
        category_name,
        location_name,
        nickname,
        username,
    ) in rows:
        responsible_user_id = asset.holder_user_id or public_responsible_id
        db.session.add(
            InventoryItem(
                task_id=task.id,
                asset_id=asset.id,
                responsible_user_id=responsible_user_id,
                asset_code=asset.asset_code,
                asset_name=asset.asset_name,
                asset_status_snapshot=asset.status,
                organization_id=asset.organization_id,
                organization_name=str(organization_name),
                category_id=asset.category_id,
                category_name=str(category_name),
                holder_user_id=asset.holder_user_id,
                holder_name=(nickname or username) if asset.holder_user_id else None,
                ledger_location_id=asset.location_id,
                ledger_location_name=str(location_name) if location_name else None,
                parent_asset_id=asset.parent_asset_id,
                parent_asset_code=(
                    db.session.scalar(
                        select(Asset.asset_code).where(
                            Asset.id == asset.parent_asset_id
                        )
                    )
                    if asset.parent_asset_id
                    else None
                ),
            )
        )
    db.session.flush()
    audit_service.record_resource_change(
        action="INVENTORY_TASK_CREATE",
        resource_type="inventory_task",
        resource_id=task.id,
        actor_id=actor_id,
        before_data=None,
        after_data={
            "task_no": task.task_no,
            "status": task.status,
            "asset_count": len(rows),
        },
    )
    db.session.commit()
    return _task_to_dict(task, actor_id)


def publish_task(task_id: int, actor_id: int) -> dict[str, Any]:
    task = _require_task(task_id)
    _require_manage(task, actor_id)
    if task.status != InventoryTaskStatus.DRAFT.value:
        raise BusinessException("只有草稿任务可以发布")
    task.status = InventoryTaskStatus.IN_PROGRESS.value
    task.published_at = _now()
    task.version += 1
    audit_service.record_resource_change(
        action="INVENTORY_TASK_PUBLISH",
        resource_type="inventory_task",
        resource_id=task.id,
        actor_id=actor_id,
        before_data={"status": InventoryTaskStatus.DRAFT.value},
        after_data={"status": task.status},
    )
    db.session.commit()
    return _task_to_dict(task, actor_id)


def list_tasks(
    *, actor_id: int, page_index: int, size: int, status: str | None = None
) -> PageResult:
    permission_service.require_permission(actor_id, "inventory:view")
    filters = []
    if not _is_super_admin(actor_id):
        filters.append(
            or_(
                exists(
                    select(InventoryTaskAdmin.id).where(
                        InventoryTaskAdmin.task_id == InventoryTask.id,
                        InventoryTaskAdmin.user_id == actor_id,
                    )
                ),
                exists(
                    select(InventoryItem.id).where(
                        InventoryItem.task_id == InventoryTask.id,
                        InventoryItem.responsible_user_id == actor_id,
                    )
                ),
            )
        )
    if status and status != "OVERDUE":
        filters.append(InventoryTask.status == status)
    if status == "OVERDUE":
        filters.extend(
            [
                InventoryTask.status == InventoryTaskStatus.IN_PROGRESS.value,
                InventoryTask.deadline_at < _now(),
            ]
        )
    total = int(
        db.session.scalar(select(func.count(InventoryTask.id)).where(*filters)) or 0
    )
    tasks = list(
        db.session.scalars(
            select(InventoryTask)
            .where(*filters)
            .order_by(InventoryTask.deadline_at.asc(), InventoryTask.id.desc())
            .limit(size)
            .offset(page_index * size)
        ).all()
    )
    return PageResult(
        items=[_task_to_dict(task, actor_id) for task in tasks],
        total=total,
        page=page_index,
        size=size,
    )


def get_task(task_id: int, actor_id: int) -> dict[str, Any]:
    task = _require_task(task_id)
    _require_view(task, actor_id)
    return _task_to_dict(task, actor_id)


def list_items(
    *,
    task_id: int,
    actor_id: int,
    page_index: int,
    size: int,
    status: str | None = None,
    responsible_user_id: int | None = None,
) -> PageResult:
    task = _require_task(task_id)
    _require_view(task, actor_id)
    filters = [InventoryItem.task_id == task.id]
    if not _can_manage(task.id, actor_id):
        filters.append(InventoryItem.responsible_user_id == actor_id)
    elif responsible_user_id is not None:
        filters.append(InventoryItem.responsible_user_id == responsible_user_id)
    if status:
        if status == "EXCEPTION":
            filters.append(
                or_(
                    InventoryItem.review_status.in_(
                        [
                            InventoryReviewStatus.PENDING.value,
                            InventoryReviewStatus.RETURNED.value,
                        ]
                    ),
                    InventoryItem.status.in_(
                        [
                            InventoryItemStatus.LOSS.value,
                            InventoryItemStatus.UNSUBMITTED.value,
                        ]
                    ),
                    InventoryItem.location_result.in_(
                        [
                            InventoryLocationResult.DIFFERENT.value,
                            InventoryLocationResult.TEMPORARY.value,
                        ]
                    ),
                )
            )
        else:
            filters.append(InventoryItem.status == status)
    total = int(
        db.session.scalar(select(func.count(InventoryItem.id)).where(*filters)) or 0
    )
    items = list(
        db.session.scalars(
            select(InventoryItem)
            .where(*filters)
            .order_by(InventoryItem.id.asc())
            .limit(size)
            .offset(page_index * size)
        ).all()
    )
    return PageResult(
        items=[_item_to_dict(item, task, actor_id) for item in items],
        total=total,
        page=page_index,
        size=size,
    )


def list_my_pending_items(actor_id: int) -> list[dict[str, Any]]:
    permission_service.require_permission(actor_id, "inventory:view")
    rows = list(
        db.session.execute(
            select(InventoryItem, InventoryTask)
            .join(InventoryTask, InventoryTask.id == InventoryItem.task_id)
            .where(
                InventoryTask.status == InventoryTaskStatus.IN_PROGRESS.value,
                InventoryItem.responsible_user_id == actor_id,
                InventoryItem.status == InventoryItemStatus.PENDING.value,
            )
            .order_by(
                InventoryTask.deadline_at.asc(),
                InventoryItem.id.asc(),
            )
        ).all()
    )
    return [_item_to_dict(item, task, actor_id) for item, task in rows]


def _normalize_asset_code(scanned_value: str) -> str:
    value = scanned_value.strip()
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        query = parse_qs(parsed.query)
        for key in ("assetCode", "asset_code", "code"):
            if query.get(key):
                return query[key][0].strip()
        path_value = unquote(parsed.path.rstrip("/").split("/")[-1])
        if path_value:
            return path_value
    return value


def scan(task_id: int, payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    task = _require_task(task_id)
    _require_view(task, actor_id)
    if task.status != InventoryTaskStatus.IN_PROGRESS.value:
        raise BusinessException("当前任务已停止收集，不能继续扫码")
    scanned_value = payload["scanned_value"]
    asset_code = _normalize_asset_code(scanned_value)
    asset = db.session.scalar(select(Asset).where(Asset.asset_code == asset_code))
    item = None
    outcome = "UNKNOWN_ASSET"
    if asset is not None:
        item = db.session.scalar(
            select(InventoryItem).where(
                InventoryItem.task_id == task.id,
                InventoryItem.asset_id == asset.id,
            )
        )
        outcome = "OUTSIDE_SCOPE" if item is None else "MATCHED"
        if (
            item is not None
            and not _can_manage(task.id, actor_id)
            and item.responsible_user_id != actor_id
        ):
            outcome = "OUTSIDE_ASSIGNMENT"
        if item is not None and item.status != InventoryItemStatus.PENDING.value:
            outcome = "ALREADY_SUBMITTED"
    event = InventoryScanEvent(
        task_id=task.id,
        scanned_by=actor_id,
        scanned_value=scanned_value,
        normalized_asset_code=asset_code,
        asset_id=asset.id if asset else None,
        item_id=item.id if item else None,
        outcome=outcome,
    )
    db.session.add(event)
    db.session.commit()
    return {
        "outcome": outcome,
        "asset_code": asset_code,
        "item": _item_to_dict(item, task, actor_id)
        if item and outcome == "MATCHED"
        else None,
        "message": {
            "MATCHED": "已匹配到本次盘点资产",
            "OUTSIDE_SCOPE": "该资产不在本次盘点范围，已记录异常扫码",
            "OUTSIDE_ASSIGNMENT": "该资产不在你的盘点分配范围，已记录异常扫码",
            "ALREADY_SUBMITTED": "该资产已经提交过盘点结果",
            "UNKNOWN_ASSET": "系统中未找到该资产编码，已记录异常扫码",
        }[outcome],
    }


def list_scan_events(
    *,
    task_id: int,
    actor_id: int,
    page_index: int,
    size: int,
    outcome: str | None = None,
) -> PageResult:
    task = _require_task(task_id)
    _require_manage(task, actor_id)
    filters = [InventoryScanEvent.task_id == task.id]
    if outcome:
        filters.append(InventoryScanEvent.outcome == outcome)
    else:
        filters.append(InventoryScanEvent.outcome != "MATCHED")
    total = int(
        db.session.scalar(select(func.count(InventoryScanEvent.id)).where(*filters))
        or 0
    )
    events = list(
        db.session.scalars(
            select(InventoryScanEvent)
            .where(*filters)
            .order_by(InventoryScanEvent.id.desc())
            .limit(size)
            .offset(page_index * size)
        ).all()
    )
    user_ids = {event.scanned_by for event in events}
    asset_ids = {event.asset_id for event in events if event.asset_id is not None}
    users = {
        user.id: user
        for user in db.session.scalars(select(User).where(User.id.in_(user_ids))).all()
    }
    assets = {
        asset.id: asset
        for asset in db.session.scalars(
            select(Asset).where(Asset.id.in_(asset_ids))
        ).all()
    }
    return PageResult(
        items=[
            {
                "id": event.id,
                "scanned_value": event.scanned_value,
                "normalized_asset_code": event.normalized_asset_code,
                "asset_id": event.asset_id,
                "asset_name": assets[event.asset_id].asset_name
                if event.asset_id in assets
                else None,
                "item_id": event.item_id,
                "outcome": event.outcome,
                "scanned_by": event.scanned_by,
                "scanner_name": _user_name(users.get(event.scanned_by)),
                "created_at": _iso(event.created_at),
                "resolution": event.resolution,
                "resolution_reason": event.resolution_reason,
                "resolved_by": event.resolved_by,
                "resolved_at": _iso(event.resolved_at),
            }
            for event in events
        ],
        total=total,
        page=page_index,
        size=size,
    )


def upload_photo(
    task_id: int, item_id: int, file: FileStorage | None, actor_id: int
) -> dict[str, Any]:
    task = _require_task(task_id)
    _require_view(task, actor_id)
    item = db.session.get(InventoryItem, item_id)
    if item is None or item.task_id != task.id:
        raise BusinessException("盘点明细不存在", result_code=ResultCode.NOT_FOUND)
    if task.status != InventoryTaskStatus.IN_PROGRESS.value:
        raise BusinessException("当前任务已停止收集")
    if not _can_manage(task.id, actor_id) and item.responsible_user_id != actor_id:
        raise BusinessException(
            "不能为他人的盘点资产上传照片", result_code=ResultCode.FORBIDDEN
        )
    if file is None or not file.filename:
        raise BusinessException("请选择盘点照片")
    mime_type = file.mimetype.lower()
    if mime_type not in _ALLOWED_PHOTO_TYPES:
        raise BusinessException("盘点照片仅支持 JPG、PNG 和 HEIC")
    existing_count = int(
        db.session.scalar(
            select(func.count(InventoryPhoto.id)).where(
                InventoryPhoto.item_id == item.id
            )
        )
        or 0
    )
    if existing_count >= 25:
        raise BusinessException("该资产保留的历史盘点照片已达上限，请联系管理员")
    data = file.read(_MAX_PHOTO_BYTES + 1)
    if len(data) > _MAX_PHOTO_BYTES:
        raise BusinessException("单张盘点照片不能超过 10MB")
    extension = _ALLOWED_PHOTO_TYPES[mime_type]
    storage_name = f"{task.id}_{item.id}_{uuid4().hex}{extension}"
    folder = Path(current_app.instance_path) / "inventory_photos"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / storage_name).write_bytes(data)
    original_name = secure_filename(file.filename) or f"photo{extension}"
    photo = InventoryPhoto(
        task_id=task.id,
        item_id=item.id,
        uploaded_by=actor_id,
        storage_name=storage_name,
        original_name=original_name,
        mime_type=mime_type,
        size_bytes=len(data),
    )
    db.session.add(photo)
    db.session.commit()
    return _photo_to_dict(photo)


def get_photo(photo_id: int, actor_id: int) -> tuple[Path, str, str]:
    photo = db.session.get(InventoryPhoto, photo_id)
    if photo is None:
        raise BusinessException("盘点照片不存在", result_code=ResultCode.NOT_FOUND)
    task = _require_task(photo.task_id)
    _require_view(task, actor_id)
    path = Path(current_app.instance_path) / "inventory_photos" / photo.storage_name
    if not path.is_file():
        raise BusinessException("盘点照片文件不存在", result_code=ResultCode.NOT_FOUND)
    return path, photo.mime_type, photo.original_name


def submit_item(
    task_id: int, item_id: int, payload: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    task = _require_task(task_id)
    _require_view(task, actor_id)
    if task.status != InventoryTaskStatus.IN_PROGRESS.value:
        raise BusinessException("当前任务已停止收集")
    item = db.session.get(InventoryItem, item_id)
    if item is None or item.task_id != task.id:
        raise BusinessException("盘点明细不存在", result_code=ResultCode.NOT_FOUND)
    if not _can_manage(task.id, actor_id) and item.responsible_user_id != actor_id:
        raise BusinessException(
            "不能提交他人的盘点资产", result_code=ResultCode.FORBIDDEN
        )
    if (
        item.status != InventoryItemStatus.PENDING.value
        and item.review_status != InventoryReviewStatus.RETURNED.value
    ):
        raise BusinessException("该资产已经提交盘点结果")

    now = _now()
    if payload["result"] == "FOUND":
        scanned_value = payload["scanned_value"]
        normalized = _normalize_asset_code(scanned_value)
        if normalized != item.asset_code:
            raise BusinessException("扫码结果与当前资产不一致")
        matched_event = db.session.scalar(
            select(InventoryScanEvent.id)
            .where(
                InventoryScanEvent.task_id == task.id,
                InventoryScanEvent.item_id == item.id,
                InventoryScanEvent.scanned_by == actor_id,
                InventoryScanEvent.outcome == "MATCHED",
            )
            .order_by(InventoryScanEvent.id.desc())
        )
        if matched_event is None:
            raise BusinessException("请先真实扫描资产标签")
        photo_ids = sorted(set(payload["photo_ids"]))
        photo_count = int(
            db.session.scalar(
                select(func.count(InventoryPhoto.id)).where(
                    InventoryPhoto.item_id == item.id,
                    InventoryPhoto.id.in_(photo_ids),
                    InventoryPhoto.uploaded_by == actor_id,
                )
            )
            or 0
        )
        if photo_count < task.min_photo_count:
            raise BusinessException(
                f"每件资产至少需要上传 {task.min_photo_count} 张现场照片"
            )
        actual_location_id = payload.get("actual_location_id")
        temporary_location = payload.get("temporary_location")
        if actual_location_id is not None:
            location = db.session.get(AssetLocation, actual_location_id)
            if (
                location is None
                or location.status != RecordStatus.ENABLED.value
                or not location.is_selectable
            ):
                raise BusinessException("实际地点不可用")
            item.actual_location_id = location.id
            item.actual_location_text = location.name
            item.location_result = (
                InventoryLocationResult.MATCHED.value
                if location.id == item.ledger_location_id
                else InventoryLocationResult.DIFFERENT.value
            )
        else:
            item.actual_location_id = None
            item.actual_location_text = temporary_location
            item.location_result = InventoryLocationResult.TEMPORARY.value
        item.status = InventoryItemStatus.FOUND.value
        item.physical_result = "FOUND"
        item.loss_reason = None
        item.loss_description = None
        item.borrowed_by = None
        item.review_status = (
            InventoryReviewStatus.AUTO_CONFIRMED.value
            if item.location_result == InventoryLocationResult.MATCHED.value
            else InventoryReviewStatus.PENDING.value
        )
    else:
        item.status = InventoryItemStatus.LOSS.value
        item.physical_result = "LOSS"
        item.location_result = None
        item.actual_location_id = None
        item.actual_location_text = None
        item.loss_reason = payload["loss_reason"]
        item.loss_description = payload.get("loss_description")
        item.borrowed_by = payload.get("borrowed_by")
        item.review_status = InventoryReviewStatus.PENDING.value
    item.submission_method = InventorySubmissionMethod.SCANNED.value
    item.submitted_by = actor_id
    item.submitted_at = now
    item.is_late = now > _aware(task.deadline_at)
    item.resolution = None
    item.resolution_reason = None
    item.resolved_by = None
    item.resolved_at = None
    item.version += 1
    _record_item_version(item, action="SUBMIT", actor_id=actor_id)
    audit_service.record_resource_change(
        action="INVENTORY_ITEM_SUBMIT",
        resource_type="inventory_item",
        resource_id=item.id,
        actor_id=actor_id,
        before_data={"status": InventoryItemStatus.PENDING.value},
        after_data={
            "status": item.status,
            "location_result": item.location_result,
            "review_status": item.review_status,
        },
    )
    db.session.commit()
    return _item_to_dict(item, task, actor_id)


def admin_mark(task_id: int, payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    task = _require_task(task_id)
    _require_manage(task, actor_id)
    if task.status != InventoryTaskStatus.IN_PROGRESS.value:
        raise BusinessException("当前任务已停止收集")
    item_ids = sorted(set(payload["item_ids"]))
    items = list(
        db.session.scalars(
            select(InventoryItem).where(
                InventoryItem.task_id == task.id,
                InventoryItem.id.in_(item_ids),
            )
        ).all()
    )
    if len(items) != len(item_ids):
        raise BusinessException("包含不属于本任务的盘点明细")
    now = _now()
    for item in items:
        if (
            item.status != InventoryItemStatus.PENDING.value
            and item.review_status != InventoryReviewStatus.RETURNED.value
        ):
            raise BusinessException(f"资产 {item.asset_code} 已提交，不能直接标记")
        item.status = InventoryItemStatus.FOUND.value
        item.physical_result = "FOUND"
        item.location_result = None
        item.actual_location_id = None
        item.actual_location_text = None
        item.submission_method = InventorySubmissionMethod.ADMIN_MARKED.value
        item.submitted_by = actor_id
        item.submitted_at = now
        item.is_late = now > _aware(task.deadline_at)
        item.review_status = InventoryReviewStatus.AUTO_CONFIRMED.value
        item.admin_mark_reason = payload["reason"]
        item.version += 1
        _record_item_version(
            item, action="ADMIN_MARK", actor_id=actor_id, reason=payload["reason"]
        )
    audit_service.record_resource_change(
        action="INVENTORY_ADMIN_MARK",
        resource_type="inventory_task",
        resource_id=task.id,
        actor_id=actor_id,
        before_data=None,
        after_data={"item_ids": item_ids},
        reason=payload["reason"],
    )
    db.session.commit()
    return _task_to_dict(task, actor_id)


def end_collection(
    task_id: int, payload: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    task = _require_task(task_id)
    _require_manage(task, actor_id)
    if task.status != InventoryTaskStatus.IN_PROGRESS.value:
        raise BusinessException("只有进行中的任务可以结束收集")
    pending_count = int(
        db.session.scalar(
            select(func.count(InventoryItem.id)).where(
                InventoryItem.task_id == task.id,
                or_(
                    InventoryItem.status == InventoryItemStatus.PENDING.value,
                    InventoryItem.review_status == InventoryReviewStatus.RETURNED.value,
                ),
            )
        )
        or 0
    )
    if payload["confirm_unsubmitted_count"] != pending_count:
        raise BusinessException("未提交资产数量已变化，请刷新后重新确认")
    now = _now()
    items = list(
        db.session.scalars(
            select(InventoryItem).where(
                InventoryItem.task_id == task.id,
                or_(
                    InventoryItem.status == InventoryItemStatus.PENDING.value,
                    InventoryItem.review_status == InventoryReviewStatus.RETURNED.value,
                ),
            )
        ).all()
    )
    for item in items:
        item.status = InventoryItemStatus.UNSUBMITTED.value
        item.physical_result = None
        item.review_status = InventoryReviewStatus.PENDING.value
        item.version += 1
        _record_item_version(item, action="END_COLLECTION", actor_id=actor_id)
    task.status = InventoryTaskStatus.REVIEWING.value
    task.collection_ended_at = now
    task.version += 1
    audit_service.record_resource_change(
        action="INVENTORY_COLLECTION_END",
        resource_type="inventory_task",
        resource_id=task.id,
        actor_id=actor_id,
        before_data={"status": InventoryTaskStatus.IN_PROGRESS.value},
        after_data={"status": task.status, "unsubmitted_count": pending_count},
    )
    db.session.commit()
    return _task_to_dict(task, actor_id)


def resolve_item(
    task_id: int, item_id: int, payload: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    task = _require_task(task_id)
    _require_manage(task, actor_id)
    if task.status != InventoryTaskStatus.REVIEWING.value:
        raise BusinessException("只有异常处理阶段可以确认盘点结果")
    item = db.session.get(InventoryItem, item_id)
    if item is None or item.task_id != task.id:
        raise BusinessException("盘点明细不存在", result_code=ResultCode.NOT_FOUND)
    resolution = payload["resolution"]
    if item.status == InventoryItemStatus.LOSS.value and resolution != "CONFIRMED_LOSS":
        raise BusinessException("盘亏资产只能确认为盘亏")
    if item.status == InventoryItemStatus.UNSUBMITTED.value and resolution not in [
        "CONFIRMED_LOSS",
        "EXEMPTED",
    ]:
        raise BusinessException("未提交资产只能确认为盘亏或无需盘点")
    if (
        item.status == InventoryItemStatus.FOUND.value
        and item.location_result
        in [
            InventoryLocationResult.DIFFERENT.value,
            InventoryLocationResult.TEMPORARY.value,
        ]
        and resolution not in ["KEEP_LEDGER_LOCATION", "LOCATION_RECORDED"]
    ):
        raise BusinessException("地点差异需要选择保留台账地点或记录现场地点")
    if resolution == "EXEMPTED":
        item.status = InventoryItemStatus.EXEMPTED.value
        item.physical_result = None
    elif resolution == "CONFIRMED_LOSS":
        item.status = InventoryItemStatus.LOSS.value
        item.physical_result = "LOSS"
    item.review_status = InventoryReviewStatus.RESOLVED.value
    item.resolution = resolution
    item.resolution_reason = payload["reason"]
    item.resolved_by = actor_id
    item.resolved_at = _now()
    item.version += 1
    _record_item_version(
        item, action="RESOLVE", actor_id=actor_id, reason=payload["reason"]
    )
    audit_service.record_resource_change(
        action="INVENTORY_EXCEPTION_RESOLVE",
        resource_type="inventory_item",
        resource_id=item.id,
        actor_id=actor_id,
        before_data=None,
        after_data={"status": item.status, "resolution": resolution},
        reason=payload["reason"],
    )
    db.session.commit()
    return _item_to_dict(item, task, actor_id)


def return_item(
    task_id: int, item_id: int, payload: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    task = _require_task(task_id)
    _require_manage(task, actor_id)
    if task.status != InventoryTaskStatus.IN_PROGRESS.value:
        raise BusinessException("只有收集中的任务可以退回盘点结果")
    item = db.session.get(InventoryItem, item_id)
    if item is None or item.task_id != task.id:
        raise BusinessException("盘点明细不存在", result_code=ResultCode.NOT_FOUND)
    if item.submission_method != InventorySubmissionMethod.SCANNED.value:
        raise BusinessException("只有员工自主提交的盘点结果可以退回")
    if item.status not in [
        InventoryItemStatus.FOUND.value,
        InventoryItemStatus.LOSS.value,
    ]:
        raise BusinessException("当前盘点结果不能退回修改")
    if item.review_status == InventoryReviewStatus.RETURNED.value:
        raise BusinessException("该盘点结果已经退回")

    before_data = {
        "status": item.status,
        "physical_result": item.physical_result,
        "location_result": item.location_result,
        "actual_location_id": item.actual_location_id,
        "actual_location_text": item.actual_location_text,
        "loss_reason": item.loss_reason,
        "loss_description": item.loss_description,
        "borrowed_by": item.borrowed_by,
        "submission_method": item.submission_method,
        "submitted_by": item.submitted_by,
        "submitted_at": item.submitted_at.isoformat() if item.submitted_at else None,
        "photo_ids": list(
            db.session.scalars(
                select(InventoryPhoto.id)
                .where(InventoryPhoto.item_id == item.id)
                .order_by(InventoryPhoto.id.asc())
            ).all()
        ),
        "version": item.version,
    }
    item.status = InventoryItemStatus.PENDING.value
    item.physical_result = None
    item.location_result = None
    item.actual_location_id = None
    item.actual_location_text = None
    item.loss_reason = None
    item.loss_description = None
    item.borrowed_by = None
    item.submission_method = None
    item.submitted_by = None
    item.submitted_at = None
    item.is_late = False
    item.review_status = InventoryReviewStatus.RETURNED.value
    item.resolution = "RETURNED"
    item.resolution_reason = payload["reason"]
    item.resolved_by = actor_id
    item.resolved_at = _now()
    item.admin_mark_reason = None
    item.version += 1
    _record_item_version(
        item, action="RETURN", actor_id=actor_id, reason=payload["reason"]
    )
    audit_service.record_resource_change(
        action="INVENTORY_ITEM_RETURN",
        resource_type="inventory_item",
        resource_id=item.id,
        actor_id=actor_id,
        before_data=before_data,
        after_data={"status": item.status, "review_status": item.review_status},
        reason=payload["reason"],
    )
    db.session.commit()
    return _item_to_dict(item, task, actor_id)


def reopen_items(
    task_id: int, payload: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    task = _require_task(task_id)
    _require_manage(task, actor_id)
    if task.status != InventoryTaskStatus.REVIEWING.value:
        raise BusinessException("只有异常处理中的任务可以重新开放")
    deadline = _aware(payload["deadline_at"])
    if deadline <= _now():
        raise BusinessException("新的截止时间必须晚于当前时间")
    item_ids = sorted(set(payload["item_ids"]))
    items = list(
        db.session.scalars(
            select(InventoryItem).where(
                InventoryItem.task_id == task.id,
                InventoryItem.id.in_(item_ids),
            )
        ).all()
    )
    if len(items) != len(item_ids):
        raise BusinessException("包含不属于本任务的盘点明细")
    for item in items:
        if item.status not in [
            InventoryItemStatus.UNSUBMITTED.value,
            InventoryItemStatus.LOSS.value,
        ]:
            raise BusinessException(f"资产 {item.asset_code} 当前结果不能重新开放")
        item.status = InventoryItemStatus.PENDING.value
        item.physical_result = None
        item.location_result = None
        item.actual_location_id = None
        item.actual_location_text = None
        item.loss_reason = None
        item.loss_description = None
        item.borrowed_by = None
        item.submission_method = None
        item.submitted_by = None
        item.submitted_at = None
        item.is_late = False
        item.review_status = InventoryReviewStatus.NONE.value
        item.resolution = None
        item.resolution_reason = None
        item.resolved_by = None
        item.resolved_at = None
        item.version += 1
        _record_item_version(
            item, action="REOPEN", actor_id=actor_id, reason=payload["reason"]
        )
    task.status = InventoryTaskStatus.IN_PROGRESS.value
    task.deadline_at = deadline
    task.collection_ended_at = None
    task.version += 1
    audit_service.record_resource_change(
        action="INVENTORY_ITEMS_REOPEN",
        resource_type="inventory_task",
        resource_id=task.id,
        actor_id=actor_id,
        before_data={"status": InventoryTaskStatus.REVIEWING.value},
        after_data={
            "status": task.status,
            "item_ids": item_ids,
            "deadline_at": deadline.isoformat(),
        },
        reason=payload["reason"],
    )
    db.session.commit()
    return _task_to_dict(task, actor_id)


def complete_task(task_id: int, actor_id: int) -> dict[str, Any]:
    task = _require_task(task_id)
    _require_manage(task, actor_id)
    if task.status != InventoryTaskStatus.REVIEWING.value:
        raise BusinessException("只有异常处理中的任务可以完成")
    unresolved = int(
        db.session.scalar(
            select(func.count(InventoryItem.id)).where(
                InventoryItem.task_id == task.id,
                InventoryItem.review_status.in_(
                    [
                        InventoryReviewStatus.PENDING.value,
                        InventoryReviewStatus.RETURNED.value,
                    ]
                ),
            )
        )
        or 0
    )
    if unresolved:
        raise BusinessException(f"仍有 {unresolved} 条异常未处理，不能完成盘点")
    task.status = InventoryTaskStatus.COMPLETED.value
    task.completed_at = _now()
    task.version += 1
    _record_inventory_lifecycle_rows(task, actor_id)
    audit_service.record_resource_change(
        action="INVENTORY_TASK_COMPLETE",
        resource_type="inventory_task",
        resource_id=task.id,
        actor_id=actor_id,
        before_data={"status": InventoryTaskStatus.REVIEWING.value},
        after_data={"status": task.status, **_task_counts(task.id)},
    )
    db.session.commit()
    return _task_to_dict(task, actor_id)


def cancel_task(task_id: int, payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    task = _require_task(task_id)
    _require_manage(task, actor_id)
    if task.status == InventoryTaskStatus.COMPLETED.value:
        raise BusinessException("已完成任务不能取消")
    if task.status == InventoryTaskStatus.CANCELLED.value:
        raise BusinessException("任务已经取消")
    before_status = task.status
    task.status = InventoryTaskStatus.CANCELLED.value
    task.cancelled_at = _now()
    task.cancel_reason = payload["reason"]
    task.version += 1
    audit_service.record_resource_change(
        action="INVENTORY_TASK_CANCEL",
        resource_type="inventory_task",
        resource_id=task.id,
        actor_id=actor_id,
        before_data={"status": before_status},
        after_data={"status": task.status},
        reason=payload["reason"],
    )
    db.session.commit()
    return _task_to_dict(task, actor_id)


def update_admins(
    task_id: int, payload: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    task = _require_task(task_id)
    _require_manage(task, actor_id)
    if task.status in [
        InventoryTaskStatus.COMPLETED.value,
        InventoryTaskStatus.CANCELLED.value,
    ]:
        raise BusinessException("已结束任务不能调整盘点管理员")
    admin_ids = sorted(set(payload["admin_user_ids"]))
    _validate_enabled_users(admin_ids)
    before = _task_admin_ids(task.id)
    db.session.query(InventoryTaskAdmin).filter(
        InventoryTaskAdmin.task_id == task.id
    ).delete()
    db.session.add_all(
        [InventoryTaskAdmin(task_id=task.id, user_id=user_id) for user_id in admin_ids]
    )
    task.version += 1
    audit_service.record_resource_change(
        action="INVENTORY_ADMINS_UPDATE",
        resource_type="inventory_task",
        resource_id=task.id,
        actor_id=actor_id,
        before_data={"admin_user_ids": before},
        after_data={"admin_user_ids": admin_ids},
        reason=payload["reason"],
    )
    db.session.commit()
    return _task_to_dict(task, actor_id)


def update_deadline(
    task_id: int, payload: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    task = _require_task(task_id)
    _require_manage(task, actor_id)
    if task.status != InventoryTaskStatus.IN_PROGRESS.value:
        raise BusinessException("只有收集中的任务可以调整截止时间")
    deadline = _aware(payload["deadline_at"])
    if deadline <= _now():
        raise BusinessException("新的截止时间必须晚于当前时间")
    before = task.deadline_at
    task.deadline_at = deadline
    task.version += 1
    audit_service.record_resource_change(
        action="INVENTORY_DEADLINE_UPDATE",
        resource_type="inventory_task",
        resource_id=task.id,
        actor_id=actor_id,
        before_data={"deadline_at": before.isoformat()},
        after_data={"deadline_at": deadline.isoformat()},
        reason=payload["reason"],
    )
    db.session.commit()
    return _task_to_dict(task, actor_id)


def withdraw_item(
    task_id: int, item_id: int, payload: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    task = _require_task(task_id)
    if task.status != InventoryTaskStatus.IN_PROGRESS.value:
        raise BusinessException("当前任务已停止收集，不能撤回")
    item = db.session.get(InventoryItem, item_id)
    if item is None or item.task_id != task.id:
        raise BusinessException("盘点明细不存在", result_code=ResultCode.NOT_FOUND)
    if item.responsible_user_id != actor_id:
        raise BusinessException(
            "只能撤回本人提交的盘点结果", result_code=ResultCode.FORBIDDEN
        )
    if (
        item.submission_method != InventorySubmissionMethod.SCANNED.value
        or item.submitted_by != actor_id
    ):
        raise BusinessException("只有本人真实扫码提交的结果可以撤回")
    if item.status not in [
        InventoryItemStatus.FOUND.value,
        InventoryItemStatus.LOSS.value,
    ]:
        raise BusinessException("当前结果不能撤回")
    item.status = InventoryItemStatus.PENDING.value
    item.physical_result = None
    item.location_result = None
    item.actual_location_id = None
    item.actual_location_text = None
    item.loss_reason = None
    item.loss_description = None
    item.borrowed_by = None
    item.submission_method = None
    item.submitted_by = None
    item.submitted_at = None
    item.is_late = False
    item.review_status = InventoryReviewStatus.NONE.value
    item.resolution = None
    item.resolution_reason = None
    item.version += 1
    _record_item_version(
        item, action="WITHDRAW", actor_id=actor_id, reason=payload["reason"]
    )
    audit_service.record_resource_change(
        action="INVENTORY_ITEM_WITHDRAW",
        resource_type="inventory_item",
        resource_id=item.id,
        actor_id=actor_id,
        before_data=None,
        after_data={"status": item.status},
        reason=payload["reason"],
    )
    db.session.commit()
    return _item_to_dict(item, task, actor_id)


def transfer_responsibility(
    task_id: int, item_id: int, payload: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    task = _require_task(task_id)
    _require_manage(task, actor_id)
    if task.status not in [
        InventoryTaskStatus.DRAFT.value,
        InventoryTaskStatus.IN_PROGRESS.value,
    ]:
        raise BusinessException("当前阶段不能转交盘点责任")
    item = db.session.get(InventoryItem, item_id)
    if item is None or item.task_id != task.id:
        raise BusinessException("盘点明细不存在", result_code=ResultCode.NOT_FOUND)
    new_user_id = payload["responsible_user_id"]
    _validate_enabled_users([new_user_id])
    before = item.responsible_user_id
    item.responsible_user_id = new_user_id
    item.version += 1
    _record_item_version(
        item,
        action="RESPONSIBILITY_TRANSFER",
        actor_id=actor_id,
        reason=payload["reason"],
    )
    audit_service.record_resource_change(
        action="INVENTORY_RESPONSIBILITY_TRANSFER",
        resource_type="inventory_item",
        resource_id=item.id,
        actor_id=actor_id,
        before_data={"responsible_user_id": before},
        after_data={"responsible_user_id": new_user_id},
        reason=payload["reason"],
    )
    db.session.commit()
    return _item_to_dict(item, task, actor_id)


def resolve_surplus(
    task_id: int, event_id: int, payload: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    task = _require_task(task_id)
    _require_manage(task, actor_id)
    event = db.session.get(InventoryScanEvent, event_id)
    if event is None or event.task_id != task.id:
        raise BusinessException("扫码异常记录不存在", result_code=ResultCode.NOT_FOUND)
    if event.outcome not in ["OUTSIDE_SCOPE", "UNKNOWN_ASSET"]:
        raise BusinessException("只有任务外资产或未知资产可以进行盘盈决策")
    event.resolution = payload["resolution"]
    event.resolution_reason = payload["reason"]
    event.resolved_by = actor_id
    event.resolved_at = _now()
    audit_service.record_resource_change(
        action="INVENTORY_SURPLUS_RESOLVE",
        resource_type="inventory_scan_event",
        resource_id=event.id,
        actor_id=actor_id,
        before_data=None,
        after_data={"resolution": event.resolution},
        reason=payload["reason"],
    )
    db.session.commit()
    return {
        "id": event.id,
        "resolution": event.resolution,
        "resolution_reason": event.resolution_reason,
    }


def send_reminders(
    task_id: int, payload: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    task = _require_task(task_id)
    _require_manage(task, actor_id)
    if task.status != InventoryTaskStatus.IN_PROGRESS.value:
        raise BusinessException("只有收集中的任务可以催办")
    pending_users = set(
        db.session.scalars(
            select(InventoryItem.responsible_user_id).where(
                InventoryItem.task_id == task.id,
                or_(
                    InventoryItem.status == InventoryItemStatus.PENDING.value,
                    InventoryItem.review_status == InventoryReviewStatus.RETURNED.value,
                ),
            )
        ).all()
    )
    requested = set(payload.get("recipient_user_ids") or [])
    recipients = sorted(pending_users if not requested else pending_users & requested)
    if not recipients:
        raise BusinessException("没有符合条件的待催办人员")
    now = _now()
    batch_no = f"REM{now.strftime('%Y%m%d%H%M%S')}{uuid4().hex[:6].upper()}"
    message = (
        payload.get("message") or f"盘点任务“{task.name}”尚未完成，请在截止时间前提交。"
    )
    db.session.add_all(
        [
            InventoryReminder(
                task_id=task.id,
                recipient_user_id=user_id,
                sent_by=actor_id,
                batch_no=batch_no,
                channel="LOCAL_FEISHU",
                status="QUEUED",
                message=message,
                sent_at=now,
            )
            for user_id in recipients
        ]
    )
    audit_service.record_resource_change(
        action="INVENTORY_REMINDER_SEND",
        resource_type="inventory_task",
        resource_id=task.id,
        actor_id=actor_id,
        before_data=None,
        after_data={
            "batch_no": batch_no,
            "recipient_user_ids": recipients,
            "channel": "LOCAL_FEISHU",
        },
    )
    db.session.commit()
    return {
        "batch_no": batch_no,
        "recipient_count": len(recipients),
        "channel": "LOCAL_FEISHU",
        "status": "QUEUED",
    }


def list_result_versions(
    task_id: int, item_id: int, actor_id: int
) -> list[dict[str, Any]]:
    task = _require_task(task_id)
    _require_view(task, actor_id)
    item = db.session.get(InventoryItem, item_id)
    if item is None or item.task_id != task.id:
        raise BusinessException("盘点明细不存在", result_code=ResultCode.NOT_FOUND)
    if not _can_manage(task.id, actor_id) and item.responsible_user_id != actor_id:
        raise BusinessException("无权查看结果版本", result_code=ResultCode.FORBIDDEN)
    versions = list(
        db.session.scalars(
            select(InventoryResultVersion)
            .where(InventoryResultVersion.item_id == item.id)
            .order_by(InventoryResultVersion.version_no.desc())
        ).all()
    )
    users = {
        user.id: user
        for user in db.session.scalars(
            select(User).where(
                User.id.in_({version.changed_by for version in versions})
            )
        ).all()
    }
    return [
        {
            "id": version.id,
            "version_no": version.version_no,
            "action": version.action,
            "reason": version.reason,
            "changed_by": version.changed_by,
            "changed_by_name": _user_name(users.get(version.changed_by)),
            "snapshot": version.snapshot,
            "created_at": _iso(version.created_at),
        }
        for version in versions
    ]


def build_report(task_id: int, actor_id: int) -> tuple[BytesIO, str]:
    task = _require_task(task_id)
    if not _can_manage(task.id, actor_id):
        permission_service.require_permission(actor_id, "inventory:export")
        _require_view(task, actor_id)
    items = list(
        db.session.scalars(
            select(InventoryItem)
            .where(InventoryItem.task_id == task.id)
            .order_by(InventoryItem.asset_code.asc())
        ).all()
    )
    header = [
        "资产编码",
        "资产名称",
        "所属组织",
        "分类",
        "责任人ID",
        "台账地点",
        "现场地点",
        "实物结果",
        "地点差异",
        "提交方式",
        "是否逾期",
        "复核状态",
        "处理结果",
        "照片数量",
    ]

    def row(item: InventoryItem) -> list[Any]:
        photo_count = int(
            db.session.scalar(
                select(func.count(InventoryPhoto.id)).where(
                    InventoryPhoto.item_id == item.id
                )
            )
            or 0
        )
        return [
            item.asset_code,
            item.asset_name,
            item.organization_name,
            item.category_name,
            item.responsible_user_id,
            item.ledger_location_name,
            item.actual_location_text,
            item.physical_result,
            item.location_result,
            item.submission_method,
            "是" if item.is_late else "否",
            item.review_status,
            item.resolution,
            photo_count,
        ]

    summary = [
        ["盘点任务", task.name],
        ["任务编号", task.task_no],
        ["状态", _effective_status(task)],
        ["截止时间", task.deadline_at],
        ["资产总数", len(items)],
    ] + [[key, value] for key, value in _task_counts(task.id).items()]
    people: dict[int, list[int]] = {}
    for item in items:
        values = people.setdefault(item.responsible_user_id, [0, 0])
        values[0] += 1
        values[1] += item.status != InventoryItemStatus.PENDING.value
    sheets = [
        ("盘点汇总", summary),
        ("资产明细", [header] + [row(item) for item in items]),
        (
            "盘亏",
            [header]
            + [
                row(item)
                for item in items
                if item.status == InventoryItemStatus.LOSS.value
            ],
        ),
        (
            "地点差异",
            [header]
            + [
                row(item)
                for item in items
                if item.location_result == InventoryLocationResult.DIFFERENT.value
            ],
        ),
        (
            "临时地点",
            [header]
            + [
                row(item)
                for item in items
                if item.location_result == InventoryLocationResult.TEMPORARY.value
            ],
        ),
        (
            "未完成",
            [header]
            + [
                row(item)
                for item in items
                if item.status
                in [
                    InventoryItemStatus.PENDING.value,
                    InventoryItemStatus.UNSUBMITTED.value,
                ]
            ],
        ),
        (
            "无需盘点",
            [header]
            + [
                row(item)
                for item in items
                if item.status == InventoryItemStatus.EXEMPTED.value
            ],
        ),
        (
            "管理员代确认",
            [header]
            + [
                row(item)
                for item in items
                if item.submission_method
                == InventorySubmissionMethod.ADMIN_MARKED.value
            ],
        ),
        (
            "人员完成情况",
            [["责任人ID", "应盘数量", "已处理数量", "完成率"]]
            + [
                [
                    user_id,
                    values[0],
                    values[1],
                    f"{round(values[1] * 100 / values[0], 1)}%",
                ]
                for user_id, values in people.items()
            ],
        ),
    ]
    content = build_workbook(sheets)
    audit_service.record_resource_change(
        action="INVENTORY_REPORT_EXPORT",
        resource_type="inventory_task",
        resource_id=task.id,
        actor_id=actor_id,
        before_data=None,
        after_data={"file_name": f"{task.task_no}.xlsx"},
    )
    db.session.commit()
    return BytesIO(content), f"{task.task_no}-盘点报告.xlsx"


def overview(actor_id: int) -> dict[str, Any]:
    page = list_tasks(actor_id=actor_id, page_index=0, size=100, status=None)
    tasks = page.items
    active = [
        task
        for task in tasks
        if task["status"] in ["IN_PROGRESS", "OVERDUE", "REVIEWING"]
    ]
    total_assets = sum(int(task["counts"]["total"]) for task in active)
    checked_assets = sum(int(task["counts"]["checked"]) for task in active)
    pending_assets = sum(int(task["counts"]["pending"]) for task in active)
    exceptions = sum(int(task["counts"]["exceptions"]) for task in active)
    completion_rate = (
        round(checked_assets * 100 / total_assets, 1) if total_assets else 0.0
    )
    next_deadline = min((task["deadline_at"] for task in active), default=None)
    return {
        "active_tasks": len(active),
        "pending_assets": pending_assets,
        "exception_items": exceptions,
        "completion_rate": completion_rate,
        "checked_assets": checked_assets,
        "total_assets": total_assets,
        "next_deadline": next_deadline,
    }


__all__ = [
    "admin_mark",
    "cancel_task",
    "complete_task",
    "create_task",
    "end_collection",
    "get_photo",
    "get_task",
    "list_items",
    "list_my_pending_items",
    "list_tasks",
    "overview",
    "publish_task",
    "reopen_items",
    "resolve_item",
    "scan",
    "submit_item",
    "upload_photo",
]
