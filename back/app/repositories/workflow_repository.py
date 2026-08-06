"""Operation request, stock-in, and approval queries."""

from __future__ import annotations

from sqlalchemy import ColumnElement, false, func, or_, select, update

from app.enums import ApprovalStatus, ExecutionStatus, OperationType, RuntimeTaskStatus
from app.extensions import db
from app.models import (
    ApprovalRecord,
    ApprovalStep,
    ApprovalTask,
    OperationRequest,
    StockInItem,
    StockInRequest,
)
from app.repositories.base import BaseRepository, Page


class OperationRequestRepository(BaseRepository[OperationRequest]):
    def __init__(self) -> None:
        super().__init__(OperationRequest)

    def transition_pending(
        self,
        operation_request_id: int,
        expected_version: int,
        target_status: str,
    ) -> bool:
        result = db.session.execute(
            update(OperationRequest)
            .where(
                OperationRequest.id == operation_request_id,
                OperationRequest.approval_status == ApprovalStatus.PENDING.value,
                OperationRequest.version == expected_version,
            )
            .values(
                approval_status=target_status,
                version=OperationRequest.version + 1,
            )
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    def claim_execution(
        self,
        operation_request_id: int,
        expected_status: str,
        expected_version: int,
    ) -> bool:
        result = db.session.execute(
            update(OperationRequest)
            .where(
                OperationRequest.id == operation_request_id,
                OperationRequest.approval_status == ApprovalStatus.APPROVED.value,
                OperationRequest.execution_status == expected_status,
                OperationRequest.version == expected_version,
            )
            .values(
                execution_status=ExecutionStatus.PROCESSING.value,
                execution_error=None,
                version=OperationRequest.version + 1,
            )
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    def find_for_update(self, operation_request_id: int) -> OperationRequest | None:
        statement = (
            select(OperationRequest)
            .where(OperationRequest.id == operation_request_id)
            .with_for_update()
        )
        return db.session.scalar(statement)

    def find_by_idempotency_key(
        self, applicant_id: int, operation_type: str, idempotency_key: str
    ) -> OperationRequest | None:
        statement = select(OperationRequest).where(
            OperationRequest.applicant_id == applicant_id,
            OperationRequest.operation_type == operation_type,
            OperationRequest.idempotency_key == idempotency_key,
        )
        return db.session.scalar(statement)

    def find_by_external_instance(
        self, external_instance_id: str
    ) -> OperationRequest | None:
        statement = select(OperationRequest).where(
            OperationRequest.external_instance_id == external_instance_id
        )
        return db.session.scalar(statement)

    def page_stock_in(
        self,
        *,
        organization_ids: set[int] | None,
        include_applicant_id: int | None,
        page: int,
        size: int,
        request_no: str | None = None,
        approval_status: str | None = None,
        execution_status: str | None = None,
    ) -> Page[tuple[OperationRequest, StockInRequest]]:
        filters: list[ColumnElement[bool]] = [
            OperationRequest.operation_type == OperationType.STOCK_IN.value
        ]
        if organization_ids is not None:
            scope_filters: list[ColumnElement[bool]] = []
            if organization_ids:
                scope_filters.append(
                    StockInRequest.organization_id.in_(organization_ids)
                )
            if include_applicant_id is not None:
                scope_filters.append(
                    OperationRequest.applicant_id == include_applicant_id
                )
            filters.append(or_(*scope_filters) if scope_filters else false())
        if request_no:
            filters.append(OperationRequest.request_no == request_no.strip())
        if approval_status:
            filters.append(OperationRequest.approval_status == approval_status)
        if execution_status:
            filters.append(OperationRequest.execution_status == execution_status)

        from_clause = OperationRequest.__table__.join(
            StockInRequest.__table__,
            StockInRequest.operation_request_id == OperationRequest.id,
        )
        total = int(
            db.session.scalar(
                select(func.count(OperationRequest.id))
                .select_from(from_clause)
                .where(*filters)
            )
            or 0
        )
        stmt = (
            select(OperationRequest, StockInRequest)
            .select_from(from_clause)
            .where(*filters)
            .order_by(OperationRequest.id.desc())
            .limit(size)
            .offset(page * size)
        )
        rows = list(db.session.execute(stmt).tuples().all())
        return Page(items=rows, total=total, page=page, size=size)

    def find_accessible_stock_in(
        self,
        operation_request_id: int,
        organization_ids: set[int] | None,
        include_applicant_id: int | None,
    ) -> tuple[OperationRequest, StockInRequest] | None:
        filters: list[ColumnElement[bool]] = [
            OperationRequest.id == operation_request_id,
            OperationRequest.operation_type == OperationType.STOCK_IN.value,
        ]
        if organization_ids is not None:
            scope_filters: list[ColumnElement[bool]] = []
            if organization_ids:
                scope_filters.append(
                    StockInRequest.organization_id.in_(organization_ids)
                )
            if include_applicant_id is not None:
                scope_filters.append(
                    OperationRequest.applicant_id == include_applicant_id
                )
            filters.append(or_(*scope_filters) if scope_filters else false())
        statement = (
            select(OperationRequest, StockInRequest)
            .join(
                StockInRequest,
                StockInRequest.operation_request_id == OperationRequest.id,
            )
            .where(*filters)
        )
        return db.session.execute(statement).tuples().one_or_none()


class StockInRequestRepository(BaseRepository[StockInRequest]):
    def __init__(self) -> None:
        super().__init__(StockInRequest)

    def find_by_operation(self, operation_request_id: int) -> StockInRequest | None:
        return self.find_one(
            StockInRequest.operation_request_id == operation_request_id
        )


class StockInItemRepository(BaseRepository[StockInItem]):
    def __init__(self) -> None:
        super().__init__(StockInItem)

    def find_by_request(self, stock_in_request_id: int) -> list[StockInItem]:
        stmt = (
            select(StockInItem)
            .where(StockInItem.stock_in_request_id == stock_in_request_id)
            .order_by(StockInItem.id.asc())
        )
        return list(db.session.scalars(stmt).all())

    def has_supplier_reference(self, supplier_id: int) -> bool:
        statement = (
            select(StockInItem.id)
            .where(StockInItem.supplier_id == supplier_id)
            .limit(1)
        )
        return db.session.scalar(statement) is not None

    def normalized_serial_in_open_request(self, normalized_serial: str) -> bool:
        stmt = (
            select(StockInItem.id)
            .join(StockInRequest, StockInRequest.id == StockInItem.stock_in_request_id)
            .join(
                OperationRequest,
                OperationRequest.id == StockInRequest.operation_request_id,
            )
            .where(
                StockInItem.normalized_serial == normalized_serial,
                OperationRequest.approval_status == ApprovalStatus.PENDING.value,
            )
            .limit(1)
        )
        return db.session.scalar(stmt) is not None

    def rfid_in_open_request(self, rfid_tag: str) -> bool:
        stmt = (
            select(StockInItem.id)
            .join(StockInRequest, StockInRequest.id == StockInItem.stock_in_request_id)
            .join(
                OperationRequest,
                OperationRequest.id == StockInRequest.operation_request_id,
            )
            .where(
                StockInItem.rfid_tag == rfid_tag,
                OperationRequest.approval_status == ApprovalStatus.PENDING.value,
            )
            .limit(1)
        )
        return db.session.scalar(stmt) is not None

    def release_identifier_reservations(self, stock_in_request_id: int) -> None:
        db.session.execute(
            update(StockInItem)
            .where(StockInItem.stock_in_request_id == stock_in_request_id)
            .values(serial_reservation_key=None, rfid_reservation_key=None)
            .execution_options(synchronize_session=False)
        )


class ApprovalStepRepository(BaseRepository[ApprovalStep]):
    def __init__(self) -> None:
        super().__init__(ApprovalStep)

    def find_by_operation(self, operation_request_id: int) -> ApprovalStep | None:
        return self.find_one(ApprovalStep.operation_request_id == operation_request_id)

    def find_current_for_update(self, operation_request_id: int) -> ApprovalStep | None:
        statement = (
            select(ApprovalStep)
            .where(
                ApprovalStep.operation_request_id == operation_request_id,
                ApprovalStep.status == RuntimeTaskStatus.PENDING.value,
            )
            .order_by(ApprovalStep.level_no.asc(), ApprovalStep.id.asc())
            .with_for_update()
            .limit(1)
        )
        return db.session.scalar(statement)

    def find_by_operation_ordered(
        self, operation_request_id: int
    ) -> list[ApprovalStep]:
        statement = (
            select(ApprovalStep)
            .where(ApprovalStep.operation_request_id == operation_request_id)
            .order_by(ApprovalStep.level_no.asc(), ApprovalStep.id.asc())
        )
        return list(db.session.scalars(statement).all())

    def claim_pending(self, step_id: int, expected_version: int) -> bool:
        result = db.session.execute(
            update(ApprovalStep)
            .where(
                ApprovalStep.id == step_id,
                ApprovalStep.status == RuntimeTaskStatus.PENDING.value,
                ApprovalStep.version == expected_version,
            )
            .values(version=ApprovalStep.version + 1)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1


class ApprovalTaskRepository(BaseRepository[ApprovalTask]):
    def __init__(self) -> None:
        super().__init__(ApprovalTask)

    def find_for_approver(
        self, approval_step_id: int, approver_id: int
    ) -> ApprovalTask | None:
        return self.find_one(
            ApprovalTask.approval_step_id == approval_step_id,
            ApprovalTask.approver_id == approver_id,
        )

    def find_for_update(
        self, approval_step_id: int, actor_id: int
    ) -> ApprovalTask | None:
        statement = (
            select(ApprovalTask)
            .where(
                ApprovalTask.approval_step_id == approval_step_id,
                ApprovalTask.approver_id == actor_id,
            )
            .order_by(ApprovalTask.id.asc())
            .with_for_update()
            .limit(1)
        )
        return db.session.scalar(statement)

    def find_by_idempotency_key(
        self, applicant_id: int, operation_type: str, idempotency_key: str
    ) -> OperationRequest | None:
        statement = select(OperationRequest).where(
            OperationRequest.applicant_id == applicant_id,
            OperationRequest.operation_type == operation_type,
            OperationRequest.idempotency_key == idempotency_key,
        )
        return db.session.scalar(statement)

    def find_by_step(self, approval_step_id: int) -> list[ApprovalTask]:
        stmt = (
            select(ApprovalTask)
            .where(ApprovalTask.approval_step_id == approval_step_id)
            .order_by(ApprovalTask.id.asc())
        )
        return list(db.session.scalars(stmt).all())


class ApprovalRecordRepository(BaseRepository[ApprovalRecord]):
    def __init__(self) -> None:
        super().__init__(ApprovalRecord)


operation_request_repository = OperationRequestRepository()
stock_in_request_repository = StockInRequestRepository()
stock_in_item_repository = StockInItemRepository()
approval_step_repository = ApprovalStepRepository()
approval_task_repository = ApprovalTaskRepository()
approval_record_repository = ApprovalRecordRepository()

__all__ = [
    "ApprovalStepRepository",
    "ApprovalTaskRepository",
    "ApprovalRecordRepository",
    "OperationRequestRepository",
    "StockInItemRepository",
    "StockInRequestRepository",
    "approval_step_repository",
    "approval_task_repository",
    "approval_record_repository",
    "operation_request_repository",
    "stock_in_item_repository",
    "stock_in_request_repository",
]
