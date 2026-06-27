"""Tests for the PR review guardrails JSON document."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
GUARDRAILS_PATH = ROOT / "docs" / "development" / "pr_review_guardrails.json"


def _load_guardrails() -> dict[str, Any]:
    return json.loads(GUARDRAILS_PATH.read_text(encoding="utf-8"))


def test_pr_review_guardrails_json_has_required_top_level_keys() -> None:
    guardrails = _load_guardrails()

    assert guardrails["version"] == 1
    assert {
        "name",
        "version",
        "purpose",
        "required_review_steps",
        "global_forbidden_changes",
        "docs_only_pr_requirements",
        "code_pr_requirements",
        "parallel_pr_guardrails",
    }.issubset(guardrails)


def test_pr_review_guardrails_required_review_steps() -> None:
    guardrails = _load_guardrails()

    assert {"inspect_diff", "verify_ci", "give_merge_or_no_merge_call"}.issubset(
        guardrails["required_review_steps"]
    )


def test_pr_review_guardrails_global_forbidden_changes() -> None:
    guardrails = _load_guardrails()

    assert {
        "workflow_execution",
        "subprocess_calls",
        "docx_generation_from_orchestration",
        "pricing_scope_or_notes_inference",
        "private_customer_data",
        "generated_output_artifacts",
    }.issubset(guardrails["global_forbidden_changes"])


def test_pr_review_guardrails_docs_only_requirements() -> None:
    guardrails = _load_guardrails()

    assert {
        "no_code_files_changed",
        "no_test_files_changed",
        "no_behavior_changes",
    }.issubset(guardrails["docs_only_pr_requirements"])
