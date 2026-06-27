# Records CLI Workflow

The records CLI is a developer/internal tool for working with SQLite-backed customer and job records in Phoenix Office. It is intended for local inspection, fixture loading, smoke testing, and early data workflow development.

Records are stored in a local SQLite database file. Missing database files are initialized automatically when a command opens the store.

## Supported Commands

Current import commands:

```bash
python -m phoenix_office.cli records import customer examples/records/customer_abby_hill.json --db output/records.sqlite
python -m phoenix_office.cli records import job examples/records/job_abby_hill.json --db output/records.sqlite
python -m phoenix_office.cli records import customers path/to/customers.json --db output/records.sqlite
python -m phoenix_office.cli records import jobs path/to/jobs.json --db output/records.sqlite
```

Current read-only inspection commands:

```bash
python -m phoenix_office.cli records list customers --db output/records.sqlite
python -m phoenix_office.cli records list jobs --db output/records.sqlite
python -m phoenix_office.cli records show customer customer-abby-hill --db output/records.sqlite
python -m phoenix_office.cli records show job job-abby-hill --db output/records.sqlite
```

Current export commands:

```bash
python -m phoenix_office.cli records export customers output/customers.json --db output/records.sqlite
python -m phoenix_office.cli records export jobs output/jobs.json --db output/records.sqlite
```

Current proposal details validation command:

```bash
python -m phoenix_office.cli records proposal-details validate examples/records/proposal_details_abby_hill.json
```

For new jobs, operators may copy `examples/records/proposal_details_template.json` as a starter `RecordProposalDetails` file. Replace all placeholder values before sending a proposal; scope, pricing, and notes remain operator-authored and are not inferred from records.

Current proposal details fixtures include `examples/records/proposal_details_template.json`, `examples/records/proposal_details_abby_hill.json`, and `examples/records/proposal_details_sample_north_prairie.json`.

Current proposal input composition command:

```bash
python -m phoenix_office.cli records proposal-input customer-abby-hill job-abby-hill examples/records/proposal_details_abby_hill.json output/abby_hill_proposal_input.json --db output/records.sqlite
```

Current proposal input validation command:

```bash
python -m phoenix_office.cli proposal validate output/abby_hill_proposal_input.json
```

Current proposal input inspection command:

```bash
python -m phoenix_office.cli proposal inspect output/abby_hill_proposal_input.json
```

The `list` and `show` commands are read-only. They open the SQLite-backed record store and print existing records without modifying them.

The `export` commands write JSON files. They export all customer or job records from the SQLite store and create parent directories through the existing file export helpers.

The `proposal-details validate` command validates `RecordProposalDetails` JSON only. It does not compose `ProposalInput`, read customer or job records, open SQLite, generate DOCX, or infer pricing or scope.

The `proposal-input` command writes a `ProposalInput` JSON file only. It combines an existing `CustomerRecord`, an existing `JobRecord`, and explicit `RecordProposalDetails` JSON. It does not generate a DOCX and does not infer pricing, scope, item description, or notes.

The `proposal validate` command validates `ProposalInput` JSON only. It does not generate DOCX, load a DOCX template, read records, open SQLite, or infer pricing or scope.

The `proposal inspect` command validates and loads `ProposalInput` JSON, then prints a short human-readable summary. It does not generate DOCX, load a DOCX template, read records, open SQLite, or infer pricing or scope.

DOCX generation remains the existing separate proposal command, using the generated proposal input JSON:

```bash
python -m phoenix_office.cli proposal generate output/abby_hill_proposal_input.json output/abby_hill_proposal.docx --template tests/fixtures/templates/a1_proposal_template.docx
```

## Record-backed Proposal Workflow

The current record-backed proposal workflow is an explicit-details-driven command chain. Records provide customer and job site fields, while `RecordProposalDetails` provides proposal date, item description, scope, pricing, notes, and company configuration.

For the full operator/developer walkthrough, see the [proposal workflow runbook](proposal_workflow_runbook.md). For a condensed before-generation checklist, see the [proposal workflow operator checklist](proposal_workflow_operator_checklist.md).

```bash
python -m phoenix_office.cli records import customer examples/records/customer_abby_hill.json --db output/records.sqlite
python -m phoenix_office.cli records import job examples/records/job_abby_hill.json --db output/records.sqlite
python -m phoenix_office.cli records proposal-details validate examples/records/proposal_details_abby_hill.json
python -m phoenix_office.cli records proposal-input customer-abby-hill job-abby-hill examples/records/proposal_details_abby_hill.json output/abby_hill_proposal_input.json --db output/records.sqlite
python -m phoenix_office.cli proposal validate output/abby_hill_proposal_input.json
python -m phoenix_office.cli proposal inspect output/abby_hill_proposal_input.json
python -m phoenix_office.cli proposal generate output/abby_hill_proposal_input.json output/abby_hill_proposal.docx --template tests/fixtures/templates/a1_proposal_template.docx
```

`records proposal-details validate` is an optional preflight check for explicit proposal details JSON. `records proposal-input` writes `ProposalInput` JSON only. `proposal validate` is an optional preflight check for composed `ProposalInput` JSON. `proposal inspect` is an optional review step that prints a human-readable summary without rendering a DOCX. `proposal generate` remains the command that renders the DOCX artifact. This workflow is not natural-language intake, and pricing or scope are not inferred from records.

## Abby Hill Example

The repository includes example records that can be imported into a local development database:

```bash
python -m phoenix_office.cli records import customer examples/records/customer_abby_hill.json --db output/records.sqlite
python -m phoenix_office.cli records import job examples/records/job_abby_hill.json --db output/records.sqlite
```

After import, inspect the records:

```bash
python -m phoenix_office.cli records list customers --db output/records.sqlite
python -m phoenix_office.cli records list jobs --db output/records.sqlite
python -m phoenix_office.cli records show customer customer-abby-hill --db output/records.sqlite
python -m phoenix_office.cli records show job job-abby-hill --db output/records.sqlite
```

Optionally validate the explicit proposal details before composing proposal input JSON:

```bash
python -m phoenix_office.cli records proposal-details validate examples/records/proposal_details_abby_hill.json
```

Compose a proposal input JSON file from the imported records plus explicit proposal details:

```bash
python -m phoenix_office.cli records proposal-input customer-abby-hill job-abby-hill examples/records/proposal_details_abby_hill.json output/abby_hill_proposal_input.json --db output/records.sqlite
```

Optionally validate the composed proposal input before generating a DOCX:

```bash
python -m phoenix_office.cli proposal validate output/abby_hill_proposal_input.json
```

Optionally inspect the composed proposal input summary before generating a DOCX:

```bash
python -m phoenix_office.cli proposal inspect output/abby_hill_proposal_input.json
```

Export the records back to JSON:

```bash
python -m phoenix_office.cli records export customers output/records_customers.json --db output/records.sqlite
python -m phoenix_office.cli records export jobs output/records_jobs.json --db output/records.sqlite
```

## Current Non-Goals

The records CLI does not currently provide:

- edit, delete, or update commands
- web UI
- natural language intake
- orchestrator behavior
- worker execution
- proposal generation from records

Proposal generation still uses the existing proposal input and DOCX rendering flow. Records can compose proposal input JSON, but records commands do not render DOCX files.
