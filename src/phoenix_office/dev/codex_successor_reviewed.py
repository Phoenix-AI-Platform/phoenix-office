"""Execute one externally approved successor through existing reviewed boundaries."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Final

from phoenix_office.dev.codex_reviewed import (
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
_CATEGORY_PATTERN: Final = re.compile(r"[a-z][a-z0-9_]{0,79}")

TaskSpecBuilder = Callable[..., dict[str, object]]
ReviewedExecutor = Callable[..., dict[str, object]]


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
