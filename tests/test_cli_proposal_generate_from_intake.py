"""Tests for A-1 proposal intake DOCX generation CLI command."""

from __future__ import annotations

import json
from pathlib import Path

from docx import Document

from phoenix_office.cli import main

ROOT = Path(__file__).parents[1]
A1_INTAKE_JSON = ROOT / "examples" / "proposals" / "a1_residential_tank_removal_intake.json"
A1_TEMPLATE = ROOT / "tests" / "fixtures" / "templates" / "a1_proposal_template.docx"


def read_docx_text(path: Path) -> str:
    document = Document(path)
    parts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.extend(paragraph.text for paragraph in cell.paragraphs)
    return "\n".join(parts)


def test_cli_proposal_generate_from_intake_example(tmp_path: Path, capsys) -> None:
    output_path = tmp_path / "a1_intake_proposal.docx"

    exit_code = main(
        [
            "proposal",
            "generate-from-intake",
            str(A1_INTAKE_JSON),
            str(output_path),
            "--template",
            str(A1_TEMPLATE),
        ]
    )

    captured = capsys.readouterr()
    text = read_docx_text(output_path)

    assert exit_code == 0
    assert "Generated proposal DOCX" in captured.out
    assert str(output_path) in captured.out
    assert captured.err == ""
    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert "Jane Customer" in text
    assert "123 Main St." in text
    assert "Milwaukee, WI 53202" in text
    assert "July 1, 2026" in text
    assert "Removal of 1,000 Gallon Aboveground Storage Tank" in text
    assert "TOTAL: Starting at $3,000.00" in text
    assert "Customer is responsible for access to the tank area." in text


def test_cli_proposal_generate_from_intake_invalid_intake_fails(
    tmp_path: Path, capsys
) -> None:
    input_path = tmp_path / "invalid_a1_intake.json"
    output_path = tmp_path / "a1_intake_proposal.docx"
    input_path.write_text(
        json.dumps(
            {
                "customer_name": "Jane Customer",
                "job_address": {
                    "street_address": "123 Main St.",
                    "city_state_zip": "Milwaukee, WI 53202",
                },
                "proposal_date": "2026-07-01",
                "item_description": "Removal of 1,000 Gallon Aboveground Storage Tank",
                "scope_notes": ["Remove tank"],
                "pricing_lines": [],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "proposal",
            "generate-from-intake",
            str(input_path),
            str(output_path),
            "--template",
            str(A1_TEMPLATE),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "Error: invalid A-1 proposal intake JSON:" in captured.err
    assert "pricing_lines" in captured.err
    assert not output_path.exists()
