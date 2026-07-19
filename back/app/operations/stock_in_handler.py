"""Stock-in execution adapter for the common operation executor."""

from app.services import asset_service


class StockInHandler:
    operation_type = "STOCK_IN"
    safe_error_message = "资产入库执行失败，请联系管理员或稍后重试"

    def revalidate_for_execution(self, operation_request_id: int) -> None:
        return None

    def execute(self, operation_request_id: int, actor_id: int) -> None:
        asset_service.stock_in_request(operation_request_id, actor_id)


__all__ = ["StockInHandler"]
