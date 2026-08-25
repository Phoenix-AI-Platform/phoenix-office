"""One-shot composition of reviewed task specs and the supervised runner."""

from __future__ import annotations

import stat
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from phoenix_office.dev.codex_package import (
    AUTHORIZATION_FILENAME,
    EVIDENCE_FILENAME,
    HANDOFF_FILENAME,
    CodexPilotPackageBuildError,
    CodexPilotPackageInspection,
    build_codex_pilot_package,
    load_codex_pilot_task_spec,
    qualify_codex_control_directory,
    qualify_codex_new_claim_store_path,
    qualify_codex_repository_root,
)

REVIEWED_EXECUTION_SCHEMA_VERSION: Final = (
    "codex-pilot-reviewed-execution-result.v1"
)
PACKAGE_DIRECTORY_NAME: Final = "package"
GIT_INSPECTION_TIMEOUT_SECONDS: Final = 10

_TERMINAL_LIFECYCLE_STATES: Final = {
    "aborted",
    "cancelled",
    "completed_pending_review",
    "failed",
    "timed_out",
}


@dataclass(frozen=True, slots=True)
class ReviewedRunnerOutcome:
    """Bounded runner outcome plus independently verified lifecycle facts."""

    result: Mapping[str, object]
    execution_backend_selected: str | None = None
    durable_lifecycle_state: str | None = None
    durable_lifecycle_terminal: bool = False


PackageBuilder = Callable[..., dict[str, Any]]
PackageInspector = Callable[[Path, Path, Path], CodexPilotPackageInspection]
RunnerInvoker = Callable[[Path, Path, Path, Path], ReviewedRunnerOutcome]


def execute_reviewed_codex_task(
    *,
    task_spec_path: Path,
    control_root: Path,
    claim_store_path: Path,
    repository_root: Path,
    evidence_control_reviewers: Mapping[str, str],
    package_inspector: PackageInspector,
    runner_invoker: RunnerInvoker,
    package_builder: PackageBuilder = build_codex_pilot_package,
) -> dict[str, object]:
    """Build one reviewed package and invoke the existing runner at most once."""

    task_id: str | None = None
    issue_number: int | None = None
    package_result: dict[str, Any] | None = None
    try:
        repository = qualify_codex_repository_root(repository_root)
        spec = load_codex_pilot_task_spec(
            task_spec_path,
            required_control_ids=set(evidence_control_reviewers),
        )
        task_id = spec.task_id
        issue_number = spec.issue_number
        _require_exact_clean_main(repository, spec.base_commit_sha)
        qualified_control_root = qualify_codex_control_directory(
            control_root,
            repository,
        )
        qualified_claim_store = qualify_codex_new_claim_store_path(
            claim_store_path,
            repository,
        )
        package_root = qualified_control_root / PACKAGE_DIRECTORY_NAME
        package_result = package_builder(
            task_spec_path=task_spec_path,
            output_dir=package_root,
            repository_root=repository,
            evidence_control_reviewers=evidence_control_reviewers,
            inspector=package_inspector,
        )
        if package_result.get("package_build_result") != "pass":
            return _blocked_result(
                str(package_result.get("category") or "package_build_failed"),
                task_id=task_id,
                issue_number=issue_number,
                package_result=package_result,
            )
        if package_result.get("preclaim_ready") is not True:
            return _blocked_result(
                "package_not_preclaim_ready",
                task_id=task_id,
                issue_number=issue_number,
                package_result=package_result,
            )

        handoff_path = _require_generated_artifact(
            package_root,
            HANDOFF_FILENAME,
        )
        evidence_path = _require_generated_artifact(
            package_root,
            EVIDENCE_FILENAME,
        )
        authorization_path = _require_generated_artifact(
            package_root,
            AUTHORIZATION_FILENAME,
        )
        runner_outcome = runner_invoker(
            handoff_path,
            evidence_path,
            authorization_path,
            qualified_claim_store,
        )
    except CodexPilotPackageBuildError as exc:
        return _blocked_result(
            exc.category,
            task_id=task_id,
            issue_number=issue_number,
            package_result=package_result,
        )
    except Exception:
        return _blocked_result(
            "reviewed_execution_internal_failure",
            task_id=task_id,
            issue_number=issue_number,
            package_result=package_result,
        )

    return _combined_result(
        task_id=task_id,
        issue_number=issue_number,
        package_result=package_result,
        runner_outcome=runner_outcome,
    )


def blocked_reviewed_execution_result(category: str) -> dict[str, object]:
    """Return the bounded public preclaim failure shape."""

    return _blocked_result(category)


def _require_exact_clean_main(repository: Path, expected_sha: str) -> None:
    branch = _git_output(repository, "branch", "--show-current")
    if branch != "main":
        raise CodexPilotPackageBuildError("noncanonical_base_branch")
    status = _git_output(repository, "status", "--porcelain=v1")
    if status:
        raise CodexPilotPackageBuildError("dirty_worktree")
    head = _git_output(repository, "rev-parse", "HEAD")
    if head != expected_sha:
        raise CodexPilotPackageBuildError("stale_base_commit")


def _git_output(repository: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), *args],
            capture_output=True,
            check=False,
            shell=False,
            text=True,
            timeout=GIT_INSPECTION_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CodexPilotPackageBuildError("git_inspection_failed") from exc
    if completed.returncode != 0:
        raise CodexPilotPackageBuildError("git_inspection_failed")
    return completed.stdout.strip()


def _require_generated_artifact(package_root: Path, filename: str) -> Path:
    expected = package_root / filename
    try:
        resolved_root = package_root.resolve(strict=True)
        resolved = expected.resolve(strict=True)
        root_details = package_root.lstat()
        details = expected.lstat()
    except OSError as exc:
        raise CodexPilotPackageBuildError("generated_package_unavailable") from exc
    if (
        resolved.parent != resolved_root
        or _is_link_or_reparse(root_details)
        or not expected.is_file()
        or not stat.S_ISREG(details.st_mode)
        or _is_link_or_reparse(details)
    ):
        raise CodexPilotPackageBuildError("generated_package_unavailable")
    return resolved


def _is_link_or_reparse(details: object) -> bool:
    mode = getattr(details, "st_mode", 0)
    attributes = getattr(details, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(mode) or bool(attributes & reparse_flag)


def _blocked_result(
    category: str,
    *,
    task_id: str | None = None,
    issue_number: int | None = None,
    package_result: Mapping[str, object] | None = None,
) -> dict[str, object]:
    package = package_result or {}
    return {
        "schema_version": REVIEWED_EXECUTION_SCHEMA_VERSION,
        "task_id": task_id,
        "issue_number": issue_number,
        "status": "blocked",
        "category": category,
        "package_build_result": package.get("package_build_result", "blocked"),
        "preclaim_ready": bool(package.get("preclaim_ready", False)),
        "authorization_id": package.get("authorization_id"),
        "authorization_fingerprint": package.get("authorization_fingerprint"),
        "claim_created": False,
        "authorization_consumed": False,
        "attempt_id": None,
        "runner_invoked": False,
        "execution_backend_selected": None,
        "changed_paths": [],
        "observed_usage_tokens": None,
        "authorized_budget_tokens": None,
        "usage_overage_tokens": None,
        "usage_ratio_basis_points": None,
        "usage_category": "usage_unknown",
        "phoenix_validation_result": None,
        "durable_lifecycle_state": None,
        "durable_lifecycle_terminal": False,
        "pr_created_by_runner": False,
        "office_pr": None,
        "office_pr_head": None,
        "auto_retry_used": False,
        "replacement_authorization_created": False,
        "background_resume_used": False,
        "worker_may_merge": False,
        "pr_merged": False,
    }


def _combined_result(
    *,
    task_id: str,
    issue_number: int,
    package_result: Mapping[str, object],
    runner_outcome: ReviewedRunnerOutcome,
) -> dict[str, object]:
    runner = runner_outcome.result
    attempt_id = _bounded_optional_text(runner.get("attempt_id"))
    pull_request = _bounded_optional_text(runner.get("pull_request_identity"))
    category = _bounded_optional_text(runner.get("category")) or "runner_result_invalid"
    status = _bounded_optional_text(runner.get("status")) or "failed"
    changed_paths = _bounded_changed_paths(runner.get("changed_paths"))
    lifecycle_state = _bounded_optional_text(
        runner_outcome.durable_lifecycle_state
    )
    lifecycle_terminal = bool(
        runner_outcome.durable_lifecycle_terminal
        and lifecycle_state in _TERMINAL_LIFECYCLE_STATES
    )
    pr_created = pull_request is not None
    if attempt_id is not None and not lifecycle_terminal:
        status = "failed"
        category = "lifecycle_storage_uncertain"
    return {
        "schema_version": REVIEWED_EXECUTION_SCHEMA_VERSION,
        "task_id": task_id,
        "issue_number": issue_number,
        "status": status,
        "category": category,
        "package_build_result": package_result.get("package_build_result"),
        "preclaim_ready": package_result.get("preclaim_ready") is True,
        "authorization_id": package_result.get("authorization_id"),
        "authorization_fingerprint": package_result.get(
            "authorization_fingerprint"
        ),
        "claim_created": attempt_id is not None,
        "authorization_consumed": attempt_id is not None,
        "attempt_id": attempt_id,
        "runner_invoked": True,
        "execution_backend_selected": _bounded_optional_text(
            runner_outcome.execution_backend_selected
        ),
        "changed_paths": changed_paths,
        "observed_usage_tokens": _bounded_optional_integer(
            runner.get("observed_usage_tokens")
        ),
        "authorized_budget_tokens": _bounded_optional_integer(
            runner.get("authorized_budget_tokens")
        ),
        "usage_overage_tokens": _bounded_optional_integer(
            runner.get("usage_overage_tokens")
        ),
        "usage_ratio_basis_points": _bounded_optional_integer(
            runner.get("usage_ratio_basis_points")
        ),
        "usage_category": _bounded_optional_text(runner.get("usage_category"))
        or "usage_unknown",
        "phoenix_validation_result": _validation_result(runner),
        "durable_lifecycle_state": lifecycle_state,
        "durable_lifecycle_terminal": lifecycle_terminal,
        "pr_created_by_runner": pr_created,
        "office_pr": pull_request,
        "office_pr_head": None,
        "auto_retry_used": False,
        "replacement_authorization_created": False,
        "background_resume_used": False,
        "worker_may_merge": False,
        "pr_merged": False,
    }


def _validation_result(runner: Mapping[str, object]) -> str | None:
    category = runner.get("category")
    if category == "pr_opened_and_stopped":
        return "pass"
    if isinstance(category, str) and "validation" in category:
        return "fail"
    command_categories = runner.get("validation_categories")
    if (
        isinstance(command_categories, (list, tuple))
        and command_categories
        and all(item == "passed" for item in command_categories)
    ):
        return "pass"
    return None


def _bounded_changed_paths(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)) or len(value) > 20:
        return []
    paths: list[str] = []
    for item in value:
        if (
            not isinstance(item, str)
            or not 1 <= len(item) <= 260
            or item.startswith(("/", "\\"))
            or ":" in item
            or ".." in Path(item).parts
        ):
            return []
        paths.append(item)
    return paths


def _bounded_optional_text(value: object) -> str | None:
    if not isinstance(value, str) or not 1 <= len(value) <= 200:
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return None
    if "\\" in value or value.startswith("/"):
        return None
    return value


def _bounded_optional_integer(value: object) -> int | None:
    if type(value) is not int or not 0 <= value <= 10**9:
        return None
    return value
