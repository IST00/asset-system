"""Persistent CSV exports and 80×30 mm Code 39 asset label PDFs."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4

from flask import current_app
from sqlalchemy import select

from app.common import BusinessException, PageResult, ResultCode
from app.extensions import db
from app.models import (
    Asset,
    AssetCategory,
    AssetLocation,
    AssetSource,
    ExportJob,
    Organization,
    Supplier,
    Unit,
    User,
)
from app.models.mixins import utc_now
from app.services import (
    asset_access_service,
    asset_service,
    audit_service,
    permission_service,
)

_ASSET_CSV = "ASSET_CSV"
_LABEL_PDF = "LABEL_PDF"
_PROCESSING = "PROCESSING"
_SUCCESS = "SUCCESS"
_FAILED = "FAILED"
_EXPIRED = "EXPIRED"
_MAX_LABEL_ASSETS = 100

_CODE39_MASKS = {
    "0": 0x034,
    "1": 0x121,
    "2": 0x061,
    "3": 0x160,
    "4": 0x031,
    "5": 0x130,
    "6": 0x070,
    "7": 0x025,
    "8": 0x124,
    "9": 0x064,
    "A": 0x109,
    "B": 0x049,
    "C": 0x148,
    "D": 0x019,
    "E": 0x118,
    "F": 0x058,
    "G": 0x00D,
    "H": 0x10C,
    "I": 0x04C,
    "J": 0x01C,
    "K": 0x103,
    "L": 0x043,
    "M": 0x142,
    "N": 0x013,
    "O": 0x112,
    "P": 0x052,
    "Q": 0x007,
    "R": 0x106,
    "S": 0x046,
    "T": 0x016,
    "U": 0x181,
    "V": 0x0C1,
    "W": 0x1C0,
    "X": 0x091,
    "Y": 0x190,
    "Z": 0x0D0,
    "-": 0x085,
    ".": 0x184,
    " ": 0x0C4,
    "$": 0x0A8,
    "/": 0x0A2,
    "+": 0x08A,
    "%": 0x02A,
    "*": 0x094,
}


@dataclass(frozen=True)
class DownloadTarget:
    path: Path
    original_name: str
    mime_type: str


def _storage_root() -> Path:
    configured = current_app.config.get("EXPORT_STORAGE_DIR")
    root = (
        Path(str(configured))
        if configured
        else Path(current_app.instance_path) / "exports"
    )
    return root.resolve()


def _resolve_storage_key(storage_key: str) -> Path:
    root = _storage_root()
    target = (root / storage_key).resolve()
    if root != target and root not in target.parents:
        raise BusinessException("导出文件存储路径无效")
    return target


def _write_file(storage_key: str, content: bytes) -> Path:
    target = _resolve_storage_key(storage_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f"{target.suffix}.tmp")
    temporary.write_bytes(content)
    temporary.replace(target)
    return target


def _json_safe(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    return value


def _serialize(job: ExportJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "original_name": job.original_name,
        "mime_type": job.mime_type,
        "size_bytes": job.size_bytes,
        "item_count": job.item_count,
        "expires_at": job.expires_at,
        "downloaded_at": job.downloaded_at,
        "error_message": job.error_message,
        "created_at": job.created_at,
    }


def _selected_assets(asset_ids: Sequence[int], actor_id: int) -> list[Asset]:
    ids = sorted(set(asset_ids))
    if not ids:
        raise BusinessException("请选择要导出的资产")
    permission_service.require_permission(actor_id, "asset:view")
    rows = list(
        db.session.scalars(
            select(Asset)
            .where(Asset.id.in_(ids), asset_access_service.access_filter(actor_id))
            .order_by(Asset.id.asc())
        ).all()
    )
    if len(rows) != len(ids):
        raise BusinessException("部分资产不存在或超出当前数据权限")
    return rows


def _resolve_assets(payload: Mapping[str, Any], actor_id: int) -> list[Asset]:
    asset_ids = payload.get("asset_ids")
    if isinstance(asset_ids, list) and asset_ids:
        return _selected_assets(asset_ids, actor_id)
    filters = payload.get("filters")
    return asset_service.list_for_export(
        actor_id=actor_id,
        filters=filters if isinstance(filters, Mapping) else {},
    )


def _name_map(model: type[Any], ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    return {
        int(row.id): str(row.name)
        for row in db.session.scalars(select(model).where(model.id.in_(ids))).all()
    }


def _user_map(ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    return {
        row.id: row.nickname or row.username
        for row in db.session.scalars(select(User).where(User.id.in_(ids))).all()
    }


def _csv_bytes(assets: Sequence[Asset], actor_id: int) -> bytes:
    include_amount = permission_service.has_permission(actor_id, "asset:amount:view")
    organizations = _name_map(Organization, {row.organization_id for row in assets})
    categories = _name_map(AssetCategory, {row.category_id for row in assets})
    units = _name_map(Unit, {row.unit_id for row in assets if row.unit_id is not None})
    suppliers = _name_map(
        Supplier, {row.supplier_id for row in assets if row.supplier_id is not None}
    )
    sources = _name_map(
        AssetSource, {row.source_id for row in assets if row.source_id is not None}
    )
    locations = _name_map(
        AssetLocation,
        {row.location_id for row in assets if row.location_id is not None},
    )
    organization_ids = {
        row.usage_department_id for row in assets if row.usage_department_id is not None
    }
    departments = _name_map(Organization, organization_ids)
    user_ids = {
        value
        for row in assets
        for value in (row.manager_id, row.holder_user_id)
        if value is not None
    }
    users = _user_map(user_ids)

    output = StringIO(newline="")
    writer = csv.writer(output)
    headers = [
        "资产编码",
        "资产名称",
        "资产分类",
        "资产状态",
        "规格型号",
        "设备序列号",
        "RFID",
        "所属公司",
        "使用人",
        "使用部门",
        "存放地点",
        "责任管理员",
        "供应商",
        "资产来源",
        "计量单位",
        "购入日期",
        "信息完整度",
    ]
    if include_amount:
        headers.extend(["采购金额", "零金额原因"])
    headers.extend(["单据编号", "备注"])
    writer.writerow(headers)
    for asset in assets:
        row: list[object] = [
            asset.asset_code,
            asset.asset_name,
            categories.get(asset.category_id, ""),
            asset.status,
            asset.specification_model or "",
            asset.serial_number or "",
            asset.rfid_tag or "",
            organizations.get(asset.organization_id, ""),
            users.get(asset.holder_user_id or -1, ""),
            departments.get(asset.usage_department_id or -1, ""),
            locations.get(asset.location_id or -1, ""),
            users.get(asset.manager_id, ""),
            suppliers.get(asset.supplier_id or -1, ""),
            sources.get(asset.source_id or -1, ""),
            units.get(asset.unit_id or -1, ""),
            asset.purchase_date.isoformat(),
            asset.data_completeness,
        ]
        if include_amount:
            row.extend([f"{asset.original_amount:.2f}", asset.zero_amount_reason or ""])
        row.extend([asset.receipt_no or "", asset.remark or ""])
        writer.writerow(row)
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _pdf_text(value: str) -> str:
    return value.encode("utf-16-be").hex().upper()


def _code39_value(value: str) -> str:
    normalized = "".join(
        character if character in _CODE39_MASKS and character != "*" else "-"
        for character in value.upper()
    )
    return f"*{normalized}*"


def _barcode_commands(
    value: str, *, x: float, y: float, width: float, height: float
) -> list[str]:
    encoded = _code39_value(value)
    narrow = 1.0
    wide = 2.4
    gap = 1.0
    units = 0.0
    for character in encoded:
        mask = _CODE39_MASKS[character]
        units += sum(
            wide if mask & (1 << (8 - index)) else narrow for index in range(9)
        )
        units += gap
    scale = width / units
    cursor = x
    commands: list[str] = ["0 0 0 rg"]
    for character in encoded:
        mask = _CODE39_MASKS[character]
        for index in range(9):
            element_width = (wide if mask & (1 << (8 - index)) else narrow) * scale
            if index % 2 == 0:
                commands.append(
                    f"{cursor:.2f} {y:.2f} {element_width:.2f} {height:.2f} re f"
                )
            cursor += element_width
        cursor += gap * scale
    return commands


def _label_content(asset: Asset, company_name: str) -> bytes:
    company = company_name[:24] or "资产管理"
    asset_name = asset.asset_name[:28]
    serial = (asset.serial_number or "无序列号")[:32]
    detail_path = f"/assets/{asset.id}"
    commands = [
        "q",
        "0.97 0.98 1 rg 0 0 226.77 85.04 re f",
        "0.13 0.32 0.63 RG 0.7 w 4 4 218.77 77.04 re S",
        f"BT /F1 8 Tf 8 70 Td <{_pdf_text(company)}> Tj ET",
        f"BT /F1 9 Tf 8 57 Td <{_pdf_text(asset_name)}> Tj ET",
        f"BT /F1 6.8 Tf 8 47 Td <{_pdf_text('序列号：' + serial)}> Tj ET",
        f"BT /F2 5.8 Tf 156 69 Td <{_pdf_text(detail_path)}> Tj ET",
    ]
    commands.extend(
        _barcode_commands(asset.asset_code, x=8, y=15, width=210, height=25)
    )
    commands.extend(
        [
            f"BT /F2 7 Tf 8 7 Td <{_pdf_text(asset.asset_code)}> Tj ET",
            "Q",
        ]
    )
    return "\n".join(commands).encode("ascii")


def _pdf_bytes(assets: Sequence[Asset]) -> bytes:
    company_names = _name_map(Organization, {row.organization_id for row in assets})
    objects: list[bytes] = []
    page_object_ids = [5 + index * 2 for index in range(len(assets))]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{object_id} 0 R" for object_id in page_object_ids)
    objects.append(
        f"<< /Type /Pages /Kids [{kids}] /Count {len(assets)} >>".encode("ascii")
    )
    objects.append(
        b"<< /Type /Font /Subtype /Type0 /BaseFont /STSong-Light "
        b"/Encoding /UniGB-UCS2-H /DescendantFonts [4 0 R] >>"
    )
    objects.append(
        b"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /STSong-Light "
        b"/CIDSystemInfo << /Registry (Adobe) /Ordering (GB1) /Supplement 4 >> >>"
    )
    for index, asset in enumerate(assets):
        content_object_id = page_object_ids[index] + 1
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 226.77 85.04] "
                "/Resources << /Font << /F1 3 0 R /F2 3 0 R >> >> "
                f"/Contents {content_object_id} 0 R >>"
            ).encode("ascii")
        )
        content = _label_content(asset, company_names.get(asset.organization_id, ""))
        objects.append(
            f"<< /Length {len(content)} >>\nstream\n".encode("ascii")
            + content
            + b"\nendstream"
        )

    result = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(len(result))
        result.extend(f"{object_id} 0 obj\n".encode("ascii"))
        result.extend(body)
        result.extend(b"\nendobj\n")
    xref_offset = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    result.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    result.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(result)


def create(payload: Mapping[str, Any], actor_id: int) -> dict[str, Any]:
    job_type = str(payload["job_type"])
    permission_code = "asset:export" if job_type == _ASSET_CSV else "asset:label:print"
    permission_service.require_permission(actor_id, permission_code)
    assets = _resolve_assets(payload, actor_id)
    if not assets:
        raise BusinessException("当前条件下没有可导出的资产")
    if job_type == _LABEL_PDF and len(assets) > _MAX_LABEL_ASSETS:
        raise BusinessException(f"单次最多生成 {_MAX_LABEL_ASSETS} 张标签")

    now = utc_now()
    retention_hours = int(current_app.config.get("EXPORT_RETENTION_HOURS", 24))
    suffix = ".csv" if job_type == _ASSET_CSV else ".pdf"
    mime_type = (
        "text/csv; charset=utf-8" if job_type == _ASSET_CSV else "application/pdf"
    )
    timestamp = now.astimezone(timezone(timedelta(hours=8))).strftime("%Y%m%d-%H%M%S")
    original_name = (
        f"资产台账-{timestamp}{suffix}"
        if job_type == _ASSET_CSV
        else f"资产条码标签-{timestamp}{suffix}"
    )
    storage_key = f"{now:%Y/%m/%d}/{uuid4().hex}{suffix}"
    snapshot = {
        "asset_ids": [asset.id for asset in assets],
        "filters": _json_safe(payload.get("filters") or {}),
    }
    job = ExportJob(
        job_type=job_type,
        status=_PROCESSING,
        created_by=actor_id,
        filter_snapshot=snapshot,
        original_name=original_name,
        storage_key=storage_key,
        mime_type=mime_type,
        item_count=len(assets),
        expires_at=now + timedelta(hours=retention_hours),
    )
    db.session.add(job)
    db.session.commit()

    target: Path | None = None
    try:
        content = (
            _csv_bytes(assets, actor_id)
            if job_type == _ASSET_CSV
            else _pdf_bytes(assets)
        )
        target = _write_file(storage_key, content)
        job.status = _SUCCESS
        job.size_bytes = len(content)
        audit_service.record_resource_change(
            action="ASSET_EXPORT_CREATE"
            if job_type == _ASSET_CSV
            else "ASSET_LABEL_CREATE",
            resource_type="export_job",
            resource_id=job.id,
            actor_id=actor_id,
            before_data=None,
            after_data={
                "job_type": job.job_type,
                "item_count": job.item_count,
                "expires_at": job.expires_at.isoformat(),
            },
        )
        lifecycle_type = (
            "ASSET_EXPORT" if job_type == _ASSET_CSV else "ASSET_LABEL_PRINT"
        )
        for asset in assets:
            audit_service.record_asset_lifecycle(
                asset_id=asset.id,
                operation_type=lifecycle_type,
                request_no=f"EXP-{job.id}",
                actor_id=actor_id,
                before_data={"asset_code": asset.asset_code},
                after_data={
                    "export_job_id": job.id,
                    "job_type": job.job_type,
                    "original_name": job.original_name,
                },
            )
        db.session.commit()
        return _serialize(job)
    except Exception as exc:
        db.session.rollback()
        if target is not None and target.exists():
            target.unlink()
        failed = db.session.get(ExportJob, job.id)
        if failed is not None:
            failed.status = _FAILED
            failed.error_message = str(exc)[:2000]
            db.session.commit()
        if isinstance(exc, BusinessException):
            raise
        raise BusinessException("导出文件生成失败") from exc


def page(*, actor_id: int, page_index: int, size: int) -> PageResult:
    permission_codes = permission_service.get_user_permissions(actor_id)
    if not {"asset:export", "asset:label:print"} & permission_codes:
        raise BusinessException("无权查看导出任务", result_code=ResultCode.FORBIDDEN)
    statement = (
        select(ExportJob)
        .where(ExportJob.created_by == actor_id)
        .order_by(ExportJob.id.desc())
    )
    total = int(
        db.session.scalar(
            select(db.func.count(ExportJob.id)).where(ExportJob.created_by == actor_id)
        )
        or 0
    )
    rows = list(
        db.session.scalars(statement.offset(page_index * size).limit(size)).all()
    )
    return PageResult(
        items=[_serialize(row) for row in rows],
        total=total,
        page=page_index,
        size=size,
    )


def _is_expired(value: datetime, now: datetime) -> bool:
    normalized = (
        value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    )
    return normalized <= now


def download_target(export_id: int, actor_id: int) -> DownloadTarget:
    job = db.session.get(ExportJob, export_id)
    if job is None or job.created_by != actor_id:
        raise BusinessException("导出任务不存在", result_code=ResultCode.NOT_FOUND)
    permission_code = (
        "asset:export" if job.job_type == _ASSET_CSV else "asset:label:print"
    )
    permission_service.require_permission(actor_id, permission_code)
    if job.status != _SUCCESS:
        raise BusinessException("导出文件当前不可下载")
    if _is_expired(job.expires_at, utc_now()):
        job.status = _EXPIRED
        db.session.commit()
        raise BusinessException("导出文件已过期，请重新生成")
    path = _resolve_storage_key(job.storage_key)
    if not path.is_file():
        raise BusinessException("导出文件不存在", result_code=ResultCode.NOT_FOUND)
    job.downloaded_at = utc_now()
    audit_service.record_resource_change(
        action="ASSET_EXPORT_DOWNLOAD",
        resource_type="export_job",
        resource_id=job.id,
        actor_id=actor_id,
        before_data=None,
        after_data={"job_type": job.job_type, "item_count": job.item_count},
    )
    db.session.commit()
    return DownloadTarget(
        path=path,
        original_name=job.original_name,
        mime_type=job.mime_type,
    )


def cleanup_expired_files(*, now: datetime | None = None) -> int:
    current = now or utc_now()
    rows = list(
        db.session.scalars(
            select(ExportJob).where(
                ExportJob.status == _SUCCESS,
                ExportJob.expires_at <= current,
            )
        ).all()
    )
    removed = 0
    for job in rows:
        path = _resolve_storage_key(job.storage_key)
        if path.is_file():
            path.unlink()
            removed += 1
        job.status = _EXPIRED
        audit_service.record_resource_change(
            action="ASSET_EXPORT_EXPIRE",
            resource_type="export_job",
            resource_id=job.id,
            actor_id=job.created_by,
            before_data={"status": _SUCCESS},
            after_data={"status": _EXPIRED, "cleanup_source": "maintenance_command"},
        )
    db.session.commit()
    return removed


__all__ = [
    "DownloadTarget",
    "cleanup_expired_files",
    "create",
    "download_target",
    "page",
]
