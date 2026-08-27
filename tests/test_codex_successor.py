from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import pytest

from phoenix_office import cli
from phoenix_office.dev.codex_package import (
    CODEX_PILOT_TASK_SPEC_CONTROL_IDS,
    CODEX_PILOT_TASK_SPEC_MAX_ISSUE_NUMBER,
)
from phoenix_office.dev.codex_successor import (
    REPOSITORY_IDENTITY,
    SUCCESSOR_CANDIDATE_SCHEMA_VERSION,
    SUCCESSOR_EXECUTION_SCHEMA_VERSION,
    CodexSuccessorProposalError,
    RepositoryState,
    SystemCodexSuccessorServices,
    VerificationState,
    _bounded_process_environment,
    codex_successor_proposal_fingerprint,
    parse_codex_successor_proposal_payload,
    parse_selected_codex_successor_issue,
    propose_codex_successor,
)

HEAD = "a" * 40
VERIFICATION_ID = "12345678-1234-4234-9234-123456789abc"
ALLOWED_PATH = "docs/development/progress_dashboard.md"


@dataclass
class FakeServices:
    root: Path | None = None
    state: RepositoryState = RepositoryState("main", HEAD, True)
    issues: object = field(default_factory=list)
    dependencies: dict[int, object] = field(default_factory=dict)
    paths: tuple[str, ...] = (ALLOWED_PATH,)
    failure: str | None = None
    calls: list[str] = field(default_factory=list)

    def canonical_repository_root(self) -> Path:
        self.calls.append("canonical_repository_root")
        if self.root is None:
            raise CodexSuccessorProposalError("outside_repository")
        return self.root

    def repository_state(self) -> RepositoryState:
        self.calls.append("repository_state")
        return self.state

    def tracked_paths(self) -> tuple[str, ...]:
        self.calls.append("tracked_paths")
        return self.paths

    def list_open_issues(self) -> object:
        self.calls.append("list_open_issues")
        if self.failure is not None:
            raise CodexSuccessorProposalError(self.failure)
        return self.issues

    def read_issue(self, issue_number: int) -> object:
        self.calls.append(f"read_issue:{issue_number}")
        if not isinstance(self.issues, list):
            raise CodexSuccessorProposalError("github_read_failed")
        matches = [item for item in self.issues if item.get("number") == issue_number]
        if len(matches) != 1:
            raise CodexSuccessorProposalError("github_read_failed")
        return matches[0]

    def read_dependency(self, issue_number: int) -> object:
        self.calls.append(f"read_dependency:{issue_number}")
        if issue_number not in self.dependencies:
            raise CodexSuccessorProposalError("github_read_failed")
        return self.dependencies[issue_number]


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    target = root / ALLOWED_PATH
    target.parent.mkdir(parents=True)
    target.write_text("# Dashboard\n", encoding="utf-8")
    return root


def _evidence_payload(
    *,
    head: str = HEAD,
    health: str = "pass",
    coverage: str = "complete",
    office_entries: int = 1,
) -> dict[str, object]:
    office = {
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
    return {
        "schema_version": "2.0",
        "verification_id": VERIFICATION_ID,
        "overall_health": health,
        "overall_evidence_coverage": coverage,
        "summary": {
            "total_configured_repositories": office_entries,
            "repositories_discovered": office_entries,
            "clean_working_trees": office_entries,
            "dirty_working_trees": 0,
            "health_pass": office_entries,
            "health_fail": 0,
            "health_unknown": 0,
            "evidence_complete": office_entries,
            "evidence_partial": 0,
            "evidence_insufficient": 0,
            "failed_commands": 0,
            "commands_not_started": 0,
        },
        "repositories": [dict(office) for _ in range(office_entries)],
    }


def _write_evidence(path: Path, **overrides: object) -> Path:
    path.write_text(
        json.dumps(_evidence_payload(**overrides), sort_keys=True),
        encoding="utf-8",
    )
    return path


def _candidate_metadata(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": SUCCESSOR_CANDIDATE_SCHEMA_VERSION,
        "task_id": "TASK-076",
        "candidate_state": "ready",
        "queue": "autonomy",
        "priority": 50,
        "risk_class": "low",
        "depends_on": [],
        "repository": REPOSITORY_IDENTITY,
        "base_branch": "main",
        "allowed_paths": [ALLOWED_PATH],
        "expected_pr_title": "docs: record the next autonomy milestone",
        "execution_class": "docs-only-supervised",
    }
    value.update(overrides)
    return value


def _execution_definition(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": SUCCESSOR_EXECUTION_SCHEMA_VERSION,
        "task_id": "TASK-076",
        "objective": "Document the next verified autonomy milestone.",
        "branch_name": "codex/issue-076-docs",
        "budget_ceiling": 225000,
        "timeout_seconds": 1800,
        "control_references": {
            control_id: f"{control_id}-reviewed"
            for control_id in CODEX_PILOT_TASK_SPEC_CONTROL_IDS
        },
        "constraints": [
            "Edit only the authorized Markdown path.",
            "Do not create publication authority for the worker.",
        ],
        "acceptance_criteria": [
            "The reviewed documentation reflects the verified milestone.",
            "All Phoenix-owned validation gates pass.",
        ],
    }
    value.update(overrides)
    return value


def _issue(
    number: int = 391,
    *,
    title: str = "TASK-076: Record the next autonomy milestone",
    metadata: dict[str, object] | None = None,
    execution: dict[str, object] | None = None,
    include_execution: bool = True,
    body: str | None = None,
) -> dict[str, object]:
    if body is None:
        payload = metadata if metadata is not None else _candidate_metadata()
        execution_payload = (
            execution
            if execution is not None
            else _execution_definition(task_id=payload.get("task_id"))
        )
        body = (
            "Reviewed successor metadata:\n\n"
            "```phoenix-codex-successor\n"
            f"{json.dumps(payload, sort_keys=True)}\n"
            "```"
        )
        if include_execution:
            body += (
                "\n\nReviewed execution definition:\n\n"
                "```phoenix-codex-execution\n"
                f"{json.dumps(execution_payload, sort_keys=True)}\n"
                "```"
            )
    return {"number": number, "title": title, "state": "OPEN", "body": body}


def _propose(
    repository: Path,
    evidence: Path,
    services: FakeServices,
    **kwargs: Any,
) -> dict[str, object]:
    if services.root is None:
        services.root = repository
    return propose_codex_successor(
        repository_root=repository,
        verification_evidence_path=evidence,
        services=services,
        **kwargs,
    )


def test_valid_verified_candidate_returns_one_bounded_proposal(
    repository: Path,
    tmp_path: Path,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")
    services = FakeServices(issues=[_issue()])

    result = _propose(repository, evidence, services)

    assert result == {
        "schema_version": "codex-successor-proposal.v2",
        "status": "success",
        "category": "successor_proposed",
        "verified_base_sha": HEAD,
        "verification_id": VERIFICATION_ID,
        "candidate_count": 1,
        "selected_issue_number": 391,
        "selected_task_id": "TASK-076",
        "selected_title": "TASK-076: Record the next autonomy milestone",
        "selected_priority": 50,
        "selected_risk_class": "low",
        "selected_execution_class": "docs-only-supervised",
        "selected_allowed_paths": [ALLOWED_PATH],
        "selected_expected_pr_title": "docs: record the next autonomy milestone",
        "selected_execution_definition": _execution_definition(),
        "selection_reason": "highest_priority_then_lowest_issue_number",
        "proposal_fingerprint": result["proposal_fingerprint"],
        "proposal_ready_for_architecture_review": True,
    }
    assert len(str(result["proposal_fingerprint"])) == 64
    assert services.calls == [
        "canonical_repository_root",
        "repository_state",
        "tracked_paths",
        "list_open_issues",
    ]


def _python_repository_paths(repository: Path) -> tuple[str, ...]:
    paths = (
        "src/phoenix_office/dev/codex_runner.py",
        "src/phoenix_office/dev/codex_successor.py",
        "src/phoenix_office/dev/codex_future.py",
        "src/phoenix_office/dev/__init__.py",
        "src/phoenix_office/core/contracts.py",
        "src/phoenix_office/cli.py",
        "tests/test_codex_runner.py",
        "tests/test_codex_successor.py",
        "tests/test_codex_wsl.py",
        "tests/test_cli.py",
    )
    for path_text in paths:
        path = repository / path_text
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# synthetic tracked source\n", encoding="utf-8")
    return paths


@pytest.mark.parametrize(
    "allowed_paths",
    [
        [
            "src/phoenix_office/dev/codex_successor.py",
            "tests/test_codex_successor.py",
        ],
        [
            "src/phoenix_office/dev/codex_runner.py",
            "src/phoenix_office/dev/codex_successor.py",
            "tests/test_codex_successor.py",
        ],
    ],
)
def test_bounded_python_valid_two_and_three_path_candidates(
    repository: Path,
    tmp_path: Path,
    allowed_paths: list[str],
) -> None:
    tracked = _python_repository_paths(repository)
    evidence = _write_evidence(tmp_path / "verification.json")
    candidate = _candidate_metadata(
        execution_class="bounded-python-supervised",
        allowed_paths=sorted(allowed_paths),
        expected_pr_title="dev: refine successor policy",
        risk_class="low",
    )
    execution = _execution_definition(objective="Develop Python code and focused tests safely.")

    result = _propose(
        repository,
        evidence,
        FakeServices(paths=tracked, issues=[_issue(metadata=candidate, execution=execution)]),
    )

    assert result["category"] == "successor_proposed"
    assert result["selected_execution_class"] == "bounded-python-supervised"
    assert result["proposal_ready_for_architecture_review"] is True


@pytest.mark.parametrize(
    ("candidate_updates", "objective"),
    [
        ({"allowed_paths": ["src/phoenix_office/dev/codex_successor.py"]}, None),
        (
            {
                "allowed_paths": [
                    "src/phoenix_office/dev/codex_runner.py",
                    "src/phoenix_office/dev/codex_successor.py",
                    "tests/test_codex_runner.py",
                    "tests/test_codex_successor.py",
                ]
            },
            None,
        ),
        (
            {
                "allowed_paths": [
                    "src/phoenix_office/dev/codex_future.py",
                    "tests/test_codex_successor.py",
                ]
            },
            None,
        ),
        ({"allowed_paths": [ALLOWED_PATH, "tests/test_codex_successor.py"]}, None),
        (
            {"allowed_paths": ["tests/test_codex_runner.py", "tests/test_codex_successor.py"]},
            None,
        ),
        (
            {
                "allowed_paths": [
                    "src/phoenix_office/dev/codex_runner.py",
                    "src/phoenix_office/dev/codex_successor.py",
                ]
            },
            None,
        ),
        (
            {
                "allowed_paths": [
                    "src/phoenix_office/dev/__init__.py",
                    "tests/test_codex_successor.py",
                ]
            },
            None,
        ),
        (
            {
                "allowed_paths": [
                    "src/phoenix_office/core/contracts.py",
                    "tests/test_codex_successor.py",
                ]
            },
            None,
        ),
        (
            {"allowed_paths": ["src/phoenix_office/cli.py", "tests/test_codex_successor.py"]},
            None,
        ),
        (
            {"allowed_paths": ["src/phoenix_office/dev/codex_runner.py", "tests/test_cli.py"]},
            None,
        ),
        ({"risk_class": "medium"}, None),
        ({"expected_pr_title": "docs: wrong class"}, None),
        ({"execution_class": "unknown-supervised"}, None),
        ({}, "Clarify the reviewed milestone safely."),
    ],
)
def test_bounded_python_ineligible_candidates_never_become_ready(
    repository: Path,
    tmp_path: Path,
    candidate_updates: dict[str, object],
    objective: str | None,
) -> None:
    tracked = tuple(
        path
        for path in _python_repository_paths(repository)
        if path != "src/phoenix_office/dev/codex_future.py"
    )
    evidence = _write_evidence(tmp_path / "verification.json")
    defaults: dict[str, object] = {
        "execution_class": "bounded-python-supervised",
        "allowed_paths": [
            "src/phoenix_office/dev/codex_successor.py",
            "tests/test_codex_successor.py",
        ],
        "expected_pr_title": "dev: refine successor policy",
        "risk_class": "low",
    }
    defaults.update(candidate_updates)
    execution = _execution_definition(
        objective=objective or "Develop Python code and focused tests safely."
    )

    result = _propose(
        repository,
        evidence,
        FakeServices(
            paths=tracked,
            issues=[_issue(metadata=_candidate_metadata(**defaults), execution=execution)],
        ),
    )

    assert result["proposal_ready_for_architecture_review"] is False
    assert result["category"] in {
        "malformed_candidate_metadata",
        "malformed_execution_definition",
        "unsafe_allowed_path",
    }


def test_authorization_incompatible_objective_is_not_proposal_ready(
    repository: Path,
    tmp_path: Path,
) -> None:
    task_077_objective = (
        "Record the first verified successor-driven supervised Codex autonomy "
        "pilot in the Phoenix development progress dashboard."
    )
    evidence = _write_evidence(tmp_path / "verification.json")
    issue = _issue(
        execution=_execution_definition(objective=task_077_objective),
    )

    result = _propose(repository, evidence, FakeServices(issues=[issue]))

    assert result["category"] == "malformed_execution_definition"
    assert result["proposal_ready_for_architecture_review"] is False
    assert result["proposal_fingerprint"] is None


def test_task_spec_issue_number_ceiling_is_shared() -> None:
    assert CODEX_PILOT_TASK_SPEC_MAX_ISSUE_NUMBER == 9_999_999


def test_maximum_task_spec_issue_number_is_proposal_ready(
    repository: Path,
    tmp_path: Path,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")
    issue = _issue(CODEX_PILOT_TASK_SPEC_MAX_ISSUE_NUMBER)

    result = _propose(repository, evidence, FakeServices(issues=[issue]))

    assert result["category"] == "successor_proposed"
    assert result["selected_issue_number"] == 9_999_999
    assert result["proposal_ready_for_architecture_review"] is True


def test_issue_above_task_spec_ceiling_is_not_proposal_ready(
    repository: Path,
    tmp_path: Path,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")
    issue = _issue(CODEX_PILOT_TASK_SPEC_MAX_ISSUE_NUMBER + 1)

    result = _propose(repository, evidence, FakeServices(issues=[issue]))

    assert result["category"] == "malformed_candidate_metadata"
    assert result["selected_issue_number"] is None
    assert result["proposal_ready_for_architecture_review"] is False


def test_successful_proposal_parser_uses_task_spec_issue_number_ceiling(
    repository: Path,
    tmp_path: Path,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")
    result = _propose(
        repository,
        evidence,
        FakeServices(issues=[_issue()]),
    )
    maximum = {
        **result,
        "selected_issue_number": CODEX_PILOT_TASK_SPEC_MAX_ISSUE_NUMBER,
    }
    above_maximum = {
        **result,
        "selected_issue_number": CODEX_PILOT_TASK_SPEC_MAX_ISSUE_NUMBER + 1,
    }

    parsed = parse_codex_successor_proposal_payload(maximum)

    assert parsed.issue_number == 9_999_999
    with pytest.raises(CodexSuccessorProposalError) as error:
        parse_codex_successor_proposal_payload(above_maximum)
    assert error.value.category == "malformed_proposal"


def test_dependency_issue_number_bound_remains_independent(
    repository: Path,
    tmp_path: Path,
) -> None:
    dependency_issue = CODEX_PILOT_TASK_SPEC_MAX_ISSUE_NUMBER + 1
    evidence = _write_evidence(tmp_path / "verification.json")
    issue = _issue(
        metadata=_candidate_metadata(depends_on=[dependency_issue]),
    )
    services = FakeServices(
        issues=[issue],
        dependencies={
            dependency_issue: {
                "number": dependency_issue,
                "state": "CLOSED",
                "stateReason": "COMPLETED",
            }
        },
    )

    result = _propose(repository, evidence, services)

    assert result["category"] == "successor_proposed"
    assert services.calls[-1] == f"read_dependency:{dependency_issue}"


def test_priority_descending_deterministically_selects_highest(
    repository: Path,
    tmp_path: Path,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")
    low = _issue(391, metadata=_candidate_metadata(priority=10))
    high = _issue(
        392,
        title="TASK-077: Higher priority",
        metadata=_candidate_metadata(task_id="TASK-077", priority=90),
    )

    result = _propose(repository, evidence, FakeServices(issues=[low, high]))

    assert result["candidate_count"] == 2
    assert result["selected_issue_number"] == 392


def test_issue_number_is_final_tiebreak(
    repository: Path,
    tmp_path: Path,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")
    later = _issue(399, title="TASK-079: Later", metadata=_candidate_metadata())
    earlier = _issue(392, title="TASK-078: Earlier", metadata=_candidate_metadata())

    result = _propose(repository, evidence, FakeServices(issues=[later, earlier]))

    assert result["candidate_count"] == 2
    assert result["selected_issue_number"] == 392


def test_legacy_and_deferred_issues_are_ignored(
    repository: Path,
    tmp_path: Path,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")
    legacy = _issue(382, body="TASK-071 remains open but has no candidate contract.")
    deferred = _issue(
        391,
        metadata=_candidate_metadata(candidate_state="deferred"),
    )

    result = _propose(
        repository,
        evidence,
        FakeServices(issues=[legacy, deferred]),
    )

    assert result["status"] == "blocked"
    assert result["category"] == "no_eligible_successor"
    assert result["candidate_count"] == 0


def test_non_autonomy_queue_is_ignored(repository: Path, tmp_path: Path) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")
    issue = _issue(metadata=_candidate_metadata(queue="manual"))

    result = _propose(repository, evidence, FakeServices(issues=[issue]))

    assert result["category"] == "no_eligible_successor"


def test_deferred_candidate_does_not_require_current_tracked_path(
    repository: Path,
    tmp_path: Path,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")
    issue = _issue(
        metadata=_candidate_metadata(
            candidate_state="deferred",
            allowed_paths=["docs/development/future.md"],
        )
    )

    result = _propose(repository, evidence, FakeServices(issues=[issue]))

    assert result["category"] == "no_eligible_successor"


@pytest.mark.parametrize(
    ("state", "reason", "expected_category"),
    [
        ("OPEN", None, "no_eligible_successor"),
        ("CLOSED", "NOT_PLANNED", "no_eligible_successor"),
        ("CLOSED", "COMPLETED", "successor_proposed"),
    ],
)
def test_dependency_must_be_proven_completed(
    repository: Path,
    tmp_path: Path,
    state: str,
    reason: str | None,
    expected_category: str,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")
    candidate = _issue(metadata=_candidate_metadata(depends_on=[390]))
    services = FakeServices(
        issues=[candidate],
        dependencies={390: {"number": 390, "state": state, "stateReason": reason}},
    )

    result = _propose(repository, evidence, services)

    assert result["category"] == expected_category
    assert services.calls[-1] == "read_dependency:390"


def test_unknown_dependency_fails_closed(repository: Path, tmp_path: Path) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")
    candidate = _issue(metadata=_candidate_metadata(depends_on=[390]))

    result = _propose(repository, evidence, FakeServices(issues=[candidate]))

    assert result["status"] == "blocked"
    assert result["category"] == "github_read_failed"


@pytest.mark.parametrize(
    ("state", "category"),
    [
        (RepositoryState("feature", HEAD, True), "non_main_checkout"),
        (RepositoryState("main", "not-a-sha", True), "invalid_head"),
        (RepositoryState("main", HEAD, False), "dirty_worktree"),
    ],
)
def test_repository_state_failures_block_before_evidence_or_github(
    repository: Path,
    tmp_path: Path,
    state: RepositoryState,
    category: str,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")
    services = FakeServices(state=state, issues=[_issue()])

    result = _propose(repository, evidence, services)

    assert result["category"] == category
    assert services.calls == ["canonical_repository_root", "repository_state"]


@pytest.mark.parametrize(
    "repository_identity",
    ["SomeoneElse/phoenix-office", "Phoenix-AI-Platform/unrelated", None],
)
def test_noncanonical_repository_identity_fails_closed(
    repository: Path,
    tmp_path: Path,
    repository_identity: str | None,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")
    services = FakeServices(
        state=RepositoryState("main", HEAD, True, repository_identity),
        issues=[_issue()],
    )

    result = _propose(repository, evidence, services)

    assert result["category"] == "repository_identity_mismatch"
    assert services.calls == ["canonical_repository_root", "repository_state"]


@pytest.mark.parametrize(
    "origin",
    [
        "https://github.com/Phoenix-AI-Platform/phoenix-office.git",
        "git@github.com:Phoenix-AI-Platform/phoenix-office.git",
        "ssh://git@github.com/Phoenix-AI-Platform/phoenix-office.git",
    ],
)
def test_existing_canonical_origin_semantics_are_reused(
    repository: Path,
    origin: str,
) -> None:
    def run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        arguments = argv[3:]
        if arguments == ["rev-parse", "--show-toplevel"]:
            output = str(repository)
        elif arguments == ["branch", "--show-current"]:
            output = "main"
        elif arguments == ["rev-parse", "HEAD"]:
            output = HEAD
        elif arguments == ["status", "--porcelain=v1"]:
            output = ""
        elif arguments == ["remote", "get-url", "origin"]:
            output = origin
        else:  # pragma: no cover - test contract guard
            raise AssertionError(argv)
        return subprocess.CompletedProcess(argv, 0, output, "")

    services = SystemCodexSuccessorServices(repository, process_runner=run)

    assert services.canonical_repository_root() == repository.resolve()
    assert services.repository_state().repository_identity == REPOSITORY_IDENTITY


def test_missing_origin_uses_bounded_identity_failure(repository: Path) -> None:
    def run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        arguments = argv[3:]
        if arguments == ["rev-parse", "--show-toplevel"]:
            return subprocess.CompletedProcess(argv, 0, str(repository), "")
        if arguments == ["remote", "get-url", "origin"]:
            return subprocess.CompletedProcess(argv, 2, "", "missing origin")
        output = {
            ("branch", "--show-current"): "main",
            ("rev-parse", "HEAD"): HEAD,
            ("status", "--porcelain=v1"): "",
        }[tuple(arguments)]
        return subprocess.CompletedProcess(argv, 0, output, "")

    services = SystemCodexSuccessorServices(repository, process_runner=run)

    with pytest.raises(CodexSuccessorProposalError) as error:
        services.repository_state()

    assert error.value.category == "repository_identity_mismatch"
    assert "missing origin" not in str(error.value)


@pytest.mark.parametrize("from_subdirectory", [False, True])
def test_root_and_subdirectory_invocation_share_one_canonical_root(
    repository: Path,
    tmp_path: Path,
    from_subdirectory: bool,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")
    invocation_path = repository / "docs" if from_subdirectory else repository
    calls: list[tuple[list[str], dict[str, object]]] = []

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs))
        if argv[0] == "gh":
            return subprocess.CompletedProcess(argv, 0, json.dumps([_issue()]), "")
        arguments = argv[3:]
        output = {
            ("rev-parse", "--show-toplevel"): str(repository),
            ("branch", "--show-current"): "main",
            ("rev-parse", "HEAD"): HEAD,
            ("status", "--porcelain=v1"): "",
            ("remote", "get-url", "origin"): (
                "https://github.com/Phoenix-AI-Platform/phoenix-office.git"
            ),
            ("ls-files", "-z"): f"{ALLOWED_PATH}\0",
        }[tuple(arguments)]
        return subprocess.CompletedProcess(argv, 0, output, "")

    services = SystemCodexSuccessorServices(invocation_path, process_runner=run)
    result = propose_codex_successor(
        repository_root=invocation_path,
        verification_evidence_path=evidence,
        services=services,
    )

    assert result["category"] == "successor_proposed"
    assert services.canonical_repository_root() == repository.resolve()
    for argv, kwargs in calls[1:]:
        assert Path(str(kwargs["cwd"])).resolve() == repository.resolve()
        if argv[0] == "git":
            assert Path(argv[2]).resolve() == repository.resolve()


def test_outside_repository_is_rejected_before_other_gates(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    evidence = _write_evidence(tmp_path / "verification.json")

    def run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 128, "", "not a repository")

    services = SystemCodexSuccessorServices(outside, process_runner=run)
    result = propose_codex_successor(
        repository_root=outside,
        verification_evidence_path=evidence,
        services=services,
    )

    assert result["category"] == "outside_repository"


@pytest.mark.parametrize(
    ("overrides", "category"),
    [
        ({"head": "b" * 40}, "verification_head_mismatch"),
        ({"health": "fail"}, "verification_failed_or_partial"),
        ({"coverage": "partial"}, "verification_failed_or_partial"),
        ({"office_entries": 2}, "verification_repository_ambiguous"),
    ],
)
def test_invalid_or_stale_evidence_blocks_before_github(
    repository: Path,
    tmp_path: Path,
    overrides: dict[str, object],
    category: str,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json", **overrides)
    services = FakeServices(issues=[_issue()])

    result = _propose(repository, evidence, services)

    assert result["category"] == category
    assert services.calls == ["canonical_repository_root", "repository_state"]


def test_missing_and_malformed_evidence_are_bounded(
    repository: Path,
    tmp_path: Path,
) -> None:
    missing = _propose(
        repository,
        tmp_path / "missing.json",
        FakeServices(issues=[_issue()]),
    )
    malformed_path = tmp_path / "malformed.json"
    malformed_path.write_text("{", encoding="utf-8")
    malformed = _propose(
        repository,
        malformed_path,
        FakeServices(issues=[_issue()]),
    )

    assert missing["category"] == "missing_verification_evidence"
    assert malformed["category"] == "malformed_verification_evidence"


def test_github_read_failure_is_bounded(repository: Path, tmp_path: Path) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")
    services = FakeServices(failure="github_read_failed")

    result = _propose(repository, evidence, services)

    assert result["status"] == "blocked"
    assert result["category"] == "github_read_failed"
    assert result["selected_issue_number"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {"not": "a list"},
        [{"number": 391}],
        [{"number": 391, "title": "valid", "state": "CLOSED", "body": ""}],
        [
            {"number": 391, "title": "valid", "state": "OPEN", "body": ""},
            {"number": 391, "title": "duplicate", "state": "OPEN", "body": ""},
        ],
    ],
)
def test_malformed_github_candidate_payload_fails_closed(
    repository: Path,
    tmp_path: Path,
    payload: object,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")

    result = _propose(repository, evidence, FakeServices(issues=payload))

    assert result["category"] == "malformed_candidate_payload"


@pytest.mark.parametrize(
    "body",
    [
        '```phoenix-codex-successor\n{"schema_version":"bad"}\n```',
        "```phoenix-codex-successor\nnot-json\n```",
        ("```phoenix-codex-successor\n{}\n```\n```phoenix-codex-successor\n{}\n```"),
    ],
)
def test_malformed_explicit_candidate_metadata_fails_closed(
    repository: Path,
    tmp_path: Path,
    body: str,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")

    result = _propose(
        repository,
        evidence,
        FakeServices(issues=[_issue(body=body)]),
    )

    assert result["category"] == "malformed_candidate_metadata"


def test_ready_candidate_without_execution_definition_is_not_proposal_ready(
    repository: Path,
    tmp_path: Path,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")

    result = _propose(
        repository,
        evidence,
        FakeServices(issues=[_issue(include_execution=False)]),
    )

    assert result["category"] == "missing_execution_definition"
    assert result["proposal_ready_for_architecture_review"] is False


@pytest.mark.parametrize(
    "execution",
    [
        {"schema_version": "bad"},
        _execution_definition(branch_name="feature/unsafe"),
        _execution_definition(control_references={}),
    ],
)
def test_malformed_execution_definition_fails_closed(
    repository: Path,
    tmp_path: Path,
    execution: dict[str, object],
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")

    result = _propose(
        repository,
        evidence,
        FakeServices(issues=[_issue(execution=execution)]),
    )

    assert result["category"] == "malformed_execution_definition"


def test_candidate_execution_task_identity_must_match(
    repository: Path,
    tmp_path: Path,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")

    result = _propose(
        repository,
        evidence,
        FakeServices(issues=[_issue(execution=_execution_definition(task_id="TASK-999"))]),
    )

    assert result["category"] == "candidate_execution_mismatch"


@pytest.mark.parametrize(
    "allowed_paths",
    [
        ["src/phoenix_office/cli.py"],
        ["docs/development/../private.md"],
        ["docs/development/missing.md"],
        ["C:/private/customer.md"],
    ],
)
def test_unsafe_or_untracked_allowed_path_is_rejected(
    repository: Path,
    tmp_path: Path,
    allowed_paths: list[str],
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")
    candidate = _issue(metadata=_candidate_metadata(allowed_paths=allowed_paths))

    result = _propose(repository, evidence, FakeServices(issues=[candidate]))

    assert result["category"] == "unsafe_allowed_path"


@pytest.mark.parametrize(
    ("title", "expected_category"),
    [
        ("docs: record a bounded successor", "successor_proposed"),
        ("feat: add a successor", "malformed_candidate_metadata"),
        ("chore: update a successor", "malformed_candidate_metadata"),
        ("docs: ", "malformed_candidate_metadata"),
        ("docs: token=unsafe-value", "malformed_candidate_metadata"),
    ],
)
def test_docs_only_candidate_requires_existing_docs_pr_title_contract(
    repository: Path,
    tmp_path: Path,
    title: str,
    expected_category: str,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")
    candidate = _issue(metadata=_candidate_metadata(expected_pr_title=title))

    result = _propose(repository, evidence, FakeServices(issues=[candidate]))

    assert result["category"] == expected_category
    assert result["proposal_ready_for_architecture_review"] is (
        expected_category == "successor_proposed"
    )


def test_fingerprint_is_deterministic_and_binds_dependency_facts(
    repository: Path,
    tmp_path: Path,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")
    candidate = _issue(metadata=_candidate_metadata(depends_on=[390]))
    dependencies = {390: {"number": 390, "state": "CLOSED", "stateReason": "COMPLETED"}}

    first = _propose(
        repository,
        evidence,
        FakeServices(issues=[candidate], dependencies=dependencies),
    )
    second = _propose(
        repository,
        evidence,
        FakeServices(issues=[candidate], dependencies=dependencies),
    )

    assert first["proposal_fingerprint"] == second["proposal_fingerprint"]
    assert first["proposal_fingerprint"] is not None


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("objective", "Document a materially different reviewed objective."),
        (
            "acceptance_criteria",
            ["A different reviewed acceptance criterion is satisfied."],
        ),
        ("branch_name", "codex/issue-076-alternate"),
        ("budget_ceiling", 225001),
        ("timeout_seconds", 1801),
        (
            "control_references",
            {
                control_id: f"{control_id}-changed"
                for control_id in CODEX_PILOT_TASK_SPEC_CONTROL_IDS
            },
        ),
    ],
)
def test_execution_definition_is_bound_into_proposal_fingerprint(
    repository: Path,
    tmp_path: Path,
    field: str,
    replacement: object,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")
    original = _propose(
        repository,
        evidence,
        FakeServices(issues=[_issue()]),
    )
    changed = _propose(
        repository,
        evidence,
        FakeServices(issues=[_issue(execution=_execution_definition(**{field: replacement}))]),
    )

    assert original["proposal_fingerprint"] != changed["proposal_fingerprint"]


def test_execution_class_is_bound_into_proposal_fingerprint(
    repository: Path,
) -> None:
    candidate = parse_selected_codex_successor_issue(
        _issue(),
        repository_root=repository,
        tracked_paths=(ALLOWED_PATH,),
    )
    verification = VerificationState(VERIFICATION_ID, HEAD)

    docs_fingerprint = codex_successor_proposal_fingerprint(
        verification=verification,
        candidate=candidate,
        dependency_facts=(),
    )
    python_fingerprint = codex_successor_proposal_fingerprint(
        verification=verification,
        candidate=replace(
            candidate,
            execution_class="bounded-python-supervised",
        ),
        dependency_facts=(),
    )

    assert docs_fingerprint != python_fingerprint


def test_fingerprint_and_serialization_failures_are_bounded(
    repository: Path,
    tmp_path: Path,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")
    services = FakeServices(issues=[_issue()])

    serialization = _propose(
        repository,
        evidence,
        services,
        canonical_serializer=lambda _value: (_ for _ in ()).throw(TypeError()),
    )
    fingerprint = _propose(
        repository,
        evidence,
        FakeServices(issues=[_issue()]),
        fingerprint_function=lambda _value: "not-a-fingerprint",
    )

    assert serialization["category"] == "serialization_uncertainty"
    assert fingerprint["category"] == "fingerprint_failure"
    assert serialization["proposal_fingerprint"] is None
    assert fingerprint["proposal_fingerprint"] is None


def test_public_result_never_contains_raw_payload_paths_or_secrets(
    repository: Path,
    tmp_path: Path,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")
    secret = "token=super-secret-value"
    issue = _issue(title=f"TASK-076: {secret}")

    result = _propose(repository, evidence, FakeServices(issues=[issue]))
    encoded = json.dumps(result, sort_keys=True)

    assert result["category"] == "malformed_candidate_payload"
    assert secret not in encoded
    assert str(repository) not in encoded
    assert str(evidence) not in encoded


def test_system_github_adapter_uses_only_read_commands_and_bounded_environment(
    repository: Path,
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs))
        if argv[0] == "git":
            output = str(repository)
        elif argv[1:3] == ["issue", "list"]:
            output = "[]"
        elif argv[3] == "391":
            output = json.dumps(_issue())
        else:
            output = json.dumps({"number": 390, "state": "CLOSED", "stateReason": "COMPLETED"})
        return subprocess.CompletedProcess(argv, 0, output, "")

    environment = {
        "PATH": "safe-path",
        "USERPROFILE": "safe-profile",
        "GH_TOKEN": "preferred-gh-token",
        "GITHUB_TOKEN": "fallback-github-token",
        "OPENAI_API_KEY": "forbidden-token",
        "AWS_SECRET_ACCESS_KEY": "forbidden-secret",
    }
    services = SystemCodexSuccessorServices(
        repository,
        process_runner=run,
        environment=environment,
    )

    assert services.list_open_issues() == []
    assert services.read_issue(391) == _issue()
    assert services.read_dependency(390) == {
        "number": 390,
        "state": "CLOSED",
        "stateReason": "COMPLETED",
    }
    github_calls = [call for call in calls if call[0][0] == "gh"]
    assert [call[0][1:3] for call in github_calls] == [
        ["issue", "list"],
        ["issue", "view"],
        ["issue", "view"],
    ]
    assert all(call[1]["shell"] is False for call in calls)
    for argv, kwargs in calls:
        child_environment = kwargs["env"]
        assert isinstance(child_environment, dict)
        if argv[0] == "gh":
            assert child_environment["GH_TOKEN"] == "preferred-gh-token"
        else:
            assert "GH_TOKEN" not in child_environment
        assert "GITHUB_TOKEN" not in child_environment
        assert "OPENAI_API_KEY" not in child_environment
        assert "AWS_SECRET_ACCESS_KEY" not in child_environment


def test_bounded_environment_excludes_arbitrary_credentials() -> None:
    result = _bounded_process_environment(
        {
            "PATH": "safe",
            "TEMP": "safe-temp",
            "GH_TOKEN": "secret",
            "SECRET_THING": "secret",
            "UNRELATED": "value",
        }
    )

    assert result["PATH"] == "safe"
    assert result["TEMP"] == "safe-temp"
    assert result["GH_PROMPT_DISABLED"] == "1"
    assert "GH_TOKEN" not in result
    assert "SECRET_THING" not in result
    assert "UNRELATED" not in result


def test_github_auth_environment_supports_tokens_with_deterministic_precedence() -> None:
    gh_only = _bounded_process_environment(
        {"PATH": "safe", "GH_TOKEN": "gh-auth-value"},
        include_github_auth=True,
    )
    github_only = _bounded_process_environment(
        {"PATH": "safe", "GITHUB_TOKEN": "github-auth-value"},
        include_github_auth=True,
    )
    both = _bounded_process_environment(
        {
            "PATH": "safe",
            "GH_TOKEN": "preferred-gh-value",
            "GITHUB_TOKEN": "fallback-github-value",
            "OPENAI_API_KEY": "unrelated-secret",
            "AWS_SECRET_ACCESS_KEY": "unrelated-secret",
        },
        include_github_auth=True,
    )

    assert gh_only["GH_TOKEN"] == "gh-auth-value"
    assert "GITHUB_TOKEN" not in gh_only
    assert github_only["GITHUB_TOKEN"] == "github-auth-value"
    assert "GH_TOKEN" not in github_only
    assert both["GH_TOKEN"] == "preferred-gh-value"
    assert "GITHUB_TOKEN" not in both
    assert "OPENAI_API_KEY" not in both
    assert "AWS_SECRET_ACCESS_KEY" not in both


def test_github_auth_token_never_enters_public_or_exception_output(
    repository: Path,
    tmp_path: Path,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")
    secret_token = "gh-auth-value-never-public"

    def run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if argv[0] == "gh":
            return subprocess.CompletedProcess(argv, 1, secret_token, secret_token)
        arguments = argv[3:]
        output = {
            ("rev-parse", "--show-toplevel"): str(repository),
            ("branch", "--show-current"): "main",
            ("rev-parse", "HEAD"): HEAD,
            ("status", "--porcelain=v1"): "",
            ("remote", "get-url", "origin"): (
                "https://github.com/Phoenix-AI-Platform/phoenix-office.git"
            ),
            ("ls-files", "-z"): f"{ALLOWED_PATH}\0",
        }[tuple(arguments)]
        return subprocess.CompletedProcess(argv, 0, output, "")

    services = SystemCodexSuccessorServices(
        repository,
        process_runner=run,
        environment={"PATH": "safe", "GH_TOKEN": secret_token},
    )
    result = propose_codex_successor(
        repository_root=repository,
        verification_evidence_path=evidence,
        services=services,
    )

    assert result["category"] == "github_read_failed"
    assert secret_token not in json.dumps(result, sort_keys=True)
    with pytest.raises(CodexSuccessorProposalError) as error:
        services.list_open_issues()
    assert secret_token not in str(error.value)


def test_selector_has_no_mutation_or_execution_authority(
    repository: Path,
    tmp_path: Path,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")
    services = FakeServices(issues=[_issue()])

    result = _propose(repository, evidence, services)

    assert result["status"] == "success"
    assert set(services.calls) <= {
        "canonical_repository_root",
        "repository_state",
        "tracked_paths",
        "list_open_issues",
    }
    for forbidden in (
        "create_issue",
        "update_issue",
        "create_claim",
        "build_package",
        "invoke_codex",
        "create_branch",
        "commit",
        "push",
        "create_pull_request",
        "merge",
        "retry",
    ):
        assert not hasattr(services, forbidden)


def test_cli_json_surface_returns_success(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    result = {
        "schema_version": "codex-successor-proposal.v2",
        "status": "success",
        "category": "successor_proposed",
        "proposal_ready_for_architecture_review": True,
    }
    monkeypatch.setattr(cli, "propose_codex_successor", lambda **_kwargs: result)
    monkeypatch.setattr(cli, "SystemCodexSuccessorServices", lambda _path: object())

    exit_code = cli.main(
        [
            "dev",
            "codex-successor-propose",
            "--verification-evidence",
            "verification.json",
            "--json",
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == result


def test_cli_blocked_result_returns_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    result = {
        "schema_version": "codex-successor-proposal.v2",
        "status": "blocked",
        "category": "no_eligible_successor",
        "proposal_ready_for_architecture_review": False,
    }
    monkeypatch.setattr(cli, "propose_codex_successor", lambda **_kwargs: result)
    monkeypatch.setattr(cli, "SystemCodexSuccessorServices", lambda _path: object())

    exit_code = cli.main(
        [
            "dev",
            "codex-successor-propose",
            "--verification-evidence",
            "verification.json",
            "--json",
        ]
    )

    assert exit_code == 1
