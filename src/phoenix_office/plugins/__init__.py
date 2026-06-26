"""Phoenix Office plugin capability metadata."""

from phoenix_office.plugins.office import get_office_plugin_capabilities
from phoenix_office.plugins.registry import (
    get_plugin_capability_by_id,
    get_registered_plugin_capabilities,
    validate_unique_capability_ids,
)

__all__ = [
    "get_office_plugin_capabilities",
    "get_plugin_capability_by_id",
    "get_registered_plugin_capabilities",
    "validate_unique_capability_ids",
]
