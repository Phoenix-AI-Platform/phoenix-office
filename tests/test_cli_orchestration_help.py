"""Tests for help/discoverability of orchestration inspection CLI commands."""

from __future__ import annotations

import pytest

from phoenix_office.cli import build_parser


def test_orchestration_help_exposes_plan_and_review(capsys) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["orchestration", "--help"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "plan" in captured.out
    assert "review" in captured.out
    assert "orchestration" in captured.out


def test_orchestration_plan_help_exposes_inspect(capsys) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["orchestration", "plan", "--help"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "inspect" in captured.out
    assert "WorkflowPlan" in captured.out
    assert "without executing" in captured.out


def test_orchestration_plan_inspect_help_exposes_positional(capsys) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["orchestration", "plan", "inspect", "--help"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "plan_json" in captured.out
    assert "WorkflowPlan" in captured.out


def test_orchestration_review_help_exposes_inspect(capsys) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["orchestration", "review", "--help"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "inspect" in captured.out
    assert "WorkflowPlanReview" in captured.out
    assert "without mutating" in captured.out


def test_orchestration_review_inspect_help_exposes_positional(capsys) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["orchestration", "review", "inspect", "--help"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "review_json" in captured.out
    assert "WorkflowPlanReview" in captured.out
