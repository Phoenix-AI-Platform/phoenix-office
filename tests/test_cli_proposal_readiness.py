"""Tests for proposal readiness CLI command."""

from __future__ import annotations

import json
from pathlib import Path

from phoenix_office.cli import main

ROOT = Path(__file__).parents[1]
EXAMPLE_JSON = ROOT / "examples" / "proposals" / "abby_hill.json"


def _write_placeholder_proposal_input(tmp_path: Path) -> Path:
    input_path = tmp_path / "placeholder_proposal.json"
    payload = json.loads(EXAMPLE_JSON.read_text(encoding="utf-8"))
    payload["item_description"] = "TODO: Replace with explicit item description."
    payload["pricing"]["pricing_note"] = "Replace with explicit pricing note."
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    return input_path


def test_cli_proposal_readiness_reports_ready_example(capsys) -> None:
    exit_code = main(["proposal", "readiness", str(EXAMPLE_JSON)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"ProposalInput readiness: ready ({EXAMPLE_JSON})" in captured.out
    assert "Ready for DOCX generation: yes" in captured.out
    assert (
        "Next manual command: "
        "python -m phoenix_office.cli proposal generate "
        f"{EXAMPLE_JSON} output/proposal.docx "
        "--template tests/fixtures/templates/a1_proposal_template.docx"
    ) in captured.out
    assert captured.err == ""

def test_cli_proposal_readiness_blocks_placeholder_text(
    tmp_path: Path,
    capsys,
) -> None:
    input_path = _write_placeholder_proposal_input(tmp_path)

    exit_code = main(["proposal", "readiness", str(input_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert f"ProposalInput readiness: blocked ({input_path})" in captured.out
    assert "Ready for DOCX generation: no" in captured.out
    assert "Blocker fields: item_description, pricing.pricing_note" in captured.out
    assert captured.err == ""


def test_cli_proposal_readiness_json_reports_ready(capsys) -> None:
    exit_code = main(["proposal", "readiness", str(EXAMPLE_JSON), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload == {
        "blocker_field_paths": [],
        "input_path": str(EXAMPLE_JSON),
        "ready_for_docx_generation": True,
        "status": "ready",
    }
    assert captured.err == ""


def test_cli_proposal_readiness_json_reports_blockers(
    tmp_path: Path,
    capsys,
) -> None:
    input_path = _write_placeholder_proposal_input(tmp_path)

    exit_code = main(["proposal", "readiness", str(input_path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert payload == {
        "blocker_field_paths": [
            "item_description",
            "pricing.pricing_note",
        ],
        "input_path": str(input_path),
        "ready_for_docx_generation": False,
        "status": "blocked",
    }
    assert captured.err == ""


def test_cli_proposal_readiness_invalid_data_fails(
    tmp_path: Path,
    capsys,
) -> None:
    input_path = tmp_path / "invalid_proposal_data.json"
    payload = json.loads(EXAMPLE_JSON.read_text(encoding="utf-8"))
    payload["scope_items"] = []
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = main(["proposal", "readiness", str(input_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "Error: invalid proposal input:" in captured.err
