"""Tests for early Phoenix Core contract skeletons."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

from phoenix_office.cli import _validate_codex_pilot_authorization_packet
from phoenix_office.core.contracts import (
    CODEX_PILOT_AUDIT_EVENT_TRANSITIONS,
    CODEX_PILOT_AUTHORIZATION_FINGERPRINT_FIELDS,
    CODEX_PILOT_REQUIRED_VALIDATION_COMMANDS,
    ApprovalDecision,
    ApprovalPolicy,
    ApprovalPreview,
    ApprovalRecord,
    ApprovalRequest,
    ApprovalStatus,
    ApprovedScope,
    CodexHandoffPackage,
    CodexPilotAuthorizationPacket,
    CodexPilotEvidenceControl,
    CodexPilotEvidencePackage,
    CodexPilotEvidenceReviewerRole,
    CodexPilotEvidenceStatus,
    EventSeverity,
    EvidenceResult,
    EvidenceType,
    FailureCode,
    OperationType,
    PermissionMode,
    PluginCapability,
    PluginFailureMode,
    Requester,
    RequesterType,
    RiskLevel,
    SourceKind,
    TaskEnvelope,
    TaskPermissions,
    TaskPriority,
    TaskSource,
    TaskStatus,
    VerificationEvidence,
    VerificationPlan,
    VerifierType,
    WorkerError,
    WorkerEvent,
    WorkerEventType,
    WorkerType,
    codex_pilot_audit_event_digest,
    codex_pilot_authorization_fingerprint,
    codex_pilot_objective_digest,
    compose_codex_pilot_initial_claim_bundle,
    derive_codex_pilot_attempt_snapshot,
    validate_codex_pilot_attempt_snapshot,
    validate_codex_pilot_attempt_snapshot_binding,
    validate_codex_pilot_audit_event_binding,
    validate_codex_pilot_audit_event_record,
    validate_codex_pilot_authorization_packet,
    validate_codex_pilot_claim_binding,
    validate_codex_pilot_claim_record,
)

FIXED_TIME = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)


def test_contract_enum_values_match_architecture_docs():
    assert TaskStatus.REQUESTED.value == "requested"
    assert TaskPriority.URGENT.value == "urgent"
    assert RequesterType.GITHUB.value == "github"
    assert SourceKind.GITHUB_ISSUE.value == "github_issue"
    assert WorkerType.CODEX.value == "codex"
    assert WorkerEventType.APPROVAL_REQUESTED.value == "approval_requested"
    assert EventSeverity.ERROR.value == "error"
    assert OperationType.SIMULATE.value == "simulate"
    assert RiskLevel.CRITICAL.value == "critical"
    assert PermissionMode.EXTERNAL_COMMUNICATION.value == "external_communication"
    assert ApprovalStatus.PENDING.value == "pending"
    assert ApprovalDecision.DENIED.value == "denied"
    assert EvidenceType.HUMAN_CONFIRMATION.value == "human_confirmation"
    assert EvidenceResult.INCONCLUSIVE.value == "inconclusive"
    assert VerifierType.SYSTEM.value == "system"
    assert FailureCode.POLICY_BLOCKED.value == "policy_blocked"


def test_task_envelope_creation_and_serialization():
    task = TaskEnvelope(
        task_id="task-1",
        title="Implement contract skeletons",
        objective="Create early Phoenix Core contracts.",
        requester=Requester(type=RequesterType.HUMAN, id="matth"),
        source=TaskSource(kind=SourceKind.GITHUB_ISSUE, uri="github://issues/17"),
        status=TaskStatus.PLANNED,
        priority=TaskPriority.HIGH,
        constraints=["Do not build orchestrator runtime."],
        acceptance_criteria=["pytest passes", "ruff passes"],
        context_refs=["docs/architecture/contracts.md"],
        allowed_resources={"repositories": ["Phoenix-AI-Platform/phoenix-office"]},
        permissions=TaskPermissions(read=True, write=True),
        approval_policy=ApprovalPolicy(required_before=[PermissionMode.EXECUTE]),
        verification_plan=VerificationPlan(
            commands=["python -m pytest"],
            evidence_required=[EvidenceType.TEST_OUTPUT],
        ),
        created_at=FIXED_TIME,
        updated_at=FIXED_TIME,
    )

    data = task.to_dict()
    assert data["status"] == "planned"
    assert data["requester"] == {"type": "human", "id": "matth"}
    assert data["permissions"]["write"] is True
    assert data["approval_policy"]["required_before"] == ["execute"]
    assert data["verification_plan"]["evidence_required"] == ["test_output"]
    assert data["created_at"] == "2026-06-26T12:00:00+00:00"
    assert json.loads(task.to_json()) == data


def test_worker_event_creation_and_serialization():
    event = WorkerEvent(
        event_id="event-1",
        task_id="task-1",
        worker_id="codex-1",
        worker_type=WorkerType.CODEX,
        event_type=WorkerEventType.FAILED,
        message="Validation failed.",
        status="failed",
        severity=EventSeverity.ERROR,
        data={"check": "pytest"},
        artifact_refs=["artifact://pytest-output"],
        error=WorkerError(
            code=FailureCode.VALIDATION_FAILED,
            message="One test failed.",
            retryable=False,
        ),
        created_at=FIXED_TIME,
    )

    data = event.to_dict()
    assert data["worker_type"] == "codex"
    assert data["event_type"] == "failed"
    assert data["error"]["code"] == "validation_failed"
    assert json.loads(event.to_json()) == data


def test_plugin_capability_creation_and_serialization():
    capability = PluginCapability(
        capability_id="office.generate_proposal",
        plugin_id="phoenix-office",
        name="Generate proposal",
        version="0.1.0",
        description="Generate a proposal document.",
        category="office",
        operation_type=OperationType.MUTATE,
        risk_level=RiskLevel.MEDIUM,
        input_schema_ref="schema://proposal-input",
        output_schema_ref="schema://proposal-output",
        required_permissions=[PermissionMode.READ, PermissionMode.WRITE],
        required_secrets=[],
        supports_dry_run=False,
        requires_approval=False,
        verification_methods=["artifact_inspection"],
        failure_modes=[
            PluginFailureMode(
                code="template_missing",
                retryable=False,
                description="Template file is unavailable.",
            )
        ],
    )

    data = capability.to_dict()
    assert data["operation_type"] == "mutate"
    assert data["required_permissions"] == ["read", "write"]
    assert data["failure_modes"][0]["code"] == "template_missing"
    assert json.loads(capability.to_json()) == data


def test_approval_request_and_record_creation_and_serialization():
    request = ApprovalRequest(
        approval_request_id="approval-request-1",
        task_id="task-1",
        requested_by_worker_id="codex-1",
        capability_id="docker.restart_service",
        action="Restart service",
        target_resources=["docker://unifi-controller"],
        reason="Apply approved configuration.",
        risk_level=RiskLevel.HIGH,
        expected_result="Service restarts cleanly.",
        preview=ApprovalPreview(summary="Restart one Docker service."),
        rollback_plan="Restore previous compose file and restart.",
        requested_approvers=["matth"],
        status=ApprovalStatus.PENDING,
        created_at=FIXED_TIME,
    )
    record = ApprovalRecord(
        approval_record_id="approval-record-1",
        approval_request_id=request.approval_request_id,
        task_id=request.task_id,
        decision=ApprovalDecision.APPROVED,
        decided_by_type="human",
        decided_by_id="matth",
        decision_reason="Approved maintenance window.",
        approved_scope=ApprovedScope(
            actions=["Restart service"],
            resources=["docker://unifi-controller"],
            single_use=True,
        ),
        conditions=["Verify service health after restart."],
        created_at=FIXED_TIME,
    )

    request_data = request.to_dict()
    record_data = record.to_dict()
    assert request_data["preview"]["summary"] == "Restart one Docker service."
    assert request_data["status"] == "pending"
    assert record_data["decision"] == "approved"
    assert record_data["approved_scope"]["single_use"] is True
    assert json.loads(request.to_json()) == request_data
    assert json.loads(record.to_json()) == record_data


def test_verification_evidence_creation_and_serialization():
    evidence = VerificationEvidence(
        evidence_id="evidence-1",
        task_id="task-1",
        worker_id="codex-1",
        capability_id="github.open_pr",
        evidence_type=EvidenceType.TEST_OUTPUT,
        summary="All tests passed.",
        result=EvidenceResult.PASSED,
        command="python -m pytest",
        artifact_refs=["artifact://pytest-output"],
        observed_state={"tests": 42},
        verified_by_type=VerifierType.WORKER,
        verified_by_id="codex-1",
        created_at=FIXED_TIME,
    )

    data = evidence.to_dict()
    assert data["evidence_type"] == "test_output"
    assert data["result"] == "passed"
    assert data["verified_by_type"] == "worker"
    assert data["observed_state"] == {"tests": 42}
    assert json.loads(evidence.to_json()) == data

CODEX_HANDOFF_EXAMPLE = Path("examples/tasks/codex_handoff_package.json")


def _codex_handoff_task() -> TaskEnvelope:
    return TaskEnvelope(
        task_id="task-issue-259-codex-handoff-package",
        title="Add machine-readable Codex handoff package",
        objective="Define and test a deterministic Codex handoff package contract.",
        requester=Requester(type=RequesterType.HUMAN, id="human:operator"),
        source=TaskSource(
            kind=SourceKind.GITHUB_ISSUE,
            uri="https://github.com/Phoenix-AI-Platform/phoenix-office/issues/259",
        ),
        constraints=[
            "Do not add CLI behavior.",
            "Do not invoke Codex or GitHub workflows.",
        ],
        acceptance_criteria=[
            "CodexHandoffPackage serializes deterministically.",
            "The example JSON parses with stable safety defaults.",
        ],
        context_refs=[
            "AGENTS.md",
            "src/phoenix_office/core/contracts.py",
            "docs/process/issue-to-codex-handoff.md",
        ],
        allowed_resources={
            "paths": [
                "src/phoenix_office/core/contracts.py",
                "src/phoenix_office/core/__init__.py",
                "tests/test_core_contracts.py",
                "examples/tasks/codex_handoff_package.json",
                "docs/process/issue-to-codex-handoff.md",
            ],
            "repositories": ["Phoenix-AI-Platform/phoenix-office"],
        },
        permissions=TaskPermissions(
            read=True,
            write=True,
            execute=False,
            network=False,
            destructive=False,
        ),
        approval_policy=ApprovalPolicy(required_before=[], approvers=[]),
        verification_plan=VerificationPlan(
            commands=[
                "python -m pytest --basetemp .pytest_tmp",
                "python -m ruff check . --no-cache",
                "git diff --check",
            ],
            evidence_required=[EvidenceType.TEST_OUTPUT],
        ),
        created_at=FIXED_TIME,
        updated_at=FIXED_TIME,
    )


def test_codex_handoff_package_creation_and_serialization():
    from phoenix_office.core import CodexHandoffPackage as ExportedCodexHandoffPackage

    assert ExportedCodexHandoffPackage is CodexHandoffPackage

    task = _codex_handoff_task()
    package = CodexHandoffPackage(
        schema_version="codex-handoff-package.v1",
        handoff_id="codex-handoff-issue-259",
        task=task,
        repository="Phoenix-AI-Platform/phoenix-office",
        base_branch="main",
        expected_pr_title="feat: add machine-readable Codex handoff package",
        prompt="Implement Issue #259 from the verified Phoenix Office checkout.",
        workspace_path="C:/tmp/phoenix-office",
        required_repo_paths=[
            "AGENTS.md",
            "src/phoenix_office/core/contracts.py",
            "docs/process/issue-to-codex-handoff.md",
        ],
        required_pr_body_headings=[
            "Summary",
            "Scope",
            "Changed files",
            "Out-of-scope confirmation",
            "Validation performed",
            "Risks",
        ],
    )

    data = package.to_dict()

    assert data["schema_version"] == "codex-handoff-package.v1"
    assert data["handoff_id"] == "codex-handoff-issue-259"
    assert data["task"] == task.to_dict()
    assert data["worker_type"] == "codex"
    assert data["invocation_mode"] == "manual"
    assert data["invocation_authorized"] is False
    assert data["review_required"] is True
    assert data["worker_may_merge"] is False
    assert json.loads(package.to_json()) == data


def test_codex_pilot_evidence_package_creation_and_serialization():
    from phoenix_office.core import (
        CodexPilotEvidencePackage as ExportedCodexPilotEvidencePackage,
    )

    assert ExportedCodexPilotEvidencePackage is CodexPilotEvidencePackage

    package = CodexPilotEvidencePackage(
        schema_version="codex-pilot-evidence.v1",
        repository="Phoenix-AI-Platform/phoenix-office",
        pilot_kind="docs-only-supervised",
        handoff_id="pilot-evidence-issue-285",
        controls=[
            CodexPilotEvidenceControl(
                control_id="authentication_runner_access",
                status=CodexPilotEvidenceStatus.VERIFIED,
                evidence_ref="auth-runner-access-001",
                reviewer_role=CodexPilotEvidenceReviewerRole.HUMAN_OPERATOR,
            )
        ],
    )

    data = package.to_dict()

    assert data["schema_version"] == "codex-pilot-evidence.v1"
    assert data["repository"] == "Phoenix-AI-Platform/phoenix-office"
    assert data["pilot_kind"] == "docs-only-supervised"
    assert data["pilot_ready"] is False
    assert data["invocation_authorized"] is False
    assert data["controls"][0]["status"] == "verified"
    assert data["controls"][0]["reviewer_role"] == "human_operator"
    assert json.loads(package.to_json()) == data


def test_codex_pilot_authorization_packet_creation_and_serialization():
    from phoenix_office.core import (
        CodexPilotAuthorizationPacket as ExportedCodexPilotAuthorizationPacket,
    )

    assert ExportedCodexPilotAuthorizationPacket is CodexPilotAuthorizationPacket

    package = CodexPilotAuthorizationPacket(
        schema_version="codex-pilot-authorization.v1",
        authorization_id="pilot-auth-issue-292",
        repository="Phoenix-AI-Platform/phoenix-office",
        pilot_kind="docs-only-supervised",
        decision_state="human_authorized_for_one_run",
        authorizer_role="human_operator",
        base_commit_sha="0" * 40,
        handoff_path="handoff.json",
        evidence_path="evidence.json",
        handoff_id="codex-handoff-issue-259",
        objective="Document the supervised Codex pilot authorization packet.",
        allowed_paths=["docs/process/supervised-codex-pilot-authorization.md"],
        expected_pr_title="docs: update supervised Codex pilot authorization",
        branch_name="codex/supervised-pilot-authorization",
        validation_commands=[
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest --basetemp .pytest_tmp",
            "python -m ruff check . --no-cache",
            "git diff --check",
        ],
        budget_metric="tokens",
        budget_ceiling=50000,
        budget_enforcement_ref="budget-control-reviewed",
        timeout_seconds=1800,
        cancellation_ref="operator-cancel-reviewed",
        authentication_runner_ref="runner-access-reviewed",
        branch_permission_ref="branch-permission-reviewed",
        pr_permission_ref="pr-permission-reviewed",
        duplicate_pr_check_ref="duplicate-pr-check-reviewed",
        branch_collision_check_ref="branch-collision-check-reviewed",
        codex_no_approve_merge_ref="no-approve-merge-reviewed",
        final_ci_required=True,
        assistant_review_required=True,
        worker_may_approve=False,
        worker_may_merge=False,
        one_invocation_only=True,
        retry_authorized=False,
        background_execution_authorized=False,
    )

    data = package.to_dict()

    assert data["schema_version"] == "codex-pilot-authorization.v1"
    assert data["authorization_id"] == "pilot-auth-issue-292"
    assert data["repository"] == "Phoenix-AI-Platform/phoenix-office"
    assert data["pilot_kind"] == "docs-only-supervised"
    assert data["decision_state"] == "human_authorized_for_one_run"
    assert data["authorizer_role"] == "human_operator"
    assert data["worker_may_approve"] is False
    assert data["worker_may_merge"] is False
    assert data["retry_authorized"] is False
    assert data["background_execution_authorized"] is False
    assert json.loads(package.to_json()) == data


def _valid_codex_authorization_dict() -> dict[str, object]:
    return {
        "schema_version": "codex-pilot-authorization.v1",
        "authorization_id": "pilot-auth-issue-292",
        "repository": "Phoenix-AI-Platform/phoenix-office",
        "pilot_kind": "docs-only-supervised",
        "decision_state": "human_authorized_for_one_run",
        "authorizer_role": "human_operator",
        "base_commit_sha": "0" * 40,
        "handoff_path": "handoff.json",
        "evidence_path": "evidence.json",
        "handoff_id": "codex-handoff-issue-259",
        "objective": "Document the supervised Codex pilot authorization packet.",
        "allowed_paths": [
            "docs/process/alpha.md",
            "docs/process/zeta.md",
        ],
        "expected_pr_title": "docs: update supervised Codex pilot authorization",
        "branch_name": "codex/supervised-pilot-authorization",
        "validation_commands": CODEX_PILOT_REQUIRED_VALIDATION_COMMANDS,
        "budget_metric": "tokens",
        "budget_ceiling": 50000,
        "budget_enforcement_ref": "budget-control-reviewed",
        "timeout_seconds": 1800,
        "cancellation_ref": "operator-cancel-reviewed",
        "authentication_runner_ref": "runner-access-reviewed",
        "branch_permission_ref": "branch-permission-reviewed",
        "pr_permission_ref": "pr-permission-reviewed",
        "duplicate_pr_check_ref": "duplicate-pr-check-reviewed",
        "branch_collision_check_ref": "branch-collision-check-reviewed",
        "codex_no_approve_merge_ref": "no-approve-merge-reviewed",
        "final_ci_required": True,
        "assistant_review_required": True,
        "worker_may_approve": False,
        "worker_may_merge": False,
        "one_invocation_only": True,
        "retry_authorized": False,
        "background_execution_authorized": False,
    }


def _valid_codex_claim_record(
    authorization: dict[str, object] | None = None,
) -> dict[str, object]:
    authorization = authorization or _valid_codex_authorization_dict()
    return {
        "schema_version": "codex-pilot-claim.v1",
        "attempt_id": "pilot-attempt-abc123def456",
        "authorization_id": authorization["authorization_id"],
        "authorization_fingerprint_schema_version": (
            "phoenix-codex-authorization-fingerprint.v1"
        ),
        "authorization_fingerprint": codex_pilot_authorization_fingerprint(
            authorization
        ),
        "handoff_id": authorization["handoff_id"],
        "repository": authorization["repository"],
        "pilot_kind": authorization["pilot_kind"],
        "base_commit_sha": authorization["base_commit_sha"],
        "branch_name": authorization["branch_name"],
        "expected_pr_title": authorization["expected_pr_title"],
        "objective_digest_schema_version": "codex-pilot-objective-digest.v1",
        "objective_digest": codex_pilot_objective_digest(
            authorization["objective"]
        ),
        "allowed_paths": list(authorization["allowed_paths"]),
        "validation_commands": list(authorization["validation_commands"]),
        "budget_metric": authorization["budget_metric"],
        "budget_ceiling": authorization["budget_ceiling"],
        "timeout_seconds": authorization["timeout_seconds"],
        "budget_enforcement_ref": authorization["budget_enforcement_ref"],
        "cancellation_ref": authorization["cancellation_ref"],
        "authentication_runner_ref": authorization["authentication_runner_ref"],
        "branch_permission_ref": authorization["branch_permission_ref"],
        "pr_permission_ref": authorization["pr_permission_ref"],
        "duplicate_pr_check_ref": authorization["duplicate_pr_check_ref"],
        "branch_collision_check_ref": authorization["branch_collision_check_ref"],
        "codex_no_approve_merge_ref": authorization["codex_no_approve_merge_ref"],
        "final_ci_required": True,
        "assistant_review_required": True,
        "worker_may_approve": False,
        "worker_may_merge": False,
        "one_invocation_only": True,
        "retry_authorized": False,
        "background_execution_authorized": False,
        "initial_lifecycle_state": "claim_created",
    }


def _valid_codex_audit_event(
    claim: dict[str, object] | None = None,
    *,
    previous_lifecycle_state: str = "claim_not_started",
    next_lifecycle_state: str = "claim_created",
    event_sequence: int = 0,
    previous_event_digest: str | None = None,
    **optional_fields: object,
) -> dict[str, object]:
    claim = claim or _valid_codex_claim_record()
    transition = CODEX_PILOT_AUDIT_EVENT_TRANSITIONS[
        (previous_lifecycle_state, next_lifecycle_state)
    ]
    event: dict[str, object] = {
        "schema_version": "codex-pilot-audit-event.v1",
        "attempt_id": claim["attempt_id"],
        "authorization_id": claim["authorization_id"],
        "authorization_fingerprint": claim["authorization_fingerprint"],
        "event_sequence": event_sequence,
        "previous_lifecycle_state": previous_lifecycle_state,
        "next_lifecycle_state": next_lifecycle_state,
        "event_category": transition["event_category"],
        "result_category": transition["result_category"],
        "actor_role": transition["actor_role"],
        "codex_approved": False,
        "codex_merged": False,
        "previous_event_digest": previous_event_digest,
        "event_digest": "0" * 64,
    }
    event.update(optional_fields)
    event["event_digest"] = codex_pilot_audit_event_digest(
        {key: value for key, value in event.items() if key != "event_digest"}
    )
    return event


def _valid_codex_audit_event_chain() -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    claim = _valid_codex_claim_record()
    event_zero = _valid_codex_audit_event(claim)
    event_one = _valid_codex_audit_event(
        claim,
        previous_lifecycle_state="claim_created",
        next_lifecycle_state="invocation_starting",
        event_sequence=1,
        previous_event_digest=event_zero["event_digest"],
    )
    return claim, event_zero, event_one


def test_codex_pilot_claim_record_validation_and_binding_are_deterministic():
    authorization = _valid_codex_authorization_dict()
    claim = _valid_codex_claim_record(authorization)

    first = validate_codex_pilot_claim_binding(claim, authorization)
    second = validate_codex_pilot_claim_binding(dict(claim), dict(authorization))

    assert first == second
    assert first["claim_structural_valid"] is True
    assert first["claim_structural_errors"] == []
    assert first["claim_binding_passed"] is True
    assert first["claim_binding_blockers"] == []


def test_codex_pilot_claim_validation_accepts_sorted_authorized_paths():
    authorization = _valid_codex_authorization_dict()
    assert authorization["allowed_paths"] == [
        "docs/process/alpha.md",
        "docs/process/zeta.md",
    ]
    claim = _valid_codex_claim_record(authorization)

    result = validate_codex_pilot_claim_binding(claim, authorization)

    assert result["claim_structural_valid"] is True
    assert result["claim_binding_passed"] is True


def test_codex_pilot_claim_validation_rejects_unsorted_allowed_paths():
    authorization = _valid_codex_authorization_dict()
    claim = _valid_codex_claim_record(authorization)
    claim["allowed_paths"] = [
        "docs/process/zeta.md",
        "docs/process/alpha.md",
    ]

    result = validate_codex_pilot_claim_record(claim)

    assert result["claim_structural_valid"] is False
    assert "allowed_paths are invalid" in result["claim_structural_errors"]


def test_compose_codex_pilot_initial_claim_bundle_is_deterministic_and_exact():
    authorization = _valid_codex_authorization_dict()
    original = copy.deepcopy(authorization)
    attempt_id = "pilot-attempt-abc123def456"

    first = compose_codex_pilot_initial_claim_bundle(authorization, attempt_id)
    second = compose_codex_pilot_initial_claim_bundle(dict(authorization), attempt_id)
    expected_claim = _valid_codex_claim_record(authorization)
    expected_event = _valid_codex_audit_event(expected_claim)
    expected_snapshot = derive_codex_pilot_attempt_snapshot(
    expected_claim,
    [expected_event],
    )["snapshot"]

    assert first == second
    assert first["claim_bundle_passed"] is True
    assert first["claim_bundle_blockers"] == []
    assert first["claim_record"] == expected_claim
    assert first["claim_record"]["authorization_fingerprint"] == (
    "d4a8b6a9f0b5b289534c5026a2e640ab8e30fba0549a1d9cd37056b60535d1ab"
    )
    assert first["claim_record"]["objective_digest"] == (
    "ecb05382c1182a9afab0b6f9d41b3f5aedbe69ef378e0694396abd2037586feb"
    )
    assert first["claim_record"]["allowed_paths"] == authorization["allowed_paths"]
    assert first["claim_record"]["validation_commands"] == authorization[
    "validation_commands"
    ]
    assert first["claim_record"]["allowed_paths"] is not authorization["allowed_paths"]
    assert first["claim_record"]["validation_commands"] is not authorization[
    "validation_commands"
    ]
    assert first["audit_events"] == [expected_event]
    assert first["audit_events"][0]["event_digest"] == (
    "6249aadd0ac77258b4f295910ce9e8b1f552742c4bb6e36ee0f3cce1193ba8e3"
    )
    assert first["snapshot"] == expected_snapshot
    assert authorization == original


def test_compose_codex_pilot_initial_claim_bundle_rejects_invalid_authorization():
    authorization = _valid_codex_authorization_dict()
    authorization["allowed_paths"] = [
    "docs/process/zeta.md",
    "docs/process/alpha.md",
    ]
    attempt_id = "pilot-attempt-abc123def456"

    result = compose_codex_pilot_initial_claim_bundle(authorization, attempt_id)
    output = json.dumps(result, sort_keys=True)

    assert result["claim_bundle_passed"] is False
    assert result["claim_bundle_blockers"] == ["authorization package is invalid"]
    assert result["claim_record"] is None
    assert result["audit_events"] is None
    assert result["snapshot"] is None
    assert "zeta.md" not in output


def test_compose_codex_pilot_initial_claim_bundle_rejects_invalid_attempt_id():
    authorization = _valid_codex_authorization_dict()
    attempt_id = "pilot-attempt-token-value"

    result = compose_codex_pilot_initial_claim_bundle(authorization, attempt_id)
    output = json.dumps(result, sort_keys=True)

    assert result["claim_bundle_passed"] is False
    assert result["claim_bundle_blockers"] == ["attempt_id is invalid"]
    assert result["claim_record"] is None
    assert result["audit_events"] is None
    assert result["snapshot"] is None
    assert "token-value" not in output


def test_compose_codex_pilot_initial_claim_bundle_does_not_touch_external_dependencies(
    monkeypatch,
):
    authorization = _valid_codex_authorization_dict()
    original = copy.deepcopy(authorization)

    class _Sentinel:
        def __getattr__(self, name):
            raise AssertionError(name)

    import phoenix_office.core.contracts as contracts

    monkeypatch.setattr(contracts, "datetime", _Sentinel(), raising=False)
    monkeypatch.setattr(contracts, "Path", _Sentinel(), raising=False)
    monkeypatch.setattr(contracts, "random", _Sentinel(), raising=False)
    monkeypatch.setattr(contracts, "subprocess", _Sentinel(), raising=False)
    monkeypatch.setattr(contracts, "socket", _Sentinel(), raising=False)

    first = compose_codex_pilot_initial_claim_bundle(
    authorization,
    "pilot-attempt-abc123def456",
    )
    second = compose_codex_pilot_initial_claim_bundle(
    authorization,
    "pilot-attempt-abc123def456",
    )

    assert first == second
    assert authorization == original


def test_codex_pilot_objective_digest_known_vector():
    assert codex_pilot_objective_digest(
    "Document the supervised Codex pilot authorization packet."
    ) == "ecb05382c1182a9afab0b6f9d41b3f5aedbe69ef378e0694396abd2037586feb"


def test_codex_pilot_authorization_fingerprint_uses_shared_field_order():
    authorization = _valid_codex_authorization_dict()
    fingerprint = codex_pilot_authorization_fingerprint(authorization)
    assert len(fingerprint) == 64
    assert CODEX_PILOT_AUTHORIZATION_FINGERPRINT_FIELDS[0] == "schema_version"


def test_codex_pilot_claim_validation_rejects_missing_unknown_and_wrong_type():
    claim = _valid_codex_claim_record()
    claim.pop("attempt_id")
    claim["unknown"] = "safe"
    claim["budget_ceiling"] = True

    result = validate_codex_pilot_claim_record(claim)

    assert result["claim_structural_valid"] is False
    assert "claim record is missing required fields" in result["claim_structural_errors"]
    assert "claim record contains unknown fields" in result["claim_structural_errors"]
    assert "budget_ceiling is invalid" in result["claim_structural_errors"]


def test_codex_pilot_claim_validation_rejects_unsafe_values_without_leaking_them():
    claim = _valid_codex_claim_record()
    claim["attempt_id"] = "pilot-attempt-token-value"
    claim["branch_name"] = "codex/C:/Users/private-name"
    claim["allowed_paths"] = ["docs/process/../secret.md"]

    result = validate_codex_pilot_claim_record(claim)
    output = json.dumps(result, sort_keys=True)

    assert result["claim_structural_valid"] is False
    assert "attempt_id is invalid" in result["claim_structural_errors"]
    assert "branch_name is invalid" in result["claim_structural_errors"]
    assert "allowed_paths are invalid" in result["claim_structural_errors"]
    assert "token-value" not in output
    assert "C:/Users/private-name" not in output
    assert "../secret" not in output


CODEX_CLAIM_PROJECTION_FIELDS_FOR_TEST = [
    "authorization_id",
    "handoff_id",
    "base_commit_sha",
    "branch_name",
    "expected_pr_title",
    "allowed_paths",
    "budget_ceiling",
    "timeout_seconds",
    "budget_enforcement_ref",
    "cancellation_ref",
    "authentication_runner_ref",
    "branch_permission_ref",
    "pr_permission_ref",
    "duplicate_pr_check_ref",
    "branch_collision_check_ref",
    "codex_no_approve_merge_ref",
]


def _mutated_projection_value(value: object) -> object:
    if isinstance(value, bool):
        return not value
    if type(value) is int:
        return value + 1
    if isinstance(value, list):
        return list(reversed(value))
    if isinstance(value, str):
        return f"{value}-changed"
    raise AssertionError(f"Unhandled value: {value!r}")


def test_codex_pilot_claim_validation_rejects_duplicate_paths_and_command_reordering():
    claim = _valid_codex_claim_record()
    duplicate_paths = dict(claim)
    duplicate_paths["allowed_paths"] = ["docs/process/a.md", "docs/process/a.md"]
    reordered_commands = dict(claim)
    reordered_commands["validation_commands"] = list(
        reversed(CODEX_PILOT_REQUIRED_VALIDATION_COMMANDS)
    )

    duplicate_result = validate_codex_pilot_claim_record(duplicate_paths)
    reordered_result = validate_codex_pilot_claim_record(reordered_commands)

    assert duplicate_result["claim_structural_valid"] is False
    assert "allowed_paths are invalid" in duplicate_result["claim_structural_errors"]
    assert reordered_result["claim_structural_valid"] is False
    assert (
        "validation_commands are invalid"
        in reordered_result["claim_structural_errors"]
    )


def test_codex_pilot_claim_validation_rejects_forbidden_path_segment_families():
    forbidden_paths = [
        "docs/process/API/change.md",
        "docs/process/customer/change.md",
        "docs/process/DOCX/change.md",
        "docs/process/example/change.md",
        "docs/process/fixture/change.md",
        "docs/process/MCP/change.md",
        "docs/process/orchestration/change.md",
        "docs/process/proposal/change.md",
        "docs/process/server/change.md",
        "docs/process/source/change.md",
        "docs/process/template/change.md",
        "docs/process/test/change.md",
        "docs/process/workflow/change.md",
        "docs/process/worker/change.md",
    ]
    for path in forbidden_paths:
        claim = _valid_codex_claim_record()
        claim["allowed_paths"] = [path]

        result = validate_codex_pilot_claim_record(claim)

        assert result["claim_structural_valid"] is False
        assert "allowed_paths are invalid" in result["claim_structural_errors"]


def test_codex_pilot_claim_binding_detects_every_projection_mismatch():
    authorization = _valid_codex_authorization_dict()
    for field_name in CODEX_CLAIM_PROJECTION_FIELDS_FOR_TEST:
        claim = _valid_codex_claim_record(authorization)
        if field_name == "base_commit_sha":
            claim[field_name] = "1" * 40
        elif field_name == "allowed_paths":
            claim[field_name] = ["docs/process/omega.md"]
        else:
            claim[field_name] = _mutated_projection_value(authorization[field_name])

        result = validate_codex_pilot_claim_binding(claim, authorization)

        assert result["claim_structural_valid"] is True
        assert result["claim_binding_passed"] is False
        assert f"{field_name} mismatch" in result["claim_binding_blockers"]


def test_codex_pilot_claim_binding_detects_constant_and_command_mismatches():
    authorization = _valid_codex_authorization_dict()
    for field_name, value in [
        ("repository", "Phoenix-AI-Platform/other-repo"),
        ("pilot_kind", "other-pilot"),
        ("validation_commands", list(reversed(CODEX_PILOT_REQUIRED_VALIDATION_COMMANDS))),
        ("budget_metric", "minutes"),
        ("final_ci_required", False),
        ("assistant_review_required", False),
        ("worker_may_approve", True),
        ("worker_may_merge", True),
        ("one_invocation_only", False),
        ("retry_authorized", True),
        ("background_execution_authorized", True),
    ]:
        invalid_authorization = dict(authorization)
        invalid_authorization[field_name] = value
        claim = _valid_codex_claim_record(authorization)

        result = validate_codex_pilot_claim_binding(claim, invalid_authorization)

        assert result["claim_structural_valid"] is True
        assert result["authorization_structural_valid"] is False
        assert result["claim_binding_passed"] is False
        assert result["claim_binding_blockers"] == [
            "authorization package structurally invalid"
        ]


def test_codex_pilot_claim_binding_requires_structurally_valid_authorization():
    authorization = _valid_codex_authorization_dict()
    claim = _valid_codex_claim_record(authorization)
    invalid_authorization_cases = [
        ("decision_state", "pending"),
        ("authorizer_role", "assistant"),
        ("handoff_path", "docs/process/handoff.md"),
        ("evidence_path", "C:/Users/private-name/evidence.json"),
        ("objective", "Ship production runtime behavior"),
        ("expected_pr_title", "feat: add runtime behavior"),
        ("branch_name", "main"),
        ("budget_enforcement_ref", "token-value"),
        ("cancellation_ref", "password=secret"),
        ("authentication_runner_ref", "https://example.com/secret"),
        ("branch_permission_ref", "/home/private-name"),
        ("pr_permission_ref", "AppData"),
        ("duplicate_pr_check_ref", "."),
        ("branch_collision_check_ref", ".."),
        ("codex_no_approve_merge_ref", "sk-proj-super-secret"),
    ]
    for field_name, value in invalid_authorization_cases:
        invalid_authorization = dict(authorization)
        invalid_authorization[field_name] = value

        result = validate_codex_pilot_claim_binding(claim, invalid_authorization)
        output = json.dumps(result, sort_keys=True)

        assert result["claim_structural_valid"] is True
        assert result["authorization_structural_valid"] is False
        assert result["claim_binding_passed"] is False
        assert result["claim_binding_blockers"] == [
            "authorization package structurally invalid"
        ]
        assert str(value) not in output


def test_codex_pilot_authorization_validation_is_shared_and_sanitized():
    authorization = _valid_codex_authorization_dict()
    authorization["allowed_paths"] = [
        "docs/process/zeta.md",
        "docs/process/alpha.md",
    ]

    result = validate_codex_pilot_authorization_packet(authorization)

    assert result["authorization_structural_valid"] is False
    assert "authorization allowed paths are invalid" in (
        result["authorization_structural_errors"]
    )


def test_codex_pilot_authorization_identifier_rejects_evidence_marker_parity():
    unsafe_values = [
        "https://example.com",
        "slash/value",
        "slash\\value",
        "drive:path",
        "name=value",
        "sk-proj-secret",
        "token-value",
        "secret-value",
        "password-value",
        "users-value",
        "home-control-reviewed",
        "myHomeControl",
        "AppData-control",
    ]
    reference_fields = [
        "authorization_id",
        "handoff_id",
        "budget_enforcement_ref",
        "cancellation_ref",
        "authentication_runner_ref",
        "branch_permission_ref",
        "pr_permission_ref",
        "duplicate_pr_check_ref",
        "branch_collision_check_ref",
        "codex_no_approve_merge_ref",
    ]
    for field_name in reference_fields:
        for value in unsafe_values:
            authorization = _valid_codex_authorization_dict()
            authorization[field_name] = value

            result = validate_codex_pilot_authorization_packet(authorization)
            output = json.dumps(result, sort_keys=True)

            assert result["authorization_structural_valid"] is False
            assert f"authorization {field_name} is invalid" in (
                result["authorization_structural_errors"]
            )
            assert value not in output


def test_codex_pilot_authorization_allows_home_text_in_non_identifier_fields():
    authorization = _valid_codex_authorization_dict()
    authorization["objective"] = "Document the home office review process."
    authorization["expected_pr_title"] = "docs: document home office review"
    authorization["allowed_paths"] = ["docs/process/home-office-review.md"]
    authorization["branch_name"] = "codex/home-office-review"
    claim = _valid_codex_claim_record(authorization)

    authorization_result = validate_codex_pilot_authorization_packet(authorization)
    binding_result = validate_codex_pilot_claim_binding(claim, authorization)

    assert authorization_result["authorization_structural_valid"] is True
    assert authorization_result["authorization_structural_errors"] == []
    assert binding_result["claim_structural_valid"] is True
    assert binding_result["authorization_structural_valid"] is True
    assert binding_result["claim_binding_passed"] is True


def test_cli_and_core_authorization_validators_return_identical_results():
    authorization = _valid_codex_authorization_dict()
    authorization["authorization_id"] = "myHomeControl"
    authorization["allowed_paths"] = [
        "docs/process/zeta.md",
        "docs/process/alpha.md",
    ]

    core_result = validate_codex_pilot_authorization_packet(authorization)
    cli_errors = _validate_codex_pilot_authorization_packet(authorization)

    assert cli_errors == core_result["authorization_structural_errors"]
    assert core_result["authorization_structural_valid"] is False
    assert cli_errors == [
        "authorization allowed paths are invalid",
        "authorization authorization_id is invalid",
    ]


def test_codex_pilot_claim_binding_detects_fingerprint_and_objective_mismatches():
    authorization = _valid_codex_authorization_dict()
    claim = _valid_codex_claim_record(authorization)
    claim["authorization_fingerprint"] = "1" * 64
    claim["objective_digest"] = "2" * 64

    result = validate_codex_pilot_claim_binding(claim, authorization)

    assert result["claim_structural_valid"] is True
    assert result["claim_binding_passed"] is False
    assert result["claim_binding_blockers"] == [
        "authorization fingerprint mismatch",
        "objective digest mismatch",
    ]


def test_codex_pilot_claim_binding_is_false_for_structural_failure():
    authorization = _valid_codex_authorization_dict()
    claim = _valid_codex_claim_record(authorization)
    claim["schema_version"] = "wrong"

    result = validate_codex_pilot_claim_binding(claim, authorization)

    assert result["claim_structural_valid"] is False
    assert result["claim_binding_passed"] is False
    assert result["claim_binding_blockers"] == []


def test_codex_pilot_audit_event_record_accepts_all_transition_rows():
    claim = _valid_codex_claim_record()
    required_values = {
        "branch_identity": "codex/supervised-pilot-audit-event",
        "pull_request_identity": "pr-302",
        "usage_category": "within_budget",
        "timeout_category": "timeout_reached",
        "cancellation_category": "operator_cancelled",
        "final_ci_category": "passed",
        "assistant_review_verdict": "approved",
        "recovery_category": "operator_recovery",
    }
    for (previous_state, next_state), transition in (
        CODEX_PILOT_AUDIT_EVENT_TRANSITIONS.items()
    ):
        optional = {
            field_name: required_values[field_name]
            for field_name in transition["required"]
        }
        event = _valid_codex_audit_event(
            claim,
            previous_lifecycle_state=previous_state,
            next_lifecycle_state=next_state,
            event_sequence=0 if previous_state == "claim_not_started" else 1,
            previous_event_digest=(
                None if previous_state == "claim_not_started" else "1" * 64
            ),
            **optional,
        )

        result = validate_codex_pilot_audit_event_record(event)

        assert result["event_structural_valid"] is True
        assert result["event_structural_errors"] == []


def test_codex_pilot_audit_event_digest_known_vectors():
    claim, event_zero, event_one = _valid_codex_audit_event_chain()

    assert claim["attempt_id"] == "pilot-attempt-abc123def456"
    assert codex_pilot_audit_event_digest(
        {key: value for key, value in event_zero.items() if key != "event_digest"}
    ) == event_zero["event_digest"]
    assert codex_pilot_audit_event_digest(
        {key: value for key, value in event_one.items() if key != "event_digest"}
    ) == event_one["event_digest"]
    assert event_zero["event_digest"] == (
        "6249aadd0ac77258b4f295910ce9e8b1f552742c4bb6e36ee0f3cce1193ba8e3"
    )
    assert event_one["event_digest"] == (
        "aa77baa8de60e25eaadc240d6a5985aee72212790f11d8512e1eb40ade187db3"
    )


def test_codex_pilot_audit_event_digest_rejects_non_candidate_payloads():
    _claim, event_zero, _event_one = _valid_codex_audit_event_chain()
    base_payload = {
        key: value for key, value in event_zero.items() if key != "event_digest"
    }
    cases = [
        {"event_digest": "0" * 64},
        {key: value for key, value in base_payload.items() if key != "attempt_id"},
        {**base_payload, "unknown": "safe"},
        {**base_payload, "next_lifecycle_state": "invocation_starting"},
        {**base_payload, "branch_identity": "codex/supervised-pilot"},
        {**base_payload, "attempt_id": "pilot-attempt-tokenvalue"},
        {**base_payload, "event_digest": "0" * 64},
    ]

    for payload in cases:
        try:
            codex_pilot_audit_event_digest(payload)
        except ValueError as exc:
            assert str(exc) == "audit event digest payload is invalid"
        else:
            raise AssertionError("invalid digest payload was accepted")


def test_codex_pilot_audit_event_validation_rejects_shape_and_digest_errors():
    claim, event_zero, _event_one = _valid_codex_audit_event_chain()
    malformed = dict(event_zero)
    malformed.pop("attempt_id")
    malformed["unknown"] = "safe"
    malformed["event_sequence"] = True
    malformed["codex_approved"] = 0
    digest_mismatch = dict(event_zero)
    digest_mismatch["event_digest"] = "1" * 64

    result = validate_codex_pilot_audit_event_record(malformed)
    digest_result = validate_codex_pilot_audit_event_record(digest_mismatch)
    output = json.dumps(result, sort_keys=True)

    assert result["event_structural_valid"] is False
    assert "audit event is missing required fields" in result["event_structural_errors"]
    assert "audit event contains unknown fields" in result["event_structural_errors"]
    assert "event_sequence is invalid" in result["event_structural_errors"]
    assert (
        "codex_approved must be JSON boolean false"
        in result["event_structural_errors"]
    )
    assert "event_digest_mismatch" in digest_result["event_structural_errors"]
    assert claim["authorization_fingerprint"] not in output


def test_codex_pilot_audit_event_validation_rejects_optional_field_matrix():
    claim = _valid_codex_claim_record()
    missing_required = _valid_codex_audit_event(
        claim,
        previous_lifecycle_state="invocation_started",
        next_lifecycle_state="pr_opened_and_stopped",
        event_sequence=1,
        previous_event_digest="1" * 64,
        branch_identity="codex/supervised-pilot-audit-event",
        pull_request_identity="pr-302",
        usage_category="within_budget",
    )
    missing_required.pop("usage_category")
    missing_required["event_digest"] = "0" * 64
    forbidden_present = _valid_codex_audit_event(claim)
    forbidden_present["branch_identity"] = "codex/supervised-pilot-audit-event"
    forbidden_present["event_digest"] = "0" * 64

    missing_result = validate_codex_pilot_audit_event_record(missing_required)
    forbidden_result = validate_codex_pilot_audit_event_record(forbidden_present)

    assert missing_result["event_structural_valid"] is False
    assert "audit event is missing required optional fields" in (
        missing_result["event_structural_errors"]
    )
    assert forbidden_result["event_structural_valid"] is False
    assert "audit event contains forbidden optional fields" in (
        forbidden_result["event_structural_errors"]
    )


def test_codex_pilot_audit_event_validation_anchors_sequence_zero():
    claim = _valid_codex_claim_record()
    wrong_zero = _valid_codex_audit_event(claim)
    wrong_zero["previous_lifecycle_state"] = "claim_created"
    wrong_zero["next_lifecycle_state"] = "invocation_starting"
    wrong_zero["event_category"] = "invocation_starting"
    wrong_zero["result_category"] = "started"
    wrong_zero["actor_role"] = "codex_worker"
    wrong_zero["event_digest"] = "0" * 64
    wrong_root_sequence = _valid_codex_audit_event(claim)
    wrong_root_sequence["event_sequence"] = 1
    wrong_root_sequence["previous_event_digest"] = "1" * 64
    wrong_root_sequence["event_digest"] = "0" * 64

    wrong_zero_result = validate_codex_pilot_audit_event_record(wrong_zero)
    wrong_root_sequence_result = validate_codex_pilot_audit_event_record(
        wrong_root_sequence
    )

    assert wrong_zero_result["event_structural_valid"] is False
    assert "sequence zero transition is invalid" in (
        wrong_zero_result["event_structural_errors"]
    )
    assert wrong_root_sequence_result["event_structural_valid"] is False
    assert "claim-created transition sequence is invalid" in (
        wrong_root_sequence_result["event_structural_errors"]
    )
    assert "nonzero transition previous state is invalid" in (
        wrong_root_sequence_result["event_structural_errors"]
    )


def test_codex_pilot_audit_event_validation_rejects_invalid_optional_values():
    claim = _valid_codex_claim_record()
    event = _valid_codex_audit_event(
        claim,
        previous_lifecycle_state="invocation_started",
        next_lifecycle_state="pr_opened_and_stopped",
        event_sequence=1,
        previous_event_digest="1" * 64,
        branch_identity="codex/supervised-pilot-audit-event",
        pull_request_identity="pr-302",
        usage_category="within_budget",
    )
    event["branch_identity"] = "codex/.hidden"
    event["pull_request_identity"] = "pr-0"
    event["usage_category"] = "token-value"
    event["event_digest"] = "0" * 64

    result = validate_codex_pilot_audit_event_record(event)
    output = json.dumps(result, sort_keys=True)

    assert result["event_structural_valid"] is False
    assert "branch_identity is invalid" in result["event_structural_errors"]
    assert "pull_request_identity is invalid" in result["event_structural_errors"]
    assert "usage_category is invalid" in result["event_structural_errors"]
    assert "token-value" not in output


def test_codex_pilot_audit_event_binding_accepts_zero_and_linked_event():
    claim, event_zero, event_one = _valid_codex_audit_event_chain()

    zero_result = validate_codex_pilot_audit_event_binding(event_zero, claim, None)
    one_result = validate_codex_pilot_audit_event_binding(event_one, claim, event_zero)

    assert zero_result["event_structural_valid"] is True
    assert zero_result["event_binding_passed"] is True
    assert zero_result["event_binding_blockers"] == []
    assert one_result["event_structural_valid"] is True
    assert one_result["previous_event_structural_valid"] is True
    assert one_result["event_binding_passed"] is True
    assert one_result["event_binding_blockers"] == []


def test_codex_pilot_audit_event_binding_rejects_identity_and_sequence_errors():
    claim, event_zero, event_one = _valid_codex_audit_event_chain()
    event_one["attempt_id"] = "pilot-attempt-other1234"
    event_one["event_sequence"] = 3
    event_one["previous_event_digest"] = "2" * 64
    event_one["event_digest"] = codex_pilot_audit_event_digest(
        {key: value for key, value in event_one.items() if key != "event_digest"}
    )

    result = validate_codex_pilot_audit_event_binding(event_one, claim, event_zero)

    assert result["event_structural_valid"] is True
    assert result["event_binding_passed"] is False
    assert "attempt_id mismatch" in result["event_binding_blockers"]
    assert "event sequence is not contiguous" in result["event_binding_blockers"]
    assert "previous_event_digest mismatch" in result["event_binding_blockers"]


def test_codex_pilot_audit_event_binding_rejects_cross_claim_previous_event():
    claim, event_zero, event_one = _valid_codex_audit_event_chain()
    other_claim = _valid_codex_claim_record()
    other_claim["attempt_id"] = "pilot-attempt-other1234"
    other_attempt_previous = _valid_codex_audit_event(other_claim)
    other_authorization_previous = dict(event_zero)
    other_authorization_previous["authorization_id"] = "other-auth-reviewed"
    other_authorization_previous["event_digest"] = codex_pilot_audit_event_digest(
        {
            key: value
            for key, value in other_authorization_previous.items()
            if key != "event_digest"
        }
    )
    other_fingerprint_previous = dict(event_zero)
    other_fingerprint_previous["authorization_fingerprint"] = "1" * 64
    other_fingerprint_previous["event_digest"] = codex_pilot_audit_event_digest(
        {
            key: value
            for key, value in other_fingerprint_previous.items()
            if key != "event_digest"
        }
    )

    for previous_event, expected_blocker in [
        (other_attempt_previous, "previous attempt_id mismatch"),
        (other_authorization_previous, "previous authorization_id mismatch"),
        (
            other_fingerprint_previous,
            "previous authorization_fingerprint mismatch",
        ),
    ]:
        current = dict(event_one)
        current["previous_event_digest"] = previous_event["event_digest"]
        current["event_digest"] = codex_pilot_audit_event_digest(
            {key: value for key, value in current.items() if key != "event_digest"}
        )

        result = validate_codex_pilot_audit_event_binding(current, claim, previous_event)

        assert result["event_structural_valid"] is True
        assert result["previous_event_structural_valid"] is True
        assert result["event_binding_passed"] is False
        assert expected_blocker in result["event_binding_blockers"]


def test_codex_pilot_audit_event_binding_rejects_previous_and_terminal_errors():
    claim, event_zero, event_one = _valid_codex_audit_event_chain()
    terminal = _valid_codex_audit_event(
        claim,
        previous_lifecycle_state="claim_created",
        next_lifecycle_state="aborted",
        event_sequence=1,
        previous_event_digest=event_zero["event_digest"],
        recovery_category="operator_recovery",
    )
    later = dict(terminal)
    later["event_sequence"] = 2
    later["previous_lifecycle_state"] = "aborted"
    later["next_lifecycle_state"] = "failed"
    later["previous_event_digest"] = terminal["event_digest"]
    later["event_digest"] = "0" * 64

    missing_previous_result = validate_codex_pilot_audit_event_binding(
        event_one,
        claim,
        None,
    )
    terminal_result = validate_codex_pilot_audit_event_binding(later, claim, terminal)

    assert missing_previous_result["event_binding_passed"] is False
    assert "previous event is required" in (
        missing_previous_result["event_binding_blockers"]
    )
    assert terminal_result["event_binding_passed"] is False
    assert terminal_result["event_structural_valid"] is False
    assert "invalid_lifecycle_transition" in terminal_result["event_structural_errors"]


def test_codex_pilot_audit_event_binding_rejects_pr_identity_mismatch():
    claim = _valid_codex_claim_record()
    opened = _valid_codex_audit_event(
        claim,
        previous_lifecycle_state="invocation_started",
        next_lifecycle_state="pr_opened_and_stopped",
        event_sequence=3,
        previous_event_digest="1" * 64,
        branch_identity="codex/supervised-pilot-audit-event",
        pull_request_identity="pr-302",
        usage_category="within_budget",
    )
    completed = _valid_codex_audit_event(
        claim,
        previous_lifecycle_state="pr_opened_and_stopped",
        next_lifecycle_state="completed_pending_review",
        event_sequence=4,
        previous_event_digest=opened["event_digest"],
        branch_identity="codex/other-branch",
        pull_request_identity="pr-303",
        final_ci_category="passed",
        assistant_review_verdict="approved",
    )

    result = validate_codex_pilot_audit_event_binding(completed, claim, opened)

    assert result["event_structural_valid"] is True
    assert result["event_binding_passed"] is False
    assert "branch_identity mismatch" in result["event_binding_blockers"]
    assert "pull_request_identity mismatch" in result["event_binding_blockers"]


def test_codex_pilot_audit_event_binding_rejects_invalid_claim_and_event():
    claim, event_zero, _event_one = _valid_codex_audit_event_chain()
    claim["schema_version"] = "wrong"
    event_zero["schema_version"] = "wrong"

    result = validate_codex_pilot_audit_event_binding(event_zero, claim, None)

    assert result["event_structural_valid"] is False
    assert result["event_binding_passed"] is False


def _valid_codex_audit_event_full_chain() -> tuple[
    dict[str, object],
    list[dict[str, object]],
]:
    claim, event_zero, event_one = _valid_codex_audit_event_chain()
    event_two = _valid_codex_audit_event(
        claim,
        previous_lifecycle_state="invocation_starting",
        next_lifecycle_state="invocation_started",
        event_sequence=2,
        previous_event_digest=event_one["event_digest"],
    )
    event_three = _valid_codex_audit_event(
        claim,
        previous_lifecycle_state="invocation_started",
        next_lifecycle_state="pr_opened_and_stopped",
        event_sequence=3,
        previous_event_digest=event_two["event_digest"],
        branch_identity="codex/supervised-pilot-audit-event",
        pull_request_identity="pr-302",
        usage_category="within_budget",
    )
    event_four = _valid_codex_audit_event(
        claim,
        previous_lifecycle_state="pr_opened_and_stopped",
        next_lifecycle_state="completed_pending_review",
        event_sequence=4,
        previous_event_digest=event_three["event_digest"],
        branch_identity="codex/supervised-pilot-audit-event",
        pull_request_identity="pr-302",
        final_ci_category="passed",
        assistant_review_verdict="approved",
    )
    return claim, [event_zero, event_one, event_two, event_three, event_four]


def _derived_snapshot_for_events(
    claim: dict[str, object],
    events: list[dict[str, object]],
) -> dict[str, object]:
    snapshot = derive_codex_pilot_attempt_snapshot(claim, events)["snapshot"]
    assert isinstance(snapshot, dict)
    return snapshot


def _valid_terminal_snapshot(
    state: str,
    sequence: int,
    **optional_fields: object,
) -> dict[str, object]:
    claim, event_zero, event_one = _valid_codex_audit_event_chain()
    if sequence == 1:
        previous_state = "claim_created"
        previous_event = event_zero
        events = [event_zero]
    elif sequence == 2:
        previous_state = "invocation_starting"
        previous_event = event_one
        events = [event_zero, event_one]
    elif sequence == 3:
        event_two = _valid_codex_audit_event(
            claim,
            previous_lifecycle_state="invocation_starting",
            next_lifecycle_state="invocation_started",
            event_sequence=2,
            previous_event_digest=event_one["event_digest"],
        )
        previous_state = "invocation_started"
        previous_event = event_two
        events = [event_zero, event_one, event_two]
    else:
        raise AssertionError(f"Unexpected terminal sequence: {sequence}")
    terminal_event = _valid_codex_audit_event(
        claim,
        previous_lifecycle_state=previous_state,
        next_lifecycle_state=state,
        event_sequence=sequence,
        previous_event_digest=previous_event["event_digest"],
        **optional_fields,
    )
    return _derived_snapshot_for_events(claim, [*events, terminal_event])


def test_codex_pilot_attempt_snapshot_derives_newly_claimed_state():
    claim, event_zero, _event_one = _valid_codex_audit_event_chain()

    result = derive_codex_pilot_attempt_snapshot(claim, [event_zero])

    assert result["snapshot_derivation_passed"] is True
    assert result["event_chain_valid"] is True
    assert result["snapshot"] == {
        "schema_version": "codex-pilot-attempt-snapshot.v1",
        "attempt_id": claim["attempt_id"],
        "authorization_id": claim["authorization_id"],
        "authorization_fingerprint": claim["authorization_fingerprint"],
        "latest_event_sequence": 0,
        "latest_event_digest": event_zero["event_digest"],
        "current_lifecycle_state": "claim_created",
        "terminal": False,
        "branch_identity": None,
        "pull_request_identity": None,
        "final_ci_category": None,
        "assistant_review_verdict": None,
        "codex_approved": False,
        "codex_merged": False,
        "authorization_reusable": False,
    }


def test_codex_pilot_attempt_snapshot_derives_branch_review_and_terminal_state():
    claim, events = _valid_codex_audit_event_full_chain()

    result = derive_codex_pilot_attempt_snapshot(claim, events)

    assert result["snapshot_derivation_passed"] is True
    assert result["snapshot"]["latest_event_sequence"] == 4
    assert result["snapshot"]["latest_event_digest"] == events[-1]["event_digest"]
    assert result["snapshot"]["current_lifecycle_state"] == "completed_pending_review"
    assert result["snapshot"]["terminal"] is True
    assert result["snapshot"]["branch_identity"] == "codex/supervised-pilot-audit-event"
    assert result["snapshot"]["pull_request_identity"] == "pr-302"
    assert result["snapshot"]["final_ci_category"] == "passed"
    assert result["snapshot"]["assistant_review_verdict"] == "approved"
    assert result["snapshot"]["codex_approved"] is False
    assert result["snapshot"]["codex_merged"] is False
    assert result["snapshot"]["authorization_reusable"] is False


def test_codex_pilot_attempt_snapshot_validation_accepts_every_lifecycle_state():
    claim, events = _valid_codex_audit_event_full_chain()
    snapshots = [
        _derived_snapshot_for_events(claim, events[:1]),
        _derived_snapshot_for_events(claim, events[:2]),
        _derived_snapshot_for_events(claim, events[:3]),
        _derived_snapshot_for_events(claim, events[:4]),
        _derived_snapshot_for_events(claim, events),
        _valid_terminal_snapshot("aborted", 1, recovery_category="operator_recovery"),
        _valid_terminal_snapshot("failed", 2, recovery_category="operator_recovery"),
        _valid_terminal_snapshot(
            "cancelled",
            3,
            usage_category="within_budget",
            cancellation_category="operator_cancelled",
        ),
        _valid_terminal_snapshot(
            "timed_out",
            3,
            usage_category="within_budget",
            timeout_category="timeout_reached",
        ),
    ]

    for snapshot in snapshots:
        result = validate_codex_pilot_attempt_snapshot(snapshot)

        assert result["snapshot_structural_valid"] is True
        assert result["snapshot_structural_errors"] == []


def test_codex_pilot_attempt_snapshot_validation_rejects_shape_and_types_safely():
    claim, events = _valid_codex_audit_event_full_chain()
    snapshot = derive_codex_pilot_attempt_snapshot(claim, events)["snapshot"]
    invalid = dict(snapshot)
    invalid.pop("attempt_id")
    invalid["unknown"] = "C:/Users/private-name"
    invalid["schema_version"] = "wrong"
    invalid["latest_event_sequence"] = True
    invalid["terminal"] = 0
    invalid["branch_identity"] = "codex/.hidden"
    invalid["pull_request_identity"] = "pr-0"
    invalid["final_ci_category"] = "token-value"
    invalid["assistant_review_verdict"] = "password=secret"
    invalid["codex_approved"] = True
    invalid["codex_merged"] = 0
    invalid["authorization_reusable"] = None

    result = validate_codex_pilot_attempt_snapshot(invalid)
    output = json.dumps(result, sort_keys=True)

    assert result["snapshot_structural_valid"] is False
    assert "snapshot is missing required fields" in result["snapshot_structural_errors"]
    assert "snapshot contains unknown fields" in result["snapshot_structural_errors"]
    assert "snapshot schema_version is invalid" in result["snapshot_structural_errors"]
    assert "snapshot latest_event_sequence is invalid" in (
        result["snapshot_structural_errors"]
    )
    assert "snapshot terminal must be a JSON boolean" in (
        result["snapshot_structural_errors"]
    )
    assert "snapshot branch_identity is invalid" in result["snapshot_structural_errors"]
    assert "snapshot pull_request_identity is invalid" in (
        result["snapshot_structural_errors"]
    )
    assert "snapshot final_ci_category is invalid" in (
        result["snapshot_structural_errors"]
    )
    assert "snapshot assistant_review_verdict is invalid" in (
        result["snapshot_structural_errors"]
    )
    assert "snapshot codex_approved must be JSON boolean false" in (
        result["snapshot_structural_errors"]
    )
    assert "snapshot codex_merged must be JSON boolean false" in (
        result["snapshot_structural_errors"]
    )
    assert "snapshot authorization_reusable must be JSON boolean false" in (
        result["snapshot_structural_errors"]
    )
    assert "C:/Users/private-name" not in output
    assert "token-value" not in output
    assert "password=secret" not in output


def test_codex_pilot_attempt_snapshot_validation_rejects_cross_field_invariants():
    claim, events = _valid_codex_audit_event_full_chain()
    base = _derived_snapshot_for_events(claim, events[:1])
    cases = [
        ("claim_created_terminal", {"terminal": True}, "snapshot terminal state is invalid"),
        (
            "claim_not_started",
            {"current_lifecycle_state": "claim_not_started"},
            "snapshot current_lifecycle_state is invalid",
        ),
        (
            "invocation_started_with_context",
            {
                "current_lifecycle_state": "invocation_started",
                "latest_event_sequence": 2,
                "branch_identity": "codex/supervised-pilot-audit-event",
                "pull_request_identity": "pr-302",
            },
            "snapshot context is invalid",
        ),
        (
            "completed_pending_review_missing_context",
            {"current_lifecycle_state": "completed_pending_review", "latest_event_sequence": 4},
            "snapshot context is invalid",
        ),
        (
            "bad_attempt_id",
            {"attempt_id": "safe-but-not-attempt"},
            "snapshot attempt_id is invalid",
        ),
    ]

    for _name, updates, expected_error in cases:
        snapshot = dict(base)
        snapshot.update(updates)

        result = validate_codex_pilot_attempt_snapshot(snapshot)

        assert result["snapshot_structural_valid"] is False
        assert expected_error in result["snapshot_structural_errors"]


def test_codex_pilot_attempt_snapshot_validation_matches_claim_attempt_id_safety():
    claim, events = _valid_codex_audit_event_full_chain()
    snapshot = _derived_snapshot_for_events(claim, events[:1])
    unsafe_attempt_ids = [
        "pilot-attempt-token-value",
        "pilot-attempt-secret-value",
        "pilot-attempt-password-value",
        "pilot-attempt-users-value",
        "pilot-attempt-AppData-value",
        "pilot-attempt-C:/Users/private-name",
    ]

    for attempt_id in unsafe_attempt_ids:
        invalid_claim = _valid_codex_claim_record()
        invalid_claim["attempt_id"] = attempt_id
        invalid_snapshot = dict(snapshot)
        invalid_snapshot["attempt_id"] = attempt_id

        claim_result = validate_codex_pilot_claim_record(invalid_claim)
        snapshot_result = validate_codex_pilot_attempt_snapshot(invalid_snapshot)
        snapshot_output = json.dumps(snapshot_result, sort_keys=True)

        assert claim_result["claim_structural_valid"] is False
        assert "attempt_id is invalid" in claim_result["claim_structural_errors"]
        assert snapshot_result["snapshot_structural_valid"] is False
        assert "snapshot attempt_id is invalid" in (
            snapshot_result["snapshot_structural_errors"]
        )
        assert attempt_id not in snapshot_output


def test_codex_pilot_attempt_snapshot_validation_rejects_context_partial_pairs():
    claim, events = _valid_codex_audit_event_full_chain()
    opened = _derived_snapshot_for_events(claim, events[:4])
    completed = _derived_snapshot_for_events(claim, events)
    cases = [
        {**opened, "pull_request_identity": None},
        {**opened, "final_ci_category": "passed"},
        {**opened, "assistant_review_verdict": "approved"},
        {**completed, "branch_identity": None},
        {**completed, "pull_request_identity": None},
        {**completed, "final_ci_category": None},
        {**completed, "assistant_review_verdict": None},
    ]

    for snapshot in cases:
        result = validate_codex_pilot_attempt_snapshot(snapshot)

        assert result["snapshot_structural_valid"] is False
        assert "snapshot context is invalid" in result["snapshot_structural_errors"]


def test_codex_pilot_attempt_snapshot_validation_rejects_impossible_sequences():
    claim, events = _valid_codex_audit_event_full_chain()
    snapshots = [
        _derived_snapshot_for_events(claim, events[:1]),
        _derived_snapshot_for_events(claim, events[:2]),
        _derived_snapshot_for_events(claim, events[:3]),
        _derived_snapshot_for_events(claim, events[:4]),
        _derived_snapshot_for_events(claim, events),
        _valid_terminal_snapshot("aborted", 1, recovery_category="operator_recovery"),
    ]

    for snapshot in snapshots:
        invalid = dict(snapshot)
        invalid["latest_event_sequence"] = 99

        result = validate_codex_pilot_attempt_snapshot(invalid)

        assert result["snapshot_structural_valid"] is False
        assert "snapshot state sequence is invalid" in result["snapshot_structural_errors"]


def test_codex_pilot_attempt_snapshot_binding_accepts_exact_derivation():
    claim, events = _valid_codex_audit_event_full_chain()
    snapshot = derive_codex_pilot_attempt_snapshot(claim, events)["snapshot"]

    result = validate_codex_pilot_attempt_snapshot_binding(snapshot, claim, events)

    assert result["snapshot_structural_valid"] is True
    assert result["claim_structural_valid"] is True
    assert result["event_chain_valid"] is True
    assert result["snapshot_derivation_passed"] is True
    assert result["snapshot_binding_passed"] is True
    assert result["snapshot_binding_blockers"] == []


def test_codex_pilot_attempt_snapshot_binding_rejects_candidate_mismatch():
    claim, events = _valid_codex_audit_event_full_chain()
    snapshot = derive_codex_pilot_attempt_snapshot(claim, events)["snapshot"]
    mismatched_fields = [
        ("attempt_id", "pilot-attempt-other123456789"),
        ("authorization_id", "other-auth-reviewed"),
        ("authorization_fingerprint", "1" * 64),
        ("latest_event_digest", "1" * 64),
        ("branch_identity", "codex/other-branch"),
        ("pull_request_identity", "pr-303"),
        ("final_ci_category", "failed"),
        ("assistant_review_verdict", "changes_requested"),
    ]

    for field_name, value in mismatched_fields:
        candidate = dict(snapshot)
        candidate[field_name] = value

        result = validate_codex_pilot_attempt_snapshot_binding(candidate, claim, events)

        assert result["snapshot_structural_valid"] is True
        assert result["snapshot_derivation_passed"] is True
        assert result["snapshot_binding_passed"] is False
        assert result["snapshot_binding_blockers"] == ["snapshot_mismatch"]


def test_codex_pilot_attempt_snapshot_binding_rejects_sequence_state_terminal_mismatch():
    claim, events = _valid_codex_audit_event_full_chain()
    early_claim, event_zero, event_one = _valid_codex_audit_event_chain()
    candidates = [
        _derived_snapshot_for_events(early_claim, [event_zero, event_one]),
        _derived_snapshot_for_events(claim, events),
        _valid_terminal_snapshot("aborted", 1, recovery_category="operator_recovery"),
    ]
    candidates[2]["current_lifecycle_state"] = "failed"

    event_sets = [events, events[:4], events]
    for candidate, event_set in zip(candidates, event_sets, strict=True):
        result = validate_codex_pilot_attempt_snapshot_binding(
            candidate,
            claim,
            event_set,
        )

        assert result["snapshot_structural_valid"] is True
        assert result["snapshot_derivation_passed"] is True
        assert result["snapshot_binding_passed"] is False
        assert result["snapshot_binding_blockers"] == ["snapshot_mismatch"]


def test_codex_pilot_attempt_snapshot_derivation_rejects_non_list_or_empty_events():
    claim = _valid_codex_claim_record()

    non_list = derive_codex_pilot_attempt_snapshot(claim, {"event": "not-list"})
    empty = derive_codex_pilot_attempt_snapshot(claim, [])

    assert non_list["snapshot_derivation_passed"] is False
    assert non_list["snapshot_derivation_blockers"] == ["event_sequence_invalid"]
    assert empty["snapshot_derivation_passed"] is False
    assert empty["snapshot_derivation_blockers"] == ["event_sequence_invalid"]


def test_codex_pilot_attempt_snapshot_derivation_rejects_reordered_and_skipped_events():
    claim, events = _valid_codex_audit_event_full_chain()
    reordered = [events[1], events[0]]
    skipped = [events[0], events[2]]

    reordered_result = derive_codex_pilot_attempt_snapshot(claim, reordered)
    skipped_result = derive_codex_pilot_attempt_snapshot(claim, skipped)

    assert reordered_result["snapshot_derivation_passed"] is False
    assert "event_binding_mismatch" in reordered_result["snapshot_derivation_blockers"]
    assert "event_sequence_invalid" in reordered_result["snapshot_derivation_blockers"]
    assert skipped_result["snapshot_derivation_passed"] is False
    assert "event_binding_mismatch" in skipped_result["snapshot_derivation_blockers"]
    assert "event_sequence_invalid" in skipped_result["snapshot_derivation_blockers"]


def test_codex_pilot_attempt_snapshot_derivation_rejects_duplicate_or_altered_events():
    claim, events = _valid_codex_audit_event_full_chain()
    duplicate = [events[0], events[1], events[1]]
    altered = list(events)
    altered[2] = dict(altered[2])
    altered[2]["authorization_id"] = "other-auth-reviewed"

    duplicate_result = derive_codex_pilot_attempt_snapshot(claim, duplicate)
    altered_result = derive_codex_pilot_attempt_snapshot(claim, altered)

    assert duplicate_result["snapshot_derivation_passed"] is False
    assert "event_binding_mismatch" in duplicate_result["snapshot_derivation_blockers"]
    assert "event_sequence_invalid" in duplicate_result["snapshot_derivation_blockers"]
    assert altered_result["snapshot_derivation_passed"] is False
    assert "audit_event_corrupt" in altered_result["snapshot_derivation_blockers"]
    assert "event_binding_mismatch" in altered_result["snapshot_derivation_blockers"]


def test_codex_pilot_attempt_snapshot_derivation_rejects_cross_claim_event():
    claim, events = _valid_codex_audit_event_full_chain()
    other_claim = _valid_codex_claim_record()
    other_claim["attempt_id"] = "pilot-attempt-other1234"
    cross_claim_event = _valid_codex_audit_event(
        other_claim,
        previous_lifecycle_state="claim_created",
        next_lifecycle_state="invocation_starting",
        event_sequence=1,
        previous_event_digest=events[0]["event_digest"],
    )
    mixed = [events[0], cross_claim_event]

    result = derive_codex_pilot_attempt_snapshot(claim, mixed)

    assert result["snapshot_derivation_passed"] is False
    assert "event_binding_mismatch" in result["snapshot_derivation_blockers"]


def test_codex_pilot_attempt_snapshot_derivation_rejects_terminal_continuation():
    claim, event_zero, _event_one = _valid_codex_audit_event_chain()
    terminal = _valid_codex_audit_event(
        claim,
        previous_lifecycle_state="claim_created",
        next_lifecycle_state="aborted",
        event_sequence=1,
        previous_event_digest=event_zero["event_digest"],
        recovery_category="operator_recovery",
    )
    continued = dict(terminal)
    continued["event_sequence"] = 2
    continued["previous_lifecycle_state"] = "aborted"
    continued["next_lifecycle_state"] = "failed"
    continued["previous_event_digest"] = terminal["event_digest"]
    continued["event_digest"] = "0" * 64

    result = derive_codex_pilot_attempt_snapshot(claim, [event_zero, terminal, continued])

    assert result["snapshot_derivation_passed"] is False
    assert "audit_event_corrupt" in result["snapshot_derivation_blockers"]
    assert "event_binding_mismatch" in result["snapshot_derivation_blockers"]


def test_codex_pilot_attempt_snapshot_binding_propagates_invalid_claim_and_event():
    claim, event_zero, _event_one = _valid_codex_audit_event_chain()
    snapshot = derive_codex_pilot_attempt_snapshot(claim, [event_zero])["snapshot"]
    claim["schema_version"] = "wrong"
    event_zero["event_digest"] = "1" * 64

    result = validate_codex_pilot_attempt_snapshot_binding(snapshot, claim, [event_zero])

    assert result["snapshot_structural_valid"] is True
    assert result["claim_structural_valid"] is False
    assert result["event_chain_valid"] is False
    assert result["snapshot_binding_passed"] is False
    assert "snapshot_derivation_failed" in result["snapshot_binding_blockers"]
    assert "claim_record_invalid" in result["snapshot_derivation_blockers"]


def _collect_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        strings: list[str] = []
        for key, item in value.items():
            strings.extend(_collect_strings(key))
            strings.extend(_collect_strings(item))
        return strings
    if isinstance(value, list):
        strings = []
        for item in value:
            strings.extend(_collect_strings(item))
        return strings
    return []


def test_codex_handoff_package_example_has_expected_stable_fields():
    data = json.loads(CODEX_HANDOFF_EXAMPLE.read_text(encoding="utf-8"))

    assert data["schema_version"] == "codex-handoff-package.v1"
    assert data["handoff_id"] == "codex-handoff-issue-259"
    assert data["repository"] == "Phoenix-AI-Platform/phoenix-office"
    assert data["base_branch"] == "main"
    assert data["expected_pr_title"] == (
        "feat: add machine-readable Codex handoff package"
    )
    assert data["task"]["task_id"] == "task-issue-259-codex-handoff-package"
    assert data["task"]["source"]["kind"] == "github_issue"
    assert data["worker_type"] == "codex"
    assert data["invocation_mode"] == "manual"
    assert data["invocation_authorized"] is False
    assert data["review_required"] is True
    assert data["worker_may_merge"] is False
    assert "AGENTS.md" in data["required_repo_paths"]
    assert "Summary" in data["required_pr_body_headings"]


def test_codex_handoff_package_example_contains_no_private_data_or_secrets():
    data = json.loads(CODEX_HANDOFF_EXAMPLE.read_text(encoding="utf-8"))
    searchable_text = "\n".join(_collect_strings(data)).lower()

    forbidden_fragments = [
        "sk-proj-",
        "sk-live-",
        "begin private key",
        "password=",
        "rambler",
        "abby hill",
        "schloss",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in searchable_text
