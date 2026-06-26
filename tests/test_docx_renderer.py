"""Tests for DOCX proposal rendering."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from docx import Document

from phoenix_office.models.proposal import PricingLine, ProposalInput, ScopeItem
from phoenix_office.renderers.docx_proposal import DocxProposalRenderer

A1_TEMPLATE_PATH = Path(__file__).parent / "fixtures" / "templates" / "a1_proposal_template.docx"
PROPOSAL_PLACEHOLDERS = [
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
PRICING_NOTE = (
    "Price is based on normal pumping, cleaning, and removal of the tank. "
    "Additional charges may apply depending on the quantity and condition of the tank "
    "contents or if hazardous materials are encountered."
)


def build_generic_proposal() -> ProposalInput:
    return ProposalInput(
        customer_name="Test Customer",
        street_address="123 Main St.",
        city_state_zip="Milwaukee, WI 53202",
        proposal_date=date(2026, 6, 25),
        item_description="Tank removal test item",
        scope_items=[
            ScopeItem(number=1, description="Pump contents"),
            ScopeItem(number=2, description="Remove tank"),
        ],
        pricing=PricingLine(
            amount=Decimal("1500.00"),
            is_starting_at=False,
            pricing_note="Additional charges may apply.",
        ),
        notes=["Please call before arrival.", "Gate code is 1234."],
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


def build_simple_template(path: Path) -> None:
    document = Document()
    document.add_paragraph("Customer: {{customer_name}}")
    document.add_paragraph("Address: {{street_address}}")
    document.add_paragraph("City/State/ZIP: {{city_state_zip}}")
    document.add_paragraph("Date: {{proposal_date}}")
    document.add_paragraph("Item: {{item_description}}")
    document.add_paragraph("Scope: {{scope_block}}")
    document.add_paragraph("{{total_line}}")
    document.add_paragraph("Terms: {{pricing_note}}")
    document.add_paragraph("Notes: {{notes}}")

    split_paragraph = document.add_paragraph("Split customer: ")
    split_paragraph.add_run("{{customer_")
    split_paragraph.add_run("name}}")

    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "Table customer: {{customer_name}}"

    document.save(path)


def read_docx_text(path: Path) -> str:
    document = Document(path)
    parts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.extend(paragraph.text for paragraph in cell.paragraphs)
    return "\n".join(parts)


def render_simple_template(tmp_path: Path) -> str:
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "proposal.docx"
    build_simple_template(template_path)

    DocxProposalRenderer().render(build_generic_proposal(), template_path, output_path)

    return read_docx_text(output_path)


def test_render_creates_docx_file_from_simple_template(tmp_path):
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "output" / "proposal.docx"
    build_simple_template(template_path)

    result = DocxProposalRenderer().render(
    build_abby_hill_proposal(),
    A1_TEMPLATE_PATH,
    output_path,
)

    assert result == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_replaces_placeholders_in_normal_paragraphs(tmp_path):
    text = render_simple_template(tmp_path)

    assert "Customer: Test Customer" in text
    assert "Address: 123 Main St." in text
    assert "City/State/ZIP: Milwaukee, WI 53202" in text
    assert "Date: June 25, 2026" in text
    assert "Item: Tank removal test item" in text
    assert "Scope: 1. Pump contents" in text
    assert "2. Remove tank" in text
    assert "TOTAL: $1,500.00" in text
    assert "Terms: Additional charges may apply." in text


def test_replaces_placeholder_split_across_word_runs(tmp_path):
    text = render_simple_template(tmp_path)

    assert "Split customer: Test Customer" in text
    assert "{{customer_" not in text
    assert "name}}" not in text


def test_replaces_placeholders_inside_table_cell(tmp_path):
    text = render_simple_template(tmp_path)

    assert "Table customer: Test Customer" in text


def test_general_notes_render_correctly(tmp_path):
    text = render_simple_template(tmp_path)

    assert "Notes: Please call before arrival.\nGate code is 1234." in text


def test_unresolved_proposal_placeholders_are_not_left_in_generated_output(tmp_path):
    text = render_simple_template(tmp_path)

    for placeholder in PROPOSAL_PLACEHOLDERS:
        assert placeholder not in text


def test_render_creates_verified_abby_hill_docx(tmp_path):
    output_path = tmp_path / "abby_hill_proposal.docx"

    result = DocxProposalRenderer().render(build_abby_hill_proposal(), A1_TEMPLATE_PATH, output_path)

    assert result == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_abby_hill_text_appears_in_generated_docx(tmp_path):
    output_path = tmp_path / "abby_hill_proposal.docx"

    DocxProposalRenderer().render(build_abby_hill_proposal(), A1_TEMPLATE_PATH, output_path)

    text = read_docx_text(output_path)
    expected_text = [
        "A-1 Tank Removal LLC",
        "W178 N6006 Prairie Sky Court",
        "Menomonee Falls, Wisconsin 53051",
        "(262) 252-4030",
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
        "Payment due upon completion",
        "Proposal Accepted By:",
    ]

    for expected in expected_text:
        assert expected in text
    for placeholder in PROPOSAL_PLACEHOLDERS:
        assert placeholder not in text
