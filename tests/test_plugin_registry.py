"""Tests for metadata-only Phoenix plugin capability registry."""

import pytest

from phoenix_office.core.contracts import (
    OperationType,
    PluginCapability,
    RiskLevel,
)
from phoenix_office.plugins.registry import (
    get_plugin_capability_by_id,
    get_registered_plugin_capabilities,
    validate_unique_capability_ids,
)


def test_registry_returns_proposal_generation_capability():
    capabilities = get_registered_plugin_capabilities()

    assert any(
        capability.capability_id == "office.generate_proposal"
        for capability in capabilities
    )


def test_registry_returns_plugin_capability_objects():
    capabilities = get_registered_plugin_capabilities()

    assert capabilities
    assert all(isinstance(capability, PluginCapability) for capability in capabilities)


def test_get_plugin_capability_by_id_returns_expected_capability():
    capability = get_plugin_capability_by_id("office.generate_proposal")

    assert capability is not None
    assert capability.capability_id == "office.generate_proposal"
    assert capability.plugin_id == "phoenix-office"


def test_get_plugin_capability_by_id_returns_none_for_missing_capability():
    assert get_plugin_capability_by_id("missing.capability") is None


def test_validate_unique_capability_ids_raises_for_duplicates():
    capabilities = [
        PluginCapability(
            capability_id="duplicate.capability",
            plugin_id="plugin-one",
            name="Duplicate One",
            version="0.1.0",
            description="First duplicate capability.",
            category="test",
            operation_type=OperationType.MUTATE,
            risk_level=RiskLevel.MEDIUM,
            input_schema_ref="schema://input-one",
            output_schema_ref="schema://output-one",
        ),
        PluginCapability(
            capability_id="duplicate.capability",
            plugin_id="plugin-two",
            name="Duplicate Two",
            version="0.1.0",
            description="Second duplicate capability.",
            category="test",
            operation_type=OperationType.MUTATE,
            risk_level=RiskLevel.MEDIUM,
            input_schema_ref="schema://input-two",
            output_schema_ref="schema://output-two",
        ),
    ]

    with pytest.raises(ValueError, match="duplicate.capability"):
        validate_unique_capability_ids(capabilities)
