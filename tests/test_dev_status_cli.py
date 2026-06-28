"""Tests for the read-only development status command."""

from __future__ import annotations

from phoenix_office import cli
from phoenix_office.cli import main


def test_dev_status_prints_project_state_summary(tmp_path, capsys, monkeypatch):
    project_state_path = tmp_path / "docs" / "development" / "project_state.md"
    project_state_path.parent.mkdir(parents=True)
    project_state_path.write_text(
        "# Phoenix Office Project State\n\n"
        "## Current Verified Spine\n\n"
        "```text\n"
        "#116 cli: add optional JSON output to proposal inspect\n"
        "#118 chore: fix E501 in project state guard script\n"
        "```\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "DEV_STATUS_PROJECT_STATE_PATH", project_state_path)

    exit_code = main(["dev", "status"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "project name: Phoenix Office" in captured.out
    assert f"status source path: {project_state_path}" in captured.out
    assert "project-state file exists: yes" in captured.out
    assert (
        "latest recorded PR entry: #118 chore: fix E501 in project state guard script"
        in captured.out
    )
    assert captured.err == ""


def test_dev_status_handles_missing_project_state_file(tmp_path, capsys, monkeypatch):
    missing_path = tmp_path / "docs" / "development" / "project_state.md"
    monkeypatch.setattr(cli, "DEV_STATUS_PROJECT_STATE_PATH", missing_path)

    exit_code = main(["dev", "status"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "project name: Phoenix Office" in captured.out
    assert f"status source path: {missing_path}" in captured.out
    assert "project-state file exists: no" in captured.out
    assert "latest recorded PR entry: (none)" in captured.out
    assert f"Error: project-state file does not exist: {missing_path}" in captured.err
