# A-1 Proposal Intake CLI Workflow

## Purpose

This guide shows the current manual CLI flow for preparing an A-1 proposal from explicit intake JSON. The commands are deterministic and operator-driven. They do not infer missing pricing, scope, notes, item descriptions, or customer data.

Use this workflow when starting from an A-1 intake JSON draft. The customer-backed variant below starts from an explicit `CustomerRecord` JSON file and still requires the operator to provide proposal date, item description, scope, pricing, and notes.

## 1. Create An Editable Intake Draft

Create a starter A-1 intake JSON file:

```bash
python -m phoenix_office.cli proposal draft-json output/a1_proposal_intake.json
```

Create a customer-specific draft with known customer and job address fields:

```bash
python -m phoenix_office.cli proposal draft-json output/a1_proposal_intake.json --customer-name "Jane Customer" --street-address "123 Main St." --city-state-zip "Milwaukee, WI 53202"
```

Review and edit the draft before using it. Placeholder values must be replaced by the operator.

## Customer-Backed Intake Draft Example

Create or export a single customer record JSON file:

```bash
python -m phoenix_office.cli records show customer customer-abby-hill --db output/records.sqlite > output/abby_hill_customer.json
```

Create an A-1 intake draft from that customer record plus explicit proposal fields:

```bash
python -m phoenix_office.cli proposal customer-draft-json output/abby_hill_customer.json output/abby_hill_intake.json --proposal-date 2026-07-01 --item-description "Removal of 1,000 Gallon Aboveground Storage Tank" --scope-note "Pump contents of tank (contents unknown)" --scope-note "Remove and dispose of tank and residual contents" --pricing-description "Residential tank removal" --pricing-amount 3000.00 --pricing-note "Explicit operator-provided pricing note." --starting-at --special-note "Explicit operator-provided special note."
```

Validate the customer-backed intake draft:

```bash
python -m phoenix_office.cli proposal intake-validate output/abby_hill_intake.json
```

Inspect the customer-backed intake draft:

```bash
python -m phoenix_office.cli proposal intake-inspect output/abby_hill_intake.json
python -m phoenix_office.cli proposal intake-inspect output/abby_hill_intake.json --json
```

Normalize the customer-backed intake draft into `ProposalInput` JSON:

```bash
python -m phoenix_office.cli proposal intake-normalize output/abby_hill_intake.json output/abby_hill_proposal_input.json
```

Generate a DOCX only after explicit review:

```bash
python -m phoenix_office.cli proposal generate-from-intake output/abby_hill_intake.json output/abby_hill_proposal.docx --template tests/fixtures/templates/a1_proposal_template.docx
```

## 2. Validate Intake JSON

Validate the intake file without printing the full summary:

```bash
python -m phoenix_office.cli proposal intake-validate output/a1_proposal_intake.json
```

For machine-readable validation output:

```bash
python -m phoenix_office.cli proposal intake-validate output/a1_proposal_intake.json --json
```

If the intake is structurally valid but still contains unresolved placeholder text, validation still succeeds and reports placeholder field paths. JSON validation includes `placeholder_field_paths`.

```bash
python -m phoenix_office.cli proposal intake-validate output/placeholder_a1_proposal_intake.json
python -m phoenix_office.cli proposal intake-validate output/placeholder_a1_proposal_intake.json --json
```

Validation does not normalize the intake, render DOCX, or write output files.

## 3. Inspect Intake JSON

Print a human-readable intake summary before normalization or rendering:

```bash
python -m phoenix_office.cli proposal intake-inspect output/a1_proposal_intake.json
```

For machine-readable summary output:

```bash
python -m phoenix_office.cli proposal intake-inspect output/a1_proposal_intake.json --json
```

If unresolved placeholder text remains, human-readable inspection reports warning field paths and JSON inspection includes `placeholder_field_paths`.

```bash
python -m phoenix_office.cli proposal intake-inspect output/placeholder_a1_proposal_intake.json
python -m phoenix_office.cli proposal intake-inspect output/placeholder_a1_proposal_intake.json --json
```

Inspection is read-only. It validates and summarizes the intake only.

## 4. Normalize To ProposalInput JSON

Convert the explicit intake JSON into the existing `ProposalInput` shape:

```bash
python -m phoenix_office.cli proposal intake-normalize output/a1_proposal_intake.json output/a1_proposal_input.json
```

The normalized JSON can then be reviewed with the existing ProposalInput commands:

```bash
python -m phoenix_office.cli proposal validate output/a1_proposal_input.json
python -m phoenix_office.cli proposal inspect output/a1_proposal_input.json
python -m phoenix_office.cli proposal inspect output/a1_proposal_input.json --json
```

`proposal validate` still succeeds for structurally valid normalized `ProposalInput` JSON with unresolved placeholder text, and reports warning field paths.

```bash
python -m phoenix_office.cli proposal validate output/placeholder_a1_proposal_input.json
```

`proposal inspect` reports placeholder warning field paths in human-readable output, and `--json` includes `placeholder_field_paths`.

```bash
python -m phoenix_office.cli proposal inspect output/placeholder_a1_proposal_input.json
python -m phoenix_office.cli proposal inspect output/placeholder_a1_proposal_input.json --json
```

`proposal generate` also refuses normalized `ProposalInput` JSON that still contains unresolved placeholder text such as `TODO:` or `replace with explicit`; the error reports the placeholder field paths.

Example reviewed normalized-input generation command:

```bash
python -m phoenix_office.cli proposal generate output/a1_proposal_input.json output/a1_proposal.docx --template tests/fixtures/templates/a1_proposal_template.docx
```

Example normalized-input command that should fail until placeholders are replaced:

```bash
python -m phoenix_office.cli proposal generate output/abby_hill_placeholder_proposal_input.json output/abby_hill_proposal.docx --template tests/fixtures/templates/a1_proposal_template.docx
```

Use the explicit override only when the operator intentionally wants placeholder text rendered from normalized `ProposalInput` JSON:

```bash
python -m phoenix_office.cli proposal generate output/abby_hill_placeholder_proposal_input.json output/abby_hill_proposal.docx --template tests/fixtures/templates/a1_proposal_template.docx --allow-placeholder-proposal-input
```

## 5. Generate DOCX From Intake

When the intake has been reviewed and the operator explicitly wants a DOCX artifact, run:

```bash
python -m phoenix_office.cli proposal generate-from-intake output/a1_proposal_intake.json output/a1_proposal.docx --template tests/fixtures/templates/a1_proposal_template.docx
```

By default, `generate-from-intake` refuses to render DOCX when the intake still contains unresolved placeholder text such as `TODO:` or `replace with explicit`, and the error reports the placeholder field paths.

Example command that should fail until placeholders are replaced:

```bash
python -m phoenix_office.cli proposal generate-from-intake output/abby_hill_placeholder_intake.json output/abby_hill_proposal.docx --template tests/fixtures/templates/a1_proposal_template.docx
```

Use the explicit override only when the operator intentionally wants placeholder text rendered into the DOCX:

```bash
python -m phoenix_office.cli proposal generate-from-intake output/abby_hill_placeholder_intake.json output/abby_hill_proposal.docx --template tests/fixtures/templates/a1_proposal_template.docx --allow-placeholder-intake
```

Generated DOCX files are local output artifacts. Do not commit generated proposal outputs, private customer data, or real customer documents.

## Boundaries

This workflow does not:

- call AI or LLM services
- infer pricing, scope, notes, item descriptions, or customer data
- mutate records
- trigger workflows
- run background workers
- send, submit, approve, or file proposals

DOCX generation remains the explicit `generate-from-intake` step. All previous steps are validation, inspection, or JSON preparation only.
