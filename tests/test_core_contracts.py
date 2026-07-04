"""Tests for early Phoenix Core contract skeletons."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from phoenix_office.core.contracts import (
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
    codex_pilot_authorization_fingerprint,
    codex_pilot_objective_digest,
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
