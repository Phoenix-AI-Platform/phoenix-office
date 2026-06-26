"""Tests for the GitHub pull request template guardrails."""

from pathlib import Path

PR_TEMPLATE = Path(".github/pull_request_template.md")


def test_pull_request_template_exists():
    assert PR_TEMPLATE.exists()


def test_pull_request_template_references_phoenix_guardrails():
    text = PR_TEMPLATE.read_text(encoding="utf-8")

    assert "orchestrator" in text
    assert "worker execution" in text
    assert "plugin runtime behavior" in text
    assert "proposal generation behavior" in text
    assert "CLI behavior" in text
    assert "DOCX rendering behavior" in text
    assert "python -m pytest" in text
    assert "ruff check ." in text
