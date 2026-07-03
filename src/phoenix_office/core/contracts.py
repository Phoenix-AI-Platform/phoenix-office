"""Early Phoenix Core contract skeletons.

These dataclasses mirror the Markdown sketches in
``docs/architecture/contracts.md``. They are intentionally simple,
serializable contract shapes only. They do not implement orchestration,
worker execution, plugin runtime behavior, approval policy, or persistence.
"""

from __future__ import annotations

import json
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
    HUMAN_OPERATOR_AND_ASSISTANT_REVIEWER = "human_operator_and_assistant_reviewer"


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
