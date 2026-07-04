"""Early Phoenix Core contract skeletons.

These dataclasses mirror the Markdown sketches in
``docs/architecture/contracts.md``. They are intentionally simple,
serializable contract shapes only. They do not implement orchestration,
worker execution, plugin runtime behavior, approval policy, or persistence.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any


class _StringEnum(StrEnum):
    """String enum base so serialized values are stable and readable."""


class TaskStatus(_StringEnum):
    """Lifecycle states for a Phoenix task envelope."""

    REQUESTED = "requested"
    PLANNED = "planned"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskPriority(_StringEnum):
    """Priority values for Phoenix tasks."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class RequesterType(_StringEnum):
    """Sources that can request Phoenix work."""

    HUMAN = "human"
    SYSTEM = "system"
    SCHEDULE = "schedule"
    GITHUB = "github"


class SourceKind(_StringEnum):
    """Task intake surfaces."""

    CHAT = "chat"
    GITHUB_ISSUE = "github_issue"
    AUTOMATION = "automation"
    API = "api"


class WorkerType(_StringEnum):
    """Worker classes Phoenix can coordinate."""

    CODEX = "codex"
    CHATGPT_ARCHITECT = "chatgpt_architect"
    LOCAL_LLM = "local_llm"
    UNITY_AI = "unity_ai"
    BROWSER = "browser"
    INFRASTRUCTURE = "infrastructure"
    FUTURE = "future"


class CodexPilotEvidenceStatus(_StringEnum):
    """Status values for supervised Codex pilot external-control evidence."""

    VERIFIED = "verified"
    BLOCKED = "blocked"
    UNVERIFIED = "unverified"


class CodexPilotEvidenceReviewerRole(_StringEnum):
    """Reviewer roles for supervised Codex pilot external controls."""

    HUMAN_OPERATOR = "human_operator"
    ASSISTANT_REVIEWER = "assistant_reviewer"
    HUMAN_OPERATOR_AND_ASSISTANT_REVIEWER = (
        "human_operator_and_assistant_reviewer"
    )


class WorkerEventType(_StringEnum):
    """Worker lifecycle event types."""

    ACCEPTED = "accepted"
    PROGRESS = "progress"
    APPROVAL_REQUESTED = "approval_requested"
    BLOCKED = "blocked"
    FAILED = "failed"
    COMPLETED = "completed"
    VERIFIED = "verified"


class EventSeverity(_StringEnum):
    """Severity levels for worker and platform events."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class OperationType(_StringEnum):
    """Plugin operation classes."""

    READ = "read"
    SIMULATE = "simulate"
    MUTATE = "mutate"


class RiskLevel(_StringEnum):
    """Risk levels used by capabilities and approval requests."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PermissionMode(_StringEnum):
    """Permission modes that can gate Phoenix work."""

    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    NETWORK = "network"
    DESTRUCTIVE = "destructive"
    EXTERNAL_COMMUNICATION = "external_communication"


class ApprovalStatus(_StringEnum):
    """Approval request states."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ApprovalDecision(_StringEnum):
    """Approval record decisions."""

    APPROVED = "approved"
    DENIED = "denied"


class EvidenceType(_StringEnum):
    """Verification evidence categories."""

    TEST_OUTPUT = "test_output"
    LINT_OUTPUT = "lint_output"
    API_READBACK = "api_readback"
    LOG_EXCERPT = "log_excerpt"
    SCREENSHOT = "screenshot"
    ARTIFACT = "artifact"
    HUMAN_CONFIRMATION = "human_confirmation"


class EvidenceResult(_StringEnum):
    """Verification evidence outcomes."""

    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class VerifierType(_StringEnum):
    """Actors that can verify Phoenix work."""

    WORKER = "worker"
    HUMAN = "human"
    SYSTEM = "system"


class FailureCode(_StringEnum):
    """Structured worker and plugin failure categories."""

    MISSING_CONTEXT = "missing_context"
    PERMISSION_DENIED = "permission_denied"
    TOOL_UNAVAILABLE = "tool_unavailable"
    VALIDATION_FAILED = "validation_failed"
    EXECUTION_FAILED = "execution_failed"
    POLICY_BLOCKED = "policy_blocked"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _serialize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {
            contract_field.name: _serialize(getattr(value, contract_field.name))
            for contract_field in fields(value)
        }
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


@dataclass(slots=True)
class SerializableContract:
    """Mixin for simple dict and JSON serialization of contract dataclasses."""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible dictionary representation."""
        return _serialize(self)

    def to_json(self) -> str:
        """Return a JSON string representation."""
        return json.dumps(self.to_dict(), sort_keys=True)


@dataclass(slots=True)
class Requester(SerializableContract):
    """Requester identity for a task envelope."""

    type: RequesterType
    id: str


@dataclass(slots=True)
class TaskSource(SerializableContract):
    """Original source of a task request."""

    kind: SourceKind
    uri: str | None = None


@dataclass(slots=True)
class TaskPermissions(SerializableContract):
    """Permission switches carried by early task envelopes."""

    read: bool = True
    write: bool = False
    execute: bool = False
    network: bool = False
    destructive: bool = False


@dataclass(slots=True)
class ApprovalPolicy(SerializableContract):
    """Approval requirements attached to a task envelope."""

    required_before: list[PermissionMode] = field(default_factory=list)
    approvers: list[str] = field(default_factory=list)


@dataclass(slots=True)
class VerificationPlan(SerializableContract):
    """Verification commands and expected evidence for a task."""

    commands: list[str] = field(default_factory=list)
    evidence_required: list[EvidenceType] = field(default_factory=list)


@dataclass(slots=True)
class TaskEnvelope(SerializableContract):
    """Serializable task contract derived from the Phoenix architecture docs."""

    task_id: str
    title: str
    objective: str
    requester: Requester
    source: TaskSource
    status: TaskStatus = TaskStatus.REQUESTED
    priority: TaskPriority = TaskPriority.NORMAL
    constraints: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    context_refs: list[str] = field(default_factory=list)
    allowed_resources: dict[str, list[str]] = field(default_factory=dict)
    permissions: TaskPermissions = field(default_factory=TaskPermissions)
    approval_policy: ApprovalPolicy = field(default_factory=ApprovalPolicy)
    verification_plan: VerificationPlan = field(default_factory=VerificationPlan)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)


@dataclass(slots=True)
class CodexHandoffPackage(SerializableContract):
    """Machine-readable package for preparing a manual Codex handoff."""

    schema_version: str
    handoff_id: str
    task: TaskEnvelope
    repository: str
    base_branch: str
    expected_pr_title: str
    prompt: str
    workspace_path: str | None = None
    required_repo_paths: list[str] = field(default_factory=list)
    required_pr_body_headings: list[str] = field(default_factory=list)
    worker_type: WorkerType = WorkerType.CODEX
    invocation_mode: str = "manual"
    invocation_authorized: bool = False
    review_required: bool = True
    worker_may_merge: bool = False


@dataclass(slots=True)
class CodexPilotEvidenceControl(SerializableContract):
    """Evidence status for one supervised Codex pilot external control."""

    control_id: str
    status: CodexPilotEvidenceStatus
    evidence_ref: str
    reviewer_role: CodexPilotEvidenceReviewerRole


@dataclass(slots=True)
class CodexPilotEvidencePackage(SerializableContract):
    """Machine-readable external-control evidence package for Codex pilots."""

    schema_version: str
    repository: str
    pilot_kind: str
    handoff_id: str
    controls: list[CodexPilotEvidenceControl] = field(default_factory=list)
    pilot_ready: bool = False
    invocation_authorized: bool = False


@dataclass(slots=True)
class CodexPilotAuthorizationPacket(SerializableContract):
    """One-attempt human authorization record for a supervised Codex pilot."""

    schema_version: str
    authorization_id: str
    repository: str
    pilot_kind: str
    decision_state: str
    authorizer_role: str
    base_commit_sha: str
    handoff_path: str
    evidence_path: str
    handoff_id: str
    objective: str
    allowed_paths: list[str]
    expected_pr_title: str
    branch_name: str
    validation_commands: list[str]
    budget_metric: str
    budget_ceiling: int
    budget_enforcement_ref: str
    timeout_seconds: int
    cancellation_ref: str
    authentication_runner_ref: str
    branch_permission_ref: str
    pr_permission_ref: str
    duplicate_pr_check_ref: str
    branch_collision_check_ref: str
    codex_no_approve_merge_ref: str
    final_ci_required: bool
    assistant_review_required: bool
    worker_may_approve: bool
    worker_may_merge: bool
    one_invocation_only: bool
    retry_authorized: bool
    background_execution_authorized: bool


CODEX_PILOT_AUTHORIZATION_SCHEMA_VERSION = "codex-pilot-authorization.v1"
CODEX_PILOT_AUTHORIZATION_REPOSITORY = "Phoenix-AI-Platform/phoenix-office"
CODEX_PILOT_AUTHORIZATION_KIND = "docs-only-supervised"
CODEX_PILOT_AUTHORIZATION_DECISION_STATE = "human_authorized_for_one_run"
CODEX_PILOT_AUTHORIZATION_AUTHOR_ROLE = "human_operator"
CODEX_PILOT_AUTHORIZATION_FINGERPRINT_SCHEMA_VERSION = (
    "phoenix-codex-authorization-fingerprint.v1"
)
CODEX_PILOT_AUTHORIZATION_FINGERPRINT_PREFIX = (
    f"{CODEX_PILOT_AUTHORIZATION_FINGERPRINT_SCHEMA_VERSION}\n"
)
CODEX_PILOT_AUTHORIZATION_PACKAGE_FIELDS = {
    "schema_version",
    "authorization_id",
    "repository",
    "pilot_kind",
    "decision_state",
    "authorizer_role",
    "base_commit_sha",
    "handoff_path",
    "evidence_path",
    "handoff_id",
    "objective",
    "allowed_paths",
    "expected_pr_title",
    "branch_name",
    "validation_commands",
    "budget_metric",
    "budget_ceiling",
    "budget_enforcement_ref",
    "timeout_seconds",
    "cancellation_ref",
    "authentication_runner_ref",
    "branch_permission_ref",
    "pr_permission_ref",
    "duplicate_pr_check_ref",
    "branch_collision_check_ref",
    "codex_no_approve_merge_ref",
    "final_ci_required",
    "assistant_review_required",
    "worker_may_approve",
    "worker_may_merge",
    "one_invocation_only",
    "retry_authorized",
    "background_execution_authorized",
}
CODEX_PILOT_AUTHORIZATION_FINGERPRINT_FIELDS = [
    "schema_version",
    "authorization_id",
    "repository",
    "pilot_kind",
    "decision_state",
    "authorizer_role",
    "base_commit_sha",
    "handoff_path",
    "evidence_path",
    "handoff_id",
    "objective",
    "allowed_paths",
    "expected_pr_title",
    "branch_name",
    "validation_commands",
    "budget_metric",
    "budget_ceiling",
    "budget_enforcement_ref",
    "timeout_seconds",
    "cancellation_ref",
    "authentication_runner_ref",
    "branch_permission_ref",
    "pr_permission_ref",
    "duplicate_pr_check_ref",
    "branch_collision_check_ref",
    "codex_no_approve_merge_ref",
    "final_ci_required",
    "assistant_review_required",
    "worker_may_approve",
    "worker_may_merge",
    "one_invocation_only",
    "retry_authorized",
    "background_execution_authorized",
]
CODEX_PILOT_AUTHORIZATION_REFERENCE_FIELDS = [
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
CODEX_PILOT_AUTHORIZATION_REQUIRED_TRUE_FIELDS = [
    "final_ci_required",
    "assistant_review_required",
    "one_invocation_only",
]
CODEX_PILOT_AUTHORIZATION_REQUIRED_FALSE_FIELDS = [
    "worker_may_approve",
    "worker_may_merge",
    "retry_authorized",
    "background_execution_authorized",
]
CODEX_PILOT_CLAIM_SCHEMA_VERSION = "codex-pilot-claim.v1"
CODEX_PILOT_OBJECTIVE_DIGEST_SCHEMA_VERSION = "codex-pilot-objective-digest.v1"
CODEX_PILOT_OBJECTIVE_DIGEST_PREFIX = (
    f"{CODEX_PILOT_OBJECTIVE_DIGEST_SCHEMA_VERSION}\n"
)
CODEX_PILOT_CLAIM_REQUIRED_FIELDS = {
    "schema_version",
    "attempt_id",
    "authorization_id",
    "authorization_fingerprint_schema_version",
    "authorization_fingerprint",
    "handoff_id",
    "repository",
    "pilot_kind",
    "base_commit_sha",
    "branch_name",
    "expected_pr_title",
    "objective_digest_schema_version",
    "objective_digest",
    "allowed_paths",
    "validation_commands",
    "budget_metric",
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
    "final_ci_required",
    "assistant_review_required",
    "worker_may_approve",
    "worker_may_merge",
    "one_invocation_only",
    "retry_authorized",
    "background_execution_authorized",
    "initial_lifecycle_state",
}
CODEX_PILOT_REQUIRED_VALIDATION_COMMANDS = [
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest --basetemp .pytest_tmp",
    "python -m ruff check . --no-cache",
    "git diff --check",
]
CODEX_PILOT_CLAIM_REFERENCE_FIELDS = [
    "attempt_id",
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
CODEX_PILOT_CLAIM_PROJECTION_FIELDS = [
    "authorization_id",
    "handoff_id",
    "repository",
    "pilot_kind",
    "base_commit_sha",
    "branch_name",
    "expected_pr_title",
    "allowed_paths",
    "validation_commands",
    "budget_metric",
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
    "final_ci_required",
    "assistant_review_required",
    "worker_may_approve",
    "worker_may_merge",
    "one_invocation_only",
    "retry_authorized",
    "background_execution_authorized",
]


def codex_pilot_authorization_fingerprint(package: object) -> str:
    """Return the deterministic v1 authorization fingerprint."""
    data = _contract_mapping(package)
    if set(data) != CODEX_PILOT_AUTHORIZATION_PACKAGE_FIELDS:
        raise ValueError("authorization fingerprint field set is invalid")
    payload = {
        field_name: data[field_name]
        for field_name in CODEX_PILOT_AUTHORIZATION_FINGERPRINT_FIELDS
    }
    _validate_codex_pilot_fingerprint_payload(payload)
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest_input = (
        CODEX_PILOT_AUTHORIZATION_FINGERPRINT_PREFIX.encode("utf-8")
        + canonical.encode("utf-8")
    )
    return hashlib.sha256(digest_input).hexdigest()


def codex_pilot_objective_digest(objective: object) -> str:
    """Return the deterministic v1 objective digest for a validated objective."""
    if not isinstance(objective, str) or not _is_safe_text(objective, 200):
        raise ValueError("objective is invalid")
    return hashlib.sha256(
        CODEX_PILOT_OBJECTIVE_DIGEST_PREFIX.encode("utf-8")
        + objective.encode("utf-8")
    ).hexdigest()


def codex_pilot_authorization_structural_errors(package: object) -> list[str]:
    """Return sanitized structural errors for a Codex pilot authorization packet."""
    try:
        data = _contract_mapping(package)
    except ValueError:
        return ["authorization package root must be an object"]
    return _authorization_structural_errors(data)


def validate_codex_pilot_authorization_packet(package: object) -> dict[str, Any]:
    """Validate a candidate codex-pilot-authorization.v1 packet."""
    errors = codex_pilot_authorization_structural_errors(package)
    return {
        "authorization_structural_errors": errors,
        "authorization_structural_valid": not errors,
    }


def validate_codex_pilot_claim_record(record: object) -> dict[str, Any]:
    """Validate a candidate codex-pilot-claim.v1 record without side effects."""
    errors: list[str] = []
    if not isinstance(record, dict):
        return _claim_result(
            structural_valid=False,
            structural_errors=["claim record root must be an object"],
        )
    fields_set = set(record)
    if CODEX_PILOT_CLAIM_REQUIRED_FIELDS - fields_set:
        errors.append("claim record is missing required fields")
    if fields_set - CODEX_PILOT_CLAIM_REQUIRED_FIELDS:
        errors.append("claim record contains unknown fields")

    _validate_claim_constants(record, errors)
    _validate_claim_types_and_shapes(record, errors)
    return _claim_result(structural_valid=not errors, structural_errors=errors)


def validate_codex_pilot_claim_binding(
    record: object,
    authorization_package: object,
) -> dict[str, Any]:
    """Validate claim binding against an inspected authorization object."""
    structural = validate_codex_pilot_claim_record(record)
    blockers: list[str] = []
    if not structural["claim_structural_valid"]:
        return {
            **structural,
            "claim_binding_blockers": [],
            "claim_binding_passed": False,
        }
    claim = _contract_mapping(record)
    try:
        authorization = _contract_mapping(authorization_package)
    except ValueError:
        return {
            **structural,
            "authorization_structural_errors": [
                "authorization package root must be an object"
            ],
            "claim_binding_blockers": ["authorization package is invalid"],
            "claim_binding_passed": False,
        }

    authorization_structural = validate_codex_pilot_authorization_packet(authorization)
    if not authorization_structural["authorization_structural_valid"]:
        return {
            **structural,
            **authorization_structural,
            "claim_binding_blockers": ["authorization package structurally invalid"],
            "claim_binding_passed": False,
        }

    try:
        fingerprint = codex_pilot_authorization_fingerprint(authorization)
    except ValueError:
        blockers.append("authorization fingerprint is invalid")
    else:
        if claim.get("authorization_fingerprint") != fingerprint:
            blockers.append("authorization fingerprint mismatch")

    try:
        objective_digest = codex_pilot_objective_digest(authorization.get("objective"))
    except ValueError:
        blockers.append("authorization objective is invalid")
    else:
        if claim.get("objective_digest") != objective_digest:
            blockers.append("objective digest mismatch")

    for field_name in CODEX_PILOT_CLAIM_PROJECTION_FIELDS:
        if claim.get(field_name) != authorization.get(field_name):
            blockers.append(f"{field_name} mismatch")

    return {
        **structural,
        **authorization_structural,
        "claim_binding_blockers": sorted(blockers),
        "claim_binding_passed": not blockers,
    }


def _claim_result(
    *,
    structural_valid: bool,
    structural_errors: list[str],
) -> dict[str, Any]:
    return {
        "claim_binding_passed": False,
        "claim_structural_errors": sorted(set(structural_errors)),
        "claim_structural_valid": structural_valid,
    }


def _contract_mapping(value: object) -> dict[str, Any]:
    if isinstance(value, SerializableContract):
        return value.to_dict()
    if isinstance(value, dict):
        return value
    raise ValueError("object is not a mapping")


def _validate_codex_pilot_fingerprint_payload(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise ValueError("authorization fingerprint payload is invalid")
    for value in payload.values():
        _validate_codex_pilot_fingerprint_value(value)


def _validate_codex_pilot_fingerprint_value(value: Any) -> None:
    if isinstance(value, str):
        if not _is_fingerprint_safe_text(value, 500):
            raise ValueError("authorization fingerprint payload is invalid")
    elif isinstance(value, bool):
        return
    elif type(value) is int:
        return
    elif isinstance(value, list):
        for item in value:
            _validate_codex_pilot_fingerprint_value(item)
    else:
        raise ValueError("authorization fingerprint payload is invalid")


def _authorization_structural_errors(package: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    package_fields = set(package)
    if CODEX_PILOT_AUTHORIZATION_PACKAGE_FIELDS - package_fields:
        errors.append("authorization package is missing required fields")
    if package_fields - CODEX_PILOT_AUTHORIZATION_PACKAGE_FIELDS:
        errors.append("authorization package contains unknown fields")

    expected_values = {
        "schema_version": CODEX_PILOT_AUTHORIZATION_SCHEMA_VERSION,
        "repository": CODEX_PILOT_AUTHORIZATION_REPOSITORY,
        "pilot_kind": CODEX_PILOT_AUTHORIZATION_KIND,
        "decision_state": CODEX_PILOT_AUTHORIZATION_DECISION_STATE,
        "authorizer_role": CODEX_PILOT_AUTHORIZATION_AUTHOR_ROLE,
        "budget_metric": "tokens",
    }
    for field_name, expected_value in expected_values.items():
        if package.get(field_name) != expected_value:
            errors.append(f"authorization {field_name} is invalid")

    for field_name in CODEX_PILOT_AUTHORIZATION_REFERENCE_FIELDS:
        if not _is_safe_identifier(package.get(field_name)):
            errors.append(f"authorization {field_name} is invalid")

    if not _is_lower_hex(package.get("base_commit_sha"), 40):
        errors.append("authorization base_commit_sha is invalid")
    for field_name in ["handoff_path", "evidence_path"]:
        if not _is_safe_authorization_json_path(package.get(field_name)):
            errors.append(f"authorization {field_name} is invalid")
    if not _is_safe_authorization_objective(package.get("objective")):
        errors.append("authorization objective is invalid")
    if not _is_allowed_paths(package.get("allowed_paths")):
        errors.append("authorization allowed paths are invalid")
    if not _is_safe_pr_title(package.get("expected_pr_title")):
        errors.append("authorization expected_pr_title is invalid")
    if not _is_safe_branch(package.get("branch_name")):
        errors.append("authorization branch_name is invalid")
    if package.get("validation_commands") != CODEX_PILOT_REQUIRED_VALIDATION_COMMANDS:
        errors.append("authorization validation commands are invalid")

    budget_ceiling = package.get("budget_ceiling")
    if (
        type(budget_ceiling) is not int
        or budget_ceiling < 1
        or budget_ceiling > 1_000_000
    ):
        errors.append("authorization budget is invalid")
    timeout_seconds = package.get("timeout_seconds")
    if (
        type(timeout_seconds) is not int
        or timeout_seconds < 60
        or timeout_seconds > 7200
    ):
        errors.append("authorization timeout is invalid")

    for field_name in CODEX_PILOT_AUTHORIZATION_REQUIRED_TRUE_FIELDS:
        if type(package.get(field_name)) is not bool or package.get(field_name) is not True:
            errors.append(f"authorization {field_name} must be JSON boolean true")
    for field_name in CODEX_PILOT_AUTHORIZATION_REQUIRED_FALSE_FIELDS:
        if type(package.get(field_name)) is not bool or package.get(field_name) is not False:
            errors.append(f"authorization {field_name} must be JSON boolean false")
    return sorted(set(errors))


def _is_fingerprint_safe_text(value: str, max_length: int) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and len(value) <= max_length
        and all(32 <= ord(character) <= 126 for character in value)
    )


def _validate_claim_constants(record: dict[str, Any], errors: list[str]) -> None:
    expected = {
        "schema_version": CODEX_PILOT_CLAIM_SCHEMA_VERSION,
        "authorization_fingerprint_schema_version": (
            CODEX_PILOT_AUTHORIZATION_FINGERPRINT_SCHEMA_VERSION
        ),
        "repository": CODEX_PILOT_AUTHORIZATION_REPOSITORY,
        "pilot_kind": CODEX_PILOT_AUTHORIZATION_KIND,
        "objective_digest_schema_version": CODEX_PILOT_OBJECTIVE_DIGEST_SCHEMA_VERSION,
        "budget_metric": "tokens",
        "initial_lifecycle_state": "claim_created",
    }
    for field_name, expected_value in expected.items():
        if record.get(field_name) != expected_value:
            errors.append(f"{field_name} is invalid")

    exact_true = ["final_ci_required", "assistant_review_required", "one_invocation_only"]
    exact_false = [
        "worker_may_approve",
        "worker_may_merge",
        "retry_authorized",
        "background_execution_authorized",
    ]
    for field_name in exact_true:
        if type(record.get(field_name)) is not bool or record.get(field_name) is not True:
            errors.append(f"{field_name} must be JSON boolean true")
    for field_name in exact_false:
        if type(record.get(field_name)) is not bool or record.get(field_name) is not False:
            errors.append(f"{field_name} must be JSON boolean false")


def _validate_claim_types_and_shapes(
    record: dict[str, Any],
    errors: list[str],
) -> None:
    for field_name in CODEX_PILOT_CLAIM_REFERENCE_FIELDS:
        if not _is_safe_identifier(record.get(field_name)):
            errors.append(f"{field_name} is invalid")
    if not _is_attempt_id(record.get("attempt_id")):
        errors.append("attempt_id is invalid")
    if not _is_lower_hex(record.get("authorization_fingerprint"), 64):
        errors.append("authorization_fingerprint is invalid")
    if not _is_lower_hex(record.get("objective_digest"), 64):
        errors.append("objective_digest is invalid")
    if not _is_lower_hex(record.get("base_commit_sha"), 40):
        errors.append("base_commit_sha is invalid")
    if not _is_safe_branch(record.get("branch_name")):
        errors.append("branch_name is invalid")
    if not _is_safe_pr_title(record.get("expected_pr_title")):
        errors.append("expected_pr_title is invalid")
    if not _is_allowed_paths(record.get("allowed_paths")):
        errors.append("allowed_paths are invalid")
    if record.get("validation_commands") != CODEX_PILOT_REQUIRED_VALIDATION_COMMANDS:
        errors.append("validation_commands are invalid")
    budget = record.get("budget_ceiling")
    if type(budget) is not int or budget < 1 or budget > 1_000_000:
        errors.append("budget_ceiling is invalid")
    timeout = record.get("timeout_seconds")
    if type(timeout) is not int or timeout < 60 or timeout > 7200:
        errors.append("timeout_seconds is invalid")


def _is_safe_text(value: str, max_length: int) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and len(value) <= max_length
        and all(32 <= ord(character) <= 126 for character in value)
        and not _contains_unsafe_marker(value)
    )


def _contains_unsafe_marker(value: str) -> bool:
    lowered = value.lower()
    markers = [
        "://",
        "appdata",
        "credential",
        "password",
        "private customer",
        "private-name",
        "secret",
        "sk-",
        "token",
        "users",
        "home",
        "/home",
        "home/",
        "~",
        "=",
    ]
    return any(marker in lowered for marker in markers)


def _contains_sensitive_marker(value: str) -> bool:
    lowered = value.lower()
    markers = [
        "appdata",
        "credential",
        "customer name",
        "password",
        "private customer",
        "private-name",
        "secret",
        "sk-",
        "token",
        "users",
        "/home",
        "home/",
        "~",
    ]
    return any(marker in lowered for marker in markers)


def _is_safe_identifier(value: object) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 80
        and value not in {".", ".."}
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value) is not None
        and not _contains_unsafe_marker(value)
    )


def _is_attempt_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= 80
        and re.fullmatch(r"pilot-attempt-[a-z0-9][a-z0-9._-]{11,62}", value)
        is not None
        and not _contains_unsafe_marker(value)
    )


def _is_lower_hex(value: object, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_safe_branch(value: object) -> bool:
    if not isinstance(value, str) or not _is_safe_text(value, 100):
        return False
    if (
        not value.startswith("codex/")
        or " " in value
        or ".." in value
        or "@{" in value
        or value.endswith("/")
        or value.startswith(".")
        or value.endswith(".")
        or "//" in value
        or "\\" in value
        or ":" in value
    ):
        return False
    return all(_is_safe_branch_component(segment) for segment in value.split("/"))


def _is_safe_branch_component(value: str) -> bool:
    return (
        bool(value)
        and value not in {".", ".."}
        and not value.startswith(".")
        and not value.lower().endswith(".lock")
        and re.fullmatch(r"[A-Za-z0-9._-]+", value) is not None
    )


def _is_safe_pr_title(value: object) -> bool:
    return (
        isinstance(value, str)
        and 6 <= len(value) <= 120
        and value.startswith("docs: ")
        and _is_safe_text(value, 120)
        and "/" not in value
        and "\\" not in value
        and "=" not in value
    )


def _is_allowed_paths(value: object) -> bool:
    if not isinstance(value, list) or not 1 <= len(value) <= 3:
        return False
    if not all(isinstance(path, str) for path in value):
        return False
    if len(set(value)) != len(value):
        return False
    if value != sorted(value):
        return False
    return all(_is_allowed_doc_path(path) for path in value)


def _is_allowed_doc_path(value: str) -> bool:
    if (
        not _is_safe_text(value, 160)
        or "\\" in value
        or ":" in value
        or "//" in value
        or value.startswith("/")
        or not value.endswith(".md")
        or value == "docs/development/project_state.md"
    ):
        return False
    if not (
        value.startswith("docs/process/")
        or value.startswith("docs/development/")
    ):
        return False
    segments = value.split("/")
    lowered_segments = {segment.lower() for segment in segments}
    forbidden_segments = {
        "api",
        "apis",
        "customer",
        "customers",
        "docx",
        "example",
        "examples",
        "fixture",
        "fixtures",
        "mcp",
        "orchestration",
        "proposal",
        "proposals",
        "server",
        "servers",
        "source",
        "sources",
        "src",
        "template",
        "templates",
        "test",
        "tests",
        "workflow",
        "workflows",
        "worker",
        "workers",
    }
    return lowered_segments.isdisjoint(forbidden_segments) and all(
        _is_safe_path_segment(segment) for segment in segments
    )


def _is_safe_authorization_json_path(value: object) -> bool:
    return (
        isinstance(value, str)
        and _is_safe_repo_relative_path(value, suffix=".json", max_length=160)
    )


def _is_safe_authorization_objective(value: object) -> bool:
    if not isinstance(value, str):
        return False
    if (
        not _is_safe_text(value, 200)
        or "/" in value
        or "\\" in value
        or "=" in value
    ):
        return False
    lowered = value.lower()
    return "document" in lowered or "docs" in lowered or "documentation" in lowered


def _is_safe_repo_relative_path(
    value: str,
    *,
    suffix: str,
    max_length: int,
) -> bool:
    if (
        not _is_safe_text(value, max_length)
        or " " in value
        or "\\" in value
        or ":" in value
        or "//" in value
        or value.startswith("/")
        or value.startswith("~")
        or not value.endswith(suffix)
    ):
        return False
    return all(_is_safe_path_segment(segment) for segment in value.split("/"))


def _is_safe_path_segment(value: str) -> bool:
    return (
        bool(value)
        and value not in {".", ".."}
        and re.fullmatch(r"[A-Za-z0-9._-]+", value) is not None
    )


@dataclass(slots=True)
class WorkerError(SerializableContract):
    """Structured worker failure details."""

    code: FailureCode
    message: str
    retryable: bool = False


@dataclass(slots=True)
class WorkerEvent(SerializableContract):
    """Serializable worker event derived from the Phoenix architecture docs."""

    event_id: str
    task_id: str
    worker_id: str
    worker_type: WorkerType
    event_type: WorkerEventType
    message: str
    status: str
    severity: EventSeverity = EventSeverity.INFO
    data: dict[str, Any] = field(default_factory=dict)
    artifact_refs: list[str] = field(default_factory=list)
    error: WorkerError | None = None
    created_at: datetime = field(default_factory=_utcnow)


@dataclass(slots=True)
class PluginFailureMode(SerializableContract):
    """Known plugin capability failure mode."""

    code: str
    retryable: bool
    description: str


@dataclass(slots=True)
class PluginCapability(SerializableContract):
    """Serializable plugin capability contract derived from architecture docs."""

    capability_id: str
    plugin_id: str
    name: str
    version: str
    description: str
    category: str
    operation_type: OperationType
    risk_level: RiskLevel
    input_schema_ref: str
    output_schema_ref: str
    required_permissions: list[PermissionMode] = field(default_factory=list)
    required_secrets: list[str] = field(default_factory=list)
    supports_dry_run: bool = False
    requires_approval: bool = False
    verification_methods: list[str] = field(default_factory=list)
    failure_modes: list[PluginFailureMode] = field(default_factory=list)


@dataclass(slots=True)
class ApprovalPreview(SerializableContract):
    """Preview information included in an approval request."""

    summary: str
    diff_ref: str | None = None
    dry_run_ref: str | None = None


@dataclass(slots=True)
class ApprovalRequest(SerializableContract):
    """Serializable approval request derived from the Phoenix architecture docs."""

    approval_request_id: str
    task_id: str
    requested_by_worker_id: str
    action: str
    reason: str
    risk_level: RiskLevel
    expected_result: str
    preview: ApprovalPreview
    capability_id: str | None = None
    target_resources: list[str] = field(default_factory=list)
    rollback_plan: str | None = None
    expires_at: datetime | None = None
    requested_approvers: list[str] = field(default_factory=list)
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = field(default_factory=_utcnow)


@dataclass(slots=True)
class ApprovedScope(SerializableContract):
    """Scope granted by an approval record."""

    actions: list[str] = field(default_factory=list)
    resources: list[str] = field(default_factory=list)
    expires_at: datetime | None = None
    single_use: bool = True


@dataclass(slots=True)
class ApprovalRecord(SerializableContract):
    """Serializable approval decision derived from the Phoenix architecture docs."""

    approval_record_id: str
    approval_request_id: str
    task_id: str
    decision: ApprovalDecision
    decided_by_type: str
    decided_by_id: str
    decision_reason: str | None = None
    approved_scope: ApprovedScope = field(default_factory=ApprovedScope)
    conditions: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utcnow)


@dataclass(slots=True)
class VerificationEvidence(SerializableContract):
    """Serializable verification evidence derived from architecture docs."""

    evidence_id: str
    task_id: str
    evidence_type: EvidenceType
    summary: str
    result: EvidenceResult
    verified_by_type: VerifierType
    verified_by_id: str
    worker_id: str | None = None
    capability_id: str | None = None
    command: str | None = None
    artifact_refs: list[str] = field(default_factory=list)
    observed_state: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
