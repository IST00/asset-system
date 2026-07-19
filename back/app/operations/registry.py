"""Explicit operation-type to handler registry."""

from __future__ import annotations

from typing import Protocol

from app.common import BusinessException


class OperationHandler(Protocol):
    operation_type: str

    def revalidate_for_execution(self, operation_request_id: int) -> None: ...

    def execute(self, operation_request_id: int, actor_id: int) -> None: ...


class OperationHandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, OperationHandler] = {}

    def register(self, handler: OperationHandler) -> None:
        operation_type = handler.operation_type.strip().upper()
        if operation_type in self._handlers:
            raise BusinessException(f"操作处理器 {operation_type} 重复注册")
        self._handlers[operation_type] = handler

    def get(self, operation_type: str) -> OperationHandler:
        normalized_type = operation_type.strip().upper()
        handler = self._handlers.get(normalized_type)
        if handler is None:
            raise BusinessException(f"操作处理器 {normalized_type} 未注册")
        return handler

    def clear(self) -> None:
        self._handlers.clear()

    def contains(self, operation_type: str) -> bool:
        return operation_type.strip().upper() in self._handlers


operation_handler_registry = OperationHandlerRegistry()

__all__ = [
    "OperationHandler",
    "OperationHandlerRegistry",
    "operation_handler_registry",
]
