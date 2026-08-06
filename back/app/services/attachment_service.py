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
from app.models import AssetAttachment
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


def _active_count(asset_id: int, business_type: str) -> int:
    return len(
        db.session.scalars(
            select(AssetAttachment.id).where(
                AssetAttachment.asset_id == asset_id,
                AssetAttachment.business_type == business_type,
                AssetAttachment.status == _ACTIVE,
            )
        ).all()
    )


def list_for_asset(asset_id: int, actor_id: int) -> list[dict]:
    asset_access_service.get_accessible(asset_id, actor_id)
    rows = db.session.scalars(
        select(AssetAttachment)
        .where(AssetAttachment.asset_id == asset_id)
        .order_by(
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
    original_name: str,
    mime_type: str,
    content: bytes,
) -> dict:
    asset = asset_access_service.get_accessible(asset_id, actor_id)
    permission_service.require_permission(actor_id, "asset:attachment:manage")
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
        if _active_count(asset_id, business_type) >= _MAX_PHOTOS_PER_ASSET:
            raise BusinessException("每项资产最多保留 5 张有效照片")
    else:
        suffix = (_IMAGE_TYPES | _DOCUMENT_TYPES).get(mime_type)
        if suffix is None:
            raise BusinessException("业务附件仅支持图片、PDF、Word 或 Excel 文件")
        if len(content) > _MAX_DOCUMENT_BYTES:
            raise BusinessException("单个业务附件不能超过 20MB")
        if _active_count(asset_id, business_type) >= _MAX_FILES_PER_ASSET_AND_TYPE:
            raise BusinessException("同类有效附件最多保留 20 个")

    safe_stem = secure_filename(Path(normalized_name).stem)[:80] or "file"
    storage_key = f"assets/{asset_id}/{uuid4().hex}-{safe_stem}{suffix}"
    _storage().write(storage_key, content)
    first_photo = (
        business_type == "PHOTO" and _active_count(asset_id, business_type) == 0
    )
    row = AssetAttachment(
        asset_id=asset_id,
        business_type=business_type,
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
    asset_access_service.get_accessible(attachment.asset_id, actor_id)
    if attachment.status != _ACTIVE:
        raise BusinessException("附件已作废，不能下载")
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
