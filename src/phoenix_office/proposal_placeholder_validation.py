"""Helpers for detecting unresolved placeholder text in proposal input data."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from phoenix_office.models.proposal import ProposalInput

DEFAULT_PROPOSAL_PLACEHOLDER_MARKERS = (
    "todo:",
    "replace with explicit",
)


def proposal_input_placeholder_paths(
    proposal: ProposalInput,
    *,
    markers: Iterable[str] = DEFAULT_PROPOSAL_PLACEHOLDER_MARKERS,
) -> list[str]:
    """Return field paths containing unresolved placeholder text.

    The helper is deterministic and read-only. It inspects normalized
    ``ProposalInput`` data only and returns paths into the model dump for string
    values containing any configured marker, case-insensitively.
    """
    normalized_markers = tuple(marker.casefold() for marker in markers)
    return _placeholder_paths(proposal.model_dump(mode="json"), normalized_markers)


def _placeholder_paths(
    value: Any,
    markers: tuple[str, ...],
    path: str = "",
) -> list[str]:
    if isinstance(value, str):
        normalized = value.casefold()
        if any(marker in normalized for marker in markers):
            return [path or "<root>"]
        return []

    if isinstance(value, dict):
        paths: list[str] = []
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            paths.extend(_placeholder_paths(child, markers, child_path))
        return paths

    if isinstance(value, list):
        paths = []
        for index, child in enumerate(value):
            paths.extend(_placeholder_paths(child, markers, f"{path}[{index}]"))
        return paths

    return []
