from __future__ import annotations

import hashlib
import inspect
import io
import os
import shutil
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

import pytest

import phoenix_office.dev.codex_wsl as wsl_module
from phoenix_office.core import (
    CODEX_PILOT_BOUNDED_PYTHON_KIND,
    CODEX_PILOT_DOCS_ONLY_KIND,
)
from phoenix_office.dev.codex_runner import (
    DiffGateResult,
    SystemCodexPilotServices,
)
from phoenix_office.dev.codex_wsl import (
    WSL_CODEX_REQUIRED_VERSION,
    ShadowPatch,
    WindowsSnapshot,
    WslCapabilityResult,
    WslCodexRuntimeSpec,
    WslCodexWorker,
    WslExecutionResult,
    WslGateResult,
    WslInvocationControl,
    WslPlatformSpec,
    WslProcessStopResult,
    apply_shadow_patch,
    build_windows_snapshot,
    validate_snapshot_archive,
    validate_transfer_paths,
    windows_snapshot_matches,
)

DOCS_PATH = "docs/process/status.md"
PYTHON_PATHS = (
    "src/phoenix_office/dev/codex_successor.py",
    "tests/test_codex_successor.py",
)


class _FakeModelProcess:
    def __init__(
        self,
        outcome: tuple[str, str] | BaseException,
        *,
        returncode: int = 0,
    ) -> None:
        self.outcome = outcome
        self.returncode = returncode

    def communicate(self, *_args, **_kwargs) -> tuple[str, str]:
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9

    def wait(self, timeout: int | None = None) -> int:
        del timeout
        return self.returncode


def _controlled_model_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    process: _FakeModelProcess,
) -> tuple[WslCodexWorker, WslInvocationControl]:
    worker = WslCodexWorker(tmp_path, host_popen=lambda *_args, **_kwargs: process)
    worker._runtime_spec = _runtime(tmp_path / "runtime")
    control = WslInvocationControl(
        "a" * 32,
        PurePosixPath("/home/worker/.local/share/phoenix/task-064-invocations/a"),
        PurePosixPath(
            "/home/worker/.local/share/phoenix/task-064-invocations/a/"
            "invocation.json"
        ),
    )
    monkeypatch.setattr(worker, "_runtime_is_current", lambda _spec: True)
    monkeypatch.setattr(worker, "_prepare_invocation_control", lambda _platform: control)
    monkeypatch.setattr(worker, "_await_invocation_ready", lambda _control: True)
    monkeypatch.setattr(worker, "_prove_linux_invocation_exit", lambda _control: True)
    monkeypatch.setattr(worker, "_cleanup_invocation_control", lambda _control: True)
    return worker, control


def _captured_model_codex_arguments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pilot_kind: str,
) -> tuple[str, ...]:
    process = _FakeModelProcess(
        ('{"type":"turn.completed","usage":{"total_tokens":7}}\n', "")
    )
    worker, _control = _controlled_model_worker(tmp_path, monkeypatch, process)
    observed: list[tuple[str, ...]] = []

    def capture(argv, **_kwargs):
        observed.append(tuple(str(argument) for argument in argv))
        return process

    monkeypatch.setattr(worker, "_host_popen", capture)

    result, messages = worker._run_model(
        workspace="/home/worker/shadow",
        prompt="bounded",
        timeout_seconds=30,
        on_started=lambda: None,
        pilot_kind=pilot_kind,
    )

    assert result == WslExecutionResult("succeeded", "wsl_codex_completed", 7)
    assert messages == ()
    assert len(observed) == 1
    runtime = worker._runtime_spec
    assert runtime is not None
    executable_index = observed[0].index(str(runtime.executable))
    return observed[0][executable_index + 1 :]


def _expected_docs_model_arguments(workspace: str) -> tuple[str, ...]:
    return (
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


def _git(cwd: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "--quiet")
    _git(repository, "config", "user.name", "Phoenix Test")
    _git(repository, "config", "user.email", "test@phoenix.invalid")
    document = repository / DOCS_PATH
    document.parent.mkdir(parents=True)
    document.write_text(
        "Initial status.\n",
        encoding="utf-8",
    )
    (repository / "src").mkdir()
    (repository / "src" / "safe.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repository, "add", "--all")
    _git(repository, "commit", "--quiet", "-m", "baseline")
    return repository, _git(repository, "rev-parse", "HEAD")


def _python_repository(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "python-repository"
    repository.mkdir()
    _git(repository, "init", "--quiet")
    _git(repository, "config", "user.name", "Phoenix Test")
    _git(repository, "config", "user.email", "test@phoenix.invalid")
    for relative in (*PYTHON_PATHS, DOCS_PATH):
        target = repository / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "def bounded_value():\n    return 1\n"
            if relative.endswith(".py")
            else "Initial status.\n",
            encoding="utf-8",
        )
    _git(repository, "add", "--all")
    _git(repository, "commit", "--quiet", "-m", "baseline")
    return repository, _git(repository, "rev-parse", "HEAD")


def _fake_windows_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"MZ" + (b"\0" * 30))
    return path


def _platform(tmp_path: Path) -> WslPlatformSpec:
    executable = _fake_windows_executable(tmp_path / "Windows" / "System32" / "wsl.exe")
    metadata = executable.stat()
    return WslPlatformSpec(
        executable,
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        "BoundedDistro",
        PurePosixPath("/home/worker"),
        "worker",
        "ext2/ext3",
    )


def _runtime(tmp_path: Path) -> WslCodexRuntimeSpec:
    platform = _platform(tmp_path)
    return WslCodexRuntimeSpec(
        platform,
        PurePosixPath(
            "/home/worker/.local/share/phoenix/diagnostics/"
            "task-064-codex-01461/runtime/codex"
        ),
        1,
        2,
        3,
        4,
        "a" * 64,
        (("HOME", "/home/worker"), ("PATH", wsl_module.LINUX_PATH)),
    )


def _completed(
    argv: list[str],
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(argv, returncode, stdout, stderr)


def _simulated_shadow_patch(
    worker: WslCodexWorker,
    monkeypatch: pytest.MonkeyPatch,
    *,
    pilot_kind: str,
    tracked_paths: tuple[str, ...],
    allowed_paths: tuple[str, ...],
    changed_paths: tuple[str, ...],
    payloads: dict[str, bytes],
    baseline_payloads: dict[str, bytes] | None = None,
    baseline_read_fails: bool = False,
) -> ShadowPatch | None:
    shadow = "/home/worker/shadow"
    baseline = ("head", "refs", "config")
    worker._runtime_spec = _runtime(worker._canonical_repository / "runtime")
    monkeypatch.setattr(worker, "_shadow_git_control_state", lambda _shadow: baseline)
    head_payloads = payloads if baseline_payloads is None else baseline_payloads

    def fake_text(_platform, argv, **_kwargs):
        command = tuple(argv)
        if "status" in command:
            status = "".join(f" M {path}\0" for path in changed_paths)
            return _completed(list(command), stdout=status)
        if "diff" in command and "--quiet" in command:
            return _completed(list(command))
        if command[:2] == ("/usr/bin/test", "-L"):
            return _completed(list(command), returncode=1)
        if command[:2] == ("/usr/bin/test", "-f"):
            return _completed(list(command))
        if command[0] == "/usr/bin/readlink":
            return _completed(list(command), stdout=f"{command[-1]}\n")
        if command[0] == "/usr/bin/stat":
            return _completed(list(command), stdout="regular file:1\n")
        if "add" in command:
            return _completed(list(command))
        if "diff" in command and "--name-only" in command:
            names = "".join(f"{path}\0" for path in sorted(changed_paths))
            return _completed(list(command), stdout=names)
        raise AssertionError(command)

    def fake_bytes(_platform, argv, **_kwargs):
        command = tuple(argv)
        if command[0] == "/usr/bin/cat":
            relative = command[-1].removeprefix(f"{shadow}/")
            return subprocess.CompletedProcess(
                list(command),
                0,
                payloads[relative],
                b"",
            )
        if "cat-file" in command:
            relative = command[-1].removeprefix("HEAD:")
            if baseline_read_fails or relative not in head_payloads:
                return subprocess.CompletedProcess(list(command), 1, b"", b"")
            return subprocess.CompletedProcess(
                list(command),
                0,
                head_payloads[relative],
                b"",
            )
        if "diff" in command:
            return subprocess.CompletedProcess(
                list(command),
                0,
                b"diff --git a/bounded b/bounded\n",
                b"",
            )
        raise AssertionError(command)

    monkeypatch.setattr(worker, "_run_wsl_text", fake_text)
    monkeypatch.setattr(worker, "_run_wsl_bytes", fake_bytes)
    return worker._validated_shadow_patch(
        shadow,
        tracked_paths,
        allowed_paths,
        baseline,
        pilot_kind=pilot_kind,
    )


def test_wsl_absence_is_bounded_and_path_free(tmp_path: Path):
    worker = WslCodexWorker(
        tmp_path,
        wsl_executable_resolver=lambda: None,
    )

    result = worker.runtime_gate()

    assert result == WslGateResult(False, "wsl_unavailable")
    assert str(tmp_path) not in repr(result)


@pytest.mark.parametrize(
    ("kernel", "home", "expected"),
    [
        ("5.15.0-microsoft-standard-WSL2", "/home/worker", "wsl2_ready"),
        ("4.4.0-microsoft-standard", "/home/worker", "wsl_not_version_2"),
        ("5.15.0-microsoft-standard-WSL2", "/mnt/c/worker", "wsl_native_home_unavailable"),
    ],
)
def test_wsl_discovery_requires_wsl2_and_native_home(
    tmp_path: Path,
    kernel: str,
    home: str,
    expected: str,
):
    executable = _fake_windows_executable(tmp_path / "wsl.exe")
    observed: list[tuple[str, ...]] = []

    def fake_run(argv, **_kwargs):
        arguments = tuple(str(item) for item in argv)
        observed.append(arguments)
        if arguments[-2:] == ("/usr/bin/printenv", "WSL_DISTRO_NAME"):
            return _completed(list(arguments), stdout="BoundedDistro\n")
        if arguments[-2:] == ("/usr/bin/uname", "-r"):
            return _completed(list(arguments), stdout=f"{kernel}\n")
        if arguments[-2:] == ("/usr/bin/printenv", "HOME"):
            return _completed(list(arguments), stdout=f"{home}\n")
        if arguments[-2:] == ("/usr/bin/id", "-un"):
            return _completed(list(arguments), stdout="worker\n")
        if arguments[-5:-1] == ("/usr/bin/stat", "-f", "-c", "%T"):
            return _completed(list(arguments), stdout="ext2/ext3\n")
        raise AssertionError(arguments)

    worker = WslCodexWorker(
        tmp_path,
        wsl_executable_resolver=lambda: executable,
        host_run=fake_run,
    )

    result, platform = worker._discover_platform()

    assert result.category == expected
    assert result.passed is (expected == "wsl2_ready")
    if result.passed:
        assert platform is not None
        assert platform.distro_name == "BoundedDistro"
        assert all("--distribution" in command for command in observed[1:])
        assert "BoundedDistro" not in repr(platform)
        assert home not in repr(platform)


def test_default_distro_failure_is_bounded(tmp_path: Path):
    executable = _fake_windows_executable(tmp_path / "wsl.exe")
    worker = WslCodexWorker(
        tmp_path,
        wsl_executable_resolver=lambda: executable,
        host_run=lambda argv, **_kwargs: _completed(list(argv), 1),
    )

    result, platform = worker._discover_platform()

    assert result == WslGateResult(False, "wsl_default_distro_unavailable")
    assert platform is None


@pytest.mark.parametrize("filesystem", ["9p", "drvfs", "overlay", "tmpfs", "unknown"])
def test_non_ext4_workspace_filesystems_are_rejected(filesystem: str):
    assert not wsl_module._native_linux_filesystem(filesystem)


def test_pinned_official_package_accepts_only_exact_01461():
    manifest = {"name": "@openai/codex", "version": "0.146.1"}
    lock = {
        "packages": {
            "node_modules/@openai/codex": {
                "version": "0.146.1",
                "integrity": "sha512-bounded",
            }
        }
    }

    assert wsl_module._official_pinned_package(manifest, lock)
    manifest["version"] = "0.147.0"
    assert not wsl_module._official_pinned_package(manifest, lock)
    manifest["version"] = "0.146.1"
    lock["packages"]["node_modules/@openai/codex"]["version"] = "0.147.0"
    assert not wsl_module._official_pinned_package(manifest, lock)


@pytest.mark.parametrize(
    "relative",
    ["/usr/bin/codex", "../codex", "runtime/../codex", ""],
)
def test_pinned_runtime_descriptor_rejects_path_escape(relative: str):
    assert (
        wsl_module._pinned_runtime_relative_path(
            {"version": "0.146.1", "relative_path": relative}
        )
        is None
    )


def test_runtime_spec_hides_runtime_distro_and_home_paths(tmp_path: Path):
    spec = _runtime(tmp_path)

    rendered = repr(spec)

    assert str(spec.executable) not in rendered
    assert "BoundedDistro" not in rendered
    assert "/home/worker" not in rendered
    assert spec.version == WSL_CODEX_REQUIRED_VERSION


def test_frozen_runtime_disappearance_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    spec = _runtime(tmp_path)
    worker = WslCodexWorker(tmp_path)
    worker._runtime_spec = spec
    spec.platform.wsl_executable.unlink()

    assert not worker._runtime_is_current(spec)


def test_authentication_unavailable_blocks_before_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    worker = WslCodexWorker(tmp_path)
    spec = _runtime(tmp_path)
    worker._runtime_spec = spec
    worker._runtime_result = WslGateResult(True, "wsl_codex_runtime_ready")
    monkeypatch.setattr(worker, "_runtime_is_current", lambda _spec: True)
    monkeypatch.setattr(
        worker,
        "_run_codex_bounded",
        lambda *_args, **_kwargs: _completed([], 1, "private auth output"),
    )

    result = worker.authentication_gate()

    assert result == WslGateResult(False, "wsl_codex_authentication_unavailable")
    assert "private auth output" not in repr(result)


def test_linux_environment_is_explicit_and_secret_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    worker = WslCodexWorker(tmp_path)
    platform = _platform(tmp_path)

    def fake_printenv(_platform, argv, **_kwargs):
        name = argv[-1]
        if name == "HTTPS_PROXY":
            return _completed(list(argv), stdout="https://proxy.invalid\n")
        return _completed(list(argv), 1)

    monkeypatch.setattr(worker, "_run_wsl_text", fake_printenv)

    environment = worker._linux_codex_environment(
        platform,
        PurePosixPath("/home/worker/.local/share/phoenix/tmp"),
    )

    assert environment is not None
    values = dict(environment)
    assert values["PATH"] == wsl_module.LINUX_PATH
    assert values["HTTPS_PROXY"] == "https://proxy.invalid"
    assert "OPENAI_API_KEY" not in values
    assert "CODEX_API_KEY" not in values
    assert "CODEX_ACCESS_TOKEN" not in values
    assert "CODEX_THREAD_ID" not in values
    assert "UNRELATED_SECRET" not in values


@pytest.mark.parametrize(
    "paths",
    [
        ("/absolute.md",),
        ("../parent.md",),
        ("safe/../../escape.md",),
        ("docs/name:stream.md",),
        ("docs/CON.md",),
        ("docs/name. ",),
        ("docs/status.md", "DOCS/STATUS.md"),
        ("docs/cafe\u0301.md",),
        ("docs\\status.md",),
    ],
)
def test_transfer_path_validation_rejects_cross_platform_hazards(
    paths: tuple[str, ...],
):
    with pytest.raises(ValueError, match="transfer path|colliding"):
        validate_transfer_paths(paths)


def test_transfer_path_validation_is_sorted_and_deterministic():
    assert validate_transfer_paths(("docs/z.md", "docs/a.md")) == (
        "docs/a.md",
        "docs/z.md",
    )


def test_windows_snapshot_contains_only_explicit_worker_visible_paths(tmp_path: Path):
    repository, head = _repository(tmp_path)
    control = repository / "claim-state.sqlite3"
    control.write_bytes(b"not business data")
    _git(repository, "add", "claim-state.sqlite3")
    _git(repository, "commit", "--amend", "--quiet", "--no-edit")
    head = _git(repository, "rev-parse", "HEAD")

    visible = (DOCS_PATH,)
    first = build_windows_snapshot(
        repository,
        head,
        visible,
        pilot_kind=CODEX_PILOT_DOCS_ONLY_KIND,
    )
    second = build_windows_snapshot(
        repository,
        head,
        visible,
        pilot_kind=CODEX_PILOT_DOCS_ONLY_KIND,
    )

    assert first == second
    assert first.tracked_paths == visible
    assert first.pilot_kind == CODEX_PILOT_DOCS_ONLY_KIND
    with tarfile.open(fileobj=io.BytesIO(first.archive), mode="r:") as archive:
        names = tuple(archive.getnames())
    assert names == visible
    assert "src/safe.py" not in names
    assert "claim-state.sqlite3" not in names
    assert all(not name.startswith(".git") for name in names)


def test_docs_snapshot_rejects_python_paths(tmp_path: Path):
    repository, head = _python_repository(tmp_path)

    with pytest.raises(ValueError, match="worker-visible paths are invalid"):
        build_windows_snapshot(
            repository,
            head,
            PYTHON_PATHS,
            pilot_kind=CODEX_PILOT_DOCS_ONLY_KIND,
        )


def test_bounded_python_snapshot_accepts_exact_authorized_set(tmp_path: Path):
    repository, head = _python_repository(tmp_path)

    snapshot = build_windows_snapshot(
        repository,
        head,
        PYTHON_PATHS,
        pilot_kind=CODEX_PILOT_BOUNDED_PYTHON_KIND,
    )

    assert snapshot.pilot_kind == CODEX_PILOT_BOUNDED_PYTHON_KIND
    assert snapshot.tracked_paths == PYTHON_PATHS
    with tarfile.open(fileobj=io.BytesIO(snapshot.archive), mode="r:") as archive:
        assert tuple(archive.getnames()) == PYTHON_PATHS


def test_bounded_python_snapshot_rejects_markdown(tmp_path: Path):
    repository, head = _python_repository(tmp_path)

    with pytest.raises(ValueError, match="worker-visible paths are invalid"):
        build_windows_snapshot(
            repository,
            head,
            (DOCS_PATH,),
            pilot_kind=CODEX_PILOT_BOUNDED_PYTHON_KIND,
        )


def test_snapshot_rejects_unknown_pilot_kind(tmp_path: Path):
    repository, head = _repository(tmp_path)

    with pytest.raises(ValueError, match="worker-visible paths are invalid"):
        build_windows_snapshot(
            repository,
            head,
            (DOCS_PATH,),
            pilot_kind="unknown-supervised",
        )


def test_snapshot_match_is_bound_to_explicit_pilot_kind(tmp_path: Path):
    repository, head = _repository(tmp_path)
    snapshot = build_windows_snapshot(
        repository,
        head,
        (DOCS_PATH,),
        pilot_kind=CODEX_PILOT_DOCS_ONLY_KIND,
    )
    mismatched = WindowsSnapshot(
        snapshot.archive,
        snapshot.digest,
        snapshot.tracked_paths,
        CODEX_PILOT_BOUNDED_PYTHON_KIND,
        snapshot.source_state_digest,
    )

    assert windows_snapshot_matches(repository, head, snapshot)
    assert not windows_snapshot_matches(repository, head, mismatched)


def test_windows_snapshot_requires_each_visible_path_at_reviewed_base(tmp_path: Path):
    repository, head = _repository(tmp_path)

    with pytest.raises(ValueError, match="source is unavailable"):
        build_windows_snapshot(
            repository,
            head,
            ("docs/process/missing.md",),
            pilot_kind=CODEX_PILOT_DOCS_ONLY_KIND,
        )


def test_windows_snapshot_rejects_symlink_or_hardlink(tmp_path: Path):
    repository, _head = _repository(tmp_path)
    target = repository / DOCS_PATH
    linked = repository / "docs" / "process" / "linked.md"
    try:
        os.link(target, linked)
    except OSError:
        pytest.skip("host does not permit hardlinks")
    _git(repository, "add", "docs/process/linked.md")
    _git(repository, "commit", "--quiet", "-m", "hardlink")
    head = _git(repository, "rev-parse", "HEAD")

    with pytest.raises(ValueError, match="unsafe tracked file"):
        build_windows_snapshot(
            repository,
            head,
            (DOCS_PATH,),
            pilot_kind=CODEX_PILOT_DOCS_ONLY_KIND,
        )


def test_windows_snapshot_rejects_submodule_index_entry(tmp_path: Path):
    repository, head = _repository(tmp_path)
    _git(
        repository,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{head},vendor/module",
    )
    tree = _git(repository, "write-tree")
    commit = _git(repository, "commit-tree", tree, "-p", head, "-m", "submodule")
    _git(repository, "reset", "--hard", commit)

    with pytest.raises(ValueError, match="unsupported tracked object"):
        build_windows_snapshot(
            repository,
            commit,
            (DOCS_PATH,),
            pilot_kind=CODEX_PILOT_DOCS_ONLY_KIND,
        )


@pytest.mark.parametrize(
    ("name", "entry_type", "linkname"),
    [
        ("../escape.md", tarfile.REGTYPE, ""),
        ("/absolute.md", tarfile.REGTYPE, ""),
        ("docs/link.md", tarfile.SYMTYPE, "docs/status.md"),
        ("docs/hardlink.md", tarfile.LNKTYPE, "docs/status.md"),
        ("docs/device.md", tarfile.CHRTYPE, ""),
        ("docs/fifo.md", tarfile.FIFOTYPE, ""),
    ],
)
def test_snapshot_archive_rejects_traversal_links_and_special_files(
    name: str,
    entry_type: bytes,
    linkname: str,
):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        info = tarfile.TarInfo(name)
        info.type = entry_type
        info.linkname = linkname
        payload = b"bounded\n" if entry_type == tarfile.REGTYPE else b""
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))

    assert not validate_snapshot_archive(buffer.getvalue(), (name,))


def test_snapshot_match_detects_windows_change_during_worker(tmp_path: Path):
    repository, head = _repository(tmp_path)
    snapshot = build_windows_snapshot(
        repository,
        head,
        (DOCS_PATH,),
        pilot_kind=CODEX_PILOT_DOCS_ONLY_KIND,
    )
    assert windows_snapshot_matches(repository, head, snapshot)

    (repository / "src" / "safe.py").write_text("VALUE = 2\n", encoding="utf-8")

    assert not windows_snapshot_matches(repository, head, snapshot)


def test_shadow_patch_rejects_unlisted_changed_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    worker = WslCodexWorker(tmp_path)
    worker._runtime_spec = _runtime(tmp_path / "runtime")
    baseline = ("head", "refs", "config")
    monkeypatch.setattr(worker, "_shadow_git_control_state", lambda _shadow: baseline)

    def fake_run(_platform, argv, **_kwargs):
        if "status" in argv:
            return _completed(list(argv), stdout="?? docs/unlisted.md\0")
        if "diff" in argv and "--quiet" in argv:
            return _completed(list(argv))
        raise AssertionError(argv)

    monkeypatch.setattr(worker, "_run_wsl_text", fake_run)

    assert worker._validated_shadow_patch(
        "/home/worker/shadow",
        (DOCS_PATH,),
        (DOCS_PATH,),
        baseline,
        pilot_kind=CODEX_PILOT_DOCS_ONLY_KIND,
    ) is None


def test_docs_shadow_patch_accepts_markdown_compatibly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    worker = WslCodexWorker(tmp_path)

    patch = _simulated_shadow_patch(
        worker,
        monkeypatch,
        pilot_kind=CODEX_PILOT_DOCS_ONLY_KIND,
        tracked_paths=(DOCS_PATH,),
        allowed_paths=(DOCS_PATH,),
        changed_paths=(DOCS_PATH,),
        payloads={DOCS_PATH: b"Updated documentation.\n"},
    )

    assert patch is not None
    assert patch.changed_paths == (DOCS_PATH,)


def test_docs_shadow_patch_preserves_whole_file_sensitive_rejection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    worker = WslCodexWorker(tmp_path)

    assert _simulated_shadow_patch(
        worker,
        monkeypatch,
        pilot_kind=CODEX_PILOT_DOCS_ONLY_KIND,
        tracked_paths=(DOCS_PATH,),
        allowed_paths=(DOCS_PATH,),
        changed_paths=(DOCS_PATH,),
        payloads={DOCS_PATH: b"token=preexisting-synthetic-value\n"},
    ) is None


def test_docs_shadow_patch_rejects_python_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    worker = WslCodexWorker(tmp_path)

    assert _simulated_shadow_patch(
        worker,
        monkeypatch,
        pilot_kind=CODEX_PILOT_DOCS_ONLY_KIND,
        tracked_paths=(DOCS_PATH,),
        allowed_paths=(DOCS_PATH,),
        changed_paths=(PYTHON_PATHS[0],),
        payloads={PYTHON_PATHS[0]: b"VALUE = 2\n"},
    ) is None


def test_bounded_python_shadow_patch_accepts_exact_authorized_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    worker = WslCodexWorker(tmp_path)

    patch = _simulated_shadow_patch(
        worker,
        monkeypatch,
        pilot_kind=CODEX_PILOT_BOUNDED_PYTHON_KIND,
        tracked_paths=PYTHON_PATHS,
        allowed_paths=PYTHON_PATHS,
        changed_paths=PYTHON_PATHS,
        payloads={path: b"def bounded_value():\n    return 2\n" for path in PYTHON_PATHS},
    )

    assert patch is not None
    assert patch.changed_paths == PYTHON_PATHS


def test_bounded_python_shadow_patch_allows_unchanged_sensitive_finding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    worker = WslCodexWorker(tmp_path)
    baseline = b"token=synthetic-fixture-value\nVALUE = 1\n"
    resulting = b"token=synthetic-fixture-value\nVALUE = 2\n"

    assert _simulated_shadow_patch(
        worker,
        monkeypatch,
        pilot_kind=CODEX_PILOT_BOUNDED_PYTHON_KIND,
        tracked_paths=PYTHON_PATHS,
        allowed_paths=PYTHON_PATHS,
        changed_paths=(PYTHON_PATHS[0],),
        payloads={PYTHON_PATHS[0]: resulting},
        baseline_payloads={PYTHON_PATHS[0]: baseline},
    ) is not None


def test_bounded_python_shadow_patch_allows_moved_sensitive_finding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    worker = WslCodexWorker(tmp_path)
    baseline = b"token=synthetic-fixture-value\nVALUE = 1\n"
    resulting = b"VALUE = 2\ntoken=synthetic-fixture-value\n"

    assert _simulated_shadow_patch(
        worker,
        monkeypatch,
        pilot_kind=CODEX_PILOT_BOUNDED_PYTHON_KIND,
        tracked_paths=PYTHON_PATHS,
        allowed_paths=PYTHON_PATHS,
        changed_paths=(PYTHON_PATHS[0],),
        payloads={PYTHON_PATHS[0]: resulting},
        baseline_payloads={PYTHON_PATHS[0]: baseline},
    ) is not None


def test_bounded_python_shadow_patch_allows_task081_style_existing_regex(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    worker = WslCodexWorker(tmp_path)
    baseline = (
        b'SENSITIVE = re.compile(r"(?i)(?:[A-Z]:\\\\Users\\\\|/home/|/Users/)'
        b'[^\\s`]+")\n'
    )
    resulting = baseline + b"\ndef reject_self_dependency():\n    return True\n"
    assert any(
        pattern.search(baseline.decode()) for pattern in wsl_module._SENSITIVE_PATTERNS
    )

    assert _simulated_shadow_patch(
        worker,
        monkeypatch,
        pilot_kind=CODEX_PILOT_BOUNDED_PYTHON_KIND,
        tracked_paths=PYTHON_PATHS,
        allowed_paths=PYTHON_PATHS,
        changed_paths=(PYTHON_PATHS[0],),
        payloads={PYTHON_PATHS[0]: resulting},
        baseline_payloads={PYTHON_PATHS[0]: baseline},
    ) is not None


def test_bounded_python_shadow_patch_rejects_new_sensitive_finding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    worker = WslCodexWorker(tmp_path)

    assert _simulated_shadow_patch(
        worker,
        monkeypatch,
        pilot_kind=CODEX_PILOT_BOUNDED_PYTHON_KIND,
        tracked_paths=PYTHON_PATHS,
        allowed_paths=PYTHON_PATHS,
        changed_paths=(PYTHON_PATHS[0],),
        payloads={PYTHON_PATHS[0]: b"token=new-synthetic-value\n"},
        baseline_payloads={PYTHON_PATHS[0]: b"VALUE = 1\n"},
    ) is None


def test_bounded_python_shadow_patch_rejects_duplicated_sensitive_finding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    worker = WslCodexWorker(tmp_path)
    finding = b"token=synthetic-fixture-value\n"

    assert _simulated_shadow_patch(
        worker,
        monkeypatch,
        pilot_kind=CODEX_PILOT_BOUNDED_PYTHON_KIND,
        tracked_paths=PYTHON_PATHS,
        allowed_paths=PYTHON_PATHS,
        changed_paths=(PYTHON_PATHS[0],),
        payloads={PYTHON_PATHS[0]: finding + finding},
        baseline_payloads={PYTHON_PATHS[0]: finding},
    ) is None


def test_bounded_python_shadow_patch_rejects_changed_sensitive_finding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    worker = WslCodexWorker(tmp_path)

    assert _simulated_shadow_patch(
        worker,
        monkeypatch,
        pilot_kind=CODEX_PILOT_BOUNDED_PYTHON_KIND,
        tracked_paths=PYTHON_PATHS,
        allowed_paths=PYTHON_PATHS,
        changed_paths=(PYTHON_PATHS[0],),
        payloads={PYTHON_PATHS[0]: b"token=new-synthetic-value\n"},
        baseline_payloads={PYTHON_PATHS[0]: b"token=old-synthetic-value\n"},
    ) is None


def test_bounded_python_shadow_patch_rejects_baseline_read_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    worker = WslCodexWorker(tmp_path)

    assert _simulated_shadow_patch(
        worker,
        monkeypatch,
        pilot_kind=CODEX_PILOT_BOUNDED_PYTHON_KIND,
        tracked_paths=PYTHON_PATHS,
        allowed_paths=PYTHON_PATHS,
        changed_paths=(PYTHON_PATHS[0],),
        payloads={PYTHON_PATHS[0]: b"VALUE = 2\n"},
        baseline_read_fails=True,
    ) is None


@pytest.mark.parametrize(
    "baseline_payload",
    [
        pytest.param(b"\xff", id="non-utf8"),
        pytest.param(b"VALUE = 1\0\n", id="nul"),
    ],
)
def test_bounded_python_shadow_patch_rejects_unsafe_baseline_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    baseline_payload: bytes,
):
    worker = WslCodexWorker(tmp_path)

    assert _simulated_shadow_patch(
        worker,
        monkeypatch,
        pilot_kind=CODEX_PILOT_BOUNDED_PYTHON_KIND,
        tracked_paths=PYTHON_PATHS,
        allowed_paths=PYTHON_PATHS,
        changed_paths=(PYTHON_PATHS[0],),
        payloads={PYTHON_PATHS[0]: b"VALUE = 2\n"},
        baseline_payloads={PYTHON_PATHS[0]: baseline_payload},
    ) is None


def test_bounded_python_shadow_patch_rejects_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    worker = WslCodexWorker(tmp_path)

    assert _simulated_shadow_patch(
        worker,
        monkeypatch,
        pilot_kind=CODEX_PILOT_BOUNDED_PYTHON_KIND,
        tracked_paths=PYTHON_PATHS,
        allowed_paths=PYTHON_PATHS,
        changed_paths=(DOCS_PATH,),
        payloads={DOCS_PATH: b"Updated documentation.\n"},
    ) is None


def test_bounded_python_shadow_patch_rejects_outside_allowlist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    worker = WslCodexWorker(tmp_path)
    outside = "tests/test_codex_runner.py"

    assert _simulated_shadow_patch(
        worker,
        monkeypatch,
        pilot_kind=CODEX_PILOT_BOUNDED_PYTHON_KIND,
        tracked_paths=PYTHON_PATHS,
        allowed_paths=PYTHON_PATHS,
        changed_paths=(outside,),
        payloads={outside: b"def changed():\n    return True\n"},
    ) is None


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(b"\xff", id="non-utf8"),
        pytest.param(b"VALUE = 'bounded'\0\n", id="nul"),
    ],
)
def test_bounded_python_shadow_patch_rejects_unsafe_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
):
    worker = WslCodexWorker(tmp_path)

    assert _simulated_shadow_patch(
        worker,
        monkeypatch,
        pilot_kind=CODEX_PILOT_BOUNDED_PYTHON_KIND,
        tracked_paths=PYTHON_PATHS,
        allowed_paths=PYTHON_PATHS,
        changed_paths=(PYTHON_PATHS[0],),
        payloads={PYTHON_PATHS[0]: payload},
    ) is None


def test_shadow_patch_rejects_unknown_pilot_kind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    worker = WslCodexWorker(tmp_path)

    assert _simulated_shadow_patch(
        worker,
        monkeypatch,
        pilot_kind="unknown-supervised",
        tracked_paths=(DOCS_PATH,),
        allowed_paths=(DOCS_PATH,),
        changed_paths=(DOCS_PATH,),
        payloads={DOCS_PATH: b"Updated documentation.\n"},
    ) is None


def test_validated_patch_applies_only_to_disposable_windows_worktree(tmp_path: Path):
    canonical, head = _repository(tmp_path)
    worktree = tmp_path / "task-worktree"
    _git(canonical, "worktree", "add", "--quiet", "-b", "codex/test", str(worktree), head)
    shadow = tmp_path / "shadow"
    _git(canonical, "clone", "--quiet", str(canonical), str(shadow))
    changed = shadow / DOCS_PATH
    changed.write_text("Updated only in shadow.\n", encoding="utf-8")
    patch = subprocess.run(
        ["git", "diff", "--binary", "--full-index", "--no-renames"],
        cwd=shadow,
        check=True,
        capture_output=True,
    ).stdout
    validated = ShadowPatch(patch, (DOCS_PATH,))

    assert apply_shadow_patch(worktree, validated)
    assert (worktree / DOCS_PATH).read_text(encoding="utf-8") == (
        "Updated only in shadow.\n"
    )
    assert (canonical / DOCS_PATH).read_text(encoding="utf-8") == (
        "Initial status.\n"
    )


def test_apply_patch_rejects_dirty_destination(tmp_path: Path):
    repository, _head = _repository(tmp_path)
    (repository / DOCS_PATH).write_text("Dirty.\n", encoding="utf-8")

    assert not apply_shadow_patch(
        repository,
        ShadowPatch(b"not a patch", (DOCS_PATH,)),
    )


def test_shadow_success_requires_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repository, head = _repository(tmp_path)
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    worker = WslCodexWorker(canonical)
    worker._runtime_spec = _runtime(tmp_path / "runtime")
    worker._runtime_result = WslGateResult(True, "wsl_codex_runtime_ready")
    worker._capability_result = WslCapabilityResult(
        True,
        "wsl_workspace_write_capability_proved",
    )
    monkeypatch.setattr(worker, "_runtime_is_current", lambda _spec: True)
    monkeypatch.setattr(worker, "_create_native_workspace", lambda _purpose: "/home/w/shadow")
    extracted_paths: list[tuple[str, ...]] = []

    def extract(_shadow, archive, paths):
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as payload:
            assert tuple(payload.getnames()) == (DOCS_PATH,)
        extracted_paths.append(paths)
        return True

    monkeypatch.setattr(worker, "_extract_snapshot", extract)
    monkeypatch.setattr(worker, "_initialize_snapshot_git", lambda *_args: True)
    monkeypatch.setattr(worker, "_shadow_git_control_state", lambda *_args: ("a", "b", "c"))
    monkeypatch.setattr(
        worker,
        "_run_model",
        lambda **_kwargs: (
            WslExecutionResult(
                "succeeded",
                "ok",
                3,
                input_tokens=2,
                cached_input_tokens=1,
                output_tokens=1,
                reasoning_output_tokens=1,
            ),
            (),
        ),
    )
    monkeypatch.setattr(wsl_module, "windows_snapshot_matches", lambda *_args: True)
    monkeypatch.setattr(
        worker,
        "_validated_shadow_patch",
        lambda *_args, **_kwargs: ShadowPatch(b"patch", (DOCS_PATH,)),
    )
    monkeypatch.setattr(wsl_module, "apply_shadow_patch", lambda *_args: True)
    monkeypatch.setattr(worker, "_cleanup_native_workspace", lambda *_args: False)

    result = worker.invoke_codex(
        windows_worktree=repository,
        base_commit_sha=head,
        allowed_paths=(DOCS_PATH,),
        pilot_kind=CODEX_PILOT_DOCS_ONLY_KIND,
        prompt="bounded prompt",
        timeout_seconds=30,
        on_started=lambda: None,
    )

    assert result == WslExecutionResult(
        "failed",
        "wsl_temp_cleanup_failed",
        3,
        input_tokens=2,
        cached_input_tokens=1,
        output_tokens=1,
        reasoning_output_tokens=1,
    )
    assert extracted_paths == [(DOCS_PATH,)]
    assert worker.last_transfer_evidence.patch_applied
    assert not worker.last_transfer_evidence.temp_cleanup


def test_docs_model_argv_remains_unchanged_without_reasoning_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    arguments = _captured_model_codex_arguments(
        tmp_path,
        monkeypatch,
        CODEX_PILOT_DOCS_ONLY_KIND,
    )

    assert arguments == _expected_docs_model_arguments("/home/worker/shadow")
    assert not any("reasoning" in argument for argument in arguments)


def test_bounded_python_model_argv_pins_only_medium_reasoning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    arguments = _captured_model_codex_arguments(
        tmp_path,
        monkeypatch,
        CODEX_PILOT_BOUNDED_PYTHON_KIND,
    )
    expected = list(_expected_docs_model_arguments("/home/worker/shadow"))
    insertion_index = expected.index("--cd")
    expected[insertion_index:insertion_index] = [
        "-c",
        'model_reasoning_effort="medium"',
    ]

    assert arguments == tuple(expected)
    assert arguments.count('model_reasoning_effort="medium"') == 1
    assert "--model" not in arguments
    assert not any(argument.startswith("model=") for argument in arguments)
    assert not any("provider" in argument for argument in arguments)


def test_unknown_model_pilot_kind_fails_before_process_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    def fail_launch(*_args, **_kwargs):
        pytest.fail("unknown pilot kind must fail before model launch")

    worker = WslCodexWorker(tmp_path, host_popen=fail_launch)
    worker._runtime_spec = _runtime(tmp_path / "runtime")
    monkeypatch.setattr(worker, "_runtime_is_current", lambda _spec: True)
    monkeypatch.setattr(
        worker,
        "_prepare_invocation_control",
        lambda _platform: pytest.fail(
            "unknown pilot kind must fail before invocation control setup"
        ),
    )

    result, messages = worker._run_model(
        workspace="/home/worker/shadow",
        prompt="bounded",
        timeout_seconds=30,
        on_started=lambda: None,
        pilot_kind="unknown-supervised",
    )

    assert result == WslExecutionResult("failed", "wsl_codex_pilot_kind_invalid")
    assert messages == ()


def test_model_cancellation_terminates_target_and_proves_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    process = _FakeModelProcess(KeyboardInterrupt())
    worker, control = _controlled_model_worker(tmp_path, monkeypatch, process)
    observed: list[WslInvocationControl] = []

    def stop_target(_process, selected):
        observed.append(selected)
        return WslProcessStopResult(True, True, True, True)

    monkeypatch.setattr(worker, "_stop_targeted_linux_invocation", stop_target)

    result, messages = worker._run_model(
        workspace="/home/worker/shadow",
        prompt="bounded",
        timeout_seconds=30,
        on_started=lambda: None,
        pilot_kind=CODEX_PILOT_DOCS_ONLY_KIND,
    )

    assert result == WslExecutionResult("cancelled", "wsl_codex_cancelled")
    assert result.worker_exit_proved
    assert messages == ()
    assert observed == [control]


@pytest.mark.parametrize(
    "stop_result",
    [
        pytest.param(
            WslProcessStopResult(True, False, False, False),
            id="target-termination-failed",
        ),
        pytest.param(
            WslProcessStopResult(True, True, False, False),
            id="target-exit-proof-failed",
        ),
    ],
)
def test_model_cancellation_fails_closed_when_process_control_is_uncertain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stop_result: WslProcessStopResult,
):
    worker, _control = _controlled_model_worker(
        tmp_path,
        monkeypatch,
        _FakeModelProcess(KeyboardInterrupt()),
    )
    monkeypatch.setattr(
        worker,
        "_stop_targeted_linux_invocation",
        lambda *_args: stop_result,
    )

    result, messages = worker._run_model(
        workspace="/home/worker/shadow",
        prompt="bounded",
        timeout_seconds=30,
        on_started=lambda: None,
        pilot_kind=CODEX_PILOT_DOCS_ONLY_KIND,
    )

    assert result.category == "wsl_process_control_uncertain"
    assert result.status == "failed"
    assert not result.worker_exit_proved
    assert messages == ()


def test_model_timeout_requires_target_exit_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    process = _FakeModelProcess(subprocess.TimeoutExpired("wsl", 30))
    worker, _control = _controlled_model_worker(tmp_path, monkeypatch, process)
    monkeypatch.setattr(
        worker,
        "_stop_targeted_linux_invocation",
        lambda *_args: WslProcessStopResult(True, True, True, True),
    )

    result, messages = worker._run_model(
        workspace="/home/worker/shadow",
        prompt="bounded",
        timeout_seconds=30,
        on_started=lambda: None,
        pilot_kind=CODEX_PILOT_DOCS_ONLY_KIND,
    )

    assert result == WslExecutionResult("timed_out", "wsl_codex_timed_out")
    assert result.worker_exit_proved
    assert messages == ()


def test_model_timeout_fails_closed_when_target_exit_is_unproved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    process = _FakeModelProcess(subprocess.TimeoutExpired("wsl", 30))
    worker, _control = _controlled_model_worker(tmp_path, monkeypatch, process)
    monkeypatch.setattr(
        worker,
        "_stop_targeted_linux_invocation",
        lambda *_args: WslProcessStopResult(True, True, False, False),
    )

    result, messages = worker._run_model(
        workspace="/home/worker/shadow",
        prompt="bounded",
        timeout_seconds=30,
        on_started=lambda: None,
        pilot_kind=CODEX_PILOT_DOCS_ONLY_KIND,
    )

    assert result.category == "wsl_process_control_uncertain"
    assert result.status == "failed"
    assert not result.worker_exit_proved
    assert messages == ()


def test_invocation_start_audit_failure_terminates_and_proves_target_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    worker, _control = _controlled_model_worker(
        tmp_path,
        monkeypatch,
        _FakeModelProcess(("", "")),
    )
    stops: list[bool] = []

    def stop_target(*_args):
        stops.append(True)
        return WslProcessStopResult(True, True, True, True)

    monkeypatch.setattr(worker, "_stop_targeted_linux_invocation", stop_target)

    def audit_failure():
        raise RuntimeError("bounded injected audit failure")

    result, messages = worker._run_model(
        workspace="/home/worker/shadow",
        prompt="bounded",
        timeout_seconds=30,
        on_started=audit_failure,
        pilot_kind=CODEX_PILOT_DOCS_ONLY_KIND,
    )

    assert result == WslExecutionResult("failed", "invocation_start_audit_failed")
    assert result.worker_exit_proved
    assert stops == [True]
    assert messages == ()


def test_model_success_still_requires_guest_exit_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    stdout = (
        '{"type":"turn.completed","usage":{"total_tokens":7,'
        '"input_tokens":5,"cached_input_tokens":2,"output_tokens":2,'
        '"reasoning_output_tokens":1}}\n'
    )
    worker, _control = _controlled_model_worker(
        tmp_path,
        monkeypatch,
        _FakeModelProcess((stdout, "")),
    )
    proofs: list[bool] = []
    cleanups: list[bool] = []
    monkeypatch.setattr(
        worker,
        "_prove_linux_invocation_exit",
        lambda _control: proofs.append(True) or True,
    )
    monkeypatch.setattr(
        worker,
        "_cleanup_invocation_control",
        lambda _control: cleanups.append(True) or True,
    )

    result, messages = worker._run_model(
        workspace="/home/worker/shadow",
        prompt="bounded",
        timeout_seconds=30,
        on_started=lambda: None,
        pilot_kind=CODEX_PILOT_DOCS_ONLY_KIND,
    )

    assert result == WslExecutionResult(
        "succeeded",
        "wsl_codex_completed",
        7,
        input_tokens=5,
        cached_input_tokens=2,
        output_tokens=2,
        reasoning_output_tokens=1,
    )
    assert proofs == [True]
    assert cleanups == [True]
    assert messages == ()


def test_codex_usage_components_are_bounded_and_total_remains_authoritative():
    valid = wsl_module._parse_codex_jsonl(
        '{"type":"turn.completed","usage":{"total_tokens":100,'
        '"input_tokens":60,"cached_input_tokens":40,"output_tokens":30,'
        '"reasoning_output_tokens":20}}\n'
    )
    missing = wsl_module._parse_codex_jsonl(
        '{"type":"turn.completed","usage":{"total_tokens":9}}\n'
    )
    malformed = wsl_module._parse_codex_jsonl(
        '{"type":"turn.completed","usage":{"total_tokens":101,'
        '"input_tokens":-1,"cached_input_tokens":true,'
        '"output_tokens":1000000001,"reasoning_output_tokens":"20"}}\n'
    )
    fallback = wsl_module._parse_codex_jsonl(
        '{"type":"turn.completed","usage":'
        '{"input_tokens":3,"output_tokens":4}}\n'
    )
    malformed_total = wsl_module._parse_codex_jsonl(
        '{"type":"turn.completed","usage":{"total_tokens":"invalid"}}\n'
    )

    assert valid["usage_tokens"] == 100
    assert valid["input_tokens"] == 60
    assert valid["cached_input_tokens"] == 40
    assert valid["output_tokens"] == 30
    assert valid["reasoning_output_tokens"] == 20
    assert valid["usage_tokens"] != sum(
        int(valid[field])
        for field in (
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
        )
    )
    assert all(
        missing[field] is None
        for field in (
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
        )
    )
    assert malformed["usage_tokens"] == 101
    assert all(
        malformed[field] is None
        for field in (
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
        )
    )
    assert fallback["usage_tokens"] == 7
    assert malformed_total["usage_tokens"] is None


def test_only_final_turn_completed_usage_object_is_parsed_once(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[object] = []
    original = wsl_module._codex_usage_telemetry

    def observe(value: object) -> dict[str, int | None]:
        calls.append(value)
        return original(value)

    monkeypatch.setattr(wsl_module, "_codex_usage_telemetry", observe)

    result = wsl_module._parse_codex_jsonl(
        '{"type":"turn.completed","usage":{"total_tokens":3}}\n'
        '{"type":"turn.completed","usage":{"total_tokens":5,'
        '"input_tokens":4}}\n'
    )

    assert result["usage_tokens"] == 5
    assert result["input_tokens"] == 4
    assert calls == [{"total_tokens": 5, "input_tokens": 4}]


def test_targeted_stop_uses_only_selected_invocation_control(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    process = _FakeModelProcess(("", ""))
    worker, target = _controlled_model_worker(tmp_path, monkeypatch, process)
    unrelated = WslInvocationControl(
        "b" * 32,
        PurePosixPath("/home/worker/.local/share/phoenix/task-064-invocations/b"),
        PurePosixPath(
            "/home/worker/.local/share/phoenix/task-064-invocations/b/"
            "invocation.json"
        ),
    )
    targeted: list[WslInvocationControl] = []
    monkeypatch.setattr(wsl_module, "_terminate_process", lambda _process: True)
    monkeypatch.setattr(
        worker,
        "_terminate_linux_invocation",
        lambda control: targeted.append(control) or True,
    )
    monkeypatch.setattr(
        worker,
        "_prove_linux_invocation_exit",
        lambda control: targeted.append(control) or True,
    )
    monkeypatch.setattr(
        worker,
        "_cleanup_invocation_control",
        lambda control: targeted.append(control) or True,
    )

    result = worker._stop_targeted_linux_invocation(process, target)

    assert result == WslProcessStopResult(True, True, True, True)
    assert targeted == [target, target, target]
    assert unrelated not in targeted


def test_shadow_cleanup_is_withheld_when_worker_exit_is_unproved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repository, head = _repository(tmp_path)
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    worker = WslCodexWorker(canonical)
    worker._runtime_spec = _runtime(tmp_path / "runtime")
    worker._runtime_result = WslGateResult(True, "wsl_codex_runtime_ready")
    worker._capability_result = WslCapabilityResult(
        True,
        "wsl_workspace_write_capability_proved",
    )
    monkeypatch.setattr(worker, "_runtime_is_current", lambda _spec: True)
    monkeypatch.setattr(worker, "_create_native_workspace", lambda _purpose: "/home/w/shadow")
    monkeypatch.setattr(worker, "_extract_snapshot", lambda *_args: True)
    monkeypatch.setattr(worker, "_initialize_snapshot_git", lambda *_args: True)
    monkeypatch.setattr(worker, "_shadow_git_control_state", lambda *_args: ("a", "b", "c"))
    monkeypatch.setattr(
        worker,
        "_run_model",
        lambda **_kwargs: (
            WslExecutionResult(
                "failed",
                "wsl_process_control_uncertain",
                worker_exit_proved=False,
            ),
            (),
        ),
    )
    monkeypatch.setattr(
        wsl_module,
        "windows_snapshot_matches",
        lambda *_args: pytest.fail("Windows diff checks must wait for worker exit"),
    )
    cleanups: list[str] = []
    monkeypatch.setattr(
        worker,
        "_cleanup_native_workspace",
        lambda workspace: cleanups.append(workspace) or True,
    )

    result = worker.invoke_codex(
        windows_worktree=repository,
        base_commit_sha=head,
        allowed_paths=(DOCS_PATH,),
        pilot_kind=CODEX_PILOT_DOCS_ONLY_KIND,
        prompt="bounded prompt",
        timeout_seconds=30,
        on_started=lambda: None,
    )

    assert result.category == "wsl_process_control_uncertain"
    assert not result.worker_exit_proved
    assert cleanups == []
    assert not worker.last_transfer_evidence.temp_cleanup


def test_transport_cleanup_and_git_status_wait_for_worker_exit_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    worker = WslCodexWorker(tmp_path)
    monkeypatch.setattr(
        worker,
        "authentication_gate",
        lambda: WslGateResult(True, "wsl_codex_authenticated"),
    )
    monkeypatch.setattr(
        worker,
        "_create_native_workspace",
        lambda _purpose: "/home/worker/transport",
    )
    monkeypatch.setattr(worker, "_initialize_shadow_git", lambda *_args: True)
    monkeypatch.setattr(
        worker,
        "_run_model",
        lambda **_kwargs: (
            WslExecutionResult(
                "failed",
                "wsl_process_control_uncertain",
                worker_exit_proved=False,
            ),
            (),
        ),
    )
    monkeypatch.setattr(
        worker,
        "_run_wsl_text",
        lambda *_args, **_kwargs: pytest.fail(
            "Git status must not race an unproved worker exit"
        ),
    )
    cleanups: list[str] = []
    monkeypatch.setattr(
        worker,
        "_cleanup_native_workspace",
        lambda workspace: cleanups.append(workspace) or True,
    )

    result = worker.transport_gate(30)

    assert result == WslGateResult(False, "wsl_process_control_uncertain")
    assert cleanups == []


def test_worker_source_has_no_shell_wrappers_or_unsafe_fallbacks():
    source = inspect.getsource(wsl_module)

    assert "shell=True" not in source
    assert '"sh", "-c"' not in source
    assert '"bash", "-c"' not in source
    assert "danger-full-access" not in source
    assert "dangerously-bypass-approvals-and-sandbox" not in source
    assert "--yolo" not in source
    assert "wsl.exe --terminate" not in source
    assert '"--terminate"' not in source
    assert "pkill" not in source
    assert "killall" not in source
    assert "os.killpg(pgid" in source
    assert "0.147.0" not in inspect.getsource(WslCodexWorker)
    assert "shutil.which(\"codex\")" not in source


def test_snapshot_digest_is_content_bound(tmp_path: Path):
    repository, head = _repository(tmp_path)
    snapshot = build_windows_snapshot(
        repository,
        head,
        (DOCS_PATH,),
        pilot_kind=CODEX_PILOT_DOCS_ONLY_KIND,
    )

    expected = hashlib.sha256()
    expected.update(DOCS_PATH.encode("utf-8"))
    expected.update(b"\0")
    expected.update(b"100644\0")
    expected.update((repository / DOCS_PATH).read_bytes())
    assert snapshot.digest == expected.hexdigest()

    expected_source = hashlib.sha256()
    for relative in (DOCS_PATH, "src/safe.py"):
        expected_source.update(relative.encode("utf-8"))
        expected_source.update(b"\0")
        expected_source.update(b"100644\0")
        expected_source.update((repository / relative).read_bytes())
    assert snapshot.source_state_digest == expected_source.hexdigest()


def test_fake_snapshot_cannot_expose_archive_in_repr():
    snapshot = WindowsSnapshot(
        b"private archive bytes",
        "bounded",
        ("docs/process/a.md",),
        CODEX_PILOT_DOCS_ONLY_KIND,
    )

    assert "private archive bytes" not in repr(snapshot)


@pytest.mark.skipif(
    os.environ.get("PHOENIX_RUN_REAL_WSL_CANCELLATION_SMOKE") != "1",
    reason="real targeted WSL cancellation smoke is opt-in",
)
def test_real_targeted_wsl_cancellation_preserves_unrelated_process(tmp_path: Path):
    worker = WslCodexWorker(tmp_path)
    runtime = worker.runtime_gate()
    assert runtime.passed, runtime
    spec = worker._runtime_spec
    assert spec is not None
    controls: list[tuple[WslInvocationControl, subprocess.Popen[str]]] = []

    def launch_sleep() -> tuple[WslInvocationControl, subprocess.Popen[str]]:
        control = worker._prepare_invocation_control(spec.platform)
        assert control is not None
        command = (
            "/usr/bin/timeout",
            "--signal=TERM",
            "--kill-after=5s",
            "120s",
            "/usr/bin/python3",
            "-c",
            "import time; time.sleep(120)",
        )
        argv = worker._wsl_argv(
            spec.platform,
            worker._supervised_linux_argv(control, command),
        )
        kwargs: dict[str, object] = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "shell": False,
            "env": wsl_module._sanitized_wsl_host_environment(),
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        process = subprocess.Popen(list(argv), **kwargs)
        controls.append((control, process))
        assert worker._await_invocation_ready(control)
        return control, process

    try:
        target_control, target_process = launch_sleep()
        unrelated_control, unrelated_process = launch_sleep()

        stopped = worker._stop_targeted_linux_invocation(
            target_process,
            target_control,
        )
        unrelated_ready = worker._run_invocation_control(
            "ready",
            unrelated_control,
        )

        assert stopped == WslProcessStopResult(True, True, True, True)
        assert unrelated_ready is not None
        assert unrelated_ready.returncode == 0
        assert unrelated_process.poll() is None
    finally:
        for control, process in reversed(controls):
            if process.poll() is None:
                stopped = worker._stop_targeted_linux_invocation(process, control)
                assert stopped.exit_proved


@pytest.mark.skipif(
    os.environ.get("PHOENIX_RUN_REAL_WSL_SMOKE") != "1",
    reason="real pinned WSL Codex smoke is opt-in",
)
def test_real_pinned_wsl_shadow_transfer_smoke(tmp_path: Path):
    canonical, _head = _repository(tmp_path)
    process_document = canonical / "docs" / "process" / "status.md"
    process_document.parent.mkdir(parents=True, exist_ok=True)
    process_document.write_text("Initial process status.\n", encoding="utf-8")
    _git(canonical, "add", "docs/process/status.md")
    _git(canonical, "commit", "--quiet", "-m", "add process document")
    head = _git(canonical, "rev-parse", "HEAD")
    branch = "codex/task-064-shadow-smoke"
    allowed = ("docs/process/status.md",)
    worker = WslCodexWorker(canonical)
    service = SystemCodexPilotServices(canonical, wsl_worker=worker)

    capability = service.capability_probe(180)
    assert capability.passed
    worktree_result = service.create_worktree(
        {
            "branch_name": branch,
            "base_commit_sha": head,
            "allowed_paths": list(allowed),
            "pilot_kind": CODEX_PILOT_DOCS_ONLY_KIND,
        }
    )
    assert worktree_result.passed
    assert worktree_result.handle is not None
    worktree = worktree_result.handle
    canonical_before = build_windows_snapshot(
        canonical,
        head,
        allowed,
        pilot_kind=CODEX_PILOT_DOCS_ONLY_KIND,
    )
    started: list[bool] = []
    try:
        execution = service.invoke_codex(
            worktree,
            (
                "Modify exactly one file: docs/process/status.md. Replace its complete "
                "contents with exactly: Phoenix synthetic WSL shadow transfer "
                "verified. followed by one newline. Do not modify any other file."
            ),
            180,
            lambda: started.append(True),
        )
        assert execution.status == "succeeded", execution
        assert started == [True]
        assert windows_snapshot_matches(canonical, head, canonical_before)
        assert process_document.read_text(encoding="utf-8") == (
            "Initial process status.\n"
        )
        diff = service.inspect_diff(worktree, allowed)
        assert diff.passed, diff
        assert diff == DiffGateResult(True, "diff_allowed", allowed)
        assert (worktree.path / "docs" / "process" / "status.md").read_text(
            encoding="utf-8"
        ) == "Phoenix synthetic WSL shadow transfer verified.\n"
        evidence = worker.last_transfer_evidence
        assert evidence.shadow_workspace_created
        assert evidence.shadow_git_baseline_created
        assert evidence.windows_worktree_unchanged_during_worker
        assert evidence.changed_paths_validated_before_apply
        assert evidence.patch_exported
        assert evidence.patch_applied
        assert evidence.temp_cleanup
    finally:
        _git(canonical, "worktree", "remove", "--force", str(worktree.path))
        _git(canonical, "branch", "-D", branch)
        shutil.rmtree(worktree.path.parent, ignore_errors=True)
