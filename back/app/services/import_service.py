"""Server-side spreadsheet previews and atomic import confirmation."""

from __future__ import annotations

import csv
import unicodedata
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Mapping, NamedTuple, Sequence, cast
from uuid import uuid4
from xml.etree import ElementTree
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from sqlalchemy import func, select

from app.common import BusinessException, PageResult, ResultCode
from app.enums import AssetDataCompleteness, AssetStatus, RecordStatus, UsageType
from app.extensions import db
from app.models import (
    Asset,
    AssetCategory,
    AssetLocation,
    AssetSource,
    ImportJob,
    AssetLifecycleRecord,
    Organization,
    PublicUsageObject,
    Role,
    Supplier,
    Unit,
    User,
    UserRole,
    UserNotification,
)
from app.models.mixins import utc_now
from app.repositories.master_data_repository import location_code_sequence_repository
from app.repositories.supplier_repository import supplier_code_sequence_repository
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
_HISTORY_MAX_ROWS = 10000

_PERMISSIONS = {
    _ASSET: "asset:import",
    _ORGANIZATION: "organization:import",
    _CATEGORY: "asset-category:import",
}

_HEADERS = {
    _ASSET: [
        "资产编码",
        "所属公司",
        "资产名称",
        "资产分类",
        "计量单位",
        "金额",
        "零金额原因",
        "采购日期",
        "供应商",
        "责任管理员",
        "资产来源",
        "存放地点",
        "使用公司",
        "使用部门",
        "使用人",
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

_UNIT_AUTO_CREATE_NAMES = {
    "个",
    "只",
    "台",
    "张",
    "套",
    "件",
    "箱",
    "部",
    "辆",
    "块",
}
_UNIT_ALIASES = {
    "PCS": "个",
    "PC": "个",
    "PIECE": "个",
    "EA": "个",
    "EACH": "个",
    "臺": "台",
    "SET": "套",
    "UNIT": "台",
}


class _UnitImportDecision(NamedTuple):
    unit: Unit | None
    create_name: str | None
    pending: bool
    error: str | None
    action: str | None


class _CategoryImportDecision(NamedTuple):
    category: AssetCategory | None
    create_path: tuple[str, ...] | None
    default_unit_name: str | None
    default_service_life_months: int | None
    error: str | None
    action: str | None


_REQUIRED = {
    _ASSET: {
        "所属公司",
        "资产名称",
        "资产分类",
        "金额",
        "采购日期",
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
    required = _REQUIRED.get(import_type, set())
    missing = required - headers
    if missing:
        raise BusinessException(f"模板缺少列：{'、'.join(sorted(missing))}")


def _xlsx_title(row: Sequence[str]) -> bool:
    return any(
        str(item or "").strip() == "资产履历" for item in row[: min(5, len(row))]
    )


def _legacy_history_rows(
    content: bytes, original_name: str
) -> tuple[list[dict[str, str]], str]:
    matrix = _xlsx_rows(content)
    if not matrix:
        raise BusinessException("导入文件为空")
    if not matrix or not _xlsx_title(matrix[0]):
        raise BusinessException("这不是有效的资产履历导出文件")
    header_index = next(
        (index for index, row in enumerate(matrix) if row and row[0] == "状态"), None
    )
    if header_index is None or header_index + 1 >= len(matrix):
        raise BusinessException("资产履历导出文件缺少表头或数据")
    headers = [item.strip() for item in matrix[header_index]]
    if len(headers) != len(set(headers)):
        raise BusinessException("导入文件存在重复列名")
    if len(matrix) - header_index - 1 > _HISTORY_MAX_ROWS:
        raise BusinessException(f"资产履历单次导入最多 {_HISTORY_MAX_ROWS} 行")
    rows = [
        {
            header: (row[index].strip() if index < len(row) else "")
            for index, header in enumerate(headers)
        }
        for row in matrix[header_index + 1 :]
        if any(cell.strip() for cell in row)
    ]
    return rows, "XLSX"


def _legacy_history_preview(
    source_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, str]]] = {}
    for source_row in source_rows:
        values = {str(key): str(value).strip() for key, value in source_row.items()}
        asset_code = values.get("资产编码", "")
        if not asset_code:
            continue
        groups.setdefault(asset_code, []).append(values)

    if len(groups) > _MAX_ROWS:
        raise BusinessException(
            f"文件包含 {len(groups)} 个资产，单次最多 {_MAX_ROWS} 个"
        )

    existing_codes = set(db.session.scalars(select(Asset.asset_code)).all())
    existing_serials = set(
        value
        for value in db.session.scalars(select(Asset.normalized_serial)).all()
        if value
    )
    existing_rfids = set(
        value for value in db.session.scalars(select(Asset.rfid_tag)).all() if value
    )
    rows_by_name = _rows_by_name(Organization)
    organizations_by_path = _organization_paths()
    categories = list(db.session.scalars(select(AssetCategory)).all())
    categories_by_code = {row.code: row for row in categories}
    categories_by_path = _category_paths(categories)
    categories_by_normalized_path = _category_normalized_paths(categories)
    units_by_name = _rows_by_name(Unit)
    sources_by_code = _rows_by_code(AssetSource)
    sources_by_name = _rows_by_name(AssetSource)
    suppliers_by_name = _rows_by_name(Supplier)
    organizations_by_code = _rows_by_code(Organization)
    users_by_name = {
        user.nickname or user.username: user
        for user in db.session.scalars(select(User)).all()
    }
    public_objects_by_name = {
        item.name: item for item in db.session.scalars(select(PublicUsageObject)).all()
    }
    locations = list(db.session.scalars(select(AssetLocation)).all())
    seen_codes: set[str] = set()
    seen_serials: set[str] = set()
    seen_rfids: set[str] = set()

    preview: list[dict[str, Any]] = []
    first_row_index = {
        rows[0].get("资产编码", ""): index for index, rows in enumerate(groups.values())
    }
    for asset_code, rows in groups.items():
        values = rows[0]
        errors: list[str] = []
        warnings: list[str] = []
        auto_actions: list[str] = []
        location_path: list[str] = []
        pending_location = False

        if asset_code in existing_codes or asset_code in seen_codes:
            errors.append("资产编码已存在")
        seen_codes.add(asset_code)

        organization = _organization_by_code_or_name(
            values.get("所属公司", ""), organizations_by_code, rows_by_name
        )
        usage_company = _organization_by_code_or_name(
            values.get("使用公司", ""), organizations_by_code, rows_by_name
        )
        usage_department = _organization_by_code_or_name(
            values.get("使用部门", ""),
            organizations_by_code,
            rows_by_name,
            organizations_by_path,
        )
        if organization is None or organization.status != RecordStatus.ENABLED.value:
            errors.append("所属公司不存在或已停用")
        if usage_company is None or usage_company.status != RecordStatus.ENABLED.value:
            errors.append("使用公司不存在或已停用")
        if usage_department is not None and usage_department.status != (
            RecordStatus.ENABLED.value
        ):
            errors.append("使用部门不存在或已停用")

        category = _category_by_code_or_path(
            values.get("资产类别", ""), categories_by_code, categories_by_path
        )
        unit_name = _unit_display_name(values.get("计量单位", ""))
        unit_for_category = units_by_name.get(unit_name) if unit_name else None
        category_decision = _category_decision(
            values.get("资产类别", ""),
            categories_by_code,
            categories_by_path,
            categories,
            categories_by_normalized_path,
            unit_for_category.name
            if unit_for_category is not None
            and unit_for_category.status == RecordStatus.ENABLED.value
            else None,
            _parse_positive_int(values.get("使用期限", ""), "使用期限"),
            list(units_by_name.values()),
        )
        category = category_decision.category
        if category_decision.error is not None:
            errors.append(category_decision.error)
        elif category_decision.action is not None:
            auto_actions.append(category_decision.action)

        manager = users_by_name.get(values.get("管理人", ""))
        if (
            manager is None or not manager.enabled
        ) and manager is not users_by_name.get("Admin"):
            manager = users_by_name.get("Admin")
        if manager is None or not manager.enabled:
            errors.append("责任管理员不存在或已停用，且未找到可用的 Admin")

        amount = _parse_decimal(values.get("金额", ""), "金额")
        purchase_date = _parse_date(values.get("购入日期", ""))
        if purchase_date is None:
            errors.append("购入日期必须使用 YYYY-MM-DD 格式")

        unit_decision = _unit_import_decision(
            values.get("计量单位", ""), units_by_name, category
        )
        unit = unit_decision.unit
        matched_source: AssetSource | None = sources_by_name.get(
            values.get("来源", "")
        ) or sources_by_code.get(values.get("来源", ""))
        region_name = values.get("区域名称", "")
        location_name = values.get("存放地点", "")
        location_text = location_name
        location = _match_location(
            location_text,
            locations,
            region_name=region_name,
            location_name=location_name,
        )
        supplier_text = values.get("供应商", "")
        supplier: Supplier | None = suppliers_by_name.get(supplier_text)
        supplier_create_name = (
            supplier_text if supplier is None and supplier_text else None
        )
        serial = values.get("设备序列号", "")
        normalized_serial = serial.lower() or None
        if normalized_serial and (
            normalized_serial in existing_serials or normalized_serial in seen_serials
        ):
            errors.append("序列号已存在")
        seen_serials.add(normalized_serial) if normalized_serial else None
        rfid = values.get("RFID", "") or None
        if rfid and (rfid in existing_rfids or rfid in seen_rfids):
            errors.append("RFID 已存在")
        seen_rfids.add(rfid) if rfid else None

        holder = users_by_name.get(values.get("使用人", ""))
        if (
            usage_department is None
            and holder is not None
            and holder.organization_id is not None
        ):
            usage_department = db.session.get(Organization, holder.organization_id)
        if values.get("使用人") and holder is None:
            auto_actions.append(
                f"使用人「{values['使用人']}」将在确认导入时自动创建（未绑定飞书身份）"
            )
        elif values.get("使用人") and holder is not None and not holder.enabled:
            auto_actions.append(
                f"使用人「{values['使用人']}」已停用，导入将保留该账号及资产使用关系"
            )
        if unit_decision.error is not None:
            errors.append(unit_decision.error)
        if unit_decision.pending:
            warnings.append("计量单位待补充")
        if matched_source is None:
            warnings.append("资产来源待补充")
        usage_type = (
            UsageType.PUBLIC.value if values.get("使用公司") == "黄豆公共" else None
        )
        public_object_name = (
            values.get("使用人", "") if usage_type == UsageType.PUBLIC.value else ""
        )
        public_object = (
            public_objects_by_name.get(public_object_name)
            if public_object_name
            else None
        )
        if usage_type == UsageType.PUBLIC.value and public_object_name:
            auto_actions.append(
                f"公共使用对象「{public_object_name}」将在确认导入时自动创建"
            )
        elif usage_type == UsageType.PUBLIC.value:
            warnings.append("公共使用对象待补充")
        location_keep_empty = (
            bool(values.get("使用人")) and holder is None and not location_text
        ) or (holder is not None and holder.enabled and not location_text)
        if location is None and not location_keep_empty:
            location_path = _location_path(
                location_text=location_text,
                region_name=region_name,
                location_name=location_name,
            )
            if len(location_path) > 1 and location_path[-1]:
                pass  # Reliable region/location path will be auto-created.
            elif not location_path and region_name:
                location_path = [region_name, _PENDING_LOCATION_NAME]
            else:
                location_path = [_PENDING_LOCATION_NAME]
            if not location_path[-1]:
                location_path[-1] = _PENDING_LOCATION_NAME
            pending_location = location_path[-1] == _PENDING_LOCATION_NAME
        if location_path:
            auto_actions.append(
                f"存放地点「{_location_display(location_path)}」将在确认导入时自动创建"
            )
        elif location_keep_empty:
            auto_actions.append("已识别使用人，存放地点将保持为空，待领用 / 发放后补充")
        if supplier_create_name:
            auto_actions.append(
                f"供应商「{supplier_create_name}」将在确认导入时自动创建"
            )

        status = (
            AssetStatus.IN_USE.value
            if values.get("状态") == "在用"
            else AssetStatus.IDLE.value
        )
        service_life = _parse_positive_int(values.get("使用期限", ""), "使用期限")
        if service_life is None:
            errors.append("使用期限必须是正整数")
            service_life = category.service_life_months if category else 36

        normalized: dict[str, Any] | None = None
        if (
            not errors
            and organization
            and usage_company
            and (category is not None or category_decision.create_path is not None)
            and manager
        ):
            normalized = {
                "asset_code": asset_code,
                "asset_name": values["资产名称"],
                "status": status,
                "organization_id": organization.id,
                "usage_company_id": usage_company.id,
                "usage_department_id": (
                    usage_department.id if usage_department is not None else None
                ),
                "usage_type": usage_type,
                "holder_user_id": holder.id if holder else None,
                "holder_user_create_name": (
                    values.get("使用人")
                    if usage_type != UsageType.PUBLIC.value
                    and holder is None
                    and values.get("使用人")
                    else None
                ),
                "public_object_id": public_object.id if public_object else None,
                "public_object_create_name": (
                    public_object_name
                    if public_object is None and public_object_name
                    else None
                ),
                "category_id": category.id if category else None,
                "category_create_path": list(category_decision.create_path or ()),
                "category_default_unit_name": category_decision.default_unit_name,
                "category_default_service_life_months": category_decision.default_service_life_months,
                "unit_id": unit.id if unit else None,
                "unit_create_name": unit_decision.create_name,
                "pending_unit": unit_decision.pending,
                "supplier_id": supplier.id if supplier else None,
                "supplier_create_name": supplier_create_name,
                "original_amount": str(amount.quantize(Decimal("0.01"))),
                "purchase_date": purchase_date.isoformat() if purchase_date else "",
                "service_life_months": service_life,
                "manager_id": manager.id,
                "source_id": matched_source.id if matched_source else None,
                "location_id": location.id if location else None,
                "location_create_path": location_path,
                "pending_location": pending_location,
                "location_keep_empty": location_keep_empty,
                "specification_model": values.get("规格型号") or None,
                "serial_number": serial or None,
                "normalized_serial": normalized_serial,
                "rfid_tag": rfid,
                "remark": values.get("标签") or None,
                "originals": {
                    "category": values.get("资产类别") or None,
                    "unit": values.get("计量单位") or None,
                    "source": values.get("来源") or None,
                    "supplier": values.get("供应商") or None,
                    "location": values.get("存放地点") or None,
                    "manager": values.get("管理人") or None,
                    "holder_user": values.get("使用人") or None,
                    "usage_department": values.get("使用部门") or None,
                },
                "history": _normalized_history(rows, users_by_name),
            }
        preview.append(
            {
                "line": first_row_index.get(asset_code, 0) + 1,
                "action": "CREATE",
                "values": _legacy_history_values(values, len(rows)),
                "errors": errors,
                "warnings": warnings,
                "auto_actions": auto_actions,
                "normalized": normalized,
            }
        )
    return preview


_PENDING_LOCATION_NAME = "待补充存放地点"

_DEFAULT_CATEGORY_UNIT_NAME = "台"
_DEFAULT_CATEGORY_SERVICE_LIFE_MONTHS = 36


def _location_candidates(location_text: str) -> list[list[str]]:
    text = location_text.strip()
    if not text:
        return [[]]
    separators = "／/\\>→-"
    for separator in separators:
        if separator in text:
            return [
                [part.strip() for part in part_text.split(separator) if part.strip()]
                for part_text in text.split(separator)
                if part_text.strip()
            ]
    return [[text]]


def _match_location(
    location_text: str,
    locations: Sequence[AssetLocation],
    *,
    region_name: str = "",
    location_name: str = "",
) -> AssetLocation | None:
    candidates: list[list[str]] = []
    if region_name or location_name:
        candidates.append(
            [part for part in (region_name.strip(), location_name.strip()) if part]
        )
    candidates.extend(_location_candidates(location_text))
    by_code = {row.code: row for row in locations}
    for candidate in candidates:
        if len(candidate) == 1 and candidate[0] in by_code:
            matched = by_code[candidate[0]]
            if matched.status == RecordStatus.ENABLED.value and matched.is_selectable:
                return matched
            return None
    for candidate in candidates:
        if not candidate:
            continue
        child: AssetLocation | None = None
        valid = True
        for name in candidate:
            child = next(
                (
                    row
                    for row in locations
                    if row.name == name
                    and row.parent_id == (child.id if child is not None else None)
                ),
                cast(AssetLocation, None),
            )
            if child is None:
                valid = False
                break
        if valid and child is not None:
            if child.status == RecordStatus.ENABLED.value and child.is_selectable:
                return child
            return None
    for candidate in candidates:
        if not candidate:
            continue
        leaf = candidate[-1]
        matched = next(
            (row for row in locations if row.name == leaf),
            cast(AssetLocation, None),
        )
        if (
            matched is not None
            and matched.status == RecordStatus.ENABLED.value
            and matched.is_selectable
        ):
            return matched
    return None


def _location_path(
    location_text: str = "",
    *,
    region_name: str = "",
    location_name: str = "",
) -> list[str]:
    candidates: list[list[str]] = []
    if region_name or location_name:
        candidates.append(
            [part for part in (region_name.strip(), location_name.strip()) if part]
        )
    candidates.extend(_location_candidates(location_text))
    for candidate in candidates:
        if candidate and len(candidate) > 1:
            return candidate
    if candidates:
        return candidates[0]
    return []


def _location_display(path: Sequence[str]) -> str:
    return " / ".join(path)


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


def _organization_paths() -> dict[str, Organization]:
    rows = list(db.session.scalars(select(Organization)).all())
    rows_by_id = {row.id: row for row in rows}
    result: dict[str, Organization] = {}
    for row in rows:
        names = [row.name]
        parent_id = row.parent_id
        visited = {row.id}
        while (
            parent_id is not None
            and parent_id in rows_by_id
            and parent_id not in visited
        ):
            parent = rows_by_id[parent_id]
            names.append(parent.name)
            visited.add(parent_id)
            parent_id = parent.parent_id
        result["/".join(reversed(names))] = row
    return result


def _organization_by_code_or_name(
    value: str,
    rows_by_code: Mapping[str, Organization],
    rows_by_name: Mapping[str, Organization],
    rows_by_path: Mapping[str, Organization] | None = None,
) -> Organization | None:
    direct = rows_by_code.get(value)
    if direct is not None or not value:
        return direct
    direct = rows_by_name.get(value)
    if direct is not None or rows_by_path is None:
        return direct
    return rows_by_path.get(value)


def _normalize_category_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    for separator in ("/", "\\", "＞", ">", "—", "–"):
        if separator in normalized:
            normalized = normalized.replace(separator, "/")
    normalized = "/".join(
        "".join(part.split()).lower() for part in normalized.split("/") if part.strip()
    )
    return normalized


def _category_normalized_paths(
    rows: Sequence[AssetCategory],
) -> dict[str, AssetCategory]:
    by_id = {row.id: row for row in rows}
    result: dict[str, AssetCategory] = {}
    for row in rows:
        names = [row.name]
        parent_id = row.parent_id
        visited = {row.id}
        while parent_id is not None and parent_id in by_id and parent_id not in visited:
            parent = by_id[parent_id]
            names.append(parent.name)
            visited.add(parent_id)
            parent_id = parent.parent_id
        result[_normalize_category_text("/".join(reversed(names)))] = row
    return result


def _category_parts(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", value).strip()
    for separator in ("/", "\\", "＞", ">", "—", "–"):
        normalized = normalized.replace(separator, "/")
    return [part.strip() for part in normalized.split("/") if part.strip()]


def _category_by_code_or_path(
    value: str,
    rows_by_code: Mapping[str, AssetCategory],
    rows_by_path: Mapping[str, AssetCategory],
    *,
    normalized_paths: Mapping[str, AssetCategory] | None = None,
    rows: Sequence[AssetCategory] | None = None,
) -> AssetCategory | None:
    direct = rows_by_code.get(value)
    if direct is not None or not value:
        return direct
    direct = rows_by_path.get(value)
    if direct is not None:
        return direct
    if normalized_paths is None:
        return None
    direct = normalized_paths.get(_normalize_category_text(value))
    if direct is not None:
        return direct

    parts = _category_parts(value)
    leaf_name = parts[-1] if parts else ""
    candidates = [
        row
        for row in (rows if rows is not None else normalized_paths.values())
        if row.name == leaf_name and row.status == RecordStatus.ENABLED.value
    ]
    return candidates[0] if len(candidates) == 1 else None


def _asset_preview(source_rows: Sequence[Mapping[str, str]]) -> list[dict[str, Any]]:
    organizations = _rows_by_code(Organization)
    sources = _rows_by_code(AssetSource)
    locations = list(db.session.scalars(select(AssetLocation)).all())
    suppliers_by_code = _rows_by_code(Supplier)
    suppliers_by_name = _rows_by_name(Supplier)
    users = {row.username: row for row in db.session.scalars(select(User)).all()}
    users_by_display_name = {
        (user.nickname or user.username): user
        for user in db.session.scalars(select(User)).all()
    }
    organizations_by_name = _rows_by_name(Organization)
    organizations_by_path = _organization_paths()
    units_by_name = _rows_by_name(Unit)
    sources_by_name = _rows_by_name(AssetSource)
    categories = list(db.session.scalars(select(AssetCategory)).all())
    categories_by_path = _category_paths(categories)
    categories_by_code = {row.code: row for row in categories}
    categories_by_normalized_path = _category_normalized_paths(categories)
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
        auto_actions: list[str] = []
        for header in _REQUIRED[_ASSET]:
            if not values.get(header):
                errors.append(f"{header}不能为空")
        organization = _organization_by_code_or_name(
            values.get("所属公司", ""),
            organizations,
            organizations_by_name,
            organizations_by_path,
        )
        category = _category_by_code_or_path(
            values.get("资产分类", ""), categories_by_code, categories_by_path
        )
        unit_name = _unit_display_name(values.get("计量单位", ""))
        unit_for_category = units_by_name.get(unit_name) if unit_name else None
        category_decision = _category_decision(
            values.get("资产分类", ""),
            categories_by_code,
            categories_by_path,
            categories,
            categories_by_normalized_path,
            unit_for_category.name
            if unit_for_category is not None
            and unit_for_category.status == RecordStatus.ENABLED.value
            else None,
            None,
            list(units_by_name.values()),
        )
        category = category_decision.category
        usage_company = _organization_by_code_or_name(
            values.get("使用公司", ""),
            organizations,
            organizations_by_name,
            organizations_by_path,
        )
        usage_department = _organization_by_code_or_name(
            values.get("使用部门", ""),
            organizations,
            organizations_by_name,
            organizations_by_path,
        )
        holder = users_by_display_name.get(values.get("使用人", ""))
        if not values.get("使用公司"):
            usage_company = organization
        if (
            usage_department is None
            and holder is not None
            and holder.organization_id is not None
        ):
            usage_department = db.session.get(Organization, holder.organization_id)
        if not values.get("使用人") and values.get("使用部门"):
            holder = None
        manager_account = values.get("责任管理员", "")
        manager = users.get(manager_account)
        if manager is None and manager_account:
            manager = next(
                (
                    user
                    for user in users.values()
                    if (user.nickname or "").strip().lower() == manager_account.lower()
                ),
                None,
            )
        if manager is None:
            manager = users.get("admin")
            if manager is None:
                manager = next(
                    (
                        user
                        for user in users.values()
                        if (user.nickname or "").strip().lower() == "admin"
                    ),
                    None,
                )
        if organization is None or organization.status != RecordStatus.ENABLED.value:
            errors.append("所属公司不存在或已停用")
        if usage_company is None or usage_company.status != RecordStatus.ENABLED.value:
            errors.append("使用公司不存在或已停用")
        if usage_department is not None and usage_department.status != (
            RecordStatus.ENABLED.value
        ):
            errors.append("使用部门不存在或已停用")
        if values.get("使用人") and holder is None:
            auto_actions.append(
                f"使用人「{values['使用人']}」将在确认导入时自动创建（未绑定飞书身份）"
            )
        elif values.get("使用人") and holder is not None and not holder.enabled:
            auto_actions.append(
                f"使用人「{values['使用人']}」已停用，导入将保留该账号及资产使用关系"
            )
        if category_decision.error is not None:
            errors.append(category_decision.error)
        elif category_decision.action is not None:
            auto_actions.append(category_decision.action)
        if manager is None or not manager.enabled:
            errors.append("责任管理员不存在或已停用，且未找到可用的 Admin")

        unit_text = values.get("计量单位", "")
        source_text = values.get("资产来源", "")
        location_text = values.get("存放地点", "")
        unit_decision = _unit_import_decision(unit_text, units_by_name, category)
        unit = unit_decision.unit
        asset_source = sources.get(source_text) or sources_by_name.get(source_text)
        location = _match_location(location_text, locations)
        location_path: list[str] = []
        pending_location = False
        if unit_decision.error is not None:
            errors.append(unit_decision.error)
        if unit_decision.pending:
            warnings.append(
                "计量单位待补充" if not unit_text else "计量单位未匹配，原文字已保留"
            )
        if unit_decision.action is not None:
            auto_actions.append(unit_decision.action)
        if asset_source is None:
            warnings.append(
                "资产来源待补充" if not source_text else "资产来源未匹配，原文字已保留"
            )
        elif asset_source.status != RecordStatus.ENABLED.value:
            errors.append("资产来源已停用")
        location_keep_empty = (
            bool(values.get("使用人")) and holder is None and not location_text
        ) or (holder is not None and holder.enabled and not location_text)
        if location is None and not location_keep_empty:
            location_path = _location_path(location_text)
            if location_path and location_path[-1] != _PENDING_LOCATION_NAME:
                location_path[-1] = _PENDING_LOCATION_NAME
            else:
                location_path = [_PENDING_LOCATION_NAME]
            pending_location = True
            auto_actions.append(
                f"存放地点「{_location_display(location_path)}」将在确认导入时自动创建"
            )
        elif location_keep_empty:
            auto_actions.append("已识别使用人，存放地点将保持为空，待领用 / 发放后补充")

        supplier_text = values.get("供应商", "")
        supplier = suppliers_by_code.get(supplier_text) or suppliers_by_name.get(
            supplier_text
        )
        if supplier is not None and supplier.status != RecordStatus.ENABLED.value:
            errors.append("供应商已停用")
        supplier_create_name = (
            supplier_text if supplier is None and supplier_text else None
        )
        if supplier_create_name:
            auto_actions.append(
                f"供应商「{supplier_create_name}」将在确认导入时自动创建"
            )

        amount: Decimal | None = None
        try:
            amount = Decimal(values.get("金额", ""))
            if amount < 0:
                errors.append("金额不能小于 0")
            if amount == 0 and not values.get("零金额原因"):
                errors.append("零金额资产必须填写原因")
        except InvalidOperation:
            errors.append("金额必须是合法数字")
        purchase_date = _parse_date(
            values.get("采购日期", "") or values.get("购入日期", "")
        )
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
            and usage_company
            and (category is not None or category_decision.create_path is not None)
            and manager
            and amount is not None
            and purchase_date
        ):
            normalized = {
                "asset_code": asset_code or None,
                "organization_id": organization.id,
                "usage_company_id": usage_company.id,
                "usage_department_id": (
                    usage_department.id if usage_department is not None else None
                ),
                "holder_user_id": holder.id if holder is not None else None,
                "holder_user_create_name": (
                    values.get("使用人")
                    if usage_company is None
                    or usage_company.name != "黄豆公共"
                    and holder is None
                    and values.get("使用人")
                    else None
                ),
                "asset_name": values["资产名称"],
                "category_id": category.id if category else None,
                "category_create_path": list(category_decision.create_path or ()),
                "category_default_unit_name": category_decision.default_unit_name,
                "category_default_service_life_months": category_decision.default_service_life_months,
                "unit_id": unit.id if unit else None,
                "unit_create_name": unit_decision.create_name,
                "pending_unit": unit_decision.pending,
                "original_amount": str(amount.quantize(Decimal("0.01"))),
                "zero_amount_reason": values.get("零金额原因") or None,
                "purchase_date": purchase_date.isoformat(),
                "supplier_id": supplier.id if supplier else None,
                "supplier_create_name": supplier_create_name,
                "manager_id": manager.id,
                "source_id": asset_source.id if asset_source else None,
                "location_id": location.id if location else None,
                "location_create_path": location_path,
                "pending_location": pending_location,
                "location_keep_empty": location_keep_empty,
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
                "auto_actions": auto_actions,
                "normalized": normalized,
            }
        )
    return preview


def _unit_display_name(value: str) -> str | None:
    normalized = unicodedata.normalize("NFKC", value).strip()
    normalized = normalized.rstrip("。.．").strip()
    if not normalized:
        return None
    upper = normalized.upper()
    return _UNIT_ALIASES.get(upper, normalized)


def _unit_import_decision(
    value: str,
    units: Mapping[str, Unit],
    category: AssetCategory | None,
) -> _UnitImportDecision:
    display_name = _unit_display_name(value)
    unit = units.get(display_name) if display_name is not None else None
    if unit is not None:
        if unit.status != RecordStatus.ENABLED.value:
            return _UnitImportDecision(None, None, False, "计量单位已停用", None)
        return _UnitImportDecision(unit, None, False, None, None)

    default_unit_id = category.default_unit_id if category is not None else None
    default_unit = (
        db.session.get(Unit, default_unit_id) if default_unit_id is not None else None
    )
    if default_unit is not None and default_unit.status == RecordStatus.ENABLED.value:
        source = f"「{value}」" if value.strip() else "为空"
        return _UnitImportDecision(
            default_unit,
            None,
            False,
            None,
            f"计量单位{source}未匹配，将使用分类默认单位「{default_unit.name}」",
        )

    if display_name in _UNIT_AUTO_CREATE_NAMES:
        return _UnitImportDecision(
            None,
            display_name,
            False,
            None,
            f"计量单位「{display_name}」将在确认导入时自动创建",
        )

    return _UnitImportDecision(None, None, True, None, None)


def _parse_decimal(value: str, label: str) -> Decimal:
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise BusinessException(f"{label}必须是合法数字") from exc
    if amount < 0:
        raise BusinessException(f"{label}不能小于 0")
    return amount


def _parse_positive_int(value: str, label: str) -> int | None:
    try:
        result = int(value)
    except ValueError:
        return None
    return result if result > 0 else None


def _category_paths(rows: Sequence[AssetCategory]) -> dict[str, AssetCategory]:
    by_id = {row.id: row for row in rows}
    result: dict[str, AssetCategory] = {}
    for row in rows:
        names = [row.name]
        parent_id = row.parent_id
        visited = {row.id}
        while parent_id is not None and parent_id in by_id and parent_id not in visited:
            parent = by_id[parent_id]
            names.append(parent.name)
            visited.add(parent_id)
            parent_id = parent.parent_id
        result["/".join(reversed(names))] = row
    return result


def _category_create_decision(
    create_path: tuple[str, ...],
    unit_name: str,
    default_service_life_months: int | None,
    original_value: str,
) -> _CategoryImportDecision:
    life = default_service_life_months or _DEFAULT_CATEGORY_SERVICE_LIFE_MONTHS
    return _CategoryImportDecision(
        None,
        create_path,
        unit_name,
        life,
        None,
        (
            f"资产分类「{'/'.join(create_path)}」将在确认导入时自动创建；"
            f"默认使用期限：{life} 个月；默认计量单位：{unit_name}"
        ),
    )


def _category_decision(
    value: str,
    rows_by_code: Mapping[str, AssetCategory],
    rows_by_path: Mapping[str, AssetCategory],
    rows: Sequence[AssetCategory],
    normalized_paths: Mapping[str, AssetCategory],
    default_unit_name: str | None,
    default_service_life_months: int | None,
    units: Sequence[Unit],
) -> _CategoryImportDecision:
    category = _category_by_code_or_path(
        value,
        rows_by_code,
        rows_by_path,
        normalized_paths=normalized_paths,
        rows=rows,
    )
    if category is not None:
        if category.status != RecordStatus.ENABLED.value:
            return _CategoryImportDecision(
                None,
                None,
                None,
                None,
                f"资产分类「{category.name}」已停用，请先启用或更换分类",
                None,
            )
        return _CategoryImportDecision(category, None, None, None, None, None)
    if not value:
        return _CategoryImportDecision(None, None, None, None, "资产分类不能为空", None)

    normalized = _normalize_category_text(value)
    if normalized in normalized_paths:
        category = normalized_paths[normalized]
        if category.status != RecordStatus.ENABLED.value:
            return _CategoryImportDecision(
                None,
                None,
                None,
                None,
                f"资产分类「{category.name}」已停用，请先启用或更换分类",
                None,
            )
        return _CategoryImportDecision(category, None, None, None, None, None)

    parts = _category_parts(value)
    leaf_name = parts[-1] if parts else ""
    candidates = [
        row
        for row in rows
        if row.name == leaf_name and row.status == RecordStatus.ENABLED.value
    ]
    if len(candidates) > 1:
        return _CategoryImportDecision(
            None,
            None,
            None,
            None,
            f"资产分类「{leaf_name}」存在多个匹配，请填写完整路径",
            None,
        )

    raw_parts = parts
    parent: AssetCategory | None = None
    for part in raw_parts[:-1]:
        candidates = [
            row
            for row in rows
            if row.name == part
            and row.status == RecordStatus.ENABLED.value
            and row.parent_id == (parent.id if parent is not None else None)
        ]
        if len(candidates) != 1:
            parent = None
            break
        parent = candidates[0]
    if parent is not None:
        parent_unit = db.session.get(Unit, parent.default_unit_id)
        default_unit_name = (
            parent_unit.name
            if parent_unit is not None
            and parent_unit.status == RecordStatus.ENABLED.value
            else None
        )
        default_service_life_months = parent.service_life_months
    create_path = tuple(part for part in raw_parts if part)

    preferred_unit_name = default_unit_name or _DEFAULT_CATEGORY_UNIT_NAME
    preferred_unit = db.session.scalar(
        select(Unit).where(Unit.name == preferred_unit_name)
    )
    if (
        preferred_unit is not None
        and preferred_unit.status == RecordStatus.ENABLED.value
    ):
        return _category_create_decision(
            create_path, preferred_unit.name, default_service_life_months, value
        )

    enabled_units = [row for row in units if row.status == RecordStatus.ENABLED.value]
    unit_name = next(
        (row.name for row in enabled_units if row.name in _UNIT_AUTO_CREATE_NAMES),
        next(
            (row.name for row in enabled_units),
            None,
        ),
    )
    if unit_name is None:
        # 分类必须绑定默认计量单位。单位为空时预览只登记待创建单位，确认导入时落库。
        normalized_name = _unit_display_name(_DEFAULT_CATEGORY_UNIT_NAME)
        if normalized_name is None:
            raise BusinessException("系统默认计量单位配置无效")
        unit_name = normalized_name
    return _category_create_decision(
        create_path, unit_name, default_service_life_months, value
    )


def _legacy_history_values(
    values: Mapping[str, str], history_count: int
) -> dict[str, str]:
    return {
        "资产编码": values.get("资产编码", ""),
        "资产名称": values.get("资产名称", ""),
        "所属公司": values.get("所属公司", ""),
        "使用公司": values.get("使用公司", ""),
        "使用部门": values.get("使用部门", ""),
        "资产分类": values.get("资产类别", ""),
        "管理人": values.get("管理人", ""),
        "金额": values.get("金额", ""),
        "购入日期": values.get("购入日期", ""),
        "履历条数": str(history_count),
    }


def _normalized_history(
    rows: Sequence[Mapping[str, str]], users_by_name: Mapping[str, User]
) -> list[dict[str, Any]]:
    operators = dict(users_by_name)
    history: list[dict[str, Any]] = []
    for values in rows:
        operator_name = values.get("处理人", "")
        occurred_text = values.get("处理时间", "")
        try:
            occurred_at = (
                datetime.strptime(occurred_text, "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
                if occurred_text
                else None
            )
        except ValueError:
            occurred_at = None
        operator = operators.get(operator_name)
        history.append(
            {
                "operation_type": values.get("单据类型", "") or "历史记录",
                "operation_no": values.get("入库 / 收货单号", "") or "HISTORY",
                "operator_id": operator.id if operator else None,
                "operator_name": operator_name,
                "before_data": None,
                "after_data": None,
                "remark": values.get("处理内容", ""),
                "occurred_at": occurred_at.isoformat() if occurred_at else None,
                "receipt_no": values.get("入库 / 收货单号", ""),
                "document_type": values.get("单据类型", ""),
            }
        )
    return history


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
    _xlsx_matrix = (
        _xlsx_rows(content) if Path(original_name).suffix.lower() == ".xlsx" else []
    )
    legacy_history = (
        import_type == _ASSET and bool(_xlsx_matrix) and _xlsx_title(_xlsx_matrix[0])
    )
    if legacy_history:
        rows, file_format = _legacy_history_rows(content, original_name)
        preview_rows = _legacy_history_preview(rows)
        job = ImportJob(
            job_no=_job_no(),
            import_type=import_type,
            status=_VALIDATION_FAILED
            if any(row["errors"] for row in preview_rows)
            else _PREVIEW_READY,
            original_name=original_name[:255],
            file_format=file_format,
            row_count=len(preview_rows),
            error_count=sum(len(row["errors"]) for row in preview_rows),
            warning_count=sum(len(row["warnings"]) for row in preview_rows),
            create_count=len(preview_rows),
            update_count=0,
            unchanged_count=0,
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
                "import_type": "LEGACY_ASSET_HISTORY",
                "status": job.status,
                "row_count": job.row_count,
                "error_count": job.error_count,
                "warning_count": job.warning_count,
            },
        )
        db.session.commit()
        return _serialize(job, detail=True)

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
        "usage_company_id": asset.usage_company_id,
        "usage_department_id": asset.usage_department_id,
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


def _category_snapshot(category: AssetCategory) -> dict[str, Any]:
    return {
        "id": category.id,
        "code": category.code,
        "name": category.name,
        "parent_id": category.parent_id,
        "service_life_months": category.service_life_months,
        "default_unit_id": category.default_unit_id,
        "status": category.status,
    }


def _supplier_snapshot(supplier: Supplier) -> dict[str, Any]:
    return {
        "id": supplier.id,
        "code": supplier.code,
        "name": supplier.name,
        "status": supplier.status,
    }


def _location_snapshot(location: AssetLocation) -> dict[str, Any]:
    parent = (
        db.session.get(AssetLocation, location.parent_id)
        if location.parent_id
        else None
    )
    return {
        "id": location.id,
        "code": location.code,
        "name": location.name,
        "parent_code": parent.code if parent else None,
        "status": location.status,
        "is_selectable": location.is_selectable,
    }


def _public_object_snapshot(public_object: PublicUsageObject) -> dict[str, Any]:
    return {
        "id": public_object.id,
        "code": public_object.code,
        "name": public_object.name,
        "status": public_object.status,
    }


def _resolve_import_supplier(name: str, actor_id: int, job_no: str) -> Supplier:
    supplier = db.session.scalar(select(Supplier).where(Supplier.name == name))
    if supplier is not None:
        if supplier.status != RecordStatus.ENABLED.value:
            raise BusinessException(f"供应商「{name}」已停用，请先恢复启用")
        return supplier
    supplier_code_sequence_repository.ensure_exists()
    sequence = supplier_code_sequence_repository.find_for_update()
    if sequence is None:
        raise RuntimeError("supplier code sequence was not initialized")
    sequence.current_value += 1
    supplier = Supplier(
        code=f"{sequence.prefix}{sequence.current_value:06d}",
        name=name,
        status=RecordStatus.ENABLED.value,
    )
    db.session.add(supplier)
    db.session.flush()
    audit_service.record_resource_change(
        action="SUPPLIER_IMPORT_CREATE",
        resource_type="supplier",
        resource_id=supplier.id,
        actor_id=actor_id,
        before_data=None,
        after_data=_supplier_snapshot(supplier),
        reason=f"导入任务 {job_no} 自动创建",
    )
    return supplier


def _resolve_import_location(
    path: Sequence[str], actor_id: int, job_no: str
) -> AssetLocation:
    parent: AssetLocation | None = None
    for name in path:
        location = db.session.scalar(
            select(AssetLocation).where(
                AssetLocation.parent_id == (parent.id if parent is not None else None),
                AssetLocation.name == name,
            )
        )
        if location is None:
            location_code_sequence_repository.ensure_exists()
            sequence = location_code_sequence_repository.find_for_update()
            if sequence is None:
                raise RuntimeError("location code sequence was not initialized")
            sequence.current_value += 1
            location = AssetLocation(
                code=f"{sequence.prefix}{sequence.current_value:06d}",
                name=name,
                parent_id=parent.id if parent is not None else None,
                status=RecordStatus.ENABLED.value,
                is_selectable=True,
            )
            db.session.add(location)
            db.session.flush()
            audit_service.record_resource_change(
                action="ASSET_LOCATION_IMPORT_CREATE",
                resource_type="asset_location",
                resource_id=location.id,
                actor_id=actor_id,
                before_data=None,
                after_data=_location_snapshot(location),
                reason=f"导入任务 {job_no} 自动创建",
            )
        elif (
            location.status != RecordStatus.ENABLED.value or not location.is_selectable
        ):
            raise BusinessException(
                f"存放地点「{_location_display(path)}」已停用或不可选择，请先处理基础资料"
            )
        parent = location
    if parent is None:
        raise BusinessException("存放地点路径无效，请重新预览")
    return parent


def _resolve_import_public_object(
    name: str, actor_id: int, job_no: str
) -> PublicUsageObject:
    public_object = db.session.scalar(
        select(PublicUsageObject).where(PublicUsageObject.name == name)
    )
    if public_object is not None:
        if public_object.status != RecordStatus.ENABLED.value:
            raise BusinessException(f"公共使用对象「{name}」已停用，请先恢复启用")
        return public_object
    current = int(db.session.scalar(select(func.max(PublicUsageObject.id))) or 0) + 1
    public_object = PublicUsageObject(
        code=f"PUB{current:06d}",
        name=name,
        status=RecordStatus.ENABLED.value,
    )
    db.session.add(public_object)
    db.session.flush()
    audit_service.record_resource_change(
        action="PUBLIC_USAGE_OBJECT_IMPORT_CREATE",
        resource_type="public_usage_object",
        resource_id=public_object.id,
        actor_id=actor_id,
        before_data=None,
        after_data=_public_object_snapshot(public_object),
        reason=f"导入任务 {job_no} 自动创建",
    )
    return public_object


def _unit_snapshot(unit: Unit) -> dict[str, Any]:
    return {
        "id": unit.id,
        "code": unit.code,
        "name": unit.name,
        "status": unit.status,
    }


def _resolve_import_unit(name: str, actor_id: int, job_no: str) -> Unit:
    unit = db.session.scalar(select(Unit).where(Unit.name == name))
    if unit is not None:
        if unit.status != RecordStatus.ENABLED.value:
            raise BusinessException(f"计量单位「{name}」已停用，请先恢复启用")
        return unit

    normalized_name = _unit_display_name(name)
    if normalized_name is None or normalized_name not in _UNIT_AUTO_CREATE_NAMES:
        raise BusinessException(f"计量单位「{name}」不能自动创建，请先维护基础资料")
    current = int(db.session.scalar(select(func.max(Unit.id))) or 0) + 1
    unit = Unit(
        code=f"UNIT{current:06d}",
        name=normalized_name,
        status=RecordStatus.ENABLED.value,
    )
    db.session.add(unit)
    db.session.flush()
    audit_service.record_resource_change(
        action="UNIT_IMPORT_CREATE",
        resource_type="unit",
        resource_id=unit.id,
        actor_id=actor_id,
        before_data=None,
        after_data=_unit_snapshot(unit),
        reason=f"导入任务 {job_no} 自动创建",
    )
    return unit


def _resolve_import_category(
    path: Sequence[str],
    default_unit_id: int,
    service_life_months: int,
    actor_id: int,
    job_no: str,
) -> AssetCategory:
    parent: AssetCategory | None = None
    for name in path:
        category = db.session.scalar(
            select(AssetCategory).where(
                AssetCategory.parent_id == (parent.id if parent is not None else None),
                AssetCategory.name == name,
            )
        )
        if category is None:
            current = (
                int(db.session.scalar(select(func.max(AssetCategory.id))) or 0) + 1
            )
            category = AssetCategory(
                code=f"IMPCAT{current:06d}",
                name=name,
                parent_id=parent.id if parent is not None else None,
                service_life_months=(
                    service_life_months
                    if parent is None
                    else parent.service_life_months
                ),
                default_unit_id=(
                    default_unit_id if parent is None else parent.default_unit_id
                ),
                status=RecordStatus.ENABLED.value,
            )
            db.session.add(category)
            db.session.flush()
            audit_service.record_resource_change(
                action="ASSET_CATEGORY_IMPORT_CREATE",
                resource_type="asset_category",
                resource_id=category.id,
                actor_id=actor_id,
                before_data=None,
                after_data=_category_snapshot(category),
                reason=f"导入任务 {job_no} 自动创建",
            )
        elif category.status != RecordStatus.ENABLED.value:
            raise BusinessException(
                f"资产分类「{'/'.join(path)}」中的「{category.name}」已停用，请先处理基础资料"
            )
        parent = category
    if parent is None:
        raise BusinessException("资产分类路径无效，请重新预览")
    return parent


def _resolve_import_holder(display_name: str, actor_id: int, job_no: str) -> User:
    normalized_name = display_name.strip()
    existing = db.session.scalar(
        select(User).where(
            (User.nickname == normalized_name) | (User.username == normalized_name)
        )
    )
    if existing is not None:
        return existing
    suffix = uuid4().hex[:8]
    username = f"import_user_{suffix}"
    user = User(
        username=username,
        password=f"import-unmanaged-{uuid4().hex}",
        nickname=normalized_name,
        enabled=True,
        feishu_sync_status="UNSYNCED",
    )
    db.session.add(user)
    db.session.flush()
    employee_role = db.session.scalar(select(Role).where(Role.code == "USER"))
    if employee_role is not None:
        db.session.add(UserRole(user_id=user.id, role_id=employee_role.id))
    audit_service.record_resource_change(
        action="USER_IMPORT_CREATE",
        resource_type="user",
        resource_id=user.id,
        actor_id=actor_id,
        before_data=None,
        after_data={
            "username": user.username,
            "nickname": user.nickname,
            "enabled": user.enabled,
            "feishu_open_id": None,
        },
        reason=f"导入任务 {job_no} 自动创建（未绑定飞书身份）",
    )
    return user


def _resolve_deferred_master_data(
    job: ImportJob, actor_id: int
) -> tuple[
    dict[str, Supplier],
    dict[tuple[str, ...], AssetLocation],
    dict[str, PublicUsageObject],
    dict[str, Unit],
    dict[tuple[str, ...], AssetCategory],
]:
    suppliers: dict[str, Supplier] = {}
    locations: dict[tuple[str, ...], AssetLocation] = {}
    public_objects: dict[str, PublicUsageObject] = {}
    units: dict[str, Unit] = {}
    categories: dict[tuple[str, ...], AssetCategory] = {}
    for row in job.preview_data:
        normalized = row.get("normalized")
        if not isinstance(normalized, dict):
            continue
        holder_name = normalized.get("holder_user_create_name")
        if (
            isinstance(holder_name, str)
            and holder_name
            and normalized.get("usage_type") != UsageType.PUBLIC.value
        ):
            holder = _resolve_import_holder(holder_name, actor_id, job.job_no)
            normalized["holder_user_id"] = holder.id
            normalized["usage_department_id"] = holder.organization_id
        category_default_unit_name = normalized.get("category_default_unit_name")
        if isinstance(category_default_unit_name, str) and category_default_unit_name:
            units[category_default_unit_name] = _resolve_import_unit(
                category_default_unit_name, actor_id, job.job_no
            )
        supplier_name = normalized.get("supplier_create_name")
        if isinstance(supplier_name, str) and supplier_name:
            suppliers[supplier_name] = _resolve_import_supplier(
                supplier_name, actor_id, job.job_no
            )
        location_path = normalized.get("location_create_path")
        if (
            normalized.get("location_id") is None
            and isinstance(location_path, list)
            and location_path
        ):
            path = tuple(str(item) for item in location_path)
            locations[path] = _resolve_import_location(path, actor_id, job.job_no)
        public_object_name = normalized.get("public_object_create_name")
        if isinstance(public_object_name, str) and public_object_name:
            public_objects[public_object_name] = _resolve_import_public_object(
                public_object_name, actor_id, job.job_no
            )
        unit_name = normalized.get("unit_create_name")
        if isinstance(unit_name, str) and unit_name:
            units[unit_name] = _resolve_import_unit(unit_name, actor_id, job.job_no)
        category_path = normalized.get("category_create_path")
        if (
            normalized.get("category_id") is None
            and isinstance(category_path, list)
            and category_path
            and normalized.get("category_default_unit_name") is not None
            and normalized.get("category_default_service_life_months") is not None
        ):
            path = tuple(str(item) for item in category_path)
            category_unit_name = str(normalized["category_default_unit_name"])
            categories[path] = _resolve_import_category(
                path,
                units[category_unit_name].id,
                int(normalized["category_default_service_life_months"]),
                actor_id,
                job.job_no,
            )
    return suppliers, locations, public_objects, units, categories


def _category_path_from_id(category_id: int) -> list[str]:
    rows = db.session.scalars(select(AssetCategory)).all()
    by_id = {row.id: row for row in rows}
    current = by_id.get(category_id)
    path: list[str] = []
    visited: set[int] = set()
    while current is not None and current.id not in visited:
        visited.add(current.id)
        path.append(current.name)
        current = by_id.get(current.parent_id) if current.parent_id else None
    return list(reversed(path))


def _auto_created_master_data(
    suppliers: Mapping[str, Supplier],
    locations: Mapping[tuple[str, ...], AssetLocation],
    public_objects: Mapping[str, PublicUsageObject],
    units: Mapping[str, Unit],
    categories: Mapping[tuple[str, ...], AssetCategory],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in suppliers.values():
        result.append({"type": "SUPPLIER", "id": item.id, "name": item.name})
    for item in locations.values():
        result.append(
            {
                "type": "ASSET_LOCATION",
                "id": item.id,
                "name": item.name,
                "path": _location_display(_location_path_from_id(item.id)),
            }
        )
    for item in public_objects.values():
        result.append({"type": "PUBLIC_USAGE_OBJECT", "id": item.id, "name": item.name})
    for item in units.values():
        result.append({"type": "UNIT", "id": item.id, "name": item.name})
    for item in categories.values():
        result.append(
            {
                "type": "ASSET_CATEGORY",
                "id": item.id,
                "name": item.name,
                "path": "/".join(_category_path_from_id(item.id)),
            }
        )
    return result


def _location_path_from_id(location_id: int) -> list[str]:
    rows = db.session.scalars(select(AssetLocation)).all()
    by_id = {row.id: row for row in rows}
    current = by_id.get(location_id)
    path: list[str] = []
    visited: set[int] = set()
    while current is not None and current.id not in visited:
        visited.add(current.id)
        path.append(current.name)
        current = by_id.get(current.parent_id) if current.parent_id else None
    return list(reversed(path))


def _confirm_assets(job: ImportJob, actor_id: int) -> dict[str, Any]:
    (
        suppliers,
        locations,
        public_objects,
        units,
        categories,
    ) = _resolve_deferred_master_data(job, actor_id)
    auto_created = _auto_created_master_data(
        suppliers, locations, public_objects, units, categories
    )
    created: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    seen_serials: set[str] = set()
    seen_rfids: set[str] = set()
    for row in job.preview_data:
        normalized = row.get("normalized")
        if not isinstance(normalized, dict):
            raise BusinessException("导入预览包含无效数据，请重新上传")
        organization = db.session.get(Organization, normalized["organization_id"])
        category_id = normalized.get("category_id")
        category_create_path = normalized.get("category_create_path")
        if category_id is None and isinstance(category_create_path, list):
            category = categories.get(tuple(str(item) for item in category_create_path))
        else:
            assert category_id is not None
            category = db.session.get(AssetCategory, category_id)
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
            normalized.get(field) is None for field in ("unit_id", "source_id")
        ) or (
            normalized.get("location_id") is None
            and not normalized.get("location_keep_empty")
        )
        originals = {
            key: value
            for key, value in dict(normalized.get("originals") or {}).items()
            if value
        }
        history = normalized.get("history", [])
        supplier_name = normalized.get("supplier_create_name")
        if isinstance(supplier_name, str) and supplier_name:
            normalized["supplier_id"] = suppliers[supplier_name].id
        location_path = normalized.get("location_create_path")
        if (
            normalized.get("location_id") is None
            and isinstance(location_path, list)
            and location_path
        ):
            normalized["location_id"] = locations[
                tuple(str(item) for item in location_path)
            ].id
        public_object_name = normalized.get("public_object_create_name")
        if isinstance(public_object_name, str) and public_object_name:
            normalized["public_object_id"] = public_objects[public_object_name].id
        unit_name = normalized.get("unit_create_name")
        if isinstance(unit_name, str) and unit_name:
            normalized["unit_id"] = units[unit_name].id
        service_life = int(normalized.get("service_life_months", service_life))
        purchase_date = date.fromisoformat(normalized["purchase_date"])
        asset = Asset(
            asset_code=asset_code,
            asset_name=normalized["asset_name"],
            status=normalized.get("status", AssetStatus.IDLE.value),
            organization_id=organization.id,
            usage_company_id=normalized.get("usage_company_id"),
            usage_department_id=normalized.get("usage_department_id"),
            usage_type=normalized.get("usage_type"),
            holder_user_id=normalized.get("holder_user_id"),
            public_object_id=normalized.get("public_object_id"),
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
                "pending_location": bool(normalized.get("pending_location")),
                "pending_unit": bool(normalized.get("pending_unit")),
                "location_import_policy": (
                    "HOLDER_EXISTS_KEEP_EMPTY"
                    if normalized.get("location_keep_empty")
                    else None
                ),
            },
            data_completeness=(
                AssetDataCompleteness.INCOMPLETE.value
                if incomplete
                or normalized.get("pending_location")
                or normalized.get("pending_unit")
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
        _create_historical_lifecycle(
            asset_id=asset.id,
            history=history,
            actor_id=actor_id,
            import_job_no=job.job_no,
        )
        created.append({"id": asset.id, "asset_code": asset.asset_code})
    pending_assets = [
        created[index]
        for index, row in enumerate(job.preview_data)
        if isinstance(row.get("normalized"), dict)
        and (
            row["normalized"].get("pending_location")
            or row["normalized"].get("pending_unit")
        )
    ]
    if pending_assets:
        existing_notification = db.session.scalar(
            select(UserNotification).where(
                UserNotification.user_id == actor_id,
                UserNotification.deduplication_key
                == f"IMPORT_PENDING_LOCATION:{job.id}",
            )
        )
        if existing_notification is None:
            db.session.add(
                UserNotification(
                    user_id=actor_id,
                    notification_type="IMPORT_PENDING_COMPLETION",
                    title="资产导入完成，存在待补充信息",
                    content=(
                        f"导入任务 {job.job_no} 已完成，其中 "
                        f"{len(pending_assets)} 件资产存在待补充信息，请及时处理。"
                    ),
                    deduplication_key=f"IMPORT_PENDING_LOCATION:{job.id}",
                )
            )
    return {
        "created_assets": created,
        "auto_created_master_data": auto_created,
        "pending_completion_assets": pending_assets,
    }


def _create_historical_lifecycle(
    *,
    asset_id: int,
    history: Sequence[Mapping[str, Any]],
    actor_id: int,
    import_job_no: str,
) -> None:
    if not history:
        return
    for item in history:
        occurred_text = item.get("occurred_at")
        try:
            occurred_at = (
                datetime.fromisoformat(str(occurred_text)) if occurred_text else None
            )
        except ValueError:
            occurred_at = None
        operator_id = item.get("operator_id")
        if operator_id is None:
            operator_id = actor_id
        record = AssetLifecycleRecord(
            asset_id=asset_id,
            operation_type=str(item.get("operation_type") or "历史记录"),
            operation_no=str(item.get("operation_no") or import_job_no),
            operator_id=int(operator_id),
            before_data=None,
            after_data=None,
            remark=str(item.get("remark") or ""),
            created_at=occurred_at or utc_now(),
        )
        db.session.add(record)


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
    header_length = max((len(row) for row in rows), default=0)
    sheet_rows = []
    for row_index, row in enumerate(rows, start=1):
        padded_row = list(row) + [""] * (header_length - len(row))
        cells = "".join(
            _xlsx_cell(f"{_column_name(column_index)}{row_index}", str(value))
            for column_index, value in enumerate(padded_row)
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
            "上海黄豆网络科技有限公司",
            "示例笔记本",
            "电子产品及通信设备/笔记本电脑",
            "台",
            "5999.00",
            "",
            "2026-08-03",
            "示例供应商",
            "",
            "购入",
            "海粟",
            "上海黄豆网络科技有限公司",
            "",
            "",
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
