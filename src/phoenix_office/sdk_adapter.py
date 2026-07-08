"""Phoenix SDK adapter for Phoenix Office.

This adapter intentionally exposes metadata only. It does not route proposal
generation through the SDK contract yet.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from phoenix_sdk import (
    CommandRequest,
    CommandResult,
    PhoenixPlugin,
    PluginCommand,
    PluginManifest,
)


@dataclass(frozen=True, slots=True)
class PhoenixOfficeCommand:
    """Metadata-only SDK command placeholder for Phoenix Office."""

    name: str
    description: str

    def execute(self, request: CommandRequest) -> CommandResult:
        """Prevent command execution until a dedicated execution PR is approved."""

        message = (
            "Phoenix Office SDK command execution is not implemented "
            f"for {request.command!r}."
        )
        raise NotImplementedError(message)


class PhoenixOfficePlugin:
    """SDK plugin adapter for Phoenix Office metadata."""

    _commands: tuple[PhoenixOfficeCommand, ...] = (
        PhoenixOfficeCommand(
            name="proposal.prepare_fields",
            description="Prepare deterministic proposal fields from validated proposal input.",
        ),
        PhoenixOfficeCommand(
            name="proposal.generate_docx",
            description="Render a DOCX proposal from validated input and an explicit template.",
        ),
    )

    @property
    def manifest(self) -> PluginManifest:
        """Return static Phoenix Office plugin metadata."""

        return PluginManifest(
            plugin_id="phoenix.office",
            name="Phoenix Office",
            version="0.1.0",
            description="Contractor office automation plugin for Phoenix.",
            commands=tuple(command.name for command in self._commands),
            metadata={"execution": "metadata_only"},
        )

    def list_commands(self) -> Sequence[PluginCommand]:
        """Return metadata-only commands exposed by Phoenix Office."""

        return self._commands

    def get_command(self, name: str) -> PluginCommand:
        """Return a command by name."""

        for command in self._commands:
            if command.name == name:
                return command
        raise KeyError(name)


def create_plugin() -> PhoenixPlugin:
    """Create the Phoenix Office SDK plugin adapter."""

    return PhoenixOfficePlugin()
