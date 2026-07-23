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
    assert response.get_json() == {
        "code": ResultCode.INTERNAL_ERROR.code,
        "message": ResultCode.INTERNAL_ERROR.message,
    }
    assert secret_detail not in response.get_data(as_text=True)
    assert secret_detail not in caplog.text
    assert "Unexpected error (RuntimeError)" in caplog.text
