"""Authenticated asset attachment metadata and local-storage operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from flask import current_app
from sqlalchemy import select
from werkzeug.utils import secure_filename

from app.common import BusinessException, ResultCode
from app.extensions import db
from app.models import (
    Asset,
    AssetAttachment,
    AssetRepairRecord,
    AssetScrapRecord,
    AssetTransferHandover,
    AssetUsageRequest,
    OperationRequest,
    OperationRequestAsset,
)
from app.models.mixins import utc_now
from app.services import asset_access_service, audit_service, permission_service

_ACTIVE = "ACTIVE"
_VOIDED = "VOIDED"
_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_DOCUMENT_TYPES = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
}
_MAX_PHOTO_BYTES = 10 * 1024 * 1024
_MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
_MAX_PHOTOS_PER_ASSET = 5
_MAX_FILES_PER_ASSET_AND_TYPE = 20


class StorageAdapter(Protocol):
    def write(self, storage_key: str, content: bytes) -> None: ...

    def resolve(self, storage_key: str) -> Path: ...


class LocalStorageAdapter:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def write(self, storage_key: str, content: bytes) -> None:
        target = self.resolve(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(f"{target.suffix}.tmp")
        temporary.write_bytes(content)
        temporary.replace(target)

    def resolve(self, storage_key: str) -> Path:
        target = (self.root / storage_key).resolve()
        if self.root != target and self.root not in target.parents:
            raise BusinessException("附件存储路径无效")
        return target


def _storage() -> StorageAdapter:
    configured = current_app.config.get("ASSET_STORAGE_DIR")
    root = (
        Path(str(configured))
        if configured
        else Path(current_app.instance_path) / "uploads"
    )
    return LocalStorageAdapter(root)


def _serialize(row: AssetAttachment) -> dict:
    return {
        "id": row.id,
        "asset_id": row.asset_id,
        "business_type": row.business_type,
        "business_id": row.business_id,
        "document_type": row.document_type,
        "original_name": row.original_name,
        "mime_type": row.mime_type,
        "size_bytes": row.size_bytes,
        "sha256": row.sha256,
        "is_cover": row.is_cover,
        "status": row.status,
        "uploaded_by": row.uploaded_by,
        "voided_by": row.voided_by,
        "voided_at": row.voided_at,
        "void_reason": row.void_reason,
        "version": row.version,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _audit_snapshot(row: AssetAttachment) -> dict:
    snapshot = _serialize(row)
    for key in ("voided_at", "created_at", "updated_at"):
        value = snapshot.get(key)
        if isinstance(value, datetime):
            snapshot[key] = value.isoformat()
    return snapshot


def _require_attachment(attachment_id: int) -> AssetAttachment:
    attachment = db.session.get(AssetAttachment, attachment_id)
    if attachment is None:
        raise BusinessException("附件不存在", result_code=ResultCode.NOT_FOUND)
    return attachment


_EVIDENCE_TYPES = {
    "USAGE_SIGN",
    "RETURN_HANDOVER",
    "RETURN_INSPECTION",
    "TRANSFER_RECEIPT",
}


def _is_manager(actor_id: int) -> bool:
    return permission_service.has_permission(actor_id, "asset:usage:manage")


def _require_evidence_access(
    *, asset_id: int, business_type: str, business_id: int | None, actor_id: int
) -> None:
    """Validate the asset-to-workflow link and the participant allowed to use evidence."""
    if business_type not in _EVIDENCE_TYPES:
        return
    if business_id is None:
        raise BusinessException("履约证据必须关联申请或交接单")
    asset = db.session.get(Asset, asset_id)
    if asset is None:
        raise BusinessException("资产不存在", result_code=ResultCode.NOT_FOUND)
    allowed = _is_manager(actor_id)
    if business_type == "TRANSFER_RECEIPT":
        handover = db.session.get(AssetTransferHandover, business_id)
        if handover is None or not any(
            int(item.get("asset_id", 0)) == asset_id for item in (handover.items or [])
        ):
            raise BusinessException("交接单不存在或不包含该资产")
        allowed = allowed or handover.receiver_user_id == actor_id
    else:
        operation = db.session.get(OperationRequest, business_id)
        if operation is None:
            raise BusinessException("业务申请不存在", result_code=ResultCode.NOT_FOUND)
        linked = db.session.scalar(
            select(OperationRequestAsset.id).where(
                OperationRequestAsset.operation_request_id == business_id,
                OperationRequestAsset.asset_id == asset_id,
            )
        )
        if linked is None:
            raise BusinessException("业务申请不存在或不包含该资产")
        if business_type == "USAGE_SIGN":
            detail = db.session.scalar(
                select(AssetUsageRequest).where(
                    AssetUsageRequest.operation_request_id == business_id
                )
            )
            allowed = allowed or (
                detail is not None and detail.target_user_id == actor_id
            )
        else:
            allowed = allowed or operation.applicant_id == actor_id
    if not allowed:
        raise BusinessException(
            "当前账号无权操作该履约证据", result_code=ResultCode.FORBIDDEN
        )


def _require_attachment_access(row: AssetAttachment, actor_id: int) -> None:
    if row.business_type in _EVIDENCE_TYPES:
        _require_evidence_access(
            asset_id=row.asset_id,
            business_type=row.business_type,
            business_id=row.business_id,
            actor_id=actor_id,
        )
        return
    asset_access_service.get_accessible(row.asset_id, actor_id)


def _require_business_access(
    *, asset_id: int, business_type: str, business_id: int | None, actor_id: int
) -> None:
    if business_type in _EVIDENCE_TYPES:
        _require_evidence_access(
            asset_id=asset_id,
            business_type=business_type,
            business_id=business_id,
            actor_id=actor_id,
        )
        return
    if business_type not in {"REPAIR", "SCRAP"}:
        if business_id is not None:
            raise BusinessException("普通资产附件不能关联业务记录")
        return
    if business_id is None:
        raise BusinessException("维修或报废附件必须关联业务记录")
    if business_type == "REPAIR":
        repair_record = db.session.get(AssetRepairRecord, business_id)
        record_asset_id = repair_record.asset_id if repair_record is not None else None
    else:
        scrap_record = db.session.get(AssetScrapRecord, business_id)
        record_asset_id = scrap_record.asset_id if scrap_record is not None else None
    if record_asset_id != asset_id:
        raise BusinessException("附件关联的业务记录不存在或不属于该资产")
    permission_service.require_permission(
        actor_id, "asset:repair" if business_type == "REPAIR" else "asset:scrap"
    )


def _require_sensitive_download_permission(row: AssetAttachment, actor_id: int) -> None:
    if row.document_type in {
        "REPAIR_QUOTE",
        "REPAIR_INVOICE",
        "DISPOSAL_VOUCHER",
    }:
        permission_service.require_permission(actor_id, "asset:amount:view")


def _active_count(
    asset_id: int, business_type: str, business_id: int | None = None
) -> int:
    return len(
        db.session.scalars(
            select(AssetAttachment.id).where(
                AssetAttachment.asset_id == asset_id,
                AssetAttachment.business_type == business_type,
                AssetAttachment.business_id == business_id,
                AssetAttachment.status == _ACTIVE,
            )
        ).all()
    )


def list_for_asset(
    asset_id: int,
    actor_id: int,
    *,
    business_type: str | None = None,
    business_id: int | None = None,
) -> list[dict]:
    if business_type in _EVIDENCE_TYPES:
        _require_evidence_access(
            asset_id=asset_id,
            business_type=business_type,
            business_id=business_id,
            actor_id=actor_id,
        )
    else:
        asset_access_service.get_accessible(asset_id, actor_id)
    if business_type is not None:
        _require_business_access(
            asset_id=asset_id,
            business_type=business_type,
            business_id=business_id,
            actor_id=actor_id,
        )
    statement = select(AssetAttachment).where(AssetAttachment.asset_id == asset_id)
    if business_type is not None:
        statement = statement.where(AssetAttachment.business_type == business_type)
    if business_id is not None:
        statement = statement.where(AssetAttachment.business_id == business_id)
    rows = db.session.scalars(
        statement.order_by(
            AssetAttachment.status.asc(),
            AssetAttachment.is_cover.desc(),
            AssetAttachment.created_at.desc(),
            AssetAttachment.id.desc(),
        )
    ).all()
    return [_serialize(row) for row in rows]


def upload(
    *,
    asset_id: int,
    actor_id: int,
    business_type: str,
    business_id: int | None,
    document_type: str,
    original_name: str,
    mime_type: str,
    content: bytes,
) -> dict:
    if business_type in _EVIDENCE_TYPES:
        _require_evidence_access(
            asset_id=asset_id,
            business_type=business_type,
            business_id=business_id,
            actor_id=actor_id,
        )
        asset = db.session.get(Asset, asset_id)
        if asset is None:
            raise BusinessException("资产不存在", result_code=ResultCode.NOT_FOUND)
    else:
        asset = asset_access_service.get_accessible(asset_id, actor_id)
        permission_service.require_permission(actor_id, "asset:attachment:manage")
    _require_business_access(
        asset_id=asset_id,
        business_type=business_type,
        business_id=business_id,
        actor_id=actor_id,
    )
    normalized_name = original_name.strip()
    if not normalized_name:
        raise BusinessException(
            "附件文件名不能为空", result_code=ResultCode.BAD_REQUEST
        )
    if not content:
        raise BusinessException("附件内容不能为空", result_code=ResultCode.BAD_REQUEST)

    if business_type == "PHOTO":
        suffix = _IMAGE_TYPES.get(mime_type)
        if suffix is None:
            raise BusinessException("资产照片仅支持 JPG、PNG、WebP")
        if len(content) > _MAX_PHOTO_BYTES:
            raise BusinessException("单张资产照片不能超过 10MB")
        if _active_count(asset_id, business_type, business_id) >= _MAX_PHOTOS_PER_ASSET:
            raise BusinessException("每项资产最多保留 5 张有效照片")
    else:
        suffix = (_IMAGE_TYPES | _DOCUMENT_TYPES).get(mime_type)
        if suffix is None:
            raise BusinessException("业务附件仅支持图片、PDF、Word 或 Excel 文件")
        if len(content) > _MAX_DOCUMENT_BYTES:
            raise BusinessException("单个业务附件不能超过 20MB")
        if (
            _active_count(asset_id, business_type, business_id)
            >= _MAX_FILES_PER_ASSET_AND_TYPE
        ):
            raise BusinessException("同类有效附件最多保留 20 个")

    safe_stem = secure_filename(Path(normalized_name).stem)[:80] or "file"
    storage_key = f"assets/{asset_id}/{uuid4().hex}-{safe_stem}{suffix}"
    _storage().write(storage_key, content)
    first_photo = (
        business_type == "PHOTO"
        and _active_count(asset_id, business_type, business_id) == 0
    )
    row = AssetAttachment(
        asset_id=asset_id,
        business_type=business_type,
        business_id=business_id,
        document_type=document_type,
        original_name=normalized_name[:255],
        storage_key=storage_key,
        mime_type=mime_type,
        size_bytes=len(content),
        sha256=sha256(content).hexdigest(),
        is_cover=first_photo,
        uploaded_by=actor_id,
    )
    db.session.add(row)
    db.session.flush()
    snapshot = _serialize(row)
    audit_snapshot = _audit_snapshot(row)
    audit_service.record_resource_change(
        action="ASSET_ATTACHMENT_UPLOAD",
        resource_type="asset_attachment",
        resource_id=row.id,
        actor_id=actor_id,
        before_data=None,
        after_data=audit_snapshot,
    )
    audit_service.record_asset_lifecycle(
        asset_id=asset.id,
        operation_type="ASSET_ATTACHMENT_UPLOAD",
        request_no=f"ATT-{row.id}",
        actor_id=actor_id,
        before_data={},
        after_data=audit_snapshot,
    )
    db.session.commit()
    return snapshot


def void(attachment_id: int, actor_id: int, *, version: int, reason: str) -> dict:
    attachment = _require_attachment(attachment_id)
    asset_access_service.get_accessible(attachment.asset_id, actor_id)
    permission_service.require_permission(actor_id, "asset:attachment:manage")
    if attachment.status != _ACTIVE:
        raise BusinessException("附件已作废")
    if attachment.version != version:
        raise BusinessException("附件已被其他人修改，请刷新后重试")
    normalized_reason = reason.strip()
    before_audit = _audit_snapshot(attachment)
    was_cover = attachment.is_cover
    attachment.status = _VOIDED
    attachment.is_cover = False
    attachment.voided_by = actor_id
    attachment.voided_at = utc_now()
    attachment.void_reason = normalized_reason
    attachment.version += 1
    if was_cover:
        replacement = db.session.scalar(
            select(AssetAttachment)
            .where(
                AssetAttachment.asset_id == attachment.asset_id,
                AssetAttachment.business_type == "PHOTO",
                AssetAttachment.status == _ACTIVE,
                AssetAttachment.id != attachment.id,
            )
            .order_by(AssetAttachment.created_at.asc(), AssetAttachment.id.asc())
        )
        if replacement is not None:
            replacement.is_cover = True
            replacement.version += 1
    after = _serialize(attachment)
    after_audit = _audit_snapshot(attachment)
    audit_service.record_resource_change(
        action="ASSET_ATTACHMENT_VOID",
        resource_type="asset_attachment",
        resource_id=attachment.id,
        actor_id=actor_id,
        before_data=before_audit,
        after_data=after_audit,
        reason=normalized_reason,
    )
    audit_service.record_asset_lifecycle(
        asset_id=attachment.asset_id,
        operation_type="ASSET_ATTACHMENT_VOID",
        request_no=f"ATT-{attachment.id}",
        actor_id=actor_id,
        before_data=before_audit,
        after_data=after_audit,
    )
    db.session.commit()
    return after


def set_cover(attachment_id: int, actor_id: int, *, version: int) -> dict:
    attachment = _require_attachment(attachment_id)
    asset_access_service.get_accessible(attachment.asset_id, actor_id)
    permission_service.require_permission(actor_id, "asset:attachment:manage")
    if attachment.status != _ACTIVE or attachment.business_type != "PHOTO":
        raise BusinessException("只有有效资产照片可以设为封面")
    if attachment.version != version:
        raise BusinessException("附件已被其他人修改，请刷新后重试")
    if attachment.is_cover:
        return _serialize(attachment)
    current_cover = db.session.scalar(
        select(AssetAttachment).where(
            AssetAttachment.asset_id == attachment.asset_id,
            AssetAttachment.business_type == "PHOTO",
            AssetAttachment.status == _ACTIVE,
            AssetAttachment.is_cover.is_(True),
        )
    )
    before = _audit_snapshot(attachment)
    if current_cover is not None:
        current_cover.is_cover = False
        current_cover.version += 1
    attachment.is_cover = True
    attachment.version += 1
    after = _serialize(attachment)
    audit_service.record_resource_change(
        action="ASSET_ATTACHMENT_COVER_UPDATE",
        resource_type="asset_attachment",
        resource_id=attachment.id,
        actor_id=actor_id,
        before_data=before,
        after_data=_audit_snapshot(attachment),
    )
    db.session.commit()
    return after


@dataclass(frozen=True)
class DownloadTarget:
    path: Path
    original_name: str
    mime_type: str


def download_target(attachment_id: int, actor_id: int) -> DownloadTarget:
    attachment = _require_attachment(attachment_id)
    _require_attachment_access(attachment, actor_id)
    if attachment.status != _ACTIVE:
        raise BusinessException("附件已作废，不能下载")
    _require_sensitive_download_permission(attachment, actor_id)
    path = _storage().resolve(attachment.storage_key)
    if not path.is_file():
        raise BusinessException("附件文件不存在", result_code=ResultCode.NOT_FOUND)
    return DownloadTarget(
        path=path,
        original_name=attachment.original_name,
        mime_type=attachment.mime_type,
    )


def cleanup_orphan_temporary_files(*, older_than: datetime) -> int:
    """Remove interrupted local writes; intended for a scheduled maintenance command."""
    adapter = _storage()
    if not isinstance(adapter, LocalStorageAdapter) or not adapter.root.exists():
        return 0
    removed = 0
    cutoff = older_than.timestamp()
    for path in adapter.root.rglob("*.tmp"):
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink()
            removed += 1
    return removed


__all__ = [
    "DownloadTarget",
    "LocalStorageAdapter",
    "StorageAdapter",
    "cleanup_orphan_temporary_files",
    "download_target",
    "list_for_asset",
    "set_cover",
    "upload",
    "void",
]
