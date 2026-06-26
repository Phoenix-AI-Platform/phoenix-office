"""Tests for DOCX proposal rendering."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from docx import Document

from phoenix_office.models.proposal import PricingLine, ProposalInput, ScopeItem
from phoenix_office.renderers.docx_proposal import DocxProposalRenderer

TEMPLATE_PATH = Path(__file__).parent / "fixtures" / "templates" / "a1_proposal_template.docx"
PRICING_NOTE = (
    "Price is based on normal pumping, cleaning, and removal of the tank. "
    "Additional charges may apply depending on the quantity and condition of the tank "
    "contents or if hazardous materials are encountered."
)


def build_abby_hill_proposal() -> ProposalInput:
    return ProposalInput(
        customer_name="Abby Hill",
        street_address="W3064 Piper Rd.",
        city_state_zip="Whitewater, WI",
        proposal_date=date(2026, 6, 25),
        item_description="Removal of 1,000 Gallon Aboveground Storage Tank",
        scope_items=[
            ScopeItem(number=1, description="Pump contents of tank (contents unknown)"),
            ScopeItem(number=2, description="Open and clean tank"),
            ScopeItem(number=3, description="Remove 1,000 gallon AST"),
            ScopeItem(number=4, description="Remove and dispose of tank and residual contents"),
        ],
        pricing=PricingLine(
            amount=Decimal("3000.00"),
            is_starting_at=True,
            pricing_note=PRICING_NOTE,
        ),
    )


def read_docx_text(path: Path) -> str:
    document = Document(path)
    parts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.extend(paragraph.text for paragraph in cell.paragraphs)
    return "\n".join(parts)


def test_render_creates_verified_abby_hill_docx(tmp_path):
    output_path = tmp_path / "abby_hill_proposal.docx"

    result = DocxProposalRenderer().render(build_abby_hill_proposal(), TEMPLATE_PATH, output_path)

    assert result == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_abby_hill_text_appears_in_generated_docx(tmp_path):
    output_path = tmp_path / "abby_hill_proposal.docx"

    DocxProposalRenderer().render(build_abby_hill_proposal(), TEMPLATE_PATH, output_path)

    text = read_docx_text(output_path)
    expected_text = [
        "A-1 Tank Removal Proposal",
        "Date: June 25, 2026",
        "Prepared For:",
        "Abby Hill",
        "W3064 Piper Rd.",
        "Whitewater, WI",
        "Removal of 1,000 Gallon Aboveground Storage Tank",
        "1. Pump contents of tank (contents unknown)",
        "2. Open and clean tank",
        "3. Remove 1,000 gallon AST",
        "4. Remove and dispose of tank and residual contents",
        "TOTAL: Starting at $3,000.00",
        PRICING_NOTE,
    ]
    placeholders = [
        "{{customer_name}}",
        "{{street_address}}",
        "{{city_state_zip}}",
        "{{proposal_date}}",
        "{{item_description}}",
        "{{scope_block}}",
        "{{total_line}}",
        "{{pricing_note}}",
        "{{notes}}",
    ]

    for expected in expected_text:
        assert expected in text
    for placeholder in placeholders:
        assert placeholder not in text
