"""Isolated WSL2/Linux Codex worker and shadow-workspace transfer adapter."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
import time
import unicodedata
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Final
from urllib.parse import urlsplit

from phoenix_office.core import (
    CODEX_PILOT_AUTHORIZATION_KINDS,
    CODEX_PILOT_BOUNDED_PYTHON_KIND,
    CODEX_PILOT_DOCS_ONLY_KIND,
    is_safe_codex_pilot_allowed_paths,
)

WSL_CODEX_REQUIRED_VERSION: Final = "0.146.1"
WSL_RUNTIME_PREFIX: Final = PurePosixPath(
    ".local/share/phoenix/diagnostics/task-064-codex-01461"
)
WSL_RUNTIME_DESCRIPTOR: Final = "frozen-runtime.json"
WSL_WORKSPACE_ROOT: Final = PurePosixPath(
    ".local/share/phoenix/task-064-workspaces"
)
WSL_INVOCATION_ROOT: Final = PurePosixPath(
    ".local/share/phoenix/task-064-invocations"
)
CAPABILITY_MARKER_NAME: Final = "codex-workspace-write-marker.md"
CAPABILITY_MARKER_CONTENT: Final = "PHOENIX_CODEX_WORKSPACE_WRITE_PROBE_V1\n"
MAX_COMMAND_OUTPUT_BYTES: Final = 2_000_000
MAX_JSONL_LINES: Final = 10_000
MAX_JSONL_LINE_BYTES: Final = 1_000_000
MAX_SNAPSHOT_BYTES: Final = 128_000_000
MAX_SNAPSHOT_FILES: Final = 50_000
MAX_PATCH_BYTES: Final = 2_000_000
MAX_MARKDOWN_BYTES: Final = 1_000_000
MAX_PROXY_VALUE_BYTES: Final = 4096
LINUX_PATH: Final = "/usr/local/bin:/usr/bin:/bin"
WSL_PROXY_NAMES: Final = (
    ("HTTP_PROXY", True),
    ("HTTPS_PROXY", True),
    ("NO_PROXY", False),
    ("ALL_PROXY", True),
    ("http_proxy", True),
    ("https_proxy", True),
    ("no_proxy", False),
    ("all_proxy", True),
)
_CONTROL_STATE_SUFFIXES: Final = (
    ".sqlite3",
    ".sqlite3-wal",
    ".sqlite3-shm",
    ".sqlite3-journal",
)
_GENERATED_COMPONENTS: Final = {
    ".git",
    ".pytest_cache",
    ".pytest_tmp",
    ".ruff_cache",
    "__pycache__",
}
_WINDOWS_RESERVED_NAMES: Final = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
_SENSITIVE_PATTERNS: Final = (
    re.compile(r"(?i)\b(?:sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9_]{8,})\b"),
    re.compile(r"(?i)\bgithub_pat_[A-Za-z0-9_]{8,}\b"),
    re.compile(r"(?i)\b(?:password|secret|token)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(?:[A-Z]:\\Users\\|/home/|/Users/)[^\s`]+"),
)
_LINUX_INVOCATION_SUPERVISOR: Final = """\
import json
import os
import sys

record_path, invocation_id, *command = sys.argv[1:]
if not command or len(invocation_id) != 32:
    raise SystemExit(70)
pid = os.getpid()
if os.getpgrp() != pid:
    os.setsid()
pgid = os.getpgrp()
if pid != pgid:
    raise SystemExit(71)
with open(f"/proc/{pid}/stat", encoding="ascii") as stream:
    fields = stream.read().rsplit(")", 1)[1].split()
start_ticks = int(fields[19])
payload = json.dumps(
    {
        "invocation_id": invocation_id,
        "pid": pid,
        "pgid": pgid,
        "start_ticks": start_ticks,
    },
    sort_keys=True,
    separators=(",", ":"),
).encode("ascii")
temporary = f"{record_path}.tmp"
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
descriptor = os.open(temporary, flags, 0o600)
try:
    os.write(descriptor, payload)
    os.fsync(descriptor)
finally:
    os.close(descriptor)
os.replace(temporary, record_path)
directory = os.open(os.path.dirname(record_path), os.O_RDONLY | os.O_DIRECTORY)
try:
    os.fsync(directory)
finally:
    os.close(directory)
os.execv(command[0], command)
"""
_LINUX_INVOCATION_CONTROL: Final = """\
import json
import os
import signal
import sys
import time

mode, record_path, expected_id = sys.argv[1:]

def process_stat(pid):
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii") as stream:
            fields = stream.read().rsplit(")", 1)[1].split()
        return int(fields[2]), int(fields[19])
    except (FileNotFoundError, OSError, ValueError, IndexError):
        return None

def group_members(pgid):
    members = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        raise SystemExit(21)
    for entry in entries:
        if not entry.isdigit():
            continue
        observed = process_stat(int(entry))
        if observed is not None and observed[0] == pgid:
            members.append(int(entry))
    return members

try:
    with open(record_path, encoding="ascii") as stream:
        record = json.load(stream)
except FileNotFoundError:
    raise SystemExit(22)
except (OSError, json.JSONDecodeError):
    raise SystemExit(21)
try:
    invocation_id = record["invocation_id"]
    pid = int(record["pid"])
    pgid = int(record["pgid"])
    start_ticks = int(record["start_ticks"])
except (ValueError, KeyError, TypeError):
    raise SystemExit(21)
if invocation_id != expected_id or pid <= 1 or pgid != pid or start_ticks <= 0:
    raise SystemExit(21)

leader = process_stat(pid)
if leader is not None and leader != (pgid, start_ticks):
    raise SystemExit(21)

if mode == "ready":
    raise SystemExit(0 if leader == (pgid, start_ticks) else 20)

if mode == "terminate":
    if group_members(pgid):
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError:
            raise SystemExit(20)
        for _ in range(20):
            if not group_members(pgid):
                break
            time.sleep(0.1)
        if group_members(pgid):
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except OSError:
                raise SystemExit(20)
            for _ in range(30):
                if not group_members(pgid):
                    break
                time.sleep(0.1)
    raise SystemExit(0 if not group_members(pgid) else 20)

if mode == "prove-exited":
    for _ in range(30):
        if not group_members(pgid):
            raise SystemExit(0)
        time.sleep(0.1)
    raise SystemExit(20)

raise SystemExit(21)
"""


@dataclass(frozen=True, slots=True)
class WslGateResult:
    passed: bool
    category: str


@dataclass(frozen=True, slots=True)
class WslCapabilityResult:
    passed: bool
    category: str
    native_workspace: bool = False
    workspace_write: bool = False
    outside_write_blocked: bool = False
    worker_network_blocked: bool = False
    approval_escalation_unavailable: bool = False
    temp_cleanup: bool = False


@dataclass(frozen=True, slots=True)
class WslExecutionResult:
    status: str
    category: str
    usage_tokens: int | None = None
    worker_exit_proved: bool = True


@dataclass(frozen=True, slots=True)
class WslInvocationControl:
    invocation_id: str = field(repr=False)
    directory: PurePosixPath = field(repr=False)
    record_path: PurePosixPath = field(repr=False)


@dataclass(frozen=True, slots=True)
class WslProcessStopResult:
    client_stopped: bool
    target_terminated: bool
    exit_proved: bool
    control_cleaned: bool


def _targeted_stop_confirmed(result: WslProcessStopResult) -> bool:
    return (
        result.client_stopped
        and result.target_terminated
        and result.exit_proved
        and result.control_cleaned
    )


@dataclass(frozen=True, slots=True)
class WslPlatformSpec:
    wsl_executable: Path = field(repr=False)
    wsl_device: int
    wsl_inode: int
    wsl_size: int
    wsl_modified_ns: int
    distro_name: str = field(repr=False)
    linux_home: PurePosixPath = field(repr=False)
    linux_user: str = field(repr=False)
    native_filesystem: str


@dataclass(frozen=True, slots=True)
class WslCodexRuntimeSpec:
    platform: WslPlatformSpec = field(repr=False)
    executable: PurePosixPath = field(repr=False)
    executable_device: int
    executable_inode: int
    executable_size: int
    executable_modified_seconds: int
    executable_sha256: str = field(repr=False)
    environment: tuple[tuple[str, str], ...] = field(repr=False)
    version: str = WSL_CODEX_REQUIRED_VERSION
    kind: str = "native_linux_exe"


@dataclass(frozen=True, slots=True)
class WindowsSnapshot:
    archive: bytes = field(repr=False)
    digest: str
    tracked_paths: tuple[str, ...]
    pilot_kind: str
    source_state_digest: str = field(default="", repr=False)


@dataclass(frozen=True, slots=True)
class ShadowPatch:
    payload: bytes = field(repr=False)
    changed_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WslTransferEvidence:
    shadow_workspace_created: bool = False
    shadow_git_baseline_created: bool = False
    windows_worktree_unchanged_during_worker: bool = False
    changed_paths_validated_before_apply: bool = False
    patch_exported: bool = False
    patch_applied: bool = False
    temp_cleanup: bool = False


HostRun = Callable[..., subprocess.CompletedProcess[object]]
HostPopen = Callable[..., subprocess.Popen[str]]
WslExecutableResolver = Callable[[], Path | None]
InvocationIdFactory = Callable[[], str]


class WslCodexWorker:
    """Windows control-plane adapter for one frozen WSL2 Codex worker."""

    def __init__(
        self,
        canonical_repository: Path,
        *,
        wsl_executable_resolver: WslExecutableResolver | None = None,
        host_run: HostRun | None = None,
        host_popen: HostPopen | None = None,
        invocation_id_factory: InvocationIdFactory | None = None,
    ) -> None:
        self._canonical_repository = Path(canonical_repository)
        self._wsl_executable_resolver = (
            wsl_executable_resolver or _resolve_wsl_executable
        )
        self._host_run = host_run or subprocess.run
        self._host_popen = host_popen or subprocess.Popen
        self._invocation_id_factory = invocation_id_factory or (lambda: uuid.uuid4().hex)
        self._resolution_attempted = False
        self._runtime_spec: WslCodexRuntimeSpec | None = None
        self._runtime_result: WslGateResult | None = None
        self._authentication_result: WslGateResult | None = None
        self._transport_result: WslGateResult | None = None
        self._capability_result: WslCapabilityResult | None = None
        self._last_transfer_evidence = WslTransferEvidence()

    @property
    def backend_kind(self) -> str:
        return "wsl2_linux"

    @property
    def selected_version(self) -> str | None:
        spec = self._runtime_spec
        return spec.version if spec is not None else None

    @property
    def runtime_kind(self) -> str | None:
        spec = self._runtime_spec
        return spec.kind if spec is not None else None

    @property
    def runtime_frozen(self) -> bool:
        return self._runtime_spec is not None

    @property
    def transport_result(self) -> WslGateResult | None:
        return self._transport_result

    @property
    def last_transfer_evidence(self) -> WslTransferEvidence:
        return self._last_transfer_evidence

    def runtime_gate(self) -> WslGateResult:
        if self._runtime_result is not None:
            return self._runtime_result
        if self._resolution_attempted:
            return WslGateResult(False, "wsl_codex_qualified_runtime_unavailable")
        self._resolution_attempted = True
        platform_result, platform = self._discover_platform()
        if not platform_result.passed or platform is None:
            self._runtime_result = platform_result
            return platform_result
        runtime = self._qualify_runtime(platform)
        if runtime is None:
            result = WslGateResult(
                False,
                "wsl_codex_qualified_runtime_unavailable",
            )
            self._runtime_result = result
            return result
        self._runtime_spec = runtime
        result = WslGateResult(True, "wsl_codex_runtime_ready")
        self._runtime_result = result
        return result

    def authentication_gate(self) -> WslGateResult:
        if self._authentication_result is not None:
            return self._authentication_result
        runtime = self.runtime_gate()
        if not runtime.passed:
            self._authentication_result = runtime
            return runtime
        spec = self._runtime_spec
        if spec is None or not self._runtime_is_current(spec):
            result = WslGateResult(
                False,
                "wsl_codex_qualified_runtime_unavailable",
            )
        else:
            completed = self._run_codex_bounded(
                spec,
                ("login", "status"),
                timeout=30,
            )
            result = WslGateResult(
                completed is not None and completed.returncode == 0,
                (
                    "wsl_codex_authenticated"
                    if completed is not None and completed.returncode == 0
                    else "wsl_codex_authentication_unavailable"
                ),
            )
        self._authentication_result = result
        return result

    def transport_gate(self, timeout_seconds: int) -> WslGateResult:
        if self._transport_result is not None:
            return self._transport_result
        authentication = self.authentication_gate()
        if not authentication.passed:
            self._transport_result = authentication
            return authentication
        workspace = self._create_native_workspace("transport")
        if workspace is None:
            result = WslGateResult(False, "wsl_native_workspace_unavailable")
            self._transport_result = result
            return result
        cleanup = False
        execution: WslExecutionResult | None = None
        try:
            if not self._initialize_shadow_git(
                workspace,
                "Synthetic Phoenix WSL transport probe.\n",
            ):
                result = WslGateResult(False, "wsl_transport_setup_failed")
            else:
                sentinel = "PHOENIX_TASK064_WSL_TRANSPORT_OK"
                prompt = (
                    "Do not run commands or use tools. Respond with exactly "
                    f"{sentinel} and nothing else."
                )
                execution, messages = self._run_model(
                    workspace=workspace,
                    prompt=prompt,
                    timeout_seconds=min(timeout_seconds, 120),
                    on_started=lambda: None,
                )
                if not execution.worker_exit_proved:
                    result = WslGateResult(False, "wsl_process_control_uncertain")
                else:
                    status = self._run_wsl_text(
                        self._require_platform(),
                        (
                            "/usr/bin/git",
                            "-C",
                            workspace,
                            "status",
                            "--porcelain=v1",
                        ),
                        timeout=30,
                    )
                    passed = (
                        execution.status == "succeeded"
                        and "".join(messages).strip() == sentinel
                        and status is not None
                        and status.returncode == 0
                        and not status.stdout.strip()
                    )
                    result = WslGateResult(
                        passed,
                        "wsl_codex_transport_ready"
                        if passed
                        else "wsl_codex_transport_unavailable",
                    )
        finally:
            if execution is None or execution.worker_exit_proved:
                cleanup = self._cleanup_native_workspace(workspace)
        if execution is not None and not execution.worker_exit_proved:
            result = WslGateResult(False, "wsl_process_control_uncertain")
        if not cleanup and result.passed:
            result = WslGateResult(False, "wsl_temp_cleanup_failed")
        self._transport_result = result
        return result

    def capability_probe(self, timeout_seconds: int) -> WslCapabilityResult:
        if self._capability_result is not None:
            return self._capability_result
        transport = self.transport_gate(timeout_seconds)
        if not transport.passed:
            result = WslCapabilityResult(False, transport.category)
            self._capability_result = result
            return result
        marker_workspace = self._create_native_workspace("capability")
        if marker_workspace is None:
            result = WslCapabilityResult(
                False,
                "wsl_workspace_write_capability_unproved",
            )
            self._capability_result = result
            return result
        cleanup = False
        marker_exit_proved = True
        try:
            marker_passed, marker_exit_proved = self._model_marker_probe(
                marker_workspace,
                min(timeout_seconds, 180),
            )
        finally:
            if marker_exit_proved:
                cleanup = self._cleanup_native_workspace(marker_workspace)
        if not marker_exit_proved:
            result = WslCapabilityResult(
                False,
                "wsl_process_control_uncertain",
                native_workspace=True,
                temp_cleanup=False,
            )
            self._capability_result = result
            return result
        if not marker_passed or not cleanup:
            result = WslCapabilityResult(
                False,
                "wsl_workspace_write_capability_unproved",
                native_workspace=True,
                workspace_write=marker_passed,
                temp_cleanup=cleanup,
            )
            self._capability_result = result
            return result
        security_workspace = self._create_native_workspace("security")
        if security_workspace is None:
            result = WslCapabilityResult(
                False,
                "wsl_workspace_write_capability_unproved",
            )
            self._capability_result = result
            return result
        cleanup = False
        try:
            direct_write = self._direct_marker_probe(security_workspace)
            outside_blocked = direct_write and self._outside_write_probe(
                security_workspace
            )
            network_blocked = direct_write and self._network_probe(security_workspace)
            approval_unavailable = outside_blocked and network_blocked
        finally:
            cleanup = self._cleanup_native_workspace(security_workspace)
        passed = (
            direct_write
            and outside_blocked
            and network_blocked
            and approval_unavailable
            and cleanup
        )
        result = WslCapabilityResult(
            passed,
            "wsl_workspace_write_capability_proved"
            if passed
            else "wsl_workspace_write_capability_unproved",
            native_workspace=True,
            workspace_write=direct_write,
            outside_write_blocked=outside_blocked,
            worker_network_blocked=network_blocked,
            approval_escalation_unavailable=approval_unavailable,
            temp_cleanup=cleanup,
        )
        self._capability_result = result
        return result

    def invoke_codex(
        self,
        *,
        windows_worktree: Path,
        base_commit_sha: str,
        allowed_paths: tuple[str, ...],
        pilot_kind: str,
        prompt: str,
        timeout_seconds: int,
        on_started: Callable[[], None],
    ) -> WslExecutionResult:
        capability = self._capability_result
        if capability is None or not capability.passed:
            return WslExecutionResult("failed", "wsl_backend_not_qualified")
        spec = self._runtime_spec
        if spec is None or not self._runtime_is_current(spec):
            return WslExecutionResult(
                "failed",
                "wsl_codex_qualified_runtime_unavailable",
            )
        try:
            canonical = self._canonical_repository.resolve(strict=True)
            worktree = Path(windows_worktree).resolve(strict=True)
        except (OSError, RuntimeError):
            return WslExecutionResult("failed", "windows_task_worktree_invalid")
        if worktree == canonical:
            return WslExecutionResult("failed", "canonical_worktree_rejected")
        try:
            snapshot = build_windows_snapshot(
                worktree,
                base_commit_sha,
                allowed_paths,
                pilot_kind=pilot_kind,
            )
        except (OSError, ValueError, subprocess.SubprocessError):
            return WslExecutionResult("failed", "windows_snapshot_rejected")
        shadow = self._create_native_workspace("shadow")
        if shadow is None:
            return WslExecutionResult("failed", "wsl_shadow_workspace_unavailable")
        evidence = WslTransferEvidence(shadow_workspace_created=True)
        result = WslExecutionResult("failed", "wsl_shadow_transfer_failed")
        execution: WslExecutionResult | None = None
        try:
            if not self._extract_snapshot(
                shadow,
                snapshot.archive,
                snapshot.tracked_paths,
            ):
                result = WslExecutionResult("failed", "wsl_snapshot_extract_failed")
            elif not self._initialize_snapshot_git(shadow):
                result = WslExecutionResult("failed", "wsl_git_baseline_invalid")
            else:
                evidence = _replace_transfer_evidence(
                    evidence,
                    shadow_git_baseline_created=True,
                )
                baseline = self._shadow_git_control_state(shadow)
                if baseline is None:
                    result = WslExecutionResult("failed", "wsl_git_baseline_invalid")
                else:
                    execution, _messages = self._run_model(
                        workspace=shadow,
                        prompt=prompt,
                        timeout_seconds=timeout_seconds,
                        on_started=on_started,
                    )
                    if not execution.worker_exit_proved:
                        result = execution
                    elif not windows_snapshot_matches(
                        worktree,
                        base_commit_sha,
                        snapshot,
                    ):
                        result = WslExecutionResult(
                            "failed",
                            "windows_worktree_changed_during_wsl_run",
                            execution.usage_tokens,
                        )
                    else:
                        evidence = _replace_transfer_evidence(
                            evidence,
                            windows_worktree_unchanged_during_worker=True,
                        )
                        result = execution
                        if execution.status == "succeeded":
                            patch = self._validated_shadow_patch(
                                shadow,
                                snapshot.tracked_paths,
                                allowed_paths,
                                baseline,
                                pilot_kind=snapshot.pilot_kind,
                            )
                            if patch is None:
                                result = WslExecutionResult(
                                    "failed",
                                    "wsl_shadow_diff_rejected",
                                    execution.usage_tokens,
                                )
                            else:
                                evidence = _replace_transfer_evidence(
                                    evidence,
                                    changed_paths_validated_before_apply=True,
                                    patch_exported=True,
                                )
                                if not apply_shadow_patch(worktree, patch):
                                    result = WslExecutionResult(
                                        "failed",
                                        "windows_patch_apply_failed",
                                        execution.usage_tokens,
                                    )
                                else:
                                    evidence = _replace_transfer_evidence(
                                        evidence,
                                        patch_applied=True,
                                    )
                                    result = WslExecutionResult(
                                        "succeeded",
                                        "wsl_codex_completed",
                                        execution.usage_tokens,
                                    )
        finally:
            cleanup = False
            if execution is None or execution.worker_exit_proved:
                cleanup = self._cleanup_native_workspace(shadow)
            evidence = _replace_transfer_evidence(evidence, temp_cleanup=cleanup)
            self._last_transfer_evidence = evidence
        if execution is not None and not execution.worker_exit_proved:
            return execution
        if not cleanup:
            return WslExecutionResult(
                "failed",
                "wsl_temp_cleanup_failed",
                result.usage_tokens,
            )
        return result

    def _discover_platform(
        self,
    ) -> tuple[WslGateResult, WslPlatformSpec | None]:
        candidate = self._wsl_executable_resolver()
        identity = _windows_executable_identity(candidate)
        if identity is None:
            return WslGateResult(False, "wsl_unavailable"), None
        wsl_path, device, inode, size, modified_ns = identity
        default = self._run_host_text(
            (str(wsl_path), "--exec", "/usr/bin/printenv", "WSL_DISTRO_NAME"),
            timeout=30,
        )
        if default is None or default.returncode != 0:
            return WslGateResult(False, "wsl_default_distro_unavailable"), None
        distro = _bounded_distro_name(default.stdout)
        if distro is None:
            return WslGateResult(False, "wsl_default_distro_unavailable"), None
        base = (str(wsl_path), "--distribution", distro, "--exec")
        kernel = self._run_host_text((*base, "/usr/bin/uname", "-r"), timeout=30)
        if (
            kernel is None
            or kernel.returncode != 0
            or not _is_wsl2_kernel(kernel.stdout)
        ):
            return WslGateResult(False, "wsl_not_version_2"), None
        home_result = self._run_host_text(
            (*base, "/usr/bin/printenv", "HOME"),
            timeout=30,
        )
        user_result = self._run_host_text(
            (*base, "/usr/bin/id", "-un"),
            timeout=30,
        )
        if home_result is None or user_result is None:
            return WslGateResult(False, "wsl_native_home_unavailable"), None
        home_text = home_result.stdout.strip()
        user = _bounded_linux_user(user_result.stdout)
        if (
            home_result.returncode != 0
            or user_result.returncode != 0
            or user is None
            or not _safe_native_linux_path(home_text)
        ):
            return WslGateResult(False, "wsl_native_home_unavailable"), None
        fs_result = self._run_host_text(
            (*base, "/usr/bin/stat", "-f", "-c", "%T", home_text),
            timeout=30,
        )
        filesystem = fs_result.stdout.strip() if fs_result is not None else ""
        if (
            fs_result is None
            or fs_result.returncode != 0
            or not _native_linux_filesystem(filesystem)
        ):
            return WslGateResult(False, "wsl_native_home_unavailable"), None
        platform = WslPlatformSpec(
            wsl_path,
            device,
            inode,
            size,
            modified_ns,
            distro,
            PurePosixPath(home_text),
            user,
            filesystem,
        )
        return WslGateResult(True, "wsl2_ready"), platform

    def _qualify_runtime(
        self,
        platform: WslPlatformSpec,
    ) -> WslCodexRuntimeSpec | None:
        prefix = platform.linux_home / WSL_RUNTIME_PREFIX
        if not _safe_native_linux_path(str(prefix)):
            return None
        descriptor_result = self._run_wsl_text(
            platform,
            ("/usr/bin/cat", str(prefix / WSL_RUNTIME_DESCRIPTOR)),
            timeout=30,
        )
        manifest_result = self._run_wsl_text(
            platform,
            (
                "/usr/bin/cat",
                str(prefix / "node_modules/@openai/codex/package.json"),
            ),
            timeout=30,
        )
        lock_result = self._run_wsl_text(
            platform,
            ("/usr/bin/cat", str(prefix / "package-lock.json")),
            timeout=30,
        )
        if any(
            result is None or result.returncode != 0
            for result in (descriptor_result, manifest_result, lock_result)
        ):
            return None
        try:
            descriptor = json.loads(descriptor_result.stdout)
            manifest = json.loads(manifest_result.stdout)
            lock = json.loads(lock_result.stdout)
        except (AttributeError, json.JSONDecodeError):
            return None
        if not _official_pinned_package(manifest, lock):
            return None
        relative = _pinned_runtime_relative_path(descriptor)
        if relative is None:
            return None
        executable = prefix / relative
        expected_sha = descriptor.get("sha256")
        if not isinstance(expected_sha, str) or re.fullmatch(
            r"[0-9a-f]{64}", expected_sha
        ) is None:
            return None
        if not self._linux_regular_executable(platform, executable):
            return None
        realpath = self._run_wsl_text(
            platform,
            ("/usr/bin/readlink", "-f", str(executable)),
            timeout=30,
        )
        if (
            realpath is None
            or realpath.returncode != 0
            or realpath.stdout.strip() != str(executable)
        ):
            return None
        stat_result = self._run_wsl_text(
            platform,
            ("/usr/bin/stat", "-c", "%d:%i:%s:%Y", str(executable)),
            timeout=30,
        )
        sha_result = self._run_wsl_text(
            platform,
            ("/usr/bin/sha256sum", str(executable)),
            timeout=60,
        )
        elf_result = self._run_wsl_text(
            platform,
            ("/usr/bin/od", "-An", "-tx1", "-N20", str(executable)),
            timeout=30,
        )
        arch_result = self._run_wsl_text(
            platform,
            ("/usr/bin/uname", "-m"),
            timeout=30,
        )
        identity = _parse_linux_identity(stat_result, sha_result)
        if identity is None or identity[4] != expected_sha:
            return None
        if not _compatible_elf(elf_result, arch_result):
            return None
        tmpdir = prefix / "tmp"
        made_tmp = self._run_wsl_text(
            platform,
            ("/usr/bin/mkdir", "-p", str(tmpdir)),
            timeout=30,
        )
        secured_tmp = self._run_wsl_text(
            platform,
            ("/usr/bin/chmod", "700", str(tmpdir)),
            timeout=30,
        )
        if any(
            result is None or result.returncode != 0
            for result in (made_tmp, secured_tmp)
        ):
            return None
        environment = self._linux_codex_environment(platform, tmpdir)
        if environment is None:
            return None
        spec = WslCodexRuntimeSpec(
            platform,
            executable,
            identity[0],
            identity[1],
            identity[2],
            identity[3],
            identity[4],
            environment,
        )
        version = self._run_codex_bounded(spec, ("--version",), timeout=30)
        if (
            version is None
            or version.returncode != 0
            or version.stdout.strip() != f"codex-cli {WSL_CODEX_REQUIRED_VERSION}"
        ):
            return None
        return spec

    def _linux_regular_executable(
        self,
        platform: WslPlatformSpec,
        executable: PurePosixPath,
    ) -> bool:
        path = str(executable)
        regular = self._run_wsl_text(
            platform,
            ("/usr/bin/test", "-f", path),
            timeout=30,
        )
        executable_test = self._run_wsl_text(
            platform,
            ("/usr/bin/test", "-x", path),
            timeout=30,
        )
        symlink = self._run_wsl_text(
            platform,
            ("/usr/bin/test", "-L", path),
            timeout=30,
        )
        metadata = self._run_wsl_text(
            platform,
            ("/usr/bin/stat", "-c", "%F:%h", path),
            timeout=30,
        )
        return (
            regular is not None
            and regular.returncode == 0
            and executable_test is not None
            and executable_test.returncode == 0
            and symlink is not None
            and symlink.returncode != 0
            and metadata is not None
            and metadata.returncode == 0
            and metadata.stdout.strip() == "regular file:1"
        )

    def _runtime_is_current(self, spec: WslCodexRuntimeSpec) -> bool:
        platform = spec.platform
        try:
            current = platform.wsl_executable.stat()
        except OSError:
            return False
        if platform.wsl_executable.is_symlink() or not stat.S_ISREG(current.st_mode):
            return False
        if (
            current.st_dev,
            current.st_ino,
            current.st_size,
            current.st_mtime_ns,
        ) != (
            platform.wsl_device,
            platform.wsl_inode,
            platform.wsl_size,
            platform.wsl_modified_ns,
        ):
            return False
        if not self._linux_regular_executable(platform, spec.executable):
            return False
        realpath = self._run_wsl_text(
            platform,
            ("/usr/bin/readlink", "-f", str(spec.executable)),
            timeout=30,
        )
        stat_result = self._run_wsl_text(
            platform,
            ("/usr/bin/stat", "-c", "%d:%i:%s:%Y", str(spec.executable)),
            timeout=30,
        )
        sha_result = self._run_wsl_text(
            platform,
            ("/usr/bin/sha256sum", str(spec.executable)),
            timeout=60,
        )
        identity = _parse_linux_identity(stat_result, sha_result)
        return (
            realpath is not None
            and realpath.returncode == 0
            and realpath.stdout.strip() == str(spec.executable)
            and identity
            == (
                spec.executable_device,
                spec.executable_inode,
                spec.executable_size,
                spec.executable_modified_seconds,
                spec.executable_sha256,
            )
        )

    def _linux_codex_environment(
        self,
        platform: WslPlatformSpec,
        tmpdir: PurePosixPath,
    ) -> tuple[tuple[str, str], ...] | None:
        values: list[tuple[str, str]] = [
            ("HOME", str(platform.linux_home)),
            ("USER", platform.linux_user),
            ("LOGNAME", platform.linux_user),
            ("SHELL", "/bin/bash"),
            ("PATH", LINUX_PATH),
            ("LANG", "C.UTF-8"),
            ("LC_ALL", "C.UTF-8"),
            ("TERM", "dumb"),
            ("TMPDIR", str(tmpdir)),
        ]
        for name, requires_url in WSL_PROXY_NAMES:
            observed = self._run_wsl_text(
                platform,
                ("/usr/bin/printenv", name),
                timeout=15,
            )
            if observed is None:
                return None
            if observed.returncode != 0:
                continue
            value = observed.stdout.rstrip("\r\n")
            if not _valid_proxy_value(value, requires_url=requires_url):
                return None
            values.append((name, value))
        return tuple(values)

    def _run_codex_bounded(
        self,
        spec: WslCodexRuntimeSpec,
        arguments: tuple[str, ...],
        *,
        timeout: int,
    ) -> subprocess.CompletedProcess[str] | None:
        if arguments != ("--version",) and not self._runtime_is_current(spec):
            return None
        return self._run_wsl_text(
            spec.platform,
            (
                "/usr/bin/env",
                "-i",
                *_environment_assignments(spec.environment),
                str(spec.executable),
                *arguments,
            ),
            timeout=timeout,
        )

    def _run_model(
        self,
        *,
        workspace: str,
        prompt: str,
        timeout_seconds: int,
        on_started: Callable[[], None],
    ) -> tuple[WslExecutionResult, tuple[str, ...]]:
        spec = self._runtime_spec
        if spec is None or not self._runtime_is_current(spec):
            return (
                WslExecutionResult(
                    "failed",
                    "wsl_codex_qualified_runtime_unavailable",
                ),
                (),
            )
        timeout_value = max(1, int(timeout_seconds))
        control = self._prepare_invocation_control(spec.platform)
        if control is None:
            return WslExecutionResult("failed", "wsl_codex_launch_failed"), ()
        codex_argv = (
            "/usr/bin/timeout",
            "--signal=TERM",
            "--kill-after=5s",
            f"{timeout_value}s",
            "/usr/bin/env",
            "-i",
            *_environment_assignments(spec.environment),
            str(spec.executable),
            "--ask-for-approval",
            "never",
            "exec",
            "--sandbox",
            "workspace-write",
            "--ephemeral",
            "--json",
            "--ignore-user-config",
            "--ignore-rules",
            "--strict-config",
            "--cd",
            workspace,
            "-c",
            "sandbox_workspace_write.network_access=false",
            "-c",
            'web_search="disabled"',
            "--color",
            "never",
            "-",
        )
        linux_argv = self._supervised_linux_argv(control, codex_argv)
        argv = self._wsl_argv(spec.platform, linux_argv)
        popen_kwargs: dict[str, object] = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "shell": False,
            "env": _sanitized_wsl_host_environment(),
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            process = self._host_popen(list(argv), **popen_kwargs)
        except KeyboardInterrupt:
            return (
                WslExecutionResult(
                    "failed",
                    "wsl_process_control_uncertain",
                    worker_exit_proved=False,
                ),
                (),
            )
        except (OSError, ValueError):
            self._cleanup_invocation_control(control)
            return WslExecutionResult("failed", "wsl_codex_launch_failed"), ()
        try:
            ready = self._await_invocation_ready(control)
        except KeyboardInterrupt:
            stopped = self._stop_targeted_linux_invocation(process, control)
            if _targeted_stop_confirmed(stopped):
                return WslExecutionResult("cancelled", "wsl_codex_cancelled"), ()
            return (
                WslExecutionResult(
                    "failed",
                    "wsl_process_control_uncertain",
                    worker_exit_proved=False,
                ),
                (),
            )
        if not ready:
            stopped = self._stop_targeted_linux_invocation(process, control)
            if not _targeted_stop_confirmed(stopped):
                return (
                    WslExecutionResult(
                        "failed",
                        "wsl_process_control_uncertain",
                        worker_exit_proved=False,
                    ),
                    (),
                )
            return WslExecutionResult("failed", "wsl_codex_launch_failed"), ()
        try:
            on_started()
        except KeyboardInterrupt:
            stopped = self._stop_targeted_linux_invocation(process, control)
            if _targeted_stop_confirmed(stopped):
                return WslExecutionResult("cancelled", "wsl_codex_cancelled"), ()
            return (
                WslExecutionResult(
                    "failed",
                    "wsl_process_control_uncertain",
                    worker_exit_proved=False,
                ),
                (),
            )
        except Exception:
            stopped = self._stop_targeted_linux_invocation(process, control)
            if _targeted_stop_confirmed(stopped):
                return (
                    WslExecutionResult(
                        "failed",
                        "invocation_start_audit_failed",
                    ),
                    (),
                )
            return (
                WslExecutionResult(
                    "failed",
                    "wsl_process_control_uncertain",
                    worker_exit_proved=False,
                ),
                (),
            )
        try:
            stdout, stderr = process.communicate(
                prompt,
                timeout=timeout_value + 15,
            )
        except subprocess.TimeoutExpired:
            stopped = self._stop_targeted_linux_invocation(process, control)
            if _targeted_stop_confirmed(stopped):
                return WslExecutionResult("timed_out", "wsl_codex_timed_out"), ()
            return (
                WslExecutionResult(
                    "failed",
                    "wsl_process_control_uncertain",
                    worker_exit_proved=False,
                ),
                (),
            )
        except KeyboardInterrupt:
            stopped = self._stop_targeted_linux_invocation(process, control)
            if _targeted_stop_confirmed(stopped):
                return WslExecutionResult("cancelled", "wsl_codex_cancelled"), ()
            return (
                WslExecutionResult(
                    "failed",
                    "wsl_process_control_uncertain",
                    worker_exit_proved=False,
                ),
                (),
            )
        except (BrokenPipeError, OSError):
            stopped = self._stop_targeted_linux_invocation(process, control)
            if _targeted_stop_confirmed(stopped):
                return WslExecutionResult("failed", "wsl_codex_stream_failed"), ()
            return (
                WslExecutionResult(
                    "failed",
                    "wsl_process_control_uncertain",
                    worker_exit_proved=False,
                ),
                (),
            )
        try:
            exit_proved = self._prove_linux_invocation_exit(control)
        except KeyboardInterrupt:
            stopped = self._stop_targeted_linux_invocation(process, control)
            if _targeted_stop_confirmed(stopped):
                return WslExecutionResult("cancelled", "wsl_codex_cancelled"), ()
            return (
                WslExecutionResult(
                    "failed",
                    "wsl_process_control_uncertain",
                    worker_exit_proved=False,
                ),
                (),
            )
        if not exit_proved:
            return (
                WslExecutionResult(
                    "failed",
                    "wsl_process_control_uncertain",
                    worker_exit_proved=False,
                ),
                (),
            )
        try:
            control_cleaned = self._cleanup_invocation_control(control)
        except KeyboardInterrupt:
            return WslExecutionResult("cancelled", "wsl_codex_cancelled"), ()
        if not control_cleaned:
            return (
                WslExecutionResult(
                    "failed",
                    "wsl_invocation_control_cleanup_failed",
                ),
                (),
            )
        if len(stdout.encode("utf-8")) > MAX_COMMAND_OUTPUT_BYTES:
            return WslExecutionResult("failed", "wsl_codex_output_too_large"), ()
        if len(stderr.encode("utf-8")) > MAX_COMMAND_OUTPUT_BYTES:
            return WslExecutionResult("failed", "wsl_codex_output_too_large"), ()
        parsed = _parse_codex_jsonl(stdout)
        diagnostic = _bounded_codex_failure(stderr)
        if process.returncode == 124:
            return WslExecutionResult("timed_out", "wsl_codex_timed_out"), ()
        if process.returncode != 0:
            return (
                WslExecutionResult(
                    "failed",
                    parsed["failure_category"]
                    or diagnostic
                    or "wsl_codex_nonzero_exit",
                    parsed["usage_tokens"],
                ),
                tuple(parsed["messages"]),
            )
        if parsed["fatal"] or not parsed["turn_completed"]:
            return (
                WslExecutionResult(
                    "failed",
                    parsed["failure_category"]
                    or diagnostic
                    or "wsl_codex_structured_failure",
                    parsed["usage_tokens"],
                ),
                tuple(parsed["messages"]),
            )
        return (
            WslExecutionResult(
                "succeeded",
                "wsl_codex_completed",
                parsed["usage_tokens"],
            ),
            tuple(parsed["messages"]),
        )

    def _prepare_invocation_control(
        self,
        platform: WslPlatformSpec,
    ) -> WslInvocationControl | None:
        invocation_id = self._invocation_id_factory()
        if not isinstance(invocation_id, str) or re.fullmatch(
            r"[0-9a-f]{32}",
            invocation_id,
        ) is None:
            return None
        root = platform.linux_home / WSL_INVOCATION_ROOT
        directory = root / invocation_id
        if not _safe_native_linux_path(str(directory)):
            return None
        commands = (
            ("/usr/bin/mkdir", "-p", str(root)),
            ("/usr/bin/chmod", "700", str(root)),
            ("/usr/bin/mkdir", "--mode=700", str(directory)),
        )
        for command in commands:
            completed = self._run_wsl_text(platform, command, timeout=30)
            if completed is None or completed.returncode != 0:
                return None
        return WslInvocationControl(
            invocation_id,
            directory,
            directory / "invocation.json",
        )

    @staticmethod
    def _supervised_linux_argv(
        control: WslInvocationControl,
        command: tuple[str, ...],
    ) -> tuple[str, ...]:
        return (
            "/usr/bin/env",
            "-i",
            "PATH=/usr/bin:/bin",
            "LANG=C.UTF-8",
            "LC_ALL=C.UTF-8",
            "/usr/bin/python3",
            "-c",
            _LINUX_INVOCATION_SUPERVISOR,
            str(control.record_path),
            control.invocation_id,
            *command,
        )

    def _await_invocation_ready(
        self,
        control: WslInvocationControl,
    ) -> bool:
        for _ in range(30):
            completed = self._run_invocation_control("ready", control)
            if completed is not None and completed.returncode == 0:
                return True
            if completed is not None and completed.returncode != 22:
                return False
            time.sleep(0.1)
        return False

    def _run_invocation_control(
        self,
        mode: str,
        control: WslInvocationControl,
    ) -> subprocess.CompletedProcess[str] | None:
        if mode not in {"ready", "terminate", "prove-exited"}:
            return None
        return self._run_wsl_text(
            self._require_platform(),
            (
                "/usr/bin/env",
                "-i",
                "PATH=/usr/bin:/bin",
                "LANG=C.UTF-8",
                "LC_ALL=C.UTF-8",
                "/usr/bin/python3",
                "-c",
                _LINUX_INVOCATION_CONTROL,
                mode,
                str(control.record_path),
                control.invocation_id,
            ),
            timeout=15,
        )

    def _terminate_linux_invocation(
        self,
        control: WslInvocationControl,
    ) -> bool:
        completed = self._run_invocation_control("terminate", control)
        return completed is not None and completed.returncode == 0

    def _prove_linux_invocation_exit(
        self,
        control: WslInvocationControl,
    ) -> bool:
        completed = self._run_invocation_control("prove-exited", control)
        return completed is not None and completed.returncode == 0

    def _stop_targeted_linux_invocation(
        self,
        process: subprocess.Popen[str],
        control: WslInvocationControl,
    ) -> WslProcessStopResult:
        client_stopped = False
        target_terminated = False
        exit_proved = False
        control_cleaned = False
        try:
            client_stopped = _terminate_process(process)
            target_terminated = self._terminate_linux_invocation(control)
            exit_proved = target_terminated and self._prove_linux_invocation_exit(
                control
            )
            if not client_stopped and exit_proved:
                client_stopped = _terminate_process(process)
            control_cleaned = exit_proved and self._cleanup_invocation_control(control)
        except KeyboardInterrupt:
            pass
        return WslProcessStopResult(
            client_stopped,
            target_terminated,
            exit_proved,
            control_cleaned,
        )

    def _cleanup_invocation_control(
        self,
        control: WslInvocationControl,
    ) -> bool:
        platform = self._require_platform()
        root = str(platform.linux_home / WSL_INVOCATION_ROOT)
        directory = str(control.directory)
        if not _path_within_posix(directory, root):
            return False
        removed = self._run_wsl_text(
            platform,
            ("/usr/bin/rm", "-rf", "--", directory),
            timeout=30,
        )
        exists = self._run_wsl_text(
            platform,
            ("/usr/bin/test", "-e", directory),
            timeout=30,
        )
        return (
            removed is not None
            and removed.returncode == 0
            and exists is not None
            and exists.returncode != 0
        )

    def _model_marker_probe(
        self,
        workspace: str,
        timeout_seconds: int,
    ) -> tuple[bool, bool]:
        if not self._initialize_shadow_git(
            workspace,
            "Synthetic Phoenix Codex workspace-write probe.\n",
        ):
            return False, True
        prompt = (
            f"Create exactly one file named {CAPABILITY_MARKER_NAME} in the current "
            "repository. Its exact UTF-8 content must be "
            f"{CAPABILITY_MARKER_CONTENT.strip()!r} followed by one newline. "
            "Do not modify any other file and do not run network commands."
        )
        execution, _messages = self._run_model(
            workspace=workspace,
            prompt=prompt,
            timeout_seconds=timeout_seconds,
            on_started=lambda: None,
        )
        if execution.status != "succeeded":
            return False, execution.worker_exit_proved
        marker = self._run_wsl_bytes(
            self._require_platform(),
            ("/usr/bin/cat", f"{workspace}/{CAPABILITY_MARKER_NAME}"),
            timeout=30,
        )
        status_result = self._run_wsl_text(
            self._require_platform(),
            (
                "/usr/bin/git",
                "-C",
                workspace,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ),
            timeout=30,
        )
        return (
            marker is not None
            and marker.returncode == 0
            and marker.stdout == CAPABILITY_MARKER_CONTENT.encode("utf-8")
            and status_result is not None
            and status_result.returncode == 0
            and status_result.stdout.strip() == f"?? {CAPABILITY_MARKER_NAME}",
            True,
        )

    def _direct_marker_probe(self, workspace: str) -> bool:
        platform = self._require_platform()
        codex_home = f"{workspace}/.direct-codex-home"
        setup = self._run_wsl_text(
            platform,
            ("/usr/bin/mkdir", "-p", codex_home),
            timeout=30,
        )
        if setup is None or setup.returncode != 0:
            return False
        environment = self._direct_environment(codex_home)
        marker = "direct-sandbox-marker.txt"
        command = (
            "/usr/bin/python3",
            "-c",
            (
                "from pathlib import Path; "
                f"Path({marker!r}).write_text('DIRECT_OK\\n', encoding='utf-8')"
            ),
        )
        completed = self._run_direct_sandbox(
            workspace,
            environment,
            command,
            disable_network=True,
        )
        payload = self._run_wsl_bytes(
            platform,
            ("/usr/bin/cat", f"{workspace}/{marker}"),
            timeout=30,
        )
        clean = self._run_wsl_text(
            platform,
            ("/usr/bin/rm", "-rf", f"{workspace}/{marker}", codex_home),
            timeout=30,
        )
        return (
            completed is not None
            and completed.returncode == 0
            and payload is not None
            and payload.returncode == 0
            and payload.stdout == b"DIRECT_OK\n"
            and clean is not None
            and clean.returncode == 0
        )

    def _outside_write_probe(self, workspace: str) -> bool:
        platform = self._require_platform()
        outside = self._create_native_workspace("outside")
        if outside is None:
            return False
        codex_home = f"{workspace}/.outside-codex-home"
        setup = self._run_wsl_text(
            platform,
            ("/usr/bin/mkdir", "-p", codex_home),
            timeout=30,
        )
        target = f"{outside}/forbidden.txt"
        command = (
            "/usr/bin/python3",
            "-c",
            (
                "from pathlib import Path; import sys; "
                "Path(sys.argv[1]).write_text('FORBIDDEN\\n', encoding='utf-8')"
            ),
            target,
        )
        completed = None
        if setup is not None and setup.returncode == 0:
            completed = self._run_direct_sandbox(
                workspace,
                self._direct_environment(codex_home),
                command,
                disable_network=True,
            )
        exists = self._run_wsl_text(
            platform,
            ("/usr/bin/test", "-e", target),
            timeout=30,
        )
        cleaned = self._run_wsl_text(
            platform,
            ("/usr/bin/rm", "-rf", codex_home),
            timeout=30,
        )
        outside_cleaned = self._cleanup_native_workspace(outside)
        return (
            completed is not None
            and completed.returncode != 0
            and exists is not None
            and exists.returncode != 0
            and cleaned is not None
            and cleaned.returncode == 0
            and outside_cleaned
        )

    def _network_probe(self, workspace: str) -> bool:
        platform = self._require_platform()
        codex_home = f"{workspace}/.network-codex-home"
        setup = self._run_wsl_text(
            platform,
            ("/usr/bin/mkdir", "-p", codex_home),
            timeout=30,
        )
        if setup is None or setup.returncode != 0:
            return False
        script = "\n".join(
            (
                "import socket",
                "import sys",
                "try:",
                "    sock = socket.socket()",
                "    sock.settimeout(3)",
                "    sock.connect(('1.1.1.1', 443))",
                "except OSError:",
                "    sys.exit(0)",
                "else:",
                "    sock.close()",
                "    sys.exit(9)",
            )
        )
        completed = self._run_direct_sandbox(
            workspace,
            self._direct_environment(codex_home),
            ("/usr/bin/python3", "-c", script),
            disable_network=True,
        )
        cleaned = self._run_wsl_text(
            platform,
            ("/usr/bin/rm", "-rf", codex_home),
            timeout=30,
        )
        return (
            completed is not None
            and completed.returncode == 0
            and cleaned is not None
            and cleaned.returncode == 0
        )

    def _run_direct_sandbox(
        self,
        workspace: str,
        environment: tuple[tuple[str, str], ...],
        command: tuple[str, ...],
        *,
        disable_network: bool,
    ) -> subprocess.CompletedProcess[str] | None:
        spec = self._runtime_spec
        if spec is None or not self._runtime_is_current(spec):
            return None
        arguments: list[str] = [
            "/usr/bin/env",
            "-i",
            *_environment_assignments(environment),
            str(spec.executable),
            "--ask-for-approval",
            "never",
            "--sandbox",
            "workspace-write",
            "-c",
            "sandbox_workspace_write.network_access=false",
            "-c",
            'web_search="disabled"',
            "sandbox",
            "--cd",
            workspace,
            "--permission-profile",
            ":workspace",
        ]
        if disable_network:
            arguments.append("--sandbox-state-disable-network")
        arguments.extend(("--", *command))
        return self._run_wsl_text(
            spec.platform,
            tuple(arguments),
            timeout=60,
        )

    def _direct_environment(
        self,
        codex_home: str,
    ) -> tuple[tuple[str, str], ...]:
        spec = self._require_runtime()
        values = dict(spec.environment)
        values["CODEX_HOME"] = codex_home
        return tuple(values.items())

    def _create_native_workspace(self, purpose: str) -> str | None:
        platform = self._require_platform()
        root = platform.linux_home / WSL_WORKSPACE_ROOT
        made = self._run_wsl_text(
            platform,
            ("/usr/bin/mkdir", "-p", str(root)),
            timeout=30,
        )
        secured = self._run_wsl_text(
            platform,
            ("/usr/bin/chmod", "700", str(root)),
            timeout=30,
        )
        if any(
            result is None or result.returncode != 0
            for result in (made, secured)
        ):
            return None
        created = self._run_wsl_text(
            platform,
            (
                "/usr/bin/mktemp",
                "-d",
                "-p",
                str(root),
                f"{purpose}.XXXXXXXX",
            ),
            timeout=30,
        )
        if created is None or created.returncode != 0:
            return None
        workspace = created.stdout.strip()
        if not _path_within_posix(workspace, str(root)):
            return None
        filesystem = self._run_wsl_text(
            platform,
            ("/usr/bin/stat", "-f", "-c", "%T", workspace),
            timeout=30,
        )
        if (
            filesystem is None
            or filesystem.returncode != 0
            or not _native_linux_filesystem(filesystem.stdout.strip())
        ):
            self._cleanup_native_workspace(workspace)
            return None
        return workspace

    def _cleanup_native_workspace(self, workspace: str) -> bool:
        platform = self._require_platform()
        root = str(platform.linux_home / WSL_WORKSPACE_ROOT)
        if not _path_within_posix(workspace, root):
            return False
        removed = self._run_wsl_text(
            platform,
            ("/usr/bin/rm", "-rf", "--", workspace),
            timeout=60,
        )
        exists = self._run_wsl_text(
            platform,
            ("/usr/bin/test", "-e", workspace),
            timeout=30,
        )
        return (
            removed is not None
            and removed.returncode == 0
            and exists is not None
            and exists.returncode != 0
        )

    def _initialize_shadow_git(self, workspace: str, readme: str) -> bool:
        platform = self._require_platform()
        write_script = (
            "from pathlib import Path; import sys; "
            "Path(sys.argv[1]).write_text(sys.argv[2], encoding='utf-8')"
        )
        commands = (
            ("/usr/bin/git", "-C", workspace, "init", "--quiet"),
            (
                "/usr/bin/git",
                "-C",
                workspace,
                "config",
                "user.name",
                "Phoenix WSL Worker",
            ),
            (
                "/usr/bin/git",
                "-C",
                workspace,
                "config",
                "user.email",
                "wsl-worker@phoenix.invalid",
            ),
            (
                "/usr/bin/python3",
                "-c",
                write_script,
                f"{workspace}/README.md",
                readme,
            ),
            ("/usr/bin/git", "-C", workspace, "add", "--", "README.md"),
            (
                "/usr/bin/git",
                "-C",
                workspace,
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "--quiet",
                "-m",
                "baseline",
            ),
        )
        for command in commands:
            completed = self._run_wsl_text(platform, command, timeout=60)
            if completed is None or completed.returncode != 0:
                return False
        return True

    def _extract_snapshot(
        self,
        shadow: str,
        archive: bytes,
        expected_paths: tuple[str, ...],
    ) -> bool:
        if not validate_snapshot_archive(archive, expected_paths):
            return False
        completed = self._run_wsl_bytes(
            self._require_platform(),
            (
                "/usr/bin/tar",
                "--extract",
                "--file=-",
                "--directory",
                shadow,
                "--no-same-owner",
            ),
            timeout=120,
            input_bytes=archive,
        )
        return completed is not None and completed.returncode == 0

    def _initialize_snapshot_git(self, shadow: str) -> bool:
        platform = self._require_platform()
        commands = (
            ("/usr/bin/git", "-C", shadow, "init", "--quiet"),
            (
                "/usr/bin/git",
                "-C",
                shadow,
                "config",
                "user.name",
                "Phoenix WSL Worker",
            ),
            (
                "/usr/bin/git",
                "-C",
                shadow,
                "config",
                "user.email",
                "wsl-worker@phoenix.invalid",
            ),
            (
                "/usr/bin/git",
                "-C",
                shadow,
                "add",
                "--all",
                "--force",
            ),
            (
                "/usr/bin/git",
                "-C",
                shadow,
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "--quiet",
                "-m",
                "Phoenix shadow baseline",
            ),
            (
                "/usr/bin/git",
                "-C",
                shadow,
                "status",
                "--porcelain=v1",
            ),
        )
        for index, command in enumerate(commands):
            completed = self._run_wsl_text(platform, command, timeout=120)
            if completed is None or completed.returncode != 0:
                return False
            if index == len(commands) - 1 and completed.stdout.strip():
                return False
        return True

    def _shadow_git_control_state(
        self,
        shadow: str,
    ) -> tuple[str, str, str] | None:
        platform = self._require_platform()
        outputs: list[str] = []
        for command in (
            ("/usr/bin/git", "-C", shadow, "rev-parse", "HEAD"),
            (
                "/usr/bin/git",
                "-C",
                shadow,
                "for-each-ref",
                "--format=%(refname) %(objectname)",
                "refs",
            ),
            (
                "/usr/bin/git",
                "-C",
                shadow,
                "config",
                "--local",
                "--null",
                "--list",
            ),
        ):
            completed = self._run_wsl_text(platform, command, timeout=30)
            if completed is None or completed.returncode != 0:
                return None
            outputs.append(completed.stdout)
        return tuple(outputs)  # type: ignore[return-value]

    def _validated_shadow_patch(
        self,
        shadow: str,
        tracked_paths: tuple[str, ...],
        allowed_paths: tuple[str, ...],
        baseline: tuple[str, str, str],
        *,
        pilot_kind: str,
    ) -> ShadowPatch | None:
        if (
            pilot_kind not in CODEX_PILOT_AUTHORIZATION_KINDS
            or not is_safe_codex_pilot_allowed_paths(
                list(allowed_paths), pilot_kind
            )
        ):
            return None
        try:
            if validate_transfer_paths(tracked_paths) != validate_transfer_paths(
                allowed_paths
            ):
                return None
        except ValueError:
            return None
        platform = self._require_platform()
        if self._shadow_git_control_state(shadow) != baseline:
            return None
        staged = self._run_wsl_text(
            platform,
            ("/usr/bin/git", "-C", shadow, "diff", "--cached", "--quiet"),
            timeout=30,
        )
        status = self._run_wsl_text(
            platform,
            (
                "/usr/bin/git",
                "-C",
                shadow,
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
            ),
            timeout=30,
        )
        if (
            staged is None
            or staged.returncode != 0
            or status is None
            or status.returncode != 0
        ):
            return None
        changed = _parse_porcelain_paths(status.stdout)
        if changed is None or not changed:
            return None
        try:
            new_paths = tuple(path for path in changed if path not in tracked_paths)
            validate_transfer_paths((*tracked_paths, *new_paths))
        except ValueError:
            return None
        if not set(changed).issubset(set(allowed_paths)):
            return None
        for path_text in changed:
            if pilot_kind == CODEX_PILOT_DOCS_ONLY_KIND:
                path_valid = self._validate_shadow_markdown(shadow, path_text)
            elif pilot_kind == CODEX_PILOT_BOUNDED_PYTHON_KIND:
                path_valid = self._validate_shadow_python(shadow, path_text)
            else:
                return None
            if not path_valid:
                return None
        added = self._run_wsl_text(
            platform,
            ("/usr/bin/git", "-C", shadow, "add", "--", *changed),
            timeout=60,
        )
        if added is None or added.returncode != 0:
            return None
        staged_names = self._run_wsl_text(
            platform,
            (
                "/usr/bin/git",
                "-C",
                shadow,
                "diff",
                "--cached",
                "--name-only",
                "-z",
            ),
            timeout=30,
        )
        if staged_names is None or staged_names.returncode != 0:
            return None
        staged_paths = tuple(
            sorted(path for path in staged_names.stdout.split("\0") if path)
        )
        if staged_paths != tuple(sorted(changed)):
            return None
        patch = self._run_wsl_bytes(
            platform,
            (
                "/usr/bin/git",
                "-C",
                shadow,
                "diff",
                "--cached",
                "--binary",
                "--full-index",
                "--no-ext-diff",
                "--no-renames",
                "HEAD",
                "--",
                *changed,
            ),
            timeout=60,
        )
        if (
            patch is None
            or patch.returncode != 0
            or not patch.stdout
            or len(patch.stdout) > MAX_PATCH_BYTES
            or not patch.stdout.startswith(b"diff --git ")
        ):
            return None
        return ShadowPatch(patch.stdout, tuple(sorted(changed)))

    def _validate_shadow_markdown(self, shadow: str, path_text: str) -> bool:
        if not path_text.casefold().endswith(".md"):
            return False
        return self._validate_shadow_text_file(shadow, path_text)

    def _validate_shadow_python(self, shadow: str, path_text: str) -> bool:
        if not path_text.casefold().endswith(".py"):
            return False
        return self._validate_shadow_text_file(shadow, path_text)

    def _validate_shadow_text_file(self, shadow: str, path_text: str) -> bool:
        platform = self._require_platform()
        absolute = f"{shadow}/{path_text}"
        symlink = self._run_wsl_text(
            platform,
            ("/usr/bin/test", "-L", absolute),
            timeout=30,
        )
        file_test = self._run_wsl_text(
            platform,
            ("/usr/bin/test", "-f", absolute),
            timeout=30,
        )
        realpath = self._run_wsl_text(
            platform,
            ("/usr/bin/readlink", "-f", absolute),
            timeout=30,
        )
        metadata = self._run_wsl_text(
            platform,
            ("/usr/bin/stat", "-c", "%F:%h", absolute),
            timeout=30,
        )
        payload = self._run_wsl_bytes(
            platform,
            ("/usr/bin/cat", absolute),
            timeout=30,
        )
        if any(
            result is None
            for result in (symlink, file_test, realpath, metadata, payload)
        ):
            return False
        if symlink.returncode == 0 or file_test.returncode != 0:
            return False
        if realpath.returncode != 0 or not _path_within_posix(
            realpath.stdout.strip(), shadow
        ):
            return False
        if metadata.returncode != 0 or metadata.stdout.strip() != "regular file:1":
            return False
        if payload.returncode != 0 or len(payload.stdout) > MAX_MARKDOWN_BYTES:
            return False
        if b"\0" in payload.stdout:
            return False
        try:
            text = payload.stdout.decode("utf-8")
        except UnicodeError:
            return False
        return not any(pattern.search(text) for pattern in _SENSITIVE_PATTERNS)

    def _run_wsl_text(
        self,
        platform: WslPlatformSpec,
        linux_argv: Sequence[str],
        *,
        timeout: int,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str] | None:
        return self._run_host_text(
            self._wsl_argv(platform, linux_argv),
            timeout=timeout,
            input_text=input_text,
        )

    def _run_wsl_bytes(
        self,
        platform: WslPlatformSpec,
        linux_argv: Sequence[str],
        *,
        timeout: int,
        input_bytes: bytes | None = None,
    ) -> subprocess.CompletedProcess[bytes] | None:
        argv = self._wsl_argv(platform, linux_argv)
        try:
            completed = self._host_run(
                list(argv),
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                timeout=timeout,
                env=_sanitized_wsl_host_environment(),
            )
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return None
        stdout = bytes(completed.stdout or b"")
        stderr = bytes(completed.stderr or b"")
        if len(stdout) > MAX_COMMAND_OUTPUT_BYTES or len(stderr) > MAX_COMMAND_OUTPUT_BYTES:
            return None
        return subprocess.CompletedProcess(
            list(argv),
            completed.returncode,
            stdout,
            b"",
        )

    def _run_host_text(
        self,
        argv: Sequence[str],
        *,
        timeout: int,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str] | None:
        try:
            completed = self._host_run(
                list(argv),
                input=input_text,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
                timeout=timeout,
                env=_sanitized_wsl_host_environment(),
            )
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return None
        stdout = str(completed.stdout or "")
        stderr = str(completed.stderr or "")
        if len(stdout.encode()) > MAX_COMMAND_OUTPUT_BYTES:
            return None
        if len(stderr.encode()) > MAX_COMMAND_OUTPUT_BYTES:
            return None
        return subprocess.CompletedProcess(
            list(argv),
            completed.returncode,
            stdout,
            "",
        )

    @staticmethod
    def _wsl_argv(
        platform: WslPlatformSpec,
        linux_argv: Sequence[str],
    ) -> tuple[str, ...]:
        return (
            str(platform.wsl_executable),
            "--distribution",
            platform.distro_name,
            "--exec",
            *linux_argv,
        )

    def _require_platform(self) -> WslPlatformSpec:
        spec = self._runtime_spec
        if spec is None:
            raise RuntimeError("WSL runtime is not qualified")
        return spec.platform

    def _require_runtime(self) -> WslCodexRuntimeSpec:
        spec = self._runtime_spec
        if spec is None:
            raise RuntimeError("WSL runtime is not qualified")
        return spec


def validate_transfer_paths(paths: Iterable[str]) -> tuple[str, ...]:
    """Validate a Linux path set before any Windows-facing patch is exported."""

    normalized: list[str] = []
    case_keys: dict[str, str] = {}
    for value in paths:
        if not isinstance(value, str) or not value or len(value) > 1024:
            raise ValueError("unsafe transfer path")
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("unsafe transfer path")
        if "\\" in value or ":" in value or "\0" in value:
            raise ValueError("unsafe transfer path")
        if unicodedata.normalize("NFC", value) != value:
            raise ValueError("unsafe transfer path")
        path = PurePosixPath(value)
        if path.is_absolute() or not path.parts:
            raise ValueError("unsafe transfer path")
        if any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("unsafe transfer path")
        for part in path.parts:
            if part != part.rstrip(" ."):
                raise ValueError("unsafe transfer path")
            stem = part.split(".", 1)[0].upper()
            if stem in _WINDOWS_RESERVED_NAMES:
                raise ValueError("unsafe transfer path")
            if part.casefold() in _GENERATED_COMPONENTS:
                raise ValueError("unsafe transfer path")
        canonical = path.as_posix()
        key = unicodedata.normalize("NFC", canonical).casefold()
        previous = case_keys.get(key)
        if previous is not None and previous != canonical:
            raise ValueError("case-colliding transfer paths")
        case_keys[key] = canonical
        normalized.append(canonical)
    if len(set(normalized)) != len(normalized):
        raise ValueError("duplicate transfer paths")
    return tuple(sorted(normalized))


def build_windows_snapshot(
    worktree: Path,
    base_commit_sha: str,
    visible_paths: tuple[str, ...],
    *,
    pilot_kind: str,
) -> WindowsSnapshot:
    """Create a deterministic tar snapshot of explicitly worker-visible files."""

    root = Path(worktree).resolve(strict=True)
    head = _run_git(root, "rev-parse", "HEAD")
    status_result = _run_git(root, "status", "--porcelain=v1", "-z")
    tracked_result = _run_git(root, "ls-files", "--stage", "-z")
    if head.stdout.strip() != base_commit_sha or status_result.stdout:
        raise ValueError("Windows task worktree is not at its reviewed baseline")
    entries = _parse_index_entries(tracked_result.stdout)
    if not entries or len(entries) > MAX_SNAPSHOT_FILES:
        raise ValueError("Windows snapshot file count is invalid")
    source_entries = tuple(
        (mode, path)
        for mode, path in entries
        if not path.casefold().endswith(_CONTROL_STATE_SUFFIXES)
    )
    source_paths = validate_transfer_paths(path for _mode, path in source_entries)
    if (
        pilot_kind not in CODEX_PILOT_AUTHORIZATION_KINDS
        or not is_safe_codex_pilot_allowed_paths(
            list(visible_paths), pilot_kind
        )
    ):
        raise ValueError("worker-visible paths are invalid")
    paths = validate_transfer_paths(visible_paths)
    entry_by_path = {path: mode for mode, path in source_entries}
    if any(path not in entry_by_path for path in paths):
        raise ValueError("worker-visible source is unavailable")

    source_digest = hashlib.sha256()
    selected_payloads: dict[str, bytes] = {}
    source_total = 0
    for path_text in source_paths:
        mode = entry_by_path[path_text]
        if mode not in {"100644", "100755"}:
            raise ValueError("unsupported tracked object")
        path = root.joinpath(*PurePosixPath(path_text).parts)
        path_stat = path.lstat()
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
        if (
            not stat.S_ISREG(path_stat.st_mode)
            or path.is_symlink()
            or path_stat.st_nlink != 1
        ):
            raise ValueError("unsafe tracked file")
        payload = path.read_bytes()
        source_total += len(payload)
        if source_total > MAX_SNAPSHOT_BYTES:
            raise ValueError("Windows source state is too large")
        source_digest.update(path_text.encode("utf-8"))
        source_digest.update(b"\0")
        source_digest.update(mode.encode("ascii"))
        source_digest.update(b"\0")
        source_digest.update(payload)
        if path_text in paths:
            selected_payloads[path_text] = payload

    buffer = io.BytesIO()
    digest = hashlib.sha256()
    total = 0
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for path_text in paths:
            mode = entry_by_path[path_text]
            payload = selected_payloads[path_text]
            total += len(payload)
            if total > MAX_SNAPSHOT_BYTES:
                raise ValueError("Windows snapshot is too large")
            info = tarfile.TarInfo(path_text)
            info.size = len(payload)
            info.mode = 0o755 if mode == "100755" else 0o644
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            archive.addfile(info, io.BytesIO(payload))
            digest.update(path_text.encode("utf-8"))
            digest.update(b"\0")
            digest.update(mode.encode("ascii"))
            digest.update(b"\0")
            digest.update(payload)
    return WindowsSnapshot(
        buffer.getvalue(),
        digest.hexdigest(),
        paths,
        pilot_kind,
        source_digest.hexdigest(),
    )


def validate_snapshot_archive(
    archive_bytes: bytes,
    expected_paths: tuple[str, ...],
) -> bool:
    """Reject archive path, link, type, and size ambiguity before WSL transfer."""

    if not archive_bytes or len(archive_bytes) > MAX_SNAPSHOT_BYTES:
        return False
    try:
        safe_expected = validate_transfer_paths(expected_paths)
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
            members = archive.getmembers()
            if not members or len(members) > MAX_SNAPSHOT_FILES:
                return False
            names = tuple(member.name for member in members)
            if validate_transfer_paths(names) != safe_expected:
                return False
            total = 0
            for member in members:
                if not member.isreg() or member.issym() or member.islnk():
                    return False
                if member.linkname or member.size < 0:
                    return False
                total += member.size
                if total > MAX_SNAPSHOT_BYTES:
                    return False
    except (OSError, tarfile.TarError, ValueError):
        return False
    return True


def windows_snapshot_matches(
    worktree: Path,
    base_commit_sha: str,
    expected: WindowsSnapshot,
) -> bool:
    try:
        current = build_windows_snapshot(
            worktree,
            base_commit_sha,
            expected.tracked_paths,
            pilot_kind=expected.pilot_kind,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
    return (
        current.digest == expected.digest
        and current.tracked_paths == expected.tracked_paths
        and current.pilot_kind == expected.pilot_kind
        and current.source_state_digest == expected.source_state_digest
    )


def apply_shadow_patch(worktree: Path, patch: ShadowPatch) -> bool:
    """Apply one prevalidated shadow patch without staging or publication."""

    root = Path(worktree).resolve(strict=True)
    status = _run_git(root, "status", "--porcelain=v1", "-z")
    if status.stdout:
        return False
    try:
        completed = subprocess.run(
            ["git", "apply", "--whitespace=error-all", "-"],
            cwd=root,
            input=patch.payload,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if completed.returncode != 0:
        return False
    changed = _run_git(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    paths = _parse_porcelain_paths(changed.stdout)
    return paths is not None and tuple(sorted(paths)) == patch.changed_paths


def _replace_transfer_evidence(
    value: WslTransferEvidence,
    **updates: bool,
) -> WslTransferEvidence:
    fields = {
        "shadow_workspace_created": value.shadow_workspace_created,
        "shadow_git_baseline_created": value.shadow_git_baseline_created,
        "windows_worktree_unchanged_during_worker": (
            value.windows_worktree_unchanged_during_worker
        ),
        "changed_paths_validated_before_apply": (
            value.changed_paths_validated_before_apply
        ),
        "patch_exported": value.patch_exported,
        "patch_applied": value.patch_applied,
        "temp_cleanup": value.temp_cleanup,
    }
    fields.update(updates)
    return WslTransferEvidence(**fields)


def _resolve_wsl_executable() -> Path | None:
    candidates: list[Path] = []
    system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
    if system_root:
        candidates.append(Path(system_root) / "System32" / "wsl.exe")
    discovered = shutil.which("wsl.exe")
    if discovered:
        candidates.append(Path(discovered))
    for candidate in candidates:
        identity = _windows_executable_identity(candidate)
        if identity is not None:
            return identity[0]
    return None


def _windows_executable_identity(
    candidate: Path | None,
) -> tuple[Path, int, int, int, int] | None:
    if candidate is None:
        return None
    try:
        resolved = candidate.resolve(strict=True)
        candidate_stat = candidate.lstat()
        with resolved.open("rb") as stream:
            header = stream.read(2)
    except OSError:
        return None
    if not resolved.is_absolute() or candidate.is_symlink():
        return None
    if not stat.S_ISREG(candidate_stat.st_mode) or header != b"MZ":
        return None
    return (
        resolved,
        candidate_stat.st_dev,
        candidate_stat.st_ino,
        candidate_stat.st_size,
        candidate_stat.st_mtime_ns,
    )


def _bounded_distro_name(value: str) -> str | None:
    candidate = value.strip()
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]{0,127}", candidate) is None:
        return None
    return candidate


def _bounded_linux_user(value: str) -> str | None:
    candidate = value.strip()
    if re.fullmatch(r"[a-z_][a-z0-9_-]{0,63}", candidate) is None:
        return None
    if candidate == "root":
        return None
    return candidate


def _is_wsl2_kernel(value: str) -> bool:
    folded = value.strip().casefold()
    return "microsoft" in folded and "wsl2" in folded


def _safe_native_linux_path(value: str) -> bool:
    if not value or len(value) > 4096 or "\0" in value:
        return False
    if any(ord(character) < 32 for character in value):
        return False
    path = PurePosixPath(value)
    if not path.is_absolute() or ".." in path.parts:
        return False
    return not (len(path.parts) >= 2 and path.parts[1].casefold() == "mnt")


def _native_linux_filesystem(value: str) -> bool:
    folded = value.strip().casefold()
    return folded in {"ext2/ext3", "ext4"}


def _official_pinned_package(
    manifest: object,
    lock: object,
) -> bool:
    if not isinstance(manifest, dict) or not isinstance(lock, dict):
        return False
    if manifest.get("name") != "@openai/codex":
        return False
    if manifest.get("version") != WSL_CODEX_REQUIRED_VERSION:
        return False
    packages = lock.get("packages")
    if not isinstance(packages, dict):
        return False
    item = packages.get("node_modules/@openai/codex")
    if not isinstance(item, dict) or item.get("version") != WSL_CODEX_REQUIRED_VERSION:
        return False
    integrity = item.get("integrity")
    return isinstance(integrity, str) and integrity.startswith("sha512-")


def _pinned_runtime_relative_path(value: object) -> PurePosixPath | None:
    if not isinstance(value, dict) or value.get("version") != WSL_CODEX_REQUIRED_VERSION:
        return None
    relative = value.get("relative_path")
    if not isinstance(relative, str) or not relative:
        return None
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        return None
    return path


def _parse_linux_identity(
    stat_result: subprocess.CompletedProcess[str] | None,
    sha_result: subprocess.CompletedProcess[str] | None,
) -> tuple[int, int, int, int, str] | None:
    if (
        stat_result is None
        or sha_result is None
        or stat_result.returncode != 0
        or sha_result.returncode != 0
    ):
        return None
    fields = stat_result.stdout.strip().split(":")
    sha = sha_result.stdout.strip().split(maxsplit=1)[0]
    if len(fields) != 4 or not all(field.isdigit() for field in fields):
        return None
    if re.fullmatch(r"[0-9a-f]{64}", sha) is None:
        return None
    return int(fields[0]), int(fields[1]), int(fields[2]), int(fields[3]), sha


def _compatible_elf(
    elf_result: subprocess.CompletedProcess[str] | None,
    arch_result: subprocess.CompletedProcess[str] | None,
) -> bool:
    if (
        elf_result is None
        or arch_result is None
        or elf_result.returncode != 0
        or arch_result.returncode != 0
    ):
        return False
    try:
        header = bytes.fromhex(elf_result.stdout)
    except ValueError:
        return False
    if len(header) < 20 or header[:4] != b"\x7fELF" or header[4] != 2:
        return False
    machine = int.from_bytes(header[18:20], "little")
    return (arch_result.stdout.strip(), machine) in {
        ("x86_64", 62),
        ("aarch64", 183),
    }


def _valid_proxy_value(value: str, *, requires_url: bool) -> bool:
    if not value or len(value.encode("utf-8")) > MAX_PROXY_VALUE_BYTES:
        return False
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return False
    if not requires_url:
        return True
    parsed = urlsplit(value)
    return parsed.scheme.casefold() in {"http", "https", "socks5"} and bool(
        parsed.netloc
    )


def _environment_assignments(
    values: Mapping[str, str] | Sequence[tuple[str, str]],
) -> tuple[str, ...]:
    items = values.items() if isinstance(values, Mapping) else values
    return tuple(f"{name}={value}" for name, value in items)


def _sanitized_wsl_host_environment() -> dict[str, str]:
    environment: dict[str, str] = {"WSLENV": ""}
    for name in ("SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "TEMP", "TMP"):
        value = os.environ.get(name)
        if value:
            environment[name] = value
    return environment


def _path_within_posix(value: str, root: str) -> bool:
    if not _safe_native_linux_path(value) or not _safe_native_linux_path(root):
        return False
    value_path = PurePosixPath(value)
    root_path = PurePosixPath(root)
    try:
        value_path.relative_to(root_path)
    except ValueError:
        return False
    return value_path != root_path


def _parse_codex_jsonl(value: str) -> dict[str, object]:
    fatal = False
    completed = False
    usage: int | None = None
    failure: str | None = None
    messages: list[str] = []
    lines = value.splitlines()
    if len(lines) > MAX_JSONL_LINES:
        return {
            "fatal": True,
            "turn_completed": False,
            "usage_tokens": None,
            "failure_category": "wsl_codex_output_invalid",
            "messages": [],
        }
    for line in lines:
        if len(line.encode("utf-8")) > MAX_JSONL_LINE_BYTES:
            fatal = True
            failure = "wsl_codex_output_invalid"
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            fatal = True
            failure = "wsl_codex_output_invalid"
            continue
        if not isinstance(event, dict):
            fatal = True
            continue
        event_type = event.get("type")
        if event_type == "turn.completed":
            completed = True
            usage = _usage_tokens(event.get("usage"))
        elif event_type in {"turn.failed", "error"}:
            fatal = True
            failure = "wsl_codex_structured_failure"
        elif event_type == "item.completed":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                text = item.get("text")
                if isinstance(text, str) and len(text) <= 4096:
                    messages.append(text)
    return {
        "fatal": fatal,
        "turn_completed": completed,
        "usage_tokens": usage,
        "failure_category": failure,
        "messages": messages,
    }


def _bounded_codex_failure(value: str) -> str | None:
    folded = value.casefold()
    if "authentication" in folded or "login required" in folded:
        return "wsl_codex_authentication_unavailable"
    if "unexpected argument" in folded or "unknown configuration" in folded:
        return "wsl_codex_argument_or_config_rejected"
    if "stream disconnected" in folded or "transport" in folded:
        return "wsl_codex_transport_unavailable"
    return None


def _usage_tokens(value: object) -> int | None:
    if not isinstance(value, dict):
        return None
    total = value.get("total_tokens")
    if isinstance(total, int) and not isinstance(total, bool) and total >= 0:
        return total
    input_tokens = value.get("input_tokens")
    output_tokens = value.get("output_tokens")
    if all(
        isinstance(item, int) and not isinstance(item, bool) and item >= 0
        for item in (input_tokens, output_tokens)
    ):
        return int(input_tokens) + int(output_tokens)
    return None


def _terminate_process(process: subprocess.Popen[str]) -> bool:
    try:
        if process.poll() is not None:
            return True
        process.terminate()
        process.wait(timeout=10)
        return True
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
            process.wait(timeout=10)
            return True
        except (OSError, subprocess.TimeoutExpired):
            return False


def _parse_index_entries(value: str) -> tuple[tuple[str, str], ...]:
    entries: list[tuple[str, str]] = []
    for record in value.split("\0"):
        if not record:
            continue
        metadata, separator, path = record.partition("\t")
        fields = metadata.split()
        if not separator or len(fields) != 3 or fields[2] != "0":
            raise ValueError("invalid Git index")
        entries.append((fields[0], path.replace("\\", "/")))
    return tuple(entries)


def _parse_porcelain_paths(value: str) -> tuple[str, ...] | None:
    paths: list[str] = []
    for record in value.split("\0"):
        if not record:
            continue
        if len(record) < 4 or record[2] != " ":
            return None
        status_code = record[:2]
        if any(marker in status_code for marker in "RCD"):
            return None
        path = record[3:].replace("\\", "/")
        paths.append(path)
    if not paths or len(paths) != len(set(paths)):
        return None
    try:
        return validate_transfer_paths(paths)
    except ValueError:
        return None


def _run_git(worktree: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=worktree,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="strict",
        shell=False,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        raise subprocess.CalledProcessError(completed.returncode, completed.args)
    if len(completed.stdout.encode("utf-8")) > MAX_COMMAND_OUTPUT_BYTES:
        raise ValueError("Git output is too large")
    return completed
