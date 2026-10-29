"""HTTP boundary for inventory tasks and mobile inventory submissions."""

from __future__ import annotations

from flask import Blueprint, request, send_file
from flask_jwt_extended import jwt_required

from app.common import BusinessException, Result
from app.schemas.inventory import (
    AdminMarkInventorySchema,
    CancelInventoryTaskSchema,
    CreateInventoryTaskSchema,
    EndCollectionSchema,
    InventoryItemPageQuerySchema,
    InventoryScanEventPageQuerySchema,
    InventoryTaskPageQuerySchema,
    ReopenInventoryItemsSchema,
    ResolveInventoryItemSchema,
    ResolveSurplusSchema,
    SendInventoryReminderSchema,
    TransferInventoryResponsibilitySchema,
    UpdateInventoryAdminsSchema,
    UpdateInventoryDeadlineSchema,
    WithdrawInventoryItemSchema,
    ReturnInventoryItemSchema,
    ScanInventorySchema,
    SubmitInventoryItemSchema,
)
from app.security import current_user_id
from app.services import inventory_service

bp = Blueprint("inventory", __name__, url_prefix="/api/v1/inventory")

_task_page_schema = InventoryTaskPageQuerySchema()
_item_page_schema = InventoryItemPageQuerySchema()
_scan_event_page_schema = InventoryScanEventPageQuerySchema()
_create_schema = CreateInventoryTaskSchema()
_scan_schema = ScanInventorySchema()
_submit_schema = SubmitInventoryItemSchema()
_admin_mark_schema = AdminMarkInventorySchema()
_end_schema = EndCollectionSchema()
_resolve_schema = ResolveInventoryItemSchema()
_return_schema = ReturnInventoryItemSchema()
_cancel_schema = CancelInventoryTaskSchema()
_reopen_schema = ReopenInventoryItemsSchema()
_admins_schema = UpdateInventoryAdminsSchema()
_deadline_schema = UpdateInventoryDeadlineSchema()
_withdraw_schema = WithdrawInventoryItemSchema()
_transfer_schema = TransferInventoryResponsibilitySchema()
_surplus_schema = ResolveSurplusSchema()
_reminder_schema = SendInventoryReminderSchema()


@bp.get("/overview")
@jwt_required()
def overview() -> dict:
    return Result.success(inventory_service.overview(current_user_id())).to_dict()


@bp.get("/tasks")
@jwt_required()
def tasks() -> dict:
    query = _task_page_schema.load(request.args.to_dict())
    result = inventory_service.list_tasks(
        actor_id=current_user_id(),
        page_index=query["page"],
        size=query["size"],
        status=query.get("status"),
    )
    return Result.success(result.to_dict()).to_dict()


@bp.get("/my-pending-items")
@jwt_required()
def my_pending_items() -> dict:
    return Result.success(
        inventory_service.list_my_pending_items(current_user_id())
    ).to_dict()


@bp.post("/tasks")
@jwt_required()
def create_task() -> dict:
    payload = _create_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        inventory_service.create_task(payload, current_user_id())
    ).to_dict()


@bp.get("/tasks/<int:task_id>")
@jwt_required()
def get_task(task_id: int) -> dict:
    return Result.success(
        inventory_service.get_task(task_id, current_user_id())
    ).to_dict()


@bp.post("/tasks/<int:task_id>/publish")
@jwt_required()
def publish_task(task_id: int) -> dict:
    return Result.success(
        inventory_service.publish_task(task_id, current_user_id())
    ).to_dict()


@bp.get("/tasks/<int:task_id>/items")
@jwt_required()
def items(task_id: int) -> dict:
    query = _item_page_schema.load(request.args.to_dict())
    result = inventory_service.list_items(
        task_id=task_id,
        actor_id=current_user_id(),
        page_index=query["page"],
        size=query["size"],
        status=query.get("status"),
        responsible_user_id=query.get("responsible_user_id"),
    )
    return Result.success(result.to_dict()).to_dict()


@bp.post("/tasks/<int:task_id>/scan")
@jwt_required()
def scan(task_id: int) -> dict:
    payload = _scan_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        inventory_service.scan(task_id, payload, current_user_id())
    ).to_dict()


@bp.get("/tasks/<int:task_id>/scan-events")
@jwt_required()
def scan_events(task_id: int) -> dict:
    query = _scan_event_page_schema.load(request.args.to_dict())
    result = inventory_service.list_scan_events(
        task_id=task_id,
        actor_id=current_user_id(),
        page_index=query["page"],
        size=query["size"],
        outcome=query.get("outcome"),
    )
    return Result.success(result.to_dict()).to_dict()


@bp.post("/tasks/<int:task_id>/items/<int:item_id>/photos")
@jwt_required()
def upload_photo(task_id: int, item_id: int) -> dict:
    file = request.files.get("file")
    return Result.success(
        inventory_service.upload_photo(task_id, item_id, file, current_user_id())
    ).to_dict()


@bp.get("/photos/<int:photo_id>")
@jwt_required()
def photo(photo_id: int):
    path, mime_type, original_name = inventory_service.get_photo(
        photo_id, current_user_id()
    )
    return send_file(
        path,
        mimetype=mime_type,
        download_name=original_name,
        as_attachment=False,
        conditional=True,
    )


@bp.post("/tasks/<int:task_id>/items/<int:item_id>/submit")
@jwt_required()
def submit_item(task_id: int, item_id: int) -> dict:
    payload = _submit_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        inventory_service.submit_item(task_id, item_id, payload, current_user_id())
    ).to_dict()


@bp.post("/tasks/<int:task_id>/admin-mark")
@jwt_required()
def admin_mark(task_id: int) -> dict:
    payload = _admin_mark_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        inventory_service.admin_mark(task_id, payload, current_user_id())
    ).to_dict()


@bp.post("/tasks/<int:task_id>/end-collection")
@jwt_required()
def end_collection(task_id: int) -> dict:
    payload = _end_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        inventory_service.end_collection(task_id, payload, current_user_id())
    ).to_dict()


@bp.post("/tasks/<int:task_id>/items/<int:item_id>/resolve")
@jwt_required()
def resolve_item(task_id: int, item_id: int) -> dict:
    payload = _resolve_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        inventory_service.resolve_item(task_id, item_id, payload, current_user_id())
    ).to_dict()


@bp.post("/tasks/<int:task_id>/items/<int:item_id>/return")
@jwt_required()
def return_item(task_id: int, item_id: int) -> dict:
    payload = _return_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        inventory_service.return_item(task_id, item_id, payload, current_user_id())
    ).to_dict()


@bp.post("/tasks/<int:task_id>/reopen")
@jwt_required()
def reopen_items(task_id: int) -> dict:
    payload = _reopen_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        inventory_service.reopen_items(task_id, payload, current_user_id())
    ).to_dict()


@bp.post("/tasks/<int:task_id>/complete")
@jwt_required()
def complete_task(task_id: int) -> dict:
    return Result.success(
        inventory_service.complete_task(task_id, current_user_id())
    ).to_dict()


@bp.post("/tasks/<int:task_id>/cancel")
@jwt_required()
def cancel_task(task_id: int) -> dict:
    payload = _cancel_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        inventory_service.cancel_task(task_id, payload, current_user_id())
    ).to_dict()


@bp.post("/tasks/<int:task_id>/admins")
@jwt_required()
def update_admins(task_id: int) -> dict:
    payload = _admins_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        inventory_service.update_admins(task_id, payload, current_user_id())
    ).to_dict()


@bp.post("/tasks/<int:task_id>/deadline")
@jwt_required()
def update_deadline(task_id: int) -> dict:
    payload = _deadline_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        inventory_service.update_deadline(task_id, payload, current_user_id())
    ).to_dict()


@bp.post("/tasks/<int:task_id>/items/<int:item_id>/withdraw")
@jwt_required()
def withdraw_item(task_id: int, item_id: int) -> dict:
    payload = _withdraw_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        inventory_service.withdraw_item(task_id, item_id, payload, current_user_id())
    ).to_dict()


@bp.post("/tasks/<int:task_id>/items/<int:item_id>/responsible")
@jwt_required()
def transfer_responsibility(task_id: int, item_id: int) -> dict:
    payload = _transfer_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        inventory_service.transfer_responsibility(
            task_id, item_id, payload, current_user_id()
        )
    ).to_dict()


@bp.get("/tasks/<int:task_id>/items/<int:item_id>/versions")
@jwt_required()
def result_versions(task_id: int, item_id: int) -> dict:
    return Result.success(
        inventory_service.list_result_versions(task_id, item_id, current_user_id())
    ).to_dict()


@bp.post("/tasks/<int:task_id>/scan-events/<int:event_id>/resolve")
@jwt_required()
def resolve_surplus(task_id: int, event_id: int) -> dict:
    payload = _surplus_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        inventory_service.resolve_surplus(task_id, event_id, payload, current_user_id())
    ).to_dict()


@bp.post("/tasks/<int:task_id>/reminders")
@jwt_required()
def send_reminders(task_id: int) -> dict:
    payload = _reminder_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        inventory_service.send_reminders(task_id, payload, current_user_id())
    ).to_dict()


@bp.get("/tasks/<int:task_id>/report")
@jwt_required()
def report(task_id: int):
    stream, file_name = inventory_service.build_report(task_id, current_user_id())
    return send_file(
        stream,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        download_name=file_name,
        as_attachment=True,
    )


@bp.errorhandler(413)
def file_too_large(_error: Exception) -> dict:
    raise BusinessException("上传文件过大")


__all__ = ["bp"]
