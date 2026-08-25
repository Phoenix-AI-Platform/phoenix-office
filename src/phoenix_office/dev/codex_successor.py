"""Deterministic read-only successor proposals for the Codex autonomy queue."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import unicodedata
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, Protocol

SUCCESSOR_PROPOSAL_SCHEMA_VERSION: Final = "codex-successor-proposal.v1"
SUCCESSOR_CANDIDATE_SCHEMA_VERSION: Final = (
    "codex-successor-candidate.v1"
)
SUCCESSOR_FINGERPRINT_SCHEMA_VERSION: Final = (
    "codex-successor-proposal-fingerprint.v1"
)
REPOSITORY_IDENTITY: Final = "Phoenix-AI-Platform/phoenix-office"
BASE_BRANCH: Final = "main"
CANDIDATE_FENCE: Final = "phoenix-codex-successor"
CURRENT_EXECUTION_CLASS: Final = "docs-only-supervised"

MAX_EVIDENCE_BYTES: Final = 2 * 1024 * 1024
MAX_GITHUB_OUTPUT_BYTES: Final = 8 * 1024 * 1024
MAX_GIT_OUTPUT_BYTES: Final = 4 * 1024 * 1024
MAX_ISSUES: Final = 100
MAX_ISSUE_BODY_CHARACTERS: Final = 65_536
MAX_CANDIDATE_BYTES: Final = 16 * 1024
MAX_DEPENDENCIES_PER_CANDIDATE: Final = 20
MAX_DEPENDENCY_QUERIES: Final = 100
MAX_TRACKED_PATHS: Final = 100_000
MAX_ALLOWED_PATHS: Final = 3
MAX_PRIORITY: Final = 1_000
GIT_TIMEOUT_SECONDS: Final = 10
GITHUB_TIMEOUT_SECONDS: Final = 60

_CANDIDATE_FIELDS: Final = {
    "allowed_paths",
    "base_branch",
    "candidate_state",
    "depends_on",
    "execution_class",
    "expected_pr_title",
    "priority",
    "queue",
    "repository",
    "risk_class",
    "schema_version",
    "task_id",
}
_CANDIDATE_STATES: Final = {"blocked", "deferred", "ready"}
_CANDIDATE_QUEUES: Final = {"autonomy", "manual"}
_RISK_CLASSES: Final = {"low", "medium", "high"}
_SHA_PATTERN: Final = re.compile(r"[0-9a-f]{40}")
_TASK_ID_PATTERN: Final = re.compile(r"TASK-[0-9]{3,6}")
_FINGERPRINT_PATTERN: Final = re.compile(r"[0-9a-f]{64}")
_CANDIDATE_BLOCK_PATTERN: Final = re.compile(
    rf"(?ms)^```{re.escape(CANDIDATE_FENCE)}[ \t]*\n"
    r"(?P<payload>.*?)\n```[ \t]*$"
)
_SENSITIVE_TEXT_PATTERNS: Final = (
    re.compile(r"(?i)\b(?:sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9_]{8,})\b"),
    re.compile(r"(?i)\bgithub_pat_[A-Za-z0-9_]{8,}\b"),
    re.compile(r"(?i)\b(?:password|secret|token)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(?:[A-Z]:\\Users\\|/home/|/Users/)[^\s`]+"),
)
_PROCESS_ENVIRONMENT_NAMES: Final = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "HOME",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "LOCALAPPDATA",
    "APPDATA",
    "TEMP",
    "TMP",
    "TMPDIR",
)


class CodexSuccessorProposalError(Exception):
    """Bounded failure safe to expose as a proposal category."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class RepositoryState:
    """Read-only local Git facts used by the verified-state gate."""

    branch: str
    head: str
    clean: bool


@dataclass(frozen=True, slots=True)
class VerificationState:
    """Bounded Phoenix Tools evidence identity bound to the local HEAD."""

    verification_id: str
    base_sha: str


@dataclass(frozen=True, slots=True)
class DependencyFact:
    """Bounded dependency state used for eligibility and fingerprinting."""

    issue_number: int
    state: str
    state_reason: str | None

    @property
    def completed(self) -> bool:
        return self.state == "CLOSED" and self.state_reason == "COMPLETED"


@dataclass(frozen=True, slots=True)
class SuccessorCandidate:
    """Strict explicit successor metadata from one open GitHub issue."""

    issue_number: int
    title: str
    task_id: str
    candidate_state: str
    queue: str
    priority: int
    risk_class: str
    depends_on: tuple[int, ...]
    repository: str
    base_branch: str
    allowed_paths: tuple[str, ...]
    expected_pr_title: str
    execution_class: str


class CodexSuccessorServices(Protocol):
    """Injectable read-only boundary for local Git and GitHub facts."""

    def repository_state(self) -> RepositoryState:
        ...

    def tracked_paths(self) -> tuple[str, ...]:
        ...

    def list_open_issues(self) -> object:
        ...

    def read_dependency(self, issue_number: int) -> object:
        ...


ProcessRunner = Callable[..., subprocess.CompletedProcess[str]]
CanonicalSerializer = Callable[[Mapping[str, object]], bytes]
FingerprintFunction = Callable[[bytes], str]


class SystemCodexSuccessorServices:
    """Shell-free local Git and read-only GitHub CLI adapter."""

    def __init__(
        self,
        repository_root: Path,
        *,
        process_runner: ProcessRunner | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self._repository_root = Path(repository_root)
        self._process_runner = process_runner or subprocess.run
        self._environment = dict(environment if environment is not None else os.environ)

    def repository_state(self) -> RepositoryState:
        """Inspect branch, HEAD, and cleanliness without mutation."""

        branch = self._run_git("branch", "--show-current").strip()
        head = self._run_git("rev-parse", "HEAD").strip()
        status_output = self._run_git("status", "--porcelain=v1")
        return RepositoryState(branch=branch, head=head, clean=not status_output.strip())

    def tracked_paths(self) -> tuple[str, ...]:
        """Return the bounded tracked-path set needed for candidate validation."""

        output = self._run_git("ls-files", "-z")
        if not output:
            raise CodexSuccessorProposalError("repository_paths_unavailable")
        paths = tuple(item for item in output.split("\0") if item)
        if (
            not paths
            or len(paths) > MAX_TRACKED_PATHS
            or len(paths) != len(set(paths))
        ):
            raise CodexSuccessorProposalError("repository_paths_unavailable")
        return paths

    def list_open_issues(self) -> object:
        """Read the bounded open-issue snapshot; no mutation command exists."""

        output = self._run_gh(
            "issue",
            "list",
            "--repo",
            REPOSITORY_IDENTITY,
            "--state",
            "open",
            "--limit",
            str(MAX_ISSUES + 1),
            "--json",
            "number,title,state,body",
        )
        return _load_github_json(output)

    def read_dependency(self, issue_number: int) -> object:
        """Read only the exact bounded facts required for one dependency."""

        if type(issue_number) is not int or not 1 <= issue_number <= 10**9:
            raise CodexSuccessorProposalError("dependency_state_unknown")
        output = self._run_gh(
            "issue",
            "view",
            str(issue_number),
            "--repo",
            REPOSITORY_IDENTITY,
            "--json",
            "number,state,stateReason",
        )
        try:
            return _load_github_json(output)
        except CodexSuccessorProposalError as exc:
            raise CodexSuccessorProposalError("dependency_state_unknown") from exc

    def _run_git(self, *arguments: str) -> str:
        return self._run(
            ("git", "-C", str(self._repository_root), *arguments),
            failure_category="repository_inspection_failed",
            timeout=GIT_TIMEOUT_SECONDS,
            max_output_bytes=MAX_GIT_OUTPUT_BYTES,
        )

    def _run_gh(self, *arguments: str) -> str:
        if tuple(arguments[:2]) not in {("issue", "list"), ("issue", "view")}:
            raise CodexSuccessorProposalError("github_read_failed")
        return self._run(
            ("gh", *arguments),
            failure_category="github_read_failed",
            timeout=GITHUB_TIMEOUT_SECONDS,
            max_output_bytes=MAX_GITHUB_OUTPUT_BYTES,
        )

    def _run(
        self,
        argv: tuple[str, ...],
        *,
        failure_category: str,
        timeout: int,
        max_output_bytes: int,
    ) -> str:
        try:
            completed = self._process_runner(
                list(argv),
                capture_output=True,
                check=False,
                cwd=self._repository_root,
                env=_bounded_process_environment(self._environment),
                shell=False,
                text=True,
                timeout=timeout,
            )
        except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
            raise CodexSuccessorProposalError(failure_category) from exc
        if completed.returncode != 0:
            raise CodexSuccessorProposalError(failure_category)
        if (
            len(completed.stdout.encode("utf-8")) > max_output_bytes
            or len(completed.stderr.encode("utf-8")) > max_output_bytes
        ):
            raise CodexSuccessorProposalError(failure_category)
        return completed.stdout


def propose_codex_successor(
    *,
    repository_root: Path,
    verification_evidence_path: Path,
    services: CodexSuccessorServices | None = None,
    canonical_serializer: CanonicalSerializer | None = None,
    fingerprint_function: FingerprintFunction | None = None,
) -> dict[str, object]:
    """Return zero or one deterministic proposal without opening authority."""

    system = services or SystemCodexSuccessorServices(repository_root)
    state: RepositoryState | None = None
    verification: VerificationState | None = None
    candidate_count = 0
    try:
        state = system.repository_state()
        _require_canonical_repository_state(state)
        verification = _load_verification_evidence(
            verification_evidence_path,
            current_head=state.head,
        )
        tracked_paths = _validate_tracked_paths(system.tracked_paths())
        issues = _validate_issue_payload(system.list_open_issues())
        candidates = _parse_explicit_candidates(
            issues,
            repository_root=Path(repository_root),
            tracked_paths=tracked_paths,
        )
        dependencies = _resolve_dependency_facts(candidates, system)
        eligible = tuple(
            candidate
            for candidate in candidates
            if candidate.candidate_state == "ready"
            and candidate.queue == "autonomy"
            and all(dependencies[number].completed for number in candidate.depends_on)
        )
        candidate_count = len(eligible)
        if not eligible:
            return _blocked_result(
                "no_eligible_successor",
                verified_base_sha=verification.base_sha,
                verification_id=verification.verification_id,
            )
        selected = sorted(
            eligible,
            key=lambda candidate: (-candidate.priority, candidate.issue_number),
        )[0]
        fingerprint = _proposal_fingerprint(
            verification=verification,
            candidate=selected,
            dependency_facts=tuple(
                dependencies[number] for number in selected.depends_on
            ),
            canonical_serializer=canonical_serializer or _canonical_json_bytes,
            fingerprint_function=fingerprint_function or _sha256_hex,
        )
        return _successful_result(
            verification=verification,
            candidate_count=candidate_count,
            candidate=selected,
            fingerprint=fingerprint,
        )
    except CodexSuccessorProposalError as exc:
        return _blocked_result(
            exc.category,
            verified_base_sha=(
                verification.base_sha
                if verification is not None
                else state.head
                if state is not None and _SHA_PATTERN.fullmatch(state.head)
                else None
            ),
            verification_id=(
                verification.verification_id if verification is not None else None
            ),
            candidate_count=candidate_count,
        )
    except Exception:
        return _blocked_result(
            "successor_proposal_internal_failure",
            verified_base_sha=(
                verification.base_sha if verification is not None else None
            ),
            verification_id=(
                verification.verification_id if verification is not None else None
            ),
            candidate_count=candidate_count,
        )


def _require_canonical_repository_state(state: RepositoryState) -> None:
    if state.branch != BASE_BRANCH:
        raise CodexSuccessorProposalError("non_main_checkout")
    if _SHA_PATTERN.fullmatch(state.head) is None:
        raise CodexSuccessorProposalError("invalid_head")
    if not state.clean:
        raise CodexSuccessorProposalError("dirty_worktree")


def _load_verification_evidence(
    path: Path,
    *,
    current_head: str,
) -> VerificationState:
    try:
        details = path.lstat()
    except FileNotFoundError as exc:
        raise CodexSuccessorProposalError("missing_verification_evidence") from exc
    except OSError as exc:
        raise CodexSuccessorProposalError("verification_evidence_unreadable") from exc
    if (
        not stat.S_ISREG(details.st_mode)
        or _is_link_or_reparse(details)
        or not 1 <= details.st_size <= MAX_EVIDENCE_BYTES
    ):
        raise CodexSuccessorProposalError("verification_evidence_unreadable")
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        payload = _load_json_without_duplicates(text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise CodexSuccessorProposalError("malformed_verification_evidence") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != "2.0":
        raise CodexSuccessorProposalError("malformed_verification_evidence")
    if (
        payload.get("overall_health") != "pass"
        or payload.get("overall_evidence_coverage") != "complete"
    ):
        raise CodexSuccessorProposalError("verification_failed_or_partial")
    verification_id = payload.get("verification_id")
    if not _valid_verification_id(verification_id):
        raise CodexSuccessorProposalError("malformed_verification_evidence")
    configured_repositories = _validate_verification_summary(
        payload.get("summary")
    )
    repositories = payload.get("repositories")
    if (
        not isinstance(repositories, list)
        or len(repositories) != configured_repositories
    ):
        raise CodexSuccessorProposalError("malformed_verification_evidence")
    repository_names = [
        item.get("repository") if isinstance(item, dict) else None
        for item in repositories
    ]
    if any(not _safe_repository_name(name) for name in repository_names):
        raise CodexSuccessorProposalError("malformed_verification_evidence")
    office_entries = [
        item
        for item in repositories
        if isinstance(item, dict) and item.get("repository") == "phoenix-office"
    ]
    if len(office_entries) != 1:
        raise CodexSuccessorProposalError("verification_repository_ambiguous")
    if len(repository_names) != len(set(repository_names)):
        raise CodexSuccessorProposalError("malformed_verification_evidence")
    office = office_entries[0]
    git = office.get("git")
    if (
        office.get("health") != "pass"
        or office.get("evidence_coverage") != "complete"
        or not isinstance(git, dict)
        or git.get("is_git_work_tree") is not True
        or git.get("branch") != BASE_BRANCH
        or git.get("working_tree_clean") is not True
        or git.get("status_entries") != []
    ):
        raise CodexSuccessorProposalError("verification_failed_or_partial")
    evidence_head = git.get("commit")
    if not isinstance(evidence_head, str) or evidence_head != current_head:
        raise CodexSuccessorProposalError("verification_head_mismatch")
    return VerificationState(
        verification_id=verification_id,
        base_sha=evidence_head,
    )


def _validate_verification_summary(value: object) -> int:
    if not isinstance(value, dict):
        raise CodexSuccessorProposalError("malformed_verification_evidence")
    required_zero = (
        "commands_not_started",
        "dirty_working_trees",
        "evidence_insufficient",
        "evidence_partial",
        "failed_commands",
        "health_fail",
        "health_unknown",
    )
    if any(value.get(name) != 0 for name in required_zero):
        raise CodexSuccessorProposalError("verification_failed_or_partial")
    total = value.get("total_configured_repositories")
    if (
        type(total) is not int
        or not 1 <= total <= 20
        or value.get("repositories_discovered") != total
        or value.get("clean_working_trees") != total
        or value.get("health_pass") != total
        or value.get("evidence_complete") != total
    ):
        raise CodexSuccessorProposalError("verification_failed_or_partial")
    return total


def _validate_issue_payload(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list) or len(value) > MAX_ISSUES:
        raise CodexSuccessorProposalError("malformed_candidate_payload")
    issues: list[Mapping[str, object]] = []
    numbers: set[int] = set()
    required_fields = {"body", "number", "state", "title"}
    for item in value:
        if not isinstance(item, dict) or set(item) != required_fields:
            raise CodexSuccessorProposalError("malformed_candidate_payload")
        number = item.get("number")
        title = item.get("title")
        state = item.get("state")
        body = item.get("body")
        if (
            type(number) is not int
            or not 1 <= number <= 10**9
            or number in numbers
            or state != "OPEN"
            or not _safe_public_text(title, max_length=160)
            or not isinstance(body, str)
            or len(body) > MAX_ISSUE_BODY_CHARACTERS
        ):
            raise CodexSuccessorProposalError("malformed_candidate_payload")
        numbers.add(number)
        issues.append(item)
    return tuple(issues)


def _parse_explicit_candidates(
    issues: tuple[Mapping[str, object], ...],
    *,
    repository_root: Path,
    tracked_paths: frozenset[str],
) -> tuple[SuccessorCandidate, ...]:
    candidates: list[SuccessorCandidate] = []
    for issue in issues:
        metadata = _candidate_metadata_from_body(str(issue["body"]))
        if metadata is None:
            continue
        candidate = _candidate_from_metadata(issue, metadata)
        if candidate.candidate_state == "ready" and candidate.queue == "autonomy":
            _require_candidate_paths(
                candidate.allowed_paths,
                repository_root=repository_root,
                tracked_paths=tracked_paths,
            )
        candidates.append(candidate)
    return tuple(candidates)


def _candidate_metadata_from_body(body: str) -> Mapping[str, object] | None:
    normalized = body.replace("\r\n", "\n").replace("\r", "\n")
    marker = f"```{CANDIDATE_FENCE}"
    if marker not in normalized:
        return None
    matches = tuple(_CANDIDATE_BLOCK_PATTERN.finditer(normalized))
    if len(matches) != 1 or normalized.count(marker) != 1:
        raise CodexSuccessorProposalError("malformed_candidate_metadata")
    candidate_text = matches[0].group("payload")
    if not 1 <= len(candidate_text.encode("utf-8")) <= MAX_CANDIDATE_BYTES:
        raise CodexSuccessorProposalError("malformed_candidate_metadata")
    try:
        value = _load_json_without_duplicates(candidate_text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise CodexSuccessorProposalError("malformed_candidate_metadata") from exc
    if not isinstance(value, dict) or set(value) != _CANDIDATE_FIELDS:
        raise CodexSuccessorProposalError("malformed_candidate_metadata")
    return value


def _candidate_from_metadata(
    issue: Mapping[str, object],
    value: Mapping[str, object],
) -> SuccessorCandidate:
    task_id = value.get("task_id")
    candidate_state = value.get("candidate_state")
    queue = value.get("queue")
    priority = value.get("priority")
    risk_class = value.get("risk_class")
    depends_on = value.get("depends_on")
    allowed_paths = value.get("allowed_paths")
    expected_pr_title = value.get("expected_pr_title")
    if (
        value.get("schema_version") != SUCCESSOR_CANDIDATE_SCHEMA_VERSION
        or not isinstance(task_id, str)
        or _TASK_ID_PATTERN.fullmatch(task_id) is None
        or candidate_state not in _CANDIDATE_STATES
        or queue not in _CANDIDATE_QUEUES
        or type(priority) is not int
        or not 0 <= priority <= MAX_PRIORITY
        or risk_class not in _RISK_CLASSES
        or value.get("repository") != REPOSITORY_IDENTITY
        or value.get("base_branch") != BASE_BRANCH
        or value.get("execution_class") != CURRENT_EXECUTION_CLASS
        or not _safe_public_text(expected_pr_title, max_length=120)
    ):
        raise CodexSuccessorProposalError("malformed_candidate_metadata")
    dependency_numbers = _validated_dependency_numbers(depends_on)
    safe_paths = _validated_allowed_paths(allowed_paths)
    issue_number = issue["number"]
    if issue_number in dependency_numbers:
        raise CodexSuccessorProposalError("malformed_candidate_metadata")
    return SuccessorCandidate(
        issue_number=issue_number,
        title=str(issue["title"]),
        task_id=task_id,
        candidate_state=str(candidate_state),
        queue=str(queue),
        priority=priority,
        risk_class=str(risk_class),
        depends_on=dependency_numbers,
        repository=REPOSITORY_IDENTITY,
        base_branch=BASE_BRANCH,
        allowed_paths=safe_paths,
        expected_pr_title=str(expected_pr_title),
        execution_class=CURRENT_EXECUTION_CLASS,
    )


def _validated_dependency_numbers(value: object) -> tuple[int, ...]:
    if not isinstance(value, list) or len(value) > MAX_DEPENDENCIES_PER_CANDIDATE:
        raise CodexSuccessorProposalError("malformed_candidate_metadata")
    if any(type(item) is not int or not 1 <= item <= 10**9 for item in value):
        raise CodexSuccessorProposalError("malformed_candidate_metadata")
    if value != sorted(set(value)):
        raise CodexSuccessorProposalError("malformed_candidate_metadata")
    return tuple(value)


def _validated_allowed_paths(value: object) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not 1 <= len(value) <= MAX_ALLOWED_PATHS
        or any(not isinstance(item, str) for item in value)
        or value != sorted(set(value))
        or len({item.casefold() for item in value}) != len(value)
        or any(not _safe_markdown_path(item) for item in value)
    ):
        raise CodexSuccessorProposalError("unsafe_allowed_path")
    return tuple(value)


def _require_candidate_paths(
    paths: tuple[str, ...],
    *,
    repository_root: Path,
    tracked_paths: frozenset[str],
) -> None:
    try:
        repository = repository_root.resolve(strict=True)
    except OSError as exc:
        raise CodexSuccessorProposalError("repository_paths_unavailable") from exc
    for value in paths:
        if value not in tracked_paths:
            raise CodexSuccessorProposalError("unsafe_allowed_path")
        candidate = repository_root.joinpath(*PurePosixPath(value).parts)
        try:
            details = candidate.lstat()
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise CodexSuccessorProposalError("unsafe_allowed_path") from exc
        if (
            not stat.S_ISREG(details.st_mode)
            or _is_link_or_reparse(details)
            or not _path_within(resolved, repository)
        ):
            raise CodexSuccessorProposalError("unsafe_allowed_path")


def _resolve_dependency_facts(
    candidates: tuple[SuccessorCandidate, ...],
    services: CodexSuccessorServices,
) -> dict[int, DependencyFact]:
    relevant = tuple(
        candidate
        for candidate in candidates
        if candidate.candidate_state == "ready" and candidate.queue == "autonomy"
    )
    dependency_numbers = sorted(
        {number for candidate in relevant for number in candidate.depends_on}
    )
    if len(dependency_numbers) > MAX_DEPENDENCY_QUERIES:
        raise CodexSuccessorProposalError("dependency_state_unknown")
    facts: dict[int, DependencyFact] = {}
    for number in dependency_numbers:
        facts[number] = _validate_dependency_payload(
            services.read_dependency(number),
            expected_number=number,
        )
    return facts


def _validate_dependency_payload(
    value: object,
    *,
    expected_number: int,
) -> DependencyFact:
    if not isinstance(value, dict) or set(value) != {
        "number",
        "state",
        "stateReason",
    }:
        raise CodexSuccessorProposalError("dependency_state_unknown")
    state = value.get("state")
    reason = value.get("stateReason")
    if value.get("number") != expected_number or state not in {"OPEN", "CLOSED"}:
        raise CodexSuccessorProposalError("dependency_state_unknown")
    if state == "CLOSED" and reason not in {"COMPLETED", "NOT_PLANNED"}:
        raise CodexSuccessorProposalError("dependency_state_unknown")
    if state == "OPEN" and reason not in {None, "REOPENED"}:
        raise CodexSuccessorProposalError("dependency_state_unknown")
    return DependencyFact(
        issue_number=expected_number,
        state=state,
        state_reason=reason,
    )


def _proposal_fingerprint(
    *,
    verification: VerificationState,
    candidate: SuccessorCandidate,
    dependency_facts: tuple[DependencyFact, ...],
    canonical_serializer: CanonicalSerializer,
    fingerprint_function: FingerprintFunction,
) -> str:
    payload: dict[str, object] = {
        "schema_version": SUCCESSOR_FINGERPRINT_SCHEMA_VERSION,
        "verified_base_sha": verification.base_sha,
        "verification_id": verification.verification_id,
        "candidate": {
            "allowed_paths": list(candidate.allowed_paths),
            "base_branch": candidate.base_branch,
            "candidate_state": candidate.candidate_state,
            "depends_on": list(candidate.depends_on),
            "dependency_facts": [
                {
                    "issue_number": fact.issue_number,
                    "state": fact.state,
                    "state_reason": fact.state_reason,
                }
                for fact in dependency_facts
            ],
            "execution_class": candidate.execution_class,
            "expected_pr_title": candidate.expected_pr_title,
            "issue_number": candidate.issue_number,
            "priority": candidate.priority,
            "queue": candidate.queue,
            "repository": candidate.repository,
            "risk_class": candidate.risk_class,
            "task_id": candidate.task_id,
            "title": candidate.title,
        },
    }
    try:
        canonical = canonical_serializer(payload)
    except Exception as exc:
        raise CodexSuccessorProposalError("serialization_uncertainty") from exc
    if not isinstance(canonical, bytes) or not 1 <= len(canonical) <= MAX_CANDIDATE_BYTES:
        raise CodexSuccessorProposalError("serialization_uncertainty")
    try:
        fingerprint = fingerprint_function(canonical)
    except Exception as exc:
        raise CodexSuccessorProposalError("fingerprint_failure") from exc
    if not isinstance(fingerprint, str) or _FINGERPRINT_PATTERN.fullmatch(
        fingerprint
    ) is None:
        raise CodexSuccessorProposalError("fingerprint_failure")
    return fingerprint


def _successful_result(
    *,
    verification: VerificationState,
    candidate_count: int,
    candidate: SuccessorCandidate,
    fingerprint: str,
) -> dict[str, object]:
    return {
        "schema_version": SUCCESSOR_PROPOSAL_SCHEMA_VERSION,
        "status": "success",
        "category": "successor_proposed",
        "verified_base_sha": verification.base_sha,
        "verification_id": verification.verification_id,
        "candidate_count": candidate_count,
        "selected_issue_number": candidate.issue_number,
        "selected_task_id": candidate.task_id,
        "selected_title": candidate.title,
        "selected_priority": candidate.priority,
        "selected_risk_class": candidate.risk_class,
        "selected_execution_class": candidate.execution_class,
        "selected_allowed_paths": list(candidate.allowed_paths),
        "selected_expected_pr_title": candidate.expected_pr_title,
        "selection_reason": "highest_priority_then_lowest_issue_number",
        "proposal_fingerprint": fingerprint,
        "proposal_ready_for_architecture_review": True,
    }


def _blocked_result(
    category: str,
    *,
    verified_base_sha: str | None = None,
    verification_id: str | None = None,
    candidate_count: int = 0,
) -> dict[str, object]:
    return {
        "schema_version": SUCCESSOR_PROPOSAL_SCHEMA_VERSION,
        "status": "blocked",
        "category": category,
        "verified_base_sha": verified_base_sha,
        "verification_id": verification_id,
        "candidate_count": candidate_count,
        "selected_issue_number": None,
        "selected_task_id": None,
        "selected_title": None,
        "selected_priority": None,
        "selected_risk_class": None,
        "selected_execution_class": None,
        "selected_allowed_paths": [],
        "selected_expected_pr_title": None,
        "selection_reason": None,
        "proposal_fingerprint": None,
        "proposal_ready_for_architecture_review": False,
    }


def _validate_tracked_paths(value: object) -> frozenset[str]:
    if (
        not isinstance(value, tuple)
        or not 1 <= len(value) <= MAX_TRACKED_PATHS
        or any(not isinstance(item, str) or not item for item in value)
        or len(value) != len(set(value))
    ):
        raise CodexSuccessorProposalError("repository_paths_unavailable")
    return frozenset(value)


def _safe_markdown_path(value: str) -> bool:
    if (
        not 1 <= len(value) <= 260
        or value != unicodedata.normalize("NFC", value)
        or "\\" in value
        or ":" in value
        or value.startswith(("/", ".git"))
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        return False
    path = PurePosixPath(value)
    return bool(
        not path.is_absolute()
        and all(part not in {"", ".", "..", ".git"} for part in path.parts)
        and path.suffix.lower() == ".md"
        and value.startswith(("docs/development/", "docs/process/"))
    )


def _safe_public_text(value: object, *, max_length: int) -> bool:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= max_length
        or value != value.strip()
        or value != unicodedata.normalize("NFC", value)
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or re.search(r"(?i)(?:[A-Z]:[\\/]|/home/|/Users/|\\\\)", value)
    ):
        return False
    return not any(pattern.search(value) for pattern in _SENSITIVE_TEXT_PATTERNS)


def _safe_repository_name(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and re.fullmatch(r"[a-z][a-z0-9-]{0,63}", value)
    )


def _valid_verification_id(value: object) -> bool:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        return False
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return False
    return str(parsed) == value.lower()


def _load_json_without_duplicates(value: str) -> object:
    def object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = item
        return result

    def reject_constant(_value: str) -> object:
        raise ValueError("non-finite JSON number")

    return json.loads(
        value,
        object_pairs_hook=object_pairs,
        parse_constant=reject_constant,
    )


def _load_github_json(value: str) -> object:
    try:
        return _load_json_without_duplicates(value)
    except (json.JSONDecodeError, ValueError) as exc:
        raise CodexSuccessorProposalError("malformed_candidate_payload") from exc


def _canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _bounded_process_environment(source: Mapping[str, str]) -> dict[str, str]:
    case_insensitive = os.name == "nt"
    selected: dict[str, str] = {}
    source_items = tuple(source.items())
    for name in _PROCESS_ENVIRONMENT_NAMES:
        match = next(
            (
                (key, value)
                for key, value in source_items
                if key == name or (case_insensitive and key.casefold() == name.casefold())
            ),
            None,
        )
        if match is None:
            continue
        key, value = match
        if _safe_environment_value(value):
            selected[key] = value
    selected.update(
        {
            "GH_PROMPT_DISABLED": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "NO_COLOR": "1",
        }
    )
    return selected


def _safe_environment_value(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value.encode("utf-8")) <= 32_768
        and "\0" not in value
        and all(character in "\t" or ord(character) >= 32 for character in value)
        and all(ord(character) != 127 for character in value)
    )


def _is_link_or_reparse(details: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(details.st_mode) or bool(
        getattr(details, "st_file_attributes", 0) & reparse_flag
    )


def _path_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
