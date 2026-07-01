# A-1 Proposal Intake CLI Workflow

## Purpose

This guide shows the current manual CLI flow for preparing an A-1 proposal from explicit intake JSON. The commands are deterministic and operator-driven. They do not infer missing pricing, scope, notes, item descriptions, or customer data.

Use this workflow when starting from an A-1 intake JSON draft rather than record-backed customer and job records.

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

## 2. Validate Intake JSON

Validate the intake file without printing the full summary:

```bash
python -m phoenix_office.cli proposal intake-validate output/a1_proposal_intake.json
```

For machine-readable validation output:

```bash
python -m phoenix_office.cli proposal intake-validate output/a1_proposal_intake.json --json
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

## 5. Generate DOCX From Intake

When the intake has been reviewed and the operator explicitly wants a DOCX artifact, run:

```bash
python -m phoenix_office.cli proposal generate-from-intake output/a1_proposal_intake.json output/a1_proposal.docx --template tests/fixtures/templates/a1_proposal_template.docx
```

Generated DOCX files are local output artifacts. Do not commit generated proposal outputs, private customer data, or real customer documents.

## Boundaries

This workflow does not:

- call AI or LLM services
- read customer or job records
- infer pricing, scope, notes, item descriptions, or customer data
- mutate records
- trigger workflows
- run background workers
- send, submit, approve, or file proposals

DOCX generation remains the explicit `generate-from-intake` step. All previous steps are validation, inspection, or JSON preparation only.
