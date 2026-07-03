"""Tests for read-only Codex CLI runtime capability probing."""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

import phoenix_office.cli as cli
from phoenix_office.cli import main

SUPPORTED_HELP = """
Usage: codex exec [OPTIONS]

Run Codex non-interactively.
Read prompt from stdin or prompt from -
  --ephemeral
  --sandbox <MODE>
  --cd <DIR>
  -C <DIR>
  --json
  --output-last-message <FILE>
  -o <FILE>
"""


def _completed(argv: list[str], stdout: str, returncode: int = 0):
    return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr="")


def _install_probe_mocks(
    monkeypatch: pytest.MonkeyPatch,
    *,
    version_stdout: str = "codex-cli 1.2.3\n",
    help_stdout: str = SUPPORTED_HELP,
    version_returncode: int = 0,
    help_returncode: int = 0,
    executable_found: bool = True,
    timeout_argv: list[str] | None = None,
) -> list[tuple[list[str], dict[str, Any]]]:
    calls: list[tuple[list[str], dict[str, Any]]] = []
    monkeypatch.setattr(
        cli.shutil,
        "which",
        lambda name: "C:/Users/example/bin/codex.exe"
        if name == "codex" and executable_found
        else None,
    )

    def fake_run(argv, **kwargs):
        calls.append((list(argv), kwargs))
        if timeout_argv is not None and list(argv) == timeout_argv:
            raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))
        if list(argv) == ["codex", "--version"]:
            return _completed(list(argv), version_stdout, version_returncode)
        if list(argv) == ["codex", "exec", "--help"]:
            return _completed(list(argv), help_stdout, help_returncode)
        raise AssertionError(f"Unexpected argv: {argv!r}")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    return calls


def test_dev_codex_runtime_probe_fully_supported_cli_report(monkeypatch, capsys):
    _install_probe_mocks(monkeypatch)

    exit_code = main(["dev", "codex-runtime-probe"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Codex CLI runtime capability probe" in captured.out
    assert "Executable found: yes" in captured.out
    assert "Sanitized CLI version: codex-cli 1.2.3" in captured.out
    assert "Version probe status: success" in captured.out
    assert "Exec-help probe status: success" in captured.out
    assert "Non-interactive exec: yes" in captured.out
    assert "Stdin prompt input: yes" in captured.out
    assert "Ephemeral option: yes" in captured.out
    assert "Sandbox option: yes" in captured.out
    assert "Working-directory option: yes" in captured.out
    assert "JSON option: yes" in captured.out
    assert "Output last message option: yes" in captured.out
    assert "Explicit budget option: no" in captured.out
    assert "Pilot ready: no" in captured.out
    assert "Invocation performed: no" in captured.out
    assert "Prompt submitted: no" in captured.out
    assert "GitHub access performed: no" in captured.out
    assert "Mutation performed: no" in captured.out
    assert captured.err == ""


def test_dev_codex_runtime_probe_json_supported_cli(monkeypatch, capsys):
    _install_probe_mocks(monkeypatch)

    exit_code = main(["dev", "codex-runtime-probe", "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["schema_version"] == "codex-runtime-probe.v1"
    assert payload["command"] == "dev codex-runtime-probe"
    assert payload["executable_found"] is True
    assert payload["sanitized_cli_version"] == "codex-cli 1.2.3"
    assert payload["version_probe"]["status"] == "success"
    assert payload["exec_help_probe"]["status"] == "success"
    assert payload["non_interactive_exec_detected"] is True
    assert payload["stdin_prompt_input_detected"] is True
    assert payload["ephemeral_option_detected"] is True
    assert payload["sandbox_option_detected"] is True
    assert payload["working_directory_option_detected"] is True
    assert payload["json_option_detected"] is True
    assert payload["output_last_message_option_detected"] is True
    assert payload["explicit_budget_option_detected"] is False
    assert payload["pilot_ready"] is False
    assert payload["invocation_performed"] is False
    assert payload["prompt_submitted"] is False
    assert payload["network_access_performed"] is False
    assert payload["github_access_performed"] is False
    assert payload["mutation_performed"] is False
    assert payload["blockers"] == []
    assert "authentication and runner access" in payload["external_checks_required"]


def test_dev_codex_runtime_probe_executable_missing(monkeypatch, capsys):
    calls = _install_probe_mocks(monkeypatch, executable_found=False)

    exit_code = main(["dev", "codex-runtime-probe", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert calls == []
    assert payload["executable_found"] is False
    assert "codex executable not found" in payload["blockers"]


@pytest.mark.parametrize(
    ("timeout_argv", "probe_name"),
    [
        (["codex", "--version"], "version_probe"),
        (["codex", "exec", "--help"], "exec_help_probe"),
    ],
)
def test_dev_codex_runtime_probe_timeouts_fail_closed(
    monkeypatch, capsys, timeout_argv, probe_name
):
    _install_probe_mocks(monkeypatch, timeout_argv=timeout_argv)

    exit_code = main(["dev", "codex-runtime-probe", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload[probe_name]["status"] == "timeout"
    assert payload[probe_name]["timed_out"] is True
    assert any("timeout" in blocker for blocker in payload["blockers"])


@pytest.mark.parametrize(
    ("version_returncode", "help_returncode", "probe_name"),
    [(7, 0, "version_probe"), (0, 7, "exec_help_probe")],
)
def test_dev_codex_runtime_probe_nonzero_exits_fail_closed(
    monkeypatch, capsys, version_returncode, help_returncode, probe_name
):
    _install_probe_mocks(
        monkeypatch,
        version_returncode=version_returncode,
        help_returncode=help_returncode,
    )

    exit_code = main(["dev", "codex-runtime-probe", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload[probe_name]["status"] == "nonzero_exit"
    assert any("nonzero_exit" in blocker for blocker in payload["blockers"])


@pytest.mark.parametrize("bad_version", ["", "\n", "C:/Users/name/codex"])
def test_dev_codex_runtime_probe_empty_or_malformed_version_output(
    monkeypatch, capsys, bad_version
):
    _install_probe_mocks(monkeypatch, version_stdout=bad_version)

    exit_code = main(["dev", "codex-runtime-probe", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["version_probe"]["status"] == "malformed_output"
    assert payload["sanitized_cli_version"] is None


@pytest.mark.parametrize(
    ("help_text", "field", "blocker"),
    [
        (
            SUPPORTED_HELP.replace("Usage: codex exec [OPTIONS]", "Usage: codex run"),
            "non_interactive_exec_detected",
            "non-interactive codex exec evidence",
        ),
        (
            SUPPORTED_HELP.replace("Read prompt from stdin or prompt from -", ""),
            "stdin_prompt_input_detected",
            "stdin or '-' prompt input support",
        ),
        (
            SUPPORTED_HELP.replace("  --ephemeral", ""),
            "ephemeral_option_detected",
            "--ephemeral option",
        ),
        (
            SUPPORTED_HELP.replace("  --sandbox <MODE>", ""),
            "sandbox_option_detected",
            "--sandbox option",
        ),
        (
            SUPPORTED_HELP.replace("  --cd <DIR>", "").replace("  -C <DIR>", ""),
            "working_directory_option_detected",
            "--cd or -C option",
        ),
        (
            SUPPORTED_HELP.replace("  --json", ""),
            "json_option_detected",
            "--json option",
        ),
        (
            SUPPORTED_HELP.replace("  --output-last-message <FILE>", "").replace(
                "  -o <FILE>", ""
            ),
            "output_last_message_option_detected",
            "--output-last-message or -o option",
        ),
    ],
)
def test_dev_codex_runtime_probe_missing_required_capability_fails_closed(
    monkeypatch, capsys, help_text, field, blocker
):
    _install_probe_mocks(monkeypatch, help_stdout=help_text)

    exit_code = main(["dev", "codex-runtime-probe", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload[field] is False
    assert f"missing capability: {blocker}" in payload["blockers"]


def test_dev_codex_runtime_probe_budget_option_detected(monkeypatch, capsys):
    _install_probe_mocks(
        monkeypatch,
        help_stdout=f"{SUPPORTED_HELP}\n  --token-budget <TOKENS>\n",
    )

    exit_code = main(["dev", "codex-runtime-probe", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["explicit_budget_option_detected"] is True
    assert payload["pilot_ready"] is False


def test_dev_codex_runtime_probe_budget_option_not_inferred(
    monkeypatch, capsys
):
    _install_probe_mocks(
        monkeypatch,
        help_stdout=f"{SUPPORTED_HELP}\nAccount usage limits may apply.\n",
    )

    exit_code = main(["dev", "codex-runtime-probe", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["explicit_budget_option_detected"] is False


def test_dev_codex_runtime_probe_uses_exact_fixed_argv_and_safe_subprocess(
    monkeypatch, capsys
):
    calls = _install_probe_mocks(monkeypatch)

    exit_code = main(["dev", "codex-runtime-probe", "--json"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["local_cli_ready"] is True
    assert [argv for argv, _kwargs in calls] == [
        ["codex", "--version"],
        ["codex", "exec", "--help"],
    ]
    for argv, kwargs in calls:
        assert kwargs["shell"] is False
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["input"] is None
        assert kwargs["timeout"] == 5
        assert "cwd" not in kwargs
        assert "env" not in kwargs
        assert not any("prompt" == arg.lower() for arg in argv)
        assert not any("bypass" in arg.lower() for arg in argv)
        assert not any("auth" in arg.lower() for arg in argv)


def test_dev_codex_runtime_probe_does_not_leak_machine_paths_or_environment(
    monkeypatch, capsys
):
    _install_probe_mocks(
        monkeypatch,
        version_stdout="C:/Users/matth/AppData/codex\ncodex-cli 1.2.3\n",
        help_stdout=f"{SUPPORTED_HELP}\nC:/Users/matth/config\nTOKEN=secret\n",
    )

    exit_code = main(["dev", "codex-runtime-probe", "--json"])

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert exit_code == 0
    assert payload["sanitized_cli_version"] == "codex-cli 1.2.3"
    assert "C:/Users" not in output
    assert "matth" not in output
    assert "TOKEN" not in output
    assert "secret" not in output


def test_dev_codex_runtime_probe_json_is_deterministic(monkeypatch, capsys):
    _install_probe_mocks(monkeypatch)

    first_exit = main(["dev", "codex-runtime-probe", "--json"])
    first = capsys.readouterr().out
    second_exit = main(["dev", "codex-runtime-probe", "--json"])
    second = capsys.readouterr().out

    assert first_exit == 0
    assert second_exit == 0
    assert first == second
    assert json.loads(first)["pilot_ready"] is False


def test_dev_codex_runtime_probe_has_no_mutating_behavior(monkeypatch, capsys):
    calls = _install_probe_mocks(monkeypatch)

    exit_code = main(["dev", "codex-runtime-probe", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["invocation_performed"] is False
    assert payload["prompt_submitted"] is False
    assert payload["network_access_performed"] is False
    assert payload["github_access_performed"] is False
    assert payload["mutation_performed"] is False
    assert len(calls) == 2
