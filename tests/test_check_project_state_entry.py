"""Tests for the project-state PR entry checker."""

from __future__ import annotations

from scripts.check_project_state_entry import (
    check_project_state_entry,
    has_project_state_entry,
    main,
)

PROJECT_STATE_TEXT = """# Phoenix Office Project State

## Current Verified Spine

```text
#105 docs: add ProposalInput validation examples
#107 ci: add pull request body section guard
```
"""


def test_has_project_state_entry_returns_true_for_present_pr_number() -> None:
    assert has_project_state_entry(PROJECT_STATE_TEXT, 107) is True


def test_has_project_state_entry_returns_false_for_missing_pr_number() -> None:
    assert has_project_state_entry(PROJECT_STATE_TEXT, 108) is False


def test_has_project_state_entry_does_not_match_partial_pr_number() -> None:
    assert has_project_state_entry("#1070 later entry\n", 107) is False


def test_check_project_state_entry_reads_temp_file(tmp_path) -> None:
    project_state_path = tmp_path / "project_state.md"
    project_state_path.write_text(PROJECT_STATE_TEXT, encoding="utf-8")

    assert check_project_state_entry(project_state_path, 105) is True


def test_main_passes_when_entry_exists(tmp_path, capsys) -> None:
    project_state_path = tmp_path / "project_state.md"
    project_state_path.write_text(PROJECT_STATE_TEXT, encoding="utf-8")

    exit_code = main([
        "--pr-number",
        "107",
        "--project-state-path",
        str(project_state_path),
    ])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Project state contains entry for PR #107." in captured.out
    assert captured.err == ""


def test_main_fails_when_entry_is_missing(tmp_path, capsys) -> None:
    project_state_path = tmp_path / "project_state.md"
    project_state_path.write_text(PROJECT_STATE_TEXT, encoding="utf-8")

    exit_code = main([
        "--pr-number",
        "108",
        "--project-state-path",
        str(project_state_path),
    ])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Project state is missing an entry for PR #108" in captured.err
