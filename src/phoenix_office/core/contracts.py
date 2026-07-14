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
from copy import deepcopy
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any, Protocol


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
CODEX_PILOT_AUDIT_EVENT_SCHEMA_VERSION = "codex-pilot-audit-event.v1"
CODEX_PILOT_AUDIT_EVENT_DIGEST_SCHEMA_VERSION = (
    "codex-pilot-audit-event-digest.v1"
)
CODEX_PILOT_AUDIT_EVENT_DIGEST_PREFIX = (
    f"{CODEX_PILOT_AUDIT_EVENT_DIGEST_SCHEMA_VERSION}\n"
)
CODEX_PILOT_AUDIT_EVENT_REQUIRED_FIELDS = {
    "schema_version",
    "attempt_id",
    "authorization_id",
    "authorization_fingerprint",
    "event_sequence",
    "previous_lifecycle_state",
    "next_lifecycle_state",
    "event_category",
    "result_category",
    "actor_role",
    "codex_approved",
    "codex_merged",
    "previous_event_digest",
    "event_digest",
}
CODEX_PILOT_AUDIT_EVENT_OPTIONAL_FIELDS = {
    "branch_identity",
    "pull_request_identity",
    "usage_category",
    "timeout_category",
    "cancellation_category",
    "final_ci_category",
    "assistant_review_verdict",
    "recovery_category",
}
CODEX_PILOT_AUDIT_EVENT_FIELDS = (
    CODEX_PILOT_AUDIT_EVENT_REQUIRED_FIELDS | CODEX_PILOT_AUDIT_EVENT_OPTIONAL_FIELDS
)
CODEX_PILOT_AUDIT_TERMINAL_STATES = {
    "aborted",
    "failed",
    "cancelled",
    "timed_out",
    "completed_pending_review",
}
CODEX_PILOT_AUDIT_EVENT_TRANSITIONS: dict[
    tuple[str, str],
    dict[str, object],
] = {
    ("claim_not_started", "claim_created"): {
        "event_category": "claim_created",
        "result_category": "claim_created",
        "actor_role": "phoenix_gate",
        "required": set(),
    },
    ("claim_created", "invocation_starting"): {
        "event_category": "invocation_starting",
        "result_category": "started",
        "actor_role": "phoenix_gate",
        "required": set(),
    },
    ("claim_created", "aborted"): {
        "event_category": "claim_aborted",
        "result_category": "aborted",
        "actor_role": "phoenix_audit",
        "required": {"recovery_category"},
    },
    ("claim_created", "failed"): {
        "event_category": "claim_failed",
        "result_category": "failed",
        "actor_role": "phoenix_audit",
        "required": {"recovery_category"},
    },
    ("claim_created", "cancelled"): {
        "event_category": "claim_cancelled",
        "result_category": "cancelled",
        "actor_role": "phoenix_audit",
        "required": {"cancellation_category"},
    },
    ("claim_created", "timed_out"): {
        "event_category": "claim_timed_out",
        "result_category": "timed_out",
        "actor_role": "phoenix_audit",
        "required": {"timeout_category"},
    },
    ("invocation_starting", "invocation_started"): {
        "event_category": "invocation_started",
        "result_category": "started",
        "actor_role": "phoenix_gate",
        "required": set(),
    },
    ("invocation_starting", "aborted"): {
        "event_category": "invocation_start_aborted",
        "result_category": "aborted",
        "actor_role": "phoenix_audit",
        "required": {"recovery_category"},
    },
    ("invocation_starting", "failed"): {
        "event_category": "invocation_start_failed",
        "result_category": "failed",
        "actor_role": "phoenix_audit",
        "required": {"recovery_category"},
    },
    ("invocation_starting", "cancelled"): {
        "event_category": "invocation_start_cancelled",
        "result_category": "cancelled",
        "actor_role": "phoenix_audit",
        "required": {"cancellation_category"},
    },
    ("invocation_starting", "timed_out"): {
        "event_category": "invocation_start_timed_out",
        "result_category": "timed_out",
        "actor_role": "phoenix_audit",
        "required": {"timeout_category"},
    },
    ("invocation_started", "pr_opened_and_stopped"): {
        "event_category": "pr_opened_and_stopped",
        "result_category": "opened_pr",
        "actor_role": "phoenix_gate",
        "required": {"branch_identity", "pull_request_identity", "usage_category"},
    },
    ("invocation_started", "aborted"): {
        "event_category": "invocation_aborted",
        "result_category": "aborted",
        "actor_role": "phoenix_audit",
        "required": {"usage_category", "recovery_category"},
    },
    ("invocation_started", "failed"): {
        "event_category": "invocation_failed",
        "result_category": "failed",
        "actor_role": "phoenix_audit",
        "required": {"usage_category", "recovery_category"},
    },
    ("invocation_started", "cancelled"): {
        "event_category": "invocation_cancelled",
        "result_category": "cancelled",
        "actor_role": "phoenix_audit",
        "required": {"usage_category", "cancellation_category"},
    },
    ("invocation_started", "timed_out"): {
        "event_category": "invocation_timed_out",
        "result_category": "timed_out",
        "actor_role": "phoenix_audit",
        "required": {"usage_category", "timeout_category"},
    },
    ("pr_opened_and_stopped", "completed_pending_review"): {
        "event_category": "completed_pending_review",
        "result_category": "completed_pending_review",
        "actor_role": "phoenix_audit",
        "required": {
            "branch_identity",
            "pull_request_identity",
            "final_ci_category",
            "assistant_review_verdict",
        },
    },
}
CODEX_PILOT_AUDIT_EVENT_ALLOWED_VALUES = {
    "usage_category": {"within_budget", "budget_exceeded", "usage_unknown"},
    "timeout_category": {"timeout_not_reached", "timeout_reached", "timeout_unknown"},
    "cancellation_category": {
        "operator_cancelled",
        "no_cancellation_requested",
        "cancellation_unknown",
    },
    "final_ci_category": {"passed", "failed", "pending", "unknown"},
    "assistant_review_verdict": {
        "approved",
        "changes_requested",
        "commented",
        "pending",
        "unknown",
    },
    "recovery_category": {
        "durable_claim_without_invocation",
        "runner_crash",
        "operator_recovery",
        "storage_uncertain",
    },
}
CODEX_PILOT_ATTEMPT_SNAPSHOT_SCHEMA_VERSION = "codex-pilot-attempt-snapshot.v1"
CODEX_PILOT_ATTEMPT_SNAPSHOT_FIELDS = {
    "schema_version",
    "attempt_id",
    "authorization_id",
    "authorization_fingerprint",
    "latest_event_sequence",
    "latest_event_digest",
    "current_lifecycle_state",
    "terminal",
    "branch_identity",
    "pull_request_identity",
    "final_ci_category",
    "assistant_review_verdict",
    "codex_approved",
    "codex_merged",
    "authorization_reusable",
}
CODEX_PILOT_AUDIT_LIFECYCLE_STATES = {
    state
    for transition in CODEX_PILOT_AUDIT_EVENT_TRANSITIONS
    for state in transition
}
CODEX_PILOT_ATTEMPT_SNAPSHOT_STATE_SEQUENCES = {
    "claim_created": {0},
    "invocation_starting": {1},
    "invocation_started": {2},
    "pr_opened_and_stopped": {3},
    "completed_pending_review": {4},
    "aborted": {1, 2, 3},
    "failed": {1, 2, 3},
    "cancelled": {1, 2, 3},
    "timed_out": {1, 2, 3},
}
CODEX_PILOT_ATTEMPT_SNAPSHOT_NO_CONTEXT_STATES = {
    "claim_created",
    "invocation_starting",
    "invocation_started",
    "aborted",
    "failed",
    "cancelled",
    "timed_out",
}
CODEX_PILOT_INITIAL_CLAIM_BUNDLE_FIELDS = {
    "claim_bundle_passed",
    "claim_bundle_blockers",
    "claim_record",
    "audit_events",
    "snapshot",
}
CODEX_PILOT_INITIAL_CLAIM_PREPARATION_UNIQUENESS_KEYS = [
    "attempt_id",
    "authorization_id",
    "authorization_fingerprint",
]
CODEX_PILOT_INITIAL_CLAIM_CONFLICT_FIELDS = {
    "attempt_id_conflict",
    "authorization_id_conflict",
    "authorization_fingerprint_conflict",
}
CODEX_PILOT_INITIAL_CLAIM_STORE_CREATE_RESULT_FIELDS = {
    "claim_store_create_category",
}
CODEX_PILOT_INITIAL_CLAIM_STORE_CREATE_CATEGORIES = {
    "created",
    "bundle_invalid",
    "authorization_context_invalid",
    "bundle_binding_mismatch",
    "attempt_id_conflict",
    "authorization_id_conflict",
    "authorization_fingerprint_conflict",
    "claim_store_unavailable",
    "claim_durability_uncertain",
    "commit_incomplete",
    "claim_record_corrupt",
    "audit_event_corrupt",
    "snapshot_corrupt",
}
CODEX_PILOT_INITIAL_CLAIM_STORE_READ_RESULT_FIELDS = {
    "claim_store_read_category",
}
CODEX_PILOT_INITIAL_CLAIM_STORE_READ_CATEGORIES = {
    "read_success",
    "attempt_id_invalid",
    "authorization_context_invalid",
    "bundle_binding_mismatch",
    "missing_commit",
    "commit_incomplete",
    "claim_record_corrupt",
    "audit_event_corrupt",
    "snapshot_corrupt",
    "uniqueness_entry_corrupt",
    "digest_mismatch",
    "identity_mismatch",
    "history_mismatch",
    "claim_store_unavailable",
    "claim_durability_uncertain",
}
CODEX_PILOT_PREPARED_INITIAL_CLAIM_COMMIT_FIELDS = {
    "claim_record",
    "sequence_zero_event",
    "snapshot",
    "claim_record_bytes",
    "sequence_zero_event_bytes",
    "snapshot_bytes",
    "uniqueness_entries",
}


class CodexPilotInitialClaimStore(Protocol):
    """Backend-neutral atomic initial-claim create boundary."""

    def create_initial_claim_commit(
        self,
        preparation_result: object,
        authorization_package: object,
    ) -> object:
        """Create one initial-claim commit atomically."""
        ...


class CodexPilotInitialClaimReader(Protocol):
    """Backend-neutral read boundary for one committed initial-claim unit."""

    def read_initial_claim_bundle(
        self,
        attempt_id: object,
        authorization_package: object,
    ) -> object:
        """Read one committed initial-claim unit atomically."""
        ...


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


def codex_pilot_audit_event_digest(event: object) -> str:
    """Return the deterministic v1 audit-event digest for a complete payload."""
    data = _contract_mapping(event)
    _validate_codex_pilot_audit_digest_payload(data)
    canonical = json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest_input = (
        CODEX_PILOT_AUDIT_EVENT_DIGEST_PREFIX.encode("utf-8")
        + canonical.encode("utf-8")
    )
    return hashlib.sha256(digest_input).hexdigest()


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


def validate_codex_pilot_initial_claim_uniqueness_entries(
    uniqueness_entries: object,
    claim_record: object,
) -> dict[str, object]:
    """Validate the ordered v1 initial-claim uniqueness entries without side effects."""
    blockers: set[str] = set()
    claim_result = validate_codex_pilot_claim_record(claim_record)
    claim_structural_valid = claim_result["claim_structural_valid"]
    if not claim_structural_valid:
        blockers.add("claim_record_invalid")

    structural_valid = True
    binding_passed = claim_structural_valid

    if type(uniqueness_entries) is not list:
        blockers.add("uniqueness_entries_invalid")
        structural_valid = False
        binding_passed = False
    elif len(uniqueness_entries) != 3:
        blockers.add("uniqueness_entries_invalid")
        structural_valid = False
        binding_passed = False
    else:
        claim_data = _contract_mapping(claim_record) if claim_structural_valid else None
        authoritative_attempt_id = (
            claim_data["attempt_id"] if claim_data is not None else None
        )
        for index, key_name in enumerate(CODEX_PILOT_INITIAL_CLAIM_PREPARATION_UNIQUENESS_KEYS):
            entry = uniqueness_entries[index]
            blocker_name = f"{key_name}_uniqueness_invalid"
            if type(entry) is not dict or len(entry) != 1:
                blockers.add(blocker_name)
                structural_valid = False
                binding_passed = False
                continue

            outer_key = next(iter(entry))
            if type(outer_key) is not str or outer_key != key_name:
                blockers.add(blocker_name)
                structural_valid = False
                binding_passed = False
                continue

            key_map = entry[outer_key]
            if type(key_map) is not dict or len(key_map) != 1:
                blockers.add(blocker_name)
                structural_valid = False
                binding_passed = False
                continue

            inner_key = next(iter(key_map))
            if type(inner_key) is not str:
                blockers.add(blocker_name)
                structural_valid = False
                binding_passed = False
                continue

            if claim_data is not None and inner_key != claim_data[key_name]:
                blockers.add(blocker_name)
                binding_passed = False
                continue

            value = key_map[inner_key]
            if type(value) is not str:
                blockers.add(blocker_name)
                structural_valid = False
                binding_passed = False
                continue

            if value != authoritative_attempt_id:
                blockers.add(blocker_name)
                binding_passed = False

    return {
        "uniqueness_entries_structural_valid": structural_valid,
        "uniqueness_entries_binding_passed": binding_passed,
        "uniqueness_entry_blockers": sorted(blockers),
    }


def validate_codex_pilot_initial_claim_committed_unit(
    committed_unit: object,
    attempt_id: object,
    authorization_package: object,
) -> dict[str, object]:
    """Validate one already-loaded committed initial-claim unit in memory."""
    request_result = validate_codex_pilot_initial_claim_read_request(
        attempt_id,
        authorization_package,
    )
    if not request_result["claim_read_request_valid"]:
        return {
            "committed_unit_validation_passed": False,
            "committed_unit_blockers": request_result["claim_read_request_blockers"],
        }

    blockers: set[str] = set()
    required_fields = CODEX_PILOT_PREPARED_INITIAL_CLAIM_COMMIT_FIELDS
    if type(committed_unit) is not dict:
        blockers.add("commit_incomplete")
        return {
            "committed_unit_validation_passed": False,
            "committed_unit_blockers": sorted(blockers),
        }

    if len(committed_unit) != len(required_fields):
        blockers.add("commit_incomplete")
        return {
            "committed_unit_validation_passed": False,
            "committed_unit_blockers": sorted(blockers),
        }

    for key in committed_unit:
        if type(key) is not str:
            blockers.add("commit_incomplete")
            return {
                "committed_unit_validation_passed": False,
                "committed_unit_blockers": sorted(blockers),
            }

        if key not in required_fields:
            blockers.add("commit_incomplete")
            return {
                "committed_unit_validation_passed": False,
                "committed_unit_blockers": sorted(blockers),
            }

    def _validate_record_bytes(field_name: str, record: object) -> None:
        bytes_value = committed_unit[field_name]
        if type(bytes_value) is not bytes:
            blockers.add("digest_mismatch")
            return
        try:
            round_trip = json.loads(bytes_value.decode("utf-8"))
        except (TypeError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            blockers.add("digest_mismatch")
            return
        if type(round_trip) is not dict:
            blockers.add("digest_mismatch")
            return
        canonical = json.dumps(
            round_trip,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        if bytes_value != canonical:
            blockers.add("digest_mismatch")
            return
        if type(record) is dict:
            try:
                record_canonical = json.dumps(
                    record,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            except (TypeError, ValueError):
                return
            if bytes_value != record_canonical:
                blockers.add("digest_mismatch")

    claim_record = committed_unit["claim_record"]
    _validate_record_bytes("claim_record_bytes", claim_record)
    claim_structural_valid = False
    if type(claim_record) is not dict:
        blockers.add("claim_record_corrupt")
    else:
        claim_result = validate_codex_pilot_claim_record(claim_record)
        claim_structural_valid = claim_result["claim_structural_valid"]
        if not claim_structural_valid:
            blockers.add("claim_record_corrupt")
        if claim_structural_valid and claim_record.get("attempt_id") != attempt_id:
            blockers.add("identity_mismatch")
        if claim_structural_valid:
            claim_binding = validate_codex_pilot_claim_binding(
                claim_record,
                authorization_package,
            )
            if not claim_binding["claim_binding_passed"]:
                blockers.add("bundle_binding_mismatch")

    sequence_zero_event = committed_unit["sequence_zero_event"]
    _validate_record_bytes("sequence_zero_event_bytes", sequence_zero_event)
    event_structural_valid = False
    event_digest_valid = False
    event_identity_mismatch = False
    event_digest_mismatch = False
    event_history_mismatch = False
    event_binding_result: dict[str, Any] | None = None
    if type(sequence_zero_event) is not dict:
        blockers.add("audit_event_corrupt")
    else:
        event_payload = _audit_event_digest_payload_from_record(sequence_zero_event)
        event_structural_valid = not _audit_event_candidate_errors(event_payload)
        event_digest = sequence_zero_event.get("event_digest")
        event_digest_valid = type(event_digest) is str and _is_lower_hex(
            event_digest,
            64,
        )
        if not event_structural_valid or not event_digest_valid:
            blockers.add("audit_event_corrupt")
        if claim_structural_valid and event_structural_valid and event_digest_valid:
            event_binding_result = validate_codex_pilot_audit_event_binding(
                sequence_zero_event,
                claim_record,
                None,
            )
        if claim_structural_valid and all(
            field_name in sequence_zero_event
            for field_name in [
                "attempt_id",
                "authorization_id",
                "authorization_fingerprint",
            ]
        ):
            for field_name in [
                "attempt_id",
                "authorization_id",
                "authorization_fingerprint",
            ]:
                if sequence_zero_event.get(field_name) != claim_record.get(field_name):
                    blockers.add("identity_mismatch")
                    event_identity_mismatch = True
                    break
        if event_structural_valid and event_digest_valid:
            try:
                recomputed_event_digest = codex_pilot_audit_event_digest(event_payload)
            except ValueError:
                blockers.add("audit_event_corrupt")
            else:
                if event_digest != recomputed_event_digest:
                    blockers.add("digest_mismatch")
                    event_digest_mismatch = True
        event_history_mismatch = (
            event_structural_valid
            and event_digest_valid
            and (
                sequence_zero_event.get("event_sequence") != 0
                or sequence_zero_event.get("previous_event_digest") is not None
                or (
                    sequence_zero_event.get("previous_lifecycle_state"),
                    sequence_zero_event.get("next_lifecycle_state"),
                )
                != ("claim_not_started", "claim_created")
            )
        )
        if (
            event_binding_result is not None
            and not event_binding_result["event_binding_passed"]
            and event_history_mismatch
        ):
            blockers.add("history_mismatch")

    snapshot = committed_unit["snapshot"]
    _validate_record_bytes("snapshot_bytes", snapshot)
    snapshot_structural_valid = False
    snapshot_identity_mismatch = False
    snapshot_digest_mismatch = False
    snapshot_history_mismatch = False
    snapshot_binding_result: dict[str, Any] | None = None
    if type(snapshot) is not dict:
        blockers.add("snapshot_corrupt")
    else:
        snapshot_result = validate_codex_pilot_attempt_snapshot(snapshot)
        snapshot_structural_valid = snapshot_result["snapshot_structural_valid"]
        if not snapshot_structural_valid:
            blockers.add("snapshot_corrupt")
        if claim_structural_valid and all(
            field_name in snapshot
            for field_name in [
                "attempt_id",
                "authorization_id",
                "authorization_fingerprint",
            ]
        ):
            for field_name in [
                "attempt_id",
                "authorization_id",
                "authorization_fingerprint",
            ]:
                if snapshot.get(field_name) != claim_record.get(field_name):
                    blockers.add("identity_mismatch")
                    snapshot_identity_mismatch = True
                    break
        if (
            claim_structural_valid
            and event_structural_valid
            and event_digest_valid
            and snapshot_structural_valid
        ):
            snapshot_binding_result = validate_codex_pilot_attempt_snapshot_binding(
                snapshot,
                claim_record,
                [sequence_zero_event],
            )
        if event_structural_valid and event_digest_valid and snapshot_structural_valid:
            if snapshot.get("latest_event_digest") != event_digest:
                blockers.add("digest_mismatch")
                snapshot_digest_mismatch = True
            if (
                snapshot.get("latest_event_sequence")
                != sequence_zero_event.get("event_sequence")
                or snapshot.get("current_lifecycle_state")
                != sequence_zero_event.get("next_lifecycle_state")
                or snapshot.get("terminal") is not False
            ):
                blockers.add("history_mismatch")
                snapshot_history_mismatch = True
        if (
            snapshot_binding_result is not None
            and not snapshot_binding_result["snapshot_binding_passed"]
            and not event_identity_mismatch
            and not event_digest_mismatch
            and not snapshot_identity_mismatch
            and not snapshot_digest_mismatch
            and not snapshot_history_mismatch
        ):
            blockers.add("history_mismatch")

    uniqueness_entries = committed_unit["uniqueness_entries"]
    uniqueness_result = validate_codex_pilot_initial_claim_uniqueness_entries(
        uniqueness_entries,
        claim_record,
    )
    if not uniqueness_result["uniqueness_entries_structural_valid"]:
        blockers.add("uniqueness_entry_corrupt")
    elif claim_structural_valid and not uniqueness_result["uniqueness_entries_binding_passed"]:
        blockers.add("identity_mismatch")

    return {
        "committed_unit_validation_passed": not blockers,
        "committed_unit_blockers": sorted(blockers),
    }


def compose_codex_pilot_initial_claim_bundle(
    authorization_package: object,
    attempt_id: object,
) -> dict[str, Any]:
    """Compose the deterministic initial claim bundle for one supervised attempt."""
    blockers: list[str] = []
    authorization_result = validate_codex_pilot_authorization_packet(authorization_package)
    if not authorization_result["authorization_structural_valid"]:
        blockers.append("authorization package is invalid")
    if not _is_exact_codex_pilot_attempt_id(attempt_id):
        blockers.append("attempt_id is invalid")
    if blockers:
        return {
            "claim_bundle_passed": False,
            "claim_bundle_blockers": blockers,
            "claim_record": None,
            "audit_events": None,
            "snapshot": None,
        }

    authorization = _contract_mapping(authorization_package)
    claim_record = {
        "schema_version": CODEX_PILOT_CLAIM_SCHEMA_VERSION,
        "attempt_id": attempt_id,
        "authorization_id": authorization["authorization_id"],
        "authorization_fingerprint_schema_version": (
            CODEX_PILOT_AUTHORIZATION_FINGERPRINT_SCHEMA_VERSION
        ),
        "authorization_fingerprint": codex_pilot_authorization_fingerprint(authorization),
        "handoff_id": authorization["handoff_id"],
        "repository": authorization["repository"],
        "pilot_kind": authorization["pilot_kind"],
        "base_commit_sha": authorization["base_commit_sha"],
        "branch_name": authorization["branch_name"],
        "expected_pr_title": authorization["expected_pr_title"],
        "objective_digest_schema_version": CODEX_PILOT_OBJECTIVE_DIGEST_SCHEMA_VERSION,
        "objective_digest": codex_pilot_objective_digest(authorization["objective"]),
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
        "final_ci_required": authorization["final_ci_required"],
        "assistant_review_required": authorization["assistant_review_required"],
        "worker_may_approve": authorization["worker_may_approve"],
        "worker_may_merge": authorization["worker_may_merge"],
        "one_invocation_only": authorization["one_invocation_only"],
        "retry_authorized": authorization["retry_authorized"],
        "background_execution_authorized": authorization["background_execution_authorized"],
        "initial_lifecycle_state": "claim_created",
    }
    claim_result = validate_codex_pilot_claim_record(claim_record)
    if not claim_result["claim_structural_valid"]:
        return {
            "claim_bundle_passed": False,
            "claim_bundle_blockers": ["claim record is invalid"],
            "claim_record": None,
            "audit_events": None,
            "snapshot": None,
        }

    claim_binding = validate_codex_pilot_claim_binding(claim_record, authorization)
    if not claim_binding["claim_binding_passed"]:
        return {
            "claim_bundle_passed": False,
            "claim_bundle_blockers": ["claim binding failed"],
            "claim_record": None,
            "audit_events": None,
            "snapshot": None,
        }

    audit_event = {
        "schema_version": CODEX_PILOT_AUDIT_EVENT_SCHEMA_VERSION,
        "attempt_id": claim_record["attempt_id"],
        "authorization_id": claim_record["authorization_id"],
        "authorization_fingerprint": claim_record["authorization_fingerprint"],
        "event_sequence": 0,
        "previous_lifecycle_state": "claim_not_started",
        "next_lifecycle_state": "claim_created",
        "event_category": "claim_created",
        "result_category": "claim_created",
        "actor_role": "phoenix_gate",
        "codex_approved": False,
        "codex_merged": False,
        "previous_event_digest": None,
    }
    try:
        audit_event["event_digest"] = codex_pilot_audit_event_digest(audit_event)
    except ValueError:
        return {
            "claim_bundle_passed": False,
            "claim_bundle_blockers": ["sequence zero audit event is invalid"],
            "claim_record": None,
            "audit_events": None,
            "snapshot": None,
        }

    audit_event_result = validate_codex_pilot_audit_event_record(audit_event)
    if not audit_event_result["event_structural_valid"]:
        return {
            "claim_bundle_passed": False,
            "claim_bundle_blockers": ["sequence zero audit event is invalid"],
            "claim_record": None,
            "audit_events": None,
            "snapshot": None,
        }

    audit_event_binding = validate_codex_pilot_audit_event_binding(
        audit_event,
        claim_record,
        None,
    )
    if not audit_event_binding["event_binding_passed"]:
        return {
            "claim_bundle_passed": False,
            "claim_bundle_blockers": ["sequence zero audit event binding failed"],
            "claim_record": None,
            "audit_events": None,
            "snapshot": None,
        }

    snapshot_result = derive_codex_pilot_attempt_snapshot(claim_record, [audit_event])
    if not snapshot_result["snapshot_derivation_passed"] or snapshot_result["snapshot"] is None:
        return {
            "claim_bundle_passed": False,
            "claim_bundle_blockers": ["snapshot derivation failed"],
            "claim_record": None,
            "audit_events": None,
            "snapshot": None,
        }

    snapshot = snapshot_result["snapshot"]
    snapshot_validation = validate_codex_pilot_attempt_snapshot(snapshot)
    if not snapshot_validation["snapshot_structural_valid"]:
        return {
            "claim_bundle_passed": False,
            "claim_bundle_blockers": ["snapshot is invalid"],
            "claim_record": None,
            "audit_events": None,
            "snapshot": None,
        }

    snapshot_binding = validate_codex_pilot_attempt_snapshot_binding(
        snapshot,
        claim_record,
        [audit_event],
    )
    if not snapshot_binding["snapshot_binding_passed"]:
        return {
            "claim_bundle_passed": False,
            "claim_bundle_blockers": ["snapshot binding failed"],
            "claim_record": None,
            "audit_events": None,
            "snapshot": None,
        }

    return {
        "claim_bundle_passed": True,
        "claim_bundle_blockers": [],
        "claim_record": claim_record,
        "audit_events": [audit_event],
        "snapshot": snapshot,
    }


def prepare_codex_pilot_initial_claim_commit(
    bundle: object,
    authorization_package: object,
) -> dict[str, object]:
    """Prepare one deterministic validated initial-claim commit unit."""
    try:
        bundle_mapping = _contract_mapping(bundle)
    except ValueError:
        return _prepared_initial_claim_failure("initial claim bundle is invalid")

    if set(bundle_mapping) != CODEX_PILOT_INITIAL_CLAIM_BUNDLE_FIELDS:
        return _prepared_initial_claim_failure("initial claim bundle is invalid")
    if bundle_mapping.get("claim_bundle_passed") is not True:
        return _prepared_initial_claim_failure("initial claim bundle is invalid")
    if bundle_mapping.get("claim_bundle_blockers") != []:
        return _prepared_initial_claim_failure("initial claim bundle is invalid")
    if not isinstance(bundle_mapping.get("audit_events"), list):
        return _prepared_initial_claim_failure("initial claim bundle is invalid")

    audit_events = bundle_mapping["audit_events"]
    if len(audit_events) != 1:
        return _prepared_initial_claim_failure("initial claim bundle is invalid")
    sequence_zero_event = audit_events[0]

    authorization_result = validate_codex_pilot_authorization_packet(
        authorization_package
    )
    if not authorization_result["authorization_structural_valid"]:
        return _prepared_initial_claim_failure("authorization package is invalid")

    claim_record = bundle_mapping.get("claim_record")
    claim_result = validate_codex_pilot_claim_record(claim_record)
    if not claim_result["claim_structural_valid"]:
        return _prepared_initial_claim_failure("claim record is invalid")

    claim_binding = validate_codex_pilot_claim_binding(claim_record, authorization_package)
    if not claim_binding["claim_binding_passed"]:
        return _prepared_initial_claim_failure("claim binding failed")

    event_record_result = validate_codex_pilot_audit_event_record(sequence_zero_event)
    if not event_record_result["event_structural_valid"]:
        return _prepared_initial_claim_failure("sequence zero audit event is invalid")

    event_data = _contract_mapping(sequence_zero_event)
    if event_data.get("event_sequence") != 0:
        return _prepared_initial_claim_failure("sequence zero audit event is invalid")

    event_binding = validate_codex_pilot_audit_event_binding(
        sequence_zero_event,
        claim_record,
        None,
    )
    if not event_binding["event_binding_passed"]:
        return _prepared_initial_claim_failure("sequence zero audit event binding failed")

    snapshot = bundle_mapping.get("snapshot")
    snapshot_result = validate_codex_pilot_attempt_snapshot(snapshot)
    if not snapshot_result["snapshot_structural_valid"]:
        return _prepared_initial_claim_failure("snapshot is invalid")

    snapshot_binding = validate_codex_pilot_attempt_snapshot_binding(
        snapshot,
        claim_record,
        [sequence_zero_event],
    )
    if not snapshot_binding["snapshot_binding_passed"]:
        return _prepared_initial_claim_failure("snapshot binding failed")

    prepared_claim_record = deepcopy(claim_record)
    prepared_sequence_zero_event = deepcopy(sequence_zero_event)
    prepared_snapshot = deepcopy(snapshot)

    claim_data = _contract_mapping(prepared_claim_record)
    attempt_identity = claim_data["attempt_id"]
    uniqueness_entries = [
        {key_name: {claim_data[key_name]: attempt_identity}}
        for key_name in CODEX_PILOT_INITIAL_CLAIM_PREPARATION_UNIQUENESS_KEYS
    ]

    prepared_commit = {
        "claim_record": prepared_claim_record,
        "sequence_zero_event": prepared_sequence_zero_event,
        "snapshot": prepared_snapshot,
        "claim_record_bytes": _canonical_contract_json_bytes(prepared_claim_record),
        "sequence_zero_event_bytes": _canonical_contract_json_bytes(
            prepared_sequence_zero_event
        ),
        "snapshot_bytes": _canonical_contract_json_bytes(prepared_snapshot),
        "uniqueness_entries": uniqueness_entries,
    }

    return {
        "prepared_commit_passed": True,
        "prepared_commit_blockers": [],
        "prepared_commit": prepared_commit,
    }


def validate_codex_pilot_prepared_initial_claim_commit(
    preparation_result: object,
    authorization_package: object,
) -> dict[str, object]:
    """Validate the exact deterministic prepared initial-claim commit shape."""
    blockers: set[str] = set()
    structural_blockers: set[str] = set()

    if type(preparation_result) is not dict:
        return _prepared_commit_validation_result(
            structural_valid=False,
            binding_passed=False,
            blockers=["prepared_commit_result_invalid"],
        )

    preparation = preparation_result
    if set(preparation) != {
        "prepared_commit_passed",
        "prepared_commit_blockers",
        "prepared_commit",
    }:
        blockers.add("prepared_commit_result_invalid")
        structural_blockers.add("prepared_commit_result_invalid")
    if preparation.get("prepared_commit_passed") is not True:
        blockers.add("prepared_commit_result_invalid")
        structural_blockers.add("prepared_commit_result_invalid")
    if preparation.get("prepared_commit_blockers") != []:
        blockers.add("prepared_commit_result_invalid")
        structural_blockers.add("prepared_commit_result_invalid")

    prepared_commit = preparation.get("prepared_commit")
    if type(prepared_commit) is not dict:
        blockers.add("prepared_commit_result_invalid")
        structural_blockers.add("prepared_commit_result_invalid")
        return _prepared_commit_validation_result(
            structural_valid=not structural_blockers,
            binding_passed=False,
            blockers=blockers,
        )

    if set(prepared_commit) != CODEX_PILOT_PREPARED_INITIAL_CLAIM_COMMIT_FIELDS:
        blockers.add("prepared_commit_result_invalid")
        structural_blockers.add("prepared_commit_result_invalid")

    authorization_result = validate_codex_pilot_authorization_packet(authorization_package)
    if not authorization_result["authorization_structural_valid"]:
        blockers.add("authorization_package_invalid")
        structural_blockers.add("authorization_package_invalid")

    claim_record = prepared_commit.get("claim_record")
    claim_result = validate_codex_pilot_claim_record(claim_record)
    if not claim_result["claim_structural_valid"]:
        blockers.add("claim_record_invalid")
        structural_blockers.add("claim_record_invalid")

    sequence_zero_event = prepared_commit.get("sequence_zero_event")
    event_result = validate_codex_pilot_audit_event_record(sequence_zero_event)
    if not event_result["event_structural_valid"]:
        blockers.add("sequence_zero_event_invalid")
        structural_blockers.add("sequence_zero_event_invalid")
    else:
        event_data = _contract_mapping(sequence_zero_event)
        if event_data.get("event_sequence") != 0:
            blockers.add("sequence_zero_event_invalid")
            structural_blockers.add("sequence_zero_event_invalid")

    snapshot = prepared_commit.get("snapshot")
    snapshot_result = validate_codex_pilot_attempt_snapshot(snapshot)
    if not snapshot_result["snapshot_structural_valid"]:
        blockers.add("snapshot_invalid")
        structural_blockers.add("snapshot_invalid")

    if (
        claim_result["claim_structural_valid"]
        and authorization_result["authorization_structural_valid"]
    ):
        claim_binding = validate_codex_pilot_claim_binding(claim_record, authorization_package)
        if not claim_binding["claim_binding_passed"]:
            blockers.add("claim_binding_failed")

    if claim_result["claim_structural_valid"] and event_result["event_structural_valid"]:
        event_binding = validate_codex_pilot_audit_event_binding(
            sequence_zero_event,
            claim_record,
            None,
        )
        if not event_binding["event_binding_passed"]:
            blockers.add("sequence_zero_event_binding_failed")

    if (
        claim_result["claim_structural_valid"]
        and event_result["event_structural_valid"]
        and snapshot_result["snapshot_structural_valid"]
    ):
        snapshot_binding = validate_codex_pilot_attempt_snapshot_binding(
            snapshot,
            claim_record,
            [sequence_zero_event],
        )
        if not snapshot_binding["snapshot_binding_passed"]:
            blockers.add("snapshot_binding_failed")

    for field_name, record in [
        ("claim_record_bytes", claim_record),
        ("sequence_zero_event_bytes", sequence_zero_event),
        ("snapshot_bytes", snapshot),
    ]:
        bytes_value = prepared_commit.get(field_name)
        if type(bytes_value) is not bytes:
            blockers.add(f"{field_name}_invalid")
            structural_blockers.add(f"{field_name}_invalid")
            continue
        if type(record) is not dict:
            blockers.add(f"{field_name}_invalid")
            structural_blockers.add(f"{field_name}_invalid")
            continue
        try:
            decoded = bytes_value.decode("utf-8")
            round_trip = json.loads(decoded)
            canonical = _canonical_contract_json_bytes(record)
        except (TypeError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            blockers.add(f"{field_name}_invalid")
            structural_blockers.add(f"{field_name}_invalid")
            continue
        if bytes_value != canonical or round_trip != _contract_mapping(record):
            blockers.add(f"{field_name}_invalid")

    uniqueness_entries = prepared_commit.get("uniqueness_entries")
    uniqueness_result = validate_codex_pilot_initial_claim_uniqueness_entries(
        uniqueness_entries,
        claim_record,
    )
    if not uniqueness_result["uniqueness_entries_structural_valid"]:
        structural_blockers.add("prepared_commit_uniqueness_invalid")
    for blocker_name in uniqueness_result["uniqueness_entry_blockers"]:
        if blocker_name == "uniqueness_entries_invalid":
            blockers.add("prepared_commit_uniqueness_invalid")
            structural_blockers.add("prepared_commit_uniqueness_invalid")
        else:
            blockers.add(blocker_name)

    return _prepared_commit_validation_result(
        structural_valid=not structural_blockers,
        binding_passed=not blockers,
        blockers=blockers,
    )


def classify_codex_pilot_initial_claim_conflicts(
    preparation_result: object,
    authorization_package: object,
    conflict_observation: object,
) -> dict[str, object]:
    """Classify exact initial-claim uniqueness conflicts without side effects."""
    prepared_commit_result = validate_codex_pilot_prepared_initial_claim_commit(
        preparation_result,
        authorization_package,
    )
    if not (
        prepared_commit_result["prepared_commit_structural_valid"]
        and prepared_commit_result["prepared_commit_binding_passed"]
    ):
        return _conflict_classification_result(
            conflict_classification_passed=False,
            conflict_detected=None,
            conflict_category=None,
            blockers=prepared_commit_result["prepared_commit_blockers"],
        )

    conflict_observation_result = _validate_initial_claim_conflict_observation(
        conflict_observation
    )
    if not conflict_observation_result["conflict_observation_passed"]:
        return _conflict_classification_result(
            conflict_classification_passed=False,
            conflict_detected=None,
            conflict_category=None,
            blockers=conflict_observation_result["conflict_classification_blockers"],
        )

    observation = conflict_observation_result["conflict_observation"]
    if observation["attempt_id_conflict"] is True:
        conflict_category = "attempt_id_conflict"
    elif observation["authorization_id_conflict"] is True:
        conflict_category = "authorization_id_conflict"
    elif observation["authorization_fingerprint_conflict"] is True:
        conflict_category = "authorization_fingerprint_conflict"
    else:
        conflict_category = None

    return _conflict_classification_result(
        conflict_classification_passed=True,
        conflict_detected=conflict_category is not None,
        conflict_category=conflict_category,
        blockers=[],
    )


def validate_codex_pilot_audit_event_record(event: object) -> dict[str, Any]:
    """Validate a candidate codex-pilot-audit-event.v1 record."""
    errors = codex_pilot_audit_event_structural_errors(event)
    return {
        "event_binding_blockers": [],
        "event_binding_passed": False,
        "event_structural_errors": errors,
        "event_structural_valid": not errors,
    }


def validate_codex_pilot_audit_event_binding(
    event: object,
    claim_record: object,
    previous_event: object | None,
) -> dict[str, Any]:
    """Validate audit-event identity and chain binding without side effects."""
    event_result = validate_codex_pilot_audit_event_record(event)
    blockers: list[str] = []
    claim_result = validate_codex_pilot_claim_record(claim_record)
    if not claim_result["claim_structural_valid"]:
        return {
            **event_result,
            "claim_structural_valid": False,
            "event_binding_blockers": ["claim record invalid"],
            "event_binding_passed": False,
            "previous_event_structural_valid": None,
        }
    if not event_result["event_structural_valid"]:
        return {
            **event_result,
            "claim_structural_valid": True,
            "previous_event_structural_valid": None,
        }
    event_data = _contract_mapping(event)
    claim = _contract_mapping(claim_record)
    for field_name in [
        "attempt_id",
        "authorization_id",
        "authorization_fingerprint",
    ]:
        if event_data.get(field_name) != claim.get(field_name):
            blockers.append(f"{field_name} mismatch")

    sequence = event_data["event_sequence"]
    previous_structural_valid: bool | None = None
    if sequence == 0:
        if previous_event is not None:
            blockers.append("previous event must be absent for sequence zero")
        if event_data.get("previous_event_digest") is not None:
            blockers.append("previous_event_digest must be null for sequence zero")
        if (
            event_data.get("previous_lifecycle_state"),
            event_data.get("next_lifecycle_state"),
        ) != ("claim_not_started", "claim_created"):
            blockers.append("sequence zero transition is invalid")
    else:
        if previous_event is None:
            blockers.append("previous event is required")
        else:
            previous_record_result = validate_codex_pilot_audit_event_record(previous_event)
            previous_structural_valid = previous_record_result["event_structural_valid"]
            if not previous_structural_valid:
                blockers.append("previous event is structurally invalid")
            else:
                previous = _contract_mapping(previous_event)
                previous_digest = codex_pilot_audit_event_digest(
                    _audit_event_digest_payload_from_record(previous)
                )
                for field_name in [
                    "attempt_id",
                    "authorization_id",
                    "authorization_fingerprint",
                ]:
                    if previous.get(field_name) != claim.get(field_name):
                        blockers.append(f"previous {field_name} mismatch")
                    if previous.get(field_name) != event_data.get(field_name):
                        blockers.append(f"previous {field_name} mismatch")
                if previous.get("event_digest") != previous_digest:
                    blockers.append("previous event digest mismatch")
                if previous.get("event_sequence") + 1 != sequence:
                    blockers.append("event sequence is not contiguous")
                if event_data.get("previous_event_digest") != previous_digest:
                    blockers.append("previous_event_digest mismatch")
                if previous.get("next_lifecycle_state") in CODEX_PILOT_AUDIT_TERMINAL_STATES:
                    blockers.append("previous event is terminal")
                if event_data.get("previous_lifecycle_state") != previous.get(
                    "next_lifecycle_state"
                ):
                    blockers.append("previous lifecycle state mismatch")
                if (
                    previous.get("next_lifecycle_state") == "pr_opened_and_stopped"
                    and event_data.get("next_lifecycle_state") == "completed_pending_review"
                ):
                    for field_name in ["branch_identity", "pull_request_identity"]:
                        if event_data.get(field_name) != previous.get(field_name):
                            blockers.append(f"{field_name} mismatch")

    return {
        **event_result,
        "claim_structural_valid": True,
        "event_binding_blockers": sorted(set(blockers)),
        "event_binding_passed": not blockers,
        "previous_event_structural_valid": previous_structural_valid,
    }


def validate_codex_pilot_attempt_snapshot(snapshot: object) -> dict[str, Any]:
    """Validate a candidate codex-pilot-attempt-snapshot.v1 record."""
    errors = codex_pilot_attempt_snapshot_structural_errors(snapshot)
    return {
        "snapshot_binding_blockers": [],
        "snapshot_binding_passed": False,
        "snapshot_structural_errors": errors,
        "snapshot_structural_valid": not errors,
    }


def derive_codex_pilot_attempt_snapshot(
    claim_record: object,
    audit_events: object,
) -> dict[str, Any]:
    """Derive a deterministic attempt snapshot from a claim and ordered events."""
    claim_result = validate_codex_pilot_claim_record(claim_record)
    blockers: list[str] = []
    if not claim_result["claim_structural_valid"]:
        blockers.append("claim_record_invalid")
        return _snapshot_derivation_result(
            claim_structural_valid=False,
            event_chain_valid=False,
            blockers=blockers,
            snapshot=None,
        )
    if not isinstance(audit_events, list):
        blockers.append("event_sequence_invalid")
        return _snapshot_derivation_result(
            claim_structural_valid=True,
            event_chain_valid=False,
            blockers=blockers,
            snapshot=None,
        )
    if not audit_events:
        blockers.append("event_sequence_invalid")
        return _snapshot_derivation_result(
            claim_structural_valid=True,
            event_chain_valid=False,
            blockers=blockers,
            snapshot=None,
        )

    claim = _contract_mapping(claim_record)
    previous_event: object | None = None
    branch_identity: str | None = None
    pull_request_identity: str | None = None
    final_ci_category: str | None = None
    assistant_review_verdict: str | None = None
    latest_event: dict[str, Any] | None = None

    for index, event in enumerate(audit_events):
        binding = validate_codex_pilot_audit_event_binding(
            event,
            claim_record,
            previous_event,
        )
        if not binding["event_structural_valid"]:
            blockers.append("audit_event_corrupt")
        if not binding["event_binding_passed"]:
            blockers.append("event_binding_mismatch")
        if binding["event_structural_valid"]:
            event_data = _contract_mapping(event)
            if event_data.get("event_sequence") != index:
                blockers.append("event_sequence_invalid")
            if event_data.get("next_lifecycle_state") == "pr_opened_and_stopped":
                branch_identity = event_data.get("branch_identity")
                pull_request_identity = event_data.get("pull_request_identity")
            if event_data.get("next_lifecycle_state") == "completed_pending_review":
                if event_data.get("branch_identity") != branch_identity:
                    blockers.append("snapshot_context_mismatch")
                if event_data.get("pull_request_identity") != pull_request_identity:
                    blockers.append("snapshot_context_mismatch")
                final_ci_category = event_data.get("final_ci_category")
                assistant_review_verdict = event_data.get("assistant_review_verdict")
            latest_event = event_data
        previous_event = event

    if blockers or latest_event is None:
        return _snapshot_derivation_result(
            claim_structural_valid=True,
            event_chain_valid=False,
            blockers=blockers,
            snapshot=None,
        )

    snapshot = {
        "schema_version": CODEX_PILOT_ATTEMPT_SNAPSHOT_SCHEMA_VERSION,
        "attempt_id": claim["attempt_id"],
        "authorization_id": claim["authorization_id"],
        "authorization_fingerprint": claim["authorization_fingerprint"],
        "latest_event_sequence": latest_event["event_sequence"],
        "latest_event_digest": latest_event["event_digest"],
        "current_lifecycle_state": latest_event["next_lifecycle_state"],
        "terminal": (
            latest_event["next_lifecycle_state"] in CODEX_PILOT_AUDIT_TERMINAL_STATES
        ),
        "branch_identity": branch_identity,
        "pull_request_identity": pull_request_identity,
        "final_ci_category": final_ci_category,
        "assistant_review_verdict": assistant_review_verdict,
        "codex_approved": False,
        "codex_merged": False,
        "authorization_reusable": False,
    }
    return _snapshot_derivation_result(
        claim_structural_valid=True,
        event_chain_valid=True,
        blockers=[],
        snapshot=snapshot,
    )


def validate_codex_pilot_attempt_snapshot_binding(
    snapshot: object,
    claim_record: object,
    audit_events: object,
) -> dict[str, Any]:
    """Validate a candidate snapshot against the deterministic derivation."""
    snapshot_result = validate_codex_pilot_attempt_snapshot(snapshot)
    derivation_result = derive_codex_pilot_attempt_snapshot(claim_record, audit_events)
    blockers: list[str] = []
    if not snapshot_result["snapshot_structural_valid"]:
        blockers.append("snapshot_record_invalid")
    if not derivation_result["snapshot_derivation_passed"]:
        blockers.append("snapshot_derivation_failed")
    if (
        snapshot_result["snapshot_structural_valid"]
        and derivation_result["snapshot_derivation_passed"]
    ):
        snapshot_data = _contract_mapping(snapshot)
        if snapshot_data != derivation_result["snapshot"]:
            blockers.append("snapshot_mismatch")
    return {
        **snapshot_result,
        "claim_structural_valid": derivation_result["claim_structural_valid"],
        "event_chain_valid": derivation_result["event_chain_valid"],
        "snapshot_binding_blockers": sorted(set(blockers)),
        "snapshot_binding_passed": not blockers,
        "snapshot_derivation_blockers": derivation_result[
            "snapshot_derivation_blockers"
        ],
        "snapshot_derivation_passed": derivation_result[
            "snapshot_derivation_passed"
        ],
    }


def codex_pilot_audit_event_structural_errors(event: object) -> list[str]:
    """Return sanitized structural errors for a Codex pilot audit event."""
    try:
        data = _contract_mapping(event)
    except ValueError:
        return ["audit event root must be an object"]
    return _audit_event_structural_errors(data)


def codex_pilot_attempt_snapshot_structural_errors(snapshot: object) -> list[str]:
    """Return sanitized structural errors for a Codex pilot attempt snapshot."""
    try:
        data = _contract_mapping(snapshot)
    except ValueError:
        return ["snapshot root must be an object"]
    return _attempt_snapshot_structural_errors(data)


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


def _prepared_initial_claim_failure(blocker: str) -> dict[str, object]:
    return {
        "prepared_commit_passed": False,
        "prepared_commit_blockers": [blocker],
        "prepared_commit": None,
    }


def _prepared_commit_validation_result(
    *,
    structural_valid: bool,
    binding_passed: bool,
    blockers: set[str] | list[str],
) -> dict[str, object]:
    return {
        "prepared_commit_structural_valid": structural_valid,
        "prepared_commit_binding_passed": binding_passed,
        "prepared_commit_blockers": sorted(set(blockers)),
    }


def _initial_claim_store_create_result(
    *,
    result_valid: bool,
    claim_created: bool | None,
    category: str | None,
    blockers: set[str] | list[str],
) -> dict[str, object]:
    return {
        "claim_store_create_result_valid": result_valid,
        "claim_created": claim_created,
        "claim_store_create_category": category,
        "claim_store_create_result_blockers": sorted(set(blockers)),
    }


def _initial_claim_store_read_result(
    *,
    result_valid: bool,
    claim_read_succeeded: bool | None,
    category: str | None,
    blockers: set[str] | list[str],
) -> dict[str, object]:
    return {
        "claim_store_read_result_valid": result_valid,
        "claim_read_succeeded": claim_read_succeeded,
        "claim_store_read_category": category,
        "claim_store_read_result_blockers": sorted(set(blockers)),
    }


def _initial_claim_read_request_result(
    *,
    request_valid: bool,
    attempt_id_valid: bool,
    authorization_context_valid: bool,
    blockers: set[str] | list[str],
) -> dict[str, object]:
    return {
        "claim_read_request_valid": request_valid,
        "attempt_id_valid": attempt_id_valid,
        "authorization_context_valid": authorization_context_valid,
        "claim_read_request_blockers": sorted(set(blockers)),
    }


def _conflict_classification_result(
    *,
    conflict_classification_passed: bool,
    conflict_detected: bool | None,
    conflict_category: str | None,
    blockers: set[str] | list[str],
) -> dict[str, object]:
    return {
        "conflict_classification_passed": conflict_classification_passed,
        "conflict_detected": conflict_detected,
        "conflict_category": conflict_category,
        "conflict_classification_blockers": sorted(set(blockers)),
    }


def validate_codex_pilot_initial_claim_store_create_result(
    result: object,
) -> dict[str, object]:
    """Validate the bounded initial-claim store create result shape."""
    if type(result) is not dict:
        return _initial_claim_store_create_result(
            result_valid=False,
            claim_created=None,
            category=None,
            blockers=["claim_store_create_result_invalid"],
        )

    data = result
    if len(data) != 1:
        return _initial_claim_store_create_result(
            result_valid=False,
            claim_created=None,
            category=None,
            blockers=["claim_store_create_result_invalid"],
        )

    key = next(iter(data))
    if type(key) is not str or key != "claim_store_create_category":
        return _initial_claim_store_create_result(
            result_valid=False,
            claim_created=None,
            category=None,
            blockers=["claim_store_create_result_invalid"],
        )

    category = data["claim_store_create_category"]
    blockers: set[str] = set()
    if type(category) is not str or category not in (
        CODEX_PILOT_INITIAL_CLAIM_STORE_CREATE_CATEGORIES
    ):
        blockers.add("claim_store_create_category_invalid")

    if blockers:
        return _initial_claim_store_create_result(
            result_valid=False,
            claim_created=None,
            category=None,
            blockers=blockers,
        )

    return _initial_claim_store_create_result(
        result_valid=True,
        claim_created=category == "created",
        category=category,
        blockers=[],
    )


def validate_codex_pilot_initial_claim_store_read_result(
    result: object,
) -> dict[str, object]:
    """Validate the bounded initial-claim store read result shape."""
    if type(result) is not dict:
        return _initial_claim_store_read_result(
            result_valid=False,
            claim_read_succeeded=None,
            category=None,
            blockers=["claim_store_read_result_invalid"],
        )

    data = result
    if len(data) != 1:
        return _initial_claim_store_read_result(
            result_valid=False,
            claim_read_succeeded=None,
            category=None,
            blockers=["claim_store_read_result_invalid"],
        )

    key = next(iter(data))
    if type(key) is not str or key != "claim_store_read_category":
        return _initial_claim_store_read_result(
            result_valid=False,
            claim_read_succeeded=None,
            category=None,
            blockers=["claim_store_read_result_invalid"],
        )

    category = data["claim_store_read_category"]
    blockers: set[str] = set()
    if type(category) is not str or category not in (
        CODEX_PILOT_INITIAL_CLAIM_STORE_READ_CATEGORIES
    ):
        blockers.add("claim_store_read_category_invalid")

    if blockers:
        return _initial_claim_store_read_result(
            result_valid=False,
            claim_read_succeeded=None,
            category=None,
            blockers=blockers,
        )

    return _initial_claim_store_read_result(
        result_valid=True,
        claim_read_succeeded=category == "read_success",
        category=category,
        blockers=[],
    )


def validate_codex_pilot_initial_claim_read_request(
    attempt_id: object,
    authorization_package: object,
) -> dict[str, object]:
    """Validate a deterministic pre-read request for a committed initial claim."""
    attempt_id_valid = _is_exact_codex_pilot_attempt_id(attempt_id)
    authorization_context_valid = False

    authorization_result = validate_codex_pilot_authorization_packet(authorization_package)
    if authorization_result["authorization_structural_valid"]:
        try:
            authorization = _contract_mapping(authorization_package)
        except ValueError:
            authorization_context_valid = False
        else:
            try:
                codex_pilot_authorization_fingerprint(authorization)
                codex_pilot_objective_digest(authorization["objective"])
            except ValueError:
                authorization_context_valid = False
            else:
                authorization_context_valid = True

    blockers: set[str] = set()
    if not attempt_id_valid:
        blockers.add("attempt_id_invalid")
    if not authorization_context_valid:
        blockers.add("authorization_context_invalid")
    return _initial_claim_read_request_result(
        request_valid=attempt_id_valid and authorization_context_valid,
        attempt_id_valid=attempt_id_valid,
        authorization_context_valid=authorization_context_valid,
        blockers=blockers,
    )


def classify_codex_pilot_initial_claim_read_outcome(
    attempt_id: object,
    authorization_package: object,
    read_observation: object,
    committed_unit: object,
) -> dict[str, object]:
    """Classify one already-observed initial-claim read without side effects."""
    request_result = validate_codex_pilot_initial_claim_read_request(
        attempt_id,
        authorization_package,
    )
    if not request_result["attempt_id_valid"]:
        category = "attempt_id_invalid"
    elif not request_result["authorization_context_valid"]:
        category = "authorization_context_invalid"
    else:
        observation_valid = False
        if type(read_observation) is dict:
            try:
                observation_valid = (
                    len(read_observation) == 3
                    and all(type(key) is str for key in read_observation)
                    and all(
                        field_name in read_observation
                        for field_name in (
                            "store_available",
                            "durability_certain",
                            "commit_present",
                        )
                    )
                    and all(
                        type(read_observation[field_name]) is bool
                        for field_name in (
                            "store_available",
                            "durability_certain",
                            "commit_present",
                        )
                    )
                )
            except Exception:
                observation_valid = False

        if not observation_valid or read_observation["store_available"] is False:
            category = "claim_store_unavailable"
        elif read_observation["durability_certain"] is False:
            category = "claim_durability_uncertain"
        elif read_observation["commit_present"] is False:
            category = "missing_commit"
        else:
            from phoenix_office.core.committed_unit_override import (
                validate_codex_pilot_initial_claim_committed_unit as validate_committed_unit,
            )

            committed_unit_result = validate_committed_unit(
                committed_unit,
                attempt_id,
                authorization_package,
            )
            if committed_unit_result["committed_unit_validation_passed"]:
                category = "read_success"
            else:
                committed_unit_blockers = committed_unit_result[
                    "committed_unit_blockers"
                ]
                category = next(
                    (
                        blocker
                        for blocker in (
                            "bundle_binding_mismatch",
                            "commit_incomplete",
                            "claim_record_corrupt",
                            "audit_event_corrupt",
                            "snapshot_corrupt",
                            "uniqueness_entry_corrupt",
                            "digest_mismatch",
                            "identity_mismatch",
                            "history_mismatch",
                        )
                        if blocker in committed_unit_blockers
                    ),
                    "commit_incomplete",
                )

    result = {"claim_store_read_category": category}
    result_validation = validate_codex_pilot_initial_claim_store_read_result(result)
    if not result_validation["claim_store_read_result_valid"]:
        return {"claim_store_read_category": "claim_store_unavailable"}
    return result


def _validate_initial_claim_conflict_observation(
    conflict_observation: object,
) -> dict[str, object]:
    blockers: set[str] = set()
    if type(conflict_observation) is not dict:
        blockers.add("conflict_observation_invalid")
        return {
            "conflict_observation_passed": False,
            "conflict_observation": None,
            "conflict_classification_blockers": sorted(blockers),
        }

    observation = conflict_observation
    if set(observation) != CODEX_PILOT_INITIAL_CLAIM_CONFLICT_FIELDS:
        blockers.add("conflict_observation_invalid")
    else:
        for field_name in (
            "attempt_id_conflict",
            "authorization_id_conflict",
            "authorization_fingerprint_conflict",
        ):
            if type(observation.get(field_name)) is not bool:
                blockers.add("conflict_observation_invalid")
                break

    if blockers:
        return {
            "conflict_observation_passed": False,
            "conflict_observation": None,
            "conflict_classification_blockers": sorted(blockers),
        }

    return {
        "conflict_observation_passed": True,
        "conflict_observation": observation,
        "conflict_classification_blockers": [],
    }


def _contract_mapping(value: object) -> dict[str, Any]:
    if isinstance(value, SerializableContract):
        return value.to_dict()
    if isinstance(value, dict):
        return value
    raise ValueError("object is not a mapping")


def _canonical_contract_json_bytes(record: object) -> bytes:
    canonical_bytes = json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    if json.loads(canonical_bytes.decode("utf-8")) != _contract_mapping(record):
        raise ValueError("canonical record bytes are invalid")
    return canonical_bytes


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


def _audit_event_structural_errors(event: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    field_set = set(event)
    if CODEX_PILOT_AUDIT_EVENT_REQUIRED_FIELDS - field_set:
        errors.append("audit event is missing required fields")
    if field_set - CODEX_PILOT_AUDIT_EVENT_FIELDS:
        errors.append("audit event contains unknown fields")
    _validate_audit_event_core_shape(event, errors)
    if _can_digest_audit_event_record(event):
        try:
            digest = codex_pilot_audit_event_digest(
                _audit_event_digest_payload_from_record(event)
            )
        except ValueError:
            errors.append("event_digest_mismatch")
        else:
            if event.get("event_digest") != digest:
                errors.append("event_digest_mismatch")
    return sorted(set(errors))


def _validate_audit_event_core_shape(
    event: dict[str, Any],
    errors: list[str],
) -> None:
    field_set = set(event)
    if event.get("schema_version") != CODEX_PILOT_AUDIT_EVENT_SCHEMA_VERSION:
        errors.append("schema_version is invalid")
    for field_name in ["attempt_id", "authorization_id"]:
        if not _is_safe_identifier(event.get(field_name)):
            errors.append(f"{field_name} is invalid")
    if not _is_lower_hex(event.get("authorization_fingerprint"), 64):
        errors.append("authorization_fingerprint is invalid")
    if type(event.get("event_sequence")) is not int or event.get("event_sequence") < 0:
        errors.append("event_sequence is invalid")
    if not _is_lower_hex(event.get("event_digest"), 64):
        errors.append("event_digest is invalid")
    if type(event.get("codex_approved")) is not bool or event.get("codex_approved") is not False:
        errors.append("codex_approved must be JSON boolean false")
    if type(event.get("codex_merged")) is not bool or event.get("codex_merged") is not False:
        errors.append("codex_merged must be JSON boolean false")

    transition = _audit_event_transition(event)
    if transition is None:
        errors.append("invalid_lifecycle_transition")
    else:
        for field_name in ["event_category", "result_category", "actor_role"]:
            if event.get(field_name) != transition[field_name]:
                errors.append(f"{field_name} is invalid")
        required = set(transition["required"])
        present_optional = CODEX_PILOT_AUDIT_EVENT_OPTIONAL_FIELDS & field_set
        missing_required = required - field_set
        forbidden_present = present_optional - required
        if missing_required:
            errors.append("audit event is missing required optional fields")
        if forbidden_present:
            errors.append("audit event contains forbidden optional fields")

    sequence = event.get("event_sequence")
    previous_digest = event.get("previous_event_digest")
    transition_key = (
        event.get("previous_lifecycle_state"),
        event.get("next_lifecycle_state"),
    )
    if sequence == 0:
        if previous_digest is not None:
            errors.append("previous_event_digest must be null for sequence zero")
        if transition_key != ("claim_not_started", "claim_created"):
            errors.append("sequence zero transition is invalid")
    elif type(sequence) is int and sequence > 0:
        if not _is_lower_hex(previous_digest, 64):
            errors.append("previous_event_digest is invalid")
        if transition_key == ("claim_not_started", "claim_created"):
            errors.append("claim-created transition sequence is invalid")
        if event.get("previous_lifecycle_state") == "claim_not_started":
            errors.append("nonzero transition previous state is invalid")
    elif "event_sequence is invalid" not in errors:
        errors.append("event_sequence is invalid")

    _validate_audit_event_optional_values(event, errors)


def _audit_event_transition(event: dict[str, Any]) -> dict[str, object] | None:
    previous_state = event.get("previous_lifecycle_state")
    next_state = event.get("next_lifecycle_state")
    if not isinstance(previous_state, str) or not isinstance(next_state, str):
        return None
    return CODEX_PILOT_AUDIT_EVENT_TRANSITIONS.get((previous_state, next_state))


def _validate_audit_event_optional_values(
    event: dict[str, Any],
    errors: list[str],
) -> None:
    if "branch_identity" in event and not _is_safe_branch(event.get("branch_identity")):
        errors.append("branch_identity is invalid")
    if "pull_request_identity" in event and not _is_safe_pull_request_identity(
        event.get("pull_request_identity")
    ):
        errors.append("pull_request_identity is invalid")
    for field_name, allowed in CODEX_PILOT_AUDIT_EVENT_ALLOWED_VALUES.items():
        if field_name in event and event.get(field_name) not in allowed:
            errors.append(f"{field_name} is invalid")


def _attempt_snapshot_structural_errors(snapshot: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    field_set = set(snapshot)
    if CODEX_PILOT_ATTEMPT_SNAPSHOT_FIELDS - field_set:
        errors.append("snapshot is missing required fields")
    if field_set - CODEX_PILOT_ATTEMPT_SNAPSHOT_FIELDS:
        errors.append("snapshot contains unknown fields")
    if snapshot.get("schema_version") != CODEX_PILOT_ATTEMPT_SNAPSHOT_SCHEMA_VERSION:
        errors.append("snapshot schema_version is invalid")
    if not _is_exact_codex_pilot_attempt_id(snapshot.get("attempt_id")):
        errors.append("snapshot attempt_id is invalid")
    if not _is_safe_identifier(snapshot.get("authorization_id")):
        errors.append("snapshot authorization_id is invalid")
    if not _is_lower_hex(snapshot.get("authorization_fingerprint"), 64):
        errors.append("snapshot authorization_fingerprint is invalid")
    if (
        type(snapshot.get("latest_event_sequence")) is not int
        or snapshot.get("latest_event_sequence") < 0
    ):
        errors.append("snapshot latest_event_sequence is invalid")
    if not _is_lower_hex(snapshot.get("latest_event_digest"), 64):
        errors.append("snapshot latest_event_digest is invalid")
    if snapshot.get("current_lifecycle_state") not in CODEX_PILOT_AUDIT_LIFECYCLE_STATES:
        errors.append("snapshot current_lifecycle_state is invalid")
    if type(snapshot.get("terminal")) is not bool:
        errors.append("snapshot terminal must be a JSON boolean")
    if snapshot.get("branch_identity") is not None and not _is_safe_branch(
        snapshot.get("branch_identity")
    ):
        errors.append("snapshot branch_identity is invalid")
    if snapshot.get("pull_request_identity") is not None and not (
        _is_safe_pull_request_identity(snapshot.get("pull_request_identity"))
    ):
        errors.append("snapshot pull_request_identity is invalid")
    if snapshot.get("final_ci_category") is not None and snapshot.get(
        "final_ci_category"
    ) not in CODEX_PILOT_AUDIT_EVENT_ALLOWED_VALUES["final_ci_category"]:
        errors.append("snapshot final_ci_category is invalid")
    if snapshot.get("assistant_review_verdict") is not None and snapshot.get(
        "assistant_review_verdict"
    ) not in CODEX_PILOT_AUDIT_EVENT_ALLOWED_VALUES["assistant_review_verdict"]:
        errors.append("snapshot assistant_review_verdict is invalid")
    for field_name in ["codex_approved", "codex_merged", "authorization_reusable"]:
        if type(snapshot.get(field_name)) is not bool or snapshot.get(field_name) is not False:
            errors.append(f"snapshot {field_name} must be JSON boolean false")
    _validate_attempt_snapshot_invariants(snapshot, errors)
    return sorted(set(errors))


def _validate_attempt_snapshot_invariants(
    snapshot: dict[str, Any],
    errors: list[str],
) -> None:
    state = snapshot.get("current_lifecycle_state")
    sequence = snapshot.get("latest_event_sequence")
    terminal = snapshot.get("terminal")
    if state == "claim_not_started":
        errors.append("snapshot current_lifecycle_state is invalid")
    if state in CODEX_PILOT_ATTEMPT_SNAPSHOT_STATE_SEQUENCES and type(sequence) is int:
        if sequence not in CODEX_PILOT_ATTEMPT_SNAPSHOT_STATE_SEQUENCES[state]:
            errors.append("snapshot state sequence is invalid")
    if (
        state in CODEX_PILOT_AUDIT_LIFECYCLE_STATES
        and type(terminal) is bool
        and terminal != (state in CODEX_PILOT_AUDIT_TERMINAL_STATES)
    ):
        errors.append("snapshot terminal state is invalid")

    branch_present = snapshot.get("branch_identity") is not None
    pr_present = snapshot.get("pull_request_identity") is not None
    ci_present = snapshot.get("final_ci_category") is not None
    review_present = snapshot.get("assistant_review_verdict") is not None
    if state in CODEX_PILOT_ATTEMPT_SNAPSHOT_NO_CONTEXT_STATES:
        if branch_present or pr_present or ci_present or review_present:
            errors.append("snapshot context is invalid")
    elif state == "pr_opened_and_stopped":
        if not branch_present or not pr_present or ci_present or review_present:
            errors.append("snapshot context is invalid")
    elif state == "completed_pending_review":
        if not branch_present or not pr_present or not ci_present or not review_present:
            errors.append("snapshot context is invalid")
    elif state in CODEX_PILOT_AUDIT_LIFECYCLE_STATES:
        errors.append("snapshot current_lifecycle_state is invalid")


def _snapshot_derivation_result(
    *,
    claim_structural_valid: bool,
    event_chain_valid: bool,
    blockers: list[str],
    snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "claim_structural_valid": claim_structural_valid,
        "event_chain_valid": event_chain_valid,
        "snapshot": snapshot,
        "snapshot_derivation_blockers": sorted(set(blockers)),
        "snapshot_derivation_passed": not blockers and snapshot is not None,
    }


def _can_digest_audit_event_record(event: dict[str, Any]) -> bool:
    return (
        "event_digest" in event
        and _is_lower_hex(event.get("event_digest"), 64)
        and not _audit_event_candidate_errors(
            _audit_event_digest_payload_from_record(event)
        )
    )


def _audit_event_digest_payload_from_record(event: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in event.items() if key != "event_digest"}


def _validate_codex_pilot_audit_digest_payload(payload: Any) -> None:
    if _audit_event_digest_payload_errors(payload):
        raise ValueError("audit event digest payload is invalid")


def _audit_event_digest_payload_errors(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["audit event digest payload is invalid"]
    if "event_digest" in payload:
        return ["audit event digest payload is invalid"]
    payload_fields = set(payload)
    required_payload_fields = CODEX_PILOT_AUDIT_EVENT_REQUIRED_FIELDS - {
        "event_digest"
    }
    if required_payload_fields - payload_fields:
        return ["audit event digest payload is invalid"]
    if payload_fields - (CODEX_PILOT_AUDIT_EVENT_FIELDS - {"event_digest"}):
        return ["audit event digest payload is invalid"]
    if _audit_event_candidate_errors(payload):
        return ["audit event digest payload is invalid"]
    for value in payload.values():
        try:
            _validate_audit_digest_value(value)
        except ValueError:
            return ["audit event digest payload is invalid"]
    return []


def _audit_event_candidate_errors(payload: dict[str, Any]) -> list[str]:
    pseudo_event = dict(payload)
    pseudo_event["event_digest"] = "0" * 64
    errors: list[str] = []
    field_set = set(pseudo_event)
    if CODEX_PILOT_AUDIT_EVENT_REQUIRED_FIELDS - field_set:
        errors.append("audit event is missing required fields")
    if field_set - CODEX_PILOT_AUDIT_EVENT_FIELDS:
        errors.append("audit event contains unknown fields")
    _validate_audit_event_core_shape(pseudo_event, errors)
    return sorted(set(errors))


def _validate_audit_digest_value(value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str):
        if not _is_fingerprint_safe_text(value, 500):
            raise ValueError("audit event digest payload is invalid")
    elif isinstance(value, bool):
        return
    elif type(value) is int:
        return
    else:
        raise ValueError("audit event digest payload is invalid")


def _is_safe_pull_request_identity(value: object) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"pr-[1-9][0-9]{0,9}", value) is not None
    )


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
    if not _is_exact_codex_pilot_attempt_id(record.get("attempt_id")):
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
        "/home/",
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
        "/home/",
        "home/",
        "~",
    ]
    return any(marker in lowered for marker in markers)


def _contains_unsafe_identifier_marker(value: str) -> bool:
    lowered = value.lower()
    markers = [
        "://",
        "\\",
        "/",
        ":",
        "=",
        "sk-",
        "token",
        "secret",
        "password",
        "users",
        "home",
        "appdata",
    ]
    return any(marker in lowered for marker in markers)


def _is_safe_identifier(value: object) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 80
        and value not in {".", ".."}
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value) is not None
        and not _contains_unsafe_identifier_marker(value)
    )


def _is_attempt_id(value: object) -> bool:
    return (
        type(value) is str
        and len(value) <= 80
        and re.fullmatch(r"pilot-attempt-[a-z0-9][a-z0-9._-]{11,62}", value)
        is not None
        and not _contains_unsafe_marker(value)
    )


def _is_exact_codex_pilot_attempt_id(value: object) -> bool:
    return type(value) is str and _is_safe_identifier(value) and _is_attempt_id(value)


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
