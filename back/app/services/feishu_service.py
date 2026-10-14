"""Feishu native integration gateway and safe synchronization helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7
from flask import current_app
from sqlalchemy import select

from app.common import BusinessException, ResultCode
from app.extensions import db
from app.models import OperationRequest, Organization, Role, User, UserRole
from app.services import security_service

_API_BASE = "https://open.feishu.cn/open-apis"
_TIMEOUT_SECONDS = 8.0


@dataclass(frozen=True)
class FeishuCallback:
    event_id: str
    event_type: str
    payload: dict[str, Any]


class FeishuConfigurationError(BusinessException):
    pass


class ChallengeRequired(Exception):
    """Internal control-flow signal for Feishu URL verification."""


def enabled() -> bool:
    return bool(current_app.config.get("FEISHU_INTEGRATION_ENABLED"))


def notifications_enabled() -> bool:
    return enabled() and bool(current_app.config.get("FEISHU_NOTIFICATION_ENABLED"))


def configured() -> bool:
    return bool(
        current_app.config.get("FEISHU_APP_ID")
        and current_app.config.get("FEISHU_APP_SECRET")
    )


def _require_config() -> tuple[str, str]:
    if not enabled() or not configured():
        raise FeishuConfigurationError(
            "飞书原生集成未启用或未配置", result_code=ResultCode.BAD_REQUEST
        )
    return (
        str(current_app.config["FEISHU_APP_ID"]),
        str(current_app.config["FEISHU_APP_SECRET"]),
    )


def _read_json(raw: bytes) -> dict[str, Any]:
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return body if isinstance(body, dict) else {}


def _api_error(body: dict[str, Any]) -> str | None:
    code = body.get("code")
    message = body.get("msg")
    if code is None and message is None:
        return None
    return f"飞书接口调用失败：{message or code}"


def _raise_api_error(body: dict[str, Any], cause: Exception) -> None:
    message = _api_error(body)
    if message is None:
        message = f"飞书接口请求失败（HTTP {getattr(cause, 'code', 'unknown')}）"
    raise BusinessException(message) from cause


def _transport_error(error: Exception) -> BusinessException:
    reason = getattr(error, "reason", error)
    return BusinessException(f"无法连接飞书接口，请检查网络：{reason}")


def _response_format_error(error: Exception) -> BusinessException:
    return BusinessException("飞书接口返回格式异常，请稍后重试")


def _post(
    path: str, payload: dict[str, Any], *, token: str | None = None
) -> dict[str, Any]:
    app_id, app_secret = _require_config()
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    request = Request(
        f"{_API_BASE}{path}",
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            body_value = _read_json(response.read())
    except HTTPError as error:
        body_value = _read_json(error.read())
        _raise_api_error(body_value, error)
    except (URLError, TimeoutError) as error:
        raise _transport_error(error) from error
    except json.JSONDecodeError as error:
        raise _response_format_error(error) from error
    if int(body_value.get("code", -1)) != 0:
        # Feishu messages are business signals, not secrets. Keep only stable fields.
        raise BusinessException(_api_error(body_value) or "飞书接口调用失败")
    data = body_value.get("data")
    if isinstance(data, dict):
        return dict(data)
    # Some Feishu endpoints (for example tenant_access_token) return business
    # fields at the envelope top level instead of nesting them under ``data``.
    return {
        key: value for key, value in body_value.items() if key not in {"code", "msg"}
    }


def _get(path: str, *, token: str) -> dict[str, Any]:
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    request = Request(
        f"{_API_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            body_value = _read_json(response.read())
    except HTTPError as error:
        body_value = _read_json(error.read())
        _raise_api_error(body_value, error)
    except (URLError, TimeoutError) as error:
        raise _transport_error(error) from error
    except json.JSONDecodeError as error:
        raise _response_format_error(error) from error
    if int(body_value.get("code", -1)) != 0:
        raise BusinessException(_api_error(body_value) or "飞书接口调用失败")
    return dict(body_value.get("data") or {})


def tenant_access_token() -> str:
    app_id, app_secret = _require_config()
    data = _post(
        "/auth/v3/tenant_access_token/internal",
        {"app_id": app_id, "app_secret": app_secret},
    )
    token = data.get("tenant_access_token")
    if not isinstance(token, str) or not token:
        raise BusinessException("飞书访问凭证无效")
    return token


def authorize_url() -> str:
    app_id, _ = _require_config()
    redirect_uri = current_app.config.get("FEISHU_REDIRECT_URI")
    if not redirect_uri:
        raise BusinessException("飞书登录回调地址未配置")
    query = urlencode(
        {
            "app_id": app_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": "asset-system",
        }
    )
    return f"https://open.feishu.cn/open-apis/authen/v1/authorize?{query}"


def login_by_code(
    code: str,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    """Exchange a Feishu OAuth code for this system's own authenticated session."""
    from app.services.auth_service import _user_to_dict

    token_data = exchange_code(code)
    open_id = token_data.get("open_id")
    if not isinstance(open_id, str) or not open_id:
        raise BusinessException("飞书登录身份无效", result_code=ResultCode.UNAUTHORIZED)
    user = db.session.scalar(select(User).where(User.feishu_open_id == open_id))
    if user is None:
        user = _ensure_login_fallback_user(open_id)
    if user is None or not user.enabled:
        security_service.record_event(
            "LOGIN_FAILURE",
            username=open_id,
            ip_address=ip_address,
            detail="feishu_identity_not_bound",
            commit=True,
        )
        raise BusinessException(
            "飞书账号尚未绑定系统用户", result_code=ResultCode.UNAUTHORIZED
        )

    now = datetime.now(timezone.utc)
    user.failed_login_count = 0
    user.last_login_at = now
    session_data = security_service.issue_session(
        user, ip_address=ip_address, user_agent=user_agent
    )
    security_service.record_event(
        "LOGIN_SUCCESS", user=user, ip_address=ip_address, detail="feishu_oauth"
    )
    db.session.commit()
    return {**session_data, "user": _user_to_dict(user)}


def exchange_code(code: str) -> dict[str, Any]:
    _require_config()
    token_data = _post(
        "/authen/v1/oidc/access_token",
        {"grant_type": "authorization_code", "code": code},
        token=tenant_access_token(),
    )
    user_access_token = token_data.get("access_token")
    if not isinstance(user_access_token, str) or not user_access_token:
        raise BusinessException("飞书用户访问凭证无效")
    user_data = _get("/authen/v1/user_info", token=user_access_token)
    return {**token_data, **user_data}


def _upsert_feishu_user(item: dict[str, Any]) -> tuple[User, bool]:
    """Upsert one Feishu contact and return ``(user, created)``.

    This helper is shared by scheduled/manual organization sync and the
    first-login fallback. It is intentionally idempotent: repeated calls
    update the same local user rather than creating duplicates.
    """
    open_id = str(item.get("open_id") or "").strip()
    feishu_user_id = str(item.get("user_id") or "").strip()
    name = str(item.get("name") or "").strip()
    if not open_id or not name:
        raise BusinessException("飞书用户信息不完整")

    row = db.session.scalar(select(User).where(User.feishu_open_id == open_id))
    if row is None and feishu_user_id:
        row = db.session.scalar(
            select(User).where(User.feishu_user_id == feishu_user_id)
        )
    if row is None:
        emails = item.get("emails")
        email = emails[0] if isinstance(emails, list) and emails else None
        if email is None:
            email = item.get("email") or item.get("enterprise_email")
        username = str(email or f"feishu_{open_id}").lower()[:64]
        row = db.session.scalar(select(User).where(User.username == username))
    created = row is None
    if row is None:
        row = User(
            username=username,
            password=f"feishu-unmanaged-{uuid4().hex}",
            enabled=bool(item.get("active", True)),
        )
        db.session.add(row)
        db.session.flush()

    default_role = db.session.scalar(
        select(Role).where(Role.code == "USER", Role.enabled.is_(True))
    )
    if default_role is not None:
        role_ids = set(
            db.session.scalars(
                select(UserRole.role_id).where(UserRole.user_id == row.id)
            ).all()
        )
        if default_role.id not in role_ids:
            db.session.add(UserRole(user_id=row.id, role_id=default_role.id))

    department_ids = item.get("department_ids")
    departments = department_ids if isinstance(department_ids, list) else []
    department_rows = {
        str(organization.feishu_department_id): organization
        for organization in db.session.scalars(
            select(Organization).where(Organization.feishu_department_id.is_not(None))
        ).all()
    }
    department_id = next(
        (
            value
            for value in departments
            if isinstance(value, str) and value in department_rows
        ),
        None,
    )
    if department_id is not None:
        row.organization_id = department_rows[department_id].id
    elif not row.organization_id:
        row.organization_id = _default_feishu_organization_id()

    row.nickname = name or row.nickname
    row.enabled = bool(item.get("active", True))
    row.feishu_open_id = open_id
    row.feishu_user_id = feishu_user_id or None
    union_id = item.get("union_id")
    if isinstance(union_id, str) and union_id:
        row.feishu_union_id = union_id
    row.feishu_synced_at = datetime.now(timezone.utc)
    row.feishu_sync_status = "SYNCED"
    return row, created


def _ensure_login_fallback_user(open_id: str) -> User | None:
    """Create a missing contact on first login, after refreshing departments."""
    sync_organization_tree()
    item = current_user(open_id)
    if not isinstance(item, dict):
        return None
    user, _created = _upsert_feishu_user(item)
    db.session.commit()
    return user


def current_user(open_id: str) -> dict[str, Any]:
    data = _get(
        f"/contact/v3/users/{open_id}?user_id_type=open_id",
        token=tenant_access_token(),
    )
    user = data.get("user")
    if isinstance(user, dict):
        return user
    return data


def send_text(open_id: str, text: str) -> str:
    data = _post(
        "/im/v1/messages?receive_id_type=open_id",
        {
            "receive_id": open_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        },
        token=tenant_access_token(),
    )
    message_id = data.get("message_id")
    return message_id if isinstance(message_id, str) else ""


def verify_callback_signature(
    *,
    signature: str = "",
    timestamp: str = "",
    nonce: str = "",
    body: bytes = b"",
    verification_token: str = "",
) -> None:
    """Validate a callback by token or the official signature algorithm."""
    configured_token = current_app.config.get("FEISHU_VERIFICATION_TOKEN")
    token = verification_token or current_app.config.get("FEISHU_TOKEN") or ""
    if configured_token and hmac.compare_digest(str(token), str(configured_token)):
        return
    encrypt_key = current_app.config.get("FEISHU_ENCRYPT_KEY")
    if not all([signature, timestamp, nonce, encrypt_key]):
        raise BusinessException("飞书回调签名无效", result_code=ResultCode.UNAUTHORIZED)
    expected = hashlib.sha256(
        f"{timestamp}{nonce}{encrypt_key}".encode("utf-8") + body
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise BusinessException("飞书回调签名无效", result_code=ResultCode.UNAUTHORIZED)


def verify_callback_token(token: str, *, required: bool = True) -> None:
    """Validate the token carried by a decrypted callback payload."""
    configured_token = current_app.config.get("FEISHU_VERIFICATION_TOKEN")
    if configured_token:
        if not token or not hmac.compare_digest(str(token), str(configured_token)):
            raise BusinessException(
                "飞书回调令牌无效", result_code=ResultCode.UNAUTHORIZED
            )
        return
    if required:
        raise BusinessException(
            "飞书回调令牌未配置", result_code=ResultCode.UNAUTHORIZED
        )


def decrypt_callback(body: bytes) -> bytes:
    """Decrypt an official ``{"encrypt": "..."}`` callback envelope."""
    encrypt_key = current_app.config.get("FEISHU_ENCRYPT_KEY")
    if not encrypt_key:
        raise BusinessException(
            "飞书回调加密密钥未配置", result_code=ResultCode.UNAUTHORIZED
        )
    try:
        envelope = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BusinessException("飞书回调内容无效") from error
    if not isinstance(envelope, dict) or not isinstance(envelope.get("encrypt"), str):
        raise BusinessException("飞书回调缺少加密内容")
    try:
        ciphertext = base64.b64decode(envelope["encrypt"], validate=True)
        if len(ciphertext) <= 16:
            raise ValueError("ciphertext is too short")
        decryptor = Cipher(
            algorithms.AES(hashlib.sha256(str(encrypt_key).encode("utf-8")).digest()),
            modes.CBC(ciphertext[:16]),
        ).decryptor()
        padded = decryptor.update(ciphertext[16:]) + decryptor.finalize()
        unpadder = PKCS7(128).unpadder()
        plain = unpadder.update(padded) + unpadder.finalize()
    except (ValueError, TypeError) as error:
        raise BusinessException(
            "飞书回调内容解密失败", result_code=ResultCode.UNAUTHORIZED
        ) from error
    return plain


def parse_callback(body: bytes) -> FeishuCallback:
    try:
        envelope = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BusinessException("飞书回调内容无效") from error
    if not isinstance(envelope, dict):
        raise BusinessException("飞书回调内容无效")
    if envelope.get("type") == "url_verification":
        verify_callback_signature(
            verification_token=str(envelope.get("token") or ""),
            body=body,
        )
        raise ChallengeRequired(str(envelope.get("challenge") or ""))
    header = envelope.get("header")
    if not isinstance(header, dict):
        raise BusinessException("飞书回调缺少事件头")
    event_id = header.get("event_id")
    event_type = header.get("event_type")
    if not isinstance(event_id, str) or not event_id:
        raise BusinessException("飞书回调事件 ID 无效")
    if not isinstance(event_type, str) or not event_type:
        raise BusinessException("飞书回调事件类型无效")
    event = envelope.get("event")
    if not isinstance(event, dict):
        raise BusinessException("飞书回调事件内容无效")
    return FeishuCallback(event_id=event_id, event_type=event_type, payload=event)


def pending_approval_operations() -> list[Any]:
    """List external approval requests that can still consume a remote decision."""
    return list(
        db.session.scalars(
            select(OperationRequest)
            .where(
                OperationRequest.approval_channel == "FEISHU",
                OperationRequest.approval_status == "PENDING",
                OperationRequest.execution_status.not_in(
                    {"SUCCESS", "FAILED", "TERMINATED"}
                ),
                OperationRequest.external_instance_id.is_not(None),
            )
            .order_by(OperationRequest.id.asc())
        ).all()
    )


def sync_approval_operations() -> dict[str, int]:
    """Reconcile local requests with Feishu and persist immutable decision events."""
    from app.enums import ApprovalStatus
    from app.repositories.operation_repository import (
        external_approval_event_repository,
    )
    from app.services import approval_provider_service

    token = tenant_access_token()
    synced = 0
    for operation in pending_approval_operations():
        instance_code = operation.external_instance_id
        if not instance_code or instance_code.startswith("LOCAL-FEISHU-"):
            continue
        remote = _get(
            f"/approval/v4/instances/{instance_code}?user_id_type=open_id",
            token=token,
        )
        status = str(remote.get("status") or "").upper()
        if status not in {
            ApprovalStatus.APPROVED.value,
            ApprovalStatus.REJECTED.value,
            ApprovalStatus.WITHDRAWN.value,
        }:
            continue
        tasks = remote.get("task_list")
        if not isinstance(tasks, list):
            tasks = []
        completed_at = ""
        for task in reversed(tasks):
            if not isinstance(task, dict):
                continue
            value = task.get("end_time")
            if value:
                completed_at = str(value)
                break
        event_id = f"SYNC-FEISHU-{instance_code}-{status}-{completed_at or 'PENDING'}"
        if (
            external_approval_event_repository.find_by_event("FEISHU", event_id)
            is not None
        ):
            continue
        approval_provider_service.handle_callback(
            provider="FEISHU",
            external_event_id=event_id,
            external_instance_id=instance_code,
            status=status,
            actor_id=operation.applicant_id,
        )
        synced += 1
    return {"synced": synced}


def sync_organization_tree() -> dict[str, int]:
    token = tenant_access_token()
    departments: list[dict[str, Any]] = []
    page_token = ""
    while True:
        query = "page_size=50"
        if page_token:
            query += f"&page_token={page_token}"
        data = _get(f"/contact/v3/departments?{query}", token=token)
        items = data.get("items")
        if isinstance(items, list):
            departments.extend(item for item in items if isinstance(item, dict))
        page_token = str(data.get("page_token") or "")
        if data.get("has_more") is not True or not page_token:
            break

    synced = 0
    now = datetime.now(timezone.utc)
    by_id = {
        str(row.feishu_department_id): row
        for row in db.session.scalars(
            select(Organization).where(Organization.feishu_department_id.is_not(None))
        ).all()
    }
    children: dict[str | None, list[dict[str, Any]]] = {}
    for item in departments:
        parent = item.get("parent_department_id")
        children.setdefault(
            parent if isinstance(parent, str) and parent else None, []
        ).append(item)

    def upsert(item: dict[str, Any], parent_id: int | None) -> None:
        nonlocal synced
        external_id = str(item.get("department_id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not external_id or not name:
            return
        row = by_id.get(external_id)
        if row is None:
            code = f"FEISHU-{external_id}"
            row = db.session.scalar(
                select(Organization).where(Organization.code == code)
            )
            if row is None:
                row = Organization(code=code, name=name, parent_id=parent_id)
                db.session.add(row)
                db.session.flush()
        row.name = name
        if parent_id is not None:
            row.parent_id = parent_id
        row.feishu_department_id = external_id
        row.feishu_synced_at = now
        db.session.flush()
        synced += 1
        for child in children.get(external_id, []):
            upsert(child, row.id)

    for root in children.get(None, []):
        upsert(root, None)
    db.session.commit()
    return {"departments": synced}


def _default_feishu_organization_id() -> int | None:
    """Return the first synced Feishu root department as a safe default."""
    return db.session.scalar(
        select(Organization.id)
        .where(Organization.feishu_department_id.is_not(None))
        .order_by(
            Organization.parent_id.asc().nulls_first(),
            Organization.id.asc(),
        )
        .limit(1)
    )


def sync_users() -> dict[str, int]:
    token = tenant_access_token()
    users: list[dict[str, Any]] = []
    page_token = ""
    while True:
        query = "page_size=50&user_id_type=open_id"
        if page_token:
            query += f"&page_token={page_token}"
        data = _get(f"/contact/v3/users?{query}", token=token)
        items = data.get("items")
        if isinstance(items, list):
            users.extend(item for item in items if isinstance(item, dict))
        page_token = str(data.get("page_token") or "")
        if data.get("has_more") is not True or not page_token:
            break

    now = datetime.now(timezone.utc)
    synced = 0
    incoming_open_ids = {
        str(item.get("open_id") or "").strip()
        for item in users
        if isinstance(item, dict) and str(item.get("open_id") or "").strip()
    }
    missing_rows = db.session.scalars(
        select(User).where(
            User.feishu_open_id.is_not(None),
            User.feishu_open_id.notin_(incoming_open_ids),
        )
    ).all()
    for missing in missing_rows:
        missing.enabled = False
        missing.feishu_synced_at = now
        missing.feishu_sync_status = "MISSING"
        missing.feishu_open_id = None
    for item in users:
        open_id = str(item.get("open_id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not open_id or not name:
            continue
        _upsert_feishu_user(item)
        synced += 1
    db.session.commit()
    return {"users": synced}


def sync_all() -> dict[str, int]:
    organization_result = sync_organization_tree()
    user_result = sync_users()
    return {**organization_result, **user_result}


__all__ = [
    "FeishuCallback",
    "sync_approval_operations",
    "authorize_url",
    "configured",
    "enabled",
    "exchange_code",
    "notifications_enabled",
    "parse_callback",
    "send_text",
    "sync_all",
    "sync_organization_tree",
    "sync_users",
    "tenant_access_token",
    "verify_callback_signature",
]
