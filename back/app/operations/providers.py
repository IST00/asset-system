"""Narrow approval-provider contracts and deterministic local FEISHU adapter."""

from __future__ import annotations

from typing import Protocol

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
approval_provider_registry.register(LocalFeishuApprovalProvider())

__all__ = [
    "ApprovalProvider",
    "ApprovalProviderRegistry",
    "LocalFeishuApprovalProvider",
    "approval_provider_registry",
]
