"""BusinessException + global error handlers.

Controllers and services raise BusinessException(ResultCode.X) or
BusinessException("message") — translator returns Result.fail(...) JSON.
"""

from __future__ import annotations

import logging

from flask import Flask, jsonify
from flask.typing import ResponseReturnValue
from marshmallow import ValidationError
from werkzeug.exceptions import HTTPException

from app.common.result import Result, ResultCode

log = logging.getLogger(__name__)


class BusinessException(Exception):
    """Domain error; translated by the global handler into Result.fail(...)."""

    def __init__(
        self,
        message: str | None = None,
        code: int | None = None,
        result_code: ResultCode | None = None,
    ) -> None:
        if result_code is not None:
            self.code = result_code.code
            super().__init__(message or result_code.message)
        elif code is not None:
            self.code = code
            super().__init__(message or "business error")
        else:
            self.code = ResultCode.BUSINESS_ERROR.code
            super().__init__(message or ResultCode.BUSINESS_ERROR.message)

    @property
    def message(self) -> str:
        return str(self)


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(BusinessException)
    def handle_business(e: BusinessException) -> ResponseReturnValue:
        log.warning("Business error: %s", e.message)
        return jsonify(Result.fail(e.code, e.message).to_dict()), 200

    @app.errorhandler(ValidationError)
    def handle_validation(e: ValidationError) -> ResponseReturnValue:
        msg = "; ".join(
            f"{field}: {', '.join(errs) if isinstance(errs, list) else errs}"
            for field, errs in e.messages.items()  # type: ignore[union-attr]
        )
        return jsonify(Result.fail(ResultCode.BAD_REQUEST, msg).to_dict()), 400

    @app.errorhandler(401)
    def handle_unauthorized(e: HTTPException) -> ResponseReturnValue:
        return (
            jsonify(
                Result.fail(
                    ResultCode.UNAUTHORIZED, e.description or "unauthorized"
                ).to_dict()
            ),
            401,
        )

    @app.errorhandler(403)
    def handle_forbidden(e: HTTPException) -> ResponseReturnValue:
        return (
            jsonify(
                Result.fail(
                    ResultCode.FORBIDDEN, e.description or "forbidden"
                ).to_dict()
            ),
            403,
        )

    @app.errorhandler(404)
    def handle_not_found(e: HTTPException) -> ResponseReturnValue:
        return (
            jsonify(
                Result.fail(
                    ResultCode.NOT_FOUND, e.description or "not found"
                ).to_dict()
            ),
            404,
        )

    @app.errorhandler(HTTPException)
    def handle_http(e: HTTPException) -> ResponseReturnValue:
        code = e.code or ResultCode.INTERNAL_ERROR.code
        return jsonify(Result.fail(code, e.description or "http error").to_dict()), code

    @app.errorhandler(Exception)
    def handle_other(e: Exception) -> ResponseReturnValue:
        log.exception("Unexpected error")
        return jsonify(Result.fail(ResultCode.INTERNAL_ERROR, str(e)).to_dict()), 500
