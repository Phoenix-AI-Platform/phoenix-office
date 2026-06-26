"""Tests for the Phoenix Office proposal PluginCapability JSON example."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phoenix_office.plugins.registry import get_plugin_capability_by_id

CAPABILITY_ID = "office.generate_proposal"
FIXTURE_PATH = Path("examples/plugins/office_generate_proposal_capability.json")


def _load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_office_generate_proposal_capability_example_has_expected_metadata():
    data = _load_fixture()

    assert data["capability_id"] == CAPABILITY_ID
    assert data["plugin_id"] == "phoenix-office"
    assert data["name"] == "Generate Proposal"
    assert data["category"] == "office"
    assert data["operation_type"] == "mutate"
    assert data["risk_level"] == "medium"
    assert data["input_schema_ref"] == "phoenix-office://schemas/proposal-input"
    assert data["output_schema_ref"] == "phoenix-office://schemas/proposal-docx"
    assert data["required_permissions"] == ["read", "write"]
    assert data["required_secrets"] == []
    assert data["supports_dry_run"] is False
    assert data["requires_approval"] is False
    assert data["verification_methods"] == ["artifact_inspection", "test_command"]


def test_office_generate_proposal_capability_example_matches_registry_output():
    capability = get_plugin_capability_by_id(CAPABILITY_ID)

    assert capability is not None
    assert _load_fixture() == capability.to_dict()
