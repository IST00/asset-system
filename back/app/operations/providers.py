"""Narrow approval-provider contracts and deterministic local FEISHU adapter."""

from __future__ import annotations

import json
from typing import Protocol

from flask import current_app

from app.common import BusinessException


class ApprovalProvider(Protocol):
    name: str

    def submit(self, operation_request_id: int) -> str | None: ...

    def withdraw(self, operation_request_id: int, actor_id: int) -> None: ...

    def urge(self, operation_request_id: int, actor_id: int) -> None: ...


class LocalFeishuApprovalProvider:
    name = "FEISHU"

    def submit(self, operation_request_id: int) -> str:
        return f"LOCAL-FEISHU-{operation_request_id}"

    def withdraw(self, operation_request_id: int, actor_id: int) -> None:
        return None

    def urge(self, operation_request_id: int, actor_id: int) -> None:
        return None


class FormalFeishuApprovalProvider:
    name = "FEISHU"

    def submit(self, operation_request_id: int) -> str | None:
        if not current_app.config.get("FEISHU_INTEGRATION_ENABLED"):
            return LocalFeishuApprovalProvider().submit(operation_request_id)
        from app.services import feishu_service

        operation = self._operation(operation_request_id)
        user_id = self._user_id(operation.applicant_id)
        # Feishu's approval API requires the form as a compact JSON string,
        # while each field must use the exact widget ID defined by the approval.
        form = json.dumps(
            self._form(operation),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        data = feishu_service._post(
            "/approval/v4/instances?user_id_type=user_id",
            {
                "approval_code": current_app.config.get("FEISHU_APPROVAL_CODE"),
                "user_id": user_id,
                "form": form,
            },
            token=feishu_service.tenant_access_token(),
        )
        instance_code = data.get("instance_code")
        if not isinstance(instance_code, str) or not instance_code:
            raise BusinessException("飞书审批实例创建失败")
        return instance_code

    def _operation(self, operation_request_id: int):
        from app.repositories.workflow_repository import operation_request_repository

        operation = operation_request_repository.get(operation_request_id)
        if operation is None:
            raise BusinessException("申请不存在")
        return operation

    def _form(self, operation) -> list[dict[str, object]]:
        remark = "资产系统扫码领用/借用申请"
        return [
            {
                "id": "widget16218492002480001",
                "type": "radioV2",
                "value": "kp2f501k-s1h8zfz30m-0",
            },
            {
                "id": "widget15754430770720001",
                "type": "radioV2",
                "value": "kjv71lzl-tktc3ebgve-9",
            },
            {"id": "widget16219142553360001", "type": "text", "value": remark},
            {"id": "widget17364096585570001", "type": "text", "value": remark},
            {"id": "widget16219131094550001", "type": "text", "value": remark},
            {
                "id": "widget16219110356590001",
                "type": "radioV2",
                "value": "kp3fycjy-x7v731crje-0",
            },
            {
                "id": "widget16219116284970001",
                "type": "radioV2",
                "value": "kp3gb1zr-ay8xcl836ye-3",
            },
            {
                "id": "widget17364085092740001",
                "type": "radioV2",
                "value": "ma0oi5n7-nqdphlbuu5h-1",
            },
            {
                "id": "widget17410659701140001",
                "type": "textarea",
                "value": remark,
            },
            {"id": "widget16218494663460001", "type": "number", "value": 1},
            {"id": "widget16219133848580001", "type": "amount", "value": "0"},
            {
                "id": "widget16220037148970001",
                "type": "input",
                "value": operation.request_no,
            },
            {
                "id": "widget0",
                "type": "textarea",
                "value": "扫码提交的资产领用申请",
            },
            {"id": "widget16657254857830001", "type": "text", "value": remark},
            {"id": "widget16582832538970001", "type": "textarea", "value": "无"},
        ]

    def _user_id(self, applicant_id: int) -> str:
        from app.extensions import db
        from app.models import User

        user_id = db.session.scalar(
            db.select(User.feishu_user_id).where(User.id == applicant_id)
        )
        if not user_id:
            raise BusinessException("申请人尚未绑定飞书账号")
        return str(user_id)

    def withdraw(self, operation_request_id: int, actor_id: int) -> None:
        del operation_request_id
        del actor_id

    def urge(self, operation_request_id: int, actor_id: int) -> None:
        del operation_request_id
        del actor_id


class ApprovalProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ApprovalProvider] = {}

    def register(self, provider: ApprovalProvider) -> None:
        name = provider.name.strip().upper()
        if name in self._providers:
            raise BusinessException(f"审批 Provider {name} 重复注册")
        self._providers[name] = provider

    def get(self, name: str) -> ApprovalProvider:
        normalized_name = name.strip().upper()
        provider = self._providers.get(normalized_name)
        if provider is None:
            raise BusinessException(f"审批 Provider {normalized_name} 未注册")
        return provider


approval_provider_registry = ApprovalProviderRegistry()
approval_provider_registry.register(FormalFeishuApprovalProvider())

__all__ = [
    "ApprovalProvider",
    "ApprovalProviderRegistry",
    "FormalFeishuApprovalProvider",
    "LocalFeishuApprovalProvider",
    "approval_provider_registry",
]
