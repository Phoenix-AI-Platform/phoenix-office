"""Metadata-only Phoenix Office plugin capability declarations.

This module describes existing Phoenix Office behavior as Phoenix Core
``PluginCapability`` metadata. It does not execute capabilities, register
runtime hooks, or change proposal generation behavior.
"""

from phoenix_office.core.contracts import (
    OperationType,
    PermissionMode,
    PluginCapability,
    RiskLevel,
)


def get_office_plugin_capabilities() -> list[PluginCapability]:
    """Return metadata for Phoenix Office capabilities.

    The returned objects are descriptive contract metadata only. Phoenix Core
    orchestration, worker execution, and plugin runtime behavior are intentionally
    out of scope for this layer.
    """
    return [
        PluginCapability(
            capability_id="office.generate_proposal",
            plugin_id="phoenix-office",
            name="Generate Proposal",
            version="0.1.0",
            description="Generate a local proposal DOCX from proposal input and a DOCX template.",
            category="office",
            operation_type=OperationType.MUTATE,
            risk_level=RiskLevel.MEDIUM,
            input_schema_ref="phoenix-office://schemas/proposal-input",
            output_schema_ref="phoenix-office://schemas/proposal-docx",
            required_permissions=[PermissionMode.READ, PermissionMode.WRITE],
            required_secrets=[],
            supports_dry_run=False,
            requires_approval=False,
            verification_methods=["artifact_inspection", "test_command"],
        )
    ]
