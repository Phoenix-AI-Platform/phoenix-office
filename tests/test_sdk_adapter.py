from __future__ import annotations

import pytest

from phoenix_office.sdk_adapter import PhoenixOfficePlugin, create_plugin
from phoenix_sdk import CommandRequest, PhoenixPlugin, PluginCommand, ResultStatus


def test_create_plugin_satisfies_sdk_protocol() -> None:
    plugin = create_plugin()

    assert isinstance(plugin, PhoenixPlugin)
    assert plugin.manifest.plugin_id == "phoenix.office"
    assert plugin.manifest.name == "Phoenix Office"
    assert plugin.manifest.metadata["execution"] == "metadata_only"


def test_plugin_exposes_initial_command_metadata() -> None:
    plugin = PhoenixOfficePlugin()

    command_names = tuple(command.name for command in plugin.list_commands())

    assert command_names == (
        "proposal.prepare_fields",
        "proposal.generate_docx",
    )
    assert plugin.manifest.commands == command_names


def test_get_command_returns_metadata_command() -> None:
    plugin = PhoenixOfficePlugin()

    command = plugin.get_command("proposal.prepare_fields")

    assert isinstance(command, PluginCommand)
    assert command.name == "proposal.prepare_fields"


def test_get_unknown_command_raises_key_error() -> None:
    plugin = PhoenixOfficePlugin()

    with pytest.raises(KeyError):
        plugin.get_command("proposal.unknown")


def test_sdk_commands_do_not_execute_yet() -> None:
    plugin = PhoenixOfficePlugin()
    command = plugin.get_command("proposal.generate_docx")

    with pytest.raises(NotImplementedError):
        command.execute(CommandRequest(command="proposal.generate_docx"))


def test_result_status_import_remains_available_for_future_execution() -> None:
    assert ResultStatus.SUCCESS.value == "success"
