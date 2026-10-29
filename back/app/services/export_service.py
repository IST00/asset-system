"""Persistent CSV exports and 65×30 mm QR/Code 39 asset label PDFs."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4
from urllib.parse import quote

from flask import current_app
import qrcode
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import select

from app.common import BusinessException, PageResult, ResultCode
from app.extensions import db
from app.models import (
    Asset,
    AssetCategory,
    AssetLocation,
    AssetRepairRecord,
    AssetScrapRecord,
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
_REPAIR_CSV = "REPAIR_CSV"
_SCRAP_CSV = "SCRAP_CSV"
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


def _resolve_scrapped_assets(payload: Mapping[str, Any], actor_id: int) -> list[Asset]:
    asset_ids = payload.get("asset_ids")
    if isinstance(asset_ids, list) and asset_ids:
        assets = _selected_assets(asset_ids, actor_id)
        if any(asset.status != "SCRAPPED" for asset in assets):
            raise BusinessException(
                "报废资产导出只能选择已报废资产", result_code=ResultCode.BAD_REQUEST
            )
        return assets
    raw_filters = payload.get("filters")
    filters = dict(raw_filters) if isinstance(raw_filters, Mapping) else {}
    filters["status"] = "SCRAPPED"
    return asset_service.list_for_export(actor_id=actor_id, filters=filters)


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


def _scrap_csv_bytes(assets: Sequence[Asset], actor_id: int) -> bytes:
    """Build a disposal ledger from structured records with legacy fallback."""
    asset_ids = [asset.id for asset in assets]
    records = list(
        db.session.scalars(
            select(AssetScrapRecord)
            .where(AssetScrapRecord.asset_id.in_(asset_ids))
            .order_by(AssetScrapRecord.scrap_date.desc(), AssetScrapRecord.id.desc())
        ).all()
    )
    records_by_asset: dict[int, list[AssetScrapRecord]] = {}
    for record in records:
        records_by_asset.setdefault(record.asset_id, []).append(record)
    include_amount = permission_service.has_permission(actor_id, "asset:amount:view")
    organization_names = _name_map(
        Organization, {asset.organization_id for asset in assets}
    )
    category_names = _name_map(AssetCategory, {asset.category_id for asset in assets})
    user_names = _user_map(
        {record.confirmed_by for record in records if record.confirmed_by is not None}
    )
    output = StringIO(newline="")
    writer = csv.writer(output)
    headers = [
        "报废单号",
        "资产编码",
        "资产名称",
        "所属公司",
        "资产分类",
        "报废日期",
        "报废原因",
        "处置方式",
        "确认人",
        "确认时间",
    ]
    if include_amount:
        headers.append("回收金额")
    writer.writerow(headers)
    for asset in assets:
        asset_records = records_by_asset.get(asset.id, [])
        if asset_records:
            for record in asset_records:
                row: list[object] = [
                    record.scrap_no,
                    asset.asset_code,
                    asset.asset_name,
                    organization_names.get(asset.organization_id, ""),
                    category_names.get(asset.category_id, ""),
                    record.scrap_date.isoformat(),
                    record.reason,
                    record.disposition or "",
                    user_names.get(record.confirmed_by, ""),
                    record.confirmed_at.isoformat(),
                ]
                if include_amount:
                    row.append(f"{record.scrap_amount:.2f}")
                writer.writerow(row)
            continue

        # Assets created before the structured table was introduced still keep
        # the original JSON snapshot, so they remain exportable.
        legacy = asset.custom_attributes.get("scrap", {})
        legacy_record = legacy if isinstance(legacy, Mapping) else {}
        row = [
            "",
            asset.asset_code,
            asset.asset_name,
            organization_names.get(asset.organization_id, ""),
            category_names.get(asset.category_id, ""),
            str(legacy_record.get("scrap_date", "")),
            str(legacy_record.get("reason", "")),
            str(legacy_record.get("disposition", "")),
            "",
            "",
        ]
        if include_amount:
            row.append(str(legacy_record.get("scrap_amount", "")))
        writer.writerow(row)
    return ("\ufeff" + output.getvalue()).encode("utf-8")


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


def _repair_csv_bytes(assets: Sequence[Asset], actor_id: int) -> tuple[bytes, int]:
    """Build a repair ledger and return its bytes plus exported record count."""
    asset_ids = [asset.id for asset in assets]
    records = list(
        db.session.scalars(
            select(AssetRepairRecord)
            .where(AssetRepairRecord.asset_id.in_(asset_ids))
            .order_by(AssetRepairRecord.sent_at.desc(), AssetRepairRecord.id.desc())
        ).all()
    )
    include_amount = permission_service.has_permission(actor_id, "asset:amount:view")
    asset_map = {asset.id: asset for asset in assets}
    organization_names = _name_map(
        Organization, {asset.organization_id for asset in assets}
    )
    category_names = _name_map(AssetCategory, {asset.category_id for asset in assets})
    output = StringIO(newline="")
    writer = csv.writer(output)
    headers = [
        "维修单号",
        "资产编码",
        "资产名称",
        "所属公司",
        "资产分类",
        "维修前状态",
        "故障原因",
        "维修供应商",
        "送修时间",
        "完成时间",
        "维修结果",
        "确认人",
        "确认时间",
    ]
    if include_amount:
        headers.append("维修费用")
    writer.writerow(headers)
    user_names = _user_map(
        {record.confirmed_by for record in records if record.confirmed_by is not None}
    )
    for record in records:
        asset = asset_map[record.asset_id]
        row: list[object] = [
            record.repair_no,
            asset.asset_code,
            asset.asset_name,
            organization_names.get(asset.organization_id, ""),
            category_names.get(asset.category_id, ""),
            record.before_status,
            record.fault_description,
            record.repair_supplier_name or "",
            record.sent_at.isoformat(),
            record.completed_at.isoformat() if record.completed_at else "",
            record.repair_result or "",
            user_names.get(record.confirmed_by or -1, ""),
            record.confirmed_at.isoformat() if record.confirmed_at else "",
        ]
        if include_amount:
            row.append(
                f"{record.repair_cost:.2f}" if record.repair_cost is not None else ""
            )
        writer.writerow(row)
    return ("\ufeff" + output.getvalue()).encode("utf-8"), len(records)


_LABEL_WIDTH = 184.28
_LABEL_HEIGHT = 85.04
_LABEL_LEFT = 3.0
_LABEL_BOTTOM = 3.0
_LABEL_RIGHT = _LABEL_WIDTH - _LABEL_LEFT
_LABEL_TOP = _LABEL_HEIGHT - _LABEL_BOTTOM
_LABEL_TABLE_SPLIT = 130.0
_LABEL_VALUE_SPLIT = 43.5
_LABEL_FONT_NAME = "NotoSansCJKsc"
_LABEL_FONT_PATH = (
    Path(__file__).resolve().parents[1]
    / "static"
    / "fonts"
    / "NotoSansCJKsc-Regular.ttf"
)


def _label_font_name() -> str:
    if _LABEL_FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        if not _LABEL_FONT_PATH.is_file():
            raise RuntimeError(f"标签字体文件不存在: {_LABEL_FONT_PATH}")
        pdfmetrics.registerFont(TTFont(_LABEL_FONT_NAME, str(_LABEL_FONT_PATH)))
    return _LABEL_FONT_NAME


def _code39_value(value: str) -> str:
    normalized = "".join(
        character if character in _CODE39_MASKS and character != "*" else "-"
        for character in value.upper()
    )
    return f"*{normalized}*"


def _draw_barcode(
    canvas: Canvas, value: str, *, x: float, y: float, width: float, height: float
) -> None:
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
    canvas.setFillColorRGB(0, 0, 0)
    for character in encoded:
        mask = _CODE39_MASKS[character]
        for index in range(9):
            element_width = (wide if mask & (1 << (8 - index)) else narrow) * scale
            if index % 2 == 0:
                canvas.rect(cursor, y, element_width, height, stroke=0, fill=1)
            cursor += element_width
        cursor += gap * scale


def _draw_qr(canvas: Canvas, value: str, *, x: float, y: float, size: float) -> None:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=1,
        border=0,
    )
    qr.add_data(value)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    quiet_zone = 2
    module_size = size / (len(matrix) + quiet_zone * 2)
    canvas.setFillColorRGB(0, 0, 0)
    for row_index, row in enumerate(matrix):
        for column_index, is_dark in enumerate(row):
            if not is_dark:
                continue
            rect_x = x + (column_index + quiet_zone) * module_size
            rect_y = y + (len(matrix) - row_index - 1 + quiet_zone) * module_size
            canvas.rect(rect_x, rect_y, module_size, module_size, stroke=0, fill=1)


def _draw_text(
    canvas: Canvas,
    value: str,
    *,
    font_size: float,
    x: float,
    y: float,
    max_width: float | None = None,
) -> None:
    font_name = _label_font_name()
    if max_width is not None:
        measured_width = pdfmetrics.stringWidth(value, font_name, font_size)
        if measured_width > max_width:
            font_size *= max_width / measured_width
    canvas.setFillColorRGB(0, 0, 0)
    canvas.setFont(font_name, font_size)
    canvas.drawString(x, y, value)


def _draw_centered_text(
    canvas: Canvas,
    value: str,
    *,
    font_size: float,
    center_x: float,
    y: float,
    max_width: float | None = None,
) -> None:
    font_name = _label_font_name()
    if max_width is not None:
        measured_width = pdfmetrics.stringWidth(value, font_name, font_size)
        if measured_width > max_width:
            font_size *= max_width / measured_width
    canvas.setFillColorRGB(0, 0, 0)
    canvas.setFont(font_name, font_size)
    text_width = pdfmetrics.stringWidth(value, font_name, font_size)
    x = max(_LABEL_LEFT + 1.5, center_x - text_width / 2)
    canvas.drawString(x, y, value)


def _asset_qr_value(asset: Asset, qr_base_url: str | None = None) -> str:
    """Build a portable scan payload for mobile camera and app scanners.

    The first field is always the asset code so the SPA can look the asset up
    again even when the frontend deployment origin changes.  The optional
    second field is the printed Code 39 value.
    """
    base_url = (
        str(qr_base_url or current_app.config.get("ASSET_QR_BASE_URL") or "")
        .strip()
        .rstrip("/")
    )
    prefix = f"{base_url}/scan-use" if base_url else "scan-use"
    barcode_value = asset.serial_number or asset.asset_code or "-"
    return (
        f"{prefix}?asset_code={quote(str(asset.asset_code), safe='')}"
        f"&barcode={quote(str(barcode_value), safe='')}"
    )


def _draw_label(
    canvas: Canvas, asset: Asset, company_name: str, *, qr_base_url: str | None = None
) -> None:
    title = f"{company_name or '资产管理'}固定资产标签"
    asset_code = asset.asset_code[:24]
    asset_name = asset.asset_name
    purchase_date = asset.purchase_date.isoformat()
    barcode_value = (asset.serial_number or asset.asset_code or "-")[:32]
    qr_value = _asset_qr_value(asset, qr_base_url)

    canvas.setFillColorRGB(1, 1, 1)
    canvas.rect(0, 0, _LABEL_WIDTH, _LABEL_HEIGHT, stroke=0, fill=1)
    canvas.setStrokeColorRGB(0, 0, 0)
    canvas.setLineWidth(0.8)
    canvas.rect(
        _LABEL_LEFT,
        _LABEL_BOTTOM,
        _LABEL_RIGHT - _LABEL_LEFT,
        _LABEL_TOP - _LABEL_BOTTOM,
        stroke=1,
        fill=0,
    )
    canvas.line(_LABEL_TABLE_SPLIT, 30.0, _LABEL_TABLE_SPLIT, _LABEL_TOP)
    canvas.line(_LABEL_LEFT, 68.8, _LABEL_TABLE_SPLIT, 68.8)
    canvas.line(_LABEL_LEFT, 56.1, _LABEL_TABLE_SPLIT, 56.1)
    canvas.line(_LABEL_LEFT, 43.4, _LABEL_TABLE_SPLIT, 43.4)
    canvas.line(_LABEL_LEFT, 30.0, _LABEL_RIGHT, 30.0)
    canvas.line(_LABEL_VALUE_SPLIT, 68.8, _LABEL_VALUE_SPLIT, 30.0)

    _draw_centered_text(
        canvas, title, font_size=9, center_x=66.5, y=73.25, max_width=125.0
    )
    _draw_text(canvas, "资产编号", font_size=8.5, x=7.0, y=59.5)
    _draw_text(canvas, asset_code, font_size=8.5, x=46.0, y=59.5)
    _draw_text(canvas, "名称", font_size=8.5, x=11.5, y=46.8)
    # The value area runs from the label separator to the QR boundary.  Keep a
    # small right margin so long CJK names shrink instead of crossing either line.
    _draw_text(canvas, asset_name, font_size=8.5, x=46.0, y=46.8, max_width=82.0)
    _draw_text(canvas, "日期", font_size=8.5, x=11.5, y=33.4)
    _draw_text(canvas, purchase_date, font_size=8.5, x=46.0, y=33.4)

    _draw_qr(canvas, qr_value, x=130.5, y=32.0, size=48.0)
    _draw_barcode(canvas, barcode_value, x=50.0, y=13.0, width=84.0, height=13.0)
    _draw_centered_text(canvas, barcode_value, font_size=7.2, center_x=92.14, y=6.8)


def _pdf_bytes(assets: Sequence[Asset], *, qr_base_url: str | None = None) -> bytes:
    company_names = _name_map(Organization, {row.organization_id for row in assets})
    output = BytesIO()
    canvas = Canvas(
        output,
        pagesize=(_LABEL_WIDTH, _LABEL_HEIGHT),
        pageCompression=0,
        pdfVersion=(1, 4),
    )
    canvas.setTitle("资产条码标签")
    for asset in assets:
        _draw_label(
            canvas,
            asset,
            company_names.get(asset.organization_id, ""),
            qr_base_url=qr_base_url,
        )
        canvas.showPage()
    canvas.save()
    return output.getvalue()


def create(payload: Mapping[str, Any], actor_id: int) -> dict[str, Any]:
    job_type = str(payload["job_type"])
    permission_code = {
        _ASSET_CSV: "asset:export",
        _REPAIR_CSV: "repair:export",
        _SCRAP_CSV: "scrap:export",
        _LABEL_PDF: "asset:label:print",
    }.get(job_type)
    if permission_code is None:
        raise BusinessException("不支持的导出类型")
    permission_service.require_permission(actor_id, permission_code)
    assets = (
        _resolve_scrapped_assets(payload, actor_id)
        if job_type == _SCRAP_CSV
        else _resolve_assets(payload, actor_id)
    )
    if not assets:
        raise BusinessException("当前条件下没有可导出的资产")
    if job_type == _LABEL_PDF and len(assets) > _MAX_LABEL_ASSETS:
        raise BusinessException(f"单次最多生成 {_MAX_LABEL_ASSETS} 张标签")

    now = utc_now()
    retention_hours = int(current_app.config.get("EXPORT_RETENTION_HOURS", 24))
    suffix = ".pdf" if job_type == _LABEL_PDF else ".csv"
    mime_type = (
        "application/pdf" if job_type == _LABEL_PDF else "text/csv; charset=utf-8"
    )
    timestamp = now.astimezone(timezone(timedelta(hours=8))).strftime("%Y%m%d-%H%M%S")
    original_name = (
        f"资产台账-{timestamp}{suffix}"
        if job_type == _ASSET_CSV
        else (
            f"维修记录-{timestamp}{suffix}"
            if job_type == _REPAIR_CSV
            else (
                f"报废资产-{timestamp}{suffix}"
                if job_type == _SCRAP_CSV
                else f"资产条码标签-{timestamp}{suffix}"
            )
        )
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
        if job_type == _ASSET_CSV:
            content = _csv_bytes(assets, actor_id)
        elif job_type == _REPAIR_CSV:
            content, repair_count = _repair_csv_bytes(assets, actor_id)
            if repair_count == 0:
                raise BusinessException("当前资产没有维修记录")
            job.item_count = repair_count
        elif job_type == _SCRAP_CSV:
            content = _scrap_csv_bytes(assets, actor_id)
        else:
            content = _pdf_bytes(assets)
        target = _write_file(storage_key, content)
        job.status = _SUCCESS
        job.size_bytes = len(content)
        audit_service.record_resource_change(
            action=(
                "ASSET_EXPORT_CREATE"
                if job_type == _ASSET_CSV
                else (
                    "REPAIR_EXPORT_CREATE"
                    if job_type == _REPAIR_CSV
                    else (
                        "SCRAP_EXPORT_CREATE"
                        if job_type == _SCRAP_CSV
                        else "ASSET_LABEL_CREATE"
                    )
                )
            ),
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
            "ASSET_EXPORT"
            if job_type == _ASSET_CSV
            else (
                "REPAIR_EXPORT"
                if job_type == _REPAIR_CSV
                else ("SCRAP_EXPORT" if job_type == _SCRAP_CSV else "ASSET_LABEL_PRINT")
            )
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
    if (
        not {
            "asset:export",
            "repair:export",
            "scrap:export",
            "asset:label:print",
        }
        & permission_codes
    ):
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


def preview_labels(
    asset_ids: Sequence[int],
    actor_id: int,
    *,
    qr_base_url: str | None = None,
) -> DownloadTarget:
    """Generate an ephemeral inline label PDF for immediate browser preview."""
    permission_service.require_permission(actor_id, "asset:label:print")
    assets = _selected_assets(asset_ids, actor_id)
    if len(assets) > _MAX_LABEL_ASSETS:
        raise BusinessException(f"单次最多生成 {_MAX_LABEL_ASSETS} 张标签")
    now = utc_now()
    target = _write_file(
        f"{now:%Y/%m/%d}/preview/{uuid4().hex}.pdf",
        _pdf_bytes(assets, qr_base_url=qr_base_url),
    )
    audit_service.record_resource_change(
        action="ASSET_LABEL_PRINT",
        resource_type="export",
        resource_id="preview",
        before_data=None,
        after_data={
            "asset_ids": [asset.id for asset in assets],
            "preview": True,
            "qr_base_url": qr_base_url,
        },
        actor_id=actor_id,
    )
    return DownloadTarget(
        path=target,
        original_name=f"资产条码标签-{now.astimezone(timezone(timedelta(hours=8))):%Y%m%d-%H%M%S}.pdf",
        mime_type="application/pdf",
    )


def download_target(export_id: int, actor_id: int) -> DownloadTarget:
    job = db.session.get(ExportJob, export_id)
    if job is None or job.created_by != actor_id:
        raise BusinessException("导出任务不存在", result_code=ResultCode.NOT_FOUND)
    permission_code = {
        _ASSET_CSV: "asset:export",
        _REPAIR_CSV: "repair:export",
        _SCRAP_CSV: "scrap:export",
        _LABEL_PDF: "asset:label:print",
    }.get(job.job_type)
    if permission_code is None:
        raise BusinessException("不支持的导出类型")
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
        action=(
            "ASSET_EXPORT_DOWNLOAD"
            if job.job_type == _ASSET_CSV
            else (
                "REPAIR_EXPORT_DOWNLOAD"
                if job.job_type == _REPAIR_CSV
                else (
                    "SCRAP_EXPORT_DOWNLOAD"
                    if job.job_type == _SCRAP_CSV
                    else "ASSET_LABEL_DOWNLOAD"
                )
            )
        ),
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
    preview_root = _storage_root() / "preview"
    for preview_root_item in preview_root.rglob("*.pdf"):
        if (
            preview_root_item.is_file()
            and preview_root_item.stat().st_mtime
            < (current - timedelta(minutes=30)).timestamp()
        ):
            preview_root_item.unlink()
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
