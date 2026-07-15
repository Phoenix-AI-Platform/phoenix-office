# Proposal Workflow Runbook

## Purpose

This runbook explains how to operate the current deterministic, record-backed A-1 proposal workflow in Phoenix Office. It supports an optional one-command build after records already exist and the preserved transparent multi-command path.

For readiness criteria, see [A-1 proposal MVP acceptance](a1_proposal_mvp_acceptance.md). For a shorter operator aid, see the [proposal workflow operator checklist](proposal_workflow_operator_checklist.md). For command reference, see the [records CLI workflow](records_cli.md). For generated local file handling, see [output artifact conventions](output_artifact_conventions.md).

Both paths are manual local CLI operation. They do not provide an orchestrator, worker execution, natural-language intake, AI inference, plugin runtime behavior, automatic approval, or delivery.

## Supported Paths

### Optional One-Command Build After Records Exist

Use this convenience path when the selected customer and job records already exist in the SQLite database:

```text
existing CustomerRecord / JobRecord in SQLite
  -> explicit RecordProposalDetails JSON
  -> records proposal-build
  -> normalized ProposalInput JSON
  -> matching DOCX
  -> human review
  -> manual sending
```

```bash
python -m phoenix_office.cli records proposal-build \
  customer-abby-hill \
  job-abby-hill \
  examples/records/proposal_details_abby_hill.json \
  output/abby_hill_proposal_input.json \
  output/abby_hill_proposal.docx \
  --db output/records.sqlite \
  --template tests/fixtures/templates/a1_proposal_template.docx
```

This command requires explicit customer and job IDs, explicit operator-authored `RecordProposalDetails`, an existing SQLite database, an explicit DOCX template, and explicit JSON and DOCX output paths.

It reads existing records, composes exactly one in-memory `ProposalInput`, rejects unresolved placeholders, writes normalized reviewable JSON, renders a matching DOCX from the same proposal, prints the established proposal-inspection summary and both paths, and succeeds only after both final artifacts exist.

It does not import or mutate records, infer business inputs, or send or deliver artifacts. The operator must review the JSON and DOCX and decide manually whether to send the proposal.

### Preserved Transparent Multi-Command Path

Use this path when records must first be imported or when each intermediate boundary should be run and reviewed independently:

```text
CustomerRecord / JobRecord JSON
  -> import into SQLite
  -> validate RecordProposalDetails
  -> compose ProposalInput
  -> validate ProposalInput
  -> inspect ProposalInput
  -> generate DOCX
  -> human review
  -> manual sending
```

```bash
python -m phoenix_office.cli records import customer examples/records/customer_abby_hill.json --db output/records.sqlite
python -m phoenix_office.cli records import job examples/records/job_abby_hill.json --db output/records.sqlite
python -m phoenix_office.cli records proposal-details validate examples/records/proposal_details_abby_hill.json
python -m phoenix_office.cli records proposal-input customer-abby-hill job-abby-hill examples/records/proposal_details_abby_hill.json output/abby_hill_proposal_input.json --db output/records.sqlite
python -m phoenix_office.cli proposal validate output/abby_hill_proposal_input.json
python -m phoenix_office.cli proposal inspect output/abby_hill_proposal_input.json
python -m phoenix_office.cli proposal inspect output/abby_hill_proposal_input.json --json
python -m phoenix_office.cli proposal generate output/abby_hill_proposal_input.json output/abby_hill_proposal.docx --template tests/fixtures/templates/a1_proposal_template.docx
```

`records proposal-details validate` validates explicit details only. `records proposal-input` writes JSON only. `proposal validate` validates JSON only. `proposal inspect` remains read-only. `proposal generate` remains independently available for rendering an existing `ProposalInput` JSON file. Its separate legacy placeholder bypass remains unchanged; the `proposal-build` convenience exposes no bypass. Existing record import, list, show, and export behavior remains unchanged.

## Required Inputs And Local Outputs

The Abby Hill workflow uses:

- `examples/records/customer_abby_hill.json`
- `examples/records/job_abby_hill.json`
- `examples/records/proposal_details_abby_hill.json`
- `tests/fixtures/templates/a1_proposal_template.docx`
- `output/records.sqlite`
- `output/abby_hill_proposal_input.json`
- `output/abby_hill_proposal.docx`

See [output artifact conventions](output_artifact_conventions.md) for recommended generated file layout and commit policy.

The convenience build requires `output/records.sqlite` or another selected database to exist already. Normal writable record import commands may initialize a missing database; `records proposal-build` does not.

## CustomerRecord JSON

A `CustomerRecord` contains customer identity and optional billing/contact fields. The selected record supplies the proposal customer name.

Example path:

```text
examples/records/customer_abby_hill.json
```

The record's exact identifier is supplied to proposal commands:

```text
customer-abby-hill
```

## JobRecord JSON

A `JobRecord` contains job identity, related `customer_id`, job name, site address fields, status, tank fields, and job notes. The selected job supplies the proposal site street address and city/state/ZIP.

Example path:

```text
examples/records/job_abby_hill.json
```

The job must reference the selected customer. Existing deterministic composition validation rejects a customer/job mismatch.

## RecordProposalDetails JSON

`RecordProposalDetails` is explicit operator-authored business input. It provides:

- proposal date;
- item description;
- scope items;
- pricing;
- notes; and
- company configuration.

Example path:

```text
examples/records/proposal_details_abby_hill.json
```

Starter template:

```text
examples/records/proposal_details_template.json
```

Additional sanitized sample:

```text
examples/records/proposal_details_sample_north_prairie.json
```

Replace every placeholder before a proposal build. Phoenix Office does not infer pricing, scope, notes, proposal date, customer, job, item description, company data, or template.

## Importing Records Into SQLite

When the records do not yet exist, import them separately:

```bash
python -m phoenix_office.cli records import customer examples/records/customer_abby_hill.json --db output/records.sqlite
python -m phoenix_office.cli records import job examples/records/job_abby_hill.json --db output/records.sqlite
```

These normal writable commands save records and may initialize a missing database. Record import is not part of `records proposal-build`.

## Validating RecordProposalDetails

Optionally validate explicit details independently:

```bash
python -m phoenix_office.cli records proposal-details validate examples/records/proposal_details_abby_hill.json
```

This reads and validates `RecordProposalDetails` JSON only. It does not compose `ProposalInput`, open SQLite, render DOCX, or infer business data.

## Running The Optional Proposal Build

Once the customer and job exist in the selected database, run:

```bash
python -m phoenix_office.cli records proposal-build \
  CUSTOMER_ID \
  JOB_ID \
  DETAILS_JSON \
  OUTPUT_PROPOSAL_INPUT_JSON \
  OUTPUT_DOCX \
  --db RECORDS_SQLITE \
  --template TEMPLATE_DOCX
```

The command uses the same composed `ProposalInput` object for placeholder checks, normalized JSON serialization, summary output, and DOCX rendering. It prints:

```text
Customer: ...
Site Address: ...
Item Description: ...
Scope Items: ...
Pricing Lines: 1
Total: ...
Notes: ...
Company: ...
ProposalInput JSON: <path>
Proposal DOCX: <path>
```

No private record payload is printed.

## Proposal-Build Database Safety

The command opens the database through non-initializing read-only customer and job repositories. Those repositories:

1. resolve the database target;
2. reject existing `-wal`, `-shm`, or `-journal` files beside the resolved target; and
3. connect through SQLite URI `mode=ro&immutable=1`.

The command does not initialize missing tables, save records, delete sidecars, repair the database, or alter existing sidecar bytes. A zero-byte, partial, or active-sidecar database fails closed.

`immutable=1` assumes that no other process modifies the database during the proposal build. Concurrent database mutation is unsupported. TASK-043 added no locking, snapshot service, recovery path, repair path, background worker, or database orchestration service.

## Proposal-Build Output Safety

Before creating output directories or artifacts, the command validates the explicit paths, database, details, template, records, composition, and placeholders.

It then:

- refuses identical output paths;
- refuses to overwrite either existing output;
- stages normalized JSON and rendered DOCX as temporary siblings;
- verifies both staged artifacts;
- publishes each final artifact with exclusive creation;
- removes a final artifact created by the current attempt if publication is incomplete; and
- removes temporary siblings on success and failure.

The command sends, uploads, files, approves, or delivers neither artifact.

## Composing ProposalInput Independently

The transparent path remains available:

```bash
python -m phoenix_office.cli records proposal-input customer-abby-hill job-abby-hill examples/records/proposal_details_abby_hill.json output/abby_hill_proposal_input.json --db output/records.sqlite
```

This command reads the selected records and explicit details and writes deterministic `ProposalInput` JSON only. It does not render DOCX.

## Validating ProposalInput Independently

```bash
python -m phoenix_office.cli proposal validate output/abby_hill_proposal_input.json
```

This validates `ProposalInput` JSON only. It does not render, read records, or infer business data.

## Inspecting ProposalInput Independently

Human-readable inspection:

```bash
python -m phoenix_office.cli proposal inspect output/abby_hill_proposal_input.json
```

Machine-readable inspection:

```bash
python -m phoenix_office.cli proposal inspect output/abby_hill_proposal_input.json --json
```

Both inspection forms are read-only. They validate and load `ProposalInput` JSON and print review output without mutation or rendering.

## Generating DOCX Independently

```bash
python -m phoenix_office.cli proposal generate output/abby_hill_proposal_input.json output/abby_hill_proposal.docx --template tests/fixtures/templates/a1_proposal_template.docx
```

`proposal generate` remains independently responsible for rendering from an existing `ProposalInput` JSON file. `records proposal-build` is the bounded convenience path that directly reuses existing composition and rendering components to emit both JSON and DOCX after records already exist.

## Explicit Versus Inferred Data Boundaries

Record-backed fields:

- `ProposalInput.customer_name` comes from `CustomerRecord.display_name`.
- `ProposalInput.street_address` comes from `JobRecord.site_street_address`.
- `ProposalInput.city_state_zip` comes from `JobRecord.site_city_state_zip`.

Explicit details fields:

- `proposal_date`;
- `item_description`;
- `scope_items`;
- `pricing`;
- `notes`; and
- `company_config`.

No pricing, scope, notes, date, customer, job, description, company data, or template is inferred. This keeps the workflow reviewable and prevents stored records from silently changing proposal business terms.

## Troubleshooting

### Missing Database

```text
Error: records database does not exist: <path>
```

`records proposal-build` requires an existing initialized database and must not create one. If records have not been stored, import them through the separate record commands first.

### Customer Not Found

```text
Customer not found: customer-abby-hill
```

Confirm the exact customer ID exists in the database passed with `--db`.

### Job Not Found

```text
Job not found: job-abby-hill
```

Confirm the exact job ID exists in the same database.

### Customer/Job Mismatch

```text
Error: failed to compose proposal input for customer <customer-id> and job <job-id>
```

Existing deterministic composition validation rejects a job belonging to another customer. Select a matching pair; do not alter records through proposal build.

### Invalid Proposal Details

```text
Error: invalid RecordProposalDetails JSON: <path>
```

Confirm the file is valid JSON matching the `RecordProposalDetails` shape. Use `records proposal-details validate` as an optional independent preflight.

### Unresolved Placeholders

```text
Error: unresolved placeholder text in composed proposal; refusing proposal build.
```

Replace every reported field in the explicit details. `records proposal-build` exposes no placeholder bypass.

### Missing Or Corrupt Template

```text
Error: DOCX template file does not exist: <path>
Error: DOCX template is not usable: <path>
```

Provide an existing, openable DOCX template. The build validates it before final outputs.

### Existing JSON Output

```text
Error: proposal input JSON output already exists: <path>
```

Choose a new JSON path. The existing file remains unchanged, and the DOCX is not created.

### Existing DOCX Output

```text
Error: proposal DOCX output already exists: <path>
```

Choose a new DOCX path. The existing file remains unchanged, and the JSON is not created.

### Identical Output Paths

```text
Error: proposal output paths must be different
```

Provide distinct JSON and DOCX destinations. The command fails before producing either artifact.

### Existing WAL, SHM, Or Journal State

```text
Error: failed to read records database: <path>
```

The immutable read boundary rejects existing SQLite `-wal`, `-shm`, or `-journal` state. It does not delete or repair sidecars. Stop, ensure the database is closed and consistent through its owning application or process, and retry only when no active sidecar state remains. Do not manually delete sidecars as a normal workaround.

## Manual Review Before Sending

After either workflow finishes:

1. review the normalized `ProposalInput` JSON;
2. open the DOCX;
3. verify customer name and site address;
4. verify scope, pricing, notes, company information, payment terms, and signature area; and
5. decide manually whether and how to send the proposal.

Phoenix Office does not approve, send, upload, file, or deliver the result.

## Current Limitations

- Manual local CLI operation only.
- No natural-language intake or AI inference.
- No automatic pricing, scope, notes, date, customer, job, description, company-data, or template decision.
- No orchestrator, worker execution, plugin runtime execution, API, or MCP.
- No scheduling or background operation.
- No PDF generation in this workflow.
- No automatic review, approval, email, upload, filing, sending, or delivery.
- No concurrent database mutation support for immutable proposal builds.
- No unattended customer-facing operation.
