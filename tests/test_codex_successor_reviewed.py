from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from phoenix_office import cli
from phoenix_office.dev.codex_reviewed import blocked_reviewed_execution_result
from phoenix_office.dev.codex_successor import (
    REPOSITORY_IDENTITY,
    SUCCESSOR_CANDIDATE_SCHEMA_VERSION,
    SUCCESSOR_EXECUTION_SCHEMA_VERSION,
    CodexSuccessorProposalError,
    RepositoryState,
    propose_codex_successor,
)
from phoenix_office.dev.codex_successor_reviewed import (
    SUCCESSOR_REVIEWED_EXECUTION_SCHEMA_VERSION,
    SUCCESSOR_TASK_SPEC_FILENAME,
    execute_approved_codex_successor,
)
from phoenix_office.dev.codex_successor_task_spec import (
    ARCHITECTURE_APPROVAL_DECISION,
    ARCHITECTURE_APPROVAL_SCHEMA_VERSION,
    ARCHITECTURE_APPROVER_ROLE,
    CodexSuccessorTaskSpecError,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_PATH = "docs/development/progress_dashboard.md"
ISSUE_NUMBER = 398
TASK_ID = "TASK-079"
VERIFICATION_ID = "12345678-1234-4234-9234-123456789abc"


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
        "expected_pr_title": "docs: execute one approved successor",
        "execution_class": "docs-only-supervised",
    }
    value.update(updates)
    return value


def _execution(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": SUCCESSOR_EXECUTION_SCHEMA_VERSION,
        "task_id": TASK_ID,
        "objective": "Document one approved successor execution milestone.",
        "branch_name": "codex/issue-079-approved-successor",
        "budget_ceiling": 225000,
        "timeout_seconds": 1800,
        "control_references": {
            control_id: f"{control_id}-reviewed"
            for control_id in cli.CODEX_PILOT_EVIDENCE_CONTROL_REVIEWERS
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
    candidate: dict[str, object] | None = None,
    execution: dict[str, object] | None = None,
    title: str = "TASK-079: Execute an approved successor in one command",
) -> dict[str, object]:
    candidate_payload = candidate or _candidate()
    execution_payload = execution or _execution()
    return {
        "number": ISSUE_NUMBER,
        "title": title,
        "state": "OPEN",
        "body": (
            "```phoenix-codex-successor\n"
            f"{json.dumps(candidate_payload, sort_keys=True)}\n"
            "```\n\n"
            "```phoenix-codex-execution\n"
            f"{json.dumps(execution_payload, sort_keys=True)}\n"
            "```"
        ),
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
    calls: list[str] = field(default_factory=list)

    def canonical_repository_root(self) -> Path:
        self.calls.append("canonical_repository_root")
        return REPOSITORY_ROOT

    def repository_state(self) -> RepositoryState:
        self.calls.append("repository_state")
        return RepositoryState("main", self.head, True, REPOSITORY_IDENTITY)

    def tracked_paths(self) -> tuple[str, ...]:
        self.calls.append("tracked_paths")
        return (ALLOWED_PATH,)

    def list_open_issues(self) -> object:
        self.calls.append("list_open_issues")
        return [self.issue]

    def read_issue(self, issue_number: int) -> object:
        self.calls.append(f"read_issue:{issue_number}")
        return self.issue

    def read_dependency(self, issue_number: int) -> object:
        self.calls.append(f"read_dependency:{issue_number}")
        if issue_number not in self.dependencies:
            raise CodexSuccessorProposalError("dependency_state_unknown")
        return self.dependencies[issue_number]


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


def _artifacts(
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path, dict[str, object], FakeServices]:
    control = tmp_path / "control"
    control.mkdir()
    source = FakeServices(_issue(), _head())
    proposal = propose_codex_successor(
        repository_root=REPOSITORY_ROOT,
        verification_evidence_path=_evidence(control / "verification.json", source.head),
        services=source,
    )
    assert proposal["status"] == "success"
    proposal_path = _write_json(control / "proposal.json", proposal)
    approval_path = _write_json(control / "approval.json", _approval(proposal))
    services = FakeServices(_issue(), source.head)
    return (
        proposal_path,
        approval_path,
        control,
        control / "claim-store.sqlite3",
        proposal,
        services,
    )


def _reviewed_success() -> dict[str, object]:
    return {
        "status": "success",
        "category": "pr_opened_and_stopped",
        "package_build_result": "pass",
        "preclaim_ready": True,
        "authorization_id": "pilot-auth-issue-398-approved",
        "authorization_fingerprint": "a" * 64,
        "runner_invoked": True,
        "claim_created": True,
        "authorization_consumed": True,
        "attempt_id": "pilot-attempt-approved",
        "execution_backend_selected": "wsl2_linux",
        "changed_paths": [ALLOWED_PATH],
        "observed_usage_tokens": 1000,
        "input_tokens": 700,
        "cached_input_tokens": 500,
        "output_tokens": 300,
        "reasoning_output_tokens": 200,
        "authorized_budget_tokens": 225000,
        "usage_overage_tokens": 0,
        "usage_ratio_basis_points": 44,
        "usage_category": "within_budget",
        "phoenix_validation_result": "pass",
        "durable_lifecycle_state": "pr_opened_and_stopped",
        "durable_lifecycle_terminal": False,
        "pr_created_by_runner": True,
        "office_pr": "pr-399",
        "office_pr_head": None,
        "auto_retry_used": False,
        "replacement_authorization_created": False,
        "background_resume_used": False,
        "worker_may_merge": False,
        "pr_merged": False,
    }


def _execute(
    tmp_path: Path,
    *,
    services: FakeServices | None = None,
    reviewed_executor: Any | None = None,
    task_spec_builder: Any | None = None,
) -> dict[str, object]:
    proposal, approval, control, claim, _payload, default_services = _artifacts(
        tmp_path
    )
    kwargs: dict[str, object] = {}
    if reviewed_executor is not None:
        kwargs["reviewed_executor"] = reviewed_executor
    if task_spec_builder is not None:
        kwargs["task_spec_builder"] = task_spec_builder
    return execute_approved_codex_successor(
        proposal_path=proposal,
        architecture_approval_path=approval,
        control_root=control,
        claim_store_path=claim,
        repository_root=REPOSITORY_ROOT,
        evidence_control_reviewers=cli.CODEX_PILOT_EVIDENCE_CONTROL_REVIEWERS,
        package_inspector=lambda *_paths: pytest.fail("package inspector called"),
        runner_invoker=lambda *_paths: pytest.fail("runner invoker called"),
        services=services or default_services,
        **kwargs,
    )


def test_valid_approved_successor_compiles_then_delegates_exactly_once(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    def reviewed(**kwargs: object) -> dict[str, object]:
        calls.append(dict(kwargs))
        task_spec = Path(str(kwargs["task_spec_path"]))
        assert task_spec.name == SUCCESSOR_TASK_SPEC_FILENAME
        assert task_spec.is_file()
        return _reviewed_success()

    proposal, approval, _control, _claim, _payload, services = _artifacts(tmp_path)
    proposal_before = proposal.read_bytes()
    approval_before = approval.read_bytes()
    result = execute_approved_codex_successor(
        proposal_path=proposal,
        architecture_approval_path=approval,
        control_root=proposal.parent,
        claim_store_path=proposal.parent / "claim-store.sqlite3",
        repository_root=REPOSITORY_ROOT,
        evidence_control_reviewers=cli.CODEX_PILOT_EVIDENCE_CONTROL_REVIEWERS,
        package_inspector=lambda *_paths: pytest.fail("inspector called"),
        runner_invoker=lambda *_paths: pytest.fail("runner called"),
        services=services,
        reviewed_executor=reviewed,
    )

    assert len(calls) == 1
    assert result["status"] == "success"
    assert result["category"] == "pr_opened_and_stopped"
    assert result["architecture_approval_validated"] is True
    assert result["task_spec_validated"] is True
    assert result["task_spec_written"] is True
    assert result["runner_invoked"] is True
    assert result["claim_created"] is True
    assert result["authorization_consumed"] is True
    assert result["input_tokens"] == 700
    assert result["cached_input_tokens"] == 500
    assert result["output_tokens"] == 300
    assert result["reasoning_output_tokens"] == 200
    assert result["durable_lifecycle_state"] == "pr_opened_and_stopped"
    assert result["durable_lifecycle_terminal"] is False
    assert result["architecture_approval_created"] is False
    assert result["successor_reselected"] is False
    assert proposal.read_bytes() == proposal_before
    assert approval.read_bytes() == approval_before
    assert "list_open_issues" not in services.calls


def test_stale_base_blocks_before_reviewed_executor(tmp_path: Path) -> None:
    calls = 0

    def reviewed(**_kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return _reviewed_success()

    result = _execute(
        tmp_path,
        services=FakeServices(_issue(), "f" * 40),
        reviewed_executor=reviewed,
    )

    assert result["category"] == "stale_proposal_base_sha"
    assert result["runner_invoked"] is False
    assert result["claim_created"] is False
    assert calls == 0


def test_changed_selected_issue_blocks_before_reviewed_executor(
    tmp_path: Path,
) -> None:
    calls = 0

    def reviewed(**_kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return _reviewed_success()

    changed = _issue(candidate=_candidate(priority=81))
    result = _execute(
        tmp_path,
        services=FakeServices(changed, _head()),
        reviewed_executor=reviewed,
    )

    assert result["category"] == "selected_issue_changed"
    assert result["runner_invoked"] is False
    assert calls == 0


def test_incomplete_dependency_blocks_before_reviewed_executor(
    tmp_path: Path,
) -> None:
    services = FakeServices(
        _issue(),
        _head(),
        dependencies={390: {"number": 390, "state": "OPEN", "stateReason": None}},
    )
    result = _execute(
        tmp_path,
        services=services,
        reviewed_executor=lambda **_kwargs: pytest.fail("reviewed executor called"),
    )

    assert result["category"] == "dependency_not_completed"
    assert result["runner_invoked"] is False
    assert result["authorization_consumed"] is False


def test_fingerprint_mismatch_blocks_before_reviewed_executor(
    tmp_path: Path,
) -> None:
    proposal_path, approval_path, control, claim, proposal, services = _artifacts(
        tmp_path
    )
    proposal["proposal_fingerprint"] = "f" * 64
    _write_json(proposal_path, proposal)
    _write_json(approval_path, _approval(proposal))

    result = execute_approved_codex_successor(
        proposal_path=proposal_path,
        architecture_approval_path=approval_path,
        control_root=control,
        claim_store_path=claim,
        repository_root=REPOSITORY_ROOT,
        evidence_control_reviewers=cli.CODEX_PILOT_EVIDENCE_CONTROL_REVIEWERS,
        package_inspector=lambda *_paths: pytest.fail("inspector called"),
        runner_invoker=lambda *_paths: pytest.fail("runner called"),
        services=services,
        reviewed_executor=lambda **_kwargs: pytest.fail("reviewed executor called"),
    )

    assert result["category"] == "proposal_fingerprint_mismatch"
    assert result["runner_invoked"] is False


@pytest.mark.parametrize(
    ("approval_update", "expected_category"),
    [
        ({"decision": "rejected"}, "approval_not_approved"),
        ({"approver_role": "phoenix"}, "disallowed_approver_role"),
        ({"selected_issue_number": ISSUE_NUMBER + 1}, "approval_binding_mismatch"),
    ],
)
def test_invalid_approval_blocks_before_reviewed_executor(
    tmp_path: Path,
    approval_update: dict[str, object],
    expected_category: str,
) -> None:
    proposal, approval, control, claim, payload, services = _artifacts(tmp_path)
    _write_json(approval, _approval(payload, **approval_update))

    result = execute_approved_codex_successor(
        proposal_path=proposal,
        architecture_approval_path=approval,
        control_root=control,
        claim_store_path=claim,
        repository_root=REPOSITORY_ROOT,
        evidence_control_reviewers=cli.CODEX_PILOT_EVIDENCE_CONTROL_REVIEWERS,
        package_inspector=lambda *_paths: pytest.fail("inspector called"),
        runner_invoker=lambda *_paths: pytest.fail("runner called"),
        services=services,
        reviewed_executor=lambda **_kwargs: pytest.fail("reviewed executor called"),
    )

    assert result["category"] == expected_category
    assert result["runner_invoked"] is False
    assert result["claim_created"] is False


def test_missing_approval_is_not_created_by_command(tmp_path: Path) -> None:
    proposal, approval, control, claim, _payload, services = _artifacts(tmp_path)
    approval.unlink()

    result = execute_approved_codex_successor(
        proposal_path=proposal,
        architecture_approval_path=approval,
        control_root=control,
        claim_store_path=claim,
        repository_root=REPOSITORY_ROOT,
        evidence_control_reviewers=cli.CODEX_PILOT_EVIDENCE_CONTROL_REVIEWERS,
        package_inspector=lambda *_paths: pytest.fail("inspector called"),
        runner_invoker=lambda *_paths: pytest.fail("runner called"),
        services=services,
        reviewed_executor=lambda **_kwargs: pytest.fail("reviewed executor called"),
    )

    assert result["category"] == "approval_receipt_unavailable"
    assert result["architecture_approval_created"] is False
    assert not approval.exists()


def test_task_spec_collision_blocks_before_reviewed_executor(tmp_path: Path) -> None:
    proposal, approval, control, claim, _payload, services = _artifacts(tmp_path)
    (control / SUCCESSOR_TASK_SPEC_FILENAME).write_text("existing", encoding="utf-8")

    result = execute_approved_codex_successor(
        proposal_path=proposal,
        architecture_approval_path=approval,
        control_root=control,
        claim_store_path=claim,
        repository_root=REPOSITORY_ROOT,
        evidence_control_reviewers=cli.CODEX_PILOT_EVIDENCE_CONTROL_REVIEWERS,
        package_inspector=lambda *_paths: pytest.fail("inspector called"),
        runner_invoker=lambda *_paths: pytest.fail("runner called"),
        services=services,
        reviewed_executor=lambda **_kwargs: pytest.fail("reviewed executor called"),
    )

    assert result["category"] == "output_collision"
    assert result["runner_invoked"] is False


def test_compiler_failure_blocks_reviewed_executor(tmp_path: Path) -> None:
    calls = 0

    def compiler(**_kwargs: object) -> dict[str, object]:
        raise CodexSuccessorTaskSpecError("malformed_execution_definition")

    def reviewed(**_kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return _reviewed_success()

    result = _execute(
        tmp_path,
        task_spec_builder=compiler,
        reviewed_executor=reviewed,
    )

    assert result["category"] == "malformed_execution_definition"
    assert result["task_spec_written"] is False
    assert result["runner_invoked"] is False
    assert calls == 0


def test_package_preclaim_failure_remains_fail_closed(tmp_path: Path) -> None:
    reviewed_calls = 0

    def reviewed(**_kwargs: object) -> dict[str, object]:
        nonlocal reviewed_calls
        reviewed_calls += 1
        result = blocked_reviewed_execution_result(
            "generated_package_validation_failed"
        )
        result["package_build_result"] = "blocked"
        result["preclaim_ready"] = False
        return result

    result = _execute(tmp_path, reviewed_executor=reviewed)

    assert reviewed_calls == 1
    assert result["category"] == "generated_package_validation_failed"
    assert result["package_build_result"] == "blocked"
    assert result["preclaim_ready"] is False
    assert result["runner_invoked"] is False
    assert result["claim_created"] is False
    assert result["authorization_consumed"] is False
    assert result["input_tokens"] is None
    assert result["cached_input_tokens"] is None
    assert result["output_tokens"] is None
    assert result["reasoning_output_tokens"] is None


def test_reviewed_executor_exception_is_not_retried(tmp_path: Path) -> None:
    calls = 0

    def reviewed(**_kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        raise RuntimeError("synthetic failure")

    result = _execute(tmp_path, reviewed_executor=reviewed)

    assert calls == 1
    assert result["category"] == "reviewed_execution_internal_failure"
    assert result["auto_retry_used"] is False
    assert result["background_resume_used"] is False
    assert result["runner_invoked"] is False


def test_public_result_is_bounded_and_authority_remains_phoenix_owned(
    tmp_path: Path,
) -> None:
    result = _execute(
        tmp_path,
        reviewed_executor=lambda **_kwargs: _reviewed_success(),
    )
    encoded = json.dumps(result, sort_keys=True)

    assert result["schema_version"] == SUCCESSOR_REVIEWED_EXECUTION_SCHEMA_VERSION
    assert str(tmp_path) not in encoded
    assert "phoenix-codex-execution" not in encoded
    assert result["successor_reselected"] is False
    assert result["architecture_approval_created"] is False
    assert result["auto_retry_used"] is False
    assert result["background_resume_used"] is False
    assert result["worker_may_approve"] is False
    assert result["worker_may_merge"] is False
    assert result["pr_merged"] is False


def test_cli_executes_existing_approval_once_and_returns_bounded_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[dict[str, object]] = []
    expected = _reviewed_success() | {
        "schema_version": SUCCESSOR_REVIEWED_EXECUTION_SCHEMA_VERSION,
        "selected_issue_number": ISSUE_NUMBER,
        "selected_task_id": TASK_ID,
    }

    def execute(**kwargs: object) -> dict[str, object]:
        calls.append(dict(kwargs))
        return expected

    monkeypatch.setattr(cli, "execute_approved_codex_successor", execute)
    monkeypatch.setattr(cli, "SystemCodexSuccessorServices", lambda _path: object())
    exit_code = cli.main(
        [
            "dev",
            "codex-successor-execute-approved",
            "proposal.json",
            "approval.json",
            "--control-root",
            str(tmp_path / "control"),
            "--claim-store",
            str(tmp_path / "claim.sqlite3"),
            "--json",
        ]
    )

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0]["proposal_path"] == Path("proposal.json")
    assert calls[0]["architecture_approval_path"] == Path("approval.json")
    assert json.loads(capsys.readouterr().out) == expected
