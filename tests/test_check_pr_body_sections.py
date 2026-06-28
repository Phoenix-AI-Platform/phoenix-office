"""Tests for the pull request body section checker."""

from __future__ import annotations

import json

from scripts.check_pr_body_sections import (
    load_pr_body_from_event,
    main,
    missing_required_sections,
)

VALID_PR_BODY = """## Summary

- Adds a narrow change.

## Scope

- Process guard only.

## Changed files

- `scripts/check_pr_body_sections.py`

## Out-of-scope confirmation

- No product behavior changed.

## Validation performed

- `python -m pytest`

## Risks

- Low.
"""


def test_missing_required_sections_returns_empty_for_complete_body() -> None:
    assert missing_required_sections(VALID_PR_BODY) == []


def test_missing_required_sections_reports_missing_headings() -> None:
    body = """## Summary

- Missing several sections.

## Scope

- Narrow.
"""

    assert missing_required_sections(body) == [
        "Changed files",
        "Out-of-scope confirmation",
        "Validation performed",
        "Risks",
    ]


def test_main_fails_when_required_sections_are_missing(capsys) -> None:
    exit_code = main(["--body", "## Summary\n\n- Incomplete."])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "PR body is missing required section headings" in captured.err
    assert "- Scope" in captured.err


def test_main_passes_when_required_sections_are_present(capsys) -> None:
    exit_code = main(["--body", VALID_PR_BODY])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PR body contains required section headings." in captured.out
    assert captured.err == ""


def test_load_pr_body_from_event(tmp_path) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps({"pull_request": {"body": VALID_PR_BODY}}),
        encoding="utf-8",
    )

    assert load_pr_body_from_event(event_path) == VALID_PR_BODY
