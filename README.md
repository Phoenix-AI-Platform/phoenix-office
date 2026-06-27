# Phoenix Office

Contractor office automation plugin for the Phoenix AI Platform.

Initial focus: proposal generation with DOCX/PDF output.

---

## Installation

```bash
pip install -e ".[dev]"
```

---

## Quick Start — Proposal Generation

```python
from datetime import date
from decimal import Decimal

from phoenix_office.generators.proposal import ProposalGenerator
from phoenix_office.models.proposal import (
    CompanyConfig,
    PricingLine,
    ProposalInput,
    ScopeItem,
)

# 1. Build the proposal input
proposal = ProposalInput(
    customer_name="Abby Hill",
    street_address="W3064 Piper Rd.",
    city_state_zip="Whitewater, WI",
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
        pricing_note=(
            "Price is based on normal pumping, cleaning, and removal of the tank. "
            "Additional charges may apply depending on the quantity and condition of "
            "the tank contents or if hazardous materials are encountered."
        ),
    ),
    company_config=CompanyConfig(
        company_name="A-1 Tank Removal",
        terms_and_conditions="Payment is due upon completion of work.",
    ),
    notes=[
        "Price is based on normal pumping, cleaning, and removal of the tank.",
        "Additional charges may apply depending on the quantity and condition of the tank contents.",
    ],
)

# 2. Generate rendered fields
fields = ProposalGenerator().prepare(proposal)

# 3. Inspect the rendered output
print(fields.customer_name)    # Abby Hill
print(fields.proposal_date)    # January 15, 2024
print(fields.scope_block)
# 1. Pump contents of tank (contents unknown)
# 2. Open and clean tank
# 3. Remove 1,000 gallon AST
# 4. Remove and dispose of tank and residual contents

print(fields.total_line)       # TOTAL: Starting at $3,000.00
print(fields.pricing_note)     # Price is based on normal pumping…
```

`ProposalFields` is a plain dataclass whose string attributes can be
injected directly into a DOCX template or passed to a PDF renderer.

### DOCX Rendering

To render a finished Word document from a template with
`DocxProposalRenderer`:

```python
from phoenix_office.renderers import DocxProposalRenderer

DocxProposalRenderer().render(
    proposal,
    template_path="templates/proposal.docx",
    output_path="output/proposal.docx",
)
```

Use ``{{customer_name}}``, ``{{street_address}}``, ``{{city_state_zip}}``,
``{{proposal_date}}``, ``{{item_description}}``, ``{{scope_block}}``,
``{{total_line}}``, ``{{pricing_note}}``, and ``{{notes}}`` placeholders in
the DOCX template. The renderer replaces text while preserving the original
template layout as much as possible. Place ``{{total_line}}`` on the line
where the full TOTAL text should appear, since that field already includes the
configured total label.

### Manual A-1 Proposal Workflow

For the current manual A-1 proposal workflow, see:

- [A-1 proposal MVP acceptance](docs/development/a1_proposal_mvp_acceptance.md)
- [Operator checklist](docs/development/proposal_workflow_operator_checklist.md)
- [Proposal workflow runbook](docs/development/proposal_workflow_runbook.md)
- [Records CLI workflow](docs/development/records_cli.md)
- [Output artifact conventions](docs/development/output_artifact_conventions.md)

---

## Data Model

| Model | Purpose |
|---|---|
| `ProposalInput` | Top-level proposal data container |
| `ScopeItem` | A single numbered scope-of-work line item |
| `PricingLine` | Total price, "starting at" flag, and optional pricing note |
| `CompanyConfig` | Company-specific formatting preferences (labels, terms) |

### A-1 Formatting Conventions

- Scope items are numbered sequentially starting at 1.
- Parenthetical notes like `(contents unknown)` are part of the item description.
- When `is_starting_at=True`, the total renders as `"Starting at $X,XXX.XX"`.
- The pricing note is placed **below** the TOTAL line alongside terms/disclaimers,
  not inline with the total.
- One blank line separates the TOTAL from the terms/disclaimers in the final document.

### Making Formatting Configurable

Use `CompanyConfig` to override labels for other contractors:

```python
cfg = CompanyConfig(
    total_label="TOTAL PRICE",
    starting_at_label="Starting from",
    terms_and_conditions="Your custom terms here.",
)
```

---

## Development

```bash
# Run tests
python -m pytest

# Lint
python -m ruff check src/ tests/
```

---

## Roadmap

- [x] DOCX template renderer (python-docx)
- [ ] PDF export
- [ ] Customer records / CRM
- [ ] Job history
- [ ] Phoenix Core integration
