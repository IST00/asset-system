"""Server-side spreadsheet previews and atomic import confirmation."""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Mapping, Sequence, cast
from uuid import uuid4
from xml.etree import ElementTree
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from sqlalchemy import func, select

from app.common import BusinessException, PageResult, ResultCode
from app.enums import AssetDataCompleteness, AssetStatus, RecordStatus
from app.extensions import db
from app.models import (
    Asset,
    AssetCategory,
    AssetLocation,
    AssetSource,
    ImportJob,
    Organization,
    Supplier,
    Unit,
    User,
)
from app.models.mixins import utc_now
from app.services import (
    asset_code_service,
    asset_data_service,
    audit_service,
    organization_service,
    permission_service,
)

_ASSET = "ASSET"
_ORGANIZATION = "ORGANIZATION"
_CATEGORY = "CATEGORY"
_PREVIEW_READY = "PREVIEW_READY"
_VALIDATION_FAILED = "VALIDATION_FAILED"
_CONFIRMED = "CONFIRMED"
_MAX_BYTES = 10 * 1024 * 1024
_MAX_ROWS = 2000

_PERMISSIONS = {
    _ASSET: "asset:import",
    _ORGANIZATION: "organization:import",
    _CATEGORY: "asset-category:import",
}

_HEADERS = {
    _ASSET: [
        "资产编码",
        "所属公司编码",
        "资产名称",
        "资产分类编码",
        "计量单位编码",
        "原值",
        "零金额原因",
        "采购日期",
        "供应商编码或名称",
        "责任管理员账号",
        "资产来源编码",
        "存放地点编码",
        "规格型号",
        "序列号",
        "RFID",
        "备注",
    ],
    _ORGANIZATION: ["编码", "名称", "上级编码", "状态"],
    _CATEGORY: [
        "编码",
        "名称",
        "上级编码",
        "使用期限（月）",
        "默认计量单位编码",
        "状态",
    ],
}

_REQUIRED = {
    _ASSET: {
        "所属公司编码",
        "资产名称",
        "资产分类编码",
        "原值",
        "采购日期",
        "责任管理员账号",
    },
    _ORGANIZATION: {"编码", "名称", "状态"},
    _CATEGORY: {"编码", "名称", "使用期限（月）", "默认计量单位编码", "状态"},
}


def _permission(import_type: str, actor_id: int) -> None:
    code = _PERMISSIONS.get(import_type)
    if code is None:
        raise BusinessException("不支持的导入类型", result_code=ResultCode.BAD_REQUEST)
    permission_service.require_permission(actor_id, code)


def _job_no() -> str:
    return f"IMP{datetime.now(tz=timezone.utc):%Y%m%d}{uuid4().hex[:10].upper()}"


def _normalized_status(value: str) -> str | None:
    normalized = value.strip().upper()
    if normalized in {"ENABLED", "启用", "正常"}:
        return RecordStatus.ENABLED.value
    if normalized in {"DISABLED", "停用", "禁用"}:
        return RecordStatus.DISABLED.value
    return None


def _serialize(job: ImportJob, *, detail: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": job.id,
        "job_no": job.job_no,
        "import_type": job.import_type,
        "status": job.status,
        "original_name": job.original_name,
        "file_format": job.file_format,
        "row_count": job.row_count,
        "error_count": job.error_count,
        "warning_count": job.warning_count,
        "create_count": job.create_count,
        "update_count": job.update_count,
        "unchanged_count": job.unchanged_count,
        "created_by": job.created_by,
        "confirmed_by": job.confirmed_by,
        "confirmed_at": job.confirmed_at,
        "version": job.version,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "result": job.result_data,
    }
    if detail:
        result["rows"] = job.preview_data
    return result


def _column_index(reference: str) -> int:
    letters = "".join(character for character in reference if character.isalpha())
    result = 0
    for character in letters.upper():
        result = result * 26 + ord(character) - 64
    return result - 1


def _xlsx_rows(content: bytes) -> list[list[str]]:
    try:
        archive = ZipFile(BytesIO(content))
    except BadZipFile as exc:
        raise BusinessException("XLSX 文件格式损坏") from exc
    with archive:
        try:
            shared: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                shared_root = ElementTree.fromstring(
                    archive.read("xl/sharedStrings.xml")
                )
                for item in shared_root.findall("{*}si"):
                    shared.append(
                        "".join(node.text or "" for node in item.findall(".//{*}t"))
                    )
            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            first_sheet = workbook.find(".//{*}sheet")
            if first_sheet is None:
                raise BusinessException("XLSX 中没有工作表")
            relation_id = first_sheet.attrib.get(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            )
            relationships = ElementTree.fromstring(
                archive.read("xl/_rels/workbook.xml.rels")
            )
            target = None
            for relation in relationships.findall("{*}Relationship"):
                if relation.attrib.get("Id") == relation_id:
                    target = relation.attrib.get("Target")
                    break
            if not target:
                raise BusinessException("XLSX 工作表关系无效")
            sheet_path = target.lstrip("/")
            if not sheet_path.startswith("xl/"):
                sheet_path = f"xl/{sheet_path}"
            root = ElementTree.fromstring(archive.read(sheet_path))
        except KeyError as exc:
            raise BusinessException("XLSX 缺少必要的工作表结构") from exc

        rows: list[list[str]] = []
        for row in root.findall(".//{*}row"):
            values: list[str] = []
            for cell in row.findall("{*}c"):
                index = _column_index(cell.attrib.get("r", "A1"))
                while len(values) <= index:
                    values.append("")
                cell_type = cell.attrib.get("t")
                value_node = cell.find("{*}v")
                if cell_type == "inlineStr":
                    text = "".join(node.text or "" for node in cell.findall(".//{*}t"))
                elif value_node is None:
                    text = ""
                elif cell_type == "s":
                    try:
                        text = shared[int(value_node.text or "0")]
                    except (IndexError, ValueError):
                        text = ""
                else:
                    text = value_node.text or ""
                values[index] = text.strip()
            if any(values):
                rows.append(values)
        return rows


def _tabular_rows(
    content: bytes, original_name: str
) -> tuple[list[dict[str, str]], str]:
    suffix = Path(original_name).suffix.lower()
    if suffix == ".csv":
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise BusinessException("CSV 必须使用 UTF-8 编码") from exc
        matrix = [[cell.strip() for cell in row] for row in csv.reader(StringIO(text))]
        file_format = "CSV"
    elif suffix == ".xlsx":
        matrix = _xlsx_rows(content)
        file_format = "XLSX"
    else:
        raise BusinessException("仅支持 .csv 或 .xlsx 文件")
    matrix = [row for row in matrix if any(cell.strip() for cell in row)]
    if not matrix:
        raise BusinessException("导入文件为空")
    headers = [item.strip() for item in matrix[0]]
    if len(headers) != len(set(headers)):
        raise BusinessException("导入文件存在重复列名")
    if len(matrix) == 1:
        raise BusinessException("导入文件只有表头，没有数据")
    if len(matrix) - 1 > _MAX_ROWS:
        raise BusinessException(f"单次导入最多 {_MAX_ROWS} 行")
    return (
        [
            {
                header: (row[index].strip() if index < len(row) else "")
                for index, header in enumerate(headers)
            }
            for row in matrix[1:]
        ],
        file_format,
    )


def _require_headers(import_type: str, rows: Sequence[Mapping[str, str]]) -> None:
    headers = set(rows[0]) if rows else set()
    missing = _REQUIRED[import_type] - headers
    if missing:
        raise BusinessException(f"模板缺少列：{'、'.join(sorted(missing))}")


def _rows_by_code(model: type[Any]) -> dict[str, Any]:
    return {str(row.code): row for row in db.session.scalars(select(model)).all()}


def _rows_by_name(model: type[Any]) -> dict[str, Any]:
    return {str(row.name): row for row in db.session.scalars(select(model)).all()}


def _parse_date(value: str) -> date | None:
    normalized = value.strip()
    try:
        return date.fromisoformat(normalized)
    except ValueError:
        try:
            serial = float(normalized)
        except ValueError:
            return None
        if serial < 1 or serial > 2958465:
            return None
        return (datetime(1899, 12, 30) + timedelta(days=serial)).date()


def _asset_preview(source_rows: Sequence[Mapping[str, str]]) -> list[dict[str, Any]]:
    organizations = _rows_by_code(Organization)
    categories = _rows_by_code(AssetCategory)
    units = _rows_by_code(Unit)
    sources = _rows_by_code(AssetSource)
    locations = _rows_by_code(AssetLocation)
    suppliers_by_code = _rows_by_code(Supplier)
    suppliers_by_name = _rows_by_name(Supplier)
    users = {row.username: row for row in db.session.scalars(select(User)).all()}
    existing_codes = set(db.session.scalars(select(Asset.asset_code)).all())
    existing_serials = set(
        value
        for value in db.session.scalars(select(Asset.normalized_serial)).all()
        if value
    )
    existing_rfids = set(
        value for value in db.session.scalars(select(Asset.rfid_tag)).all() if value
    )
    seen_codes: set[str] = set()
    seen_serials: set[str] = set()
    seen_rfids: set[str] = set()
    preview: list[dict[str, Any]] = []

    for index, source in enumerate(source_rows, start=2):
        values = {str(key): str(value).strip() for key, value in source.items()}
        errors: list[str] = []
        warnings: list[str] = []
        for header in _REQUIRED[_ASSET]:
            if not values.get(header):
                errors.append(f"{header}不能为空")
        organization = organizations.get(values.get("所属公司编码", ""))
        category = categories.get(values.get("资产分类编码", ""))
        manager = users.get(values.get("责任管理员账号", ""))
        if organization is None or organization.status != RecordStatus.ENABLED.value:
            errors.append("所属公司编码不存在或已停用")
        if category is None or category.status != RecordStatus.ENABLED.value:
            errors.append("资产分类编码不存在或已停用")
        if manager is None or not manager.enabled:
            errors.append("责任管理员账号不存在或已停用")

        unit_text = values.get("计量单位编码", "")
        source_text = values.get("资产来源编码", "")
        location_text = values.get("存放地点编码", "")
        unit = units.get(unit_text) if unit_text else None
        asset_source = sources.get(source_text) if source_text else None
        location = locations.get(location_text) if location_text else None
        if unit is None:
            warnings.append(
                "计量单位待补充" if not unit_text else "计量单位未匹配，原值已保留"
            )
        elif unit.status != RecordStatus.ENABLED.value:
            errors.append("计量单位已停用")
        if asset_source is None:
            warnings.append(
                "资产来源待补充" if not source_text else "资产来源未匹配，原值已保留"
            )
        elif asset_source.status != RecordStatus.ENABLED.value:
            errors.append("资产来源已停用")
        if location is None:
            warnings.append(
                "存放地点待补充" if not location_text else "存放地点未匹配，原值已保留"
            )
        elif (
            location.status != RecordStatus.ENABLED.value or not location.is_selectable
        ):
            errors.append("存放地点已停用或不可选择")

        supplier_text = values.get("供应商编码或名称", "")
        supplier = suppliers_by_code.get(supplier_text) or suppliers_by_name.get(
            supplier_text
        )
        if supplier_text and (
            supplier is None or supplier.status != RecordStatus.ENABLED.value
        ):
            errors.append("供应商编码或名称未匹配")

        amount: Decimal | None = None
        try:
            amount = Decimal(values.get("原值", ""))
            if amount < 0:
                errors.append("原值不能小于 0")
            if amount == 0 and not values.get("零金额原因"):
                errors.append("零金额资产必须填写原因")
        except InvalidOperation:
            errors.append("原值必须是合法数字")
        purchase_date = _parse_date(values.get("采购日期", ""))
        if purchase_date is None:
            errors.append("采购日期必须使用 YYYY-MM-DD 格式")

        asset_code = values.get("资产编码", "")
        if asset_code:
            if asset_code in existing_codes:
                errors.append("资产编码已存在")
            if asset_code in seen_codes:
                errors.append("资产编码在文件内重复")
            seen_codes.add(asset_code)
        serial = values.get("序列号", "").strip()
        normalized_serial = serial.lower() or None
        if normalized_serial:
            if normalized_serial in existing_serials:
                errors.append("序列号已存在")
            if normalized_serial in seen_serials:
                errors.append("序列号在文件内重复")
            seen_serials.add(normalized_serial)
        rfid = values.get("RFID", "").strip() or None
        if rfid:
            if rfid in existing_rfids:
                errors.append("RFID 已存在")
            if rfid in seen_rfids:
                errors.append("RFID 在文件内重复")
            seen_rfids.add(rfid)

        normalized: dict[str, Any] | None = None
        if (
            not errors
            and organization
            and category
            and manager
            and amount is not None
            and purchase_date
        ):
            normalized = {
                "asset_code": asset_code or None,
                "organization_id": organization.id,
                "asset_name": values["资产名称"],
                "category_id": category.id,
                "unit_id": unit.id if unit else None,
                "original_amount": str(amount.quantize(Decimal("0.01"))),
                "zero_amount_reason": values.get("零金额原因") or None,
                "purchase_date": purchase_date.isoformat(),
                "supplier_id": supplier.id if supplier else None,
                "manager_id": manager.id,
                "source_id": asset_source.id if asset_source else None,
                "location_id": location.id if location else None,
                "specification_model": values.get("规格型号") or None,
                "serial_number": serial or None,
                "normalized_serial": normalized_serial,
                "rfid_tag": rfid,
                "remark": values.get("备注") or None,
                "originals": {
                    "unit": unit_text or None,
                    "source": source_text or None,
                    "location": location_text or None,
                },
            }
        preview.append(
            {
                "line": index,
                "action": "CREATE",
                "values": values,
                "errors": errors,
                "warnings": warnings,
                "normalized": normalized,
            }
        )
    return preview


def _cycle_errors(rows: Sequence[dict[str, Any]]) -> dict[str, str]:
    parent_by_code = {
        str(row["values"].get("编码", "")): str(row["values"].get("上级编码", ""))
        for row in rows
        if row["values"].get("编码")
    }
    errors: dict[str, str] = {}
    for start in parent_by_code:
        seen: set[str] = set()
        current = start
        while current in parent_by_code and parent_by_code[current]:
            if current in seen:
                errors[start] = "上级编码形成循环关系"
                break
            seen.add(current)
            current = parent_by_code[current]
    return errors


def _master_preview(
    import_type: str, source_rows: Sequence[Mapping[str, str]]
) -> list[dict[str, Any]]:
    model = Organization if import_type == _ORGANIZATION else AssetCategory
    existing = _rows_by_code(model)
    units = _rows_by_code(Unit)
    input_codes = {str(row.get("编码", "")).strip() for row in source_rows}
    seen: set[str] = set()
    preview: list[dict[str, Any]] = []
    for index, source in enumerate(source_rows, start=2):
        values = {str(key): str(value).strip() for key, value in source.items()}
        errors: list[str] = []
        for header in _REQUIRED[import_type]:
            if not values.get(header):
                errors.append(f"{header}不能为空")
        code = values.get("编码", "")
        parent_code = values.get("上级编码", "")
        if code in seen:
            errors.append("编码在文件内重复")
        seen.add(code)
        if parent_code == code and code:
            errors.append("上级编码不能与自身相同")
        if (
            parent_code
            and parent_code not in existing
            and parent_code not in input_codes
        ):
            errors.append("上级编码不存在")
        status = _normalized_status(values.get("状态", ""))
        if status is None:
            errors.append("状态只能填写启用、停用、ENABLED 或 DISABLED")

        normalized: dict[str, Any] = {
            "code": code,
            "name": values.get("名称", ""),
            "parent_code": parent_code or None,
            "status": status,
        }
        if import_type == _CATEGORY:
            try:
                life = int(values.get("使用期限（月）", ""))
                if life < 1 or life > 1200:
                    raise ValueError
                normalized["service_life_months"] = life
            except ValueError:
                errors.append("使用期限（月）必须是 1 到 1200 的整数")
            unit = units.get(values.get("默认计量单位编码", ""))
            if unit is None or unit.status != RecordStatus.ENABLED.value:
                errors.append("默认计量单位编码不存在或已停用")
            else:
                normalized["default_unit_id"] = unit.id

        current = existing.get(code)
        before: dict[str, Any] | None = None
        if current is not None:
            current_parent = (
                db.session.get(model, current.parent_id) if current.parent_id else None
            )
            before = {
                "code": current.code,
                "name": current.name,
                "parent_code": getattr(current_parent, "code", None),
                "status": current.status,
            }
            if import_type == _CATEGORY:
                before.update(
                    {
                        "service_life_months": current.service_life_months,
                        "default_unit_id": current.default_unit_id,
                    }
                )
        comparable = {key: normalized.get(key) for key in (before or {})}
        action = (
            "CREATE"
            if current is None
            else ("UNCHANGED" if comparable == before else "UPDATE")
        )
        preview.append(
            {
                "line": index,
                "action": action,
                "values": values,
                "errors": errors,
                "warnings": [],
                "normalized": normalized if not errors else None,
                "before": before,
            }
        )
    cycles = _cycle_errors(preview)
    for row in preview:
        code = str(row["values"].get("编码", ""))
        if code in cycles:
            row["errors"].append(cycles[code])
            row["normalized"] = None
    return preview


def preview(
    import_type: str, original_name: str, content: bytes, actor_id: int
) -> dict[str, Any]:
    _permission(import_type, actor_id)
    if not content:
        raise BusinessException("请选择导入文件")
    if len(content) > _MAX_BYTES:
        raise BusinessException("导入文件不能超过 10MB")
    rows, file_format = _tabular_rows(content, original_name)
    _require_headers(import_type, rows)
    preview_rows = (
        _asset_preview(rows)
        if import_type == _ASSET
        else _master_preview(import_type, rows)
    )
    error_count = sum(len(row["errors"]) for row in preview_rows)
    warning_count = sum(len(row["warnings"]) for row in preview_rows)
    job = ImportJob(
        job_no=_job_no(),
        import_type=import_type,
        status=_VALIDATION_FAILED if error_count else _PREVIEW_READY,
        original_name=original_name[:255],
        file_format=file_format,
        row_count=len(preview_rows),
        error_count=error_count,
        warning_count=warning_count,
        create_count=sum(row["action"] == "CREATE" for row in preview_rows),
        update_count=sum(row["action"] == "UPDATE" for row in preview_rows),
        unchanged_count=sum(row["action"] == "UNCHANGED" for row in preview_rows),
        preview_data=preview_rows,
        created_by=actor_id,
    )
    db.session.add(job)
    db.session.flush()
    audit_service.record_resource_change(
        action="IMPORT_PREVIEW",
        resource_type="import_job",
        resource_id=job.id,
        actor_id=actor_id,
        before_data=None,
        after_data={
            "job_no": job.job_no,
            "import_type": job.import_type,
            "status": job.status,
            "row_count": job.row_count,
            "error_count": job.error_count,
            "warning_count": job.warning_count,
        },
    )
    db.session.commit()
    return _serialize(job, detail=True)


def _require_job(job_id: int, actor_id: int) -> ImportJob:
    job = db.session.get(ImportJob, job_id)
    if job is None:
        raise BusinessException("导入任务不存在", result_code=ResultCode.NOT_FOUND)
    _permission(job.import_type, actor_id)
    if job.created_by != actor_id:
        raise BusinessException(
            "只能查看和确认自己创建的导入任务", result_code=ResultCode.FORBIDDEN
        )
    return job


def get(job_id: int, actor_id: int) -> dict[str, Any]:
    return _serialize(_require_job(job_id, actor_id), detail=True)


def page(query: Mapping[str, Any], actor_id: int) -> PageResult:
    permitted = [
        kind
        for kind in _PERMISSIONS
        if permission_service.has_permission(actor_id, _PERMISSIONS[kind])
    ]
    if not permitted:
        raise BusinessException("没有导入权限", result_code=ResultCode.FORBIDDEN)
    statement = select(ImportJob).where(
        ImportJob.created_by == actor_id,
        ImportJob.import_type.in_(permitted),
    )
    if query.get("import_type"):
        statement = statement.where(ImportJob.import_type == query["import_type"])
    if query.get("status"):
        statement = statement.where(ImportJob.status == query["status"])
    total = int(
        db.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    )
    page_number = int(query["page"])
    size = int(query["size"])
    rows = db.session.scalars(
        statement.order_by(ImportJob.created_at.desc(), ImportJob.id.desc())
        .offset(page_number * size)
        .limit(size)
    ).all()
    return PageResult(
        items=[_serialize(row) for row in rows],
        total=total,
        page=page_number,
        size=size,
    )


def _asset_snapshot(asset: Asset) -> dict[str, Any]:
    return {
        "asset_code": asset.asset_code,
        "asset_name": asset.asset_name,
        "status": asset.status,
        "organization_id": asset.organization_id,
        "category_id": asset.category_id,
        "unit_id": asset.unit_id,
        "supplier_id": asset.supplier_id,
        "original_amount": str(asset.original_amount),
        "purchase_date": asset.purchase_date.isoformat(),
        "manager_id": asset.manager_id,
        "source_id": asset.source_id,
        "location_id": asset.location_id,
        "serial_number": asset.serial_number,
        "rfid_tag": asset.rfid_tag,
        "data_completeness": asset.data_completeness,
    }


def _confirm_assets(job: ImportJob, actor_id: int) -> dict[str, Any]:
    created: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    seen_serials: set[str] = set()
    seen_rfids: set[str] = set()
    for row in job.preview_data:
        normalized = row.get("normalized")
        if not isinstance(normalized, dict):
            raise BusinessException("导入预览包含无效数据，请重新上传")
        organization = db.session.get(Organization, normalized["organization_id"])
        category = db.session.get(AssetCategory, normalized["category_id"])
        manager = db.session.get(User, normalized["manager_id"])
        if organization is None or organization.status != RecordStatus.ENABLED.value:
            raise BusinessException(f"第 {row['line']} 行所属公司已变化，请重新预览")
        if category is None or category.status != RecordStatus.ENABLED.value:
            raise BusinessException(f"第 {row['line']} 行资产分类已变化，请重新预览")
        if manager is None or not manager.enabled:
            raise BusinessException(f"第 {row['line']} 行责任管理员已变化，请重新预览")
        asset_code = normalized.get("asset_code")
        if asset_code:
            exists = db.session.scalar(
                select(Asset.id).where(Asset.asset_code == asset_code)
            )
            if exists or asset_code in seen_codes:
                raise BusinessException(f"第 {row['line']} 行资产编码已存在")
        else:
            top = organization_service.get_top_level(organization.id)
            asset_code = asset_code_service.allocate(top, category).asset_code
        seen_codes.add(asset_code)
        normalized_serial = normalized.get("normalized_serial")
        if normalized_serial:
            exists = db.session.scalar(
                select(Asset.id).where(Asset.normalized_serial == normalized_serial)
            )
            if exists or normalized_serial in seen_serials:
                raise BusinessException(f"第 {row['line']} 行序列号已存在")
            seen_serials.add(normalized_serial)
        rfid_tag = normalized.get("rfid_tag")
        if rfid_tag:
            exists = db.session.scalar(
                select(Asset.id).where(Asset.rfid_tag == rfid_tag)
            )
            if exists or rfid_tag in seen_rfids:
                raise BusinessException(f"第 {row['line']} 行 RFID 已存在")
            seen_rfids.add(rfid_tag)
        purchase_date = date.fromisoformat(normalized["purchase_date"])
        service_life = category.service_life_months
        incomplete = any(
            normalized.get(field) is None
            for field in ("unit_id", "source_id", "location_id")
        )
        originals = {
            key: value
            for key, value in dict(normalized.get("originals") or {}).items()
            if value
        }
        asset = Asset(
            asset_code=asset_code,
            asset_name=normalized["asset_name"],
            status=AssetStatus.IDLE.value,
            organization_id=organization.id,
            category_id=category.id,
            unit_id=normalized.get("unit_id"),
            supplier_id=normalized.get("supplier_id"),
            original_amount=Decimal(normalized["original_amount"]),
            zero_amount_reason=normalized.get("zero_amount_reason"),
            purchase_date=purchase_date,
            service_life_months=service_life,
            expected_expiry_date=asset_data_service.calculate_expected_expiry(
                purchase_date, service_life
            ),
            manager_id=manager.id,
            source_id=normalized.get("source_id"),
            location_id=normalized.get("location_id"),
            specification_model=normalized.get("specification_model"),
            serial_number=normalized.get("serial_number"),
            normalized_serial=normalized_serial,
            receipt_no=None,
            rfid_tag=rfid_tag,
            remark=normalized.get("remark"),
            custom_attributes={
                "import_job_no": job.job_no,
                "import_originals": originals,
            },
            data_completeness=(
                AssetDataCompleteness.INCOMPLETE.value
                if incomplete
                else AssetDataCompleteness.COMPLETE.value
            ),
        )
        db.session.add(asset)
        db.session.flush()
        snapshot = _asset_snapshot(asset)
        audit_service.record_asset_stock_in(
            asset_id=asset.id,
            request_no=job.job_no,
            actor_id=actor_id,
            after_data={**snapshot, "import_type": "HISTORICAL_IMPORT"},
        )
        created.append({"id": asset.id, "asset_code": asset.asset_code})
    return {"created_assets": created}


def _master_snapshot(
    row: Organization | AssetCategory, model: type[Any]
) -> dict[str, Any]:
    parent = db.session.get(model, row.parent_id) if row.parent_id else None
    result = {
        "code": row.code,
        "name": row.name,
        "parent_code": parent.code if parent else None,
        "status": row.status,
    }
    if isinstance(row, AssetCategory):
        result.update(
            {
                "service_life_months": row.service_life_months,
                "default_unit_id": row.default_unit_id,
            }
        )
    return result


def _confirm_master(job: ImportJob, actor_id: int) -> dict[str, Any]:
    model: type[Organization] | type[AssetCategory]
    model = Organization if job.import_type == _ORGANIZATION else AssetCategory
    existing = _rows_by_code(model)
    pending = [row for row in job.preview_data if row.get("action") != "UNCHANGED"]
    changed: list[dict[str, Any]] = []
    while pending:
        progressed = False
        for row in list(pending):
            normalized = row.get("normalized")
            if not isinstance(normalized, dict):
                raise BusinessException("导入预览包含无效数据，请重新上传")
            parent_code = normalized.get("parent_code")
            if parent_code and parent_code not in existing:
                continue
            current = existing.get(normalized["code"])
            parent_id = existing[parent_code].id if parent_code else None
            if current is not None:
                stored_before = row.get("before")
                if stored_before != _master_snapshot(current, model):
                    raise BusinessException(
                        f"第 {row['line']} 行基础资料已变化，请重新预览"
                    )
                before = _master_snapshot(current, model)
                current.name = normalized["name"]
                current.parent_id = parent_id
                current.status = normalized["status"]
                if isinstance(current, AssetCategory):
                    current.service_life_months = normalized["service_life_months"]
                    current.default_unit_id = normalized["default_unit_id"]
                current.version += 1
                action = "MASTER_DATA_IMPORT_UPDATE"
            elif job.import_type == _ORGANIZATION:
                current = Organization(
                    code=normalized["code"],
                    name=normalized["name"],
                    parent_id=parent_id,
                    status=normalized["status"],
                )
                db.session.add(current)
                db.session.flush()
                existing[current.code] = current
                before = None
                action = "MASTER_DATA_IMPORT_CREATE"
            else:
                current = AssetCategory(
                    code=normalized["code"],
                    name=normalized["name"],
                    parent_id=parent_id,
                    service_life_months=normalized["service_life_months"],
                    default_unit_id=normalized["default_unit_id"],
                    status=normalized["status"],
                )
                db.session.add(current)
                db.session.flush()
                existing[current.code] = current
                before = None
                action = "MASTER_DATA_IMPORT_CREATE"
            after = _master_snapshot(current, model)
            audit_service.record_resource_change(
                action=action,
                resource_type=(
                    "organization"
                    if job.import_type == _ORGANIZATION
                    else "asset_category"
                ),
                resource_id=current.id,
                actor_id=actor_id,
                before_data=before,
                after_data={**after, "import_job_no": job.job_no},
                reason=f"导入任务 {job.job_no}",
            )
            changed.append(
                {"id": current.id, "code": current.code, "action": row["action"]}
            )
            pending.remove(row)
            progressed = True
        if not progressed:
            raise BusinessException("导入文件的父级关系无法解析，请重新检查层级")
    return {"changed_items": changed}


def confirm(job_id: int, version: int, actor_id: int) -> dict[str, Any]:
    job = _require_job(job_id, actor_id)
    if job.version != version:
        raise BusinessException("导入任务已被修改，请刷新后重试")
    if job.status == _CONFIRMED:
        return _serialize(job, detail=True)
    if job.status != _PREVIEW_READY or job.error_count:
        raise BusinessException("导入任务仍有校验错误，不能确认")
    result = (
        _confirm_assets(job, actor_id)
        if job.import_type == _ASSET
        else _confirm_master(job, actor_id)
    )
    before = {"status": job.status, "version": job.version}
    job.status = _CONFIRMED
    job.result_data = result
    job.confirmed_by = actor_id
    job.confirmed_at = utc_now()
    job.version += 1
    audit_service.record_resource_change(
        action="IMPORT_CONFIRM",
        resource_type="import_job",
        resource_id=job.id,
        actor_id=actor_id,
        before_data=before,
        after_data={"status": job.status, "version": job.version, "result": result},
        reason=f"确认导入任务 {job.job_no}",
    )
    db.session.commit()
    return _serialize(job, detail=True)


def _xlsx_cell(reference: str, value: str) -> str:
    escaped = (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    return f'<c r="{reference}" t="inlineStr"><is><t>{escaped}</t></is></c>'


def _column_name(index: int) -> str:
    result = ""
    value = index + 1
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _xlsx_bytes(rows: Sequence[Sequence[str]], sheet_name: str) -> bytes:
    sheet_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = "".join(
            _xlsx_cell(f"{_column_name(column_index)}{row_index}", str(value))
            for column_index, value in enumerate(row)
        )
        sheet_rows.append(f'<row r="{row_index}">{cells}</row>')
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{sheet_name}" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return output.getvalue()


def template(import_type: str, actor_id: int) -> tuple[bytes, str]:
    _permission(import_type, actor_id)
    headers = _HEADERS.get(import_type)
    if headers is None:
        raise BusinessException("不支持的导入类型")
    examples = {
        _ASSET: [
            "",
            "COMP01",
            "示例笔记本",
            "NOTEBOOK",
            "TAI",
            "5999.00",
            "",
            "2026-08-03",
            "SUP000001",
            "admin",
            "PURCHASE",
            "LOC000001",
            "14 英寸",
            "SN-EXAMPLE",
            "",
            "导入前请删除示例行",
        ],
        _ORGANIZATION: ["COMP01", "示例公司", "", "启用"],
        _CATEGORY: ["NOTEBOOK", "笔记本电脑", "", "36", "TAI", "启用"],
    }
    labels = {_ASSET: "资产导入", _ORGANIZATION: "公司编码", _CATEGORY: "资产分类"}
    return _xlsx_bytes(
        [headers, examples[import_type]], labels[import_type]
    ), f"{labels[import_type]}模板.xlsx"


def export_master_data(import_type: str, actor_id: int) -> tuple[bytes, str]:
    permission_codes = {
        _ORGANIZATION: "organization:export",
        _CATEGORY: "asset-category:export",
    }
    permission_code = permission_codes.get(import_type)
    if permission_code is None:
        raise BusinessException(
            "只支持导出公司编码或资产分类", result_code=ResultCode.BAD_REQUEST
        )
    permission_service.require_permission(actor_id, permission_code)

    if import_type == _ORGANIZATION:
        items = list(db.session.scalars(select(Organization)).all())
        by_id = {item.id: item for item in items}
        headers = _HEADERS[_ORGANIZATION]
        rows = [
            [
                item.code,
                item.name,
                by_id[item.parent_id].code if item.parent_id in by_id else "",
                "启用" if item.status == RecordStatus.ENABLED.value else "停用",
            ]
            for item in sorted(items, key=lambda current: current.code)
        ]
        return _xlsx_bytes([headers, *rows], "公司编码"), "公司编码完整层级.xlsx"

    items = list(db.session.scalars(select(AssetCategory)).all())
    by_id = {item.id: item for item in items}
    unit_ids = {item.default_unit_id for item in items}
    units = (
        {
            item.id: item.code
            for item in db.session.scalars(
                select(Unit).where(Unit.id.in_(unit_ids))
            ).all()
        }
        if unit_ids
        else {}
    )
    headers = _HEADERS[_CATEGORY]
    rows = [
        [
            item.code,
            item.name,
            by_id[item.parent_id].code if item.parent_id in by_id else "",
            str(item.service_life_months),
            units.get(item.default_unit_id, ""),
            "启用" if item.status == RecordStatus.ENABLED.value else "停用",
        ]
        for item in sorted(items, key=lambda current: current.code)
    ]
    return _xlsx_bytes([headers, *rows], "资产分类"), "资产分类完整层级.xlsx"


def error_report(job_id: int, actor_id: int) -> tuple[bytes, str]:
    job = _require_job(job_id, actor_id)
    headers = ["行号", "处理动作", "错误", "警告", *_HEADERS[job.import_type]]
    rows: list[list[str]] = [headers]
    for row in job.preview_data:
        if not row.get("errors") and not row.get("warnings"):
            continue
        values = (
            cast(dict[str, Any], row.get("values"))
            if isinstance(row.get("values"), dict)
            else {}
        )
        rows.append(
            [
                str(row.get("line", "")),
                str(row.get("action", "")),
                "；".join(str(item) for item in row.get("errors", [])),
                "；".join(str(item) for item in row.get("warnings", [])),
                *(str(values.get(header, "")) for header in _HEADERS[job.import_type]),
            ]
        )
    if len(rows) == 1:
        rows.append(
            ["", "", "无错误", "无警告", *("" for _ in _HEADERS[job.import_type])]
        )
    return _xlsx_bytes(rows, "校验报告"), f"{job.job_no}-校验报告.xlsx"


__all__ = [
    "confirm",
    "error_report",
    "export_master_data",
    "get",
    "page",
    "preview",
    "template",
]
