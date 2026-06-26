"""Metadata-only Phoenix plugin capability registry.

This module aggregates ``PluginCapability`` declarations. It does not execute
capabilities, register runtime hooks, or implement orchestration behavior.
"""

from phoenix_office.core.contracts import PluginCapability
from phoenix_office.plugins.office import get_office_plugin_capabilities


def get_registered_plugin_capabilities() -> list[PluginCapability]:
    """Return all Phoenix plugin capability metadata known to this package."""
    capabilities = [*get_office_plugin_capabilities()]
    validate_unique_capability_ids(capabilities)
    return capabilities


def get_plugin_capability_by_id(capability_id: str) -> PluginCapability | None:
    """Return a registered capability by id, or ``None`` when absent."""
    return next(
        (
            capability
            for capability in get_registered_plugin_capabilities()
            if capability.capability_id == capability_id
        ),
        None,
    )


def validate_unique_capability_ids(capabilities: list[PluginCapability]) -> None:
    """Raise ``ValueError`` if duplicate capability ids are present."""
    seen: set[str] = set()
    duplicates: set[str] = set()
    for capability in capabilities:
        if capability.capability_id in seen:
            duplicates.add(capability.capability_id)
        seen.add(capability.capability_id)

    if duplicates:
        duplicate_list = ", ".join(sorted(duplicates))
        msg = f"Duplicate plugin capability ids: {duplicate_list}"
        raise ValueError(msg)
