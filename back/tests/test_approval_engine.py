"""Multi-layer OR/AND approval runtime contracts."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import app.services as services
from app import create_app
from app.common import BusinessException
from app.enums import (
    ApprovalStatus,
    AssigneeType,
    DataScope,
    ExecutionStatus,
    FlowStatus,
    RuntimeTaskStatus,
    SignMode,
)
from app.extensions import db
from app.models import (
    ApprovalFlowAssigneeRule,
    ApprovalFlowDefinition,
    ApprovalFlowLayer,
    ApprovalFlowVersion,
    ApprovalRecord,
    ApprovalStep,
    ApprovalTask,
    OperationRequest,
    Organization,
    Role,
    RoleDataScopeOrganization,
    User,
    UserRole,
)
from config import TestConfig


def _engine():
    engine = getattr(services, "approval_engine", None)
    assert engine is not None, "missing approval_engine service"
    return engine


def _operation(
    applicant_id: int, request_no: str = "ENGINE-REQUEST"
) -> OperationRequest:
    operation = OperationRequest(
        request_no=request_no,
        operation_type="TRANSFER",
        applicant_id=applicant_id,
        approval_status=ApprovalStatus.PENDING.value,
        execution_status=ExecutionStatus.NOT_STARTED.value,
    )
    db.session.add(operation)
    db.session.flush()
    return operation


def _flow(
    operation_type: str,
    layer_specs: list[tuple[str, bool, list[tuple[str, int]]]],
) -> ApprovalFlowVersion:
    definition = ApprovalFlowDefinition(
        operation_type=operation_type,
        name=f"{operation_type}审批",
        status=FlowStatus.PUBLISHED.value,
    )
    db.session.add(definition)
    db.session.flush()
    version = ApprovalFlowVersion(
        flow_definition_id=definition.id,
        version_no=1,
        status=FlowStatus.PUBLISHED.value,
    )
    db.session.add(version)
    db.session.flush()
    for level_no, (sign_mode, allow_self, assignees) in enumerate(layer_specs, start=1):
        layer = ApprovalFlowLayer(
            flow_version_id=version.id,
            level_no=level_no,
            sign_mode=sign_mode,
            allow_self_approval=allow_self,
        )
        db.session.add(layer)
        db.session.flush()
        db.session.add_all(
            [
                ApprovalFlowAssigneeRule(
                    layer_id=layer.id,
                    assignee_type=assignee_type,
                    assignee_id=assignee_id,
                )
                for assignee_type, assignee_id in assignees
            ]
        )
    db.session.flush()
    return version


def test_initialize_snapshots_layers_role_members_scope_and_future_edits(app) -> None:
    organization = Organization(code="ENGINE-ORG", name="审批组织")
    other_organization = Organization(code="ENGINE-OTHER", name="其它组织")
    applicant = User(username="engine-applicant", password="x", enabled=True)
    explicit = User(username="engine-explicit", password="x", enabled=True)
    in_scope = User(
        username="engine-in-scope",
        password="x",
        enabled=True,
        organization_id=None,
    )
    out_of_scope = User(
        username="engine-out-scope",
        password="x",
        enabled=True,
        organization_id=None,
    )
    role = Role(
        code="ENGINE-DEPARTMENT-ROLE",
        name="部门审批人",
        data_scope=DataScope.DEPARTMENT.value,
    )
    db.session.add_all(
        [
            organization,
            other_organization,
            applicant,
            explicit,
            in_scope,
            out_of_scope,
            role,
        ]
    )
    db.session.flush()
    in_scope.organization_id = organization.id
    out_of_scope.organization_id = other_organization.id
    db.session.add_all(
        [
            UserRole(user_id=in_scope.id, role_id=role.id),
            UserRole(user_id=out_of_scope.id, role_id=role.id),
        ]
    )
    operation = _operation(applicant.id)
    version = _flow(
        operation.operation_type,
        [
            (
                SignMode.OR_SIGN.value,
                False,
                [(AssigneeType.USER.value, explicit.id)],
            ),
            (
                SignMode.AND_SIGN.value,
                False,
                [(AssigneeType.ROLE.value, role.id)],
            ),
        ],
    )

    _engine().initialize(operation, version.id, organization.id)
    db.session.flush()
    steps = db.session.query(ApprovalStep).order_by(ApprovalStep.level_no).all()
    assert [step.status for step in steps] == [
        RuntimeTaskStatus.PENDING.value,
        RuntimeTaskStatus.WAITING.value,
    ]
    assert [
        task.approver_id
        for task in db.session.query(ApprovalTask).filter_by(
            approval_step_id=steps[0].id
        )
    ] == [explicit.id]
    assert [
        task.approver_id
        for task in db.session.query(ApprovalTask).filter_by(
            approval_step_id=steps[1].id
        )
    ] == [in_scope.id]

    rule = (
        db.session.query(ApprovalFlowAssigneeRule)
        .filter_by(assignee_type=AssigneeType.USER.value)
        .one()
    )
    rule.assignee_id = out_of_scope.id
    db.session.flush()
    assert (
        db.session.query(ApprovalTask)
        .filter_by(approval_step_id=steps[0].id)
        .one()
        .approver_id
        == explicit.id
    )


def test_initialize_rejects_missing_approver_and_disallowed_self_approval(app) -> None:
    organization = Organization(code="ENGINE-EMPTY-ORG", name="无审批人组织")
    applicant = User(username="engine-self", password="x", enabled=True)
    disabled = User(username="engine-disabled", password="x", enabled=False)
    db.session.add_all([organization, applicant, disabled])
    db.session.flush()
    operation = _operation(applicant.id, "ENGINE-NO-APPROVER")
    version = _flow(
        operation.operation_type,
        [
            (
                SignMode.OR_SIGN.value,
                False,
                [
                    (AssigneeType.USER.value, applicant.id),
                    (AssigneeType.USER.value, disabled.id),
                ],
            )
        ],
    )

    try:
        _engine().initialize(operation, version.id, organization.id)
    except BusinessException as error:
        assert "审批人" in error.message
    else:
        raise AssertionError("missing approver should reject initialization")
    assert db.session.query(ApprovalStep).count() == 0


def test_self_scope_role_only_resolves_the_applicant(app) -> None:
    organization = Organization(code="ENGINE-SELF-ORG", name="SELF审批组织")
    applicant = User(username="engine-self-applicant", password="x", enabled=True)
    coworker = User(username="engine-self-coworker", password="x", enabled=True)
    role = Role(
        code="ENGINE-SELF-ROLE",
        name="SELF角色",
        data_scope=DataScope.SELF.value,
    )
    db.session.add_all([organization, applicant, coworker, role])
    db.session.flush()
    applicant.organization_id = organization.id
    coworker.organization_id = organization.id
    db.session.add_all(
        [
            UserRole(user_id=applicant.id, role_id=role.id),
            UserRole(user_id=coworker.id, role_id=role.id),
        ]
    )
    operation = _operation(applicant.id, "ENGINE-SELF-ROLE")
    version = _flow(
        operation.operation_type,
        [
            (
                SignMode.OR_SIGN.value,
                True,
                [(AssigneeType.ROLE.value, role.id)],
            )
        ],
    )
    _engine().initialize(operation, version.id, organization.id)
    assert [task.approver_id for task in db.session.query(ApprovalTask).all()] == [
        applicant.id
    ]


def test_role_assignee_scope_matrix_resolves_expected_members(app) -> None:
    root = Organization(code="ENGINE-MATRIX-ROOT", name="矩阵根组织")
    target = Organization(code="ENGINE-MATRIX-TARGET", name="矩阵目标组织")
    child = Organization(code="ENGINE-MATRIX-CHILD", name="矩阵子组织")
    other = Organization(code="ENGINE-MATRIX-OTHER", name="矩阵其它组织")
    db.session.add_all([root, target, child, other])
    db.session.flush()
    target.parent_id = root.id
    child.parent_id = target.id
    users = {
        "root": User(
            username="engine-matrix-root",
            password="x",
            enabled=True,
            organization_id=root.id,
        ),
        "applicant": User(
            username="engine-matrix-applicant",
            password="x",
            enabled=True,
            organization_id=target.id,
        ),
        "peer": User(
            username="engine-matrix-peer",
            password="x",
            enabled=True,
            organization_id=target.id,
        ),
        "child": User(
            username="engine-matrix-child",
            password="x",
            enabled=True,
            organization_id=child.id,
        ),
        "other": User(
            username="engine-matrix-other",
            password="x",
            enabled=True,
            organization_id=other.id,
        ),
    }
    roles = {
        scope: Role(
            code=f"ENGINE-MATRIX-{scope}",
            name=f"矩阵{scope}",
            data_scope=scope,
        )
        for scope in (
            DataScope.SELF.value,
            DataScope.DEPARTMENT.value,
            DataScope.DEPARTMENT_TREE.value,
            DataScope.CUSTOM.value,
            DataScope.ALL.value,
        )
    }
    db.session.add_all([*users.values(), *roles.values()])
    db.session.flush()
    db.session.add_all(
        [
            UserRole(user_id=user.id, role_id=role.id)
            for role in roles.values()
            for user in users.values()
        ]
    )
    db.session.add(
        RoleDataScopeOrganization(
            role_id=roles[DataScope.CUSTOM.value].id,
            organization_id=target.id,
        )
    )
    db.session.flush()

    resolve = services.permission_service.enabled_role_member_ids
    applicant_id = users["applicant"].id
    assert resolve(roles[DataScope.SELF.value].id, target.id, applicant_id) == [
        applicant_id
    ]
    assert set(
        resolve(roles[DataScope.DEPARTMENT.value].id, target.id, applicant_id)
    ) == {users["applicant"].id, users["peer"].id}
    assert set(
        resolve(roles[DataScope.DEPARTMENT_TREE.value].id, target.id, applicant_id)
    ) == {users["root"].id, users["applicant"].id, users["peer"].id}
    assert set(resolve(roles[DataScope.CUSTOM.value].id, target.id, applicant_id)) == {
        user.id for user in users.values()
    }
    assert set(resolve(roles[DataScope.ALL.value].id, target.id, applicant_id)) == {
        user.id for user in users.values()
    }


def test_or_then_and_sign_advances_layers_and_approves_request(app) -> None:
    organization = Organization(code="ENGINE-SIGN-ORG", name="会签组织")
    applicant = User(username="engine-sign-applicant", password="x", enabled=True)
    approvers = [
        User(username=f"engine-approver-{index}", password="x", enabled=True)
        for index in range(1, 5)
    ]
    db.session.add_all([organization, applicant, *approvers])
    db.session.flush()
    operation = _operation(applicant.id, "ENGINE-SIGN")
    version = _flow(
        operation.operation_type,
        [
            (
                SignMode.OR_SIGN.value,
                False,
                [
                    (AssigneeType.USER.value, approvers[0].id),
                    (AssigneeType.USER.value, approvers[1].id),
                ],
            ),
            (
                SignMode.AND_SIGN.value,
                False,
                [
                    (AssigneeType.USER.value, approvers[2].id),
                    (AssigneeType.USER.value, approvers[3].id),
                ],
            ),
        ],
    )
    engine = _engine()
    engine.initialize(operation, version.id, organization.id)
    db.session.flush()

    first_outcome = engine.approve(operation.id, approvers[0].id, "第一层同意")
    assert first_outcome.request_approved is False
    assert first_outcome.next_layer_activated is True
    steps = db.session.query(ApprovalStep).order_by(ApprovalStep.level_no).all()
    assert steps[0].status == RuntimeTaskStatus.APPROVED.value
    assert steps[1].status == RuntimeTaskStatus.PENDING.value
    first_tasks = (
        db.session.query(ApprovalTask).filter_by(approval_step_id=steps[0].id).all()
    )
    assert sorted(task.status for task in first_tasks) == ["APPROVED", "WITHDRAWN"]

    partial = engine.approve(operation.id, approvers[2].id, None)
    assert partial.request_approved is False
    assert steps[1].status == RuntimeTaskStatus.PENDING.value
    completed = engine.approve(operation.id, approvers[3].id, "会签完成")
    assert completed.request_approved is True
    assert operation.approval_status == ApprovalStatus.APPROVED.value
    assert steps[1].status == RuntimeTaskStatus.APPROVED.value
    assert db.session.query(ApprovalRecord).count() == 3


def test_rejection_ends_request_and_withdraws_later_layers(app) -> None:
    organization = Organization(code="ENGINE-REJECT-ORG", name="拒绝组织")
    applicant = User(username="engine-reject-applicant", password="x", enabled=True)
    approvers = [
        User(username=f"engine-reject-{index}", password="x", enabled=True)
        for index in range(2)
    ]
    db.session.add_all([organization, applicant, *approvers])
    db.session.flush()
    operation = _operation(applicant.id, "ENGINE-REJECT")
    version = _flow(
        operation.operation_type,
        [
            (
                SignMode.OR_SIGN.value,
                False,
                [(AssigneeType.USER.value, approvers[0].id)],
            ),
            (
                SignMode.OR_SIGN.value,
                False,
                [(AssigneeType.USER.value, approvers[1].id)],
            ),
        ],
    )
    engine = _engine()
    engine.initialize(operation, version.id, organization.id)
    db.session.flush()

    outcome = engine.reject(operation.id, approvers[0].id, "不符合要求")
    assert outcome.request_rejected is True
    assert operation.approval_status == ApprovalStatus.REJECTED.value
    steps = db.session.query(ApprovalStep).order_by(ApprovalStep.level_no).all()
    assert [step.status for step in steps] == ["REJECTED", "WITHDRAWN"]
    later_task = (
        db.session.query(ApprovalTask).filter_by(approval_step_id=steps[1].id).one()
    )
    assert later_task.status == RuntimeTaskStatus.WITHDRAWN.value


def test_withdraw_requires_applicant_and_closes_all_runtime_rows(app) -> None:
    organization = Organization(code="ENGINE-WITHDRAW-ORG", name="撤回组织")
    applicant = User(username="engine-withdraw-applicant", password="x", enabled=True)
    approver = User(username="engine-withdraw-approver", password="x", enabled=True)
    db.session.add_all([organization, applicant, approver])
    db.session.flush()
    operation = _operation(applicant.id, "ENGINE-WITHDRAW")
    version = _flow(
        operation.operation_type,
        [
            (
                SignMode.OR_SIGN.value,
                False,
                [(AssigneeType.USER.value, approver.id)],
            )
        ],
    )
    engine = _engine()
    engine.initialize(operation, version.id, organization.id)
    db.session.flush()

    try:
        engine.withdraw(operation.id, approver.id, "越权撤回")
    except BusinessException as error:
        assert error.code == 403
    else:
        raise AssertionError("non-applicant withdrawal should fail")
    engine.withdraw(operation.id, applicant.id, "申请人撤回")
    assert operation.approval_status == ApprovalStatus.WITHDRAWN.value
    assert db.session.query(ApprovalStep).one().status == "WITHDRAWN"
    assert db.session.query(ApprovalTask).one().status == "WITHDRAWN"


def test_concurrent_or_sign_decisions_produce_one_terminal_transition(
    tmp_path,
) -> None:
    database = tmp_path / "approval-engine-concurrency.db"

    class ConcurrentConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{database}"

    concurrent_app = create_app(config=ConcurrentConfig)
    with concurrent_app.app_context():
        db.create_all()
        organization = Organization(code="ENGINE-CONCURRENT", name="并发组织")
        applicant = User(
            username="engine-concurrent-applicant", password="x", enabled=True
        )
        approvers = [
            User(
                username=f"engine-concurrent-approver-{index}",
                password="x",
                enabled=True,
            )
            for index in range(2)
        ]
        db.session.add_all([organization, applicant, *approvers])
        db.session.flush()
        operation = _operation(applicant.id, "ENGINE-CONCURRENT")
        version = _flow(
            operation.operation_type,
            [
                (
                    SignMode.OR_SIGN.value,
                    False,
                    [
                        (AssigneeType.USER.value, approvers[0].id),
                        (AssigneeType.USER.value, approvers[1].id),
                    ],
                )
            ],
        )
        _engine().initialize(operation, version.id, organization.id)
        db.session.commit()
        operation_id = operation.id
        approver_ids = [approver.id for approver in approvers]

    barrier = Barrier(2)

    def decide(approver_id: int) -> str:
        with concurrent_app.app_context():
            barrier.wait()
            try:
                services.approval_engine.approve(operation_id, approver_id, "并发同意")
                db.session.commit()
                return "APPROVED"
            except BusinessException:
                db.session.rollback()
                return "CONFLICT"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(decide, approver_ids))

    assert sorted(results) == ["APPROVED", "CONFLICT"]
    with concurrent_app.app_context():
        persisted = db.session.get(OperationRequest, operation_id)
        assert persisted is not None
        assert persisted.approval_status == ApprovalStatus.APPROVED.value
        assert db.session.query(ApprovalRecord).count() == 1
        assert sorted(task.status for task in db.session.query(ApprovalTask).all()) == [
            RuntimeTaskStatus.APPROVED.value,
            RuntimeTaskStatus.WITHDRAWN.value,
        ]
        db.drop_all()
