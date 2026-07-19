"""Operation handler contracts and explicit registry."""

from app.operations.registry import (
    OperationHandler,
    OperationHandlerRegistry,
    operation_handler_registry,
)

__all__ = [
    "OperationHandler",
    "OperationHandlerRegistry",
    "operation_handler_registry",
]
