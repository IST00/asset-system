"""Formal asset creation and query use cases."""

from __future__ import annotations

from copy import deepcopy
from collections.abc import Mapping, Sequence
import json
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import aliased

from app.common import BusinessException, PageResult, ResultCode
from app.enums import (
    ApprovalStatus,
    AssetCodeStatus,
    AssetDataCompleteness,
    AssetStatus,
    ExecutionStatus,
)
from app.extensions import db
from app.models import (
    ApprovalStep,
    ApprovalTask,
    Asset,
    AssetCategory,
    AssetLifecycleRecord,
    AssetLocation,
    PublicUsageObject,
    AssetSource,
    InventoryItem,
    InventoryTask,
    OperationRequest,
    OperationRequestAsset,
    Organization,
    Supplier,
    Unit,
    User,
)
from app.repositories import (
    QuerySpec,
    asset_code_reservation_repository,
    asset_lifecycle_repository,
    asset_repository,
    operation_log_repository,
)
from app.repositories.workflow_repository import (
    operation_request_repository,
    stock_in_item_repository,
    stock_in_request_repository,
)
from app.services import (
    asset_access_service,
    asset_code_service,
    asset_data_service,
    audit_service,
    permission_service,
)


def stock_in_request(operation_request_id: int, actor_id: int) -> None:
    operation = operation_request_repository.get(operation_request_id)
    if operation is None:
        raise BusinessException("入库申请不存在", result_code=ResultCode.NOT_FOUND)
    if operation.approval_status != ApprovalStatus.APPROVED.value:
        raise BusinessException("申请尚未审批通过")
    if operation.execution_status == ExecutionStatus.SUCCESS.value:
        return
    stock_in = stock_in_request_repository.find_by_operation(operation.id)
    if stock_in is None:
        raise BusinessException("入库申请明细不存在")
    items = stock_in_item_repository.find_by_request(stock_in.id)
    reservations = {
        item.stock_in_item_id: item
        for item in asset_code_reservation_repository.find_by_request(operation.id)
    }
    if len(items) != len(reservations):
        raise BusinessException("资产编码占用记录不完整")

    for item in items:
        reservation = reservations[item.id]
        if reservation.status == AssetCodeStatus.ACTIVE.value:
            continue
        if reservation.status != AssetCodeStatus.PENDING_STOCK_IN.value:
            raise BusinessException("资产编码状态不允许入库")
        if asset_repository.find_by_code(item.asset_code) is not None:
            raise BusinessException("资产编码已存在")
        if item.normalized_serial and asset_repository.find_by_normalized_serial(
            item.normalized_serial
        ):
            raise BusinessException("设备序列号已存在")
        if item.rfid_tag and asset_repository.find_by_rfid_tag(item.rfid_tag):
            raise BusinessException("RFID 标签已存在")
        asset = Asset(
            asset_code=item.asset_code,
            asset_name=item.asset_name,
            status=AssetStatus.IDLE.value,
            organization_id=stock_in.organization_id,
            usage_company_id=item.usage_company_id,
            usage_department_id=item.usage_department_id,
            holder_user_id=item.holder_user_id,
            category_id=item.category_id,
            unit_id=item.unit_id,
            original_amount=item.original_amount,
            zero_amount_reason=item.zero_amount_reason,
            purchase_date=item.purchase_date,
            supplier_id=item.supplier_id,
            service_life_months=item.service_life_months,
            expected_expiry_date=item.expected_expiry_date,
            manager_id=item.manager_id,
            source_id=item.source_id,
            location_id=item.location_id,
            specification_model=item.specification_model,
            serial_number=item.serial_number,
            normalized_serial=item.normalized_serial,
            receipt_no=item.receipt_no,
            rfid_tag=item.rfid_tag,
            remark=item.remark,
            custom_attributes=deepcopy(item.custom_attributes),
            data_completeness=AssetDataCompleteness.COMPLETE.value,
            created_from_request_id=operation.id,
        )
        asset_repository.add(asset)
        asset_code_service.activate(reservation.id, asset.id)
        audit_service.record_asset_stock_in(
            asset_id=asset.id,
            request_no=operation.request_no,
            actor_id=actor_id,
            after_data={
                "asset_code": asset.asset_code,
                "asset_name": asset.asset_name,
                "status": asset.status,
                "organization_id": asset.organization_id,
                "usage_company_id": asset.usage_company_id,
                "usage_department_id": asset.usage_department_id,
                "holder_user_id": asset.holder_user_id,
                "original_amount": str(asset.original_amount),
            },
        )
    stock_in_item_repository.release_identifier_reservations(stock_in.id)


def _entity_name(model: type[Any], entity_id: int | None) -> str | None:
    if entity_id is None:
        return None
    entity = db.session.get(model, entity_id)
    if entity is None:
        return None
    if isinstance(entity, User):
        return entity.nickname or entity.username
    if isinstance(entity, Asset):
        return entity.asset_name or entity.asset_code
    return str(entity.name)


_LIFECYCLE_FIELD_LABELS: dict[str, tuple[str, type[Any] | None]] = {
    "asset_name": ("资产名称", None),
    "status": ("资产状态", None),
    "usage_type": ("使用类型", None),
    "organization_id": ("所属公司", Organization),
    "usage_company_id": ("使用公司", Organization),
    "usage_department_id": ("使用部门", Organization),
    "holder_user_id": ("使用人", User),
    "manager_id": ("责任管理员", User),
    "public_object_id": ("公共使用对象", PublicUsageObject),
    "category_id": ("资产分类", AssetCategory),
    "unit_id": ("计量单位", Unit),
    "supplier_id": ("供应商", Supplier),
    "source_id": ("资产来源", AssetSource),
    "location_id": ("存放地点", AssetLocation),
    "specification_model": ("规格型号", None),
    "serial_number": ("序列号", None),
    "receipt_no": ("收货单号", None),
    "rfid_tag": ("RFID", None),
    "remark": ("备注", None),
    "original_amount": ("金额", None),
    "zero_amount_reason": ("零金额原因", None),
    "purchase_date": ("购入日期", None),
    "service_life_months": ("使用期限（月）", None),
    "warranty_supplier_id": ("保修供应商", Supplier),
    "warranty_contact": ("保修联系人", None),
    "warranty_phone": ("保修电话", None),
    "warranty_expiry_date": ("保修到期日", None),
    "warranty_description": ("保修说明", None),
    "parent_asset_id": ("主资产", Asset),
    "data_completeness": ("资料完整状态", None),
    "return_condition": ("归还状况", None),
    "condition_description": ("状况说明", None),
}

_ASSET_STATUS_LABELS = {
    "IDLE": "闲置",
    "PENDING_RECEIPT": "领用待确认",
    "IN_USE": "在用",
    "REPAIRING": "维修中",
    "SCRAPPED": "已报废",
}
_USAGE_TYPE_LABELS = {"PERSONAL": "个人", "PUBLIC": "公共"}
_DATA_COMPLETENESS_LABELS = {"COMPLETE": "资料完整", "INCOMPLETE": "资料待补充"}
_INVENTORY_STATUS_LABELS = {
    "FOUND": "正常",
    "LOSS": "盘亏",
    "EXEMPTED": "无需盘点",
    "UNSUBMITTED": "未提交",
}


def _plain_value(value: Any) -> Any:
    if value is None or value == "":
        return None
    return value


def _lifecycle_field_value(field: str, value: Any) -> str:
    normalized = _plain_value(value)
    if normalized is None:
        return "<空>"
    if field == "status" and isinstance(normalized, str):
        return _ASSET_STATUS_LABELS.get(normalized, normalized)
    if field == "usage_type" and isinstance(normalized, str):
        return _USAGE_TYPE_LABELS.get(normalized, normalized)
    if field in {"data_completeness"} and isinstance(normalized, str):
        return _DATA_COMPLETENESS_LABELS.get(normalized, normalized)
    if isinstance(normalized, int):
        model = _LIFECYCLE_FIELD_LABELS[field][1]
        if model is not None:
            return _entity_name(model, normalized) or f"#{normalized}"
    if isinstance(normalized, (dict, list)):
        return json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    return str(normalized)


def _users_by_ids(user_ids: set[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    rows = db.session.scalars(select(User).where(User.id.in_(user_ids))).all()
    return {user.id: user.nickname or user.username for user in rows}


def _format_lifecycle_changes(
    before: Mapping[str, Any] | None, after: Mapping[str, Any] | None
) -> list[str]:
    if before is None or after is None:
        return []
    fields = [field for field in after if field in _LIFECYCLE_FIELD_LABELS]
    return [
        f"【{_LIFECYCLE_FIELD_LABELS[field][0]}】字段由"
        f"【{_lifecycle_field_value(field, before.get(field))}】变更为"
        f"【{_lifecycle_field_value(field, after.get(field))}】"
        for field in fields
        if not (
            field in before
            and _plain_value(before[field]) == _plain_value(after[field])
        )
        or field not in before
    ]


def _lifecycle_change_summary(record: AssetLifecycleRecord) -> str:
    before = record.before_data if isinstance(record.before_data, Mapping) else None
    after = record.after_data if isinstance(record.after_data, Mapping) else None

    if record.operation_type == "INVENTORY_PROCESS":
        task_no = (after or {}).get("task_no") if after is not None else None
        task_name = (after or {}).get("task_name") if after is not None else None
        status = (after or {}).get("status") if after is not None else None
        status_label = (
            _INVENTORY_STATUS_LABELS.get(status, str(status))
            if status is not None
            else "未知"
        )
        return (
            f"盘点单号: {task_no or record.operation_no}（{status_label}）; "
            f"盘点单名称: {task_name or '未命名盘点'}"
        )

    if record.operation_type == "STOCK_IN":
        values = after or {}
        organization_id = values.get("organization_id")
        organization_name = (
            _entity_name(Organization, organization_id)
            if isinstance(organization_id, int)
            else None
        ) or "未指定公司"
        department_id = values.get("usage_department_id")
        department_name = (
            _entity_name(Organization, department_id)
            if isinstance(department_id, int)
            else None
        ) or "未指定部门"
        amount = values.get("original_amount", "0.00")
        import_type = values.get("import_type")
        suffix = "（历史导入）" if import_type == "HISTORICAL_IMPORT" else ""
        return (
            f"入账到 “{organization_name}” 公司，“{department_name}” 部门，"
            f"金额：{amount}{suffix}"
        )

    changes = _format_lifecycle_changes(before, after)
    if record.operation_type == "PERSONAL_USE" and record.remark == "员工签收":
        return "签字"
    if changes:
        change_text = ";".join(changes)
        if record.remark:
            return f"{change_text}；原因：{record.remark}"
        return change_text
    return record.remark or "该操作未记录变更明细"


def _serialize(asset: Asset, include_amount: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": asset.id,
        "asset_code": asset.asset_code,
        "asset_name": asset.asset_name,
        "status": asset.status,
        "version": asset.version,
        "organization_id": asset.organization_id,
        "usage_company_id": asset.usage_company_id,
        "usage_company_name": _entity_name(Organization, asset.usage_company_id),
        "company_name": _entity_name(Organization, asset.organization_id),
        "category_id": asset.category_id,
        "category_name": _entity_name(AssetCategory, asset.category_id),
        "unit_id": asset.unit_id,
        "unit_name": _entity_name(Unit, asset.unit_id),
        "supplier_id": asset.supplier_id,
        "supplier_name": _entity_name(Supplier, asset.supplier_id),
        "purchase_date": asset.purchase_date.isoformat(),
        "service_life_months": asset.service_life_months,
        "expected_expiry_date": asset.expected_expiry_date.isoformat(),
        "manager_id": asset.manager_id,
        "manager_name": _entity_name(User, asset.manager_id),
        "holder_user_id": asset.holder_user_id,
        "user_name": _entity_name(User, asset.holder_user_id),
        "usage_department_id": asset.usage_department_id,
        "department_name": _entity_name(Organization, asset.usage_department_id),
        "usage_department_name": _entity_name(Organization, asset.usage_department_id),
        "source_id": asset.source_id,
        "source_name": _entity_name(AssetSource, asset.source_id),
        "location_id": asset.location_id,
        "location_name": _entity_name(AssetLocation, asset.location_id),
        "specification_model": asset.specification_model,
        "model": asset.specification_model,
        "serial_number": asset.serial_number,
        "receipt_no": asset.receipt_no,
        "receipt_number": asset.receipt_no,
        "rfid_tag": asset.rfid_tag,
        "parent_asset_id": asset.parent_asset_id,
        "usage_type": asset.usage_type,
        "public_object_id": asset.public_object_id,
        "remark": asset.remark,
        "custom_attributes": dict(asset.custom_attributes),
        "data_completeness": asset.data_completeness,
        "information_complete": asset.data_completeness
        == AssetDataCompleteness.COMPLETE.value,
        "missing_fields": asset_data_service.missing_fields(
            asset.unit_id, asset.source_id, asset.location_id
        ),
        "created_at": asset.created_at,
        "updated_at": asset.updated_at,
    }
    if include_amount:
        result["original_amount"] = f"{asset.original_amount:.2f}"
        result["purchase_amount"] = float(asset.original_amount)
        result["zero_amount_reason"] = asset.zero_amount_reason
    return result


def _month_start(value: datetime, offset: int = 0) -> datetime:
    month_index = value.year * 12 + value.month - 1 + offset
    year, month_zero = divmod(month_index, 12)
    return datetime(year, month_zero + 1, 1, tzinfo=timezone.utc)


def dashboard(actor_id: int) -> dict[str, Any]:
    """Return real-time dashboard aggregates within the actor's data scope."""
    permission_service.require_permission(actor_id, "asset:view")
    access = asset_access_service.access_filter(actor_id)

    status_counts = {
        str(status): int(count)
        for status, count in db.session.execute(
            select(Asset.status, func.count(Asset.id))
            .where(access)
            .group_by(Asset.status)
        ).all()
    }
    total = sum(status_counts.values())

    category_rows = db.session.execute(
        select(AssetCategory.name, func.count(Asset.id))
        .join(Asset, Asset.category_id == AssetCategory.id)
        .where(access)
        .group_by(AssetCategory.id, AssetCategory.name)
        .order_by(func.count(Asset.id).desc(), AssetCategory.id.asc())
    ).all()

    incomplete_assets = int(
        db.session.scalar(
            select(func.count(Asset.id)).where(
                access,
                Asset.data_completeness == AssetDataCompleteness.INCOMPLETE.value,
            )
        )
        or 0
    )
    holder = aliased(User)
    departed_owner_assets = int(
        db.session.scalar(
            select(func.count(Asset.id))
            .outerjoin(holder, holder.id == Asset.holder_user_id)
            .where(access, Asset.holder_user_id.is_not(None), holder.enabled.is_(False))
        )
        or 0
    )
    pending_approvals = 0
    if permission_service.has_permission(actor_id, "approval:task:view"):
        pending_approvals = int(
            db.session.scalar(
                select(func.count(ApprovalTask.id)).where(
                    ApprovalTask.approver_id == actor_id,
                    ApprovalTask.status == "PENDING",
                )
            )
            or 0
        )

    current_month = _month_start(datetime.now(tz=timezone.utc))
    month_starts = [_month_start(current_month, offset) for offset in range(-5, 1)]
    month_keys = [item.strftime("%Y-%m") for item in month_starts]
    intake_counts = dict.fromkeys(month_keys, 0)
    scrapped_counts = dict.fromkeys(month_keys, 0)

    intake_dates = db.session.scalars(
        select(Asset.created_at).where(access, Asset.created_at >= month_starts[0])
    ).all()
    for created_at in intake_dates:
        key = created_at.strftime("%Y-%m")
        if key in intake_counts:
            intake_counts[key] += 1

    lifecycle_rows = db.session.execute(
        select(AssetLifecycleRecord.created_at, AssetLifecycleRecord.after_data)
        .join(Asset, Asset.id == AssetLifecycleRecord.asset_id)
        .where(access, AssetLifecycleRecord.created_at >= month_starts[0])
    ).all()
    for created_at, after_data in lifecycle_rows:
        if not isinstance(after_data, dict):
            continue
        if after_data.get("status") != AssetStatus.SCRAPPED.value:
            continue
        key = created_at.strftime("%Y-%m")
        if key in scrapped_counts:
            scrapped_counts[key] += 1

    inventory_overview: dict[str, Any] = {
        "exception_items": 0,
        "checked_assets": 0,
        "total_assets": 0,
    }
    inventory_task_name = "暂无进行中的盘点任务"
    if permission_service.has_permission(actor_id, "inventory:view"):
        from app.services import inventory_service

        inventory_overview = inventory_service.overview(actor_id)
        inventory_tasks = inventory_service.list_tasks(
            actor_id=actor_id, page_index=0, size=20
        ).items
        active_task = next(
            (
                item
                for item in inventory_tasks
                if item["status"] in ["IN_PROGRESS", "OVERDUE", "REVIEWING"]
            ),
            None,
        )
        if active_task is not None:
            inventory_task_name = str(active_task["name"])

    return {
        "metrics": {
            "total": total,
            "idle": status_counts.get(AssetStatus.IDLE.value, 0),
            "in_use": status_counts.get(AssetStatus.IN_USE.value, 0),
            "repairing": status_counts.get(AssetStatus.REPAIRING.value, 0),
            "scrapped": status_counts.get(AssetStatus.SCRAPPED.value, 0),
        },
        "issues": {
            "pending_approvals": pending_approvals,
            "inventory_exceptions": int(inventory_overview["exception_items"]),
            "incomplete_assets": incomplete_assets,
            "departed_owner_assets": departed_owner_assets,
        },
        "inventory": {
            "task_name": inventory_task_name,
            "checked": int(inventory_overview["checked_assets"]),
            "total": int(inventory_overview["total_assets"]),
            "exceptions": int(inventory_overview["exception_items"]),
        },
        "categories": [
            {"name": str(name), "value": int(count)} for name, count in category_rows
        ],
        "statuses": [
            {"status": status.value, "value": status_counts.get(status.value, 0)}
            for status in AssetStatus
        ],
        "monthly_changes": [
            {
                "month": key,
                "intake": intake_counts[key],
                "scrapped": scrapped_counts[key],
            }
            for key in month_keys
        ],
    }


def _normalized_text(value: object | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _name_ids(model: type[Any], value: str) -> Any:
    return select(model.id).where(model.name == value)


def _user_name_ids(value: str) -> Any:
    return select(User.id).where(or_(User.nickname == value, User.username == value))


def _build_asset_filters(
    *, actor_id: int, filters: Mapping[str, object | None]
) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [
        asset_access_service.access_filter(actor_id)
    ]
    keyword = _normalized_text(filters.get("keyword"))
    if keyword:
        conditions.append(
            or_(
                Asset.asset_code.contains(keyword, autoescape=True),
                Asset.asset_name.contains(keyword, autoescape=True),
                Asset.serial_number.contains(keyword, autoescape=True),
                Asset.receipt_no.contains(keyword, autoescape=True),
                Asset.rfid_tag.contains(keyword, autoescape=True),
            )
        )
    asset_code = _normalized_text(filters.get("asset_code"))
    if asset_code:
        conditions.append(Asset.asset_code == asset_code)
    raw_codes = filters.get("asset_codes")
    asset_codes: list[str] = []
    if isinstance(raw_codes, str):
        asset_codes = [item.strip() for item in raw_codes.split(",") if item.strip()]
    elif isinstance(raw_codes, Sequence):
        asset_codes = [str(item).strip() for item in raw_codes if str(item).strip()]
    if asset_codes:
        conditions.append(Asset.asset_code.in_(sorted(set(asset_codes))))
    asset_name = _normalized_text(filters.get("asset_name"))
    if asset_name:
        conditions.append(Asset.asset_name.contains(asset_name, autoescape=True))
    serial_number = _normalized_text(filters.get("serial_number"))
    if serial_number:
        conditions.append(Asset.normalized_serial == serial_number.lower())

    name_filters = (
        ("company_name", Asset.organization_id, Organization),
        ("category_name", Asset.category_id, AssetCategory),
        ("usage_company_name", Asset.usage_company_id, Organization),
        ("department_name", Asset.usage_department_id, Organization),
        ("location_name", Asset.location_id, AssetLocation),
        ("supplier_name", Asset.supplier_id, Supplier),
        ("source_name", Asset.source_id, AssetSource),
    )
    for key, column, model in name_filters:
        value = _normalized_text(filters.get(key))
        if value:
            conditions.append(column.in_(_name_ids(model, value)))
    for key, column in (
        ("user_name", Asset.holder_user_id),
        ("manager_name", Asset.manager_id),
    ):
        value = _normalized_text(filters.get(key))
        if value:
            conditions.append(column.in_(_user_name_ids(value)))

    status = _normalized_text(filters.get("status"))
    if status:
        conditions.append(Asset.status == status)
    data_completeness = _normalized_text(filters.get("data_completeness"))
    if data_completeness:
        conditions.append(Asset.data_completeness == data_completeness)
    purchase_date_from = filters.get("purchase_date_from")
    if isinstance(purchase_date_from, date):
        conditions.append(Asset.purchase_date >= purchase_date_from)
    purchase_date_to = filters.get("purchase_date_to")
    if isinstance(purchase_date_to, date):
        conditions.append(Asset.purchase_date <= purchase_date_to)
    if filters.get("only_my_assets") is True:
        conditions.append(Asset.holder_user_id == actor_id)
    return conditions


def list_for_export(
    *, actor_id: int, filters: Mapping[str, object | None], limit: int = 5000
) -> list[Asset]:
    permission_service.require_permission(actor_id, "asset:view")
    statement = (
        select(Asset)
        .where(*_build_asset_filters(actor_id=actor_id, filters=filters))
        .order_by(Asset.id.asc())
        .limit(limit + 1)
    )
    assets = list(db.session.scalars(statement).all())
    if len(assets) > limit:
        raise BusinessException(f"单次最多导出 {limit} 件资产，请缩小筛选范围")
    return assets


def page(
    *,
    actor_id: int,
    page_index: int,
    size: int,
    keyword: str | None = None,
    asset_code: str | None = None,
    asset_codes: str | None = None,
    asset_name: str | None = None,
    serial_number: str | None = None,
    company_name: str | None = None,
    category_name: str | None = None,
    status: str | None = None,
    department_name: str | None = None,
    location_name: str | None = None,
    user_name: str | None = None,
    manager_name: str | None = None,
    supplier_name: str | None = None,
    source_name: str | None = None,
    purchase_date_from: date | None = None,
    purchase_date_to: date | None = None,
    data_completeness: str | None = None,
    only_my_assets: bool = False,
) -> PageResult:
    permission_service.require_permission(actor_id, "asset:view")
    filters = _build_asset_filters(
        actor_id=actor_id,
        filters={
            "keyword": keyword,
            "asset_code": asset_code,
            "asset_codes": asset_codes,
            "asset_name": asset_name,
            "serial_number": serial_number,
            "company_name": company_name,
            "category_name": category_name,
            "status": status,
            "department_name": department_name,
            "location_name": location_name,
            "user_name": user_name,
            "manager_name": manager_name,
            "supplier_name": supplier_name,
            "source_name": source_name,
            "purchase_date_from": purchase_date_from,
            "purchase_date_to": purchase_date_to,
            "data_completeness": data_completeness,
            "only_my_assets": only_my_assets,
        },
    )
    result = asset_repository.page(
        QuerySpec(
            filters=filters,
            order_by=[Asset.id.desc()],
            page=page_index,
            size=size,
        )
    )
    include_amount = permission_service.has_permission(actor_id, "asset:amount:view")
    return PageResult(
        items=[_serialize(item, include_amount) for item in result.items],
        total=result.total,
        page=result.page,
        size=result.size,
    )


def get(asset_id: int, actor_id: int) -> dict[str, Any]:
    asset = asset_access_service.get_accessible(asset_id, actor_id)
    return _serialize(
        asset, permission_service.has_permission(actor_id, "asset:amount:view")
    )


def lifecycle(asset_id: int, actor_id: int) -> list[dict[str, Any]]:
    get(asset_id, actor_id)
    records = asset_lifecycle_repository.find_by_asset(asset_id)
    operator_names = _users_by_ids({record.operator_id for record in records})
    return [
        {
            "id": record.id,
            "operation_type": record.operation_type,
            "operation_no": record.operation_no,
            "operator_id": record.operator_id,
            "operator_name": operator_names.get(
                record.operator_id, f"用户 #{record.operator_id}"
            ),
            "before_data": record.before_data,
            "after_data": record.after_data,
            "remark": record.remark,
            "change_summary": _lifecycle_change_summary(record),
            "created_at": record.created_at,
        }
        for record in records
    ]


def related_records(asset_id: int, actor_id: int) -> dict[str, Any]:
    get(asset_id, actor_id)
    operation_rows = db.session.execute(
        select(OperationRequest, OperationRequestAsset)
        .join(
            OperationRequestAsset,
            OperationRequestAsset.operation_request_id == OperationRequest.id,
        )
        .where(OperationRequestAsset.asset_id == asset_id)
        .order_by(OperationRequest.created_at.desc(), OperationRequest.id.desc())
    ).all()
    operation_ids = [operation.id for operation, _asset in operation_rows]
    steps = (
        list(
            db.session.scalars(
                select(ApprovalStep)
                .where(ApprovalStep.operation_request_id.in_(operation_ids))
                .order_by(
                    ApprovalStep.operation_request_id.asc(), ApprovalStep.level_no.asc()
                )
            ).all()
        )
        if operation_ids
        else []
    )
    step_ids = [step.id for step in steps]
    tasks = (
        list(
            db.session.scalars(
                select(ApprovalTask)
                .where(ApprovalTask.approval_step_id.in_(step_ids))
                .order_by(ApprovalTask.approval_step_id.asc(), ApprovalTask.id.asc())
            ).all()
        )
        if step_ids
        else []
    )
    user_ids = {operation.applicant_id for operation, _asset in operation_rows}
    user_ids.update(task.approver_id for task in tasks)

    inventory_rows = db.session.execute(
        select(InventoryItem, InventoryTask)
        .join(InventoryTask, InventoryTask.id == InventoryItem.task_id)
        .where(InventoryItem.asset_id == asset_id)
        .order_by(InventoryTask.created_at.desc(), InventoryItem.id.desc())
    ).all()
    user_ids.update(
        item.submitted_by
        for item, _task in inventory_rows
        if item.submitted_by is not None
    )
    users = (
        {
            user.id: user.nickname or user.username
            for user in db.session.scalars(
                select(User).where(User.id.in_(user_ids))
            ).all()
        }
        if user_ids
        else {}
    )

    tasks_by_step: dict[int, list[dict[str, Any]]] = {}
    for task in tasks:
        tasks_by_step.setdefault(task.approval_step_id, []).append(
            {
                "id": task.id,
                "approver_id": task.approver_id,
                "approver_name": users.get(task.approver_id),
                "status": task.status,
                "opinion": task.opinion,
                "decided_at": task.decided_at,
            }
        )
    steps_by_operation: dict[int, list[dict[str, Any]]] = {}
    for step in steps:
        steps_by_operation.setdefault(step.operation_request_id, []).append(
            {
                "id": step.id,
                "level_no": step.level_no,
                "sign_mode": step.sign_mode,
                "status": step.status,
                "tasks": tasks_by_step.get(step.id, []),
            }
        )

    operations = [
        {
            "id": operation.id,
            "request_no": operation.request_no,
            "operation_type": operation.operation_type,
            "applicant_id": operation.applicant_id,
            "applicant_name": users.get(operation.applicant_id),
            "approval_channel": operation.approval_channel,
            "approval_status": operation.approval_status,
            "execution_status": operation.execution_status,
            "submitted_at": operation.submitted_at,
            "approved_at": operation.approved_at,
            "withdrawn_at": operation.withdrawn_at,
            "withdrawal_reason": operation.withdrawal_reason,
            "executed_at": operation.executed_at,
            "execution_error": operation.execution_error,
            "before_data": request_asset.before_data,
            "target_data": request_asset.target_data,
            "approval_steps": steps_by_operation.get(operation.id, []),
            "created_at": operation.created_at,
        }
        for operation, request_asset in operation_rows
    ]
    inventory_records = [
        {
            "id": item.id,
            "task_id": task.id,
            "task_no": task.task_no,
            "task_name": task.name,
            "task_status": task.status,
            "deadline_at": task.deadline_at,
            "item_status": item.status,
            "physical_result": item.physical_result,
            "location_result": item.location_result,
            "ledger_location_name": item.ledger_location_name,
            "actual_location_text": item.actual_location_text,
            "loss_reason": item.loss_reason,
            "loss_description": item.loss_description,
            "borrowed_by": item.borrowed_by,
            "submission_method": item.submission_method,
            "submitted_by": item.submitted_by,
            "submitted_by_name": users.get(item.submitted_by),
            "submitted_at": item.submitted_at,
            "is_late": item.is_late,
            "review_status": item.review_status,
            "resolution": item.resolution,
            "resolution_reason": item.resolution_reason,
            "created_at": item.created_at,
        }
        for item, task in inventory_rows
    ]
    return {"operations": operations, "inventory_records": inventory_records}


def audit_logs(actor_id: int) -> list[dict[str, Any]]:
    permission_service.require_permission(actor_id, "audit:view")
    if permission_service.accessible_organization_ids(actor_id) is not None:
        raise BusinessException(
            "审计日志第一阶段仅支持全量数据权限", result_code=ResultCode.FORBIDDEN
        )
    return [
        {
            "id": item.id,
            "action": item.action,
            "resource_type": item.resource_type,
            "resource_id": item.resource_id,
            "operator_id": item.operator_id,
            "before_data": item.before_data,
            "after_data": item.after_data,
            "reason": item.reason,
            "created_at": item.created_at,
        }
        for item in operation_log_repository.list_recent()
    ]


__all__ = [
    "audit_logs",
    "get",
    "lifecycle",
    "list_for_export",
    "page",
    "related_records",
    "stock_in_request",
]
