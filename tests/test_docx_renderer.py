"""Tests for DOCX proposal rendering."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from docx import Document

from phoenix_office.models.proposal import PricingLine, ProposalInput, ScopeItem
from phoenix_office.renderers.docx_proposal import DocxProposalRenderer


def build_proposal() -> ProposalInput:
    return ProposalInput(
        customer_name="Abby Hill",
        street_address="W3064 Piper Rd.",
        city_state_zip="Whitewater, WI 53190",
        proposal_date=date(2024, 1, 15),
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
            pricing_note="Additional charges may apply depending on tank contents.",
        ),
        notes=["Please call before arrival.", "Gate code will be provided before service."],
    )


def build_template(path) -> None:
    document = Document()
    customer = document.add_paragraph("Customer: ")
    customer.add_run("{{customer_")
    customer.add_run("name}}")
    document.add_paragraph("Address: {{street_address}}")
    document.add_paragraph("City/State/ZIP: {{city_state_zip}}")
    document.add_paragraph("Date: {{proposal_date}}")
    document.add_paragraph("Item: {{item_description}}")
    document.add_paragraph("{{scope_block}}")
    document.add_paragraph("{{total_line}}")
    document.add_paragraph("{{pricing_note}}")
    document.add_paragraph("{{notes}}")
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "Prepared for {{customer_name}}"
    document.save(path)


def read_docx_text(path) -> str:
    document = Document(path)
    parts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.extend(paragraph.text for paragraph in cell.paragraphs)
    return "\n".join(parts)


def test_render_creates_docx_file(tmp_path):
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "output" / "proposal.docx"
    build_template(template_path)

    result = DocxProposalRenderer().render(build_proposal(), template_path, output_path)

    assert result == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_rendered_text_appears_in_output_docx(tmp_path):
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "proposal.docx"
    build_template(template_path)

    DocxProposalRenderer().render(build_proposal(), template_path, output_path)

    text = read_docx_text(output_path)
    assert "Customer: Abby Hill" in text
    assert "Address: W3064 Piper Rd." in text
    assert "City/State/ZIP: Whitewater, WI 53190" in text
    assert "Date: January 15, 2024" in text
    assert "Item: Removal of 1,000 Gallon Aboveground Storage Tank" in text
    assert "1. Pump contents of tank (contents unknown)" in text
    assert "2. Open and clean tank" in text
    assert "3. Remove 1,000 gallon AST" in text
    assert "4. Remove and dispose of tank and residual contents" in text
    assert "TOTAL: Starting at $3,000.00" in text
    assert "Additional charges may apply depending on tank contents." in text
    assert "Please call before arrival.\nGate code will be provided before service." in text
    assert "Prepared for Abby Hill" in text
    assert "{{customer_name}}" not in text
