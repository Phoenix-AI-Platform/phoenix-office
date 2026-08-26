from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from phoenix_office import cli
from phoenix_office.dev import codex_successor_task_spec
from phoenix_office.dev.codex_package import (
    CODEX_PILOT_TASK_SPEC_CONTROL_IDS,
    CODEX_PILOT_TASK_SPEC_MAX_ISSUE_NUMBER,
    load_codex_pilot_task_spec,
)
from phoenix_office.dev.codex_successor import (
    REPOSITORY_IDENTITY,
    SUCCESSOR_CANDIDATE_SCHEMA_VERSION,
    SUCCESSOR_EXECUTION_SCHEMA_VERSION,
    CodexSuccessorProposalError,
    RepositoryState,
    propose_codex_successor,
)
from phoenix_office.dev.codex_successor_task_spec import (
    ARCHITECTURE_APPROVAL_DECISION,
    ARCHITECTURE_APPROVAL_SCHEMA_VERSION,
    ARCHITECTURE_APPROVER_ROLE,
    CodexSuccessorTaskSpecError,
    blocked_codex_successor_task_spec_result,
    build_approved_codex_successor_task_spec,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_PATH = "docs/development/progress_dashboard.md"
VERIFICATION_ID = "12345678-1234-4234-9234-123456789abc"
ISSUE_NUMBER = 392
TASK_ID = "TASK-076"


def _head() -> str:
    completed = subprocess.run(
        ["git", "-C", str(REPOSITORY_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        check=True,
        shell=False,
        text=True,
    )
    return completed.stdout.strip()


def _candidate(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": SUCCESSOR_CANDIDATE_SCHEMA_VERSION,
        "task_id": TASK_ID,
        "candidate_state": "ready",
        "queue": "autonomy",
        "priority": 80,
        "risk_class": "low",
        "depends_on": [390],
        "repository": REPOSITORY_IDENTITY,
        "base_branch": "main",
        "allowed_paths": [ALLOWED_PATH],
        "expected_pr_title": "docs: record approved successor compilation",
        "execution_class": "docs-only-supervised",
    }
    value.update(updates)
    return value


def _execution(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": SUCCESSOR_EXECUTION_SCHEMA_VERSION,
        "task_id": TASK_ID,
        "objective": "Document the approved deterministic successor milestone.",
        "branch_name": "codex/issue-076-compiled-docs",
        "budget_ceiling": 225000,
        "timeout_seconds": 1800,
        "control_references": {
            control_id: f"{control_id}-reviewed"
            for control_id in CODEX_PILOT_TASK_SPEC_CONTROL_IDS
        },
        "constraints": [
            "Edit only the authorized Markdown path.",
            "Do not grant publication authority to the worker.",
        ],
        "acceptance_criteria": [
            "The reviewed milestone is documented accurately.",
            "All Phoenix-owned validation gates pass.",
        ],
    }
    value.update(updates)
    return value


def _issue(
    *,
    number: int = ISSUE_NUMBER,
    candidate: dict[str, object] | None = None,
    execution: dict[str, object] | None = None,
    include_execution: bool = True,
    title: str = "TASK-076: Compile approved successor task specs",
) -> dict[str, object]:
    candidate_payload = candidate if candidate is not None else _candidate()
    body = (
        "```phoenix-codex-successor\n"
        f"{json.dumps(candidate_payload, sort_keys=True)}\n"
        "```"
    )
    if include_execution:
        execution_payload = execution if execution is not None else _execution()
        body += (
            "\n\n```phoenix-codex-execution\n"
            f"{json.dumps(execution_payload, sort_keys=True)}\n"
            "```"
        )
    return {
        "number": number,
        "title": title,
        "state": "OPEN",
        "body": body,
    }


def _evidence(path: Path, head: str) -> Path:
    payload = {
        "schema_version": "2.0",
        "verification_id": VERIFICATION_ID,
        "overall_health": "pass",
        "overall_evidence_coverage": "complete",
        "summary": {
            "total_configured_repositories": 1,
            "repositories_discovered": 1,
            "clean_working_trees": 1,
            "dirty_working_trees": 0,
            "health_pass": 1,
            "health_fail": 0,
            "health_unknown": 0,
            "evidence_complete": 1,
            "evidence_partial": 0,
            "evidence_insufficient": 0,
            "failed_commands": 0,
            "commands_not_started": 0,
        },
        "repositories": [
            {
                "repository": "phoenix-office",
                "health": "pass",
                "evidence_coverage": "complete",
                "git": {
                    "is_git_work_tree": True,
                    "branch": "main",
                    "commit": head,
                    "working_tree_clean": True,
                    "status_entries": [],
                },
            }
        ],
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


@dataclass
class FakeServices:
    issue: object
    head: str
    dependencies: dict[int, object] = field(
        default_factory=lambda: {
            390: {"number": 390, "state": "CLOSED", "stateReason": "COMPLETED"}
        }
    )
    paths: tuple[str, ...] = (ALLOWED_PATH,)
    branch: str = "main"
    clean: bool = True
    repository_identity: str | None = REPOSITORY_IDENTITY
    failure: str | None = None
    calls: list[str] = field(default_factory=list)

    def canonical_repository_root(self) -> Path:
        self.calls.append("canonical_repository_root")
        return REPOSITORY_ROOT

    def repository_state(self) -> RepositoryState:
        self.calls.append("repository_state")
        return RepositoryState(
            self.branch,
            self.head,
            self.clean,
            self.repository_identity,
        )

    def tracked_paths(self) -> tuple[str, ...]:
        self.calls.append("tracked_paths")
        return self.paths

    def list_open_issues(self) -> object:
        self.calls.append("list_open_issues")
        return [self.issue]

    def read_issue(self, issue_number: int) -> object:
        self.calls.append(f"read_issue:{issue_number}")
        if self.failure is not None:
            raise CodexSuccessorProposalError(self.failure)
        return self.issue

    def read_dependency(self, issue_number: int) -> object:
        self.calls.append(f"read_dependency:{issue_number}")
        if issue_number not in self.dependencies:
            raise CodexSuccessorProposalError("dependency_state_unknown")
        return self.dependencies[issue_number]


def _proposal(
    tmp_path: Path,
    services: FakeServices,
) -> dict[str, object]:
    result = propose_codex_successor(
        repository_root=REPOSITORY_ROOT,
        verification_evidence_path=_evidence(
            tmp_path / "verification.json",
            services.head,
        ),
        services=services,
    )
    assert result["status"] == "success"
    return result


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _approval(proposal: dict[str, object], **updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": ARCHITECTURE_APPROVAL_SCHEMA_VERSION,
        "decision": ARCHITECTURE_APPROVAL_DECISION,
        "approver_role": ARCHITECTURE_APPROVER_ROLE,
        "proposal_fingerprint": proposal["proposal_fingerprint"],
        "verified_base_sha": proposal["verified_base_sha"],
        "selected_issue_number": proposal["selected_issue_number"],
        "selected_task_id": proposal["selected_task_id"],
        "approved_at": "2026-08-25T12:00:00Z",
    }
    value.update(updates)
    return value


def _compile(
    tmp_path: Path,
    *,
    services: FakeServices | None = None,
    proposal_updates: dict[str, object] | None = None,
    approval_updates: dict[str, object] | None = None,
    output_name: str = "task-spec.json",
) -> tuple[dict[str, object], Path, dict[str, object]]:
    system = services or FakeServices(_issue(), _head())
    proposal = _proposal(
        tmp_path,
        FakeServices(system.issue, system.head, paths=system.paths),
    )
    if proposal_updates:
        proposal.update(proposal_updates)
    proposal_path = _write_json(tmp_path / "proposal.json", proposal)
    approval_path = _write_json(
        tmp_path / "approval.json",
        _approval(proposal, **(approval_updates or {})),
    )
    output = tmp_path / output_name
    result = build_approved_codex_successor_task_spec(
        proposal_path=proposal_path,
        architecture_approval_path=approval_path,
        output_path=output,
        repository_root=REPOSITORY_ROOT,
        services=system,
    )
    return result, output, proposal


def test_valid_external_approval_compiles_exact_task_spec(tmp_path: Path) -> None:
    result, output, proposal = _compile(tmp_path)

    assert result["status"] == "success"
    assert result["category"] == "task_spec_compiled"
    assert result["architecture_approval_validated"] is True
    assert result["task_spec_validated"] is True
    assert result["task_spec_written"] is True
    spec = load_codex_pilot_task_spec(
        output,
        required_control_ids=set(CODEX_PILOT_TASK_SPEC_CONTROL_IDS),
    )
    assert spec.issue_number == ISSUE_NUMBER
    assert spec.execution_class == "docs-only-supervised"
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == (
        "codex-pilot-task-spec.v2"
    )
    assert json.loads(output.read_text(encoding="utf-8"))["execution_class"] == (
        "docs-only-supervised"
    )
    assert spec.task_id == TASK_ID
    assert spec.base_commit_sha == proposal["verified_base_sha"]
    assert spec.allowed_paths == (ALLOWED_PATH,)
    assert spec.handoff_id == f"pilot-handoff-{proposal['proposal_fingerprint']}"
    assert spec.reviewed_at.isoformat() == "2026-08-25T12:00:00+00:00"
    assert set(cli.CODEX_PILOT_EVIDENCE_CONTROL_REVIEWERS) == (
        CODEX_PILOT_TASK_SPEC_CONTROL_IDS
    )


def test_bounded_python_successor_compiles_explicit_v2_class(
    tmp_path: Path,
) -> None:
    paths = (
        "src/phoenix_office/dev/codex_successor.py",
        "tests/test_codex_successor.py",
    )
    candidate = _candidate(
        execution_class="bounded-python-supervised",
        allowed_paths=list(paths),
        expected_pr_title="dev: refine successor policy",
        risk_class="low",
    )
    execution = _execution(
        objective="Develop Python code and focused tests safely."
    )
    services = FakeServices(
        _issue(candidate=candidate, execution=execution),
        _head(),
        paths=paths,
    )

    result, output, _proposal_value = _compile(tmp_path, services=services)
    payload = json.loads(output.read_text(encoding="utf-8"))
    spec = load_codex_pilot_task_spec(
        output,
        required_control_ids=set(CODEX_PILOT_TASK_SPEC_CONTROL_IDS),
    )

    assert result["status"] == "success"
    assert payload["schema_version"] == "codex-pilot-task-spec.v2"
    assert payload["execution_class"] == "bounded-python-supervised"
    assert spec.execution_class == "bounded-python-supervised"


def test_mutated_selected_execution_class_is_rejected_before_compilation(
    tmp_path: Path,
) -> None:
    with pytest.raises(CodexSuccessorTaskSpecError):
        _compile(
            tmp_path,
            proposal_updates={
                "selected_execution_class": "bounded-python-supervised"
            },
        )


def test_maximum_issue_number_compiles_with_external_approval(
    tmp_path: Path,
) -> None:
    issue = _issue(number=CODEX_PILOT_TASK_SPEC_MAX_ISSUE_NUMBER)
    result, output, proposal = _compile(
        tmp_path,
        services=FakeServices(issue, _head()),
    )

    spec = load_codex_pilot_task_spec(
        output,
        required_control_ids=set(CODEX_PILOT_TASK_SPEC_CONTROL_IDS),
    )

    assert result["status"] == "success"
    assert proposal["selected_issue_number"] == 9_999_999
    assert spec.issue_number == 9_999_999


def test_approval_issue_number_above_task_spec_ceiling_is_rejected(
    tmp_path: Path,
) -> None:
    with pytest.raises(CodexSuccessorTaskSpecError) as error:
        _compile(
            tmp_path,
            approval_updates={
                "selected_issue_number": (
                    CODEX_PILOT_TASK_SPEC_MAX_ISSUE_NUMBER + 1
                )
            },
        )

    assert error.value.category == "malformed_approval_receipt"
    assert not (tmp_path / "task-spec.json").exists()


def test_repeated_compile_produces_identical_task_spec_bytes(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first_result, first, _proposal_value = _compile(first_dir)
    second_result, second, _proposal_value = _compile(second_dir)

    assert first_result["status"] == second_result["status"] == "success"
    assert first.read_bytes() == second.read_bytes()


@pytest.mark.parametrize(
    ("execution_updates", "category"),
    [
        (
            {"objective": "Document a changed objective."},
            "selected_issue_changed",
        ),
        (
            {"acceptance_criteria": ["A changed acceptance criterion."]},
            "selected_issue_changed",
        ),
        ({"branch_name": "codex/issue-076-changed"}, "selected_issue_changed"),
        ({"budget_ceiling": 225001}, "selected_issue_changed"),
        ({"timeout_seconds": 1801}, "selected_issue_changed"),
        (
            {
                "control_references": {
                    control_id: f"{control_id}-changed"
                    for control_id in CODEX_PILOT_TASK_SPEC_CONTROL_IDS
                }
            },
            "selected_issue_changed",
        ),
    ],
)
def test_selected_execution_change_invalidates_approved_proposal(
    tmp_path: Path,
    execution_updates: dict[str, object],
    category: str,
) -> None:
    original = _issue()
    changed = _issue(execution=_execution(**execution_updates))
    services = FakeServices(changed, _head())
    proposal = _proposal(tmp_path, FakeServices(original, services.head))

    with pytest.raises(CodexSuccessorTaskSpecError) as error:
        build_approved_codex_successor_task_spec(
            proposal_path=_write_json(tmp_path / "proposal.json", proposal),
            architecture_approval_path=_write_json(
                tmp_path / "approval.json",
                _approval(proposal),
            ),
            output_path=tmp_path / "task-spec.json",
            repository_root=REPOSITORY_ROOT,
            services=services,
        )

    assert error.value.category == category
    assert not (tmp_path / "task-spec.json").exists()


def test_candidate_metadata_change_invalidates_proposal(tmp_path: Path) -> None:
    original = _issue()
    changed = _issue(candidate=_candidate(priority=81))
    services = FakeServices(changed, _head())
    proposal = _proposal(tmp_path, FakeServices(original, services.head))

    with pytest.raises(CodexSuccessorTaskSpecError) as error:
        build_approved_codex_successor_task_spec(
            proposal_path=_write_json(tmp_path / "proposal.json", proposal),
            architecture_approval_path=_write_json(
                tmp_path / "approval.json",
                _approval(proposal),
            ),
            output_path=tmp_path / "task-spec.json",
            repository_root=REPOSITORY_ROOT,
            services=services,
        )

    assert error.value.category == "selected_issue_changed"


def test_stale_base_is_blocked_before_github_read(tmp_path: Path) -> None:
    services = FakeServices(_issue(), _head())
    proposal = _proposal(tmp_path, FakeServices(services.issue, services.head))
    services.head = "0" * 40

    with pytest.raises(CodexSuccessorTaskSpecError) as error:
        build_approved_codex_successor_task_spec(
            proposal_path=_write_json(tmp_path / "proposal.json", proposal),
            architecture_approval_path=_write_json(
                tmp_path / "approval.json",
                _approval(proposal),
            ),
            output_path=tmp_path / "task-spec.json",
            repository_root=REPOSITORY_ROOT,
            services=services,
        )

    assert error.value.category == "stale_proposal_base_sha"
    assert not any(call.startswith("read_issue:") for call in services.calls)


@pytest.mark.parametrize(
    ("approval_updates", "category"),
    [
        ({"decision": "rejected"}, "approval_not_approved"),
        ({"approver_role": "phoenix"}, "disallowed_approver_role"),
        ({"approver_role": "codex"}, "disallowed_approver_role"),
        ({"approver_role": "worker"}, "disallowed_approver_role"),
        ({"proposal_fingerprint": "0" * 64}, "approval_binding_mismatch"),
        ({"verified_base_sha": "0" * 40}, "approval_binding_mismatch"),
        ({"selected_issue_number": 999}, "approval_binding_mismatch"),
        ({"selected_task_id": "TASK-999"}, "approval_binding_mismatch"),
    ],
)
def test_approval_decision_role_and_binding_fail_closed(
    tmp_path: Path,
    approval_updates: dict[str, object],
    category: str,
) -> None:
    with pytest.raises(CodexSuccessorTaskSpecError) as error:
        _compile(tmp_path, approval_updates=approval_updates)

    assert error.value.category == category
    assert not (tmp_path / "task-spec.json").exists()


@pytest.mark.parametrize(
    ("input_kind", "category"),
    [
        ("missing_proposal", "proposal_unavailable"),
        ("malformed_proposal", "malformed_proposal"),
        ("not_ready_proposal", "proposal_not_ready"),
        ("missing_approval", "approval_receipt_unavailable"),
        ("malformed_approval", "malformed_approval_receipt"),
    ],
)
def test_missing_and_malformed_inputs_fail_closed(
    tmp_path: Path,
    input_kind: str,
    category: str,
) -> None:
    services = FakeServices(_issue(), _head())
    proposal = _proposal(tmp_path, FakeServices(services.issue, services.head))
    proposal_path = tmp_path / "proposal.json"
    approval_path = tmp_path / "approval.json"
    if input_kind != "missing_proposal":
        proposal_payload: object = proposal
        if input_kind == "malformed_proposal":
            proposal_payload = {"schema_version": "wrong"}
        elif input_kind == "not_ready_proposal":
            proposal_payload = {**proposal, "status": "blocked"}
        _write_json(proposal_path, proposal_payload)
    if input_kind != "missing_approval":
        approval_payload: object = _approval(proposal)
        if input_kind == "malformed_approval":
            approval_payload = {"schema_version": "wrong"}
        _write_json(approval_path, approval_payload)

    with pytest.raises(CodexSuccessorTaskSpecError) as error:
        build_approved_codex_successor_task_spec(
            proposal_path=proposal_path,
            architecture_approval_path=approval_path,
            output_path=tmp_path / "task-spec.json",
            repository_root=REPOSITORY_ROOT,
            services=services,
        )

    assert error.value.category == category
    assert not (tmp_path / "task-spec.json").exists()


@pytest.mark.parametrize(
    ("issue", "category"),
    [
        (_issue(include_execution=False), "missing_execution_definition"),
        (
            _issue(execution=_execution(task_id="TASK-999")),
            "candidate_execution_mismatch",
        ),
        (
            _issue(execution=_execution(branch_name="feature/unsafe")),
            "malformed_execution_definition",
        ),
        (
            _issue(candidate=_candidate(expected_pr_title="feat: unsafe")),
            "malformed_candidate_metadata",
        ),
        (
            _issue(candidate=_candidate(allowed_paths=["src/phoenix_office/cli.py"])),
            "unsafe_allowed_path",
        ),
    ],
)
def test_current_issue_must_remain_task_spec_compatible(
    tmp_path: Path,
    issue: dict[str, object],
    category: str,
) -> None:
    original = _issue()
    head = _head()
    proposal = _proposal(tmp_path, FakeServices(original, head))

    with pytest.raises(CodexSuccessorTaskSpecError) as error:
        build_approved_codex_successor_task_spec(
            proposal_path=_write_json(tmp_path / "proposal.json", proposal),
            architecture_approval_path=_write_json(
                tmp_path / "approval.json",
                _approval(proposal),
            ),
            output_path=tmp_path / "task-spec.json",
            repository_root=REPOSITORY_ROOT,
            services=FakeServices(issue, head),
        )

    assert error.value.category == category


def test_authorization_incompatible_objective_cannot_compile(
    tmp_path: Path,
) -> None:
    task_077_objective = (
        "Record the first verified successor-driven supervised Codex autonomy "
        "pilot in the Phoenix development progress dashboard."
    )

    with pytest.raises(CodexSuccessorTaskSpecError) as error:
        _compile(
            tmp_path,
            proposal_updates={
                "selected_execution_definition": _execution(
                    objective=task_077_objective
                )
            },
        )

    assert error.value.category == "malformed_proposal"
    assert not (tmp_path / "task-spec.json").exists()


def test_fingerprint_mismatch_fails_closed(tmp_path: Path) -> None:
    services = FakeServices(_issue(), _head())
    proposal = _proposal(tmp_path, FakeServices(services.issue, services.head))
    proposal["proposal_fingerprint"] = "0" * 64

    with pytest.raises(CodexSuccessorTaskSpecError) as error:
        build_approved_codex_successor_task_spec(
            proposal_path=_write_json(tmp_path / "proposal.json", proposal),
            architecture_approval_path=_write_json(
                tmp_path / "approval.json",
                _approval(proposal),
            ),
            output_path=tmp_path / "task-spec.json",
            repository_root=REPOSITORY_ROOT,
            services=services,
        )

    assert error.value.category == "proposal_fingerprint_mismatch"


def test_open_dependency_fails_closed(tmp_path: Path) -> None:
    services = FakeServices(
        _issue(),
        _head(),
        dependencies={
            390: {"number": 390, "state": "OPEN", "stateReason": None}
        },
    )
    proposal = _proposal(
        tmp_path,
        FakeServices(services.issue, services.head),
    )

    with pytest.raises(CodexSuccessorTaskSpecError) as error:
        build_approved_codex_successor_task_spec(
            proposal_path=_write_json(tmp_path / "proposal.json", proposal),
            architecture_approval_path=_write_json(
                tmp_path / "approval.json",
                _approval(proposal),
            ),
            output_path=tmp_path / "task-spec.json",
            repository_root=REPOSITORY_ROOT,
            services=services,
        )

    assert error.value.category == "dependency_not_completed"


def test_serialization_uncertainty_publishes_no_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = FakeServices(_issue(), _head())
    proposal = _proposal(tmp_path, FakeServices(services.issue, services.head))
    proposal_path = _write_json(tmp_path / "proposal.json", proposal)
    approval_path = _write_json(tmp_path / "approval.json", _approval(proposal))
    monkeypatch.setattr(
        codex_successor_task_spec.json,
        "dumps",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TypeError()),
    )

    with pytest.raises(CodexSuccessorTaskSpecError) as error:
        build_approved_codex_successor_task_spec(
            proposal_path=proposal_path,
            architecture_approval_path=approval_path,
            output_path=tmp_path / "task-spec.json",
            repository_root=REPOSITORY_ROOT,
            services=services,
        )

    assert error.value.category == "serialization_uncertainty"
    assert not (tmp_path / "task-spec.json").exists()


@pytest.mark.parametrize(
    ("branch", "clean", "identity", "category"),
    [
        ("feature", True, REPOSITORY_IDENTITY, "non_main_checkout"),
        ("main", False, REPOSITORY_IDENTITY, "dirty_worktree"),
        ("main", True, "SomeoneElse/phoenix-office", "repository_identity_mismatch"),
    ],
)
def test_repository_gate_remains_fail_closed(
    tmp_path: Path,
    branch: str,
    clean: bool,
    identity: str,
    category: str,
) -> None:
    services = FakeServices(
        _issue(),
        _head(),
        branch=branch,
        clean=clean,
        repository_identity=identity,
    )
    proposal = _proposal(tmp_path, FakeServices(services.issue, services.head))

    with pytest.raises(CodexSuccessorTaskSpecError) as error:
        build_approved_codex_successor_task_spec(
            proposal_path=_write_json(tmp_path / "proposal.json", proposal),
            architecture_approval_path=_write_json(
                tmp_path / "approval.json",
                _approval(proposal),
            ),
            output_path=tmp_path / "task-spec.json",
            repository_root=REPOSITORY_ROOT,
            services=services,
        )

    assert error.value.category == category


def test_unsafe_output_and_collision_fail_closed(tmp_path: Path) -> None:
    services = FakeServices(_issue(), _head())
    proposal = _proposal(tmp_path, FakeServices(services.issue, services.head))
    proposal_path = _write_json(tmp_path / "proposal.json", proposal)
    approval_path = _write_json(tmp_path / "approval.json", _approval(proposal))

    with pytest.raises(CodexSuccessorTaskSpecError) as unsafe:
        build_approved_codex_successor_task_spec(
            proposal_path=proposal_path,
            architecture_approval_path=approval_path,
            output_path=REPOSITORY_ROOT / "task-spec.json",
            repository_root=REPOSITORY_ROOT,
            services=services,
        )
    assert unsafe.value.category == "output_inside_git_worktree"

    collision = tmp_path / "task-spec.json"
    collision.write_text("existing", encoding="utf-8")
    with pytest.raises(CodexSuccessorTaskSpecError) as existing:
        build_approved_codex_successor_task_spec(
            proposal_path=proposal_path,
            architecture_approval_path=approval_path,
            output_path=collision,
            repository_root=REPOSITORY_ROOT,
            services=FakeServices(_issue(), services.head),
        )
    assert existing.value.category == "output_collision"
    assert collision.read_text(encoding="utf-8") == "existing"


def test_github_read_uncertainty_is_bounded_and_no_authority_is_opened(
    tmp_path: Path,
) -> None:
    services = FakeServices(_issue(), _head(), failure="github_read_failed")
    proposal = _proposal(tmp_path, FakeServices(services.issue, services.head))

    with pytest.raises(CodexSuccessorTaskSpecError) as error:
        build_approved_codex_successor_task_spec(
            proposal_path=_write_json(tmp_path / "proposal.json", proposal),
            architecture_approval_path=_write_json(
                tmp_path / "approval.json",
                _approval(proposal),
            ),
            output_path=tmp_path / "task-spec.json",
            repository_root=REPOSITORY_ROOT,
            services=services,
        )

    assert error.value.category == "github_read_failed"
    for forbidden in (
        "create_issue",
        "update_issue",
        "create_approval",
        "create_authorization",
        "create_claim",
        "build_package",
        "invoke_reviewed_runner",
        "invoke_codex",
        "create_branch",
        "commit",
        "push",
        "create_pull_request",
        "merge",
        "retry",
        "background_resume",
    ):
        assert not hasattr(services, forbidden)


def test_public_result_is_bounded_and_contains_no_input_paths_or_raw_issue(
    tmp_path: Path,
) -> None:
    result, _output, _proposal_value = _compile(tmp_path)
    encoded = json.dumps(result, sort_keys=True)

    assert str(tmp_path) not in encoded
    assert "phoenix-codex-execution" not in encoded
    assert "token=" not in encoded.lower()
    assert result["package_builder_invoked"] is False
    assert result["reviewed_runner_invoked"] is False
    assert result["codex_invoked"] is False
    assert result["claim_created"] is False
    assert result["authorization_created"] is False
    assert result["github_mutation_used"] is False
    assert result["retry_used"] is False
    assert result["background_resume_used"] is False


def test_blocked_result_is_bounded() -> None:
    result = blocked_codex_successor_task_spec_result("malformed_proposal")

    assert result["status"] == "blocked"
    assert result["task_spec_written"] is False
    assert result["authorization_created"] is False
    assert result["claim_created"] is False


def test_cli_builds_one_task_spec_and_returns_bounded_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: Any,
) -> None:
    expected = {
        "schema_version": "codex-successor-task-spec-build-result.v1",
        "status": "success",
        "category": "task_spec_compiled",
    }
    monkeypatch.setattr(
        cli,
        "build_approved_codex_successor_task_spec",
        lambda **_kwargs: expected,
    )
    monkeypatch.setattr(cli, "SystemCodexSuccessorServices", lambda _path: object())

    exit_code = cli.main(
        [
            "dev",
            "codex-successor-task-spec-build",
            "proposal.json",
            "approval.json",
            "--output",
            "task-spec.json",
            "--json",
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == expected
