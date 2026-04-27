"""Common package: unified Result envelope, ResultCode, BusinessException."""

from app.common.errors import BusinessException, register_error_handlers
from app.common.result import PageResult, Result, ResultCode

__all__ = [
    "BusinessException",
    "PageResult",
    "Result",
    "ResultCode",
    "register_error_handlers",
]
