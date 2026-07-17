"""Unified response envelope + status code enum.

Mirrors com.soybean.quick.common.Result<T> / ResultCode from the Java side.
All controllers return Result.success(data) or Result.fail(...).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ResultCode(Enum):
    SUCCESS = (200, "OK")
    BAD_REQUEST = (400, "Bad Request")
    UNAUTHORIZED = (401, "Unauthorized")
    FORBIDDEN = (403, "Forbidden")
    NOT_FOUND = (404, "Not Found")
    INTERNAL_ERROR = (500, "Internal Server Error")
    BUSINESS_ERROR = (1000, "Business Error")

    def __init__(self, code: int, message: str) -> None:
        self.code: int = code
        self.message: str = message


@dataclass
class Result:
    """Wire-level response envelope: { code, message, data }."""

    code: int
    message: str
    data: Any = field(default=None)

    @classmethod
    def success(cls, data: Any = None) -> "Result":
        return cls(
            code=ResultCode.SUCCESS.code, message=ResultCode.SUCCESS.message, data=data
        )

    @classmethod
    def fail(cls, code: ResultCode | int, message: str | None = None) -> "Result":
        if isinstance(code, ResultCode):
            return cls(code=code.code, message=message or code.message, data=None)
        return cls(code=code, message=message or "error", data=None)

    def to_dict(self) -> dict[str, Any]:
        # Drop `data` when None so the wire is compact (mirrors JsonInclude.NON_NULL).
        d = asdict(self)
        if d.get("data") is None:
            d.pop("data", None)
        return d


@dataclass
class PageResult:
    """Paginated payload: data list + total + page/size (0-indexed page to match Java side)."""

    items: list[Any]
    total: int
    page: int
    size: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": self.items,
            "total": self.total,
            "page": self.page,
            "size": self.size,
        }
