"""Tests for the supervised Codex execution-to-PR runner."""

from __future__ import annotations

import inspect
import io
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

import phoenix_office.cli as cli
import phoenix_office.dev.codex_runner as runner_module
from phoenix_office.cli import main
from phoenix_office.dev import SQLiteCodexPilotInitialClaimStore
from phoenix_office.dev.codex_runner import (
    BASE_BRANCH,
    CAPABILITY_MARKER_CONTENT,
    CAPABILITY_MARKER_NAME,
    REQUIRED_EVIDENCE_CONTROLS,
    VALIDATION_COMMANDS,
    CapabilityProbeResult,
    CodexExecutionResult,
    CodexLaunchSpec,
    DiffGateResult,
    GateResult,
    PublicationResult,
    SupervisedCodexPilotRunner,
    SystemCodexPilotServices,
    ValidationGateResult,
    ValidationRuntimeSpec,
    WorktreeHandle,
    WorktreeResult,
    _codex_exec_argv,
    _parse_codex_jsonl,
    _pull_request_body,
    render_codex_worker_prompt,
    render_reviewed_codex_invocation_prompt,
)
from phoenix_office.dev.codex_wsl import (
    WslCapabilityResult,
    WslExecutionResult,
    WslGateResult,
)

BASE_SHA = "0" * 40
ATTEMPT_ID = "pilot-attempt-task060abc123"
ALLOWED_PATH = "docs/process/supervised-codex-pilot-storage.md"
BRANCH = "codex/pilot-060-runner"


@dataclass
class FakeWslWorker:
    runtime_frozen: bool = False
    runtime_kind: str = "native_linux_exe"
    runtime_result: WslGateResult = WslGateResult(True, "wsl_codex_runtime_ready")
    authentication_result: WslGateResult = WslGateResult(
        True,
        "wsl_codex_authenticated",
    )
    capability_result: WslCapabilityResult = WslCapabilityResult(
        True,
        "wsl_workspace_write_capability_proved",
    )
    execution_result: WslExecutionResult = WslExecutionResult(
        "succeeded",
        "wsl_codex_completed",
        7,
    )
    invocations: list[dict[str, object]] = field(default_factory=list)

    def runtime_gate(self) -> WslGateResult:
        return self.runtime_result

    def authentication_gate(self) -> WslGateResult:
        return self.authentication_result

    def capability_probe(self, _timeout_seconds: int) -> WslCapabilityResult:
        return self.capability_result

    def invoke_codex(self, **kwargs) -> WslExecutionResult:
        self.invocations.append(kwargs)
        return self.execution_result


def _write_windows_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"MZ" + b"\0" * 32)


def _native_launch_spec(tmp_path: Path) -> CodexLaunchSpec:
    executable = tmp_path / "codex.exe"
    _write_windows_executable(executable)
    identity = runner_module._launch_file_identity(
        executable,
        require_windows_exe=True,
    )
    assert identity is not None
    return CodexLaunchSpec(
        (str(identity.path),),
        "native_exe",
        (identity,),
    )


def _validation_runtime_spec(repository: Path) -> ValidationRuntimeSpec:
    venv_root = repository / ".venv"
    executable = venv_root
    if os.name == "nt":
        executable = executable / "Scripts" / "python.exe"
        _write_windows_executable(executable)
        ruff_executable = venv_root / "Scripts" / "ruff.exe"
        _write_windows_executable(ruff_executable)
    else:
        executable = executable / "bin" / "python"
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b"#!/usr/bin/env python3\n")
        executable.chmod(0o755)
        ruff_executable = venv_root / "bin" / "ruff"
        ruff_executable.write_text("synthetic ruff binary\n", encoding="utf-8")
        ruff_executable.chmod(0o755)
    site_packages = venv_root / "Lib" / "site-packages"
    pytest_root = site_packages / "pytest"
    internal_pytest_root = site_packages / "_pytest"
    ruff_root = site_packages / "ruff"
    for path, content in (
        (pytest_root / "__init__.py", "pytest package\n"),
        (internal_pytest_root / "__init__.py", "internal pytest package\n"),
        (internal_pytest_root / "main.py", "pytest implementation\n"),
        (ruff_root / "__init__.py", "ruff package\n"),
        (ruff_root / "__main__.py", "ruff module entrypoint\n"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    identity = runner_module._launch_file_identity(
        executable,
        require_windows_exe=os.name == "nt",
    )
    assert identity is not None
    resolved_venv = venv_root.resolve(strict=True)
    pytest_identity = runner_module._validation_tool_identity_from_paths(
        tool="pytest",
        venv_root=resolved_venv,
        roots=(pytest_root, internal_pytest_root),
        origins=(pytest_root / "__init__.py", internal_pytest_root / "__init__.py"),
        executable=None,
    )
    ruff_identity = runner_module._validation_tool_identity_from_paths(
        tool="ruff",
        venv_root=resolved_venv,
        roots=(ruff_root,),
        origins=(ruff_root / "__init__.py",),
        executable=ruff_executable,
    )
    assert pytest_identity is not None
    assert ruff_identity is not None
    return ValidationRuntimeSpec(
        identity,
        resolved_venv,
        pytest_identity,
        ruff_identity,
    )


def _authorization() -> dict[str, object]:
    return {
        "schema_version": "codex-pilot-authorization.v1",
        "authorization_id": "pilot-auth-issue-363",
        "repository": "Phoenix-AI-Platform/phoenix-office",
        "pilot_kind": "docs-only-supervised",
        "decision_state": "human_authorized_for_one_run",
        "authorizer_role": "human_operator",
        "base_commit_sha": BASE_SHA,
        "handoff_path": "handoff.json",
        "evidence_path": "evidence.json",
        "handoff_id": "codex-handoff-issue-363",
        "objective": "Update one reviewed Phoenix process document.",
        "allowed_paths": [ALLOWED_PATH],
        "expected_pr_title": "docs: update supervised Codex storage",
        "branch_name": BRANCH,
        "validation_commands": list(VALIDATION_COMMANDS),
        "budget_metric": "tokens",
        "budget_ceiling": 50_000,
        "budget_enforcement_ref": "budget-control-reviewed",
        "timeout_seconds": 1800,
        "cancellation_ref": "cancellation-control-reviewed",
        "authentication_runner_ref": "authentication-runner-reviewed",
        "branch_permission_ref": "branch-permission-reviewed",
        "pr_permission_ref": "pr-permission-reviewed",
        "duplicate_pr_check_ref": "duplicate-pr-check-reviewed",
        "branch_collision_check_ref": "branch-collision-check-reviewed",
        "codex_no_approve_merge_ref": "codex-no-approve-merge-reviewed",
        "final_ci_required": True,
        "assistant_review_required": True,
        "worker_may_approve": False,
        "worker_may_merge": False,
        "one_invocation_only": True,
        "retry_authorized": False,
        "background_execution_authorized": False,
    }


def _handoff() -> dict[str, object]:
    authorization = _authorization()
    return {
        "schema_version": "codex-handoff-package.v1",
        "handoff_id": authorization["handoff_id"],
        "repository": authorization["repository"],
        "base_branch": BASE_BRANCH,
        "expected_pr_title": authorization["expected_pr_title"],
        "prompt": "Apply the reviewed documentation clarification and stop.",
        "required_pr_body_headings": [
            "Summary",
            "Scope",
            "Changed files",
            "Out-of-scope confirmation",
            "Validation performed",
            "Risks",
        ],
        "task": {
            "task_id": "task-issue-363-runner-test",
            "title": "Update supervised Codex storage documentation",
            "objective": authorization["objective"],
            "source": {
                "kind": "github_issue",
                "uri": (
                    "https://github.com/Phoenix-AI-Platform/"
                    "phoenix-office/issues/363"
                ),
            },
            "allowed_resources": {"paths": [ALLOWED_PATH]},
            "verification_plan": {"commands": list(VALIDATION_COMMANDS)},
            "permissions": {
                "read": True,
                "write": True,
                "execute": False,
                "network": False,
                "destructive": False,
            },
        },
    }


def _evidence() -> dict[str, object]:
    authorization = _authorization()
    reference_fields = {
        "authentication_runner_access": "authentication_runner_ref",
        "per_run_budget_ceiling": "budget_enforcement_ref",
        "operator_cancellation_timeout": "cancellation_ref",
        "github_branch_creation_permission": "branch_permission_ref",
        "github_pr_creation_permission": "pr_permission_ref",
        "codex_cannot_approve_or_merge": "codex_no_approve_merge_ref",
        "duplicate_active_pr_detection": "duplicate_pr_check_ref",
        "branch_collision_detection": "branch_collision_check_ref",
    }
    return {
        "schema_version": "codex-pilot-evidence.v1",
        "repository": authorization["repository"],
        "pilot_kind": authorization["pilot_kind"],
        "handoff_id": authorization["handoff_id"],
        "pilot_ready": False,
        "invocation_authorized": False,
        "controls": [
            {
                "control_id": control_id,
                "status": "verified",
                "evidence_ref": authorization.get(
                    reference_fields.get(control_id, ""),
                    f"{control_id}-reviewed",
                ),
                "reviewer_role": "assistant_reviewer",
            }
            for control_id in sorted(REQUIRED_EVIDENCE_CONTROLS)
        ],
    }


def _reviewed_prompt(handoff: dict[str, object]) -> str:
    task = handoff["task"]
    assert isinstance(task, dict)
    source = task["source"]
    assert isinstance(source, dict)
    issue_number = int(str(source["uri"]).rsplit("/", 1)[1])
    return render_reviewed_codex_invocation_prompt(
        package=handoff,
        preflight_report={
            "source_issue_number": issue_number,
            "repository": handoff["repository"],
            "base_branch": handoff["base_branch"],
            "declared_changed_files": [ALLOWED_PATH],
            "external_checks_required": list(
                runner_module.INVOCATION_EXTERNAL_CHECKS_REQUIRED
            ),
        },
    )


@dataclass
class FakeSystem:
    preclaim: GateResult = GateResult(True, "preclaim_passed")
    runtime: GateResult = GateResult(True, "runtime_ready")
    auth: GateResult = GateResult(True, "codex_authenticated")
    probe: CapabilityProbeResult = CapabilityProbeResult(True, "probe_passed")
    execution: CodexExecutionResult = CodexExecutionResult(
        "succeeded", "codex_completed", 100
    )
    first_diff: DiffGateResult = DiffGateResult(
        True, "diff_allowed", (ALLOWED_PATH,)
    )
    second_diff: DiffGateResult | None = None
    validation: ValidationGateResult = ValidationGateResult(
        True, "validation_passed", ("passed", "passed", "passed")
    )
    commit: GateResult = GateResult(True, "committed")
    prepublication: GateResult = GateResult(True, "prepublication_passed")
    push: GateResult = GateResult(True, "pushed")
    publication: PublicationResult = PublicationResult(
        True, "pull_request_created", "pr-400"
    )
    worktree_outcome: WorktreeResult | None = None
    calls: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    worktree: WorktreeHandle = field(
        default_factory=lambda: WorktreeHandle(
            Path("synthetic-worktree"),
            BRANCH,
            BASE_SHA,
            b"gitdir",
            (),
            "",
            "",
        )
    )

    def preclaim_repository_gate(self, authorization: dict[str, object]) -> GateResult:
        assert authorization["branch_name"] == BRANCH
        self.calls.append("preclaim")
        return self.preclaim

    def runtime_gate(self) -> GateResult:
        self.calls.append("runtime")
        return self.runtime

    def authentication_gate(self) -> GateResult:
        self.calls.append("auth")
        return self.auth

    def capability_probe(self, timeout_seconds: int) -> CapabilityProbeResult:
        assert timeout_seconds == 180
        self.calls.append("probe")
        return self.probe

    def create_worktree(self, authorization: dict[str, object]) -> WorktreeResult:
        assert authorization["base_commit_sha"] == BASE_SHA
        self.calls.append("worktree")
        if self.worktree_outcome is not None:
            return self.worktree_outcome
        return WorktreeResult(True, "worktree_created", self.worktree)

    def invoke_codex(
        self,
        worktree: WorktreeHandle,
        prompt: str,
        timeout_seconds: int,
        on_started,
    ) -> CodexExecutionResult:
        assert worktree is self.worktree
        assert timeout_seconds == 1800
        self.calls.append("invoke")
        self.prompts.append(prompt)
        on_started()
        return self.execution

    def inspect_diff(
        self,
        worktree: WorktreeHandle,
        allowed_paths: tuple[str, ...],
    ) -> DiffGateResult:
        assert worktree is self.worktree
        assert allowed_paths == (ALLOWED_PATH,)
        self.calls.append("diff")
        if self.calls.count("diff") == 1 or self.second_diff is None:
            return self.first_diff
        return self.second_diff

    def run_validations(
        self,
        worktree: WorktreeHandle,
        commands: tuple[str, ...],
    ) -> ValidationGateResult:
        assert worktree is self.worktree
        assert commands == VALIDATION_COMMANDS
        self.calls.append("validation")
        return self.validation

    def commit_authorized_changes(
        self,
        worktree: WorktreeHandle,
        changed_paths: tuple[str, ...],
        commit_message: str,
    ) -> GateResult:
        assert worktree is self.worktree
        assert changed_paths == (ALLOWED_PATH,)
        assert commit_message == _authorization()["expected_pr_title"]
        self.calls.append("commit")
        return self.commit

    def prepublication_gate(self, authorization: dict[str, object]) -> GateResult:
        assert authorization["branch_name"] == BRANCH
        self.calls.append("prepublication")
        return self.prepublication

    def push_authorized_branch(self, worktree: WorktreeHandle) -> GateResult:
        assert worktree is self.worktree
        self.calls.append("push")
        return self.push

    def create_pull_request(
        self,
        worktree: WorktreeHandle,
        authorization: dict[str, object],
        source_issue_number: int,
        required_headings: tuple[str, ...],
        changed_paths: tuple[str, ...],
        validation_commands: tuple[str, ...],
    ) -> PublicationResult:
        assert worktree is self.worktree
        assert authorization["expected_pr_title"] == _authorization()[
            "expected_pr_title"
        ]
        assert source_issue_number == 363
        assert required_headings == tuple(_handoff()["required_pr_body_headings"])
        assert changed_paths == (ALLOWED_PATH,)
        assert validation_commands == VALIDATION_COMMANDS
        self.calls.append("pull_request")
        return self.publication


def _run(
    tmp_path: Path,
    system: FakeSystem,
    *,
    handoff: dict[str, object] | None = None,
    evidence: dict[str, object] | None = None,
    authorization: dict[str, object] | None = None,
    reviewed_prompt: str | None = None,
    static_preflight_passed: bool = True,
    claim_store_factory: runner_module.ClaimStoreFactory = (
        SQLiteCodexPilotInitialClaimStore
    ),
) -> tuple[dict[str, object], Path]:
    actual_handoff = handoff or _handoff()
    database_path = tmp_path / "control-state.sqlite3"
    runner = SupervisedCodexPilotRunner(
        system=system,
        claim_store_factory=claim_store_factory,
        attempt_id_factory=lambda: ATTEMPT_ID,
    )
    result = runner.run(
        handoff=actual_handoff,
        evidence=evidence or _evidence(),
        authorization=authorization or _authorization(),
        reviewed_prompt=(
            reviewed_prompt
            if reviewed_prompt is not None
            else _reviewed_prompt(actual_handoff)
        ),
        claim_store_path=database_path,
        static_preflight_passed=static_preflight_passed,
    )
    return result, database_path


def test_successful_run_has_one_invocation_and_phoenix_owned_publication(tmp_path: Path):
    system = FakeSystem()

    result, database_path = _run(tmp_path, system)

    assert result == {
        "schema_version": "codex-pilot-run-result.v1",
        "status": "success",
        "category": "pr_opened_and_stopped",
        "attempt_id": ATTEMPT_ID,
        "branch_identity": BRANCH,
        "pull_request_identity": "pr-400",
        "changed_paths": [ALLOWED_PATH],
        "validation_categories": ["passed", "passed", "passed"],
        "usage_category": "within_budget",
        "observed_usage_tokens": 100,
        "authorized_budget_tokens": 50_000,
        "usage_overage_tokens": 0,
        "usage_ratio_basis_points": 20,
        "timeout_category": "timeout_unknown",
        "cancellation_category": "cancellation_unknown",
    }
    assert system.calls == [
        "preclaim",
        "runtime",
        "auth",
        "probe",
        "worktree",
        "invoke",
        "diff",
        "validation",
        "diff",
        "commit",
        "prepublication",
        "push",
        "pull_request",
    ]
    assert len(system.prompts) == 1
    assert "- open one PR and stop" not in system.prompts[0]
    assert "Do not stage, commit, push, open a pull request" in system.prompts[0]
    assert all(command not in system.prompts[0] for command in VALIDATION_COMMANDS)
    lifecycle = SQLiteCodexPilotInitialClaimStore(database_path).read_lifecycle_state(
        ATTEMPT_ID,
        _authorization(),
    )
    assert lifecycle["lifecycle_read_category"] == "read_success"
    assert lifecycle["snapshot"]["current_lifecycle_state"] == (
        "pr_opened_and_stopped"
    )
    assert lifecycle["snapshot"]["pull_request_identity"] == "pr-400"


@pytest.mark.parametrize(
    ("gate_name", "gate_value", "category", "expected_calls"),
    [
        (
            "preclaim",
            GateResult(False, "base_sha_gate_failed"),
            "base_sha_gate_failed",
            ["preclaim"],
        ),
        (
            "preclaim",
            GateResult(False, "clean_repo_gate_failed"),
            "clean_repo_gate_failed",
            ["preclaim"],
        ),
        (
            "preclaim",
            GateResult(False, "local_branch_collision"),
            "local_branch_collision",
            ["preclaim"],
        ),
        (
            "preclaim",
            GateResult(False, "remote_branch_collision"),
            "remote_branch_collision",
            ["preclaim"],
        ),
        (
            "preclaim",
            GateResult(False, "duplicate_active_pr"),
            "duplicate_active_pr",
            ["preclaim"],
        ),
        (
            "preclaim",
            GateResult(False, "validation_runtime_unavailable"),
            "validation_runtime_unavailable",
            ["preclaim"],
        ),
        (
            "preclaim",
            GateResult(False, "validation_runtime_changed"),
            "validation_runtime_changed",
            ["preclaim"],
        ),
        (
            "runtime",
            GateResult(False, "codex_unavailable"),
            "codex_unavailable",
            ["preclaim", "runtime"],
        ),
        (
            "runtime",
            GateResult(False, "process_control_unavailable"),
            "process_control_unavailable",
            ["preclaim", "runtime"],
        ),
        (
            "auth",
            GateResult(False, "codex_authentication_unavailable"),
            "codex_authentication_unavailable",
            ["preclaim", "runtime", "auth"],
        ),
        (
            "auth",
            GateResult(False, "codex_auth_preflight_failed"),
            "codex_auth_preflight_failed",
            ["preclaim", "runtime", "auth"],
        ),
        (
            "probe",
            CapabilityProbeResult(False, "codex_transport_unavailable"),
            "codex_transport_unavailable",
            ["preclaim", "runtime", "auth", "probe"],
        ),
        (
            "probe",
            CapabilityProbeResult(False, "workspace_write_capability_unproved"),
            "workspace_write_capability_unproved",
            ["preclaim", "runtime", "auth", "probe"],
        ),
    ],
)
def test_preclaim_gate_failures_consume_nothing(
    tmp_path: Path,
    gate_name: str,
    gate_value: object,
    category: str,
    expected_calls: list[str],
):
    system = FakeSystem()
    setattr(system, gate_name, gate_value)

    result, database_path = _run(tmp_path, system)

    assert result["status"] == "blocked"
    assert result["category"] == category
    assert result["attempt_id"] is None
    assert not database_path.exists()
    assert system.calls == expected_calls


@pytest.mark.parametrize(
    "mutation",
    [
        "static_preflight",
        "prompt_drift",
        "budget_control_unverified",
        "invalid_authorization",
    ],
)
def test_static_binding_failures_precede_every_system_action(
    tmp_path: Path,
    mutation: str,
):
    handoff = _handoff()
    evidence = _evidence()
    authorization = _authorization()
    reviewed_prompt = _reviewed_prompt(handoff)
    static_passed = True
    if mutation == "static_preflight":
        static_passed = False
    elif mutation == "prompt_drift":
        reviewed_prompt += "\nUnreviewed instruction."
    elif mutation == "budget_control_unverified":
        controls = evidence["controls"]
        assert isinstance(controls, list)
        next(
            item
            for item in controls
            if item["control_id"] == "per_run_budget_ceiling"
        )["status"] = "unverified"
    else:
        authorization["retry_authorized"] = True
    system = FakeSystem()

    result, database_path = _run(
        tmp_path,
        system,
        handoff=handoff,
        evidence=evidence,
        authorization=authorization,
        reviewed_prompt=reviewed_prompt,
        static_preflight_passed=static_passed,
    )

    assert result["category"] == "preclaim_static_preflight_failed"
    assert result["attempt_id"] is None
    assert system.calls == []
    assert not database_path.exists()


class TerminalAppendFailureStore(SQLiteCodexPilotInitialClaimStore):
    """Inject one failed durable terminal append without retrying it."""

    def __init__(self, database_path: Path) -> None:
        super().__init__(database_path)
        self.terminal_append_attempts = 0

    def append_lifecycle_event(self, *args, **kwargs):
        if kwargs.get("next_lifecycle_state") in {
            "failed",
            "cancelled",
            "timed_out",
        }:
            self.terminal_append_attempts += 1
            return {
                "lifecycle_append_category": "claim_store_unavailable",
                "event_sequence": None,
                "lifecycle_state": None,
            }
        return super().append_lifecycle_event(*args, **kwargs)


def _run_with_terminal_append_failure(
    tmp_path: Path,
    system: FakeSystem,
) -> tuple[dict[str, object], Path, TerminalAppendFailureStore]:
    stores: list[TerminalAppendFailureStore] = []

    def factory(database_path: Path) -> TerminalAppendFailureStore:
        store = TerminalAppendFailureStore(database_path)
        stores.append(store)
        return store

    result, database_path = _run(
        tmp_path,
        system,
        claim_store_factory=factory,
    )
    assert len(stores) == 1
    return result, database_path, stores[0]


def test_preinvocation_terminal_append_failure_surfaces_storage_uncertainty(
    tmp_path: Path,
):
    system = FakeSystem(
        worktree_outcome=WorktreeResult(False, "worktree_creation_failed")
    )

    result, database_path, store = _run_with_terminal_append_failure(
        tmp_path,
        system,
    )

    assert result["status"] == "failed"
    assert result["category"] == "lifecycle_storage_uncertain"
    assert result["attempt_id"] == ATTEMPT_ID
    assert store.terminal_append_attempts == 1
    assert system.calls == ["preclaim", "runtime", "auth", "probe", "worktree"]
    lifecycle = SQLiteCodexPilotInitialClaimStore(database_path).read_lifecycle_state(
        ATTEMPT_ID,
        _authorization(),
    )
    assert lifecycle["snapshot"]["current_lifecycle_state"] == "claim_created"
    reuse_system = FakeSystem()
    reuse_result, _ = _run(tmp_path, reuse_system)
    assert reuse_result["category"] == "claim_attempt_id_conflict"
    assert "worktree" not in reuse_system.calls


@pytest.mark.parametrize(
    ("execution_status", "execution_category"),
    [
        ("failed", "codex_structured_failure"),
        ("timed_out", "codex_timed_out"),
        ("cancelled", "codex_cancelled"),
    ],
)
def test_process_terminal_append_failure_surfaces_storage_uncertainty(
    tmp_path: Path,
    execution_status: str,
    execution_category: str,
):
    system = FakeSystem(
        execution=CodexExecutionResult(
            execution_status,
            execution_category,
            25,
        )
    )

    result, database_path, store = _run_with_terminal_append_failure(
        tmp_path,
        system,
    )

    assert result["status"] == "failed"
    assert result["category"] == "lifecycle_storage_uncertain"
    assert result["attempt_id"] == ATTEMPT_ID
    assert store.terminal_append_attempts == 1
    assert system.calls.count("invoke") == 1
    assert "diff" not in system.calls
    lifecycle = SQLiteCodexPilotInitialClaimStore(database_path).read_lifecycle_state(
        ATTEMPT_ID,
        _authorization(),
    )
    assert lifecycle["snapshot"]["current_lifecycle_state"] == (
        "invocation_started"
    )


@pytest.mark.parametrize(
    ("status", "category", "expected_state"),
    [
        ("timed_out", "codex_timed_out", "timed_out"),
        ("cancelled", "codex_cancelled", "cancelled"),
        ("failed", "codex_structured_failure", "failed"),
    ],
)
def test_process_failures_terminalize_without_publication(
    tmp_path: Path,
    status: str,
    category: str,
    expected_state: str,
):
    system = FakeSystem(execution=CodexExecutionResult(status, category, 25))

    result, database_path = _run(tmp_path, system)

    assert result["status"] == status
    assert result["category"] == category
    assert "diff" not in system.calls
    lifecycle = SQLiteCodexPilotInitialClaimStore(database_path).read_lifecycle_state(
        ATTEMPT_ID,
        _authorization(),
    )
    assert lifecycle["snapshot"]["current_lifecycle_state"] == expected_state


def test_observed_budget_excess_blocks_commit_push_and_pr(tmp_path: Path):
    system = FakeSystem(
        execution=CodexExecutionResult("succeeded", "codex_completed", 75_000)
    )

    result, database_path = _run(tmp_path, system)

    assert result["status"] == "failed"
    assert result["category"] == "budget_exceeded"
    assert result["usage_category"] == "budget_exceeded"
    assert result["observed_usage_tokens"] == 75_000
    assert result["authorized_budget_tokens"] == 50_000
    assert result["usage_overage_tokens"] == 25_000
    assert result["usage_ratio_basis_points"] == 15_000
    assert "diff" not in system.calls
    assert "validation" not in system.calls
    assert "commit" not in system.calls
    assert "push" not in system.calls
    assert "pull_request" not in system.calls
    lifecycle = SQLiteCodexPilotInitialClaimStore(database_path).read_lifecycle_state(
        ATTEMPT_ID,
        _authorization(),
    )
    assert lifecycle["snapshot"]["current_lifecycle_state"] == "failed"


def test_known_within_budget_usage_reports_exact_bounded_telemetry(tmp_path: Path):
    system = FakeSystem(
        execution=CodexExecutionResult("succeeded", "codex_completed", 25_000)
    )

    result, _database_path = _run(tmp_path, system)

    assert result["status"] == "success"
    assert result["usage_category"] == "within_budget"
    assert result["observed_usage_tokens"] == 25_000
    assert result["authorized_budget_tokens"] == 50_000
    assert result["usage_overage_tokens"] == 0
    assert result["usage_ratio_basis_points"] == 5_000
    assert all(
        type(result[field]) is int
        for field in (
            "observed_usage_tokens",
            "authorized_budget_tokens",
            "usage_overage_tokens",
            "usage_ratio_basis_points",
        )
    )
    assert system.calls.count("invoke") == 1
    assert system.calls.count("pull_request") == 1


def test_usage_ratio_uses_deterministic_integer_floor_math(tmp_path: Path):
    authorization = _authorization()
    authorization["budget_ceiling"] = 3
    system = FakeSystem(
        execution=CodexExecutionResult("succeeded", "codex_completed", 1)
    )

    result, _database_path = _run(
        tmp_path,
        system,
        authorization=authorization,
    )

    assert result["observed_usage_tokens"] == 1
    assert result["authorized_budget_tokens"] == 3
    assert result["usage_overage_tokens"] == 0
    assert result["usage_ratio_basis_points"] == 3_333


def test_unknown_usage_reports_only_null_numeric_telemetry(tmp_path: Path):
    system = FakeSystem(
        execution=CodexExecutionResult("succeeded", "codex_completed", None)
    )

    result, _database_path = _run(tmp_path, system)

    assert result["usage_category"] == "usage_unknown"
    assert result["observed_usage_tokens"] is None
    assert result["authorized_budget_tokens"] is None
    assert result["usage_overage_tokens"] is None
    assert result["usage_ratio_basis_points"] is None


@pytest.mark.parametrize(
    "budget_ceiling",
    [0, -1, True, runner_module.MAX_AUTHORIZED_BUDGET_TOKENS + 1],
)
def test_invalid_budget_fails_before_usage_ratio_math(
    tmp_path: Path,
    budget_ceiling: object,
):
    authorization = _authorization()
    authorization["budget_ceiling"] = budget_ceiling
    system = FakeSystem()

    result, _database_path = _run(
        tmp_path,
        system,
        authorization=authorization,
    )

    assert result["category"] == "preclaim_static_preflight_failed"
    assert result["observed_usage_tokens"] is None
    assert result["authorized_budget_tokens"] is None
    assert result["usage_overage_tokens"] is None
    assert result["usage_ratio_basis_points"] is None
    assert system.calls == []


def test_absurd_usage_is_sanitized_without_public_or_durable_expansion(
    tmp_path: Path,
):
    absurd_usage = runner_module.MAX_OBSERVED_USAGE_TOKENS + 1
    system = FakeSystem(
        execution=CodexExecutionResult(
            "succeeded",
            "codex_completed",
            absurd_usage,
        )
    )

    result, database_path = _run(tmp_path, system)
    serialized = json.dumps(result, sort_keys=True)

    assert result["usage_category"] == "usage_unknown"
    assert result["observed_usage_tokens"] is None
    assert result["authorized_budget_tokens"] is None
    assert result["usage_overage_tokens"] is None
    assert result["usage_ratio_basis_points"] is None
    assert str(absurd_usage) not in serialized
    assert _handoff()["prompt"] not in serialized
    assert "synthetic-worktree" not in serialized
    assert "OPENAI_API_KEY" not in serialized
    lifecycle = SQLiteCodexPilotInitialClaimStore(database_path).read_lifecycle_state(
        ATTEMPT_ID,
        _authorization(),
    )
    assert lifecycle["lifecycle_read_category"] == "read_success"
    assert "observed_usage_tokens" not in lifecycle["snapshot"]


@pytest.mark.parametrize(
    ("field_name", "field_value", "category", "forbidden_call"),
    [
        (
            "first_diff",
            DiffGateResult(False, "unauthorized_path_changed"),
            "unauthorized_path_changed",
            "validation",
        ),
        (
            "validation",
            ValidationGateResult(False, "validation_failed", ("failed",)),
            "validation_failed",
            "commit",
        ),
        (
            "commit",
            GateResult(False, "commit_failed"),
            "commit_failed",
            "prepublication",
        ),
        (
            "prepublication",
            GateResult(False, "remote_branch_collision"),
            "remote_branch_collision",
            "push",
        ),
        (
            "push",
            GateResult(False, "push_failed"),
            "push_failed",
            "pull_request",
        ),
        (
            "publication",
            PublicationResult(False, "pull_request_create_failed"),
            "pull_request_create_failed",
            "never",
        ),
    ],
)
def test_postclaim_gate_failures_never_retry(
    tmp_path: Path,
    field_name: str,
    field_value: object,
    category: str,
    forbidden_call: str,
):
    system = FakeSystem()
    setattr(system, field_name, field_value)

    result, database_path = _run(tmp_path, system)

    assert result["status"] == "failed"
    assert result["category"] == category
    assert system.calls.count("invoke") == 1
    assert system.calls.count("push") <= 1
    assert system.calls.count("pull_request") <= 1
    if forbidden_call != "never":
        assert forbidden_call not in system.calls
    lifecycle = SQLiteCodexPilotInitialClaimStore(database_path).read_lifecycle_state(
        ATTEMPT_ID,
        _authorization(),
    )
    assert lifecycle["snapshot"]["current_lifecycle_state"] == "failed"


@pytest.mark.parametrize(
    ("field_name", "field_value", "forbidden_call"),
    [
        (
            "first_diff",
            DiffGateResult(False, "unauthorized_path_changed"),
            "validation",
        ),
        (
            "validation",
            ValidationGateResult(False, "validation_failed", ("failed",)),
            "commit",
        ),
    ],
)
def test_post_worker_gate_terminal_append_failure_stops_publication(
    tmp_path: Path,
    field_name: str,
    field_value: object,
    forbidden_call: str,
):
    system = FakeSystem()
    setattr(system, field_name, field_value)

    result, database_path, store = _run_with_terminal_append_failure(
        tmp_path,
        system,
    )

    assert result["status"] == "failed"
    assert result["category"] == "lifecycle_storage_uncertain"
    assert store.terminal_append_attempts == 1
    assert forbidden_call not in system.calls
    assert "push" not in system.calls
    assert "pull_request" not in system.calls
    lifecycle = SQLiteCodexPilotInitialClaimStore(database_path).read_lifecycle_state(
        ATTEMPT_ID,
        _authorization(),
    )
    assert lifecycle["snapshot"]["current_lifecycle_state"] == (
        "invocation_started"
    )


@pytest.mark.parametrize(
    ("field_name", "field_value", "expected_pull_request_calls"),
    [
        ("push", GateResult(False, "push_failed"), 0),
        (
            "publication",
            PublicationResult(False, "pull_request_create_failed"),
            1,
        ),
    ],
)
def test_publication_failure_terminal_append_failure_never_retries(
    tmp_path: Path,
    field_name: str,
    field_value: object,
    expected_pull_request_calls: int,
):
    system = FakeSystem()
    setattr(system, field_name, field_value)

    result, database_path, store = _run_with_terminal_append_failure(
        tmp_path,
        system,
    )

    assert result["status"] == "failed"
    assert result["category"] == "lifecycle_storage_uncertain"
    assert store.terminal_append_attempts == 1
    assert system.calls.count("invoke") == 1
    assert system.calls.count("push") == 1
    assert system.calls.count("pull_request") == expected_pull_request_calls
    lifecycle = SQLiteCodexPilotInitialClaimStore(database_path).read_lifecycle_state(
        ATTEMPT_ID,
        _authorization(),
    )
    assert lifecycle["snapshot"]["current_lifecycle_state"] == (
        "invocation_started"
    )


def test_postvalidation_diff_change_blocks_commit(tmp_path: Path):
    system = FakeSystem(
        second_diff=DiffGateResult(
            True,
            "diff_allowed",
            ("docs/development/other.md",),
        )
    )

    result, _database_path = _run(tmp_path, system)

    assert result["category"] == "post_validation_diff_changed"
    assert "commit" not in system.calls


class FinalAppendFailureStore(SQLiteCodexPilotInitialClaimStore):
    def append_lifecycle_event(self, *args, **kwargs):
        if kwargs.get("next_lifecycle_state") == "pr_opened_and_stopped":
            return {
                "lifecycle_append_category": "claim_store_unavailable",
                "event_sequence": None,
                "lifecycle_state": None,
            }
        return super().append_lifecycle_event(*args, **kwargs)


class FinalAndTerminalAppendFailureStore(TerminalAppendFailureStore):
    def append_lifecycle_event(self, *args, **kwargs):
        if kwargs.get("next_lifecycle_state") == "pr_opened_and_stopped":
            return {
                "lifecycle_append_category": "claim_store_unavailable",
                "event_sequence": None,
                "lifecycle_state": None,
            }
        return super().append_lifecycle_event(*args, **kwargs)


def test_pr_audit_uncertainty_does_not_create_a_second_pr(tmp_path: Path):
    system = FakeSystem()
    runner = SupervisedCodexPilotRunner(
        system=system,
        claim_store_factory=FinalAppendFailureStore,
        attempt_id_factory=lambda: ATTEMPT_ID,
    )

    result = runner.run(
        handoff=_handoff(),
        evidence=_evidence(),
        authorization=_authorization(),
        reviewed_prompt=_reviewed_prompt(_handoff()),
        claim_store_path=tmp_path / "control.sqlite3",
        static_preflight_passed=True,
    )

    assert result["category"] == "publication_audit_storage_uncertain"
    assert system.calls.count("pull_request") == 1
    assert system.calls.count("push") == 1
    lifecycle = SQLiteCodexPilotInitialClaimStore(
        tmp_path / "control.sqlite3"
    ).read_lifecycle_state(
        ATTEMPT_ID,
        _authorization(),
    )
    assert lifecycle["snapshot"]["current_lifecycle_state"] == "failed"


def test_pr_audit_and_terminal_append_uncertainty_never_republishes(tmp_path: Path):
    system = FakeSystem()
    stores: list[FinalAndTerminalAppendFailureStore] = []

    def factory(database_path: Path) -> FinalAndTerminalAppendFailureStore:
        store = FinalAndTerminalAppendFailureStore(database_path)
        stores.append(store)
        return store

    result, database_path = _run(
        tmp_path,
        system,
        claim_store_factory=factory,
    )

    assert result["status"] == "failed"
    assert result["category"] == "lifecycle_storage_uncertain"
    assert result["pull_request_identity"] == "pr-400"
    assert len(stores) == 1
    assert stores[0].terminal_append_attempts == 1
    assert system.calls.count("invoke") == 1
    assert system.calls.count("push") == 1
    assert system.calls.count("pull_request") == 1
    lifecycle = SQLiteCodexPilotInitialClaimStore(database_path).read_lifecycle_state(
        ATTEMPT_ID,
        _authorization(),
    )
    assert lifecycle["snapshot"]["current_lifecycle_state"] == (
        "invocation_started"
    )


def _configure_windows_candidate_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    local_app_data = tmp_path / "local-app-data"
    program_files = tmp_path / "program-files"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setenv("ProgramFiles", str(program_files))
    return local_app_data / "OpenAI" / "Codex" / "bin", program_files


def _no_windows_path_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner_module.shutil, "which", lambda _name: None)


def test_windowsapps_codex_is_never_selected_or_version_preflighted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _per_user_root, program_files = _configure_windows_candidate_roots(
        tmp_path,
        monkeypatch,
    )
    packaged = (
        program_files
        / "WindowsApps"
        / "OpenAI.Codex_package"
        / "app"
        / "resources"
        / "codex.exe"
    )
    _write_windows_executable(packaged)

    def fake_which(name: str) -> str | None:
        return str(packaged) if name in {"codex.exe", "codex"} else None

    preflighted: list[CodexLaunchSpec] = []
    monkeypatch.setattr(runner_module.shutil, "which", fake_which)

    spec = runner_module._resolve_windows_codex_launch_spec(
        version_preflight=lambda candidate: (
            preflighted.append(candidate) or GateResult(True, "runtime_ready")
        )
    )

    assert spec is None
    assert preflighted == []
    assert runner_module._is_windows_apps_path(packaged)


def test_windows_direct_per_user_codex_is_runnable_and_selected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    per_user_root, _program_files = _configure_windows_candidate_roots(
        tmp_path,
        monkeypatch,
    )
    native = per_user_root / "codex.exe"
    _write_windows_executable(native)
    _no_windows_path_tools(monkeypatch)
    preflighted: list[CodexLaunchSpec] = []

    spec = runner_module._resolve_windows_codex_launch_spec(
        version_preflight=lambda candidate: (
            preflighted.append(candidate) or GateResult(True, "runtime_ready")
        )
    )

    assert spec is not None
    assert spec.kind == "native_exe"
    assert spec.argv_prefix == (str(native.resolve()),)
    assert runner_module._codex_launch_spec_is_current(spec)
    assert preflighted == [spec]


def test_windows_hashed_per_user_codex_is_runnable_and_selected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    per_user_root, _program_files = _configure_windows_candidate_roots(
        tmp_path,
        monkeypatch,
    )
    native = per_user_root / "version-or-hash" / "codex.exe"
    _write_windows_executable(native)
    _no_windows_path_tools(monkeypatch)

    spec = runner_module._resolve_windows_codex_launch_spec(
        version_preflight=lambda _candidate: GateResult(True, "runtime_ready")
    )

    assert spec is not None
    assert spec.kind == "native_exe"
    assert spec.argv_prefix == (str(native.resolve()),)


def test_unrunnable_direct_per_user_candidate_falls_back_to_hashed_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    per_user_root, _program_files = _configure_windows_candidate_roots(
        tmp_path,
        monkeypatch,
    )
    direct = per_user_root / "codex.exe"
    hashed = per_user_root / "working-child" / "codex.exe"
    _write_windows_executable(direct)
    _write_windows_executable(hashed)
    _no_windows_path_tools(monkeypatch)
    preflighted: list[CodexLaunchSpec] = []

    def preflight(candidate: CodexLaunchSpec) -> GateResult:
        preflighted.append(candidate)
        return GateResult(
            candidate.argv_prefix == (str(hashed.resolve()),),
            "bounded",
        )

    spec = runner_module._resolve_windows_codex_launch_spec(
        version_preflight=preflight
    )

    assert spec is not None
    assert spec.argv_prefix == (str(hashed.resolve()),)
    assert [candidate.argv_prefix for candidate in preflighted] == [
        (str(direct.resolve()),),
        (str(hashed.resolve()),),
    ]


def test_broken_windowsapps_candidate_never_blocks_working_per_user_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    per_user_root, program_files = _configure_windows_candidate_roots(
        tmp_path,
        monkeypatch,
    )
    per_user = per_user_root / "codex.exe"
    packaged = program_files / "WindowsApps" / "package" / "codex.exe"
    _write_windows_executable(per_user)
    _write_windows_executable(packaged)

    def fake_which(name: str) -> str | None:
        return str(packaged) if name in {"codex.exe", "codex"} else None

    monkeypatch.setattr(runner_module.shutil, "which", fake_which)
    selection_preflights: list[CodexLaunchSpec] = []
    spec = runner_module._resolve_windows_codex_launch_spec(
        version_preflight=lambda candidate: (
            selection_preflights.append(candidate)
            or GateResult(True, "runtime_ready")
        )
    )
    assert spec is not None
    assert spec.argv_prefix == (str(per_user.resolve()),)
    assert selection_preflights == [spec]

    service = SystemCodexPilotServices(
        tmp_path,
        launch_spec_resolver=lambda: spec,
    )
    runtime_preflights: list[CodexLaunchSpec] = []
    monkeypatch.setattr(
        service,
        "_version_preflight",
        lambda candidate: (
            runtime_preflights.append(candidate)
            or GateResult(True, "runtime_ready")
        ),
    )
    assert service.runtime_gate() == GateResult(True, "runtime_ready")
    assert runtime_preflights == [spec]


def test_multiple_hashed_per_user_candidates_choose_newest_then_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    per_user_root, _program_files = _configure_windows_candidate_roots(
        tmp_path,
        monkeypatch,
    )
    older = per_user_root / "old" / "codex.exe"
    newer_z = per_user_root / "z-new" / "codex.exe"
    newer_a = per_user_root / "a-new" / "codex.exe"
    for candidate in (older, newer_z, newer_a):
        _write_windows_executable(candidate)
    os.utime(older, ns=(1_000_000_000, 1_000_000_000))
    os.utime(newer_z, ns=(2_000_000_000, 2_000_000_000))
    os.utime(newer_a, ns=(2_000_000_000, 2_000_000_000))
    _no_windows_path_tools(monkeypatch)
    preflighted: list[CodexLaunchSpec] = []

    spec = runner_module._resolve_windows_codex_launch_spec(
        version_preflight=lambda candidate: (
            preflighted.append(candidate) or GateResult(True, "runtime_ready")
        )
    )

    assert spec is not None
    assert spec.argv_prefix == (str(newer_a.resolve()),)
    assert preflighted == [spec]


def test_safe_standalone_path_native_is_accepted_after_per_user_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _per_user_root, _program_files = _configure_windows_candidate_roots(
        tmp_path,
        monkeypatch,
    )
    native = tmp_path / "standalone" / "codex.exe"
    _write_windows_executable(native)

    def fake_which(name: str) -> str | None:
        return str(native) if name in {"codex.exe", "codex"} else None

    monkeypatch.setattr(runner_module.shutil, "which", fake_which)

    spec = runner_module._resolve_windows_codex_launch_spec(
        version_preflight=lambda _candidate: GateResult(True, "runtime_ready")
    )

    assert spec is not None
    assert spec.kind == "native_exe"
    assert spec.argv_prefix == (str(native.resolve()),)


def test_windows_npm_shim_derives_shell_free_node_launcher_without_parsing_shim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _configure_windows_candidate_roots(tmp_path, monkeypatch)
    npm_root = tmp_path / "npm"
    shim = npm_root / "codex.cmd"
    shim.parent.mkdir(parents=True)
    shim.write_text("not a command that Phoenix executes or parses", encoding="utf-8")
    launcher = npm_root / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/usr/bin/env node\n", encoding="utf-8")
    node = tmp_path / "node" / "node.exe"
    _write_windows_executable(node)

    def fake_which(name: str) -> str | None:
        return {
            "codex.exe": None,
            "codex.cmd": str(shim),
            "node.exe": str(node),
        }.get(name)

    monkeypatch.setattr(runner_module.shutil, "which", fake_which)

    spec = runner_module._resolve_windows_codex_launch_spec(
        version_preflight=lambda _candidate: GateResult(True, "runtime_ready")
    )

    assert spec is not None
    assert spec.kind == "npm_node_launcher"
    assert spec.argv_prefix == (str(node.resolve()), str(launcher.resolve()))
    assert runner_module._codex_launch_spec_is_current(spec)


@pytest.mark.parametrize("missing", ["launcher", "node"])
def test_windows_npm_launch_rejects_missing_required_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
):
    _configure_windows_candidate_roots(tmp_path, monkeypatch)
    npm_root = tmp_path / "npm"
    shim = npm_root / "codex.cmd"
    shim.parent.mkdir(parents=True)
    shim.write_text("shim", encoding="utf-8")
    launcher = npm_root / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
    if missing != "launcher":
        launcher.parent.mkdir(parents=True)
        launcher.write_text("launcher", encoding="utf-8")
    node = tmp_path / "node" / "node.exe"
    if missing != "node":
        _write_windows_executable(node)

    def fake_which(name: str) -> str | None:
        return {
            "codex.exe": None,
            "codex.cmd": str(shim),
            "node.exe": None if missing == "node" else str(node),
        }.get(name)

    monkeypatch.setattr(runner_module.shutil, "which", fake_which)

    assert (
        runner_module._resolve_windows_codex_launch_spec(
            version_preflight=lambda _candidate: GateResult(True, "runtime_ready")
        )
        is None
    )


def test_all_per_user_candidates_fail_then_runnable_npm_fallback_is_selected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    per_user_root, _program_files = _configure_windows_candidate_roots(
        tmp_path,
        monkeypatch,
    )
    per_user = per_user_root / "codex.exe"
    _write_windows_executable(per_user)
    npm_root = tmp_path / "npm"
    shim = npm_root / "codex.cmd"
    shim.parent.mkdir(parents=True)
    shim.write_text("never parsed", encoding="utf-8")
    launcher = npm_root / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("launcher", encoding="utf-8")
    node = tmp_path / "node" / "node.exe"
    _write_windows_executable(node)

    def fake_which(name: str) -> str | None:
        return {"codex.cmd": str(shim), "node.exe": str(node)}.get(name)

    preflighted_kinds: list[str] = []
    monkeypatch.setattr(runner_module.shutil, "which", fake_which)

    def preflight(candidate: CodexLaunchSpec) -> GateResult:
        preflighted_kinds.append(candidate.kind)
        return GateResult(candidate.kind == "npm_node_launcher", "bounded")

    spec = runner_module._resolve_windows_codex_launch_spec(
        version_preflight=preflight
    )

    assert spec is not None
    assert spec.kind == "npm_node_launcher"
    assert preflighted_kinds == ["native_exe", "npm_node_launcher"]


def test_every_windows_candidate_preflight_failure_is_bounded_and_path_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    per_user_root, _program_files = _configure_windows_candidate_roots(
        tmp_path,
        monkeypatch,
    )
    private_child_name = "private-hashed-child"
    candidate = per_user_root / private_child_name / "codex.exe"
    _write_windows_executable(candidate)
    _no_windows_path_tools(monkeypatch)
    service = SystemCodexPilotServices(
        tmp_path,
        launch_spec_resolver=lambda: runner_module._resolve_windows_codex_launch_spec(
            version_preflight=lambda _candidate: GateResult(
                False,
                "codex_launch_failed",
            )
        ),
    )

    result = service.runtime_gate()

    assert result == GateResult(False, "codex_launch_spec_unavailable")
    assert str(tmp_path) not in repr(result)
    assert private_child_name not in repr(result)


def test_launch_resolution_rejects_symlink_candidate(
    tmp_path: Path,
):
    target = tmp_path / "target.exe"
    _write_windows_executable(target)
    link = tmp_path / "codex.exe"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("host does not permit file symlinks")

    assert (
        runner_module._launch_file_identity(link, require_windows_exe=True) is None
    )


def test_system_codex_launch_has_no_shell_or_wrapper_fallback():
    source = inspect.getsource(runner_module.SystemCodexPilotServices)
    resolver_source = inspect.getsource(
        runner_module._resolve_windows_codex_launch_spec
    )

    assert "shell=True" not in source
    assert "cmd.exe" not in source + resolver_source
    assert "powershell" not in (source + resolver_source).casefold()
    assert "os.system" not in source + resolver_source
    assert "read_text" not in resolver_source


def test_worker_prompt_and_codex_argv_have_no_publication_or_bypass_authority(
    tmp_path: Path,
):
    handoff = _handoff()
    prompt = render_codex_worker_prompt(
        package=handoff,
        allowed_paths=(ALLOWED_PATH,),
    )
    spec = _native_launch_spec(tmp_path)
    argv = _codex_exec_argv(spec, Path("worktree"), platform_name="nt")

    task = handoff["task"]
    assert isinstance(task, dict)
    assert f"Task ID: {task['task_id']}" in prompt
    assert f"Task title: {task['title']}" in prompt
    assert f"Reviewed objective: {task['objective']}" in prompt
    assert handoff["prompt"] in prompt
    assert f"- {ALLOWED_PATH}" in prompt
    assert "Required Validation Commands" not in prompt
    assert "Required PR Body Headings" not in prompt
    assert handoff["expected_pr_title"] not in prompt
    assert all(command not in prompt for command in VALIDATION_COMMANDS)
    assert all(
        heading not in prompt for heading in handoff["required_pr_body_headings"]
    )
    assert "Do not stage, commit, push, open a pull request" in prompt
    assert argv[:1] == list(spec.argv_prefix)
    assert "--ask-for-approval" in argv
    assert argv[argv.index("--ask-for-approval") + 1] == "never"
    assert argv.index("--ask-for-approval") < argv.index("exec")
    assert argv[argv.index("--sandbox") + 1] == "workspace-write"
    assert "--ephemeral" in argv
    assert "--json" in argv
    assert "sandbox_workspace_write.network_access=false" in argv
    assert 'web_search="disabled"' in argv
    assert "features.unified_exec=false" in argv
    joined = " ".join(argv)
    assert "danger-full-access" not in joined
    assert "dangerously-bypass" not in joined
    assert "--yolo" not in joined


def test_worker_prompt_is_deterministically_bound_to_reviewed_task_content():
    handoff = _handoff()
    first = render_codex_worker_prompt(
        package=handoff,
        allowed_paths=(ALLOWED_PATH,),
    )
    second = render_codex_worker_prompt(
        package=handoff,
        allowed_paths=(ALLOWED_PATH,),
    )
    changed = _handoff()
    changed["prompt"] = "Apply a different reviewed clarification and stop."

    assert first == second
    assert first != render_codex_worker_prompt(
        package=changed,
        allowed_paths=(ALLOWED_PATH,),
    )


def test_worker_prompt_rejects_phoenix_validation_commands():
    handoff = _handoff()
    handoff["prompt"] = f"Update the document. Then run {VALIDATION_COMMANDS[0]}."

    with pytest.raises(ValueError, match="validation commands"):
        render_codex_worker_prompt(
            package=handoff,
            allowed_paths=(ALLOWED_PATH,),
        )


def test_capability_probe_uses_disposable_git_workspace_and_requires_exact_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    spec = _native_launch_spec(tmp_path)
    service = SystemCodexPilotServices(
        Path.cwd(),
        launch_spec_resolver=lambda: spec,
    )
    observed: dict[str, object] = {}

    def fake_version_preflight(launch_spec):
        observed["preflight_spec"] = launch_spec
        return GateResult(True, "runtime_ready")

    def fake_run_codex_process(
        *,
        workspace,
        prompt,
        timeout_seconds,
        on_started,
        launch_spec,
    ):
        observed["workspace"] = workspace
        observed["prompt"] = prompt
        observed["timeout"] = timeout_seconds
        observed["probe_spec"] = launch_spec
        assert (workspace / ".git").exists()
        on_started()
        (workspace / CAPABILITY_MARKER_NAME).write_text(
            CAPABILITY_MARKER_CONTENT,
            encoding="utf-8",
        )
        return CodexExecutionResult("succeeded", "codex_completed", 1)

    monkeypatch.setattr(service, "_version_preflight", fake_version_preflight)
    monkeypatch.setattr(
        service,
        "_authentication_preflight",
        lambda launch_spec: GateResult(
            launch_spec is spec,
            "codex_authenticated",
        ),
    )
    monkeypatch.setattr(service, "_run_codex_process", fake_run_codex_process)

    result = service.capability_probe(30)

    assert result == CapabilityProbeResult(
        True,
        "workspace_write_capability_proved",
    )
    assert CAPABILITY_MARKER_NAME in str(observed["prompt"])
    assert observed["timeout"] == 30
    assert observed["preflight_spec"] is spec
    assert observed["probe_spec"] is spec
    assert not Path(observed["workspace"]).exists()


def test_capability_probe_without_marker_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    spec = _native_launch_spec(tmp_path)
    service = SystemCodexPilotServices(
        Path.cwd(),
        launch_spec_resolver=lambda: spec,
    )
    monkeypatch.setattr(
        service,
        "_version_preflight",
        lambda launch_spec: GateResult(launch_spec is spec, "runtime_ready"),
    )
    monkeypatch.setattr(
        service,
        "_authentication_preflight",
        lambda launch_spec: GateResult(
            launch_spec is spec,
            "codex_authenticated",
        ),
    )
    monkeypatch.setattr(
        service,
        "_run_codex_process",
        lambda **_kwargs: CodexExecutionResult("succeeded", "codex_completed", 1),
    )

    result = service.capability_probe(30)

    assert result == CapabilityProbeResult(
        False,
        "workspace_write_capability_unproved",
    )


def test_safe_version_preflight_uses_exact_cached_launch_spec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    spec = _native_launch_spec(tmp_path)
    resolutions: list[bool] = []
    launches: list[tuple[list[str], dict[str, object]]] = []

    def resolve() -> CodexLaunchSpec:
        resolutions.append(True)
        return spec

    def fake_run(argv, **kwargs):
        launches.append((list(argv), kwargs))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    service = SystemCodexPilotServices(
        tmp_path,
        launch_spec_resolver=resolve,
    )

    first = service.runtime_gate()
    second = service.runtime_gate()

    assert first == GateResult(True, "runtime_ready")
    assert second is first
    assert resolutions == [True]
    assert len(launches) == 1
    argv, kwargs = launches[0]
    assert argv == [*spec.argv_prefix, "--version"]
    assert kwargs["shell"] is False
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["stdout"] is subprocess.DEVNULL
    assert kwargs["stderr"] is subprocess.DEVNULL
    assert service.codex_launch_spec_kind == "native_exe"


def test_authentication_preflight_is_shell_free_bounded_and_cached(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    spec = _native_launch_spec(tmp_path)
    launches: list[tuple[list[str], dict[str, object]]] = []
    private_output = f"authenticated using {tmp_path / 'private-auth.json'}"

    def fake_run(argv, **kwargs):
        launches.append((list(argv), kwargs))
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=private_output,
            stderr=private_output,
        )

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        runner_module,
        "_codex_worker_environment",
        lambda **_kwargs: {"PATH": "bounded", "HTTPS_PROXY": "private-value"},
    )
    service = SystemCodexPilotServices(
        tmp_path,
        launch_spec_resolver=lambda: spec,
    )

    assert service.runtime_gate() == GateResult(True, "runtime_ready")
    first = service.authentication_gate()
    second = service.authentication_gate()

    assert first == GateResult(True, "codex_authenticated")
    assert second is first
    assert len(launches) == 2
    version_argv, version_kwargs = launches[0]
    auth_argv, auth_kwargs = launches[1]
    assert version_argv == [*spec.argv_prefix, "--version"]
    assert auth_argv == [*spec.argv_prefix, "login", "status"]
    assert version_kwargs["shell"] is False
    assert auth_kwargs["shell"] is False
    assert auth_kwargs["stdin"] is subprocess.DEVNULL
    assert auth_kwargs["stdout"] is subprocess.DEVNULL
    assert auth_kwargs["stderr"] is subprocess.DEVNULL
    assert private_output not in repr(first)


@pytest.mark.parametrize(
    ("failure", "expected_category"),
    [
        ("not_authenticated", "codex_authentication_unavailable"),
        ("launch", "codex_auth_preflight_failed"),
        ("timeout", "codex_auth_preflight_failed"),
    ],
)
def test_authentication_preflight_failures_are_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    expected_category: str,
):
    spec = _native_launch_spec(tmp_path)
    private_output = f"private auth detail at {tmp_path}"

    def fake_run(argv, **kwargs):
        del kwargs
        if argv[-1] == "--version":
            return subprocess.CompletedProcess(argv, 0)
        if failure == "launch":
            raise PermissionError(private_output)
        if failure == "timeout":
            raise subprocess.TimeoutExpired(argv, 30, stderr=private_output)
        return subprocess.CompletedProcess(
            argv,
            1,
            stdout=private_output,
            stderr=private_output,
        )

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    service = SystemCodexPilotServices(
        tmp_path,
        launch_spec_resolver=lambda: spec,
    )

    result = service.authentication_gate()

    assert result == GateResult(False, expected_category)
    assert private_output not in repr(result)
    assert str(tmp_path) not in repr(result)


def test_authentication_failure_blocks_model_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    spec = _native_launch_spec(tmp_path)
    service = SystemCodexPilotServices(
        tmp_path,
        launch_spec_resolver=lambda: spec,
    )
    probe_calls: list[bool] = []
    monkeypatch.setattr(
        service,
        "_version_preflight",
        lambda launch_spec: GateResult(launch_spec is spec, "runtime_ready"),
    )
    monkeypatch.setattr(
        service,
        "_authentication_preflight",
        lambda launch_spec: GateResult(
            False,
            "codex_authentication_unavailable",
        ),
    )
    monkeypatch.setattr(
        service,
        "_capability_probe",
        lambda *_args: probe_calls.append(True),
    )

    result = service.capability_probe(30)

    assert result == CapabilityProbeResult(
        False,
        "codex_authentication_unavailable",
    )
    assert probe_calls == []


def test_codex_worker_environment_allows_only_bounded_transport_context():
    source = {
        "PATH": "bounded-path",
        "HOME": "bounded-home",
        "HTTP_PROXY": "http://proxy.invalid:8080",
        "http_proxy": "http://lowercase.invalid:8080",
        "https_proxy": "https://secure.invalid:8443",
        "NO_PROXY": "localhost,127.0.0.1",
        "all_proxy": "http://all.invalid:8080",
        "OPENAI_API_KEY": "secret-openai",
        "CODEX_THREAD_ID": "secret-thread",
        "CODEX_SESSION_ID": "secret-session",
        "CODEX_API_KEY": "secret-codex-key",
        "CODEX_ACCESS_TOKEN": "secret-codex-token",
        "OPENAI_IDENTITY_TOKEN_FILE": "private-token-path",
        "OPENAI_FEDERATION_RULE_ID": "private-federation-rule",
        "GH_TOKEN": "secret-github",
        "GITHUB_TOKEN": "secret-github-2",
        "AWS_SECRET_ACCESS_KEY": "secret-cloud",
        "AZURE_CLIENT_SECRET": "secret-cloud-2",
        "GOOGLE_APPLICATION_CREDENTIALS": "private-path",
        "UNRELATED_AMBIENT_VALUE": "excluded",
    }

    environment = runner_module._codex_worker_environment(source)

    assert environment == {
        "PATH": "bounded-path",
        "HOME": "bounded-home",
        "HTTP_PROXY": "http://proxy.invalid:8080",
        "HTTPS_PROXY": "https://secure.invalid:8443",
        "NO_PROXY": "localhost,127.0.0.1",
        "ALL_PROXY": "http://all.invalid:8080",
    }
    assert "http_proxy" not in environment
    assert "https_proxy" not in environment
    assert "no_proxy" not in environment
    assert "all_proxy" not in environment
    assert "OPENAI_API_KEY" not in environment
    assert "CODEX_THREAD_ID" not in environment
    assert "CODEX_SESSION_ID" not in environment
    assert "CODEX_API_KEY" not in environment
    assert "CODEX_ACCESS_TOKEN" not in environment
    assert "OPENAI_IDENTITY_TOKEN_FILE" not in environment
    assert "OPENAI_FEDERATION_RULE_ID" not in environment
    assert "GH_TOKEN" not in environment
    assert "GITHUB_TOKEN" not in environment
    assert "AWS_SECRET_ACCESS_KEY" not in environment
    assert "AZURE_CLIENT_SECRET" not in environment
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in environment
    assert "UNRELATED_AMBIENT_VALUE" not in environment
    assert runner_module._codex_worker_environment(
        source,
        include_transport=False,
    ) == {"PATH": "bounded-path", "HOME": "bounded-home"}


def test_windows_core_environment_is_complete_case_insensitive_and_bounded():
    source = {
        "Path": "value-path",
        "pathext": "value-pathext",
        "Shell": "value-shell",
        "ComSpec": "value-comspec",
        "systemroot": "value-systemroot",
        "SystemDrive": "value-systemdrive",
        "UserName": "value-username",
        "userdomain": "value-userdomain",
        "UserProfile": "value-userprofile",
        "HomeDrive": "value-homedrive",
        "homepath": "value-homepath",
        "ProgramFiles": "value-programfiles",
        "programfiles(x86)": "value-programfiles-x86",
        "ProgramW6432": "value-programw6432",
        "ProgramData": "value-programdata",
        "LocalAppData": "value-localappdata",
        "AppData": "value-appdata",
        "Temp": "value-temp",
        "tmp": "value-tmp",
        "TmpDir": "value-tmpdir",
        "PowerShell": "value-powershell",
        "pwsh": "value-pwsh",
        "hTtP_pRoXy": "http://proxy.invalid:8080",
        "CODEX_THREAD_ID": "excluded-thread",
        "CODEX_SESSION_ID": "excluded-session",
        "CODEX_API_KEY": "excluded-codex-key",
        "CODEX_ACCESS_TOKEN": "excluded-codex-token",
        "OPENAI_API_KEY": "excluded-openai-key",
        "OPENAI_IDENTITY_TOKEN_FILE": "excluded-token-path",
        "OPENAI_FEDERATION_RULE_ID": "excluded-rule",
        "UNRELATED_KEY": "excluded-generic-key",
        "PRIVATE_SECRET": "excluded-generic-secret",
        "ARBITRARY_TOKEN": "excluded-generic-token",
        "UNRELATED_AMBIENT_VALUE": "excluded-arbitrary-value",
    }

    environment = runner_module._codex_worker_environment(
        source,
        platform_name="nt",
    )

    expected_core_names = {
        "PATH",
        "PATHEXT",
        "SHELL",
        "COMSPEC",
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "USERNAME",
        "USERDOMAIN",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "PROGRAMW6432",
        "PROGRAMDATA",
        "LOCALAPPDATA",
        "APPDATA",
        "TEMP",
        "TMP",
        "TMPDIR",
        "POWERSHELL",
        "PWSH",
    }
    assert set(environment) == expected_core_names | {"HTTP_PROXY"}
    assert environment["PATH"] == "value-path"
    assert environment["COMSPEC"] == "value-comspec"
    assert environment["PROGRAMFILES(X86)"] == "value-programfiles-x86"
    assert environment["HTTP_PROXY"] == "http://proxy.invalid:8080"
    for excluded in (
        "CODEX_THREAD_ID",
        "CODEX_SESSION_ID",
        "CODEX_API_KEY",
        "CODEX_ACCESS_TOKEN",
        "OPENAI_API_KEY",
        "OPENAI_IDENTITY_TOKEN_FILE",
        "OPENAI_FEDERATION_RULE_ID",
        "UNRELATED_KEY",
        "PRIVATE_SECRET",
        "ARBITRARY_TOKEN",
        "UNRELATED_AMBIENT_VALUE",
    ):
        assert excluded not in environment


def test_windows_core_environment_values_never_enter_public_gate_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    spec = _native_launch_spec(tmp_path)
    private_values = (
        "private-user-value",
        "private-domain-value",
        "private-program-path",
    )
    source = {
        "USERNAME": private_values[0],
        "USERDOMAIN": private_values[1],
        "PROGRAMFILES": private_values[2],
    }
    build_environment = runner_module._codex_worker_environment

    monkeypatch.setattr(
        runner_module,
        "_codex_worker_environment",
        lambda **_kwargs: build_environment(
            source,
            platform_name="nt",
        ),
    )
    monkeypatch.setattr(
        runner_module.subprocess,
        "run",
        lambda argv, **_kwargs: subprocess.CompletedProcess(argv, 1),
    )

    result = runner_module._codex_authentication_preflight(spec, cwd=tmp_path)

    assert result == GateResult(False, "codex_authentication_unavailable")
    assert all(value not in repr(result) for value in private_values)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("HTTP_PROXY", "http://proxy.invalid\x00secret"),
        ("HTTPS_PROXY", "https://proxy.invalid\nsecret"),
        ("ALL_PROXY", "socks5://proxy.invalid:1080"),
        ("HTTP_PROXY", "not-a-url"),
        ("NO_PROXY", "x" * (runner_module.MAX_PROXY_ENV_VALUE_BYTES + 1)),
    ],
)
def test_codex_worker_environment_rejects_malformed_proxy_values(
    name: str,
    value: str,
):
    with pytest.raises(runner_module._TransportEnvironmentError):
        runner_module._codex_worker_environment({name: value})


def test_malformed_proxy_blocks_auth_preflight_without_exposure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    spec = _native_launch_spec(tmp_path)
    private_proxy = "https://proxy.invalid/private\ncredential"
    launches: list[list[str]] = []
    for canonical, lowercase, _requires_url in (
        runner_module.CODEX_PROXY_ENVIRONMENT_NAMES
    ):
        monkeypatch.delenv(canonical, raising=False)
        monkeypatch.delenv(lowercase, raising=False)
    monkeypatch.setenv("HTTPS_PROXY", private_proxy)

    def fake_run(argv, **kwargs):
        del kwargs
        launches.append(list(argv))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    service = SystemCodexPilotServices(
        tmp_path,
        launch_spec_resolver=lambda: spec,
    )

    result = service.authentication_gate()

    assert result == GateResult(False, "codex_transport_environment_invalid")
    assert private_proxy not in repr(result)
    assert launches == [[*spec.argv_prefix, "--version"]]


@pytest.mark.parametrize(
    ("failure", "expected_category"),
    [
        ("launch", "codex_launch_failed"),
        ("nonzero", "codex_version_check_failed"),
    ],
)
def test_version_preflight_failures_are_bounded_and_hide_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    expected_category: str,
):
    spec = _native_launch_spec(tmp_path)

    def fake_run(argv, **kwargs):
        del kwargs
        if failure == "launch":
            raise PermissionError(f"private executable path: {argv[0]}")
        return subprocess.CompletedProcess(argv, 2)

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    service = SystemCodexPilotServices(
        tmp_path,
        launch_spec_resolver=lambda: spec,
    )

    result = service.runtime_gate()

    assert result == GateResult(False, expected_category)
    assert str(tmp_path) not in repr(result)


def test_preflight_probe_and_task_reuse_one_exact_launch_spec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    spec = _native_launch_spec(tmp_path)
    resolutions: list[bool] = []
    observed_specs: list[CodexLaunchSpec] = []

    def resolve() -> CodexLaunchSpec:
        resolutions.append(True)
        return spec

    service = SystemCodexPilotServices(
        tmp_path,
        launch_spec_resolver=resolve,
    )

    def fake_version_preflight(launch_spec):
        observed_specs.append(launch_spec)
        return GateResult(True, "runtime_ready")

    def fake_authentication_preflight(launch_spec):
        observed_specs.append(launch_spec)
        return GateResult(True, "codex_authenticated")

    def fake_probe(timeout_seconds, launch_spec):
        assert timeout_seconds == 30
        observed_specs.append(launch_spec)
        return CapabilityProbeResult(True, "workspace_write_capability_proved")

    def fake_process(**kwargs):
        observed_specs.append(kwargs["launch_spec"])
        return CodexExecutionResult("succeeded", "codex_completed", 1)

    monkeypatch.setattr(service, "_version_preflight", fake_version_preflight)
    monkeypatch.setattr(
        service,
        "_authentication_preflight",
        fake_authentication_preflight,
    )
    monkeypatch.setattr(service, "_capability_probe", fake_probe)
    monkeypatch.setattr(service, "_run_codex_process", fake_process)
    worktree = WorktreeHandle(tmp_path, BRANCH, BASE_SHA, b"git", (), "", "")

    assert service.runtime_gate() == GateResult(True, "runtime_ready")
    assert service.capability_probe(30).passed
    assert service.invoke_codex(worktree, "prompt", 60, lambda: None).status == (
        "succeeded"
    )
    assert resolutions == [True]
    assert observed_specs == [spec, spec, spec, spec]
    assert all(observed is spec for observed in observed_specs)


def test_verified_launch_spec_disappearance_fails_closed_without_reresolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    spec = _native_launch_spec(tmp_path)
    resolutions: list[bool] = []

    def resolve() -> CodexLaunchSpec:
        resolutions.append(True)
        return spec

    service = SystemCodexPilotServices(
        tmp_path,
        launch_spec_resolver=resolve,
    )
    monkeypatch.setattr(
        service,
        "_version_preflight",
        lambda launch_spec: GateResult(launch_spec is spec, "runtime_ready"),
    )
    assert service.runtime_gate().passed
    spec.file_identities[0].path.unlink()
    worktree = WorktreeHandle(tmp_path, BRANCH, BASE_SHA, b"git", (), "", "")

    result = service.invoke_codex(worktree, "prompt", 60, lambda: None)

    assert result == CodexExecutionResult("failed", "codex_launch_spec_changed")
    assert resolutions == [True]


class InterruptingProcess:
    def __init__(self, exception: BaseException):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO("")
        self.stderr = io.StringIO("")
        self.returncode = None
        self.pid = 999999
        self._exception = exception

    def wait(self, timeout=None):
        del timeout
        raise self._exception

    def poll(self):
        return None

    def kill(self):
        self.returncode = -1


class CapturingInput(io.StringIO):
    def __init__(self):
        super().__init__()
        self.captured = ""

    def close(self):
        self.captured = self.getvalue()
        super().close()


class SuccessfulProcess:
    def __init__(self):
        self.stdin = CapturingInput()
        self.stdout = io.StringIO(
            json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {"total_tokens": 12},
                }
            )
            + "\n"
        )
        self.stderr = io.StringIO("")
        self.returncode = None
        self.pid = 999998

    def wait(self, timeout=None):
        assert timeout == 60
        self.returncode = 0
        return 0

    def poll(self):
        return self.returncode

    def kill(self):
        self.returncode = -1


class FailedProcess:
    def __init__(self, *, stdout: str = "", stderr: str = ""):
        self.stdin = CapturingInput()
        self.stdout = io.StringIO(stdout)
        self.stderr = io.StringIO(stderr)
        self.returncode = None
        self.pid = 999997

    def wait(self, timeout=None):
        assert timeout == 60
        self.returncode = 2
        return 2

    def poll(self):
        return self.returncode

    def kill(self):
        self.returncode = -1


def test_real_task_process_uses_exact_worktree_stdin_and_one_safe_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    spec = _native_launch_spec(tmp_path)
    process = SuccessfulProcess()
    launches: list[tuple[list[str], dict[str, object]]] = []
    for canonical, lowercase, _requires_url in (
        runner_module.CODEX_PROXY_ENVIRONMENT_NAMES
    ):
        monkeypatch.delenv(canonical, raising=False)
        monkeypatch.delenv(lowercase, raising=False)
    monkeypatch.setenv("HTTPS_PROXY", "https://transport.invalid:8443")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-propagate")

    def fake_popen(argv, **kwargs):
        launches.append((list(argv), kwargs))
        return process

    monkeypatch.setattr(runner_module.subprocess, "Popen", fake_popen)
    service = SystemCodexPilotServices(tmp_path)
    started: list[bool] = []

    result = service._run_codex_process(
        workspace=tmp_path,
        prompt="exact reviewed worker prompt",
        timeout_seconds=60,
        on_started=lambda: started.append(True),
        launch_spec=spec,
    )

    assert result == CodexExecutionResult("succeeded", "codex_completed", 12)
    assert started == [True]
    assert len(launches) == 1
    argv, kwargs = launches[0]
    assert argv == _codex_exec_argv(spec, tmp_path)
    assert kwargs["cwd"] == tmp_path
    assert kwargs["shell"] is False
    assert kwargs["stderr"] is subprocess.PIPE
    assert kwargs["env"]["HTTPS_PROXY"] == "https://transport.invalid:8443"
    assert "OPENAI_API_KEY" not in kwargs["env"]
    assert process.stdin.captured == "exact reviewed worker prompt"


def test_process_launch_failure_is_bounded_and_does_not_leak_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    spec = _native_launch_spec(tmp_path)

    def fail_launch(*_args, **_kwargs):
        raise PermissionError(f"cannot execute {spec.argv_prefix[0]}")

    monkeypatch.setattr(runner_module.subprocess, "Popen", fail_launch)
    service = SystemCodexPilotServices(tmp_path)

    result = service._run_codex_process(
        workspace=tmp_path,
        prompt="reviewed prompt",
        timeout_seconds=60,
        on_started=lambda: None,
        launch_spec=spec,
    )

    assert result == CodexExecutionResult("failed", "codex_launch_failed")
    assert str(tmp_path) not in repr(result)


@pytest.mark.parametrize(
    ("diagnostic", "expected_category"),
    [
        ("error: unexpected argument '--bad'", "codex_cli_argument_or_config_rejected"),
        ("authentication required; login required", "codex_authentication_unavailable"),
        ("Windows sandbox initialization failed", "windows_sandbox_failed"),
        ("stream disconnected before completion", "codex_transport_unavailable"),
        ("bounded generic failure", "codex_nonzero_exit"),
    ],
)
def test_process_nonzero_exit_uses_only_bounded_diagnostic_category(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    diagnostic: str,
    expected_category: str,
):
    spec = _native_launch_spec(tmp_path)
    private_diagnostic = f"{diagnostic}: {tmp_path}"
    process = FailedProcess(stderr=private_diagnostic)
    monkeypatch.setattr(
        runner_module.subprocess,
        "Popen",
        lambda *_args, **_kwargs: process,
    )
    service = SystemCodexPilotServices(tmp_path)

    result = service._run_codex_process(
        workspace=tmp_path,
        prompt="reviewed prompt",
        timeout_seconds=60,
        on_started=lambda: None,
        launch_spec=spec,
    )

    assert result.category == expected_category
    assert str(tmp_path) not in repr(result)
    assert private_diagnostic not in repr(result)


@pytest.mark.parametrize(
    ("exception", "status", "category"),
    [
        (subprocess.TimeoutExpired(["codex"], 1), "timed_out", "codex_timed_out"),
        (KeyboardInterrupt(), "cancelled", "codex_cancelled"),
    ],
)
def test_process_timeout_and_cancellation_terminate_child_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exception: BaseException,
    status: str,
    category: str,
):
    spec = _native_launch_spec(tmp_path)
    process = InterruptingProcess(exception)
    terminated: list[object] = []
    monkeypatch.setattr(runner_module.subprocess, "Popen", lambda *_a, **_k: process)

    def fake_terminate(child):
        terminated.append(child)
        return True

    monkeypatch.setattr(
        runner_module,
        "_terminate_process_tree",
        fake_terminate,
    )
    service = SystemCodexPilotServices(Path.cwd())

    result = service._run_codex_process(
        workspace=Path.cwd(),
        prompt="reviewed prompt",
        timeout_seconds=1,
        on_started=lambda: None,
        launch_spec=spec,
    )

    assert result.status == status
    assert result.category == category
    assert terminated == [process]


def test_structured_json_parser_is_bounded_and_classifies_usage():
    success = _parse_codex_jsonl(
        json.dumps(
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 3, "output_tokens": 4},
            }
        )
    )
    fatal = _parse_codex_jsonl('{"type":"turn.failed"}\nnot-json')
    oversized = _parse_codex_jsonl("x" * (runner_module.MAX_JSONL_LINE_BYTES + 1))

    assert success == {
        "fatal": False,
        "turn_completed": True,
        "usage_tokens": 7,
        "failure_category": None,
    }
    assert fatal["fatal"] is True
    assert oversized["fatal"] is True


def test_system_service_delegates_preclaim_runtime_auth_and_capability_to_wsl(
    tmp_path: Path,
):
    worker = FakeWslWorker()
    service = SystemCodexPilotServices(tmp_path, wsl_worker=worker)

    assert service.runtime_gate() == GateResult(
        True,
        "wsl_codex_runtime_ready",
    )
    assert service.authentication_gate() == GateResult(
        True,
        "wsl_codex_authenticated",
    )
    assert service.capability_probe(30) == CapabilityProbeResult(
        True,
        "wsl_workspace_write_capability_proved",
    )
    assert service.execution_backend_kind == "wsl2_linux"
    assert not service.execution_backend_frozen


def test_system_service_invokes_wsl_shadow_with_exact_authorized_identity(
    tmp_path: Path,
):
    worker = FakeWslWorker()
    service = SystemCodexPilotServices(tmp_path / "canonical", wsl_worker=worker)
    started: list[bool] = []
    handle = WorktreeHandle(
        tmp_path / "worktree",
        BRANCH,
        BASE_SHA,
        b"git-control",
        (),
        "worktrees",
        "config",
        (ALLOWED_PATH,),
    )

    result = service.invoke_codex(
        handle,
        "exact reviewed prompt",
        90,
        lambda: started.append(True),
    )

    assert result == CodexExecutionResult("succeeded", "wsl_codex_completed", 7)
    assert worker.invocations == [
        {
            "windows_worktree": handle.path,
            "base_commit_sha": BASE_SHA,
            "allowed_paths": (ALLOWED_PATH,),
            "prompt": "exact reviewed prompt",
            "timeout_seconds": 90,
            "on_started": worker.invocations[0]["on_started"],
        }
    ]
    worker.invocations[0]["on_started"]()
    assert started == [True]


def test_wsl_runtime_blocker_prevents_claim_and_task_worktree(tmp_path: Path):
    worker = FakeWslWorker(
        runtime_result=WslGateResult(
            False,
            "wsl_codex_qualified_runtime_unavailable",
        )
    )
    system = FakeSystem()
    service = SystemCodexPilotServices(tmp_path, wsl_worker=worker)
    system.runtime = service.runtime_gate()
    claims: list[Path] = []
    result, _database = _run(
        tmp_path,
        system,
        claim_store_factory=lambda path: claims.append(path),
    )

    assert result["category"] == "wsl_codex_qualified_runtime_unavailable"
    assert claims == []
    assert system.calls == ["preclaim", "runtime"]


def test_wsl_auth_blocker_prevents_claim_and_task_worktree(tmp_path: Path):
    worker = FakeWslWorker(
        authentication_result=WslGateResult(
            False,
            "wsl_codex_authentication_unavailable",
        )
    )
    system = FakeSystem()
    service = SystemCodexPilotServices(tmp_path, wsl_worker=worker)
    system.runtime = service.runtime_gate()
    system.auth = service.authentication_gate()
    claims: list[Path] = []
    result, _database = _run(
        tmp_path,
        system,
        claim_store_factory=lambda path: claims.append(path),
    )

    assert result["category"] == "wsl_codex_authentication_unavailable"
    assert claims == []
    assert system.calls == ["preclaim", "runtime", "auth"]


def test_wsl_capability_blocker_prevents_claim_and_task_worktree(tmp_path: Path):
    worker = FakeWslWorker(
        capability_result=WslCapabilityResult(
            False,
            "wsl_workspace_write_capability_unproved",
        )
    )
    system = FakeSystem()
    service = SystemCodexPilotServices(tmp_path, wsl_worker=worker)
    system.runtime = service.runtime_gate()
    system.auth = service.authentication_gate()
    system.probe = service.capability_probe(30)
    claims: list[Path] = []
    result, _database = _run(
        tmp_path,
        system,
        claim_store_factory=lambda path: claims.append(path),
    )

    assert result["category"] == "wsl_workspace_write_capability_unproved"
    assert claims == []
    assert "worktree" not in system.calls


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _real_worktree(tmp_path: Path) -> WorktreeHandle:
    repository = tmp_path / "repository"
    worktree = tmp_path / "worktree"
    repository.mkdir()
    _git(repository, "init", "--quiet")
    _git(repository, "config", "user.name", "Phoenix Test")
    _git(repository, "config", "user.email", "test@phoenix.invalid")
    document = repository / ALLOWED_PATH
    document.parent.mkdir(parents=True)
    document.write_text("Initial documentation.\n", encoding="utf-8")
    unrelated = repository / "src" / "safe.py"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("VALUE = 1\n", encoding="utf-8")
    _git(repository, "add", "--", ALLOWED_PATH, "src/safe.py")
    _git(repository, "commit", "-m", "initial")
    head = _git(repository, "rev-parse", "HEAD")
    _git(repository, "worktree", "add", "-b", BRANCH, str(worktree), head)
    service = SystemCodexPilotServices(repository)
    control_state = service._git_control_state(worktree)
    assert control_state is not None
    git_refs, git_worktree_state, local_git_config = control_state
    return WorktreeHandle(
        worktree,
        BRANCH,
        head,
        (worktree / ".git").read_bytes(),
        git_refs,
        git_worktree_state,
        local_git_config,
    )


def test_diff_gate_allows_only_authorized_utf8_markdown(tmp_path: Path):
    worktree = _real_worktree(tmp_path)
    (worktree.path / ALLOWED_PATH).write_text(
        "Updated reviewed documentation.\n",
        encoding="utf-8",
    )

    result = SystemCodexPilotServices(tmp_path / "repository").inspect_diff(
        worktree,
        (ALLOWED_PATH,),
    )

    assert result == DiffGateResult(True, "diff_allowed", (ALLOWED_PATH,))


def test_phoenix_commit_has_exact_parent_branch_and_authorized_scope(tmp_path: Path):
    worktree = _real_worktree(tmp_path)
    (worktree.path / ALLOWED_PATH).write_text(
        "Committed reviewed documentation.\n",
        encoding="utf-8",
    )
    service = SystemCodexPilotServices(tmp_path / "repository")

    result = service.commit_authorized_changes(
        worktree,
        (ALLOWED_PATH,),
        "docs: commit reviewed documentation",
    )

    assert result == GateResult(True, "committed")
    assert _git(worktree.path, "rev-parse", "HEAD^") == worktree.base_commit_sha
    assert _git(worktree.path, "branch", "--show-current") == BRANCH
    assert _git(
        worktree.path,
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        "HEAD",
    ) == ALLOWED_PATH
    assert _git(worktree.path, "status", "--porcelain=v1") == ""


@pytest.mark.parametrize(
    ("mutation", "expected_category"),
    [
        ("tracked", "unauthorized_path_changed"),
        ("untracked", "unauthorized_path_changed"),
        ("binary", "binary_or_unreadable_change"),
        ("non_markdown", "unsafe_changed_path"),
        ("staged", "git_control_manipulation"),
    ],
)
def test_diff_gate_rejects_unauthorized_or_unsafe_state_without_cleanup(
    tmp_path: Path,
    mutation: str,
    expected_category: str,
):
    worktree = _real_worktree(tmp_path)
    allowed_paths = (ALLOWED_PATH,)
    evidence_path = worktree.path / ALLOWED_PATH
    if mutation == "tracked":
        evidence_path = worktree.path / "src" / "safe.py"
        evidence_path.write_text("VALUE = 2\n", encoding="utf-8")
    elif mutation == "untracked":
        evidence_path = worktree.path / "unexpected.txt"
        evidence_path.write_text("unexpected\n", encoding="utf-8")
    elif mutation == "binary":
        evidence_path.write_bytes(b"\x00\xff")
    elif mutation == "non_markdown":
        evidence_path = worktree.path / "docs" / "process" / "unsafe.txt"
        evidence_path.write_text("unsafe\n", encoding="utf-8")
        allowed_paths = ("docs/process/unsafe.txt",)
    else:
        evidence_path.write_text("staged\n", encoding="utf-8")
        _git(worktree.path, "add", "--", ALLOWED_PATH)

    result = SystemCodexPilotServices(tmp_path / "repository").inspect_diff(
        worktree,
        allowed_paths,
    )

    assert result.passed is False
    assert result.category == expected_category
    assert evidence_path.exists()


def test_diff_gate_rejects_symlink_when_platform_allows_creation(tmp_path: Path):
    worktree = _real_worktree(tmp_path)
    target = worktree.path / "target.md"
    target.write_text("target\n", encoding="utf-8")
    authorized = worktree.path / ALLOWED_PATH
    authorized.unlink()
    try:
        authorized.symlink_to(target)
    except OSError:
        pytest.skip("host does not allow an unprivileged symlink")

    result = SystemCodexPilotServices(tmp_path / "repository").inspect_diff(
        worktree,
        (ALLOWED_PATH,),
    )

    assert result.passed is False
    assert result.category in {
        "symlink_or_nonfile_change",
        "symlink_or_submodule_change",
    }


def test_diff_gate_rejects_extra_branch_control_manipulation(tmp_path: Path):
    worktree = _real_worktree(tmp_path)
    (worktree.path / ALLOWED_PATH).write_text("updated\n", encoding="utf-8")
    _git(worktree.path, "branch", "codex/unreviewed-branch")

    result = SystemCodexPilotServices(tmp_path / "repository").inspect_diff(
        worktree,
        (ALLOWED_PATH,),
    )

    assert result == DiffGateResult(False, "git_control_manipulation")


def test_system_preclaim_fetches_exact_main_and_checks_all_collisions(
    monkeypatch: pytest.MonkeyPatch,
):
    service = SystemCodexPilotServices(Path("repository"))
    calls: list[list[str]] = []
    authorization = _authorization()

    def fake_run(argv, *, cwd, timeout):
        del cwd, timeout
        calls.append(list(argv))
        if argv == ["git", "branch", "--show-current"]:
            output, returncode = "main\n", 0
        elif argv == ["git", "rev-parse", "HEAD"]:
            output, returncode = f"{BASE_SHA}\n", 0
        elif argv == ["git", "status", "--porcelain=v1"]:
            output, returncode = "", 0
        elif argv == ["git", "remote", "get-url", "origin"]:
            output, returncode = (
                "https://github.com/Phoenix-AI-Platform/phoenix-office.git\n",
                0,
            )
        elif argv[:2] == ["git", "fetch"]:
            output, returncode = "", 0
        elif argv[:2] == ["git", "rev-list"]:
            output, returncode = "0\t0\n", 0
        elif argv[:2] == ["git", "show-ref"]:
            output, returncode = "", 1
        elif argv[:2] == ["git", "ls-remote"]:
            output, returncode = "", 2
        elif argv[:3] == ["gh", "pr", "list"]:
            output, returncode = "[]", 0
        else:
            raise AssertionError(argv)
        return subprocess.CompletedProcess(argv, returncode, output, "")

    monkeypatch.setattr(service, "_run", fake_run)
    monkeypatch.setattr(
        service,
        "_validation_runtime_gate",
        lambda: GateResult(True, "validation_runtime_ready"),
    )

    result = service.preclaim_repository_gate(authorization)

    assert result == GateResult(True, "collision_gates_passed")
    fetch_index = next(index for index, call in enumerate(calls) if call[:2] == ["git", "fetch"])
    collision_index = next(
        index for index, call in enumerate(calls) if call[:2] == ["git", "show-ref"]
    )
    assert fetch_index < collision_index
    fetch = calls[fetch_index]
    assert fetch[-1] == "+refs/heads/main:refs/remotes/origin/main"


@pytest.mark.parametrize(
    ("local_code", "remote_code", "pull_requests", "category"),
    [
        (0, 2, "[]", "local_branch_collision"),
        (1, 0, "[]", "remote_branch_collision"),
        (1, 2, '[{"number":400}]', "duplicate_active_pr"),
    ],
)
def test_system_collision_gates_are_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    local_code: int,
    remote_code: int,
    pull_requests: str,
    category: str,
):
    service = SystemCodexPilotServices(Path("repository"))

    def fake_run(argv, *, cwd, timeout):
        del cwd, timeout
        if argv[:2] == ["git", "show-ref"]:
            return subprocess.CompletedProcess(argv, local_code, "", "")
        if argv[:2] == ["git", "ls-remote"]:
            return subprocess.CompletedProcess(argv, remote_code, "", "")
        if argv[:3] == ["gh", "pr", "list"]:
            return subprocess.CompletedProcess(argv, 0, pull_requests, "")
        raise AssertionError(argv)

    monkeypatch.setattr(service, "_run", fake_run)

    result = service._collision_gate(_authorization())

    assert result == GateResult(False, category)


def test_validation_runtime_preclaim_qualifies_exact_canonical_venv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    canonical = tmp_path / "canonical"
    runtime = _validation_runtime_spec(canonical)
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(argv, **kwargs):
        calls.append((list(argv), kwargs))
        return subprocess.CompletedProcess(argv, 0, "private output", "private error")

    monkeypatch.setenv("OPENAI_API_KEY", "must-not-propagate")
    monkeypatch.setenv("UNRELATED_SECRET", "must-not-propagate")
    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        runner_module,
        "_validation_tool_identity_is_current",
        lambda _runtime, _identity, **_kwargs: True,
    )
    service = SystemCodexPilotServices(
        canonical,
        validation_runtime_resolver=lambda _path: runtime,
        wsl_worker=FakeWslWorker(),
    )

    result = service._validation_runtime_gate()

    assert result == GateResult(True, "validation_runtime_ready")
    assert service.validation_runtime_frozen
    assert service._validation_runtime_spec == runtime
    assert [call[0][1:] for call in calls] == [
        ["-m", "pytest", "--version"],
        ["-m", "ruff", "--version"],
    ]
    assert all(call[0][0] == str(runtime.python_identity.path) for call in calls)
    assert all(call[1]["cwd"] == canonical for call in calls)
    assert all(call[1]["shell"] is False for call in calls)
    assert calls[0][1]["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert "PYTEST_DISABLE_PLUGIN_AUTOLOAD" not in calls[1][1]["env"]
    assert all("OPENAI_API_KEY" not in call[1]["env"] for call in calls)
    assert all("UNRELATED_SECRET" not in call[1]["env"] for call in calls)
    assert str(runtime.python_identity.path) not in repr(result)


def test_missing_canonical_venv_fails_validation_runtime_preclaim(tmp_path: Path):
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    service = SystemCodexPilotServices(canonical, wsl_worker=FakeWslWorker())

    result = service._validation_runtime_gate()

    assert result == GateResult(False, "validation_runtime_unavailable")
    assert not service.validation_runtime_frozen
    assert str(canonical) not in repr(result)


@pytest.mark.parametrize("missing_module", ["pytest", "ruff"])
def test_missing_validation_module_fails_preclaim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing_module: str,
):
    canonical = tmp_path / "canonical"
    runtime = _validation_runtime_spec(canonical)
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        return subprocess.CompletedProcess(
            argv,
            1 if argv[2] == missing_module else 0,
            "private output",
            "private error",
        )

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    service = SystemCodexPilotServices(
        canonical,
        validation_runtime_resolver=lambda _path: runtime,
        wsl_worker=FakeWslWorker(),
    )

    result = service._validation_runtime_gate()

    assert result == GateResult(False, "validation_runtime_unavailable")
    assert not service.validation_runtime_frozen
    assert calls[-1][2] == missing_module
    assert str(runtime.python_identity.path) not in repr(result)


def test_validation_uses_frozen_python_minimal_environment_and_worktree_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    canonical = tmp_path / "canonical"
    runtime = _validation_runtime_spec(canonical)
    worktree_path = tmp_path / "disposable-worktree"
    worktree_path.mkdir()
    worktree = WorktreeHandle(
        worktree_path,
        BRANCH,
        BASE_SHA,
        b"gitdir",
        (),
        "",
        "",
    )
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(argv, **kwargs):
        calls.append((list(argv), kwargs))
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setenv("OPENAI_API_KEY", "must-not-propagate")
    monkeypatch.setenv("GITHUB_TOKEN", "must-not-propagate")
    monkeypatch.setenv("ARBITRARY_AMBIENT_VALUE", "must-not-propagate")
    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        runner_module,
        "_validation_tool_identity_is_current",
        lambda _runtime, _identity, **_kwargs: True,
    )
    service = SystemCodexPilotServices(canonical)
    service._validation_runtime_spec = runtime
    service._validation_runtime_preflight_result = GateResult(
        True,
        "validation_runtime_ready",
    )

    result = service.run_validations(worktree, VALIDATION_COMMANDS)

    assert result == ValidationGateResult(
        True,
        "validation_passed",
        ("passed", "passed", "passed"),
    )
    assert calls[0][0] == [
        str(runtime.python_identity.path),
        "-m",
        "pytest",
        "--basetemp",
        ".pytest_tmp",
    ]
    assert calls[1][0] == [
        str(runtime.python_identity.path),
        "-m",
        "ruff",
        "check",
        ".",
        "--no-cache",
    ]
    assert calls[2][0] == ["git", "diff", "--check"]
    assert all(call[1]["cwd"] == worktree.path for call in calls)
    assert all(call[1]["shell"] is False for call in calls)
    assert calls[0][1]["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert "PYTEST_DISABLE_PLUGIN_AUTOLOAD" not in calls[1][1]["env"]
    for _argv, kwargs in calls:
        assert "OPENAI_API_KEY" not in kwargs["env"]
        assert "GITHUB_TOKEN" not in kwargs["env"]
        assert "ARBITRARY_AMBIENT_VALUE" not in kwargs["env"]
    assert not (worktree.path / ".venv").exists()


def test_validation_runtime_identity_change_fails_closed_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    canonical = tmp_path / "canonical"
    runtime = _validation_runtime_spec(canonical)
    worktree_path = tmp_path / "disposable-worktree"
    worktree_path.mkdir()
    worktree = WorktreeHandle(
        worktree_path,
        BRANCH,
        BASE_SHA,
        b"gitdir",
        (),
        "",
        "",
    )
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        runner_module,
        "_validation_tool_identity_is_current",
        lambda _runtime, _identity, **_kwargs: True,
    )
    service = SystemCodexPilotServices(canonical)
    service._validation_runtime_spec = runtime
    service._validation_runtime_preflight_result = GateResult(
        True,
        "validation_runtime_ready",
    )
    runtime.python_identity.path.write_bytes(b"MZchanged-runtime-identity")

    result = service.run_validations(worktree, VALIDATION_COMMANDS)

    assert result == ValidationGateResult(
        False,
        "validation_runtime_changed",
        ("runtime_changed",),
    )
    assert calls == []
    assert str(runtime.python_identity.path) not in repr(result)


def test_pytest_tool_identity_change_fails_closed_before_pytest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    canonical = tmp_path / "canonical"
    runtime = _validation_runtime_spec(canonical)
    worktree_path = tmp_path / "disposable-worktree"
    worktree_path.mkdir()
    worktree = WorktreeHandle(
        worktree_path,
        BRANCH,
        BASE_SHA,
        b"gitdir",
        (),
        "",
        "",
    )
    changed = next(
        identity.path
        for identity in runtime.pytest_identity.files
        if identity.relative_path.endswith("_pytest/main.py")
    )
    changed.write_text("changed pytest implementation\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    service = SystemCodexPilotServices(canonical)
    service._validation_runtime_spec = runtime
    service._validation_runtime_preflight_result = GateResult(
        True,
        "validation_runtime_ready",
    )

    result = service.run_validations(worktree, VALIDATION_COMMANDS)

    assert result == ValidationGateResult(
        False,
        "validation_runtime_changed",
        ("runtime_changed",),
    )
    assert calls == []
    assert str(changed) not in repr(result)


def test_ruff_tool_identity_change_fails_closed_before_ruff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    canonical = tmp_path / "canonical"
    runtime = _validation_runtime_spec(canonical)
    worktree_path = tmp_path / "disposable-worktree"
    worktree_path.mkdir()
    worktree = WorktreeHandle(
        worktree_path,
        BRANCH,
        BASE_SHA,
        b"gitdir",
        (),
        "",
        "",
    )
    changed = next(
        identity.path
        for identity in runtime.ruff_identity.files
        if identity.relative_path.endswith("ruff/__main__.py")
    )
    changed.write_text("changed ruff implementation\n", encoding="utf-8")
    calls: list[list[str]] = []
    real_identity_check = runner_module._validation_tool_identity_is_current

    def identity_check(runtime_spec, identity, **kwargs):
        if identity.name == "pytest":
            return True
        return real_identity_check(runtime_spec, identity, **kwargs)

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(
        runner_module,
        "_validation_tool_identity_is_current",
        identity_check,
    )
    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    service = SystemCodexPilotServices(canonical)
    service._validation_runtime_spec = runtime
    service._validation_runtime_preflight_result = GateResult(
        True,
        "validation_runtime_ready",
    )

    result = service.run_validations(worktree, VALIDATION_COMMANDS)

    assert result == ValidationGateResult(
        False,
        "validation_runtime_changed",
        ("passed", "runtime_changed"),
    )
    assert len(calls) == 1
    assert calls[0][1:3] == ["-m", "pytest"]
    assert str(changed) not in repr(result)


def test_unrelated_venv_file_does_not_change_qualified_tool_identities(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    canonical = tmp_path / "canonical"
    runtime = _validation_runtime_spec(canonical)
    unrelated = runtime.venv_root / "unrelated-package.txt"
    unrelated.write_text("unrelated mutable content\n", encoding="utf-8")

    def rediscover(_python, _venv, tool, **_kwargs):
        return (
            runtime.pytest_identity if tool == "pytest" else runtime.ruff_identity
        )

    monkeypatch.setattr(
        runner_module,
        "_discover_validation_tool_identity",
        rediscover,
    )

    assert runner_module._validation_tool_identity_is_current(
        runtime,
        runtime.pytest_identity,
        cwd=canonical,
    )
    assert runner_module._validation_tool_identity_is_current(
        runtime,
        runtime.ruff_identity,
        cwd=canonical,
    )


def test_validation_tool_identity_rejects_path_escape(tmp_path: Path):
    canonical = tmp_path / "canonical"
    runtime = _validation_runtime_spec(canonical)
    outside = tmp_path / "outside.py"
    outside.write_text("outside validation code\n", encoding="utf-8")
    pytest_root = runtime.venv_root / "Lib" / "site-packages" / "pytest"

    identity = runner_module._validation_tool_identity_from_paths(
        tool="pytest",
        venv_root=runtime.venv_root,
        roots=(pytest_root,),
        origins=(outside,),
        executable=None,
    )

    assert identity is None


def test_validation_rechecks_frozen_python_before_each_python_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    canonical = tmp_path / "canonical"
    runtime = _validation_runtime_spec(canonical)
    worktree_path = tmp_path / "disposable-worktree"
    worktree_path.mkdir()
    worktree = WorktreeHandle(
        worktree_path,
        BRANCH,
        BASE_SHA,
        b"gitdir",
        (),
        "",
        "",
    )
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        runtime.python_identity.path.write_bytes(b"MZchanged-after-pytest")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        runner_module,
        "_validation_tool_identity_is_current",
        lambda _runtime, _identity, **_kwargs: True,
    )
    service = SystemCodexPilotServices(canonical)
    service._validation_runtime_spec = runtime
    service._validation_runtime_preflight_result = GateResult(
        True,
        "validation_runtime_ready",
    )

    result = service.run_validations(worktree, VALIDATION_COMMANDS)

    assert result == ValidationGateResult(
        False,
        "validation_runtime_changed",
        ("passed", "runtime_changed"),
    )
    assert len(calls) == 1
    assert calls[0][1:3] == ["-m", "pytest"]


@pytest.mark.parametrize("failure_mode", ["nonzero", "timeout"])
def test_phoenix_validation_runs_in_order_and_stops_on_first_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_mode: str,
):
    canonical = tmp_path / "canonical"
    runtime = _validation_runtime_spec(canonical)
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()
    worktree = WorktreeHandle(
        worktree_path,
        BRANCH,
        BASE_SHA,
        b"gitdir",
        (),
        "",
        "",
    )
    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        del kwargs
        calls.append(list(argv))
        if len(calls) == 2 and failure_mode == "timeout":
            raise subprocess.TimeoutExpired(argv, 1)
        return subprocess.CompletedProcess(
            argv,
            1 if len(calls) == 2 else 0,
            "raw output must not escape",
            "raw failure must not escape",
        )

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        runner_module,
        "_validation_tool_identity_is_current",
        lambda _runtime, _identity, **_kwargs: True,
    )
    service = SystemCodexPilotServices(canonical)
    service._validation_runtime_spec = runtime
    service._validation_runtime_preflight_result = GateResult(
        True,
        "validation_runtime_ready",
    )

    result = service.run_validations(
        worktree,
        VALIDATION_COMMANDS,
    )

    assert result.passed is False
    assert result.category == (
        "validation_timed_out" if failure_mode == "timeout" else "validation_failed"
    )
    assert result.command_categories == (
        "passed",
        "timed_out" if failure_mode == "timeout" else "failed",
    )
    assert len(calls) == 2
    assert calls[0][0] == str(runtime.python_identity.path)
    assert calls[0][1:3] == ["-m", "pytest"]
    assert calls[1][0] == str(runtime.python_identity.path)
    assert calls[1][1:4] == ["-m", "ruff", "check"]
    assert not (worktree.path / ".venv").exists()
    assert "raw" not in repr(result)


def test_system_publication_rechecks_only_remote_state_and_uses_exact_branch(
    monkeypatch: pytest.MonkeyPatch,
):
    service = SystemCodexPilotServices(Path("repository"))
    calls: list[list[str]] = []

    def fake_run(argv, *, cwd, timeout):
        del cwd, timeout
        calls.append(list(argv))
        if argv[:2] == ["git", "ls-remote"] and "--exit-code" in argv:
            return subprocess.CompletedProcess(argv, 2, "", "")
        if argv[:3] == ["gh", "pr", "list"]:
            return subprocess.CompletedProcess(argv, 0, "[]", "")
        if "push" in argv and argv[0] == "git":
            return subprocess.CompletedProcess(argv, 0, "", "")
        if argv == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(argv, 0, f"{BASE_SHA}\n", "")
        if argv[:2] == ["git", "ls-remote"]:
            return subprocess.CompletedProcess(
                argv,
                0,
                f"{BASE_SHA}\trefs/heads/{BRANCH}\n",
                "",
            )
        if argv[:3] == ["gh", "pr", "create"]:
            return subprocess.CompletedProcess(
                argv,
                0,
                "https://github.com/Phoenix-AI-Platform/phoenix-office/pull/401\n",
                "",
            )
        if argv[:3] == ["gh", "pr", "view"]:
            return subprocess.CompletedProcess(
                argv,
                0,
                json.dumps(
                    {
                        "number": 401,
                        "headRefName": BRANCH,
                        "baseRefName": "main",
                        "title": authorization["expected_pr_title"],
                        "isDraft": True,
                        "state": "OPEN",
                    }
                ),
                "",
            )
        raise AssertionError(argv)

    monkeypatch.setattr(service, "_run", fake_run)
    authorization = _authorization()
    worktree = WorktreeHandle(
        Path("worktree"),
        BRANCH,
        BASE_SHA,
        b"gitdir",
        (),
        "",
        "",
    )

    assert service.prepublication_gate(authorization).passed is True
    assert service.push_authorized_branch(worktree).passed is True
    publication = service.create_pull_request(
        worktree,
        authorization,
        363,
        tuple(_handoff()["required_pr_body_headings"]),
        (ALLOWED_PATH,),
        VALIDATION_COMMANDS,
    )

    assert publication.pull_request_identity == "pr-401"
    assert not any(call[:2] == ["git", "show-ref"] for call in calls)
    push = next(call for call in calls if call[0] == "git" and "push" in call)
    assert f"HEAD:refs/heads/{BRANCH}" in push
    assert f"--force-with-lease=refs/heads/{BRANCH}:" in push
    create = next(call for call in calls if call[:3] == ["gh", "pr", "create"])
    assert create[create.index("--base") + 1] == "main"
    assert create[create.index("--head") + 1] == BRANCH
    assert create[create.index("--title") + 1] == authorization["expected_pr_title"]
    assert "--draft" in create
    body = create[create.index("--body") + 1]
    assert "Refs #363" in body
    for heading in _handoff()["required_pr_body_headings"]:
        assert f"## {heading}" in body


def test_pull_request_body_is_bounded_and_contains_no_raw_worker_material():
    body = _pull_request_body(
        source_issue_number=363,
        required_headings=tuple(_handoff()["required_pr_body_headings"]),
        changed_paths=(ALLOWED_PATH,),
        validation_commands=VALIDATION_COMMANDS,
    )

    assert "Refs #363" in body
    assert "Apply the reviewed" not in body
    assert "stdout" not in body
    assert "stderr" not in body


def test_cli_run_emits_only_bounded_result(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    paths = [tmp_path / name for name in ("handoff.json", "evidence.json", "auth.json")]
    for path in paths:
        path.write_text("{}", encoding="utf-8")
    handoff = _handoff()
    evidence = _evidence()
    authorization = _authorization()
    monkeypatch.setattr(
        cli,
        "_run_codex_pilot_authorization_inspection",
        lambda **_kwargs: (
            authorization,
            {"authorization_packet_valid_for_one_attempt": True},
        ),
    )
    monkeypatch.setattr(
        cli,
        "_load_codex_invocation_preflight",
        lambda _path: (
            handoff,
            {
                "static_eligible": True,
                "source_issue_number": 363,
                "repository": handoff["repository"],
                "base_branch": "main",
                "declared_changed_files": [ALLOWED_PATH],
                "external_checks_required": list(
                    runner_module.INVOCATION_EXTERNAL_CHECKS_REQUIRED
                ),
            },
        ),
    )
    monkeypatch.setattr(cli, "_read_json_object_file", lambda _path: evidence)
    monkeypatch.setattr(cli, "SystemCodexPilotServices", lambda _path: object())

    class FakeRunner:
        def __init__(self, *, system):
            assert system is not None

        def run(self, **kwargs):
            assert kwargs["claim_store_path"] == tmp_path / "control.sqlite3"
            return {
                "schema_version": "codex-pilot-run-result.v1",
                "status": "blocked",
                "category": "workspace_write_capability_unproved",
                "attempt_id": None,
                "branch_identity": None,
                "pull_request_identity": None,
                "changed_paths": [],
                "validation_categories": [],
                "usage_category": "usage_unknown",
                "observed_usage_tokens": None,
                "authorized_budget_tokens": None,
                "usage_overage_tokens": None,
                "usage_ratio_basis_points": None,
                "timeout_category": "timeout_unknown",
                "cancellation_category": "cancellation_unknown",
            }

    monkeypatch.setattr(cli, "SupervisedCodexPilotRunner", FakeRunner)

    exit_code = main(
        [
            "dev",
            "codex-pilot-run",
            *(str(path) for path in paths),
            "--claim-store",
            str(tmp_path / "control.sqlite3"),
            "--json",
        ]
    )
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert exit_code == 1
    assert payload["category"] == "workspace_write_capability_unproved"
    assert payload["observed_usage_tokens"] is None
    assert payload["authorized_budget_tokens"] is None
    assert payload["usage_overage_tokens"] is None
    assert payload["usage_ratio_basis_points"] is None
    assert str(tmp_path) not in output
    assert handoff["prompt"] not in output


def test_cli_unexpected_runner_failure_is_sanitized(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    paths = [tmp_path / name for name in ("handoff.json", "evidence.json", "auth.json")]
    for path in paths:
        path.write_text("{}", encoding="utf-8")
    handoff = _handoff()
    monkeypatch.setattr(
        cli,
        "_run_codex_pilot_authorization_inspection",
        lambda **_kwargs: (
            _authorization(),
            {"authorization_packet_valid_for_one_attempt": True},
        ),
    )
    monkeypatch.setattr(
        cli,
        "_load_codex_invocation_preflight",
        lambda _path: (
            handoff,
            {
                "static_eligible": True,
                "source_issue_number": 363,
                "repository": handoff["repository"],
                "base_branch": "main",
                "declared_changed_files": [ALLOWED_PATH],
                "external_checks_required": list(
                    runner_module.INVOCATION_EXTERNAL_CHECKS_REQUIRED
                ),
            },
        ),
    )
    monkeypatch.setattr(cli, "_read_json_object_file", lambda _path: _evidence())
    monkeypatch.setattr(cli, "SystemCodexPilotServices", lambda _path: object())

    class FailingRunner:
        def __init__(self, *, system):
            del system

        def run(self, **_kwargs):
            raise RuntimeError("raw private diagnostic must not escape")

    monkeypatch.setattr(cli, "SupervisedCodexPilotRunner", FailingRunner)

    exit_code = main(
        [
            "dev",
            "codex-pilot-run",
            *(str(path) for path in paths),
            "--claim-store",
            str(tmp_path / "control.sqlite3"),
            "--json",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert json.loads(output)["category"] == "runner_internal_failure"
    assert "raw private diagnostic" not in output
    assert str(tmp_path) not in output


def test_previous_invocation_prompt_renderer_remains_byte_for_byte_compatible():
    handoff = _handoff()
    prompt = _reviewed_prompt(handoff)

    assert cli._render_codex_invocation_request_prompt(
        package=handoff,
        preflight_report={
            "source_issue_number": 363,
            "repository": handoff["repository"],
            "base_branch": "main",
            "declared_changed_files": [ALLOWED_PATH],
            "external_checks_required": list(
                runner_module.INVOCATION_EXTERNAL_CHECKS_REQUIRED
            ),
        },
    ) == prompt
