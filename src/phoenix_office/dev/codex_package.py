"""Deterministic supervised-Codex package generation without execution authority."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from phoenix_office.core import (
    CODEX_PILOT_REQUIRED_VALIDATION_COMMANDS,
    ApprovalPolicy,
    CodexHandoffPackage,
    CodexPilotAuthorizationPacket,
    CodexPilotEvidenceControl,
    CodexPilotEvidencePackage,
    CodexPilotEvidenceReviewerRole,
    CodexPilotEvidenceStatus,
    EvidenceType,
    Requester,
    RequesterType,
    SourceKind,
    TaskEnvelope,
    TaskPermissions,
    TaskPriority,
    TaskSource,
    TaskStatus,
    VerificationPlan,
    codex_pilot_authorization_structural_errors,
)

PACKAGE_BUILD_SCHEMA_VERSION = "codex-pilot-package-build-result.v1"
TASK_SPEC_SCHEMA_VERSION = "codex-pilot-task-spec.v1"
HANDOFF_FILENAME = "handoff.json"
EVIDENCE_FILENAME = "evidence.json"
AUTHORIZATION_FILENAME = "authorization.json"
PACKAGE_FILENAMES = (
    HANDOFF_FILENAME,
    EVIDENCE_FILENAME,
    AUTHORIZATION_FILENAME,
)
REPOSITORY = "Phoenix-AI-Platform/phoenix-office"
PILOT_KIND = "docs-only-supervised"
REQUIRED_PR_BODY_HEADINGS = (
    "Summary",
    "Scope",
    "Changed files",
    "Out-of-scope confirmation",
    "Validation performed",
    "Risks",
)
TASK_SPEC_FIELDS = {
    "acceptance_criteria",
    "allowed_paths",
    "base_commit_sha",
    "branch_name",
    "budget_ceiling",
    "constraints",
    "control_references",
    "expected_pr_title",
    "handoff_id",
    "issue_number",
    "objective",
    "repository",
    "reviewed_at",
    "schema_version",
    "task_id",
    "timeout_seconds",
    "title",
}
REFERENCE_FIELD_BY_CONTROL = {
    "authentication_runner_access": "authentication_runner_ref",
    "per_run_budget_ceiling": "budget_enforcement_ref",
    "operator_cancellation_timeout": "cancellation_ref",
    "github_branch_creation_permission": "branch_permission_ref",
    "github_pr_creation_permission": "pr_permission_ref",
    "codex_cannot_approve_or_merge": "codex_no_approve_merge_ref",
    "duplicate_active_pr_detection": "duplicate_pr_check_ref",
    "branch_collision_detection": "branch_collision_check_ref",
}
MAX_TASK_SPEC_BYTES = 64 * 1024
MAX_NARRATIVE_ITEMS = 20
GIT_TIMEOUT_SECONDS = 10
DATABASE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}


class CodexPilotPackageBuildError(Exception):
    """Bounded package-build failure safe for public classification."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class CodexPilotTaskSpec:
    """Reviewed, bounded source needed to compose the existing v1 artifacts."""

    task_id: str
    handoff_id: str
    issue_number: int
    title: str
    objective: str
    repository: str
    base_commit_sha: str
    allowed_paths: tuple[str, ...]
    expected_pr_title: str
    branch_name: str
    budget_ceiling: int
    timeout_seconds: int
    control_references: Mapping[str, str]
    reviewed_at: datetime
    constraints: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CodexPilotPackageInspection:
    """Results from the actual merged static inspection boundaries."""

    composite_preflight_passed: bool
    authorization_structural_valid: bool
    authorization_binding_passed: bool
    authorization_fingerprint_valid: bool
    authorization_fingerprint: str | None


PackageInspector = Callable[
    [Path, Path, Path], CodexPilotPackageInspection
]
AuthorizationIdFactory = Callable[[int], str]


def build_codex_pilot_package(
    *,
    task_spec_path: Path,
    output_dir: Path,
    repository_root: Path,
    evidence_control_reviewers: Mapping[str, str],
    inspector: PackageInspector,
    authorization_id_factory: AuthorizationIdFactory | None = None,
) -> dict[str, Any]:
    """Generate, inspect, and atomically publish one preclaim package."""

    repository = _qualified_repository_root(repository_root)
    spec = _load_task_spec(
        task_spec_path,
        required_control_ids=set(evidence_control_reviewers),
    )
    _require_current_base(repository, spec.base_commit_sha)
    target = _qualify_output_dir(output_dir, repository)
    factory = authorization_id_factory or _fresh_authorization_id
    authorization_id = factory(spec.issue_number)

    artifacts = _compose_artifacts(
        spec=spec,
        authorization_id=authorization_id,
        evidence_control_reviewers=evidence_control_reviewers,
    )
    structural_errors = codex_pilot_authorization_structural_errors(
        artifacts[AUTHORIZATION_FILENAME]
    )
    if structural_errors:
        _raise_structural_category(structural_errors)

    _reject_existing_output(target, authorization_id)
    stage = _create_stage(target.parent)
    published = False
    try:
        for filename in PACKAGE_FILENAMES:
            _write_canonical_json(stage / filename, artifacts[filename])
        inspection = inspector(
            stage / HANDOFF_FILENAME,
            stage / EVIDENCE_FILENAME,
            stage / AUTHORIZATION_FILENAME,
        )
        _require_successful_inspection(inspection)
        _reject_existing_output(target, authorization_id)
        stage.rename(target)
        published = True
    except CodexPilotPackageBuildError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise CodexPilotPackageBuildError("package_publication_failed") from exc
    finally:
        if not published and stage.exists():
            try:
                shutil.rmtree(stage)
            except OSError as exc:
                raise CodexPilotPackageBuildError(
                    "package_cleanup_uncertain"
                ) from exc

    return _successful_result(
        spec=spec,
        authorization_id=authorization_id,
        inspection=inspection,
    )


def blocked_codex_pilot_package_build_result(category: str) -> dict[str, Any]:
    """Return the bounded fail-closed package-build result."""

    return {
        "allowed_paths": [],
        "authorization_binding_passed": False,
        "authorization_fingerprint": None,
        "authorization_id": None,
        "authorization_path": None,
        "base_commit_sha": None,
        "branch_created": False,
        "branch_name": None,
        "budget_ceiling": None,
        "category": category,
        "claim_created": False,
        "commit_created": False,
        "evidence_path": None,
        "fingerprint_validation_passed": False,
        "handoff_path": None,
        "package_build_result": "blocked",
        "preclaim_ready": False,
        "pr_created": False,
        "push_performed": False,
        "runner_invoked": False,
        "schema_version": PACKAGE_BUILD_SCHEMA_VERSION,
        "structural_validation_passed": False,
    }


def _load_task_spec(
    path: Path,
    *,
    required_control_ids: set[str],
) -> CodexPilotTaskSpec:
    try:
        if path.is_symlink() or not path.is_file():
            raise CodexPilotPackageBuildError("task_spec_unavailable")
        if path.stat().st_size > MAX_TASK_SPEC_BYTES:
            raise CodexPilotPackageBuildError("task_spec_too_large")
        value = json.loads(path.read_text(encoding="utf-8"))
    except CodexPilotPackageBuildError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexPilotPackageBuildError("task_spec_malformed") from exc
    if not isinstance(value, dict) or set(value) != TASK_SPEC_FIELDS:
        raise CodexPilotPackageBuildError("task_spec_malformed")
    return _parse_task_spec(value, required_control_ids=required_control_ids)


def _parse_task_spec(
    value: dict[str, Any],
    *,
    required_control_ids: set[str],
) -> CodexPilotTaskSpec:
    if value.get("schema_version") != TASK_SPEC_SCHEMA_VERSION:
        raise CodexPilotPackageBuildError("task_spec_malformed")
    for field_name, maximum in (
        ("task_id", 80),
        ("handoff_id", 80),
        ("title", 120),
        ("objective", 200),
        ("expected_pr_title", 120),
        ("branch_name", 100),
    ):
        if not _bounded_text(value.get(field_name), maximum):
            raise CodexPilotPackageBuildError("task_spec_malformed")
    issue_number = value.get("issue_number")
    if type(issue_number) is not int or not 1 <= issue_number <= 9_999_999:
        raise CodexPilotPackageBuildError("task_spec_malformed")
    if value.get("repository") != REPOSITORY:
        raise CodexPilotPackageBuildError("task_spec_malformed")
    base_commit_sha = value.get("base_commit_sha")
    if not _lower_hex(base_commit_sha, 40):
        raise CodexPilotPackageBuildError("task_spec_malformed")
    allowed_paths = value.get("allowed_paths")
    if (
        not isinstance(allowed_paths, list)
        or not 1 <= len(allowed_paths) <= 3
        or not all(isinstance(item, str) for item in allowed_paths)
        or allowed_paths != sorted(set(allowed_paths))
    ):
        raise CodexPilotPackageBuildError("unauthorized_path")
    budget_ceiling = value.get("budget_ceiling")
    if type(budget_ceiling) is not int or not 1 <= budget_ceiling <= 1_000_000:
        raise CodexPilotPackageBuildError("task_spec_malformed")
    timeout_seconds = value.get("timeout_seconds")
    if type(timeout_seconds) is not int or not 60 <= timeout_seconds <= 7200:
        raise CodexPilotPackageBuildError("task_spec_malformed")
    references = value.get("control_references")
    if (
        not isinstance(references, dict)
        or set(references) != required_control_ids
        or not all(_bounded_identifier(item) for item in references.values())
    ):
        raise CodexPilotPackageBuildError("task_spec_malformed")
    reviewed_at = _reviewed_datetime(value.get("reviewed_at"))
    constraints = _narrative_list(value.get("constraints"))
    acceptance_criteria = _narrative_list(value.get("acceptance_criteria"))
    return CodexPilotTaskSpec(
        task_id=value["task_id"],
        handoff_id=value["handoff_id"],
        issue_number=issue_number,
        title=value["title"],
        objective=value["objective"],
        repository=value["repository"],
        base_commit_sha=base_commit_sha,
        allowed_paths=tuple(allowed_paths),
        expected_pr_title=value["expected_pr_title"],
        branch_name=value["branch_name"],
        budget_ceiling=budget_ceiling,
        timeout_seconds=timeout_seconds,
        control_references=dict(references),
        reviewed_at=reviewed_at,
        constraints=constraints,
        acceptance_criteria=acceptance_criteria,
    )


def _compose_artifacts(
    *,
    spec: CodexPilotTaskSpec,
    authorization_id: str,
    evidence_control_reviewers: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    allowed_paths = list(spec.allowed_paths)
    task = TaskEnvelope(
        task_id=spec.task_id,
        title=spec.title,
        objective=spec.objective,
        requester=Requester(type=RequesterType.HUMAN, id="human:operator"),
        source=TaskSource(
            kind=SourceKind.GITHUB_ISSUE,
            uri=(
                "https://github.com/Phoenix-AI-Platform/phoenix-office/issues/"
                f"{spec.issue_number}"
            ),
        ),
        status=TaskStatus.REQUESTED,
        priority=TaskPriority.NORMAL,
        constraints=list(spec.constraints),
        acceptance_criteria=list(spec.acceptance_criteria),
        context_refs=allowed_paths,
        allowed_resources={
            "paths": allowed_paths,
            "repositories": [spec.repository],
        },
        permissions=TaskPermissions(
            read=True,
            write=True,
            execute=False,
            network=False,
            destructive=False,
        ),
        approval_policy=ApprovalPolicy(),
        verification_plan=VerificationPlan(
            commands=list(CODEX_PILOT_REQUIRED_VALIDATION_COMMANDS),
            evidence_required=[EvidenceType.TEST_OUTPUT, EvidenceType.LINT_OUTPUT],
        ),
        created_at=spec.reviewed_at,
        updated_at=spec.reviewed_at,
    )
    handoff = CodexHandoffPackage(
        schema_version="codex-handoff-package.v1",
        handoff_id=spec.handoff_id,
        task=task,
        repository=spec.repository,
        base_branch="main",
        expected_pr_title=spec.expected_pr_title,
        prompt=_render_reviewed_prompt(spec),
        workspace_path=None,
        required_repo_paths=allowed_paths,
        required_pr_body_headings=list(REQUIRED_PR_BODY_HEADINGS),
    ).to_dict()
    handoff["task"]["risk_class"] = "docs-only"

    controls = [
        CodexPilotEvidenceControl(
            control_id=control_id,
            status=CodexPilotEvidenceStatus.VERIFIED,
            evidence_ref=spec.control_references[control_id],
            reviewer_role=CodexPilotEvidenceReviewerRole(
                evidence_control_reviewers[control_id]
            ),
        )
        for control_id in sorted(evidence_control_reviewers)
    ]
    evidence = CodexPilotEvidencePackage(
        schema_version="codex-pilot-evidence.v1",
        repository=spec.repository,
        pilot_kind=PILOT_KIND,
        handoff_id=spec.handoff_id,
        controls=controls,
        pilot_ready=False,
        invocation_authorized=False,
    ).to_dict()

    authorization_references = {
        field_name: spec.control_references[control_id]
        for control_id, field_name in REFERENCE_FIELD_BY_CONTROL.items()
    }
    authorization = CodexPilotAuthorizationPacket(
        schema_version="codex-pilot-authorization.v1",
        authorization_id=authorization_id,
        repository=spec.repository,
        pilot_kind=PILOT_KIND,
        decision_state="human_authorized_for_one_run",
        authorizer_role="human_operator",
        base_commit_sha=spec.base_commit_sha,
        handoff_path=HANDOFF_FILENAME,
        evidence_path=EVIDENCE_FILENAME,
        handoff_id=spec.handoff_id,
        objective=spec.objective,
        allowed_paths=allowed_paths,
        expected_pr_title=spec.expected_pr_title,
        branch_name=spec.branch_name,
        validation_commands=list(CODEX_PILOT_REQUIRED_VALIDATION_COMMANDS),
        budget_metric="tokens",
        budget_ceiling=spec.budget_ceiling,
        budget_enforcement_ref=authorization_references[
            "budget_enforcement_ref"
        ],
        timeout_seconds=spec.timeout_seconds,
        cancellation_ref=authorization_references["cancellation_ref"],
        authentication_runner_ref=authorization_references[
            "authentication_runner_ref"
        ],
        branch_permission_ref=authorization_references[
            "branch_permission_ref"
        ],
        pr_permission_ref=authorization_references["pr_permission_ref"],
        duplicate_pr_check_ref=authorization_references[
            "duplicate_pr_check_ref"
        ],
        branch_collision_check_ref=authorization_references[
            "branch_collision_check_ref"
        ],
        codex_no_approve_merge_ref=authorization_references[
            "codex_no_approve_merge_ref"
        ],
        final_ci_required=True,
        assistant_review_required=True,
        worker_may_approve=False,
        worker_may_merge=False,
        one_invocation_only=True,
        retry_authorized=False,
        background_execution_authorized=False,
    ).to_dict()
    return {
        HANDOFF_FILENAME: handoff,
        EVIDENCE_FILENAME: evidence,
        AUTHORIZATION_FILENAME: authorization,
    }


def _render_reviewed_prompt(spec: CodexPilotTaskSpec) -> str:
    criteria = " ".join(
        f"{index}. {item}" for index, item in enumerate(spec.acceptance_criteria, 1)
    )
    constraints = " ".join(
        f"{index}. {item}" for index, item in enumerate(spec.constraints, 1)
    )
    paths = ", ".join(spec.allowed_paths)
    return (
        f"Reviewed task {spec.task_id}: {spec.title}. "
        f"Objective: {spec.objective} "
        f"Modify only these reviewed Markdown paths: {paths}. "
        f"Acceptance criteria: {criteria} "
        f"Constraints: {constraints} "
        "Do not access the network or GitHub. Do not commit, push, approve, "
        "merge, or open a pull request. Stop after completing the authorized edit."
    )


def _require_successful_inspection(
    inspection: CodexPilotPackageInspection,
) -> None:
    if not isinstance(inspection, CodexPilotPackageInspection):
        raise CodexPilotPackageBuildError("package_inspection_uncertain")
    if not all(
        (
            inspection.composite_preflight_passed,
            inspection.authorization_structural_valid,
            inspection.authorization_binding_passed,
            inspection.authorization_fingerprint_valid,
            _lower_hex(inspection.authorization_fingerprint, 64),
        )
    ):
        raise CodexPilotPackageBuildError("generated_package_validation_failed")


def _successful_result(
    *,
    spec: CodexPilotTaskSpec,
    authorization_id: str,
    inspection: CodexPilotPackageInspection,
) -> dict[str, Any]:
    return {
        "allowed_paths": list(spec.allowed_paths),
        "authorization_binding_passed": True,
        "authorization_fingerprint": inspection.authorization_fingerprint,
        "authorization_id": authorization_id,
        "authorization_path": AUTHORIZATION_FILENAME,
        "base_commit_sha": spec.base_commit_sha,
        "branch_created": False,
        "branch_name": spec.branch_name,
        "budget_ceiling": spec.budget_ceiling,
        "category": "preclaim_ready",
        "claim_created": False,
        "commit_created": False,
        "evidence_path": EVIDENCE_FILENAME,
        "fingerprint_validation_passed": True,
        "handoff_path": HANDOFF_FILENAME,
        "package_build_result": "pass",
        "preclaim_ready": True,
        "pr_created": False,
        "push_performed": False,
        "runner_invoked": False,
        "schema_version": PACKAGE_BUILD_SCHEMA_VERSION,
        "structural_validation_passed": True,
    }


def _write_canonical_json(path: Path, payload: dict[str, Any]) -> None:
    try:
        text = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
        encoded = text.encode("utf-8")
        if json.loads(encoded.decode("utf-8")) != payload:
            raise CodexPilotPackageBuildError("serialization_uncertain")
        with path.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except CodexPilotPackageBuildError:
        raise
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        raise CodexPilotPackageBuildError("serialization_uncertain") from exc


def _qualified_repository_root(path: Path) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise CodexPilotPackageBuildError("repository_unavailable") from exc
    if not resolved.is_dir() or _is_link_or_reparse(resolved):
        raise CodexPilotPackageBuildError("repository_unavailable")
    completed = _run_git(resolved, "rev-parse", "--show-toplevel")
    if completed.returncode != 0:
        raise CodexPilotPackageBuildError("repository_unavailable")
    try:
        top = Path(completed.stdout.strip()).resolve(strict=True)
    except OSError as exc:
        raise CodexPilotPackageBuildError("repository_unavailable") from exc
    if top != resolved:
        raise CodexPilotPackageBuildError("repository_unavailable")
    return resolved


def _require_current_base(repository: Path, expected_sha: str) -> None:
    completed = _run_git(repository, "rev-parse", "HEAD")
    if completed.returncode != 0 or completed.stdout.strip() != expected_sha:
        raise CodexPilotPackageBuildError("stale_base_commit")
    if _current_branch(repository) != "main":
        raise CodexPilotPackageBuildError("noncanonical_base_branch")


def _current_branch(repository: Path) -> str:
    completed = _run_git(repository, "branch", "--show-current")
    if completed.returncode != 0:
        raise CodexPilotPackageBuildError("noncanonical_base_branch")
    return completed.stdout.strip()


def _qualify_output_dir(output_dir: Path, repository: Path) -> Path:
    if output_dir.suffix.lower() in DATABASE_SUFFIXES:
        raise CodexPilotPackageBuildError("customer_job_store_rejected")
    _reject_link_or_reparse_ancestry(output_dir)
    try:
        target = output_dir.resolve(strict=False)
    except OSError as exc:
        raise CodexPilotPackageBuildError("output_resolution_unsafe") from exc
    venv = (repository / ".venv").resolve(strict=False)
    if _path_within(target, venv):
        raise CodexPilotPackageBuildError("output_inside_venv")
    try:
        parent = target.parent.resolve(strict=True)
    except OSError as exc:
        raise CodexPilotPackageBuildError("output_resolution_unsafe") from exc
    if not parent.is_dir() or _is_link_or_reparse(parent):
        raise CodexPilotPackageBuildError("output_resolution_unsafe")
    for worktree in _registered_worktrees(repository):
        if _path_within(target, worktree):
            raise CodexPilotPackageBuildError("output_inside_git_worktree")
    if _inside_any_git_worktree(parent):
        raise CodexPilotPackageBuildError("output_inside_git_worktree")
    return target


def _registered_worktrees(repository: Path) -> tuple[Path, ...]:
    completed = _run_git(repository, "worktree", "list", "--porcelain")
    if completed.returncode != 0:
        raise CodexPilotPackageBuildError("worktree_inspection_failed")
    worktrees: list[Path] = []
    for line in completed.stdout.splitlines():
        if not line.startswith("worktree "):
            continue
        raw = line.removeprefix("worktree ")
        try:
            resolved = Path(raw).resolve(strict=True)
        except OSError as exc:
            raise CodexPilotPackageBuildError(
                "worktree_inspection_failed"
            ) from exc
        worktrees.append(resolved)
    if not worktrees:
        raise CodexPilotPackageBuildError("worktree_inspection_failed")
    return tuple(worktrees)


def _inside_any_git_worktree(path: Path) -> bool:
    completed = _run_git(path, "rev-parse", "--is-inside-work-tree")
    return completed.returncode == 0 and completed.stdout.strip() == "true"


def _run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            check=False,
            shell=False,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CodexPilotPackageBuildError("git_inspection_failed") from exc


def _reject_existing_output(target: Path, authorization_id: str) -> None:
    if not target.exists() and not target.is_symlink():
        return
    if target.is_dir() and not target.is_symlink():
        authorization_path = target / AUTHORIZATION_FILENAME
        try:
            if (
                authorization_path.is_file()
                and authorization_path.stat().st_size <= MAX_TASK_SPEC_BYTES
            ):
                payload = json.loads(authorization_path.read_text(encoding="utf-8"))
                if (
                    isinstance(payload, dict)
                    and payload.get("authorization_id") == authorization_id
                ):
                    raise CodexPilotPackageBuildError(
                        "authorization_identity_collision"
                    )
        except CodexPilotPackageBuildError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass
    raise CodexPilotPackageBuildError("output_artifacts_already_exist")


def _create_stage(parent: Path) -> Path:
    try:
        stage = Path(
            tempfile.mkdtemp(prefix=".phoenix-codex-package-", dir=parent)
        ).resolve(strict=True)
    except OSError as exc:
        raise CodexPilotPackageBuildError("package_staging_failed") from exc
    if not _path_within(stage, parent) or _is_link_or_reparse(stage):
        raise CodexPilotPackageBuildError("package_staging_failed")
    return stage


def _reject_link_or_reparse_ancestry(path: Path) -> None:
    candidate = path if path.exists() or path.is_symlink() else path.parent
    while True:
        if candidate.exists() or candidate.is_symlink():
            if _is_link_or_reparse(candidate):
                raise CodexPilotPackageBuildError("output_symlink_rejected")
        if candidate.parent == candidate:
            return
        candidate = candidate.parent


def _is_link_or_reparse(path: Path) -> bool:
    try:
        details = path.lstat()
    except OSError:
        return True
    attributes = getattr(details, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(details.st_mode) or bool(attributes & reparse_flag)


def _path_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _fresh_authorization_id(issue_number: int) -> str:
    return f"pilot-auth-issue-{issue_number}-{uuid.uuid4().hex[:16]}"


def _raise_structural_category(errors: list[str]) -> None:
    if "authorization branch_name is invalid" in errors:
        category = "unsafe_branch"
    elif "authorization allowed paths are invalid" in errors:
        category = "unauthorized_path"
    elif "authorization authorization_id is invalid" in errors:
        category = "authorization_identity_invalid"
    else:
        category = "generated_authorization_invalid"
    raise CodexPilotPackageBuildError(category)


def _reviewed_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        raise CodexPilotPackageBuildError("task_spec_malformed")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CodexPilotPackageBuildError("task_spec_malformed") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CodexPilotPackageBuildError("task_spec_malformed")
    return parsed


def _narrative_list(value: Any) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not 1 <= len(value) <= MAX_NARRATIVE_ITEMS
        or not all(_bounded_text(item, 300) for item in value)
    ):
        raise CodexPilotPackageBuildError("task_spec_malformed")
    return tuple(value)


def _bounded_text(value: Any, maximum: int) -> bool:
    return (
        isinstance(value, str)
        and value == value.strip()
        and 1 <= len(value) <= maximum
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
    )


def _bounded_identifier(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 80
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value) is not None
        and not any(
            marker in value.lower()
            for marker in ("sk-", "token", "secret", "password", "users", "home")
        )
    )


def _lower_hex(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )
