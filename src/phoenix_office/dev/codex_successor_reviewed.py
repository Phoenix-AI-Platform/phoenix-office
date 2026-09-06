"""Execute one externally approved successor through existing reviewed boundaries."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Final

from phoenix_office.dev.codex_reviewed import (
    REVIEWED_EXECUTION_SCHEMA_VERSION,
    PackageInspector,
    RunnerInvoker,
    blocked_reviewed_execution_result,
    execute_reviewed_codex_task,
)
from phoenix_office.dev.codex_successor import (
    CodexSuccessorServices,
    SystemCodexSuccessorServices,
)
from phoenix_office.dev.codex_successor_task_spec import (
    CodexSuccessorTaskSpecError,
    build_approved_codex_successor_task_spec,
)

SUCCESSOR_REVIEWED_EXECUTION_SCHEMA_VERSION: Final = (
    "codex-successor-reviewed-execution-result.v1"
)
SUCCESSOR_TASK_SPEC_FILENAME: Final = "task-spec.json"
CYCLE_ADVANCEMENT_SCHEMA_VERSION: Final = (
    "codex-reviewed-cycle-advancement-evidence.v1"
)
_CATEGORY_PATTERN: Final = re.compile(r"[a-z][a-z0-9_]{0,79}")
_PR_IDENTITY_PATTERN: Final = re.compile(r"pr-[1-9][0-9]{0,9}")
_COMMIT_SHA_PATTERN: Final = re.compile(r"[0-9a-f]{40}")
_CYCLE_STATES: Final = {
    "approved_unmerged": "awaiting_external_merge",
    "changes_requested": "revision_required",
    "closed_unmerged": "closed_without_merge",
    "merged": "merged_complete",
}
_ADVANCEMENT_FIELDS: Final = {
    "cycle_state",
    "next_base_sha",
    "successor_eligible",
    "successor_selected",
    "successor_execution_started",
}

TaskSpecBuilder = Callable[..., dict[str, object]]
ReviewedExecutor = Callable[..., dict[str, object]]


class ReviewedCycleAdvancementError(ValueError):
    """Disposition evidence cannot be advanced safely."""


def reviewed_cycle_advancement_evidence(
    reviewed_result: Mapping[str, object],
) -> dict[str, object]:
    """Classify one explicit external disposition without external operations."""

    if (
        not isinstance(reviewed_result, Mapping)
        or len(reviewed_result) > 100
        or reviewed_result.get("schema_version") != REVIEWED_EXECUTION_SCHEMA_VERSION
        or reviewed_result.get("pr_created_by_runner") is not True
        or reviewed_result.get("worker_may_merge") is not False
        or any(field in reviewed_result for field in _ADVANCEMENT_FIELDS)
        or "external_pr_disposition" not in reviewed_result
        or "external_merge_commit_sha" not in reviewed_result
    ):
        raise ReviewedCycleAdvancementError("reviewed_cycle_input_invalid")

    office_pr = reviewed_result.get("office_pr")
    office_pr_head = reviewed_result.get("office_pr_head")
    disposition = reviewed_result.get("external_pr_disposition")
    merge_commit_sha = reviewed_result.get("external_merge_commit_sha")
    if not _is_pr_identity(office_pr):
        raise ReviewedCycleAdvancementError("pull_request_identity_invalid")
    if not _is_commit_sha(office_pr_head):
        raise ReviewedCycleAdvancementError("pull_request_head_invalid")
    if not isinstance(disposition, str) or disposition not in _CYCLE_STATES:
        raise ReviewedCycleAdvancementError("external_pr_disposition_invalid")

    merged = disposition == "merged"
    if reviewed_result.get("pr_merged") is not merged:
        raise ReviewedCycleAdvancementError("external_pr_disposition_contradictory")
    if merged:
        if not _is_commit_sha(merge_commit_sha):
            raise ReviewedCycleAdvancementError("merge_commit_sha_invalid")
    elif merge_commit_sha is not None:
        raise ReviewedCycleAdvancementError("external_pr_disposition_contradictory")

    return {
        "schema_version": CYCLE_ADVANCEMENT_SCHEMA_VERSION,
        "status": "success",
        "category": "reviewed_cycle_advanced",
        "cycle_state": _CYCLE_STATES[disposition],
        "office_pr": office_pr,
        "office_pr_head": office_pr_head,
        "external_pr_disposition": disposition,
        "external_merge_commit_sha": merge_commit_sha,
        "next_base_sha": merge_commit_sha if merged else None,
        "successor_eligible": merged,
        "successor_selected": False,
        "architecture_approval_created": False,
        "successor_execution_started": False,
        "worker_may_approve": False,
        "worker_may_merge": False,
    }


def _is_pr_identity(value: object) -> bool:
    return isinstance(value, str) and _PR_IDENTITY_PATTERN.fullmatch(value) is not None


def _is_commit_sha(value: object) -> bool:
    return isinstance(value, str) and _COMMIT_SHA_PATTERN.fullmatch(value) is not None


def execute_approved_codex_successor(
    *,
    proposal_path: Path,
    architecture_approval_path: Path,
    control_root: Path,
    claim_store_path: Path,
    repository_root: Path,
    evidence_control_reviewers: Mapping[str, str],
    package_inspector: PackageInspector,
    runner_invoker: RunnerInvoker,
    services: CodexSuccessorServices | None = None,
    task_spec_builder: TaskSpecBuilder = build_approved_codex_successor_task_spec,
    reviewed_executor: ReviewedExecutor = execute_reviewed_codex_task,
) -> dict[str, object]:
    """Compile and execute one exact approved successor at most once."""

    compiler_result: Mapping[str, object] | None = None
    task_spec_path = control_root / SUCCESSOR_TASK_SPEC_FILENAME
    try:
        compiler_result = task_spec_builder(
            proposal_path=proposal_path,
            architecture_approval_path=architecture_approval_path,
            output_path=task_spec_path,
            repository_root=repository_root,
            services=(
                services
                if services is not None
                else SystemCodexSuccessorServices(repository_root)
            ),
        )
    except CodexSuccessorTaskSpecError as exc:
        return blocked_approved_codex_successor_execution_result(exc.category)
    except Exception:
        return blocked_approved_codex_successor_execution_result(
            "task_spec_compiler_internal_failure"
        )

    if not _compiler_succeeded(compiler_result):
        return blocked_approved_codex_successor_execution_result(
            _bounded_category(compiler_result.get("category"))
            or "task_spec_compilation_failed",
            compiler_result=compiler_result,
        )

    try:
        reviewed_result = reviewed_executor(
            task_spec_path=task_spec_path,
            control_root=control_root,
            claim_store_path=claim_store_path,
            repository_root=repository_root,
            evidence_control_reviewers=evidence_control_reviewers,
            package_inspector=package_inspector,
            runner_invoker=runner_invoker,
        )
    except Exception:
        return blocked_approved_codex_successor_execution_result(
            "reviewed_execution_internal_failure",
            compiler_result=compiler_result,
        )
    return _combined_result(compiler_result, reviewed_result)


def blocked_approved_codex_successor_execution_result(
    category: str,
    *,
    compiler_result: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Return the bounded fail-closed composition result."""

    bounded_category = _bounded_category(category) or "successor_execution_blocked"
    return _combined_result(
        compiler_result or {},
        blocked_reviewed_execution_result(bounded_category),
    )


def _compiler_succeeded(result: Mapping[str, object]) -> bool:
    return bool(
        result.get("status") == "success"
        and result.get("category") == "task_spec_compiled"
        and result.get("architecture_approval_validated") is True
        and result.get("task_spec_validated") is True
        and result.get("task_spec_written") is True
    )


def _combined_result(
    compiler: Mapping[str, object],
    reviewed: Mapping[str, object],
) -> dict[str, object]:
    category = _bounded_category(reviewed.get("category")) or "runner_result_invalid"
    status = reviewed.get("status")
    if status not in {"blocked", "cancelled", "failed", "success", "timed_out"}:
        status = "failed"
        category = "runner_result_invalid"
    return {
        "schema_version": SUCCESSOR_REVIEWED_EXECUTION_SCHEMA_VERSION,
        "status": status,
        "category": category,
        "verified_base_sha": compiler.get("verified_base_sha"),
        "selected_issue_number": compiler.get("selected_issue_number"),
        "selected_task_id": compiler.get("selected_task_id"),
        "proposal_fingerprint": compiler.get("proposal_fingerprint"),
        "architecture_approval_validated": bool(
            compiler.get("architecture_approval_validated", False)
        ),
        "task_spec_validated": bool(compiler.get("task_spec_validated", False)),
        "task_spec_written": bool(compiler.get("task_spec_written", False)),
        "package_build_result": reviewed.get("package_build_result", "blocked"),
        "preclaim_ready": bool(reviewed.get("preclaim_ready", False)),
        "authorization_id": reviewed.get("authorization_id"),
        "authorization_fingerprint": reviewed.get("authorization_fingerprint"),
        "runner_invoked": bool(reviewed.get("runner_invoked", False)),
        "claim_created": bool(reviewed.get("claim_created", False)),
        "authorization_consumed": bool(
            reviewed.get("authorization_consumed", False)
        ),
        "attempt_id": reviewed.get("attempt_id"),
        "execution_backend_selected": reviewed.get("execution_backend_selected"),
        "changed_paths": reviewed.get("changed_paths", []),
        "observed_usage_tokens": reviewed.get("observed_usage_tokens"),
        "input_tokens": reviewed.get("input_tokens"),
        "cached_input_tokens": reviewed.get("cached_input_tokens"),
        "output_tokens": reviewed.get("output_tokens"),
        "reasoning_output_tokens": reviewed.get("reasoning_output_tokens"),
        "authorized_budget_tokens": reviewed.get("authorized_budget_tokens"),
        "usage_overage_tokens": reviewed.get("usage_overage_tokens"),
        "usage_ratio_basis_points": reviewed.get("usage_ratio_basis_points"),
        "usage_category": reviewed.get("usage_category", "usage_unknown"),
        "phoenix_validation_result": reviewed.get("phoenix_validation_result"),
        "durable_lifecycle_state": reviewed.get("durable_lifecycle_state"),
        "durable_lifecycle_terminal": bool(
            reviewed.get("durable_lifecycle_terminal", False)
        ),
        "pr_created_by_runner": bool(reviewed.get("pr_created_by_runner", False)),
        "office_pr": reviewed.get("office_pr"),
        "office_pr_head": reviewed.get("office_pr_head"),
        "architecture_approval_created": False,
        "successor_reselected": False,
        "auto_retry_used": bool(reviewed.get("auto_retry_used", False)),
        "replacement_authorization_created": bool(
            reviewed.get("replacement_authorization_created", False)
        ),
        "background_resume_used": bool(
            reviewed.get("background_resume_used", False)
        ),
        "worker_may_approve": False,
        "worker_may_merge": bool(reviewed.get("worker_may_merge", False)),
        "pr_merged": bool(reviewed.get("pr_merged", False)),
    }


def _bounded_category(value: object) -> str | None:
    if isinstance(value, str) and _CATEGORY_PATTERN.fullmatch(value) is not None:
        return value
    return None
