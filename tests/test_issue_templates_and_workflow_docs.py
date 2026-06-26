"""Tests for issue templates and developer workflow documentation."""

from pathlib import Path

PHOENIX_TASK_TEMPLATE = Path(".github/ISSUE_TEMPLATE/phoenix_task.yml")
BUG_REPORT_TEMPLATE = Path(".github/ISSUE_TEMPLATE/bug_report.yml")
ISSUE_TEMPLATE_CONFIG = Path(".github/ISSUE_TEMPLATE/config.yml")
WORKFLOW_DOC = Path("docs/development/workflow.md")


def test_issue_templates_and_workflow_doc_exist():
    assert PHOENIX_TASK_TEMPLATE.exists()
    assert BUG_REPORT_TEMPLATE.exists()
    assert ISSUE_TEMPLATE_CONFIG.exists()
    assert WORKFLOW_DOC.exists()


def test_phoenix_task_template_references_required_guardrails():
    text = PHOENIX_TASK_TEMPLATE.read_text(encoding="utf-8").lower()

    assert "orchestrator" in text
    assert "worker execution" in text
    assert "plugin runtime behavior" in text
    assert "proposal generation behavior" in text
    assert "cli behavior" in text
    assert "docx rendering behavior" in text
    assert "acceptance criteria" in text
    assert "verification" in text


def test_workflow_doc_references_required_workflow_elements():
    text = WORKFLOW_DOC.read_text(encoding="utf-8")

    assert "ChatGPT" in text
    assert "Codex" in text
    assert "Copilot" in text
    assert "python -m pytest" in text
    assert "ruff check ." in text
    assert "TaskEnvelope" in text
    assert "PluginCapability" in text
