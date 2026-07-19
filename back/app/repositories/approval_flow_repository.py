"""Versioned approval-flow graph queries."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.enums import FlowStatus
from app.extensions import db
from app.models import (
    ApprovalFlowDefinition,
    ApprovalFlowLayer,
    ApprovalFlowVersion,
)


class ApprovalFlowRepository:
    def list_definitions(self) -> list[ApprovalFlowDefinition]:
        statement = select(ApprovalFlowDefinition).order_by(
            ApprovalFlowDefinition.operation_type.asc()
        )
        return list(db.session.scalars(statement).all())

    def get_definition(self, flow_id: int) -> ApprovalFlowDefinition | None:
        return db.session.get(ApprovalFlowDefinition, flow_id)

    def find_definition(self, operation_type: str) -> ApprovalFlowDefinition | None:
        return db.session.scalar(
            select(ApprovalFlowDefinition).where(
                ApprovalFlowDefinition.operation_type == operation_type
            )
        )

    def add_definition(
        self, definition: ApprovalFlowDefinition
    ) -> ApprovalFlowDefinition:
        db.session.add(definition)
        db.session.flush()
        return definition

    def list_versions(self, flow_id: int) -> list[ApprovalFlowVersion]:
        statement = (
            select(ApprovalFlowVersion)
            .where(ApprovalFlowVersion.flow_definition_id == flow_id)
            .options(
                selectinload(ApprovalFlowVersion.layers).selectinload(
                    ApprovalFlowLayer.assignee_rules
                )
            )
            .order_by(ApprovalFlowVersion.version_no.desc())
        )
        return list(db.session.scalars(statement).all())

    def find_draft(self, flow_id: int) -> ApprovalFlowVersion | None:
        statement = (
            select(ApprovalFlowVersion)
            .where(
                ApprovalFlowVersion.flow_definition_id == flow_id,
                ApprovalFlowVersion.status == FlowStatus.DRAFT.value,
            )
            .options(
                selectinload(ApprovalFlowVersion.layers).selectinload(
                    ApprovalFlowLayer.assignee_rules
                )
            )
            .order_by(ApprovalFlowVersion.version_no.desc())
            .limit(1)
        )
        return db.session.scalar(statement)

    def add_version(self, version: ApprovalFlowVersion) -> ApprovalFlowVersion:
        db.session.add(version)
        db.session.flush()
        return version

    def has_published(self, flow_id: int) -> bool:
        statement = select(ApprovalFlowVersion.id).where(
            ApprovalFlowVersion.flow_definition_id == flow_id,
            ApprovalFlowVersion.status == FlowStatus.PUBLISHED.value,
        )
        return db.session.scalar(statement.limit(1)) is not None

    def find_published(self, operation_type: str) -> ApprovalFlowVersion | None:
        statement = (
            select(ApprovalFlowVersion)
            .join(
                ApprovalFlowDefinition,
                ApprovalFlowDefinition.id == ApprovalFlowVersion.flow_definition_id,
            )
            .where(
                ApprovalFlowDefinition.operation_type == operation_type,
                ApprovalFlowDefinition.status == FlowStatus.PUBLISHED.value,
                ApprovalFlowVersion.status == FlowStatus.PUBLISHED.value,
            )
            .options(
                selectinload(ApprovalFlowVersion.layers).selectinload(
                    ApprovalFlowLayer.assignee_rules
                )
            )
            .order_by(ApprovalFlowVersion.version_no.desc())
            .limit(1)
        )
        return db.session.scalar(statement)

    def next_version_no(self, flow_id: int) -> int:
        latest = db.session.scalar(
            select(func.max(ApprovalFlowVersion.version_no)).where(
                ApprovalFlowVersion.flow_definition_id == flow_id
            )
        )
        return int(latest or 0) + 1

    def load_version_graph(self, version_id: int) -> ApprovalFlowVersion | None:
        statement = (
            select(ApprovalFlowVersion)
            .where(ApprovalFlowVersion.id == version_id)
            .options(
                selectinload(ApprovalFlowVersion.layers).selectinload(
                    ApprovalFlowLayer.assignee_rules
                )
            )
        )
        return db.session.scalar(statement)


approval_flow_repository = ApprovalFlowRepository()

__all__ = ["ApprovalFlowRepository", "approval_flow_repository"]
