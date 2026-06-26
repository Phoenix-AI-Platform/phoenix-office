"""Tests for Phoenix Office plugin capability metadata."""

from phoenix_office.core.contracts import (
    OperationType,
    PermissionMode,
    PluginCapability,
    RiskLevel,
)
from phoenix_office.plugins.office import get_office_plugin_capabilities


def test_office_plugin_capabilities_include_proposal_generation():
    capabilities = get_office_plugin_capabilities()

    assert any(
        capability.capability_id == "office.generate_proposal"
        for capability in capabilities
    )


def test_proposal_generation_capability_uses_core_contract():
    capability = next(
        capability
        for capability in get_office_plugin_capabilities()
        if capability.capability_id == "office.generate_proposal"
    )

    assert isinstance(capability, PluginCapability)


def test_proposal_generation_capability_metadata():
    capability = next(
        capability
        for capability in get_office_plugin_capabilities()
        if capability.capability_id == "office.generate_proposal"
    )

    assert capability.plugin_id == "phoenix-office"
    assert capability.name == "Generate Proposal"
    assert capability.category == "office"
    assert capability.operation_type is OperationType.MUTATE
    assert capability.risk_level is RiskLevel.MEDIUM
    assert capability.required_permissions == [
        PermissionMode.READ,
        PermissionMode.WRITE,
    ]
    assert capability.required_secrets == []
    assert capability.supports_dry_run is False
    assert capability.requires_approval is False
    assert capability.verification_methods == ["artifact_inspection", "test_command"]
