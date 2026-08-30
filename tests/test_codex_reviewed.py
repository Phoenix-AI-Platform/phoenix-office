from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from phoenix_office import cli
from phoenix_office.dev import (
    ReviewedRunnerOutcome,
    codex_package,
    codex_reviewed,
    execute_reviewed_codex_task,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PACKAGE_NAMES = (
    "handoff.json",
    "evidence.json",
    "authorization.json",
)


def _head() -> str:
    completed = subprocess.run(
        ["git", "-C", str(REPOSITORY_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        check=True,
        shell=False,
        text=True,
    )
    return completed.stdout.strip()


def _valid_spec(**updates: Any) -> dict[str, Any]:
    reviewers = cli.CODEX_PILOT_EVIDENCE_CONTROL_REVIEWERS
    spec: dict[str, Any] = {
        "acceptance_criteria": [
            "The exact generated package enters the supervised runner once.",
            "Phoenix stops after opening the reviewed pull request.",
        ],
        "allowed_paths": ["docs/development/progress_dashboard.md"],
        "base_commit_sha": _head(),
        "branch_name": "codex/issue-388-execute",
        "budget_ceiling": 225000,
        "constraints": [
            "Do not retry the worker.",
            "Do not grant merge authority.",
        ],
        "control_references": {
            control_id: f"{control_id}-reviewed"
            for control_id in reviewers
        },
        "expected_pr_title": "docs: record reviewed Codex execution",
        "handoff_id": "codex-handoff-issue-388",
        "issue_number": 388,
        "objective": "Document one reviewed execution through existing controls.",
        "repository": "Phoenix-AI-Platform/phoenix-office",
        "reviewed_at": "2026-08-25T12:00:00+00:00",
        "schema_version": "codex-pilot-task-spec.v1",
        "task_id": "issue-388-reviewed-execution",
        "timeout_seconds": 1800,
        "title": "Execute reviewed task specs",
    }
    spec.update(updates)
    return spec


def _write_spec(tmp_path: Path, **updates: Any) -> Path:
    path = tmp_path / "task-spec.json"
    path.write_text(
        json.dumps(_valid_spec(**updates), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def _successful_package_builder(
    calls: list[dict[str, object]],
) -> Callable[..., dict[str, Any]]:
    def build(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        output = Path(kwargs["output_dir"])
        output.mkdir()
        for name in EXPECTED_PACKAGE_NAMES:
            (output / name).write_text(
                json.dumps({"artifact": name}),
                encoding="utf-8",
            )
        return {
            "authorization_fingerprint": "a" * 64,
            "authorization_id": "pilot-auth-issue-388-reviewed",
            "category": "preclaim_ready",
            "package_build_result": "pass",
            "preclaim_ready": True,
        }

    return build


def _success_outcome() -> ReviewedRunnerOutcome:
    return ReviewedRunnerOutcome(
        result={
            "status": "success",
            "category": "pr_opened_and_stopped",
            "attempt_id": "pilot-attempt-reviewed",
            "pull_request_identity": "#389",
            "changed_paths": ["docs/development/progress_dashboard.md"],
            "validation_categories": ["pytest_passed", "ruff_passed"],
            "usage_category": "within_budget",
            "observed_usage_tokens": 1000,
            "input_tokens": 700,
            "cached_input_tokens": 500,
            "output_tokens": 300,
            "reasoning_output_tokens": 200,
            "authorized_budget_tokens": 225000,
            "usage_overage_tokens": 0,
            "usage_ratio_basis_points": 44,
        },
        execution_backend_selected="wsl2_linux",
        durable_lifecycle_state="pr_opened_and_stopped",
        durable_lifecycle_terminal=False,
    )


@pytest.fixture(autouse=True)
def _simulate_clean_exact_main(monkeypatch: pytest.MonkeyPatch) -> None:
    def git_output(_repository: Path, *args: str) -> str:
        if args == ("branch", "--show-current"):
            return "main"
        if args == ("status", "--porcelain=v1"):
            return ""
        if args == ("rev-parse", "HEAD"):
            return _head()
        raise AssertionError(args)

    monkeypatch.setattr(codex_reviewed, "_git_output", git_output)


def _execute(
    tmp_path: Path,
    *,
    package_builder: Callable[..., dict[str, Any]] | None = None,
    runner_invoker: Callable[[Path, Path, Path, Path], ReviewedRunnerOutcome]
    | None = None,
    task_spec_path: Path | None = None,
    control_root: Path | None = None,
    claim_store_path: Path | None = None,
) -> dict[str, object]:
    root = control_root or (tmp_path / "control")
    root.mkdir(exist_ok=True)
    return execute_reviewed_codex_task(
        task_spec_path=task_spec_path or _write_spec(tmp_path),
        control_root=root,
        claim_store_path=claim_store_path or (tmp_path / "claim.sqlite3"),
        repository_root=REPOSITORY_ROOT,
        evidence_control_reviewers=cli.CODEX_PILOT_EVIDENCE_CONTROL_REVIEWERS,
        package_inspector=lambda *_paths: pytest.fail("unexpected inspector"),
        runner_invoker=runner_invoker or (lambda *_paths: _success_outcome()),
        package_builder=package_builder or _successful_package_builder([]),
    )


def test_valid_spec_builds_package_then_invokes_runner_exactly_once(
    tmp_path: Path,
) -> None:
    package_calls: list[dict[str, object]] = []
    runner_calls: list[tuple[Path, Path, Path, Path]] = []

    def invoke(
        handoff: Path,
        evidence: Path,
        authorization: Path,
        claim_store: Path,
    ) -> ReviewedRunnerOutcome:
        runner_calls.append((handoff, evidence, authorization, claim_store))
        assert tuple(path.name for path in runner_calls[0][:3]) == (
            "handoff.json",
            "evidence.json",
            "authorization.json",
        )
        assert [
            json.loads(path.read_text(encoding="utf-8"))["artifact"]
            for path in runner_calls[0][:3]
        ] == list(EXPECTED_PACKAGE_NAMES)
        return _success_outcome()

    result = _execute(
        tmp_path,
        package_builder=_successful_package_builder(package_calls),
        runner_invoker=invoke,
    )

    assert len(package_calls) == 1
    assert len(runner_calls) == 1
    assert result["runner_invoked"] is True
    assert result["claim_created"] is True
    assert result["authorization_consumed"] is True


def test_success_surfaces_pr_opened_stop_and_bounded_usage(tmp_path: Path) -> None:
    result = _execute(tmp_path)

    assert result["status"] == "success"
    assert result["category"] == "pr_opened_and_stopped"
    assert result["pr_created_by_runner"] is True
    assert result["office_pr"] == "#389"
    assert result["office_pr_head"] is None
    assert result["observed_usage_tokens"] == 1000
    assert result["input_tokens"] == 700
    assert result["cached_input_tokens"] == 500
    assert result["output_tokens"] == 300
    assert result["reasoning_output_tokens"] == 200
    assert result["authorized_budget_tokens"] == 225000
    assert result["durable_lifecycle_state"] == "pr_opened_and_stopped"
    assert result["durable_lifecycle_terminal"] is False


def test_reviewed_usage_components_remain_bounded(tmp_path: Path) -> None:
    outcome = _success_outcome()
    runner_result = dict(outcome.result)
    runner_result.update(
        {
            "input_tokens": -1,
            "cached_input_tokens": True,
            "output_tokens": 10**9 + 1,
            "reasoning_output_tokens": "invalid",
        }
    )
    bounded_outcome = ReviewedRunnerOutcome(
        result=runner_result,
        execution_backend_selected=outcome.execution_backend_selected,
        durable_lifecycle_state=outcome.durable_lifecycle_state,
        durable_lifecycle_terminal=outcome.durable_lifecycle_terminal,
    )

    result = _execute(
        tmp_path,
        runner_invoker=lambda *_paths: bounded_outcome,
    )

    assert result["observed_usage_tokens"] == 1000
    assert result["input_tokens"] is None
    assert result["cached_input_tokens"] is None
    assert result["output_tokens"] is None
    assert result["reasoning_output_tokens"] is None


def test_cli_derives_exact_pr_opened_nonterminal_lifecycle() -> None:
    state, terminal = cli._durable_lifecycle_from_runner_result(
        dict(_success_outcome().result)
    )

    assert state == "pr_opened_and_stopped"
    assert terminal is False


def test_real_task_073_builder_artifacts_flow_directly_to_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        codex_package,
        "_current_branch",
        lambda _repository: "main",
    )
    control = tmp_path / "control"
    control.mkdir()
    runner_calls: list[tuple[Path, Path, Path]] = []

    def invoke(
        handoff: Path,
        evidence: Path,
        authorization: Path,
        _claim_store: Path,
    ) -> ReviewedRunnerOutcome:
        runner_calls.append((handoff, evidence, authorization))
        payloads = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in runner_calls[0]
        ]
        assert payloads[0]["task"]["task_id"] == "issue-388-reviewed-execution"
        assert payloads[1]["handoff_id"] == "codex-handoff-issue-388"
        assert payloads[2]["authorization_id"].startswith(
            "pilot-auth-issue-388-"
        )
        return _success_outcome()

    result = execute_reviewed_codex_task(
        task_spec_path=_write_spec(tmp_path),
        control_root=control,
        claim_store_path=tmp_path / "claim.sqlite3",
        repository_root=REPOSITORY_ROOT,
        evidence_control_reviewers=cli.CODEX_PILOT_EVIDENCE_CONTROL_REVIEWERS,
        package_inspector=cli._inspect_codex_pilot_package_build,
        runner_invoker=invoke,
    )

    assert result["package_build_result"] == "pass", result
    assert result["preclaim_ready"] is True
    assert len(runner_calls) == 1


@pytest.mark.parametrize(
    ("package_result", "expected_category"),
    [
        (
            {
                "category": "generated_package_validation_failed",
                "package_build_result": "blocked",
                "preclaim_ready": False,
            },
            "generated_package_validation_failed",
        ),
        (
            {
                "category": "unexpected",
                "package_build_result": "pass",
                "preclaim_ready": False,
            },
            "package_not_preclaim_ready",
        ),
    ],
)
def test_package_failure_or_not_ready_blocks_runner_without_claim(
    tmp_path: Path,
    package_result: dict[str, object],
    expected_category: str,
) -> None:
    runner_calls = 0

    def build(**_kwargs: Any) -> dict[str, Any]:
        return dict(package_result)

    def invoke(*_paths: Path) -> ReviewedRunnerOutcome:
        nonlocal runner_calls
        runner_calls += 1
        return _success_outcome()

    result = _execute(tmp_path, package_builder=build, runner_invoker=invoke)

    assert result["category"] == expected_category
    assert result["runner_invoked"] is False
    assert result["authorization_consumed"] is False
    assert result["claim_created"] is False
    assert runner_calls == 0


@pytest.mark.parametrize(
    ("branch", "expected_category"),
    [
        ("codex/issue-074-execute", "noncanonical_base_branch"),
        ("", "noncanonical_base_branch"),
    ],
)
def test_feature_or_detached_checkout_blocks_before_package_and_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    branch: str,
    expected_category: str,
) -> None:
    calls = 0

    def git_output(_repository: Path, *args: str) -> str:
        if args == ("branch", "--show-current"):
            return branch
        raise AssertionError("later Git check must not run")

    def build(**_kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {}

    monkeypatch.setattr(codex_reviewed, "_git_output", git_output)
    result = _execute(tmp_path, package_builder=build)

    assert result["category"] == expected_category
    assert result["runner_invoked"] is False
    assert calls == 0


def test_dirty_worktree_blocks_before_package_and_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def git_output(_repository: Path, *args: str) -> str:
        return {
            ("branch", "--show-current"): "main",
            ("status", "--porcelain=v1"): " M tracked.txt",
        }[args]

    monkeypatch.setattr(codex_reviewed, "_git_output", git_output)
    result = _execute(
        tmp_path,
        package_builder=lambda **_kwargs: pytest.fail("builder called"),
    )

    assert result["category"] == "dirty_worktree"
    assert result["authorization_consumed"] is False


def test_stale_sha_blocks_before_package_and_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def git_output(_repository: Path, *args: str) -> str:
        return {
            ("branch", "--show-current"): "main",
            ("status", "--porcelain=v1"): "",
            ("rev-parse", "HEAD"): "f" * 40,
        }[args]

    monkeypatch.setattr(codex_reviewed, "_git_output", git_output)
    result = _execute(
        tmp_path,
        package_builder=lambda **_kwargs: pytest.fail("builder called"),
    )

    assert result["category"] == "stale_base_commit"
    assert result["runner_invoked"] is False


def test_malformed_spec_blocks_before_package_and_claim(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.json"
    malformed.write_text("[]", encoding="utf-8")

    result = _execute(
        tmp_path,
        task_spec_path=malformed,
        package_builder=lambda **_kwargs: pytest.fail("builder called"),
    )

    assert result["category"] == "task_spec_malformed"
    assert result["runner_invoked"] is False
    assert result["authorization_consumed"] is False


def test_control_root_inside_repository_is_rejected(tmp_path: Path) -> None:
    result = _execute(
        tmp_path,
        control_root=REPOSITORY_ROOT,
        package_builder=lambda **_kwargs: pytest.fail("builder called"),
    )

    assert result["category"] == "output_inside_git_worktree"
    assert result["runner_invoked"] is False


def test_claim_store_inside_repository_is_rejected(tmp_path: Path) -> None:
    result = _execute(
        tmp_path,
        claim_store_path=REPOSITORY_ROOT / "unsafe-claim.sqlite3",
        package_builder=lambda **_kwargs: pytest.fail("builder called"),
    )

    assert result["category"] == "output_inside_git_worktree"
    assert result["runner_invoked"] is False


def test_existing_sqlite_store_is_rejected_without_inspection(tmp_path: Path) -> None:
    existing = tmp_path / "records.sqlite3"
    existing.write_bytes(b"customer job database")

    result = _execute(
        tmp_path,
        claim_store_path=existing,
        package_builder=lambda **_kwargs: pytest.fail("builder called"),
    )

    assert result["category"] == "claim_store_already_exists"
    assert existing.read_bytes() == b"customer job database"
    assert result["runner_invoked"] is False


def test_reparse_control_root_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control = tmp_path / "control"
    control.mkdir()
    original = codex_package._is_link_or_reparse
    monkeypatch.setattr(
        codex_package,
        "_is_link_or_reparse",
        lambda path: path.resolve(strict=False) == control.resolve()
        or original(path),
    )

    result = _execute(
        tmp_path,
        control_root=control,
        package_builder=lambda **_kwargs: pytest.fail("builder called"),
    )

    assert result["category"] == "output_symlink_rejected"
    assert result["runner_invoked"] is False


def test_postclaim_failure_does_not_rebuild_or_retry(tmp_path: Path) -> None:
    package_calls: list[dict[str, object]] = []
    runner_calls = 0

    def invoke(*_paths: Path) -> ReviewedRunnerOutcome:
        nonlocal runner_calls
        runner_calls += 1
        return ReviewedRunnerOutcome(
            result={
                "status": "failed",
                "category": "validation_failed",
                "attempt_id": "pilot-attempt-terminal",
                "pull_request_identity": None,
                "changed_paths": ["docs/development/progress_dashboard.md"],
                "usage_category": "within_budget",
                "observed_usage_tokens": 2000,
                "authorized_budget_tokens": 225000,
                "usage_overage_tokens": 0,
                "usage_ratio_basis_points": 88,
            },
            execution_backend_selected="wsl2_linux",
            durable_lifecycle_state="failed",
            durable_lifecycle_terminal=True,
        )

    result = _execute(
        tmp_path,
        package_builder=_successful_package_builder(package_calls),
        runner_invoker=invoke,
    )

    assert len(package_calls) == 1
    assert runner_calls == 1
    assert result["status"] == "failed"
    assert result["authorization_consumed"] is True
    assert result["durable_lifecycle_terminal"] is True
    assert result["replacement_authorization_created"] is False
    assert result["auto_retry_used"] is False
    assert result["background_resume_used"] is False
    assert result["pr_created_by_runner"] is False


def test_preclaim_runner_block_is_not_reported_as_consumed(tmp_path: Path) -> None:
    outcome = ReviewedRunnerOutcome(
        result={
            "status": "blocked",
            "category": "wsl_codex_qualified_runtime_unavailable",
            "attempt_id": None,
            "pull_request_identity": None,
            "changed_paths": [],
            "usage_category": "usage_unknown",
        },
        execution_backend_selected="wsl2_linux",
    )

    result = _execute(tmp_path, runner_invoker=lambda *_paths: outcome)

    assert result["runner_invoked"] is True
    assert result["authorization_consumed"] is False
    assert result["claim_created"] is False
    assert result["pr_created_by_runner"] is False


def test_postclaim_lifecycle_uncertainty_fails_closed(tmp_path: Path) -> None:
    outcome = ReviewedRunnerOutcome(
        result={
            "status": "timed_out",
            "category": "codex_timed_out",
            "attempt_id": "pilot-attempt-uncertain",
            "pull_request_identity": None,
            "changed_paths": [],
            "usage_category": "within_budget",
        },
        execution_backend_selected="wsl2_linux",
        durable_lifecycle_state=None,
        durable_lifecycle_terminal=False,
    )

    result = _execute(tmp_path, runner_invoker=lambda *_paths: outcome)

    assert result["status"] == "failed"
    assert result["category"] == "lifecycle_storage_uncertain"
    assert result["authorization_consumed"] is True
    assert result["auto_retry_used"] is False


@pytest.mark.parametrize(
    ("lifecycle_state", "lifecycle_terminal"),
    [
        ("completed_pending_review", True),
        ("pr_opened_and_stopped", True),
        ("unknown_state", False),
    ],
)
def test_invalid_postclaim_lifecycle_fails_closed(
    tmp_path: Path,
    lifecycle_state: str,
    lifecycle_terminal: bool,
) -> None:
    outcome = ReviewedRunnerOutcome(
        result=_success_outcome().result,
        execution_backend_selected="wsl2_linux",
        durable_lifecycle_state=lifecycle_state,
        durable_lifecycle_terminal=lifecycle_terminal,
    )

    result = _execute(tmp_path, runner_invoker=lambda *_paths: outcome)

    assert result["status"] == "failed"
    assert result["category"] == "lifecycle_storage_uncertain"
    assert result["pr_created_by_runner"] is True
    assert result["office_pr"] == "#389"
    assert result["auto_retry_used"] is False
    assert result["replacement_authorization_created"] is False
    assert result["background_resume_used"] is False


@pytest.mark.parametrize(
    ("status", "category", "lifecycle_state"),
    [
        ("failed", "validation_failed", "failed"),
        ("failed", "aborted", "aborted"),
        ("cancelled", "wsl_codex_cancelled", "cancelled"),
        ("timed_out", "wsl_codex_timed_out", "timed_out"),
    ],
)
def test_verified_terminal_failure_states_remain_terminal(
    tmp_path: Path,
    status: str,
    category: str,
    lifecycle_state: str,
) -> None:
    outcome = ReviewedRunnerOutcome(
        result={
            "status": status,
            "category": category,
            "attempt_id": "pilot-attempt-terminal-state",
            "pull_request_identity": None,
            "changed_paths": [],
            "usage_category": "within_budget",
        },
        execution_backend_selected="wsl2_linux",
        durable_lifecycle_state=lifecycle_state,
        durable_lifecycle_terminal=True,
    )

    result = _execute(tmp_path, runner_invoker=lambda *_paths: outcome)

    assert result["status"] == status
    assert result["category"] == category
    assert result["durable_lifecycle_state"] == lifecycle_state
    assert result["durable_lifecycle_terminal"] is True


def test_pr_identity_remains_visible_after_publication_audit_failure(
    tmp_path: Path,
) -> None:
    outcome = ReviewedRunnerOutcome(
        result={
            "status": "failed",
            "category": "publication_audit_storage_uncertain",
            "attempt_id": "pilot-attempt-published",
            "pull_request_identity": "pr-389",
            "changed_paths": ["docs/development/progress_dashboard.md"],
            "validation_categories": ["passed", "passed", "passed"],
            "usage_category": "within_budget",
        },
        execution_backend_selected="wsl2_linux",
        durable_lifecycle_state="failed",
        durable_lifecycle_terminal=True,
    )

    result = _execute(tmp_path, runner_invoker=lambda *_paths: outcome)

    assert result["status"] == "failed"
    assert result["pr_created_by_runner"] is True
    assert result["office_pr"] == "pr-389"
    assert result["phoenix_validation_result"] == "pass"
    assert result["auto_retry_used"] is False


def test_public_result_exposes_no_absolute_control_paths(tmp_path: Path) -> None:
    result = _execute(tmp_path)
    rendered = json.dumps(result, sort_keys=True)

    assert str(tmp_path) not in rendered
    assert str(REPOSITORY_ROOT) not in rendered
    assert "claim.sqlite3" not in rendered
    assert result["worker_may_merge"] is False
    assert result["pr_merged"] is False


def test_existing_package_only_command_does_not_invoke_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli,
        "build_codex_pilot_package",
        lambda **_kwargs: {
            "package_build_result": "pass",
            "category": "preclaim_ready",
            "handoff_path": "handoff.json",
            "evidence_path": "evidence.json",
            "authorization_path": "authorization.json",
            "authorization_id": "pilot-auth-safe",
            "authorization_fingerprint": "a" * 64,
            "preclaim_ready": True,
        },
    )
    monkeypatch.setattr(
        cli,
        "SupervisedCodexPilotRunner",
        lambda *_args, **_kwargs: pytest.fail("runner constructed"),
    )
    args = cli.build_parser().parse_args(
        [
            "dev",
            "codex-pilot-package-build",
            str(_write_spec(tmp_path)),
            "--output-dir",
            str(tmp_path / "package-only"),
            "--json",
        ]
    )

    assert args.func(args) == 0


def test_existing_standalone_runner_command_remains_callable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Path, Path, Path, Path]] = []

    def execute_from_paths(
        **kwargs: Path,
    ) -> tuple[dict[str, object], object]:
        calls.append(
            (
                kwargs["handoff_path"],
                kwargs["evidence_path"],
                kwargs["authorization_path"],
                kwargs["claim_store_path"],
            )
        )
        return _success_outcome().result, object()

    monkeypatch.setattr(cli, "_execute_codex_pilot_from_paths", execute_from_paths)
    args = cli.build_parser().parse_args(
        [
            "dev",
            "codex-pilot-run",
            "handoff.json",
            "evidence.json",
            "authorization.json",
            "--claim-store",
            str(tmp_path / "standalone.sqlite3"),
            "--json",
        ]
    )

    assert args.func(args) == 0
    assert len(calls) == 1


def test_reviewed_cli_json_remains_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    expected = codex_reviewed.blocked_reviewed_execution_result(
        "unsafe_control_root"
    )
    assert expected["input_tokens"] is None
    assert expected["cached_input_tokens"] is None
    assert expected["output_tokens"] is None
    assert expected["reasoning_output_tokens"] is None
    monkeypatch.setattr(
        cli,
        "execute_reviewed_codex_task",
        lambda **_kwargs: expected,
    )
    args = cli.build_parser().parse_args(
        [
            "dev",
            "codex-pilot-execute-reviewed",
            str(tmp_path / "task-spec.json"),
            "--control-root",
            str(tmp_path / "control"),
            "--claim-store",
            str(tmp_path / "claim.sqlite3"),
            "--json",
        ]
    )

    assert args.func(args) == 1
    output = capsys.readouterr().out
    assert str(tmp_path) not in output
    assert json.loads(output)["runner_invoked"] is False


def test_claim_store_requires_explicit_sqlite3_suffix(tmp_path: Path) -> None:
    result = _execute(
        tmp_path,
        claim_store_path=tmp_path / "claim.db",
        package_builder=lambda **_kwargs: pytest.fail("builder called"),
    )

    assert result["category"] == "claim_store_path_unsafe"
    assert result["runner_invoked"] is False


def test_generated_artifact_substitution_is_rejected_before_runner(
    tmp_path: Path,
) -> None:
    def build(**kwargs: Any) -> dict[str, Any]:
        output = Path(kwargs["output_dir"])
        output.mkdir()
        (output / "handoff.json").write_text("{}", encoding="utf-8")
        (output / "evidence.json").write_text("{}", encoding="utf-8")
        return {
            "authorization_fingerprint": "a" * 64,
            "authorization_id": "pilot-auth-issue-388-reviewed",
            "category": "preclaim_ready",
            "package_build_result": "pass",
            "preclaim_ready": True,
        }

    result = _execute(
        tmp_path,
        package_builder=build,
        runner_invoker=lambda *_paths: pytest.fail("runner called"),
    )

    assert result["category"] == "generated_package_unavailable"
    assert result["runner_invoked"] is False
