"""Supplier business use cases."""

from __future__ import annotations

from typing import Any, NoReturn

from sqlalchemy.exc import IntegrityError

from app.common import BusinessException, ResultCode
from app.enums import RecordStatus
from app.extensions import db
from app.models import Supplier
from app.repositories.asset_repository import asset_repository
from app.repositories.supplier_repository import (
    supplier_code_sequence_repository,
    supplier_repository,
)
from app.repositories.workflow_repository import stock_in_item_repository
from app.services import audit_service, permission_service


_SUPPLIER_UNIQUE_MARKERS = (
    "suppliers.code",
    "suppliers.name",
    "suppliers.unified_social_credit_code",
    "ix_suppliers_code",
    "ix_suppliers_name",
    "ix_suppliers_unified_social_credit_code",
)
_SUPPLIER_REFERENCE_MARKERS = (
    "fk_assets_supplier_id",
    "fk_stock_in_items_supplier_id",
)


def _normalize_name(value: object) -> str:
    if value is None:
        raise BusinessException(
            "供应商名称不能为空", result_code=ResultCode.BAD_REQUEST
        )
    name = str(value).strip()
    if not name:
        raise BusinessException(
            "供应商名称不能为空", result_code=ResultCode.BAD_REQUEST
        )
    return name


def _normalize_credit(value: object | None) -> str | None:
    if value is None:
        return None
    credit = str(value).strip().upper()
    return credit or None


def _normalize_optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _supplier_dict(supplier: Supplier) -> dict[str, Any]:
    return {
        "id": supplier.id,
        "code": supplier.code,
        "name": supplier.name,
        "unified_social_credit_code": supplier.unified_social_credit_code,
        "contact_name": supplier.contact_name,
        "contact_phone": supplier.contact_phone,
        "address": supplier.address,
        "remark": supplier.remark,
        "status": supplier.status,
        "version": supplier.version,
    }


def _mask_phone(phone: str | None) -> str | None:
    if not phone:
        return phone
    if len(phone) != 11:
        return "*" * len(phone)
    return f"{phone[:3]}****{phone[-4:]}"


def _integrity_context(error: IntegrityError) -> tuple[str, str]:
    statement = str(error.statement or "").lower()
    original = str(error.orig).lower()
    return statement, f"{statement} {original}"


def _is_supplier_unique_conflict(error: IntegrityError) -> bool:
    _statement, context = _integrity_context(error)
    is_unique = "unique constraint failed" in context or "duplicate entry" in context
    return is_unique and any(marker in context for marker in _SUPPLIER_UNIQUE_MARKERS)


def _is_supplier_delete_reference_conflict(error: IntegrityError) -> bool:
    statement, context = _integrity_context(error)
    is_foreign_key = (
        "foreign key constraint failed" in context
        or "cannot delete or update a parent row" in context
    )
    targets_supplier = "delete from suppliers" in statement or any(
        marker in context for marker in _SUPPLIER_REFERENCE_MARKERS
    )
    return is_foreign_key and targets_supplier


def _raise_write_integrity(error: IntegrityError) -> NoReturn:
    db.session.rollback()
    if _is_supplier_unique_conflict(error):
        raise BusinessException("供应商已存在") from None
    raise BusinessException(
        "供应商保存失败，请稍后重试", result_code=ResultCode.INTERNAL_ERROR
    ) from None


def _raise_delete_integrity(error: IntegrityError) -> NoReturn:
    db.session.rollback()
    if _is_supplier_delete_reference_conflict(error):
        raise BusinessException("供应商已被使用，不能删除") from None
    raise BusinessException(
        "供应商删除失败，请稍后重试", result_code=ResultCode.INTERNAL_ERROR
    ) from None


def _supplier_audit_snapshot(supplier: Supplier) -> dict[str, Any]:
    return {
        "id": supplier.id,
        "code": supplier.code,
        "name": supplier.name,
        "unified_social_credit_code": supplier.unified_social_credit_code,
        "contact_phone": _mask_phone(supplier.contact_phone),
        "status": supplier.status,
        "version": supplier.version,
    }


def _allocate_supplier_code() -> str:
    supplier_code_sequence_repository.ensure_exists()
    sequence = supplier_code_sequence_repository.find_for_update()
    if sequence is None:
        raise RuntimeError("supplier code sequence was not initialized")
    sequence.current_value += 1
    return f"{sequence.prefix}{sequence.current_value:06d}"


def _require_supplier(supplier_id: int) -> Supplier:
    supplier = supplier_repository.get(supplier_id)
    if supplier is None:
        raise BusinessException("供应商不存在")
    return supplier


def _stale_supplier() -> None:
    db.session.rollback()
    raise BusinessException("供应商已被其他人修改，请刷新后重试")


def create_supplier(payload: dict[str, Any], actor_id: int) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "supplier:create")
    name = _normalize_name(payload.get("name"))
    credit = _normalize_credit(payload.get("unified_social_credit_code"))
    existing = supplier_repository.find_by_name(name)
    if existing is not None:
        disabled = existing.status == RecordStatus.DISABLED.value
        db.session.rollback()
        if disabled:
            raise BusinessException("供应商已停用，请恢复启用")
        raise BusinessException("供应商已存在")
    credit_owner = (
        supplier_repository.find_by_credit_code(credit) if credit is not None else None
    )
    if credit_owner is not None:
        db.session.rollback()
        raise BusinessException("供应商已存在")
    try:
        supplier = Supplier(
            code=_allocate_supplier_code(),
            name=name,
            unified_social_credit_code=credit,
            contact_name=_normalize_optional_text(payload.get("contact_name")),
            contact_phone=_normalize_optional_text(payload.get("contact_phone")),
            address=_normalize_optional_text(payload.get("address")),
            remark=_normalize_optional_text(payload.get("remark")),
            status=RecordStatus.ENABLED.value,
        )
        supplier_repository.add(supplier)
        audit_service.record_resource_change(
            action="SUPPLIER_CREATE",
            resource_type="supplier",
            resource_id=supplier.id,
            actor_id=actor_id,
            before_data=None,
            after_data=_supplier_audit_snapshot(supplier),
        )
        db.session.commit()
    except IntegrityError as error:
        _raise_write_integrity(error)
    return _supplier_dict(supplier)


def require_enabled_supplier(supplier_id: int) -> Supplier:
    supplier = _require_supplier(supplier_id)
    if supplier.status != RecordStatus.ENABLED.value:
        raise BusinessException("供应商不存在或已停用")
    return supplier


def list_suppliers(actor_id: int) -> list[dict[str, Any]]:
    permission_service.require_permission(actor_id, "supplier:view")
    return [_supplier_dict(supplier) for supplier in supplier_repository.list_all()]


def update_supplier(
    supplier_id: int, payload: dict[str, Any], actor_id: int
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "supplier:edit")
    supplier = _require_supplier(supplier_id)
    if "version" not in payload:
        raise BusinessException("供应商版本不能为空")
    allowed_fields = {
        "version",
        "name",
        "unified_social_credit_code",
        "contact_name",
        "contact_phone",
        "address",
        "remark",
    }
    invalid = set(payload) - allowed_fields
    if invalid:
        raise BusinessException(f"供应商字段不允许更新: {', '.join(sorted(invalid))}")
    changes: dict[str, object] = {}
    if "name" in payload:
        changes["name"] = _normalize_name(payload["name"])
    if "unified_social_credit_code" in payload:
        changes["unified_social_credit_code"] = _normalize_credit(
            payload["unified_social_credit_code"]
        )
    for field in ("contact_name", "contact_phone", "address", "remark"):
        if field in payload:
            changes[field] = _normalize_optional_text(payload[field])
    if not changes:
        raise BusinessException("供应商更新内容不能为空")

    target_name = changes.get("name")
    if isinstance(target_name, str):
        owner = supplier_repository.find_by_name(target_name)
        if owner is not None and owner.id != supplier.id:
            raise BusinessException("供应商已存在")
    target_credit = changes.get("unified_social_credit_code")
    if isinstance(target_credit, str):
        owner = supplier_repository.find_by_credit_code(target_credit)
        if owner is not None and owner.id != supplier.id:
            raise BusinessException("供应商已存在")

    before_data = _supplier_audit_snapshot(supplier)
    try:
        if not supplier_repository.cas_update(
            supplier.id, int(payload["version"]), changes
        ):
            _stale_supplier()
        db.session.expire(supplier)
        audit_service.record_resource_change(
            action="SUPPLIER_UPDATE",
            resource_type="supplier",
            resource_id=supplier.id,
            actor_id=actor_id,
            before_data=before_data,
            after_data=_supplier_audit_snapshot(supplier),
        )
        db.session.commit()
    except IntegrityError as error:
        _raise_write_integrity(error)
    return _supplier_dict(supplier)


def set_supplier_enabled(
    supplier_id: int, enabled: bool, expected_version: int, actor_id: int
) -> dict[str, Any]:
    permission_service.require_permission(actor_id, "supplier:disable")
    supplier = _require_supplier(supplier_id)
    before_data = _supplier_audit_snapshot(supplier)
    target_status = (
        RecordStatus.ENABLED.value if enabled else RecordStatus.DISABLED.value
    )
    try:
        if not supplier_repository.cas_update(
            supplier.id, expected_version, {"status": target_status}
        ):
            _stale_supplier()
        db.session.expire(supplier)
        audit_service.record_resource_change(
            action="SUPPLIER_ENABLE" if enabled else "SUPPLIER_DISABLE",
            resource_type="supplier",
            resource_id=supplier.id,
            actor_id=actor_id,
            before_data=before_data,
            after_data=_supplier_audit_snapshot(supplier),
        )
        db.session.commit()
    except IntegrityError as error:
        _raise_write_integrity(error)
    return _supplier_dict(supplier)


def delete_supplier(
    supplier_id: int, expected_version: int, actor_id: int, reason: str
) -> None:
    permission_service.require_permission(actor_id, "supplier:delete")
    if reason is None:
        raise BusinessException("删除原因不能为空", result_code=ResultCode.BAD_REQUEST)
    normalized_reason = str(reason).strip()
    if not normalized_reason:
        raise BusinessException("删除原因不能为空", result_code=ResultCode.BAD_REQUEST)
    supplier = supplier_repository.find_for_update(supplier_id)
    if supplier is None:
        raise BusinessException("供应商不存在")
    if supplier.version != expected_version:
        _stale_supplier()
    if asset_repository.has_supplier_reference(
        supplier.id
    ) or stock_in_item_repository.has_supplier_reference(supplier.id):
        db.session.rollback()
        raise BusinessException("供应商已被使用，不能删除")
    before_data = _supplier_audit_snapshot(supplier)
    try:
        supplier_repository.delete(supplier)
        audit_service.record_resource_change(
            action="SUPPLIER_DELETE",
            resource_type="supplier",
            resource_id=supplier.id,
            actor_id=actor_id,
            before_data=before_data,
            after_data=None,
            reason=normalized_reason,
        )
        db.session.commit()
    except IntegrityError as error:
        _raise_delete_integrity(error)


__all__ = [
    "create_supplier",
    "delete_supplier",
    "list_suppliers",
    "require_enabled_supplier",
    "set_supplier_enabled",
    "update_supplier",
]
