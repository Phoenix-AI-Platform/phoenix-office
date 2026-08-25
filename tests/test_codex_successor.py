from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from phoenix_office import cli
from phoenix_office.dev.codex_successor import (
    REPOSITORY_IDENTITY,
    SUCCESSOR_CANDIDATE_SCHEMA_VERSION,
    CodexSuccessorProposalError,
    RepositoryState,
    SystemCodexSuccessorServices,
    _bounded_process_environment,
    propose_codex_successor,
)

HEAD = "a" * 40
VERIFICATION_ID = "12345678-1234-4234-9234-123456789abc"
ALLOWED_PATH = "docs/development/progress_dashboard.md"


@dataclass
class FakeServices:
    state: RepositoryState = RepositoryState("main", HEAD, True)
    issues: object = field(default_factory=list)
    dependencies: dict[int, object] = field(default_factory=dict)
    paths: tuple[str, ...] = (ALLOWED_PATH,)
    failure: str | None = None
    calls: list[str] = field(default_factory=list)

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


def _issue(
    number: int = 391,
    *,
    title: str = "TASK-076: Record the next autonomy milestone",
    metadata: dict[str, object] | None = None,
    body: str | None = None,
) -> dict[str, object]:
    if body is None:
        payload = metadata if metadata is not None else _candidate_metadata()
        body = (
            "Reviewed successor metadata:\n\n"
            "```phoenix-codex-successor\n"
            f"{json.dumps(payload, sort_keys=True)}\n"
            "```"
        )
    return {"number": number, "title": title, "state": "OPEN", "body": body}


def _propose(
    repository: Path,
    evidence: Path,
    services: FakeServices,
    **kwargs: Any,
) -> dict[str, object]:
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
        "schema_version": "codex-successor-proposal.v1",
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
        "selection_reason": "highest_priority_then_lowest_issue_number",
        "proposal_fingerprint": result["proposal_fingerprint"],
        "proposal_ready_for_architecture_review": True,
    }
    assert len(str(result["proposal_fingerprint"])) == 64
    assert services.calls == ["repository_state", "tracked_paths", "list_open_issues"]


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
    assert services.calls == ["repository_state"]


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
    assert services.calls == ["repository_state"]


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
        "```phoenix-codex-successor\n{\"schema_version\":\"bad\"}\n```",
        "```phoenix-codex-successor\nnot-json\n```",
        (
            "```phoenix-codex-successor\n{}\n```\n"
            "```phoenix-codex-successor\n{}\n```"
        ),
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


def test_fingerprint_is_deterministic_and_binds_dependency_facts(
    repository: Path,
    tmp_path: Path,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")
    candidate = _issue(metadata=_candidate_metadata(depends_on=[390]))
    dependencies = {
        390: {"number": 390, "state": "CLOSED", "stateReason": "COMPLETED"}
    }

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
        output = "[]" if argv[1:3] == ["issue", "list"] else json.dumps(
            {"number": 390, "state": "CLOSED", "stateReason": "COMPLETED"}
        )
        return subprocess.CompletedProcess(argv, 0, output, "")

    environment = {
        "PATH": "safe-path",
        "USERPROFILE": "safe-profile",
        "GH_TOKEN": "forbidden-token",
        "GITHUB_TOKEN": "forbidden-token",
        "OPENAI_API_KEY": "forbidden-token",
        "AWS_SECRET_ACCESS_KEY": "forbidden-secret",
    }
    services = SystemCodexSuccessorServices(
        repository,
        process_runner=run,
        environment=environment,
    )

    assert services.list_open_issues() == []
    assert services.read_dependency(390) == {
        "number": 390,
        "state": "CLOSED",
        "stateReason": "COMPLETED",
    }
    assert [call[0][1:3] for call in calls] == [
        ["issue", "list"],
        ["issue", "view"],
    ]
    assert all(call[1]["shell"] is False for call in calls)
    for _argv, kwargs in calls:
        child_environment = kwargs["env"]
        assert isinstance(child_environment, dict)
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


def test_selector_has_no_mutation_or_execution_authority(
    repository: Path,
    tmp_path: Path,
) -> None:
    evidence = _write_evidence(tmp_path / "verification.json")
    services = FakeServices(issues=[_issue()])

    result = _propose(repository, evidence, services)

    assert result["status"] == "success"
    assert set(services.calls) <= {
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
        "schema_version": "codex-successor-proposal.v1",
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
        "schema_version": "codex-successor-proposal.v1",
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
