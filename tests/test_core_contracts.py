"""Tests for early Phoenix Core contract skeletons."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from phoenix_office.core.contracts import (
    ApprovalDecision,
    ApprovalPolicy,
    ApprovalPreview,
    ApprovalRecord,
    ApprovalRequest,
    ApprovalStatus,
    ApprovedScope,
    CodexHandoffPackage,
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
