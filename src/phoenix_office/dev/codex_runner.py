"""Fail-closed supervised Codex execution and Phoenix-owned publication."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import unicodedata
import uuid
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from io import TextIOBase
from pathlib import Path, PurePosixPath
from typing import Final, Protocol
from urllib.parse import urlsplit

from phoenix_office.core import (
    CODEX_PILOT_AUTHORIZATION_KINDS,
    CODEX_PILOT_BOUNDED_PYTHON_KIND,
    CODEX_PILOT_DOCS_ONLY_KIND,
    compose_codex_pilot_initial_claim_bundle,
    is_safe_codex_pilot_allowed_paths,
    prepare_codex_pilot_initial_claim_commit,
    validate_codex_pilot_authorization_packet,
)
from phoenix_office.dev.codex_claim_store import (
    SQLiteCodexPilotInitialClaimStore,
)
from phoenix_office.dev.codex_wsl import WslCodexWorker

RUNNER_SCHEMA_VERSION: Final = "codex-pilot-run-result.v1"
RUNNER_CLI: Final = "dev codex-pilot-run"
REPOSITORY_IDENTITY: Final = "Phoenix-AI-Platform/phoenix-office"
BASE_BRANCH: Final = "main"
CAPABILITY_MARKER_NAME: Final = "codex-workspace-write-marker.md"
CAPABILITY_MARKER_CONTENT: Final = "PHOENIX_CODEX_WORKSPACE_WRITE_PROBE_V1\n"
MAX_JSONL_LINES: Final = 10_000
MAX_JSONL_LINE_BYTES: Final = 1_000_000
MAX_MARKDOWN_BYTES: Final = 1_000_000
MAX_SYSTEM_OUTPUT_BYTES: Final = 2_000_000
MAX_PROXY_ENV_VALUE_BYTES: Final = 4096
MAX_WORKER_TASK_FACTS_CHARACTERS: Final = 24_000
MAX_WORKER_PROMPT_CHARACTERS: Final = 32_000
MAX_AUTHORIZED_BUDGET_TOKENS: Final = 1_000_000
MAX_OBSERVED_USAGE_TOKENS: Final = 1_000_000_000
USAGE_RATIO_BASIS_POINTS_SCALE: Final = 10_000
MAX_USAGE_RATIO_BASIS_POINTS: Final = (
    MAX_OBSERVED_USAGE_TOKENS * USAGE_RATIO_BASIS_POINTS_SCALE
)
VALIDATION_TIMEOUT_SECONDS: Final = 1800
VALIDATION_RUNTIME_PREFLIGHT_TIMEOUT_SECONDS: Final = 30
VALIDATION_PYTEST_BASETEMP_PREFIX: Final = "phoenix-pytest-"
MAX_VALIDATION_TOOL_DISCOVERY_OUTPUT_BYTES: Final = 65_536
MAX_VALIDATION_TOOL_FILES: Final = 512
MAX_VALIDATION_TOOL_TREE_ENTRIES: Final = 4096
MAX_VALIDATION_TOOL_FILE_BYTES: Final = 64 * 1024 * 1024
MAX_VALIDATION_TOOL_TOTAL_BYTES: Final = 256 * 1024 * 1024
VALIDATION_TOOL_CODE_SUFFIXES: Final = frozenset(
    {".py", ".pyi", ".pyd", ".so", ".dll", ".exe"}
)
VALIDATION_ENVIRONMENT_NAMES: Final = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "TMPDIR",
    "HOME",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "LOCALAPPDATA",
    "APPDATA",
)
CODEX_BASE_ENVIRONMENT_NAMES: Final = (
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
    "CODEX_HOME",
    "HOME",
    "WINDIR",
)
CODEX_PROXY_ENVIRONMENT_NAMES: Final = (
    ("HTTP_PROXY", "http_proxy", True),
    ("HTTPS_PROXY", "https_proxy", True),
    ("NO_PROXY", "no_proxy", False),
    ("ALL_PROXY", "all_proxy", True),
)
REQUIRED_PR_BODY_HEADINGS: Final = (
    "Summary",
    "Scope",
    "Changed files",
    "Out-of-scope confirmation",
    "Validation performed",
    "Risks",
)
REQUIRED_EVIDENCE_CONTROLS: Final = {
    "authentication_runner_access",
    "per_run_budget_ceiling",
    "operator_cancellation_timeout",
    "github_branch_creation_permission",
    "github_pr_creation_permission",
    "codex_cannot_approve_or_merge",
    "duplicate_active_pr_detection",
    "branch_collision_detection",
    "codex_task_time_availability",
    "final_ci_requirement",
    "assistant_architecture_review",
}
INVOCATION_EXTERNAL_CHECKS_REQUIRED: Final = (
    "duplicate PR detection for the source issue and handoff id",
    "branch collision detection before branch creation",
    "repository credentials and write-permission verification",
    "platform budget or usage ceiling enforcement",
    "operator cancellation support",
    "Codex availability",
    "post-PR CI results for the final head SHA",
    "assistant review verdict before merge",
)
VALIDATION_COMMANDS: Final = (
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest --basetemp .pytest_tmp",
    "python -m ruff check . --no-cache",
    "git diff --check",
)
VALIDATION_TOOL_DISCOVERY_SCRIPT: Final = """
import importlib.util
import json
import os
import sys
import sysconfig

tool = sys.argv[1]
names = {"pytest": ("pytest", "_pytest"), "ruff": ("ruff",)}.get(tool)
if names is None:
    raise SystemExit(2)
modules = {}
for name in names:
    spec = importlib.util.find_spec(name)
    if spec is None or not isinstance(spec.origin, str):
        raise SystemExit(3)
    modules[name] = {
        "origin": spec.origin,
        "locations": list(spec.submodule_search_locations or ()),
    }
executable = None
if tool == "ruff":
    scripts = sysconfig.get_path("scripts")
    executable = os.path.join(scripts, "ruff" + (sysconfig.get_config_var("EXE") or ""))
print(json.dumps(
    {"modules": modules, "executable": executable},
    sort_keys=True,
    separators=(",", ":"),
))
""".strip()
SENSITIVE_PATTERNS: Final = (
    re.compile(r"(?i)\b(?:sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9_]{8,})\b"),
    re.compile(r"(?i)\bgithub_pat_[A-Za-z0-9_]{8,}\b"),
    re.compile(r"(?i)\b(?:password|secret|token)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(?:[A-Z]:\\Users\\|/home/|/Users/)[^\s`]+"),
)


@dataclass(frozen=True, slots=True)
class GateResult:
    passed: bool
    category: str


@dataclass(frozen=True, slots=True)
class CapabilityProbeResult:
    passed: bool
    category: str


@dataclass(frozen=True, slots=True)
class CodexLaunchFileIdentity:
    path: Path = field(repr=False)
    device: int
    inode: int
    size: int
    modified_ns: int


@dataclass(frozen=True, slots=True)
class CodexLaunchSpec:
    argv_prefix: tuple[str, ...] = field(repr=False)
    kind: str
    file_identities: tuple[CodexLaunchFileIdentity, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class ValidationRuntimeSpec:
    python_identity: CodexLaunchFileIdentity = field(repr=False)
    venv_root: Path = field(repr=False)
    pytest_identity: ValidationToolIdentity = field(repr=False)
    ruff_identity: ValidationToolIdentity = field(repr=False)


@dataclass(frozen=True, slots=True)
class ValidationToolFileIdentity:
    path: Path = field(repr=False)
    relative_path: str = field(repr=False)
    device: int
    inode: int
    size: int
    modified_ns: int
    digest: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ValidationToolIdentity:
    name: str
    files: tuple[ValidationToolFileIdentity, ...] = field(repr=False)
    manifest_digest: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class WorktreeHandle:
    path: Path
    branch_name: str
    base_commit_sha: str
    git_control_bytes: bytes
    git_refs: tuple[str, ...]
    git_worktree_state: str
    local_git_config: str
    allowed_paths: tuple[str, ...] = ()
    pilot_kind: str = CODEX_PILOT_DOCS_ONLY_KIND


@dataclass(frozen=True, slots=True)
class WorktreeResult:
    passed: bool
    category: str
    handle: WorktreeHandle | None = None


@dataclass(frozen=True, slots=True)
class CodexExecutionResult:
    status: str
    category: str
    usage_tokens: int | None = None
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class DiffGateResult:
    passed: bool
    category: str
    changed_paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidationGateResult:
    passed: bool
    category: str
    command_categories: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PublicationResult:
    passed: bool
    category: str
    pull_request_identity: str | None = None


class CodexPilotSystem(Protocol):
    """Injectable system boundary for Git, Codex, validation, and GitHub."""

    def preclaim_repository_gate(self, authorization: dict[str, object]) -> GateResult:
        ...

    def runtime_gate(self) -> GateResult:
        ...

    def authentication_gate(self) -> GateResult:
        ...

    def capability_probe(self, timeout_seconds: int) -> CapabilityProbeResult:
        ...

    def create_worktree(self, authorization: dict[str, object]) -> WorktreeResult:
        ...

    def invoke_codex(
        self,
        worktree: WorktreeHandle,
        prompt: str,
        timeout_seconds: int,
        on_started: Callable[[], None],
    ) -> CodexExecutionResult:
        ...

    def inspect_diff(
        self,
        worktree: WorktreeHandle,
        allowed_paths: tuple[str, ...],
    ) -> DiffGateResult:
        ...

    def run_validations(
        self,
        worktree: WorktreeHandle,
        commands: tuple[str, ...],
    ) -> ValidationGateResult:
        ...

    def commit_authorized_changes(
        self,
        worktree: WorktreeHandle,
        changed_paths: tuple[str, ...],
        commit_message: str,
    ) -> GateResult:
        ...

    def prepublication_gate(
        self,
        authorization: dict[str, object],
    ) -> GateResult:
        ...

    def push_authorized_branch(self, worktree: WorktreeHandle) -> GateResult:
        ...

    def create_pull_request(
        self,
        worktree: WorktreeHandle,
        authorization: dict[str, object],
        source_issue_number: int,
        required_headings: tuple[str, ...],
        changed_paths: tuple[str, ...],
        validation_commands: tuple[str, ...],
    ) -> PublicationResult:
        ...


class LifecycleClaimStore(Protocol):
    def create_initial_claim_commit(
        self,
        preparation_result: object,
        authorization_package: object,
    ) -> object:
        ...

    def append_lifecycle_event(
        self,
        attempt_id: object,
        authorization_package: object,
        *,
        expected_event_sequence: object,
        expected_lifecycle_state: object,
        next_lifecycle_state: object,
        branch_identity: object = None,
        pull_request_identity: object = None,
        usage_category: object = None,
        timeout_category: object = None,
        cancellation_category: object = None,
        final_ci_category: object = None,
        assistant_review_verdict: object = None,
        recovery_category: object = None,
    ) -> dict[str, object]:
        ...


ClaimStoreFactory = Callable[[Path], LifecycleClaimStore]
AttemptIdFactory = Callable[[], str]
CodexLaunchSpecResolver = Callable[[], CodexLaunchSpec | None]
ValidationRuntimeResolver = Callable[[Path], ValidationRuntimeSpec | None]


def render_reviewed_codex_invocation_prompt(
    *,
    package: dict[str, object],
    preflight_report: dict[str, object],
) -> str:
    """Render the class-aware reviewed invocation request without side effects."""

    task = package["task"]
    if not isinstance(task, dict):
        raise ValueError("handoff task is invalid")
    declared_paths = preflight_report["declared_changed_files"]
    execution_class = task.get("execution_class")
    if execution_class is None:
        execution_class = CODEX_PILOT_DOCS_ONLY_KIND
    if (
        not isinstance(execution_class, str)
        or execution_class not in CODEX_PILOT_AUTHORIZATION_KINDS
    ):
        raise ValueError("handoff task execution_class is invalid")
    mandatory_boundaries = _reviewed_invocation_boundaries(
        execution_class=execution_class,
        declared_paths=declared_paths,
    )

    if execution_class == CODEX_PILOT_BOUNDED_PYTHON_KIND:
        return _render_compact_bounded_python_invocation_prompt(
            package=package,
            preflight_report=preflight_report,
            task=task,
            declared_paths=declared_paths,
            mandatory_boundaries=mandatory_boundaries,
        )

    return _render_full_reviewed_codex_invocation_prompt(
        package=package,
        preflight_report=preflight_report,
        task=task,
        declared_paths=declared_paths,
        mandatory_boundaries=mandatory_boundaries,
    )


def _render_full_reviewed_codex_invocation_prompt(
    *,
    package: dict[str, object],
    preflight_report: dict[str, object],
    task: dict[str, object],
    declared_paths: object,
    mandatory_boundaries: tuple[str, ...],
) -> str:
    """Preserve the established docs-only reviewed invocation verbatim."""

    external_checks = preflight_report["external_checks_required"]
    headings = package["required_pr_body_headings"]
    return "\n".join(
        [
            "# Supervised Codex Invocation Request Draft",
            "",
            "## 1. Supervised Pilot Identity",
            "This is a provider-neutral supervised invocation request draft.",
            "The request is unsent and does not authorize Codex invocation.",
            "",
            "## 2. Source Issue And Handoff",
            f"Source issue number: {preflight_report['source_issue_number']}",
            f"Handoff ID: {package['handoff_id']}",
            f"Task ID: {task['task_id']}",
            f"Task title: {task['title']}",
            "",
            "## 3. Repository And Base Branch",
            f"Repository: {preflight_report['repository']}",
            f"Base branch: {preflight_report['base_branch']}",
            "",
            "## 4. Expected PR Title",
            str(package["expected_pr_title"]),
            "",
            "## 5. Allowed Changed Files",
            *_prompt_bullets(declared_paths),
            "",
            "## 6. Original Reviewed Package Prompt",
            str(package["prompt"]),
            "",
            "## 7. Required Validation Commands",
            *_prompt_bullets(list(VALIDATION_COMMANDS)),
            "",
            "## 8. Required PR Body Headings",
            *_prompt_bullets(headings),
            "",
            "## 9. Mandatory Execution Boundaries",
            *mandatory_boundaries,
            "",
            "## 10. External Checks Not Claimed",
            *_prompt_bullets(external_checks),
        ]
    )


def _render_compact_bounded_python_invocation_prompt(
    *,
    package: dict[str, object],
    preflight_report: dict[str, object],
    task: dict[str, object],
    declared_paths: object,
    mandatory_boundaries: tuple[str, ...],
) -> str:
    """Render only reviewed facts and worker-relevant bounded-Python boundaries."""

    return "\n".join(
        [
            "# Compact Bounded-Python Supervised Invocation",
            "",
            "## Supervised Execution Identity",
            f"Execution class: {CODEX_PILOT_BOUNDED_PYTHON_KIND}",
            f"Source issue number: {preflight_report['source_issue_number']}",
            f"Handoff ID: {package['handoff_id']}",
            f"Task ID: {task['task_id']}",
            f"Task title: {task['title']}",
            f"Repository: {preflight_report['repository']}",
            f"Base branch: {preflight_report['base_branch']}",
            f"Expected PR title: {package['expected_pr_title']}",
            "",
            "## Exact Allowed Changed Files",
            *_prompt_bullets(declared_paths),
            "",
            "## Original Reviewed Package Prompt",
            str(package["prompt"]),
            "",
            "## Required Validation Commands",
            *_prompt_bullets(list(VALIDATION_COMMANDS)),
            "",
            "## Worker Execution Boundaries",
            *mandatory_boundaries,
        ]
    )


def _reviewed_invocation_boundaries(
    *,
    execution_class: str,
    declared_paths: object,
) -> tuple[str, ...]:
    if execution_class == CODEX_PILOT_DOCS_ONLY_KIND:
        return (
            "- one issue, one branch, one PR",
            "- modify only the declared documentation files",
            "- do not broaden scope",
            "- do not use private customer data",
            "- run and report every required validation",
            "- open one PR and stop",
            "- never approve or merge",
            (
                "- do not comment, label, dispatch workflows, automatically "
                "retry, schedule, queue, or continue in the background"
            ),
            (
                "- stop without mutation when any scope or identity binding "
                "is ambiguous"
            ),
        )
    if execution_class != CODEX_PILOT_BOUNDED_PYTHON_KIND:
        raise ValueError("handoff task execution_class is invalid")
    if (
        not isinstance(declared_paths, list)
        or not declared_paths
        or any(type(path) is not str or not path for path in declared_paths)
    ):
        raise ValueError("reviewed Python paths are invalid")
    return (
        "- one reviewed attempt only",
        "- edit only the exact reviewed Python files listed above",
        "- do not modify any extra path",
        "- do not broaden scope",
        "- do not use private customer data",
        "- the worker must not access the network or GitHub",
        "- the worker must not stage, commit, push, or open a pull request",
        "- run every required validation command listed above",
        "- do not approve or merge",
        (
            "- do not retry, create a replacement authorization, or resume "
            "in the background"
        ),
        "- stop within this supervised authority",
        (
            "- stop without mutation when any scope or identity binding "
            "is ambiguous"
        ),
        (
            "- Phoenix owns publication, final CI, architecture review, approval, "
            "merge, retry, replacement authorization, and background-resume "
            "decisions. The worker must not perform or claim those actions."
        ),
    )


def render_codex_worker_prompt(
    *,
    package: dict[str, object],
    allowed_paths: tuple[str, ...],
) -> str:
    """Render only deterministic, reviewed facts and worker edit authority."""

    task = package.get("task")
    if type(task) is not dict:
        raise ValueError("handoff task is invalid")
    task_id = _bounded_worker_prompt_text(task.get("task_id"), 512)
    title = _bounded_worker_prompt_text(task.get("title"), 512)
    objective = _bounded_worker_prompt_text(task.get("objective"), 2_000)
    facts = _bounded_worker_prompt_text(
        package.get("prompt"),
        MAX_WORKER_TASK_FACTS_CHARACTERS,
    )
    if not allowed_paths or any(
        type(path) is not str or not path for path in allowed_paths
    ):
        raise ValueError("worker writable paths are invalid")
    if any(command in facts for command in VALIDATION_COMMANDS):
        raise ValueError("worker facts contain Phoenix validation commands")
    prompt = "\n".join(
        [
            "# Supervised Codex Worker Edit",
            "",
            f"Task ID: {task_id}",
            f"Task title: {title}",
            f"Reviewed objective: {objective}",
            "",
            "## Reviewed task facts",
            facts,
            "",
            "## Authorized writable files",
            *_prompt_bullets(allowed_paths),
            "",
            "## Worker boundaries",
            "- Edit only the authorized writable files listed above.",
            "- Do not inspect or mutate unrelated repository state.",
            "- Do not access the network or GitHub.",
            "- Do not stage, commit, push, open a pull request, approve, or merge.",
            "- Stop after completing the authorized edit.",
        ]
    )
    if len(prompt) > MAX_WORKER_PROMPT_CHARACTERS:
        raise ValueError("worker prompt is too large")
    return prompt


def _bounded_worker_prompt_text(value: object, maximum: int) -> str:
    if type(value) is not str:
        raise ValueError("worker prompt text is invalid")
    text = value.strip()
    if not text or len(text) > maximum or "\r" in text:
        raise ValueError("worker prompt text is invalid")
    if any(ord(character) < 32 and character not in {"\n", "\t"} for character in text):
        raise ValueError("worker prompt text is invalid")
    return text


def _prompt_bullets(values: object) -> list[str]:
    if not isinstance(values, (list, tuple)):
        raise ValueError("prompt list is invalid")
    return [f"- {value}" for value in values]


def bounded_codex_pilot_run_result(
    category: str,
    *,
    status: str = "blocked",
) -> dict[str, object]:
    """Return the bounded public result shape without diagnostic payloads."""

    return {
        "schema_version": RUNNER_SCHEMA_VERSION,
        "status": status,
        "category": category,
        "attempt_id": None,
        "branch_identity": None,
        "pull_request_identity": None,
        "changed_paths": [],
        "validation_categories": [],
        "usage_category": "usage_unknown",
        "observed_usage_tokens": None,
        "input_tokens": None,
        "cached_input_tokens": None,
        "output_tokens": None,
        "reasoning_output_tokens": None,
        "authorized_budget_tokens": None,
        "usage_overage_tokens": None,
        "usage_ratio_basis_points": None,
        "timeout_category": "timeout_unknown",
        "cancellation_category": "cancellation_unknown",
    }


class SupervisedCodexPilotRunner:
    """One-run fail-closed orchestration for a reviewed authorization."""

    def __init__(
        self,
        *,
        system: CodexPilotSystem,
        claim_store_factory: ClaimStoreFactory = SQLiteCodexPilotInitialClaimStore,
        attempt_id_factory: AttemptIdFactory | None = None,
    ) -> None:
        self._system = system
        self._claim_store_factory = claim_store_factory
        self._attempt_id_factory = attempt_id_factory or _new_attempt_id

    def run(
        self,
        *,
        handoff: object,
        evidence: object,
        authorization: object,
        reviewed_prompt: object,
        claim_store_path: Path,
        static_preflight_passed: bool,
    ) -> dict[str, object]:
        context = _validated_run_context(
            handoff=handoff,
            evidence=evidence,
            authorization=authorization,
            reviewed_prompt=reviewed_prompt,
            static_preflight_passed=static_preflight_passed,
        )
        if context is None:
            return bounded_codex_pilot_run_result("preclaim_static_preflight_failed")
        handoff_data, authorization_data, worker_prompt, source_issue, headings = context

        try:
            gate = self._system.preclaim_repository_gate(authorization_data)
        except Exception:
            return bounded_codex_pilot_run_result("preclaim_gate_unavailable")
        if not gate.passed:
            return bounded_codex_pilot_run_result(gate.category)
        try:
            runtime_gate = self._system.runtime_gate()
        except Exception:
            return bounded_codex_pilot_run_result("runtime_gate_unavailable")
        if not runtime_gate.passed:
            return bounded_codex_pilot_run_result(runtime_gate.category)
        try:
            authentication_gate = self._system.authentication_gate()
        except Exception:
            return bounded_codex_pilot_run_result("codex_auth_preflight_failed")
        if not authentication_gate.passed:
            return bounded_codex_pilot_run_result(authentication_gate.category)
        try:
            capability = self._system.capability_probe(
                min(int(authorization_data["timeout_seconds"]), 180)
            )
        except Exception:
            return bounded_codex_pilot_run_result("capability_probe_unavailable")
        if not capability.passed:
            return bounded_codex_pilot_run_result(capability.category)

        try:
            claim_store = self._claim_store_factory(Path(claim_store_path))
        except Exception:
            return bounded_codex_pilot_run_result("claim_store_unavailable")
        attempt_id = self._attempt_id_factory()
        try:
            bundle = compose_codex_pilot_initial_claim_bundle(
                authorization_data,
                attempt_id,
            )
            preparation = prepare_codex_pilot_initial_claim_commit(
                bundle,
                authorization_data,
            )
            create_result = claim_store.create_initial_claim_commit(
                preparation,
                authorization_data,
            )
        except Exception:
            return bounded_codex_pilot_run_result("claim_store_unavailable")
        if not isinstance(create_result, dict):
            return bounded_codex_pilot_run_result("claim_store_unavailable")
        create_category = create_result.get("claim_store_create_category")
        if create_category != "created":
            return bounded_codex_pilot_run_result(f"claim_{create_category}")

        result = bounded_codex_pilot_run_result("claimed", status="running")
        result["attempt_id"] = attempt_id
        result["branch_identity"] = authorization_data["branch_name"]
        lifecycle = {"sequence": 0, "state": "claim_created"}

        try:
            worktree_result = self._system.create_worktree(authorization_data)
        except Exception:
            worktree_result = WorktreeResult(False, "worktree_creation_failed")
        if not worktree_result.passed or worktree_result.handle is None:
            return self._terminal_result(
                result,
                claim_store,
                attempt_id,
                authorization_data,
                lifecycle,
                result_category=worktree_result.category,
                result_status="failed",
                next_state="failed",
                usage_category="usage_unknown",
                recovery_category="operator_recovery",
            )
        worktree = worktree_result.handle

        if not self._append(
            claim_store,
            attempt_id,
            authorization_data,
            lifecycle,
            "invocation_starting",
        ):
            return self._terminal_result(
                result,
                claim_store,
                attempt_id,
                authorization_data,
                lifecycle,
                result_category="lifecycle_append_failed",
                result_status="failed",
                next_state="failed",
                usage_category="usage_unknown",
                recovery_category="storage_uncertain",
            )

        def _record_started() -> None:
            if not self._append(
                claim_store,
                attempt_id,
                authorization_data,
                lifecycle,
                "invocation_started",
            ):
                raise RuntimeError("lifecycle append failed")

        try:
            execution = self._system.invoke_codex(
                worktree,
                worker_prompt,
                int(authorization_data["timeout_seconds"]),
                _record_started,
            )
        except Exception:
            execution = CodexExecutionResult("failed", "runner_internal_failure")
        budget_ceiling = int(authorization_data["budget_ceiling"])
        usage_telemetry = _bounded_usage_telemetry(
            execution.usage_tokens,
            budget_ceiling,
        )
        result.update(usage_telemetry)
        result.update(_bounded_usage_component_telemetry(execution))
        observed_usage = usage_telemetry["observed_usage_tokens"]
        usage_category = _usage_category(
            observed_usage if type(observed_usage) is int else None,
            budget_ceiling,
        )
        result["usage_category"] = usage_category

        if execution.status == "timed_out":
            result["timeout_category"] = "timeout_reached"
            return self._terminal_result(
                result,
                claim_store,
                attempt_id,
                authorization_data,
                lifecycle,
                result_category=execution.category,
                result_status="timed_out",
                next_state="timed_out",
                usage_category=usage_category,
                timeout_category="timeout_reached",
            )
        if execution.status == "cancelled":
            result["cancellation_category"] = "operator_cancelled"
            return self._terminal_result(
                result,
                claim_store,
                attempt_id,
                authorization_data,
                lifecycle,
                result_category=execution.category,
                result_status="cancelled",
                next_state="cancelled",
                usage_category=usage_category,
                cancellation_category="operator_cancelled",
            )
        if execution.status != "succeeded":
            return self._terminal_result(
                result,
                claim_store,
                attempt_id,
                authorization_data,
                lifecycle,
                result_category=execution.category,
                result_status="failed",
                next_state="failed",
                usage_category=usage_category,
                recovery_category="runner_crash",
            )
        if usage_category == "budget_exceeded":
            return self._terminal_result(
                result,
                claim_store,
                attempt_id,
                authorization_data,
                lifecycle,
                result_category="budget_exceeded",
                result_status="failed",
                next_state="failed",
                usage_category=usage_category,
                recovery_category="operator_recovery",
            )

        allowed_paths = tuple(str(path) for path in authorization_data["allowed_paths"])
        try:
            diff_result = self._system.inspect_diff(worktree, allowed_paths)
        except Exception:
            diff_result = DiffGateResult(False, "diff_gate_unavailable")
        if not diff_result.passed:
            return self._terminal_result(
                result,
                claim_store,
                attempt_id,
                authorization_data,
                lifecycle,
                result_category=diff_result.category,
                result_status="failed",
                next_state="failed",
                usage_category=usage_category,
                recovery_category="operator_recovery",
            )
        result["changed_paths"] = list(diff_result.changed_paths)

        try:
            validation = self._system.run_validations(
                worktree,
                tuple(
                    str(command)
                    for command in authorization_data["validation_commands"]
                ),
            )
        except Exception:
            validation = ValidationGateResult(False, "validation_gate_unavailable")
        result["validation_categories"] = list(validation.command_categories)
        if not validation.passed:
            return self._terminal_result(
                result,
                claim_store,
                attempt_id,
                authorization_data,
                lifecycle,
                result_category=validation.category,
                result_status="failed",
                next_state="failed",
                usage_category=usage_category,
                recovery_category="operator_recovery",
            )

        try:
            post_validation_diff = self._system.inspect_diff(
                worktree,
                allowed_paths,
            )
        except Exception:
            post_validation_diff = DiffGateResult(False, "diff_gate_unavailable")
        if (
            not post_validation_diff.passed
            or post_validation_diff.changed_paths != diff_result.changed_paths
        ):
            return self._terminal_result(
                result,
                claim_store,
                attempt_id,
                authorization_data,
                lifecycle,
                result_category="post_validation_diff_changed",
                result_status="failed",
                next_state="failed",
                usage_category=usage_category,
                recovery_category="operator_recovery",
            )

        try:
            commit = self._system.commit_authorized_changes(
                worktree,
                diff_result.changed_paths,
                str(authorization_data["expected_pr_title"]),
            )
        except Exception:
            commit = GateResult(False, "commit_gate_unavailable")
        if not commit.passed:
            return self._terminal_result(
                result,
                claim_store,
                attempt_id,
                authorization_data,
                lifecycle,
                result_category=commit.category,
                result_status="failed",
                next_state="failed",
                usage_category=usage_category,
                recovery_category="operator_recovery",
            )

        try:
            prepublication = self._system.prepublication_gate(authorization_data)
        except Exception:
            prepublication = GateResult(False, "prepublication_gate_unavailable")
        if not prepublication.passed:
            return self._terminal_result(
                result,
                claim_store,
                attempt_id,
                authorization_data,
                lifecycle,
                result_category=prepublication.category,
                result_status="failed",
                next_state="failed",
                usage_category=usage_category,
                recovery_category="operator_recovery",
            )

        try:
            push = self._system.push_authorized_branch(worktree)
        except Exception:
            push = GateResult(False, "push_gate_unavailable")
        if not push.passed:
            return self._terminal_result(
                result,
                claim_store,
                attempt_id,
                authorization_data,
                lifecycle,
                result_category=push.category,
                result_status="failed",
                next_state="failed",
                usage_category=usage_category,
                recovery_category="operator_recovery",
            )

        try:
            publication = self._system.create_pull_request(
                worktree,
                authorization_data,
                source_issue,
                headings,
                diff_result.changed_paths,
                tuple(
                    str(command)
                    for command in authorization_data["validation_commands"]
                ),
            )
        except Exception:
            publication = PublicationResult(False, "publication_gate_unavailable")
        if not publication.passed or publication.pull_request_identity is None:
            return self._terminal_result(
                result,
                claim_store,
                attempt_id,
                authorization_data,
                lifecycle,
                result_category=publication.category,
                result_status="failed",
                next_state="failed",
                usage_category=usage_category,
                recovery_category="operator_recovery",
            )

        result["pull_request_identity"] = publication.pull_request_identity
        if not self._append(
            claim_store,
            attempt_id,
            authorization_data,
            lifecycle,
            "pr_opened_and_stopped",
            branch_identity=authorization_data["branch_name"],
            pull_request_identity=publication.pull_request_identity,
            usage_category=usage_category,
        ):
            return self._terminal_result(
                result,
                claim_store,
                attempt_id,
                authorization_data,
                lifecycle,
                result_category="publication_audit_storage_uncertain",
                result_status="failed",
                next_state="failed",
                usage_category=usage_category,
                recovery_category="storage_uncertain",
            )
        return _with_category(result, "pr_opened_and_stopped", status="success")

    @staticmethod
    def _append(
        store: LifecycleClaimStore,
        attempt_id: str,
        authorization: dict[str, object],
        lifecycle: dict[str, object],
        next_state: str,
        **context: object,
    ) -> bool:
        try:
            append = store.append_lifecycle_event(
                attempt_id,
                authorization,
                expected_event_sequence=lifecycle["sequence"],
                expected_lifecycle_state=lifecycle["state"],
                next_lifecycle_state=next_state,
                **context,
            )
        except Exception:
            return False
        if append.get("lifecycle_append_category") != "appended":
            return False
        lifecycle["sequence"] = append["event_sequence"]
        lifecycle["state"] = append["lifecycle_state"]
        return True

    def _terminal_result(
        self,
        result: dict[str, object],
        store: LifecycleClaimStore,
        attempt_id: str,
        authorization: dict[str, object],
        lifecycle: dict[str, object],
        *,
        result_category: str,
        result_status: str,
        next_state: str,
        usage_category: str,
        timeout_category: str | None = None,
        cancellation_category: str | None = None,
        recovery_category: str | None = None,
    ) -> dict[str, object]:
        """Publish a terminal result only after its durable event is confirmed."""
        persisted = self._terminalize(
            store,
            attempt_id,
            authorization,
            lifecycle,
            next_state=next_state,
            usage_category=usage_category,
            timeout_category=timeout_category,
            cancellation_category=cancellation_category,
            recovery_category=recovery_category,
        )
        if not persisted:
            return _with_category(
                result,
                "lifecycle_storage_uncertain",
                status="failed",
            )
        return _with_category(result, result_category, status=result_status)

    def _terminalize(
        self,
        store: LifecycleClaimStore,
        attempt_id: str,
        authorization: dict[str, object],
        lifecycle: dict[str, object],
        *,
        next_state: str,
        usage_category: str,
        timeout_category: str | None = None,
        cancellation_category: str | None = None,
        recovery_category: str | None = None,
    ) -> bool:
        context: dict[str, object] = {}
        if lifecycle["state"] == "invocation_started":
            context["usage_category"] = usage_category
        if timeout_category is not None:
            context["timeout_category"] = timeout_category
        if cancellation_category is not None:
            context["cancellation_category"] = cancellation_category
        if recovery_category is not None:
            context["recovery_category"] = recovery_category
        return self._append(
            store,
            attempt_id,
            authorization,
            lifecycle,
            next_state,
            **context,
        )


def _validated_run_context(
    *,
    handoff: object,
    evidence: object,
    authorization: object,
    reviewed_prompt: object,
    static_preflight_passed: bool,
) -> tuple[
    dict[str, object],
    dict[str, object],
    str,
    int,
    tuple[str, ...],
] | None:
    if static_preflight_passed is not True:
        return None
    if type(handoff) is not dict or type(evidence) is not dict:
        return None
    if type(authorization) is not dict or type(reviewed_prompt) is not str:
        return None
    authorization_validation = validate_codex_pilot_authorization_packet(authorization)
    if not authorization_validation["authorization_structural_valid"]:
        return None
    pilot_kind = authorization.get("pilot_kind")
    if pilot_kind not in CODEX_PILOT_AUTHORIZATION_KINDS:
        return None
    if handoff.get("repository") != REPOSITORY_IDENTITY:
        return None
    if handoff.get("base_branch") != BASE_BRANCH:
        return None
    if handoff.get("handoff_id") != authorization.get("handoff_id"):
        return None
    if handoff.get("expected_pr_title") != authorization.get("expected_pr_title"):
        return None
    task = handoff.get("task")
    if type(task) is not dict:
        return None
    allowed_resources = task.get("allowed_resources")
    verification_plan = task.get("verification_plan")
    permissions = task.get("permissions")
    source = task.get("source")
    if not all(
        type(value) is dict
        for value in [allowed_resources, verification_plan, permissions, source]
    ):
        return None
    if task.get("objective") != authorization.get("objective"):
        return None
    task_execution_class = task.get("execution_class")
    if task_execution_class is None and pilot_kind == CODEX_PILOT_DOCS_ONLY_KIND:
        task_execution_class = CODEX_PILOT_DOCS_ONLY_KIND
    if task_execution_class != pilot_kind:
        return None
    allowed_paths = allowed_resources.get("paths")
    if allowed_paths != authorization.get("allowed_paths"):
        return None
    if verification_plan.get("commands") != authorization.get("validation_commands"):
        return None
    if tuple(authorization.get("validation_commands", ())) != VALIDATION_COMMANDS:
        return None
    if any(permissions.get(field) is not False for field in ("execute", "network", "destructive")):
        return None
    if evidence.get("schema_version") != "codex-pilot-evidence.v1":
        return None
    if evidence.get("repository") != REPOSITORY_IDENTITY:
        return None
    if evidence.get("pilot_kind") != pilot_kind:
        return None
    if evidence.get("handoff_id") != authorization.get("handoff_id"):
        return None
    if evidence.get("pilot_ready") is not False:
        return None
    if evidence.get("invocation_authorized") is not False:
        return None
    controls = evidence.get("controls")
    if not isinstance(controls, list):
        return None
    control_map = {
        control.get("control_id"): control
        for control in controls
        if type(control) is dict
    }
    if set(control_map) != REQUIRED_EVIDENCE_CONTROLS:
        return None
    if any(control.get("status") != "verified" for control in control_map.values()):
        return None
    headings = handoff.get("required_pr_body_headings")
    if not isinstance(headings, list) or not all(type(item) is str for item in headings):
        return None
    if any(required not in headings for required in REQUIRED_PR_BODY_HEADINGS):
        return None
    issue_number = _source_issue_number(source.get("uri"))
    if issue_number is None:
        return None
    expected_reviewed_prompt = render_reviewed_codex_invocation_prompt(
        package=handoff,
        preflight_report={
            "source_issue_number": issue_number,
            "repository": handoff["repository"],
            "base_branch": handoff["base_branch"],
            "declared_changed_files": [
                str(path).replace("\\", "/") for path in allowed_paths
            ],
            "external_checks_required": list(INVOCATION_EXTERNAL_CHECKS_REQUIRED),
        },
    )
    if reviewed_prompt != expected_reviewed_prompt:
        return None
    try:
        worker_prompt = render_codex_worker_prompt(
            package=handoff,
            allowed_paths=tuple(str(path) for path in allowed_paths),
        )
    except ValueError:
        return None
    return (
        handoff,
        authorization,
        worker_prompt,
        issue_number,
        tuple(headings),
    )


def _source_issue_number(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(
        r"https://github\.com/Phoenix-AI-Platform/phoenix-office/issues/([1-9][0-9]*)",
        value,
    )
    return int(match.group(1)) if match is not None else None


def _bounded_usage_telemetry(
    observed: object,
    authorized: object,
) -> dict[str, int | None]:
    telemetry: dict[str, int | None] = {
        "observed_usage_tokens": None,
        "authorized_budget_tokens": None,
        "usage_overage_tokens": None,
        "usage_ratio_basis_points": None,
    }
    observed_tokens = _bounded_usage_token_count(observed)
    if (
        observed_tokens is None
        or type(authorized) is not int
        or authorized < 1
        or authorized > MAX_AUTHORIZED_BUDGET_TOKENS
    ):
        return telemetry
    overage = max(observed_tokens - authorized, 0)
    ratio_basis_points = (
        observed_tokens * USAGE_RATIO_BASIS_POINTS_SCALE // authorized
    )
    if ratio_basis_points > MAX_USAGE_RATIO_BASIS_POINTS:
        return telemetry
    telemetry.update(
        {
            "observed_usage_tokens": observed_tokens,
            "authorized_budget_tokens": authorized,
            "usage_overage_tokens": overage,
            "usage_ratio_basis_points": ratio_basis_points,
        }
    )
    return telemetry


def _bounded_usage_component_telemetry(
    execution: CodexExecutionResult,
) -> dict[str, int | None]:
    return {
        "input_tokens": _bounded_usage_token_count(execution.input_tokens),
        "cached_input_tokens": _bounded_usage_token_count(
            execution.cached_input_tokens
        ),
        "output_tokens": _bounded_usage_token_count(execution.output_tokens),
        "reasoning_output_tokens": _bounded_usage_token_count(
            execution.reasoning_output_tokens
        ),
    }


def _usage_category(observed: int | None, ceiling: int) -> str:
    if observed is None:
        return "usage_unknown"
    if observed > ceiling:
        return "budget_exceeded"
    return "within_budget"


def _with_category(
    result: dict[str, object],
    category: str,
    *,
    status: str,
) -> dict[str, object]:
    updated = dict(result)
    updated["category"] = category
    updated["status"] = status
    return updated


def _new_attempt_id() -> str:
    return f"pilot-attempt-{uuid.uuid4().hex}"


class _LifecycleStartFailure(RuntimeError):
    """Internal signal used only to terminate a just-launched Codex child."""


class _TransportEnvironmentError(ValueError):
    """Internal signal for a malformed approved transport variable."""


class SystemCodexPilotServices:
    """System Git, Codex, validation, and GitHub adapter."""

    def __init__(
        self,
        repository_path: Path,
        *,
        launch_spec_resolver: CodexLaunchSpecResolver | None = None,
        validation_runtime_resolver: ValidationRuntimeResolver | None = None,
        wsl_worker: WslCodexWorker | None = None,
    ) -> None:
        self._repository_path = Path(repository_path)
        self._wsl_worker = wsl_worker
        if self._wsl_worker is None and launch_spec_resolver is None and os.name == "nt":
            self._wsl_worker = WslCodexWorker(self._repository_path)
        self._launch_spec_resolver = launch_spec_resolver or _resolve_codex_launch_spec
        self._launch_spec_resolution_attempted = False
        self._codex_launch_spec: CodexLaunchSpec | None = None
        self._runtime_preflight_result: GateResult | None = None
        self._authentication_preflight_result: GateResult | None = None
        self._validation_runtime_resolver = (
            validation_runtime_resolver or _resolve_validation_runtime_spec
        )
        self._validation_runtime_resolution_attempted = False
        self._validation_runtime_spec: ValidationRuntimeSpec | None = None
        self._validation_runtime_preflight_result: GateResult | None = None

    @property
    def codex_launch_spec_kind(self) -> str | None:
        """Return only the bounded launch topology, never resolved paths."""
        if self._wsl_worker is not None:
            return self._wsl_worker.runtime_kind
        spec = self._codex_launch_spec
        return spec.kind if spec is not None else None

    @property
    def execution_backend_kind(self) -> str:
        """Return the bounded backend kind selected before authorization."""
        return "wsl2_linux" if self._wsl_worker is not None else "native_windows"

    @property
    def execution_backend_frozen(self) -> bool:
        """Report whether the selected backend has an immutable runtime identity."""
        if self._wsl_worker is not None:
            return self._wsl_worker.runtime_frozen
        return self._codex_launch_spec is not None

    @property
    def validation_runtime_frozen(self) -> bool:
        """Report qualification without exposing the canonical interpreter path."""
        return (
            self._validation_runtime_spec is not None
            and self._validation_runtime_preflight_result
            == GateResult(True, "validation_runtime_ready")
            and _validation_runtime_is_current(self._validation_runtime_spec)
        )

    def preclaim_repository_gate(self, authorization: dict[str, object]) -> GateResult:
        checks = [
            (["git", "branch", "--show-current"], "main_branch_gate_failed"),
            (["git", "rev-parse", "HEAD"], "base_sha_gate_failed"),
            (["git", "status", "--porcelain=v1"], "clean_repo_gate_failed"),
            (["git", "remote", "get-url", "origin"], "repository_identity_gate_failed"),
        ]
        outputs: list[str] = []
        for argv, category in checks:
            completed = self._run(argv, cwd=self._repository_path, timeout=30)
            if completed is None or completed.returncode != 0:
                return GateResult(False, category)
            outputs.append(completed.stdout.strip())
        branch, head, status_output, remote = outputs
        if branch != BASE_BRANCH:
            return GateResult(False, "main_branch_gate_failed")
        if head != authorization.get("base_commit_sha"):
            return GateResult(False, "base_sha_gate_failed")
        if status_output:
            return GateResult(False, "clean_repo_gate_failed")
        if _repository_identity_from_remote(remote) != REPOSITORY_IDENTITY:
            return GateResult(False, "repository_identity_gate_failed")
        path_gate = self._authorization_paths_gate(authorization)
        if not path_gate.passed:
            return path_gate
        fetched = self._run(
            [
                "git",
                "fetch",
                "--quiet",
                "origin",
                "+refs/heads/main:refs/remotes/origin/main",
            ],
            cwd=self._repository_path,
            timeout=120,
        )
        if fetched is None or fetched.returncode != 0:
            return GateResult(False, "synchronization_gate_failed")
        counts = self._run(
            [
                "git",
                "rev-list",
                "--left-right",
                "--count",
                "HEAD...refs/remotes/origin/main",
            ],
            cwd=self._repository_path,
            timeout=30,
        )
        status = self._run(
            ["git", "status", "--porcelain=v1"],
            cwd=self._repository_path,
            timeout=30,
        )
        if counts is None or counts.returncode != 0:
            return GateResult(False, "synchronization_gate_failed")
        if counts.stdout.split() != ["0", "0"]:
            return GateResult(False, "synchronization_gate_failed")
        if status is None or status.returncode != 0 or status.stdout.strip():
            return GateResult(False, "clean_repo_gate_failed")
        collision = self._collision_gate(authorization)
        if not collision.passed:
            return collision
        validation_runtime = self._validation_runtime_gate()
        if not validation_runtime.passed:
            return validation_runtime
        return collision

    def _authorization_paths_gate(
        self,
        authorization: dict[str, object],
    ) -> GateResult:
        pilot_kind = authorization.get("pilot_kind")
        paths = authorization.get("allowed_paths")
        if not is_safe_codex_pilot_allowed_paths(paths, pilot_kind):
            return GateResult(False, "authorized_path_policy_failed")
        if pilot_kind != CODEX_PILOT_BOUNDED_PYTHON_KIND:
            return GateResult(True, "authorized_paths_ready")
        assert isinstance(paths, list)
        repository = self._repository_path.resolve(strict=True)
        for path_text in paths:
            candidate = repository.joinpath(*PurePosixPath(path_text).parts)
            tracked = self._run(
                ["git", "ls-files", "--error-unmatch", "--", path_text],
                cwd=repository,
                timeout=30,
            )
            try:
                details = candidate.lstat()
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(repository)
            except (OSError, RuntimeError, ValueError):
                return GateResult(False, "authorized_path_policy_failed")
            reparse_attribute = getattr(
                stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
            )
            file_attributes = getattr(details, "st_file_attributes", 0)
            if (
                tracked is None
                or tracked.returncode != 0
                or not stat.S_ISREG(details.st_mode)
                or candidate.is_symlink()
                or bool(file_attributes & reparse_attribute)
            ):
                return GateResult(False, "authorized_path_policy_failed")
        return GateResult(True, "authorized_paths_ready")

    def _validation_runtime_gate(self) -> GateResult:
        if self._validation_runtime_preflight_result is not None:
            if (
                self._validation_runtime_preflight_result.passed
                and self._validation_runtime_spec is not None
                and not _validation_runtime_is_current(self._validation_runtime_spec)
            ):
                self._validation_runtime_preflight_result = GateResult(
                    False,
                    "validation_runtime_changed",
                )
            return self._validation_runtime_preflight_result
        if not self._validation_runtime_resolution_attempted:
            self._validation_runtime_resolution_attempted = True
            try:
                self._validation_runtime_spec = self._validation_runtime_resolver(
                    self._repository_path
                )
            except Exception:
                self._validation_runtime_spec = None
        spec = self._validation_runtime_spec
        if spec is None:
            result = GateResult(False, "validation_runtime_unavailable")
            self._validation_runtime_preflight_result = result
            return result
        environment = _validation_environment()
        for module in ("pytest", "ruff"):
            if not _validation_runtime_is_current(spec):
                result = GateResult(False, "validation_runtime_changed")
                self._validation_runtime_preflight_result = result
                return result
            try:
                module_environment = dict(environment)
                if module == "pytest":
                    module_environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
                completed = subprocess.run(
                    [str(spec.python_identity.path), "-m", module, "--version"],
                    cwd=self._repository_path,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    shell=False,
                    timeout=VALIDATION_RUNTIME_PREFLIGHT_TIMEOUT_SECONDS,
                    env=module_environment,
                )
            except (OSError, subprocess.TimeoutExpired):
                completed = None
            if completed is None or completed.returncode != 0:
                result = GateResult(False, "validation_runtime_unavailable")
                self._validation_runtime_preflight_result = result
                return result
        if (
            not _validation_runtime_is_current(spec)
            or not _validation_tool_identity_is_current(
                spec,
                spec.pytest_identity,
                cwd=self._repository_path,
            )
            or not _validation_tool_identity_is_current(
                spec,
                spec.ruff_identity,
                cwd=self._repository_path,
            )
        ):
            result = GateResult(False, "validation_runtime_changed")
        else:
            result = GateResult(True, "validation_runtime_ready")
        self._validation_runtime_preflight_result = result
        return result

    def runtime_gate(self) -> GateResult:
        if self._wsl_worker is not None:
            result = self._wsl_worker.runtime_gate()
            return GateResult(result.passed, result.category)
        if self._runtime_preflight_result is not None:
            return self._runtime_preflight_result
        if os.name not in {"nt", "posix"}:
            result = GateResult(False, "process_control_unavailable")
            self._runtime_preflight_result = result
            return result
        spec = self._resolved_codex_launch_spec()
        if spec is None:
            result = GateResult(False, "codex_launch_spec_unavailable")
            self._runtime_preflight_result = result
            return result
        result = self._version_preflight(spec)
        self._runtime_preflight_result = result
        return result

    def _resolved_codex_launch_spec(self) -> CodexLaunchSpec | None:
        if not self._launch_spec_resolution_attempted:
            self._launch_spec_resolution_attempted = True
            try:
                self._codex_launch_spec = self._launch_spec_resolver()
            except Exception:
                self._codex_launch_spec = None
        return self._codex_launch_spec

    def _version_preflight(self, spec: CodexLaunchSpec) -> GateResult:
        return _codex_version_preflight(spec, cwd=self._repository_path)

    def _authentication_preflight(self, spec: CodexLaunchSpec) -> GateResult:
        return _codex_authentication_preflight(spec, cwd=self._repository_path)

    def authentication_gate(self) -> GateResult:
        if self._wsl_worker is not None:
            result = self._wsl_worker.authentication_gate()
            return GateResult(result.passed, result.category)
        if self._authentication_preflight_result is not None:
            return self._authentication_preflight_result
        runtime = self.runtime_gate()
        if not runtime.passed:
            self._authentication_preflight_result = runtime
            return runtime
        spec = self._codex_launch_spec
        if spec is None:
            result = GateResult(False, "codex_launch_spec_unavailable")
        else:
            result = self._authentication_preflight(spec)
        self._authentication_preflight_result = result
        return result

    def capability_probe(self, timeout_seconds: int) -> CapabilityProbeResult:
        if self._wsl_worker is not None:
            result = self._wsl_worker.capability_probe(timeout_seconds)
            return CapabilityProbeResult(result.passed, result.category)
        authentication = self.authentication_gate()
        if not authentication.passed:
            return CapabilityProbeResult(False, authentication.category)
        spec = self._codex_launch_spec
        if spec is None:
            return CapabilityProbeResult(False, "codex_launch_spec_unavailable")
        try:
            return self._capability_probe(timeout_seconds, spec)
        except Exception:
            return CapabilityProbeResult(False, "capability_probe_unavailable")

    def _capability_probe(
        self,
        timeout_seconds: int,
        launch_spec: CodexLaunchSpec,
    ) -> CapabilityProbeResult:
        with tempfile.TemporaryDirectory(prefix="phoenix-codex-capability-") as temporary:
            workspace = Path(temporary)
            setup_commands = [
                ["git", "init", "--quiet"],
                ["git", "config", "user.name", "Phoenix Capability Probe"],
                ["git", "config", "user.email", "probe@phoenix.invalid"],
            ]
            for argv in setup_commands:
                completed = self._run(argv, cwd=workspace, timeout=30)
                if completed is None or completed.returncode != 0:
                    return CapabilityProbeResult(False, "capability_probe_setup_failed")
            (workspace / "probe-readme.md").write_text(
                "Synthetic Phoenix Codex workspace-write probe.\n",
                encoding="utf-8",
            )
            setup_commit_commands = (
                ["git", "add", "--", "probe-readme.md"],
                [
                    "git",
                    "-c",
                    f"core.hooksPath={_git_null_device()}",
                    "-c",
                    "commit.gpgsign=false",
                    "commit",
                    "-m",
                    "probe",
                ],
            )
            for argv in setup_commit_commands:
                completed = self._run(list(argv), cwd=workspace, timeout=30)
                if completed is None or completed.returncode != 0:
                    return CapabilityProbeResult(False, "capability_probe_setup_failed")
            prompt = (
                f"Create exactly one file named {CAPABILITY_MARKER_NAME} in the current "
                "repository. Its exact UTF-8 content must be "
                f"{CAPABILITY_MARKER_CONTENT.strip()!r} followed by one newline. "
                "Do not modify any other file and do not run network commands."
            )
            execution = self._run_codex_process(
                workspace=workspace,
                prompt=prompt,
                timeout_seconds=timeout_seconds,
                on_started=lambda: None,
                launch_spec=launch_spec,
            )
            if execution.status == "timed_out":
                return CapabilityProbeResult(False, "capability_probe_timed_out")
            if execution.status == "cancelled":
                return CapabilityProbeResult(False, "capability_probe_cancelled")
            if execution.status != "succeeded":
                return CapabilityProbeResult(False, execution.category)
            marker = workspace / CAPABILITY_MARKER_NAME
            try:
                marker_stat = marker.lstat()
                content = marker.read_text(encoding="utf-8")
            except (FileNotFoundError, OSError, UnicodeError):
                return CapabilityProbeResult(False, "workspace_write_capability_unproved")
            if not stat.S_ISREG(marker_stat.st_mode) or marker.is_symlink():
                return CapabilityProbeResult(False, "workspace_write_capability_unproved")
            if content != CAPABILITY_MARKER_CONTENT:
                return CapabilityProbeResult(False, "workspace_write_capability_unproved")
            status = self._run(
                ["git", "status", "--porcelain=v1", "--untracked-files=all"],
                cwd=workspace,
                timeout=30,
            )
            if status is None or status.returncode != 0:
                return CapabilityProbeResult(False, "workspace_write_capability_unproved")
            if status.stdout.strip() != f"?? {CAPABILITY_MARKER_NAME}":
                return CapabilityProbeResult(False, "workspace_write_capability_unproved")
            return CapabilityProbeResult(True, "workspace_write_capability_proved")

    def create_worktree(self, authorization: dict[str, object]) -> WorktreeResult:
        try:
            parent = Path(tempfile.mkdtemp(prefix="phoenix-codex-task-"))
        except OSError:
            return WorktreeResult(False, "worktree_creation_failed")
        worktree_path = parent / "worktree"
        branch = str(authorization["branch_name"])
        base = str(authorization["base_commit_sha"])
        completed = self._run(
            [
                "git",
                "-c",
                f"core.hooksPath={_git_null_device()}",
                "worktree",
                "add",
                "-b",
                branch,
                str(worktree_path),
                base,
            ],
            cwd=self._repository_path,
            timeout=120,
        )
        if completed is None or completed.returncode != 0:
            return WorktreeResult(False, "worktree_creation_failed")
        try:
            control_file = worktree_path / ".git"
            control_stat = control_file.lstat()
            control_bytes = control_file.read_bytes()
        except OSError:
            return WorktreeResult(False, "worktree_control_invalid")
        if not stat.S_ISREG(control_stat.st_mode) or control_file.is_symlink():
            return WorktreeResult(False, "worktree_control_invalid")
        control_state = self._git_control_state(worktree_path)
        if control_state is None:
            return WorktreeResult(False, "worktree_control_invalid")
        git_refs, git_worktree_state, local_git_config = control_state
        return WorktreeResult(
            True,
            "worktree_created",
            WorktreeHandle(
                worktree_path,
                branch,
                base,
                control_bytes,
                git_refs,
                git_worktree_state,
                local_git_config,
                tuple(str(path) for path in authorization["allowed_paths"]),
                str(authorization["pilot_kind"]),
            ),
        )

    def invoke_codex(
        self,
        worktree: WorktreeHandle,
        prompt: str,
        timeout_seconds: int,
        on_started: Callable[[], None],
    ) -> CodexExecutionResult:
        if self._wsl_worker is not None:
            result = self._wsl_worker.invoke_codex(
                windows_worktree=worktree.path,
                base_commit_sha=worktree.base_commit_sha,
                allowed_paths=worktree.allowed_paths,
                pilot_kind=worktree.pilot_kind,
                prompt=prompt,
                timeout_seconds=timeout_seconds,
                on_started=on_started,
            )
            return CodexExecutionResult(
                status=result.status,
                category=result.category,
                usage_tokens=result.usage_tokens,
                input_tokens=result.input_tokens,
                cached_input_tokens=result.cached_input_tokens,
                output_tokens=result.output_tokens,
                reasoning_output_tokens=result.reasoning_output_tokens,
            )
        runtime = self.runtime_gate()
        if not runtime.passed:
            return CodexExecutionResult("failed", runtime.category)
        spec = self._codex_launch_spec
        if spec is None:
            return CodexExecutionResult("failed", "codex_launch_spec_unavailable")
        return self._run_codex_process(
            workspace=worktree.path,
            prompt=prompt,
            timeout_seconds=timeout_seconds,
            on_started=on_started,
            launch_spec=spec,
        )

    def inspect_diff(
        self,
        worktree: WorktreeHandle,
        allowed_paths: tuple[str, ...],
    ) -> DiffGateResult:
        head = self._run(["git", "rev-parse", "HEAD"], cwd=worktree.path, timeout=30)
        branch = self._run(
            ["git", "branch", "--show-current"], cwd=worktree.path, timeout=30
        )
        staged = self._run(
            ["git", "diff", "--cached", "--quiet"], cwd=worktree.path, timeout=30
        )
        if head is None or branch is None or staged is None:
            return DiffGateResult(False, "git_state_unavailable")
        if head.returncode != 0 or head.stdout.strip() != worktree.base_commit_sha:
            return DiffGateResult(False, "git_head_changed")
        if branch.returncode != 0 or branch.stdout.strip() != worktree.branch_name:
            return DiffGateResult(False, "authorized_branch_changed")
        if staged.returncode != 0:
            return DiffGateResult(False, "git_control_manipulation")
        control_state = self._git_control_state(worktree.path)
        if control_state is None or control_state != (
            worktree.git_refs,
            worktree.git_worktree_state,
            worktree.local_git_config,
        ):
            return DiffGateResult(False, "git_control_manipulation")
        control_file = worktree.path / ".git"
        try:
            if control_file.lstat() and control_file.read_bytes() != worktree.git_control_bytes:
                return DiffGateResult(False, "git_control_manipulation")
        except OSError:
            return DiffGateResult(False, "git_control_manipulation")

        status = self._run(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=worktree.path,
            timeout=30,
        )
        if status is None or status.returncode != 0:
            return DiffGateResult(False, "git_state_unavailable")
        records = [record for record in status.stdout.split("\0") if record]
        changed_paths: list[str] = []
        for record in records:
            if len(record) < 4 or record[2] != " ":
                return DiffGateResult(False, "git_status_invalid")
            status_code = record[:2]
            if any(marker in status_code for marker in "RCD"):
                return DiffGateResult(False, "unsupported_path_change")
            changed_paths.append(record[3:].replace("\\", "/"))
        if not changed_paths:
            return DiffGateResult(False, "no_authorized_changes")
        if len(set(changed_paths)) != len(changed_paths):
            return DiffGateResult(False, "git_status_invalid")

        allowed = set(allowed_paths)
        if not is_safe_codex_pilot_allowed_paths(
            list(allowed_paths), worktree.pilot_kind
        ):
            return DiffGateResult(False, "unsafe_changed_path")
        for path_text in changed_paths:
            if path_text not in allowed:
                return DiffGateResult(False, "unauthorized_path_changed")
            path = worktree.path.joinpath(*PurePosixPath(path_text).parts)
            try:
                path_stat = path.lstat()
                resolved = path.resolve(strict=True)
                resolved.relative_to(worktree.path.resolve(strict=True))
            except (FileNotFoundError, OSError, RuntimeError, ValueError):
                return DiffGateResult(False, "unsafe_changed_path")
            if not stat.S_ISREG(path_stat.st_mode) or path.is_symlink():
                return DiffGateResult(False, "symlink_or_nonfile_change")
            mode = self._run(
                ["git", "ls-files", "-s", "--", path_text],
                cwd=worktree.path,
                timeout=30,
            )
            if mode is None or mode.returncode != 0:
                return DiffGateResult(False, "git_state_unavailable")
            if mode.stdout.startswith(("120000 ", "160000 ")):
                return DiffGateResult(False, "symlink_or_submodule_change")
            try:
                payload = path.read_bytes()
                text = payload.decode("utf-8")
            except (OSError, UnicodeError):
                return DiffGateResult(False, "binary_or_unreadable_change")
            if len(payload) > MAX_MARKDOWN_BYTES or b"\0" in payload:
                return DiffGateResult(False, "binary_or_unreadable_change")
            if any(pattern.search(text) for pattern in SENSITIVE_PATTERNS):
                return DiffGateResult(False, "sensitive_content_detected")
            numstat = self._run(
                ["git", "diff", "--numstat", "HEAD", "--", path_text],
                cwd=worktree.path,
                timeout=30,
            )
            if numstat is None or numstat.returncode != 0:
                return DiffGateResult(False, "git_state_unavailable")
            if numstat.stdout.startswith("-\t-"):
                return DiffGateResult(False, "binary_or_unreadable_change")
        return DiffGateResult(True, "diff_allowed", tuple(sorted(changed_paths)))

    def run_validations(
        self,
        worktree: WorktreeHandle,
        commands: tuple[str, ...],
    ) -> ValidationGateResult:
        if commands != VALIDATION_COMMANDS:
            return ValidationGateResult(False, "validation_command_mismatch")
        spec = self._validation_runtime_spec
        if spec is None or self._validation_runtime_preflight_result != GateResult(
            True,
            "validation_runtime_ready",
        ):
            return ValidationGateResult(False, "validation_runtime_unavailable")
        try:
            temporary = tempfile.TemporaryDirectory(
                prefix=VALIDATION_PYTEST_BASETEMP_PREFIX
            )
        except (OSError, RuntimeError):
            return ValidationGateResult(
                False,
                "validation_temp_unavailable",
                ("temp_unavailable",),
            )
        raw_basetemp: Path | None = None
        pytest_basetemp: Path | None = None
        try:
            try:
                raw_basetemp = Path(temporary.name)
            except (AttributeError, TypeError, ValueError):
                result = ValidationGateResult(
                    False,
                    "validation_temp_unavailable",
                    ("temp_unavailable",),
                )
            else:
                pytest_basetemp = _resolve_validation_basetemp(
                    raw_basetemp,
                    repository_path=self._repository_path,
                    worktree_path=worktree.path,
                    venv_root=spec.venv_root,
                )
                if pytest_basetemp is None:
                    result = ValidationGateResult(
                        False,
                        "validation_temp_unsafe",
                        ("temp_unsafe",),
                    )
                else:
                    result = self._run_validations_with_basetemp(
                        worktree,
                        commands,
                        spec,
                        pytest_basetemp,
                    )
        finally:
            try:
                temporary.cleanup()
                cleanup_succeeded = True
            except (OSError, RuntimeError):
                cleanup_succeeded = False
        cleanup_path = pytest_basetemp or raw_basetemp
        try:
            cleanup_verified = (
                cleanup_succeeded
                and cleanup_path is not None
                and not cleanup_path.exists()
            )
        except OSError:
            cleanup_verified = False
        if not cleanup_verified:
            return ValidationGateResult(
                False,
                "validation_temp_cleanup_failed",
                ("temp_cleanup_failed",),
            )
        return result

    def _run_validations_with_basetemp(
        self,
        worktree: WorktreeHandle,
        commands: tuple[str, ...],
        spec: ValidationRuntimeSpec,
        pytest_basetemp: Path,
    ) -> ValidationGateResult:
        categories: list[str] = []
        for command in commands:
            if command != VALIDATION_COMMANDS[2]:
                tool_identity = (
                    spec.pytest_identity
                    if command == VALIDATION_COMMANDS[0]
                    else spec.ruff_identity
                )
                if not _validation_runtime_is_current(
                    spec
                ) or not _validation_tool_identity_is_current(
                    spec,
                    tool_identity,
                    cwd=worktree.path,
                ):
                    categories.append("runtime_changed")
                    return ValidationGateResult(
                        False,
                        "validation_runtime_changed",
                        tuple(categories),
                    )
            argv, environment = _validation_command(
                command,
                spec,
                pytest_basetemp=pytest_basetemp,
            )
            try:
                completed = subprocess.run(
                    argv,
                    cwd=worktree.path,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    shell=False,
                    timeout=VALIDATION_TIMEOUT_SECONDS,
                    env=environment,
                )
            except subprocess.TimeoutExpired:
                categories.append("timed_out")
                return ValidationGateResult(
                    False,
                    "validation_timed_out",
                    tuple(categories),
                )
            except OSError:
                categories.append("launch_failed")
                return ValidationGateResult(
                    False,
                    "validation_launch_failed",
                    tuple(categories),
                )
            if completed.returncode != 0:
                categories.append("failed")
                return ValidationGateResult(
                    False,
                    "validation_failed",
                    tuple(categories),
                )
            categories.append("passed")
        return ValidationGateResult(True, "validation_passed", tuple(categories))

    def commit_authorized_changes(
        self,
        worktree: WorktreeHandle,
        changed_paths: tuple[str, ...],
        commit_message: str,
    ) -> GateResult:
        add = self._run(
            ["git", "add", "--", *changed_paths],
            cwd=worktree.path,
            timeout=60,
        )
        if add is None or add.returncode != 0:
            return GateResult(False, "commit_stage_failed")
        staged = self._run(
            ["git", "diff", "--cached", "--name-only", "-z"],
            cwd=worktree.path,
            timeout=30,
        )
        if staged is None or staged.returncode != 0:
            return GateResult(False, "commit_stage_verification_failed")
        staged_paths = tuple(sorted(path for path in staged.stdout.split("\0") if path))
        if staged_paths != tuple(sorted(changed_paths)):
            return GateResult(False, "commit_stage_scope_mismatch")
        commit = self._run(
            [
                "git",
                "-c",
                f"core.hooksPath={_git_null_device()}",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "user.name=Phoenix",
                "-c",
                "user.email=phoenix@invalid.local",
                "commit",
                "-m",
                commit_message,
            ],
            cwd=worktree.path,
            timeout=120,
        )
        if commit is None or commit.returncode != 0:
            return GateResult(False, "commit_failed")
        parent = self._run(
            ["git", "rev-parse", "HEAD^"],
            cwd=worktree.path,
            timeout=30,
        )
        committed = self._run(
            [
                "git",
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "--no-renames",
                "-r",
                "-z",
                "HEAD",
            ],
            cwd=worktree.path,
            timeout=30,
        )
        branch = self._run(
            ["git", "branch", "--show-current"],
            cwd=worktree.path,
            timeout=30,
        )
        if parent is None or parent.returncode != 0:
            return GateResult(False, "commit_verification_failed")
        if parent.stdout.strip() != worktree.base_commit_sha:
            return GateResult(False, "commit_parent_mismatch")
        if committed is None or committed.returncode != 0:
            return GateResult(False, "commit_verification_failed")
        committed_paths = tuple(
            sorted(path for path in committed.stdout.split("\0") if path)
        )
        if committed_paths != tuple(sorted(changed_paths)):
            return GateResult(False, "commit_scope_mismatch")
        if branch is None or branch.returncode != 0:
            return GateResult(False, "commit_verification_failed")
        if branch.stdout.strip() != worktree.branch_name:
            return GateResult(False, "authorized_branch_changed")
        status = self._run(
            ["git", "status", "--porcelain=v1"], cwd=worktree.path, timeout=30
        )
        if status is None or status.returncode != 0 or status.stdout.strip():
            return GateResult(False, "post_commit_worktree_not_clean")
        return GateResult(True, "committed")

    def prepublication_gate(
        self,
        authorization: dict[str, object],
    ) -> GateResult:
        return self._remote_collision_gate(authorization)

    def push_authorized_branch(self, worktree: WorktreeHandle) -> GateResult:
        pushed = self._run(
            [
                "git",
                "-c",
                f"core.hooksPath={_git_null_device()}",
                "push",
                "--set-upstream",
                f"--force-with-lease=refs/heads/{worktree.branch_name}:",
                "origin",
                f"HEAD:refs/heads/{worktree.branch_name}",
            ],
            cwd=worktree.path,
            timeout=300,
        )
        if pushed is None or pushed.returncode != 0:
            return GateResult(False, "push_failed")
        head = self._run(
            ["git", "rev-parse", "HEAD"],
            cwd=worktree.path,
            timeout=30,
        )
        remote = self._run(
            [
                "git",
                "ls-remote",
                "--heads",
                "origin",
                f"refs/heads/{worktree.branch_name}",
            ],
            cwd=worktree.path,
            timeout=60,
        )
        if head is None or head.returncode != 0 or remote is None:
            return GateResult(False, "push_verification_failed")
        if remote.returncode != 0:
            return GateResult(False, "push_verification_failed")
        remote_fields = remote.stdout.split()
        if len(remote_fields) != 2 or remote_fields[0] != head.stdout.strip():
            return GateResult(False, "push_verification_failed")
        if remote_fields[1] != f"refs/heads/{worktree.branch_name}":
            return GateResult(False, "push_verification_failed")
        return GateResult(True, "pushed")

    def create_pull_request(
        self,
        worktree: WorktreeHandle,
        authorization: dict[str, object],
        source_issue_number: int,
        required_headings: tuple[str, ...],
        changed_paths: tuple[str, ...],
        validation_commands: tuple[str, ...],
    ) -> PublicationResult:
        body = _pull_request_body(
            source_issue_number=source_issue_number,
            required_headings=required_headings,
            changed_paths=changed_paths,
            validation_commands=validation_commands,
            pilot_kind=str(authorization["pilot_kind"]),
        )
        created = self._run(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                REPOSITORY_IDENTITY,
                "--base",
                BASE_BRANCH,
                "--head",
                worktree.branch_name,
                "--title",
                str(authorization["expected_pr_title"]),
                "--body",
                body,
                "--draft",
            ],
            cwd=worktree.path,
            timeout=300,
        )
        if created is None or created.returncode != 0:
            return PublicationResult(False, "pull_request_create_failed")
        match = re.search(r"/pull/([1-9][0-9]*)\s*$", created.stdout.strip())
        if match is None:
            return PublicationResult(False, "pull_request_identity_unavailable")
        number = int(match.group(1))
        verified = self._run(
            [
                "gh",
                "pr",
                "view",
                str(number),
                "--repo",
                REPOSITORY_IDENTITY,
                "--json",
                "number,headRefName,baseRefName,title,isDraft,state",
            ],
            cwd=worktree.path,
            timeout=60,
        )
        if verified is None or verified.returncode != 0:
            return PublicationResult(False, "pull_request_verification_failed")
        try:
            pull_request = json.loads(verified.stdout)
        except json.JSONDecodeError:
            return PublicationResult(False, "pull_request_verification_failed")
        expected = {
            "number": number,
            "headRefName": worktree.branch_name,
            "baseRefName": BASE_BRANCH,
            "title": authorization["expected_pr_title"],
            "isDraft": True,
            "state": "OPEN",
        }
        if pull_request != expected:
            return PublicationResult(False, "pull_request_verification_failed")
        return PublicationResult(True, "pull_request_created", f"pr-{number}")

    def _collision_gate(self, authorization: dict[str, object]) -> GateResult:
        branch = str(authorization["branch_name"])
        local = self._run(
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
            cwd=self._repository_path,
            timeout=30,
        )
        if local is None or local.returncode not in {0, 1}:
            return GateResult(False, "local_branch_collision_gate_failed")
        if local.returncode == 0:
            return GateResult(False, "local_branch_collision")
        return self._remote_collision_gate(authorization)

    def _remote_collision_gate(
        self,
        authorization: dict[str, object],
    ) -> GateResult:
        branch = str(authorization["branch_name"])
        remote = self._run(
            [
                "git",
                "ls-remote",
                "--exit-code",
                "--heads",
                "origin",
                f"refs/heads/{branch}",
            ],
            cwd=self._repository_path,
            timeout=60,
        )
        if remote is None or remote.returncode not in {0, 2}:
            return GateResult(False, "remote_branch_collision_gate_failed")
        if remote.returncode == 0:
            return GateResult(False, "remote_branch_collision")
        pull_requests = self._run(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                REPOSITORY_IDENTITY,
                "--head",
                branch,
                "--state",
                "open",
                "--limit",
                "2",
                "--json",
                "number",
            ],
            cwd=self._repository_path,
            timeout=60,
        )
        if pull_requests is None or pull_requests.returncode != 0:
            return GateResult(False, "duplicate_pr_gate_failed")
        try:
            existing = json.loads(pull_requests.stdout)
        except json.JSONDecodeError:
            return GateResult(False, "duplicate_pr_gate_failed")
        if not isinstance(existing, list):
            return GateResult(False, "duplicate_pr_gate_failed")
        if existing:
            return GateResult(False, "duplicate_active_pr")
        return GateResult(True, "collision_gates_passed")

    def _git_control_state(
        self,
        worktree_path: Path,
    ) -> tuple[tuple[str, ...], str, str] | None:
        commands = (
            [
                "git",
                "for-each-ref",
                "--format=%(refname) %(objectname)",
                "refs",
            ],
            ["git", "worktree", "list", "--porcelain"],
            ["git", "config", "--local", "--null", "--list"],
        )
        outputs: list[str] = []
        for argv in commands:
            completed = self._run(argv, cwd=worktree_path, timeout=30)
            if completed is None or completed.returncode != 0:
                return None
            outputs.append(completed.stdout)
        refs = tuple(sorted(line for line in outputs[0].splitlines() if line))
        return refs, outputs[1], outputs[2]

    def _run_codex_process(
        self,
        *,
        workspace: Path,
        prompt: str,
        timeout_seconds: int,
        on_started: Callable[[], None],
        launch_spec: CodexLaunchSpec,
    ) -> CodexExecutionResult:
        if not _codex_launch_spec_is_current(launch_spec):
            return CodexExecutionResult("failed", "codex_launch_spec_changed")
        argv = _codex_exec_argv(launch_spec, workspace)
        popen_kwargs: dict[str, object] = {
            "cwd": workspace,
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "shell": False,
            "env": _codex_worker_environment(),
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True
        try:
            process = subprocess.Popen(argv, **popen_kwargs)
        except (OSError, ValueError):
            return CodexExecutionResult("failed", "codex_launch_failed")
        try:
            on_started()
        except Exception:
            terminated = _terminate_process_tree(process)
            category = (
                "invocation_start_audit_failed"
                if terminated
                else "process_tree_termination_uncertain"
            )
            return CodexExecutionResult("failed", category)
        if process.stdin is None or process.stdout is None or process.stderr is None:
            terminated = _terminate_process_tree(process)
            category = (
                "codex_pipe_unavailable"
                if terminated
                else "process_tree_termination_uncertain"
            )
            return CodexExecutionResult("failed", category)
        with ThreadPoolExecutor(max_workers=2) as executor:
            reader = executor.submit(_consume_codex_jsonl_stream, process.stdout)
            diagnostic_reader = executor.submit(
                _consume_codex_diagnostic_stream,
                process.stderr,
            )
            try:
                process.stdin.write(prompt)
                process.stdin.close()
                process.wait(timeout=timeout_seconds)
                parsed = reader.result(timeout=10)
                diagnostic_category = diagnostic_reader.result(timeout=10)
            except subprocess.TimeoutExpired:
                if _terminate_process_tree(process):
                    return CodexExecutionResult("timed_out", "codex_timed_out")
                return CodexExecutionResult(
                    "failed",
                    "process_tree_termination_uncertain",
                )
            except KeyboardInterrupt:
                if _terminate_process_tree(process):
                    return CodexExecutionResult("cancelled", "codex_cancelled")
                return CodexExecutionResult(
                    "failed",
                    "process_tree_termination_uncertain",
                )
            except (BrokenPipeError, OSError, FutureTimeoutError):
                terminated = _terminate_process_tree(process)
                category = (
                    "codex_stream_failed"
                    if terminated
                    else "process_tree_termination_uncertain"
                )
                return CodexExecutionResult("failed", category)
        if process.returncode != 0:
            return _codex_execution_result_from_parsed(
                "failed",
                _codex_failure_category(
                    parsed["failure_category"],
                    diagnostic_category,
                    fallback="codex_nonzero_exit",
                ),
                parsed,
            )
        if parsed["fatal"] or not parsed["turn_completed"]:
            return _codex_execution_result_from_parsed(
                "failed",
                _codex_failure_category(
                    parsed["failure_category"],
                    diagnostic_category,
                    fallback="codex_structured_failure",
                ),
                parsed,
            )
        return _codex_execution_result_from_parsed(
            "succeeded",
            "codex_completed",
            parsed,
        )

    @staticmethod
    def _run(
        argv: list[str],
        *,
        cwd: Path,
        timeout: int,
    ) -> subprocess.CompletedProcess[str] | None:
        try:
            with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
                completed = subprocess.run(
                    argv,
                    cwd=cwd,
                    stdout=stdout,
                    stderr=stderr,
                    shell=False,
                    timeout=timeout,
                )
                stdout_size = stdout.tell()
                stderr_size = stderr.tell()
                if (
                    stdout_size > MAX_SYSTEM_OUTPUT_BYTES
                    or stderr_size > MAX_SYSTEM_OUTPUT_BYTES
                ):
                    return None
                stdout.seek(0)
                stdout_text = stdout.read().decode("utf-8", errors="replace")
                return subprocess.CompletedProcess(
                    argv,
                    completed.returncode,
                    stdout_text,
                    "",
                )
        except (OSError, subprocess.TimeoutExpired):
            return None


def _resolve_codex_launch_spec() -> CodexLaunchSpec | None:
    if os.name == "nt":
        return _resolve_windows_codex_launch_spec()
    candidate_text = shutil.which("codex")
    if candidate_text is None:
        return None
    identity = _launch_file_identity(Path(candidate_text))
    if identity is None:
        return None
    return CodexLaunchSpec(
        (str(identity.path),),
        "native_exe",
        (identity,),
    )


def _resolve_validation_runtime_spec(
    repository_path: Path,
) -> ValidationRuntimeSpec | None:
    try:
        repository_root = Path(repository_path).resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    venv_root = repository_root / ".venv"
    scripts_directory = venv_root / ("Scripts" if os.name == "nt" else "bin")
    if not _safe_runtime_directory(venv_root, parent=repository_root):
        return None
    if not _safe_runtime_directory(scripts_directory, parent=venv_root):
        return None
    python_path = scripts_directory / ("python.exe" if os.name == "nt" else "python")
    identity = _launch_file_identity(
        python_path,
        require_windows_exe=os.name == "nt",
    )
    if identity is None or not _path_is_within(identity.path, venv_root):
        return None
    try:
        resolved_venv_root = venv_root.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    pytest_identity = _discover_validation_tool_identity(
        identity,
        resolved_venv_root,
        "pytest",
    )
    ruff_identity = _discover_validation_tool_identity(
        identity,
        resolved_venv_root,
        "ruff",
    )
    if pytest_identity is None or ruff_identity is None:
        return None
    if not _validation_runtime_python_is_current(identity):
        return None
    return ValidationRuntimeSpec(
        identity,
        resolved_venv_root,
        pytest_identity,
        ruff_identity,
    )


def _discover_validation_tool_identity(
    python_identity: CodexLaunchFileIdentity,
    venv_root: Path,
    tool: str,
    *,
    cwd: Path | None = None,
) -> ValidationToolIdentity | None:
    expected_modules = {
        "pytest": ("pytest", "_pytest"),
        "ruff": ("ruff",),
    }.get(tool)
    if expected_modules is None or not _validation_runtime_python_is_current(
        python_identity
    ):
        return None
    payload = _validation_tool_discovery_payload(
        python_identity.path,
        venv_root.parent if cwd is None else cwd,
        tool,
    )
    if payload is None or set(payload) != {"modules", "executable"}:
        return None
    modules = payload.get("modules")
    if not isinstance(modules, dict) or set(modules) != set(expected_modules):
        return None
    roots: list[Path] = []
    origins: list[Path] = []
    for module_name in expected_modules:
        module = modules.get(module_name)
        if not isinstance(module, dict) or set(module) != {"origin", "locations"}:
            return None
        origin = module.get("origin")
        locations = module.get("locations")
        if not isinstance(origin, str) or not isinstance(locations, list):
            return None
        if len(locations) != 1 or not isinstance(locations[0], str):
            return None
        origins.append(Path(origin))
        roots.append(Path(locations[0]))
    executable_value = payload.get("executable")
    executable: Path | None = None
    if tool == "ruff":
        if not isinstance(executable_value, str):
            return None
        executable = Path(executable_value)
    elif executable_value is not None:
        return None
    identity = _validation_tool_identity_from_paths(
        tool=tool,
        venv_root=venv_root,
        roots=tuple(roots),
        origins=tuple(origins),
        executable=executable,
    )
    if not _validation_runtime_python_is_current(python_identity):
        return None
    return identity


def _validation_tool_discovery_payload(
    python_path: Path,
    cwd: Path,
    tool: str,
) -> dict[str, object] | None:
    try:
        with tempfile.TemporaryFile() as stdout:
            completed = subprocess.run(
                [
                    str(python_path),
                    "-c",
                    VALIDATION_TOOL_DISCOVERY_SCRIPT,
                    tool,
                ],
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=subprocess.DEVNULL,
                shell=False,
                timeout=VALIDATION_RUNTIME_PREFLIGHT_TIMEOUT_SECONDS,
                env=_validation_environment(),
            )
            if (
                completed.returncode != 0
                or stdout.tell() > MAX_VALIDATION_TOOL_DISCOVERY_OUTPUT_BYTES
            ):
                return None
            stdout.seek(0)
            raw = stdout.read(MAX_VALIDATION_TOOL_DISCOVERY_OUTPUT_BYTES + 1)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if len(raw) > MAX_VALIDATION_TOOL_DISCOVERY_OUTPUT_BYTES:
        return None
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _validation_tool_identity_from_paths(
    *,
    tool: str,
    venv_root: Path,
    roots: tuple[Path, ...],
    origins: tuple[Path, ...],
    executable: Path | None,
) -> ValidationToolIdentity | None:
    if tool not in {"pytest", "ruff"} or not roots or not origins:
        return None
    candidates: list[Path] = []
    for root in roots:
        if not _safe_runtime_directory(root, parent=venv_root):
            return None
        tree_files = _validation_tool_tree_files(root)
        if tree_files is None:
            return None
        candidates.extend(tree_files)
    candidates.extend(origins)
    if executable is not None:
        candidates.append(executable)

    by_path: dict[str, ValidationToolFileIdentity] = {}
    file_nodes: set[tuple[int, int]] = set()
    total_bytes = 0
    for candidate in sorted(candidates, key=lambda path: (str(path).casefold(), str(path))):
        identity = _validation_tool_file_identity(candidate, venv_root)
        if identity is None:
            return None
        normalized = unicodedata.normalize(
            "NFC",
            identity.relative_path,
        ).casefold()
        existing = by_path.get(normalized)
        if existing is not None:
            if existing.path != identity.path:
                return None
            continue
        node = (identity.device, identity.inode)
        if node in file_nodes:
            return None
        file_nodes.add(node)
        by_path[normalized] = identity
        total_bytes += identity.size
        if (
            len(by_path) > MAX_VALIDATION_TOOL_FILES
            or total_bytes > MAX_VALIDATION_TOOL_TOTAL_BYTES
        ):
            return None
    if not by_path:
        return None
    files = tuple(
        sorted(
            by_path.values(),
            key=lambda identity: (
                identity.relative_path.casefold(),
                identity.relative_path,
            ),
        )
    )
    manifest = hashlib.sha256()
    for identity in files:
        manifest.update(identity.relative_path.encode("utf-8"))
        manifest.update(b"\0")
        manifest.update(str(identity.size).encode("ascii"))
        manifest.update(b"\0")
        manifest.update(identity.digest.encode("ascii"))
        manifest.update(b"\n")
    return ValidationToolIdentity(tool, files, manifest.hexdigest())


def _validation_tool_tree_files(root: Path) -> tuple[Path, ...] | None:
    files: list[Path] = []
    directories = [root]
    observed_entries = 0
    while directories:
        directory = directories.pop()
        try:
            entries = sorted(
                os.scandir(directory),
                key=lambda entry: (entry.name.casefold(), entry.name),
            )
        except OSError:
            return None
        for entry in entries:
            observed_entries += 1
            if observed_entries > MAX_VALIDATION_TOOL_TREE_ENTRIES:
                return None
            if entry.name == "__pycache__":
                continue
            path = Path(entry.path)
            try:
                path_stat = path.lstat()
            except OSError:
                return None
            reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            file_attributes = getattr(path_stat, "st_file_attributes", 0)
            if path.is_symlink() or bool(file_attributes & reparse_attribute):
                return None
            if stat.S_ISDIR(path_stat.st_mode):
                directories.append(path)
            elif stat.S_ISREG(path_stat.st_mode):
                if path.suffix.casefold() in VALIDATION_TOOL_CODE_SUFFIXES:
                    files.append(path)
            else:
                return None
    return tuple(files)


def _validation_tool_file_identity(
    path: Path,
    venv_root: Path,
) -> ValidationToolFileIdentity | None:
    if not path.is_absolute() or not venv_root.is_absolute():
        return None
    try:
        before = path.lstat()
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    file_attributes = getattr(before, "st_file_attributes", 0)
    if (
        not stat.S_ISREG(before.st_mode)
        or path.is_symlink()
        or bool(file_attributes & reparse_attribute)
        or before.st_size > MAX_VALIDATION_TOOL_FILE_BYTES
        or os.path.normcase(str(path)) != os.path.normcase(str(resolved))
        or not _path_is_within(resolved, venv_root)
    ):
        return None
    digest = hashlib.sha256()
    try:
        with resolved.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        after = resolved.lstat()
        relative = resolved.relative_to(venv_root).as_posix()
    except (OSError, ValueError):
        return None
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        return None
    return ValidationToolFileIdentity(
        resolved,
        unicodedata.normalize("NFC", relative),
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        digest.hexdigest(),
    )


def _safe_runtime_directory(path: Path, *, parent: Path) -> bool:
    if not path.is_absolute() or not parent.is_absolute():
        return False
    try:
        path_stat = path.lstat()
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    file_attributes = getattr(path_stat, "st_file_attributes", 0)
    return (
        stat.S_ISDIR(path_stat.st_mode)
        and not path.is_symlink()
        and not bool(file_attributes & reparse_attribute)
        and os.path.normcase(str(path)) == os.path.normcase(str(resolved))
        and _path_is_within(resolved, parent)
    )


def _validation_runtime_is_current(spec: ValidationRuntimeSpec) -> bool:
    return _validation_runtime_python_is_current(spec.python_identity)


def _validation_runtime_python_is_current(
    identity: CodexLaunchFileIdentity,
) -> bool:
    current = _launch_file_identity(
        identity.path,
        require_windows_exe=identity.path.suffix.casefold() == ".exe",
    )
    return current == identity


def _validation_tool_identity_is_current(
    runtime: ValidationRuntimeSpec,
    expected: ValidationToolIdentity,
    *,
    cwd: Path,
) -> bool:
    if expected.name not in {"pytest", "ruff"}:
        return False
    for identity in expected.files:
        current = _validation_tool_file_identity(identity.path, runtime.venv_root)
        if current != identity:
            return False
    if not _validation_runtime_is_current(runtime):
        return False
    discovered = _discover_validation_tool_identity(
        runtime.python_identity,
        runtime.venv_root,
        expected.name,
        cwd=cwd,
    )
    return discovered == expected and _validation_runtime_is_current(runtime)


def _codex_version_preflight(
    spec: CodexLaunchSpec,
    *,
    cwd: Path | None,
) -> GateResult:
    if not _codex_launch_spec_is_current(spec):
        return GateResult(False, "codex_launch_spec_changed")
    try:
        completed = subprocess.run(
            [*spec.argv_prefix, "--version"],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            timeout=30,
            env=_codex_worker_environment(include_transport=False),
        )
    except OSError:
        return GateResult(False, "codex_launch_failed")
    except subprocess.TimeoutExpired:
        return GateResult(False, "codex_version_check_failed")
    if completed.returncode != 0:
        return GateResult(False, "codex_version_check_failed")
    if not _codex_launch_spec_is_current(spec):
        return GateResult(False, "codex_launch_spec_changed")
    return GateResult(True, "runtime_ready")


def _codex_authentication_preflight(
    spec: CodexLaunchSpec,
    *,
    cwd: Path,
) -> GateResult:
    if not _codex_launch_spec_is_current(spec):
        return GateResult(False, "codex_launch_spec_changed")
    try:
        environment = _codex_worker_environment()
        completed = subprocess.run(
            [*spec.argv_prefix, "login", "status"],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            timeout=30,
            env=environment,
        )
    except _TransportEnvironmentError:
        return GateResult(False, "codex_transport_environment_invalid")
    except (OSError, subprocess.TimeoutExpired):
        return GateResult(False, "codex_auth_preflight_failed")
    if completed.returncode != 0:
        return GateResult(False, "codex_authentication_unavailable")
    if not _codex_launch_spec_is_current(spec):
        return GateResult(False, "codex_launch_spec_changed")
    return GateResult(True, "codex_authenticated")


def _resolve_windows_codex_launch_spec(
    *,
    version_preflight: Callable[[CodexLaunchSpec], GateResult] | None = None,
) -> CodexLaunchSpec | None:
    """Select the first runnable spec in one deterministic candidate order.

    The exact per-user ``bin/codex.exe`` wins when runnable. Otherwise direct
    child candidates are ordered by newest executable mtime, then by stable
    case-folded child name. A safe standalone PATH executable follows those
    per-user candidates, and the shell-free npm/node topology is last.
    """
    preflight = version_preflight or (
        lambda spec: _codex_version_preflight(spec, cwd=None)
    )
    native_text = shutil.which("codex.exe")
    bare_text = shutil.which("codex")
    shim_text = shutil.which("codex.cmd")
    node_text = shutil.which("node.exe")

    candidates = list(
        _windows_native_codex_launch_specs(
            native_text=native_text,
            bare_text=bare_text,
        )
    )
    npm_spec = _windows_npm_codex_launch_spec(
        shim_text=shim_text,
        bare_text=bare_text,
        node_text=node_text,
    )
    if npm_spec is not None:
        candidates.append(npm_spec)

    for candidate in candidates:
        result = preflight(candidate)
        if result.passed and _codex_launch_spec_is_current(candidate):
            return candidate
    return None


def _windows_native_codex_launch_specs(
    *,
    native_text: str | None,
    bare_text: str | None,
) -> tuple[CodexLaunchSpec, ...]:
    identities = list(_windows_per_user_codex_identities())
    path_text = native_text
    if (
        path_text is None
        and bare_text is not None
        and Path(bare_text).suffix.casefold() == ".exe"
    ):
        path_text = bare_text
    if path_text is not None:
        path_candidate = Path(path_text)
        if not _is_windows_apps_path(path_candidate):
            path_identity = _windows_codex_executable_identity(path_candidate)
            if path_identity is not None:
                known_paths = {str(item.path).casefold() for item in identities}
                if str(path_identity.path).casefold() not in known_paths:
                    identities.append(path_identity)
    return tuple(
        CodexLaunchSpec(
            (str(identity.path),),
            "native_exe",
            (identity,),
        )
        for identity in identities
    )


def _windows_per_user_codex_identities() -> tuple[CodexLaunchFileIdentity, ...]:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return ()
    root = Path(local_app_data) / "OpenAI" / "Codex" / "bin"
    if not root.is_absolute():
        return ()

    direct = _windows_codex_executable_identity(root / "codex.exe", root=root)
    hashed: list[CodexLaunchFileIdentity] = []
    try:
        children = tuple(root.iterdir())
    except OSError:
        children = ()
    for child in children:
        try:
            if not child.is_dir():
                continue
        except OSError:
            continue
        identity = _windows_codex_executable_identity(
            child / "codex.exe",
            root=root,
        )
        if identity is not None:
            hashed.append(identity)
    hashed.sort(
        key=lambda identity: (
            -identity.modified_ns,
            identity.path.parent.name.casefold(),
            identity.path.parent.name,
        )
    )
    return ((direct,) if direct is not None else ()) + tuple(hashed)


def _windows_codex_executable_identity(
    path: Path,
    *,
    root: Path | None = None,
) -> CodexLaunchFileIdentity | None:
    identity = _launch_file_identity(path, require_windows_exe=True)
    if identity is None or identity.path.name.casefold() != "codex.exe":
        return None
    if root is not None and not _path_is_within(identity.path, root):
        return None
    if _is_windows_apps_path(identity.path):
        return None
    return identity


def _windows_npm_codex_launch_spec(
    *,
    shim_text: str | None,
    bare_text: str | None,
    node_text: str | None,
) -> CodexLaunchSpec | None:
    if (
        shim_text is None
        and bare_text is not None
        and Path(bare_text).suffix.casefold() == ".cmd"
    ):
        shim_text = bare_text
    if shim_text is None or node_text is None:
        return None
    shim_identity = _launch_file_identity(Path(shim_text))
    if (
        shim_identity is None
        or shim_identity.path.suffix.casefold() != ".cmd"
        or _is_windows_apps_path(shim_identity.path)
    ):
        return None
    launcher_path = (
        shim_identity.path.parent
        / "node_modules"
        / "@openai"
        / "codex"
        / "bin"
        / "codex.js"
    )
    launcher_identity = _launch_file_identity(launcher_path)
    if launcher_identity is None or not _path_is_within(
        launcher_identity.path,
        shim_identity.path.parent,
    ):
        return None
    node_identity = _launch_file_identity(
        Path(node_text),
        require_windows_exe=True,
    )
    if node_identity is None or _is_windows_apps_path(node_identity.path):
        return None
    return CodexLaunchSpec(
        (str(node_identity.path), str(launcher_identity.path)),
        "npm_node_launcher",
        (node_identity, launcher_identity, shim_identity),
    )


def _launch_file_identity(
    path: Path,
    *,
    require_windows_exe: bool = False,
) -> CodexLaunchFileIdentity | None:
    if not path.is_absolute():
        return None
    try:
        if path.is_symlink():
            return None
        path_stat = path.lstat()
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if os.path.normcase(str(path)) != os.path.normcase(str(resolved)):
        return None
    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    file_attributes = getattr(path_stat, "st_file_attributes", 0)
    if (
        not stat.S_ISREG(path_stat.st_mode)
        or bool(file_attributes & reparse_attribute)
        or path_stat.st_size <= 0
    ):
        return None
    if require_windows_exe:
        if resolved.suffix.casefold() != ".exe":
            return None
        try:
            with resolved.open("rb") as executable:
                if executable.read(2) != b"MZ":
                    return None
        except OSError:
            return None
    return CodexLaunchFileIdentity(
        resolved,
        path_stat.st_dev,
        path_stat.st_ino,
        path_stat.st_size,
        path_stat.st_mtime_ns,
    )


def _codex_launch_spec_is_current(spec: CodexLaunchSpec) -> bool:
    if spec.kind not in {"native_exe", "npm_node_launcher"}:
        return False
    if not spec.argv_prefix or not spec.file_identities:
        return False
    for identity in spec.file_identities:
        current = _launch_file_identity(
            identity.path,
            require_windows_exe=identity.path.suffix.casefold() == ".exe",
        )
        if current != identity:
            return False
    expected_prefix = (
        (str(spec.file_identities[0].path),)
        if spec.kind == "native_exe"
        else (
            str(spec.file_identities[0].path),
            str(spec.file_identities[1].path),
        )
    )
    return spec.argv_prefix == expected_prefix


def _is_windows_apps_path(path: Path) -> bool:
    folded_parts = tuple(part.casefold() for part in path.parts)
    for index in range(1, len(folded_parts)):
        if (
            folded_parts[index] == "windowsapps"
            and folded_parts[index - 1] in {"program files", "microsoft"}
        ):
            return True
    roots: list[Path] = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        roots.append(Path(local_app_data) / "Microsoft" / "WindowsApps")
    program_files = os.environ.get("ProgramFiles")
    if program_files:
        roots.append(Path(program_files) / "WindowsApps")
    return any(_path_is_within(path, root) for root in roots)


def _path_is_within(path: Path, parent: Path) -> bool:
    if not path.is_absolute() or not parent.is_absolute():
        return False
    try:
        common = os.path.commonpath((str(path), str(parent)))
    except ValueError:
        return False
    return os.path.normcase(common) == os.path.normcase(str(parent))


def _codex_exec_argv(
    launch_spec: CodexLaunchSpec,
    workspace: Path,
    *,
    platform_name: str | None = None,
) -> list[str]:
    argv = [
        *launch_spec.argv_prefix,
        "--ask-for-approval",
        "never",
        "exec",
        "--sandbox",
        "workspace-write",
        "--ephemeral",
        "--json",
        "--ignore-user-config",
        "--strict-config",
        "--cd",
        str(workspace),
        "-c",
        "sandbox_workspace_write.network_access=false",
        "-c",
        'web_search="disabled"',
    ]
    if (platform_name or os.name) == "nt":
        argv.extend(("-c", "features.unified_exec=false"))
    argv.append("-")
    return argv


def _codex_worker_environment(
    source: Mapping[str, str] | None = None,
    *,
    include_transport: bool = True,
    platform_name: str | None = None,
) -> dict[str, str]:
    ambient = os.environ if source is None else source
    case_insensitive = (platform_name or os.name) == "nt"
    environment: dict[str, str] = {}
    for canonical in CODEX_BASE_ENVIRONMENT_NAMES:
        observed = _matching_environment_values(
            ambient,
            canonical,
            case_insensitive=case_insensitive,
        )
        if observed:
            environment[canonical] = observed[0][1]
    if not include_transport:
        return environment

    for canonical, lowercase, requires_url in CODEX_PROXY_ENVIRONMENT_NAMES:
        observed = _matching_environment_values(
            ambient,
            canonical,
            lowercase,
            case_insensitive=case_insensitive,
        )
        for _name, value in observed:
            _validate_transport_environment_value(
                value,
                requires_url=requires_url,
            )
        if not observed:
            continue
        environment[canonical] = observed[0][1]
    return environment


def _matching_environment_values(
    ambient: Mapping[str, str],
    canonical: str,
    *aliases: str,
    case_insensitive: bool,
) -> list[tuple[str, str]]:
    accepted = {canonical, *aliases}
    accepted_folded = {name.casefold() for name in accepted}
    observed = [
        (name, value)
        for name, value in ambient.items()
        if name in accepted
        or (case_insensitive and name.casefold() in accepted_folded)
    ]
    return sorted(
        observed,
        key=lambda item: (
            item[0] != canonical,
            item[0].casefold(),
            item[0],
        ),
    )


def _validate_transport_environment_value(
    value: object,
    *,
    requires_url: bool,
) -> None:
    if not isinstance(value, str):
        raise _TransportEnvironmentError
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as exc:
        raise _TransportEnvironmentError from exc
    if (
        not value
        or len(encoded) > MAX_PROXY_ENV_VALUE_BYTES
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise _TransportEnvironmentError
    if not requires_url:
        return
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
    except ValueError as exc:
        raise _TransportEnvironmentError from exc
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or not parsed.netloc
        or hostname is None
        or any(character.isspace() for character in value)
    ):
        raise _TransportEnvironmentError


def _terminate_process_tree(process: subprocess.Popen[str]) -> bool:
    if process.poll() is not None:
        return True
    termination_requested = False
    if os.name == "nt":
        try:
            completed = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                shell=False,
                timeout=10,
            )
            termination_requested = completed.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            termination_requested = False
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
            termination_requested = True
        except OSError:
            termination_requested = False
    if not termination_requested:
        try:
            process.kill()
            termination_requested = True
        except OSError:
            termination_requested = False
    try:
        process.wait(timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
            process.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            return False
    return process.poll() is not None


def _parse_codex_jsonl(value: str) -> dict[str, object]:
    return _parse_codex_jsonl_lines(value.splitlines())


def _consume_codex_jsonl_stream(stream: TextIOBase) -> dict[str, object]:
    return _parse_codex_jsonl_lines(iter(stream.readline, ""))


def _consume_codex_diagnostic_stream(stream: TextIOBase) -> str | None:
    category: str | None = None
    for line_number, line in enumerate(iter(stream.readline, ""), start=1):
        if line_number > MAX_JSONL_LINES or not isinstance(line, str):
            break
        if len(line.encode("utf-8", errors="replace")) > MAX_JSONL_LINE_BYTES:
            break
        category = _codex_failure_category(
            category,
            _bounded_codex_diagnostic_category(line),
            fallback=None,
        )
    return category


def _parse_codex_jsonl_lines(lines: object) -> dict[str, object]:
    fatal = False
    turn_completed = False
    final_usage: object = None
    failure_category: str | None = None
    if not hasattr(lines, "__iter__"):
        return {
            "fatal": True,
            "turn_completed": False,
            "usage_tokens": None,
            "input_tokens": None,
            "cached_input_tokens": None,
            "output_tokens": None,
            "reasoning_output_tokens": None,
            "failure_category": None,
        }
    for line_number, line in enumerate(lines, start=1):
        if line_number > MAX_JSONL_LINES or not isinstance(line, str):
            return {
                "fatal": True,
                "turn_completed": False,
                "usage_tokens": None,
                "input_tokens": None,
                "cached_input_tokens": None,
                "output_tokens": None,
                "reasoning_output_tokens": None,
                "failure_category": failure_category,
            }
        if len(line.encode("utf-8", errors="replace")) > MAX_JSONL_LINE_BYTES:
            return {
                "fatal": True,
                "turn_completed": False,
                "usage_tokens": None,
                "input_tokens": None,
                "cached_input_tokens": None,
                "output_tokens": None,
                "reasoning_output_tokens": None,
                "failure_category": failure_category,
            }
        failure_category = _codex_failure_category(
            failure_category,
            _bounded_codex_diagnostic_category(line),
            fallback=None,
        )
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            fatal = True
            continue
        if not isinstance(event, dict):
            fatal = True
            continue
        event_type = event.get("type")
        if event_type in {"error", "turn.failed", "item.failed"}:
            fatal = True
        if event_type == "turn.completed":
            turn_completed = True
            final_usage = event.get("usage")
    usage = _codex_usage_telemetry(final_usage)
    return {
        "fatal": fatal,
        "turn_completed": turn_completed,
        **usage,
        "failure_category": failure_category,
    }


def _codex_execution_result_from_parsed(
    status: str,
    category: object,
    parsed: Mapping[str, object],
) -> CodexExecutionResult:
    return CodexExecutionResult(
        status=status,
        category=(
            category if isinstance(category, str) else "codex_structured_failure"
        ),
        usage_tokens=_bounded_usage_token_count(parsed.get("usage_tokens")),
        input_tokens=_bounded_usage_token_count(parsed.get("input_tokens")),
        cached_input_tokens=_bounded_usage_token_count(
            parsed.get("cached_input_tokens")
        ),
        output_tokens=_bounded_usage_token_count(parsed.get("output_tokens")),
        reasoning_output_tokens=_bounded_usage_token_count(
            parsed.get("reasoning_output_tokens")
        ),
    )


def _bounded_codex_diagnostic_category(value: str) -> str | None:
    lowered = value.casefold()
    if any(
        marker in lowered
        for marker in (
            "unexpected argument",
            "unrecognized option",
            "unknown option",
            "invalid value",
            "configuration error",
            "config error",
        )
    ):
        return "codex_cli_argument_or_config_rejected"
    if any(
        marker in lowered
        for marker in (
            "authentication required",
            "authentication unavailable",
            "not logged in",
            "login required",
            "missing api key",
            "unauthorized",
            "http 401",
        )
    ):
        return "codex_authentication_unavailable"
    if any(
        marker in lowered
        for marker in (
            "windows sandbox",
            "sandbox initialization failed",
            "sandbox setup failed",
            "workspace-write sandbox failed",
        )
    ):
        return "windows_sandbox_failed"
    if any(
        marker in lowered
        for marker in (
            "connection failed",
            "failed to connect",
            "network error",
            "reconnecting",
            "request failed",
            "stream disconnected",
        )
    ):
        return "codex_transport_unavailable"
    return None


def _codex_failure_category(
    *categories: object,
    fallback: str | None,
) -> str | None:
    observed = {category for category in categories if isinstance(category, str)}
    for category in (
        "codex_cli_argument_or_config_rejected",
        "codex_authentication_unavailable",
        "windows_sandbox_failed",
        "codex_transport_unavailable",
    ):
        if category in observed:
            return category
    return fallback


def _usage_tokens(value: object) -> int | None:
    if not isinstance(value, dict):
        return None
    total = _bounded_usage_token_count(value.get("total_tokens"))
    if total is not None:
        return total
    input_tokens = _bounded_usage_token_count(value.get("input_tokens"))
    output_tokens = _bounded_usage_token_count(value.get("output_tokens"))
    if input_tokens is not None and output_tokens is not None:
        return _bounded_usage_token_count(input_tokens + output_tokens)
    return None


def _codex_usage_telemetry(value: object) -> dict[str, int | None]:
    telemetry = {
        "usage_tokens": _usage_tokens(value),
        "input_tokens": None,
        "cached_input_tokens": None,
        "output_tokens": None,
        "reasoning_output_tokens": None,
    }
    if not isinstance(value, dict):
        return telemetry
    for field_name in (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
    ):
        telemetry[field_name] = _bounded_usage_token_count(value.get(field_name))
    return telemetry


def _bounded_usage_token_count(value: object) -> int | None:
    if (
        type(value) is int
        and 0 <= value <= MAX_OBSERVED_USAGE_TOKENS
    ):
        return value
    return None


def _validation_environment() -> dict[str, str]:
    environment: dict[str, str] = {}
    case_insensitive = os.name == "nt"
    for canonical in VALIDATION_ENVIRONMENT_NAMES:
        observed = _matching_environment_values(
            os.environ,
            canonical,
            case_insensitive=case_insensitive,
        )
        if observed:
            environment[canonical] = observed[0][1]
    return environment


def _validation_command(
    command: str,
    runtime: ValidationRuntimeSpec,
    *,
    pytest_basetemp: Path,
) -> tuple[list[str], dict[str, str]]:
    environment = _validation_environment()
    python = str(runtime.python_identity.path)
    if command == VALIDATION_COMMANDS[0]:
        if not pytest_basetemp.is_absolute():
            raise ValueError("pytest basetemp must be absolute")
        environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        return [
            python,
            "-m",
            "pytest",
            "--basetemp",
            str(pytest_basetemp),
        ], environment
    if command == VALIDATION_COMMANDS[1]:
        return [python, "-m", "ruff", "check", ".", "--no-cache"], environment
    if command == VALIDATION_COMMANDS[2]:
        return ["git", "diff", "--check"], environment
    raise ValueError("validation command is not authorized")


def _resolve_validation_basetemp(
    path: Path,
    *,
    repository_path: Path,
    worktree_path: Path,
    venv_root: Path,
) -> Path | None:
    if not path.is_absolute():
        return None
    try:
        path_stat = path.lstat()
        resolved = path.resolve(strict=True)
        protected_roots = tuple(
            candidate.resolve(strict=True)
            for candidate in (repository_path, worktree_path, venv_root)
        )
    except (OSError, RuntimeError):
        return None
    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    file_attributes = getattr(path_stat, "st_file_attributes", 0)
    if (
        not stat.S_ISDIR(path_stat.st_mode)
        or path.is_symlink()
        or bool(file_attributes & reparse_attribute)
    ):
        return None
    if any(
        _path_is_within(resolved, root) or _path_is_within(root, resolved)
        for root in protected_roots
    ):
        return None
    return resolved


def _git_null_device() -> str:
    return "NUL" if os.name == "nt" else "/dev/null"


def _repository_identity_from_remote(value: str) -> str | None:
    candidate = value.strip().removesuffix(".git")
    patterns = (
        r"https://github\.com/([^/]+/[^/]+)",
        r"ssh://git@github\.com/([^/]+/[^/]+)",
        r"git@github\.com:([^/]+/[^/]+)",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, candidate)
        if match is not None:
            return match.group(1)
    return None


def _safe_markdown_path(value: str) -> bool:
    if "\\" in value or value.startswith(("/", ".git")):
        return False
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", "..", ".git"} for part in path.parts):
        return False
    return path.suffix.lower() == ".md" and value.startswith(
        ("docs/process/", "docs/development/")
    )


def _pull_request_body(
    *,
    source_issue_number: int,
    required_headings: tuple[str, ...],
    changed_paths: tuple[str, ...],
    validation_commands: tuple[str, ...],
    pilot_kind: str = CODEX_PILOT_DOCS_ONLY_KIND,
) -> str:
    if pilot_kind not in CODEX_PILOT_AUTHORIZATION_KINDS:
        raise ValueError("pilot_kind is invalid")
    python_change = pilot_kind == CODEX_PILOT_BOUNDED_PYTHON_KIND
    out_of_scope_confirmation = (
        (
            "No worker approval or merge authority was added. No retry or "
            "background-resume authority was added. No changes outside the "
            "exact reviewed allowlist were permitted. No broader execution "
            "class was granted."
        )
        if python_change
        else "No product code, execution authority, approval, or merge was added."
    )
    content = {
        "Summary": (
            "Phoenix supervised a bounded Python Codex change."
            if python_change
            else "Phoenix supervised a bounded docs-only Codex change."
        ),
        "Scope": (
            "Only reviewed bounded Python paths were eligible for publication."
            if python_change
            else "Only reviewed Markdown paths were eligible for publication."
        ),
        "Changed files": "\n".join(f"- `{path}`" for path in changed_paths),
        "Out-of-scope confirmation": out_of_scope_confirmation,
        "Validation performed": "\n".join(
            f"- `{command}`: PASS" for command in validation_commands
        ),
        "Risks": "Stopped for required assistant architecture review.",
    }
    sections = [f"Refs #{source_issue_number}"]
    for heading in required_headings:
        sections.extend(["", f"## {heading}", "", content.get(heading, "Reviewed.")])
    return "\n".join(sections)
