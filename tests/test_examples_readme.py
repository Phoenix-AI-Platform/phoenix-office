"""Tests for the Phoenix examples index documentation."""

from pathlib import Path

EXAMPLES_README = Path("examples/README.md")


def test_examples_readme_exists():
    assert EXAMPLES_README.exists()


def test_examples_readme_references_key_artifacts_and_concepts():
    text = EXAMPLES_README.read_text(encoding="utf-8")

    assert "office_generate_proposal_capability.json" in text
    assert "proposal_generation_task.json" in text
    assert "codex_handoff_package.json" in text
    assert "office.generate_proposal" in text
    assert "TaskEnvelope" in text
    assert "PluginCapability" in text
    assert "CodexHandoffPackage" in text
