# Proposal Workflow Runbook

## Purpose

This runbook explains how to manually operate the current record-backed A-1 proposal workflow in Phoenix Office. It is intended for developers and operators who need to import stored record data, compose a `ProposalInput` JSON file, and generate a DOCX proposal through the existing CLI.

For a shorter step-by-step operator aid, see the [proposal workflow operator checklist](proposal_workflow_operator_checklist.md). For the records command reference, see the [records CLI workflow](records_cli.md).

This is a manual CLI workflow. It does not describe an orchestrator, worker execution, natural-language intake, plugin runtime behavior, or automated proposal pipeline.

## Current Workflow Overview

The current workflow is:

```text
CustomerRecord / JobRecord JSON
  -> import into SQLite RecordStore
  -> optionally validate explicit RecordProposalDetails JSON
  -> compose ProposalInput JSON using explicit RecordProposalDetails
  -> optionally validate composed ProposalInput JSON
  -> optionally inspect composed ProposalInput JSON
  -> render DOCX using proposal generate
```

The supported command chain is:

```bash
python -m phoenix_office.cli records import customer examples/records/customer_abby_hill.json --db output/records.sqlite
python -m phoenix_office.cli records import job examples/records/job_abby_hill.json --db output/records.sqlite
python -m phoenix_office.cli records proposal-details validate examples/records/proposal_details_abby_hill.json
python -m phoenix_office.cli records proposal-input customer-abby-hill job-abby-hill examples/records/proposal_details_abby_hill.json output/abby_hill_proposal_input.json --db output/records.sqlite
python -m phoenix_office.cli proposal validate output/abby_hill_proposal_input.json
python -m phoenix_office.cli proposal inspect output/abby_hill_proposal_input.json
python -m phoenix_office.cli proposal generate output/abby_hill_proposal_input.json output/abby_hill_proposal.docx --template tests/fixtures/templates/a1_proposal_template.docx
```

`records proposal-details validate` is an optional preflight check for explicit proposal details JSON. `records proposal-input` writes `ProposalInput` JSON only. `proposal validate` is an optional preflight check for composed `ProposalInput` JSON. `proposal inspect` is an optional review step that validates and loads `ProposalInput` JSON, then prints a human-readable summary without generating a DOCX. `proposal generate` remains responsible for DOCX generation.

## Required Input Files

The Abby Hill example workflow uses these files:

- `examples/records/customer_abby_hill.json`
- `examples/records/job_abby_hill.json`
- `examples/records/proposal_details_abby_hill.json`
- `tests/fixtures/templates/a1_proposal_template.docx`

The workflow also uses local output paths:

- `output/records.sqlite`
- `output/abby_hill_proposal_input.json`
- `output/abby_hill_proposal.docx`

The SQLite database file is created automatically when the records store is opened.

## CustomerRecord JSON

A `CustomerRecord` contains customer identity and optional billing/contact fields. In the current proposal workflow, the customer record provides the proposal customer name.

Example path:

```text
examples/records/customer_abby_hill.json
```

The record must include a `customer_id`. That ID is used later when composing proposal input JSON:

```bash
customer-abby-hill
```

## JobRecord JSON

A `JobRecord` contains job identity, the related `customer_id`, job name, site address fields, status, tank fields, and job notes. In the current proposal workflow, the job record provides the proposal site street address and city/state/ZIP.

Example path:

```text
examples/records/job_abby_hill.json
```

The job record must reference the same `customer_id` as the selected customer record. The adapter validates this relationship when composing `ProposalInput`.

## RecordProposalDetails JSON

`RecordProposalDetails` is explicit user/business input for proposal generation. It provides fields that are not inferred from records, including:

- proposal date
- item description
- scope items
- pricing
- notes
- company configuration

Example path:

```text
examples/records/proposal_details_abby_hill.json
```

Starter template path:

```text
examples/records/proposal_details_template.json
```

Operators may copy the starter template when preparing details for a new job. Replace all placeholder values before sending a proposal; scope, pricing, and notes are still operator-authored and are not inferred from records. The template does not add automation or orchestration.

Pricing is not inferred from records. Scope is not inferred from records. The operator is responsible for supplying the intended pricing and scope in `RecordProposalDetails`.

## Validating RecordProposalDetails JSON

Optionally validate the explicit proposal details file before composing `ProposalInput` JSON:

```bash
python -m phoenix_office.cli records proposal-details validate examples/records/proposal_details_abby_hill.json
```

This command validates `RecordProposalDetails` JSON only. It does not compose `ProposalInput`, read customer records, read job records, open SQLite, generate DOCX, or infer pricing or scope.

## Importing Records Into SQLite

Import the customer record into the SQLite-backed record store:

```bash
python -m phoenix_office.cli records import customer examples/records/customer_abby_hill.json --db output/records.sqlite
```

Import the job record into the same SQLite-backed record store:

```bash
python -m phoenix_office.cli records import job examples/records/job_abby_hill.json --db output/records.sqlite
```

Both commands write to `output/records.sqlite`. If the database does not exist, Phoenix Office initializes it automatically.

## Composing ProposalInput JSON

Compose a `ProposalInput` JSON file from the stored customer record, stored job record, and explicit proposal details file:

```bash
python -m phoenix_office.cli records proposal-input customer-abby-hill job-abby-hill examples/records/proposal_details_abby_hill.json output/abby_hill_proposal_input.json --db output/records.sqlite
```

This command:

- reads `customer-abby-hill` from the SQLite records database
- reads `job-abby-hill` from the same SQLite records database
- reads `examples/records/proposal_details_abby_hill.json`
- validates that the customer and job IDs match
- writes deterministic `ProposalInput` JSON to `output/abby_hill_proposal_input.json`

This command does not generate a DOCX file.

## Validating ProposalInput JSON

Optionally validate the composed `ProposalInput` JSON before generating the DOCX proposal:

```bash
python -m phoenix_office.cli proposal validate output/abby_hill_proposal_input.json
```

This command validates `ProposalInput` JSON only. It does not generate DOCX, load a DOCX template, read customer records, read job records, open SQLite, or infer pricing or scope.

## Inspecting ProposalInput JSON

Optionally inspect the composed `ProposalInput` JSON before generating the DOCX proposal:

```bash
python -m phoenix_office.cli proposal inspect output/abby_hill_proposal_input.json
```

This command validates and loads `ProposalInput` JSON, then prints a short human-readable summary. It does not generate DOCX, load a DOCX template, read customer records, read job records, open SQLite, or infer pricing or scope.

## Generating The DOCX Proposal

Generate the DOCX proposal from the composed `ProposalInput` JSON and the A-1 DOCX template:

```bash
python -m phoenix_office.cli proposal generate output/abby_hill_proposal_input.json output/abby_hill_proposal.docx --template tests/fixtures/templates/a1_proposal_template.docx
```

This command uses the existing proposal generation path and DOCX renderer. It is separate from the records CLI commands.

## Explicit Vs Inferred Data Boundaries

The current workflow deliberately separates stored records from proposal-specific business details.

Record-backed fields:

- `ProposalInput.customer_name` comes from `CustomerRecord.display_name`.
- `ProposalInput.street_address` comes from `JobRecord.site_street_address`.
- `ProposalInput.city_state_zip` comes from `JobRecord.site_city_state_zip`.

Explicit details fields:

- `proposal_date`
- `item_description`
- `scope_items`
- `pricing`
- `notes`
- `company_config`

Not inferred:

- pricing is not inferred from customer or job records
- scope is not inferred from customer or job records
- item description is not inferred from customer or job records
- notes are not inferred from internal job notes

This keeps the workflow reviewable and prevents records from silently changing proposal business terms.

## Troubleshooting Common CLI Issues

Customer not found:

```text
Customer not found: customer-abby-hill
```

Confirm the customer was imported into the same SQLite database passed with `--db`.

Job not found:

```text
Job not found: job-abby-hill
```

Confirm the job was imported into the same SQLite database passed with `--db`.

Customer/job mismatch:

```text
Error: failed to compose proposal input: CustomerRecord and JobRecord customer IDs do not match
```

Confirm the selected job belongs to the selected customer.

Invalid proposal details JSON:

```text
Error: invalid RecordProposalDetails JSON: Invalid record proposal details JSON
```

Confirm the details file is valid JSON and matches the `RecordProposalDetails` shape. Use `records proposal-details validate` as an optional preflight before `records proposal-input`.

Invalid proposal input JSON:

```text
Error: invalid proposal input: Invalid proposal input
```

Confirm the proposal input file is valid JSON and matches the `ProposalInput` shape. Use `proposal validate` as an optional preflight before `proposal generate`, or `proposal inspect` to validate and print a review summary.

Missing template:

```text
Error: DOCX template file does not exist: tests/fixtures/templates/a1_proposal_template.docx
```

Confirm the template path exists relative to the current working directory.

Missing proposal input JSON:

```text
Error: JSON input file does not exist: output/abby_hill_proposal_input.json
```

Run `records proposal-input` before `proposal validate`, `proposal inspect`, or `proposal generate`, and confirm the output path matches.

## Current Limitations / Future Work

Current limitations:

- The workflow is manual CLI operation.
- No natural-language intake exists yet.
- No orchestrator exists yet.
- No worker execution exists yet.
- No plugin runtime behavior exists yet.
- No pricing inference from records exists.
- No scope inference from records exists.
- No shortcut command exists for the full workflow.

Potential future work may include higher-level workflow coordination, richer operator prompts, approval gates, or automation. Those capabilities do not exist in the current workflow and should not be assumed by this runbook.
