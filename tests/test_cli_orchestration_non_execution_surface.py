"""Tests that orchestration CLI exposes no execution or mutation commands."""

from __future__ import annotations

import pytest

from phoenix_office.cli import build_parser

UNSUPPORTED_ORCHESTRATION_COMMANDS = [
    ["orchestration", "execute"],
    ["orchestration", "run"],
    ["orchestration", "apply"],
    ["orchestration", "plan", "execute"],
    ["orchestration", "plan", "run"],
    ["orchestration", "review", "approve"],
    ["orchestration", "review", "reject"],
    ["orchestration", "review", "apply"],
]


@pytest.mark.parametrize("argv", UNSUPPORTED_ORCHESTRATION_COMMANDS)
def test_orchestration_execution_and_mutation_commands_are_rejected(
    argv: list[str],
    capsys,
) -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(argv)

    captured = capsys.readouterr()
    assert exc_info.value.code != 0
    assert (
        "invalid choice" in captured.err
        or "unrecognized arguments" in captured.err
    )
