"""Global error-envelope security contracts."""

import logging

from app.common import ResultCode


def test_unexpected_error_hides_internal_details(app, client, caplog) -> None:
    secret_detail = "mysql://secret-user:secret-password@internal-db/assets"

    @app.get("/_test/unexpected-error")
    def raise_unexpected_error() -> None:
        raise RuntimeError(secret_detail)

    with caplog.at_level(logging.ERROR):
        response = client.get("/_test/unexpected-error")

    assert response.status_code == 500
    body = response.get_json()
    assert body["code"] == ResultCode.INTERNAL_ERROR.code
    assert body["message"] == ResultCode.INTERNAL_ERROR.message
    assert body["request_id"]
    assert secret_detail not in response.get_data(as_text=True)
    assert secret_detail not in caplog.text
    assert "Unexpected error (RuntimeError)" in caplog.text
