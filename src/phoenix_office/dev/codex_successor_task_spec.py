"""Compile externally approved successor proposals into reviewed task specs."""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from phoenix_office.dev.codex_package import (
    CODEX_PILOT_TASK_SPEC_CONTROL_IDS,
    CODEX_PILOT_TASK_SPEC_MAX_ISSUE_NUMBER,
    TASK_SPEC_SCHEMA_VERSION,
    CodexPilotPackageBuildError,
    CodexPilotTaskSpec,
    load_codex_pilot_task_spec,
    parse_codex_pilot_task_spec_payload,
    qualify_codex_control_directory,
)
from phoenix_office.dev.codex_successor import (
    REPOSITORY_IDENTITY,
    CodexSuccessorProposalError,
    CodexSuccessorServices,
    SuccessorCandidate,
    SuccessorProposal,
    SystemCodexSuccessorServices,
    _load_json_without_duplicates,
    _require_canonical_repository_state,
    codex_successor_proposal_fingerprint,
    parse_codex_successor_proposal_payload,
    parse_selected_codex_successor_issue,
    resolve_codex_successor_dependency_facts,
)

SUCCESSOR_TASK_SPEC_BUILD_SCHEMA_VERSION: Final = (
    "codex-successor-task-spec-build-result.v1"
)
ARCHITECTURE_APPROVAL_SCHEMA_VERSION: Final = (
    "codex-successor-architecture-approval.v1"
)
ARCHITECTURE_APPROVAL_DECISION: Final = "approved_for_task_spec_compilation"
ARCHITECTURE_APPROVER_ROLE: Final = "assistant_reviewer"

MAX_PROPOSAL_BYTES: Final = 64 * 1024
MAX_APPROVAL_BYTES: Final = 16 * 1024
MAX_TASK_SPEC_OUTPUT_BYTES: Final = 64 * 1024
_SHA_PATTERN: Final = re.compile(r"[0-9a-f]{40}")
_FINGERPRINT_PATTERN: Final = re.compile(r"[0-9a-f]{64}")
_TASK_ID_PATTERN: Final = re.compile(r"TASK-[0-9]{3,6}")
_OUTPUT_NAME_PATTERN: Final = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,110}\.json"
)
_APPROVAL_FIELDS: Final = {
    "approved_at",
    "approver_role",
    "decision",
    "proposal_fingerprint",
    "schema_version",
    "selected_issue_number",
    "selected_task_id",
    "verified_base_sha",
}


class CodexSuccessorTaskSpecError(Exception):
    """Bounded compilation failure safe for public classification."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class ArchitectureApprovalReceipt:
    """External architecture approval bound to one successor proposal."""

    proposal_fingerprint: str
    verified_base_sha: str
    selected_issue_number: int
    selected_task_id: str
    approved_at: str


def build_approved_codex_successor_task_spec(
    *,
    proposal_path: Path,
    architecture_approval_path: Path,
    output_path: Path,
    repository_root: Path,
    services: CodexSuccessorServices | None = None,
) -> dict[str, object]:
    """Compile one exact approved proposal and stop without execution."""

    system = services or SystemCodexSuccessorServices(repository_root)
    try:
        repository = system.canonical_repository_root()
        state = system.repository_state()
        _require_canonical_repository_state(state)
        proposal = _load_successor_proposal(proposal_path)
        if state.head != proposal.verification.base_sha:
            raise CodexSuccessorTaskSpecError("stale_proposal_base_sha")

        current_issue = system.read_issue(proposal.issue_number)
        candidate = parse_selected_codex_successor_issue(
            current_issue,
            repository_root=repository,
            tracked_paths=system.tracked_paths(),
        )
        _require_exact_selected_candidate(proposal, candidate)
        dependency_facts = resolve_codex_successor_dependency_facts(
            candidate,
            system,
        )
        if any(not fact.completed for fact in dependency_facts):
            raise CodexSuccessorTaskSpecError("dependency_not_completed")
        recomputed = codex_successor_proposal_fingerprint(
            verification=proposal.verification,
            candidate=candidate,
            dependency_facts=dependency_facts,
        )
        if recomputed != proposal.fingerprint:
            raise CodexSuccessorTaskSpecError("proposal_fingerprint_mismatch")

        approval = _load_architecture_approval(architecture_approval_path)
        _require_approval_binding(approval, proposal)
        payload = _task_spec_payload(
            proposal=proposal,
            candidate=candidate,
            approval=approval,
        )
        parsed = parse_codex_pilot_task_spec_payload(
            payload,
            required_control_ids=set(CODEX_PILOT_TASK_SPEC_CONTROL_IDS),
        )
        target = _qualify_output_path(output_path, repository)
        _write_and_round_trip_task_spec(target, payload, parsed)
        return _successful_result(proposal=proposal)
    except CodexSuccessorTaskSpecError:
        raise
    except CodexSuccessorProposalError as exc:
        raise CodexSuccessorTaskSpecError(exc.category) from exc
    except CodexPilotPackageBuildError as exc:
        raise CodexSuccessorTaskSpecError(exc.category) from exc
    except Exception as exc:
        raise CodexSuccessorTaskSpecError("task_spec_compilation_failed") from exc


def blocked_codex_successor_task_spec_result(category: str) -> dict[str, object]:
    """Return a bounded fail-closed compiler result."""

    return {
        "schema_version": SUCCESSOR_TASK_SPEC_BUILD_SCHEMA_VERSION,
        "status": "blocked",
        "category": category,
        "verified_base_sha": None,
        "selected_issue_number": None,
        "selected_task_id": None,
        "proposal_fingerprint": None,
        "architecture_approval_validated": False,
        "task_spec_validated": False,
        "task_spec_written": False,
        "output_path_exposed": False,
        "authorization_created": False,
        "claim_created": False,
        "package_builder_invoked": False,
        "reviewed_runner_invoked": False,
        "codex_invoked": False,
        "github_mutation_used": False,
        "retry_used": False,
        "background_resume_used": False,
    }


def _load_successor_proposal(path: Path) -> SuccessorProposal:
    payload = _load_bounded_json(
        path,
        maximum_bytes=MAX_PROPOSAL_BYTES,
        unavailable_category="proposal_unavailable",
        malformed_category="malformed_proposal",
    )
    return parse_codex_successor_proposal_payload(payload)


def _load_architecture_approval(path: Path) -> ArchitectureApprovalReceipt:
    value = _load_bounded_json(
        path,
        maximum_bytes=MAX_APPROVAL_BYTES,
        unavailable_category="approval_receipt_unavailable",
        malformed_category="malformed_approval_receipt",
    )
    if not isinstance(value, dict) or set(value) != _APPROVAL_FIELDS:
        raise CodexSuccessorTaskSpecError("malformed_approval_receipt")
    if value.get("schema_version") != ARCHITECTURE_APPROVAL_SCHEMA_VERSION:
        raise CodexSuccessorTaskSpecError("malformed_approval_receipt")
    if value.get("decision") != ARCHITECTURE_APPROVAL_DECISION:
        raise CodexSuccessorTaskSpecError("approval_not_approved")
    if value.get("approver_role") != ARCHITECTURE_APPROVER_ROLE:
        raise CodexSuccessorTaskSpecError("disallowed_approver_role")
    fingerprint = value.get("proposal_fingerprint")
    base_sha = value.get("verified_base_sha")
    issue_number = value.get("selected_issue_number")
    task_id = value.get("selected_task_id")
    approved_at = value.get("approved_at")
    if (
        not isinstance(fingerprint, str)
        or _FINGERPRINT_PATTERN.fullmatch(fingerprint) is None
        or not isinstance(base_sha, str)
        or _SHA_PATTERN.fullmatch(base_sha) is None
        or type(issue_number) is not int
        or not 1
        <= issue_number
        <= CODEX_PILOT_TASK_SPEC_MAX_ISSUE_NUMBER
        or not isinstance(task_id, str)
        or _TASK_ID_PATTERN.fullmatch(task_id) is None
        or not _canonical_utc_timestamp(approved_at)
    ):
        raise CodexSuccessorTaskSpecError("malformed_approval_receipt")
    return ArchitectureApprovalReceipt(
        proposal_fingerprint=fingerprint,
        verified_base_sha=base_sha,
        selected_issue_number=issue_number,
        selected_task_id=task_id,
        approved_at=str(approved_at),
    )


def _load_bounded_json(
    path: Path,
    *,
    maximum_bytes: int,
    unavailable_category: str,
    malformed_category: str,
) -> object:
    try:
        details = path.lstat()
    except OSError as exc:
        raise CodexSuccessorTaskSpecError(unavailable_category) from exc
    if (
        not stat.S_ISREG(details.st_mode)
        or _is_link_or_reparse(details)
        or not 1 <= details.st_size <= maximum_bytes
    ):
        raise CodexSuccessorTaskSpecError(unavailable_category)
    try:
        return _load_json_without_duplicates(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise CodexSuccessorTaskSpecError(malformed_category) from exc


def _require_exact_selected_candidate(
    proposal: SuccessorProposal,
    candidate: SuccessorCandidate,
) -> None:
    execution = candidate.execution_definition
    if execution is None or (
        candidate.issue_number != proposal.issue_number
        or candidate.title != proposal.title
        or candidate.task_id != proposal.task_id
        or candidate.priority != proposal.priority
        or candidate.risk_class != proposal.risk_class
        or candidate.execution_class != proposal.execution_class
        or candidate.allowed_paths != proposal.allowed_paths
        or candidate.expected_pr_title != proposal.expected_pr_title
        or execution.to_payload() != proposal.execution_definition.to_payload()
    ):
        raise CodexSuccessorTaskSpecError("selected_issue_changed")


def _require_approval_binding(
    approval: ArchitectureApprovalReceipt,
    proposal: SuccessorProposal,
) -> None:
    if (
        approval.proposal_fingerprint != proposal.fingerprint
        or approval.verified_base_sha != proposal.verification.base_sha
        or approval.selected_issue_number != proposal.issue_number
        or approval.selected_task_id != proposal.task_id
    ):
        raise CodexSuccessorTaskSpecError("approval_binding_mismatch")


def _task_spec_payload(
    *,
    proposal: SuccessorProposal,
    candidate: SuccessorCandidate,
    approval: ArchitectureApprovalReceipt,
) -> dict[str, Any]:
    execution = candidate.execution_definition
    if execution is None:
        raise CodexSuccessorTaskSpecError("missing_execution_definition")
    return {
        "acceptance_criteria": list(execution.acceptance_criteria),
        "allowed_paths": list(candidate.allowed_paths),
        "base_commit_sha": proposal.verification.base_sha,
        "branch_name": execution.branch_name,
        "budget_ceiling": execution.budget_ceiling,
        "constraints": list(execution.constraints),
        "control_references": dict(sorted(execution.control_references.items())),
        "expected_pr_title": candidate.expected_pr_title,
        "handoff_id": f"pilot-handoff-{proposal.fingerprint}",
        "issue_number": candidate.issue_number,
        "objective": execution.objective,
        "repository": REPOSITORY_IDENTITY,
        "reviewed_at": approval.approved_at,
        "schema_version": TASK_SPEC_SCHEMA_VERSION,
        "task_id": candidate.task_id,
        "timeout_seconds": execution.timeout_seconds,
        "title": candidate.title,
    }


def _qualify_output_path(path: Path, repository: Path) -> Path:
    if _OUTPUT_NAME_PATTERN.fullmatch(path.name) is None:
        raise CodexSuccessorTaskSpecError("unsafe_output_path")
    control_directory = qualify_codex_control_directory(path.parent, repository)
    target = control_directory / path.name
    try:
        resolved = target.resolve(strict=False)
    except OSError as exc:
        raise CodexSuccessorTaskSpecError("unsafe_output_path") from exc
    if resolved.parent != control_directory:
        raise CodexSuccessorTaskSpecError("unsafe_output_path")
    if target.exists() or target.is_symlink():
        try:
            details = target.lstat()
        except OSError as exc:
            raise CodexSuccessorTaskSpecError("unsafe_output_path") from exc
        if _is_link_or_reparse(details):
            raise CodexSuccessorTaskSpecError("output_symlink_rejected")
        raise CodexSuccessorTaskSpecError("output_collision")
    return resolved


def _write_and_round_trip_task_spec(
    target: Path,
    payload: dict[str, Any],
    parsed: CodexPilotTaskSpec,
) -> None:
    created = False
    complete = False
    try:
        encoded = (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        if not 1 <= len(encoded) <= MAX_TASK_SPEC_OUTPUT_BYTES:
            raise CodexSuccessorTaskSpecError("serialization_uncertainty")
        if _load_json_without_duplicates(encoded.decode("utf-8")) != payload:
            raise CodexSuccessorTaskSpecError("serialization_uncertainty")
        with target.open("xb") as stream:
            created = True
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        round_tripped = load_codex_pilot_task_spec(
            target,
            required_control_ids=set(CODEX_PILOT_TASK_SPEC_CONTROL_IDS),
        )
        if round_tripped != parsed or target.read_bytes() != encoded:
            raise CodexSuccessorTaskSpecError("serialization_uncertainty")
        complete = True
    except FileExistsError as exc:
        raise CodexSuccessorTaskSpecError("output_collision") from exc
    except CodexSuccessorTaskSpecError:
        raise
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        raise CodexSuccessorTaskSpecError("serialization_uncertainty") from exc
    finally:
        if created and not complete:
            try:
                target.unlink(missing_ok=True)
            except OSError as exc:
                raise CodexSuccessorTaskSpecError("output_cleanup_uncertain") from exc


def _successful_result(
    *,
    proposal: SuccessorProposal,
) -> dict[str, object]:
    return {
        "schema_version": SUCCESSOR_TASK_SPEC_BUILD_SCHEMA_VERSION,
        "status": "success",
        "category": "task_spec_compiled",
        "verified_base_sha": proposal.verification.base_sha,
        "selected_issue_number": proposal.issue_number,
        "selected_task_id": proposal.task_id,
        "proposal_fingerprint": proposal.fingerprint,
        "architecture_approval_validated": True,
        "task_spec_validated": True,
        "task_spec_written": True,
        "output_path_exposed": False,
        "authorization_created": False,
        "claim_created": False,
        "package_builder_invoked": False,
        "reviewed_runner_invoked": False,
        "codex_invoked": False,
        "github_mutation_used": False,
        "retry_used": False,
        "background_resume_used": False,
    }


def _canonical_utc_timestamp(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 20 or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        return False
    return bool(
        parsed.tzinfo is not None
        and parsed.utcoffset() == UTC.utcoffset(parsed)
        and parsed.isoformat(timespec="seconds").replace("+00:00", "Z") == value
    )


def _is_link_or_reparse(details: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(details.st_mode) or bool(
        getattr(details, "st_file_attributes", 0) & reparse_flag
    )
