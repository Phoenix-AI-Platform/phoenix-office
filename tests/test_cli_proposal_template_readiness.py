"""Tests for proposal template readiness CLI command."""

from __future__ import annotations

import json
from pathlib import Path

from phoenix_office.cli import main

ROOT = Path(__file__).parents[1]
A1_TEMPLATE = ROOT / "tests" / "fixtures" / "templates" / "a1_proposal_template.docx"


def test_cli_proposal_template_readiness_reports_ready_template(capsys) -> None:
    exit_code = main(["proposal", "template-readiness", str(A1_TEMPLATE)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"DOCX template readiness: ready ({A1_TEMPLATE})" in captured.out
    assert "Ready for proposal generation: yes" in captured.out
    assert captured.err == ""


def test_cli_proposal_template_readiness_json_reports_ready_template(capsys) -> None:
    exit_code = main(["proposal", "template-readiness", str(A1_TEMPLATE), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload == {
        "error": None,
        "ready": True,
        "status": "ready",
        "template_path": str(A1_TEMPLATE),
    }
    assert captured.err == ""


def test_cli_proposal_template_readiness_missing_path_fails(
    tmp_path: Path,
    capsys,
) -> None:
    template_path = tmp_path / "missing_template.docx"

    exit_code = main(["proposal", "template-readiness", str(template_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert f"DOCX template readiness: blocked ({template_path})" in captured.out
    assert "Ready for proposal generation: no" in captured.out
    assert f"Blocker: DOCX template file does not exist: {template_path}" in captured.out
    assert captured.err == ""


def test_cli_proposal_template_readiness_directory_path_fails(
    tmp_path: Path,
    capsys,
) -> None:
    exit_code = main(["proposal", "template-readiness", str(tmp_path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert payload == {
        "error": f"DOCX template path is not a file: {tmp_path}",
        "ready": False,
        "status": "blocked",
        "template_path": str(tmp_path),
    }
    assert captured.err == ""


def test_cli_proposal_template_readiness_invalid_docx_fails(
    tmp_path: Path,
    capsys,
) -> None:
    template_path = tmp_path / "invalid_template.docx"
    template_path.write_text("not a docx", encoding="utf-8")

    exit_code = main(["proposal", "template-readiness", str(template_path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert payload["ready"] is False
    assert payload["status"] == "blocked"
    assert payload["template_path"] == str(template_path)
    assert payload["error"].startswith("DOCX template could not be opened:")
    assert captured.err == ""
