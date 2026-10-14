from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from os import utime
from pathlib import Path
import re
from types import SimpleNamespace

from app.enums import AssetDataCompleteness, AssetStatus, DataScope
from app.extensions import db
from app.models import (
    Asset,
    AssetCategory,
    AssetLifecycleRecord,
    AssetRepairRecord,
    AssetLocation,
    AssetSource,
    ExportJob,
    Organization,
    Permission,
    Role,
    RolePermission,
    Unit,
    User,
    UserRole,
)
from app.models.mixins import utc_now
from app.security.passwords import hash_password
from app.services import export_service
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas

_PASSWORD = "Export-Password-2026!"


def _user(client, username: str, permissions: list[str]) -> tuple[User, dict[str, str]]:
    user = User(username=username, password=hash_password(_PASSWORD), enabled=True)
    role = Role(
        code=f"ROLE_{username.upper()}",
        name=f"{username} role",
        data_scope=DataScope.ALL.value,
    )
    permission_rows = []
    for code in permissions:
        permission = db.session.scalar(
            db.select(Permission).where(Permission.code == code)
        )
        if permission is None:
            permission = Permission(code=code, name=code, module="asset")
            db.session.add(permission)
        permission_rows.append(permission)
    db.session.add_all([user, role])
    db.session.flush()
    db.session.add(UserRole(user_id=user.id, role_id=role.id))
    db.session.add_all(
        [
            RolePermission(role_id=role.id, permission_id=permission.id)
            for permission in permission_rows
        ]
    )
    db.session.commit()
    token = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": _PASSWORD},
    ).get_json()["data"]["token"]
    return user, {"Authorization": f"Bearer {token}"}


def _asset() -> Asset:
    organization = Organization(code="EXP-ORG", name="读书资产公司")
    unit = Unit(code="EXP-UNIT", name="台")
    source = AssetSource(code="EXP-SOURCE", name="采购")
    location = AssetLocation(code="EXP-LOC", name="上海仓库", is_selectable=True)
    manager = User(
        username="export-manager",
        nickname="资产管理员",
        password=hash_password(_PASSWORD),
        enabled=True,
    )
    db.session.add_all([organization, unit, source, location, manager])
    db.session.flush()
    category = AssetCategory(
        code="EXP-CATEGORY",
        name="笔记本电脑",
        service_life_months=36,
        default_unit_id=unit.id,
    )
    db.session.add(category)
    db.session.flush()
    asset = Asset(
        asset_code="DS-IT-0001",
        asset_name="MacBook Pro",
        status=AssetStatus.IDLE.value,
        organization_id=organization.id,
        category_id=category.id,
        unit_id=unit.id,
        original_amount=Decimal("12999.00"),
        purchase_date=date(2026, 7, 31),
        service_life_months=36,
        expected_expiry_date=date(2029, 7, 31),
        manager_id=manager.id,
        source_id=source.id,
        location_id=location.id,
        serial_number="C02EXPORT",
        normalized_serial="c02export",
        rfid_tag="RFID-EXPORT-1",
        custom_attributes={},
        data_completeness=AssetDataCompleteness.COMPLETE.value,
    )
    db.session.add(asset)
    db.session.commit()
    return asset


def test_csv_export_uses_real_filters_amount_permission_and_audit(
    client, app, tmp_path
) -> None:
    app.config["EXPORT_STORAGE_DIR"] = str(tmp_path / "exports")
    asset = _asset()
    _, headers = _user(
        client,
        "export-admin",
        ["asset:view", "asset:export", "asset:amount:view"],
    )

    response = client.post(
        "/api/v1/exports",
        headers=headers,
        json={
            "job_type": "ASSET_CSV",
            "filters": {"company_name": "读书资产公司", "keyword": "MacBook"},
        },
    )
    payload = response.get_json()["data"]
    assert payload["status"] == "SUCCESS"
    assert payload["item_count"] == 1
    assert payload["original_name"].endswith(".csv")

    download = client.get(f"/api/v1/exports/{payload['id']}/download", headers=headers)
    assert download.status_code == 200
    assert download.data.startswith(b"\xef\xbb\xbf")
    text = download.data.decode("utf-8-sig")
    assert "资产编码,资产名称" in text
    assert "DS-IT-0001,MacBook Pro" in text
    assert "采购金额" in text
    assert "12999.00" in text

    lifecycle_types = set(
        db.session.scalars(
            db.select(AssetLifecycleRecord.operation_type).where(
                AssetLifecycleRecord.asset_id == asset.id
            )
        ).all()
    )
    assert "ASSET_EXPORT" in lifecycle_types


def test_csv_export_hides_amount_without_field_permission(
    client, app, tmp_path
) -> None:
    app.config["EXPORT_STORAGE_DIR"] = str(tmp_path / "exports")
    asset = _asset()
    _, headers = _user(client, "export-reader", ["asset:view", "asset:export"])

    created = client.post(
        "/api/v1/exports",
        headers=headers,
        json={"job_type": "ASSET_CSV", "asset_ids": [asset.id]},
    ).get_json()["data"]
    text = client.get(
        f"/api/v1/exports/{created['id']}/download", headers=headers
    ).data.decode("utf-8-sig")
    assert "采购金额" not in text
    assert "12999.00" not in text


def test_label_pdf_is_65_by_30_mm_and_contains_qr_and_barcode_job(
    client, app, tmp_path
) -> None:
    app.config["EXPORT_STORAGE_DIR"] = str(tmp_path / "exports")
    asset = _asset()
    _, headers = _user(client, "label-admin", ["asset:view", "asset:label:print"])

    created = client.post(
        "/api/v1/exports",
        headers=headers,
        json={"job_type": "LABEL_PDF", "asset_ids": [asset.id]},
    ).get_json()["data"]
    response = client.get(f"/api/v1/exports/{created['id']}/download", headers=headers)
    assert response.status_code == 200
    assert response.content_type == "application/pdf"
    assert response.headers["Content-Disposition"].startswith("attachment;")
    assert response.data.startswith(b"%PDF-1.4")
    preview = client.get(
        "/api/v1/exports/labels",
        headers=headers,
        query_string={"asset_ids": [asset.id]},
    )
    assert preview.status_code == 200
    assert preview.content_type == "application/pdf"
    assert preview.data.startswith(b"%PDF-1.4")
    assert preview.headers["Content-Disposition"].startswith("inline;")
    assert re.search(rb"/MediaBox\s+\[\s*0\s+0\s+184\.28\s+85\.04\s*\]", response.data)
    assert b"/FontFile2" in response.data
    assert b"NotoSansCJKsc" in response.data
    assert b"STSong-Light" not in response.data
    assert b"/Count 1" in response.data
    # Text must be painted black after the white page background is painted.
    first_text = response.data.index(b"BT 1 0 0 1")
    first_black_fill = response.data.index(b"0 0 0 rg")
    assert first_black_fill < first_text
    assert response.data.count(b"BT 1 0 0 1") == 8
    assert b"DS-IT-0001" in response.data
    assert b"MacBook Pro" in response.data
    assert b"2026-07-31" in response.data
    assert b"43.5 68.8 m 43.5 30 l S" in response.data
    # The reference layout contains both a QR matrix and a Code 39 barcode.
    assert response.data.count(b" re f") > 100
    lifecycle = db.session.scalar(
        db.select(AssetLifecycleRecord).where(
            AssetLifecycleRecord.asset_id == asset.id,
            AssetLifecycleRecord.operation_type == "ASSET_LABEL_PRINT",
        )
    )
    assert lifecycle is not None


def test_label_qr_targets_scan_use_page(client, app) -> None:
    asset = _asset()
    _, headers = _user(client, "qr-label-admin", ["asset:view", "asset:label:print"])

    response = client.get(
        "/api/v1/exports/labels",
        headers=headers,
        query_string={
            "asset_ids": [asset.id],
            "base_url": "https://assets.example.com/app",
        },
    )

    assert response.status_code == 200
    with app.app_context():
        qr_value = export_service._asset_qr_value(
            asset, qr_base_url="https://assets.example.com/app"
        )
    assert (
        qr_value
        == "https://assets.example.com/app/scan-use?asset_code=DS-IT-0001&barcode=C02EXPORT"
    )


def test_label_name_shrinks_to_fit_value_cell() -> None:
    font_name = export_service._label_font_name()
    asset_name = "超长固定资产名称用于验证标签单元格边界限制" * 3
    max_width = 82.0

    class RecordingCanvas:
        def __init__(self) -> None:
            self.font_sizes: list[float] = []

        def setFillColorRGB(self, red: float, green: float, blue: float) -> None:
            assert (red, green, blue) == (0, 0, 0)

        def setFont(self, name: str, size: float) -> None:
            assert name == font_name
            self.font_sizes.append(size)

        def drawString(self, x: float, y: float, text: str) -> None:
            assert (x, y, text) == (46.0, 46.8, asset_name)

    recording_canvas = RecordingCanvas()
    export_service._draw_text(
        recording_canvas,
        asset_name,
        font_size=8.5,
        x=46.0,
        y=46.8,
        max_width=max_width,
    )

    expected_size = 8.5 * max_width / pdfmetrics.stringWidth(asset_name, font_name, 8.5)
    assert recording_canvas.font_sizes == [expected_size]
    assert expected_size < 8.5
    assert pdfmetrics.stringWidth(asset_name, font_name, expected_size) <= max_width


def test_label_draws_asset_name_with_cell_width_limit(monkeypatch) -> None:
    draw_text_calls: list[tuple[str, dict[str, float | None]]] = []
    original_draw_text = export_service._draw_text

    def recording_draw_text(canvas: Canvas, value: str, **kwargs: object) -> None:
        draw_text_calls.append((value, kwargs))
        original_draw_text(canvas, value, **kwargs)

    monkeypatch.setattr(export_service, "_draw_text", recording_draw_text)
    asset = SimpleNamespace(
        asset_code="DS-IT-0001",
        asset_name="很长的固定资产名称",
        serial_number="C02EXPORT",
        purchase_date=date(2026, 7, 31),
    )
    canvas = Canvas(
        BytesIO(),
        pagesize=(export_service._LABEL_WIDTH, export_service._LABEL_HEIGHT),
    )

    export_service._draw_label(
        canvas,
        asset,  # type: ignore[arg-type]
        "读书资产公司",
        qr_base_url="https://assets.example.com/app",
    )

    name_call = next(
        call for call in draw_text_calls if call[0] == "很长的固定资产名称"
    )
    assert name_call[1]["max_width"] == 82.0


def test_cleanup_removes_ephemeral_preview_files(client, app, tmp_path) -> None:
    app.config["EXPORT_STORAGE_DIR"] = str(tmp_path / "exports")
    preview = Path(app.config["EXPORT_STORAGE_DIR"]) / "preview" / "expired.pdf"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"%PDF-1.4\n")
    stale_time = (utc_now() - timedelta(minutes=31)).timestamp()
    utime(preview, (stale_time, stale_time))

    removed = export_service.cleanup_expired_files()
    assert removed == 0
    assert not preview.exists()


def test_exports_are_private_and_cleanup_expires_files(client, app, tmp_path) -> None:
    storage_root = tmp_path / "exports"
    app.config["EXPORT_STORAGE_DIR"] = str(storage_root)
    asset = _asset()
    owner, owner_headers = _user(client, "export-owner", ["asset:view", "asset:export"])
    _, other_headers = _user(client, "export-other", ["asset:view", "asset:export"])
    created = client.post(
        "/api/v1/exports",
        headers=owner_headers,
        json={"job_type": "ASSET_CSV", "asset_ids": [asset.id]},
    ).get_json()["data"]

    denied = client.get(
        f"/api/v1/exports/{created['id']}/download", headers=other_headers
    ).get_json()
    assert denied["code"] == 404

    job = db.session.get(ExportJob, created["id"])
    assert job is not None and job.created_by == owner.id
    file_path = Path(app.config["EXPORT_STORAGE_DIR"]) / job.storage_key
    assert file_path.is_file()
    job.expires_at = utc_now() - timedelta(minutes=1)
    db.session.commit()

    removed = export_service.cleanup_expired_files()
    assert removed == 1
    assert not file_path.exists()
    refreshed = db.session.get(ExportJob, created["id"])
    assert refreshed is not None and refreshed.status == "EXPIRED"


def test_repair_csv_export_is_structured_and_amount_is_field_protected(
    client, app, tmp_path
) -> None:
    app.config["EXPORT_STORAGE_DIR"] = str(tmp_path / "exports")
    asset = _asset()
    sent_at = utc_now()
    db.session.add(
        AssetRepairRecord(
            asset_id=asset.id,
            repair_no="RPR-000001",
            before_status=AssetStatus.IN_USE.value,
            fault_description="无法开机",
            repair_supplier_name="原厂服务中心",
            repair_cost=Decimal("620.00"),
            sent_at=sent_at,
            completed_at=sent_at + timedelta(hours=5),
            repair_result="更换主板后恢复正常",
        )
    )
    db.session.commit()
    _, headers = _user(
        client,
        "repair-export-admin",
        ["asset:view", "repair:export", "asset:amount:view"],
    )

    created = client.post(
        "/api/v1/exports",
        headers=headers,
        json={"job_type": "REPAIR_CSV", "asset_ids": [asset.id]},
    ).get_json()["data"]
    assert created["status"] == "SUCCESS"
    assert created["item_count"] == 1
    assert created["original_name"].endswith(".csv")

    response = client.get(f"/api/v1/exports/{created['id']}/download", headers=headers)
    text = response.data.decode("utf-8-sig")
    assert "维修单号,资产编码,资产名称" in text
    assert "RPR-000001" in text
    assert "无法开机" in text
    assert "维修费用" in text
    assert "620.00" in text
    assert (
        db.session.scalar(
            db.select(AssetLifecycleRecord).where(
                AssetLifecycleRecord.asset_id == asset.id,
                AssetLifecycleRecord.operation_type == "REPAIR_EXPORT",
            )
        )
        is not None
    )


def test_repair_csv_export_hides_cost_without_amount_permission(
    client, app, tmp_path
) -> None:
    app.config["EXPORT_STORAGE_DIR"] = str(tmp_path / "exports")
    asset = _asset()
    db.session.add(
        AssetRepairRecord(
            asset_id=asset.id,
            repair_no="RPR-000002",
            before_status=AssetStatus.IDLE.value,
            fault_description="屏幕损坏",
            repair_cost=Decimal("888.00"),
            sent_at=utc_now(),
        )
    )
    db.session.commit()
    _, headers = _user(client, "repair-export-reader", ["asset:view", "repair:export"])

    created = client.post(
        "/api/v1/exports",
        headers=headers,
        json={"job_type": "REPAIR_CSV", "asset_ids": [asset.id]},
    ).get_json()["data"]
    text = client.get(
        f"/api/v1/exports/{created['id']}/download", headers=headers
    ).data.decode("utf-8-sig")
    assert "维修费用" not in text
    assert "888.00" not in text


def test_scrap_csv_export_only_includes_scrapped_assets(client, app, tmp_path) -> None:
    app.config["EXPORT_STORAGE_DIR"] = str(tmp_path / "exports")
    asset = _asset()
    asset.status = AssetStatus.SCRAPPED.value
    asset.custom_attributes = {
        "scrap": {"scrap_date": "2026-08-01", "scrap_amount": "300.00"}
    }
    db.session.commit()
    _, headers = _user(client, "scrap-export-admin", ["asset:view", "scrap:export"])

    created = client.post(
        "/api/v1/exports",
        headers=headers,
        json={"job_type": "SCRAP_CSV", "filters": {"keyword": "MacBook"}},
    ).get_json()["data"]
    assert created["status"] == "SUCCESS"
    response = client.get(f"/api/v1/exports/{created['id']}/download", headers=headers)
    text = response.data.decode("utf-8-sig")
    assert "DS-IT-0001,MacBook Pro" in text
    assert (
        db.session.scalar(
            db.select(AssetLifecycleRecord).where(
                AssetLifecycleRecord.asset_id == asset.id,
                AssetLifecycleRecord.operation_type == "SCRAP_EXPORT",
            )
        )
        is not None
    )


def test_scrap_csv_export_rejects_non_scrapped_selected_asset(
    client, app, tmp_path
) -> None:
    app.config["EXPORT_STORAGE_DIR"] = str(tmp_path / "exports")
    asset = _asset()
    _, headers = _user(client, "scrap-export-reader", ["asset:view", "scrap:export"])

    response = client.post(
        "/api/v1/exports",
        headers=headers,
        json={"job_type": "SCRAP_CSV", "asset_ids": [asset.id]},
    ).get_json()
    assert response["code"] == 400
