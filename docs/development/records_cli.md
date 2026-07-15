# Records CLI Workflow

The records CLI is a developer/internal tool for working with SQLite-backed customer and job records in Phoenix Office. It is intended for local inspection, fixture loading, smoke testing, and deterministic record-backed proposal work.

Normal writable record-store commands may initialize a missing database and its tables. `records proposal-build` is the bounded exception: it requires an existing initialized database and opens it through non-initializing immutable read-only repositories.

## Supported Commands

### Record Import

```bash
python -m phoenix_office.cli records import customer examples/records/customer_abby_hill.json --db output/records.sqlite
python -m phoenix_office.cli records import job examples/records/job_abby_hill.json --db output/records.sqlite
python -m phoenix_office.cli records import customers path/to/customers.json --db output/records.sqlite
python -m phoenix_office.cli records import jobs path/to/jobs.json --db output/records.sqlite
```

These are writable commands. They may initialize a missing database and save records.

### Record Inspection

```bash
python -m phoenix_office.cli records list customers --db output/records.sqlite
python -m phoenix_office.cli records list jobs --db output/records.sqlite
python -m phoenix_office.cli records show customer customer-abby-hill --db output/records.sqlite
python -m phoenix_office.cli records show job job-abby-hill --db output/records.sqlite
```

`list` and `show` do not modify existing record rows. They use the normal record-store construction path, which may initialize a missing database. This differs from the stricter `proposal-build` database boundary described below.

### Record Export

```bash
python -m phoenix_office.cli records export customers output/customers.json --db output/records.sqlite
python -m phoenix_office.cli records export jobs output/jobs.json --db output/records.sqlite
```

Export commands write JSON through the existing file-export helpers and may create output parent directories.

### Proposal Details Validation

```bash
python -m phoenix_office.cli records proposal-details validate examples/records/proposal_details_abby_hill.json
```

For new jobs, operators may copy `examples/records/proposal_details_template.json` as a starter `RecordProposalDetails` file. It is only a starter: replace every instructional or starter value manually before building or sending. Passing validation does not prove that every instructional phrase has been removed or that the business wording is complete. Proposal date, description, scope, pricing, notes, and company configuration remain explicit operator-authored inputs.

The placeholder validator currently recognizes strings containing the configured markers `todo:` or `replace with explicit`, case-insensitively. It is not a comprehensive detector of every draft or instructional phrase. Operators must manually review proposal date, item description, scope, pricing, notes, company information, normalized JSON, and DOCX; human review remains the final safety boundary.

Current sanitized details fixtures include:

- `examples/records/proposal_details_template.json`
- `examples/records/proposal_details_abby_hill.json`
- `examples/records/proposal_details_sample_north_prairie.json`

### ProposalInput Composition

```bash
python -m phoenix_office.cli records proposal-input customer-abby-hill job-abby-hill examples/records/proposal_details_abby_hill.json output/abby_hill_proposal_input.json --db output/records.sqlite
```

`records proposal-input` combines an existing `CustomerRecord`, an existing `JobRecord`, and explicit `RecordProposalDetails`, then writes `ProposalInput` JSON only. It does not render DOCX.

### Record-Backed Proposal Build

After the selected customer and job records already exist in SQLite, the bounded convenience command can produce both reviewable artifacts:

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

Abby Hill example:

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

#### Inputs

- `CUSTOMER_ID`: exact existing `CustomerRecord` identifier.
- `JOB_ID`: exact existing `JobRecord` identifier.
- `DETAILS_JSON`: explicit operator-authored `RecordProposalDetails` JSON.
- `OUTPUT_PROPOSAL_INPUT_JSON`: explicit path for normalized reviewable `ProposalInput` JSON.
- `OUTPUT_DOCX`: explicit path for the matching proposal DOCX.
- `--db RECORDS_SQLITE`: existing initialized SQLite records database.
- `--template TEMPLATE_DOCX`: explicit openable DOCX template.

The command infers no pricing, scope, notes, date, customer, job, description, company data, or template.

#### Outputs

On success, the command produces:

- normalized reviewable `ProposalInput` JSON;
- a matching DOCX rendered from the same in-memory `ProposalInput`;
- the existing human-readable proposal-inspection summary; and
- both final output paths.

It returns success only after both final artifacts exist. It does not send, upload, file, approve, or otherwise deliver either artifact. Human review and manual sending remain required.

#### Database Safety

`proposal-build` requires the database file and selected records to exist already. It does not call record import, initialize missing tables, update records, or mutate records.

The read-only repositories resolve the database target, reject existing `-wal`, `-shm`, or `-journal` sidecars beside that target, and then connect with SQLite URI `mode=ro&immutable=1`. The command never deletes, repairs, or alters existing sidecars. If active sidecar state exists, stop and make the database closed and consistent through its owning application or process before retrying.

`immutable=1` assumes no other process modifies the database during the build. Concurrent modification during an immutable read is unsupported. The command provides no locking, snapshotting, recovery, repair, or database service.

#### Output Safety

The command:

- rejects values containing the validator's currently configured placeholder markers and exposes no build-command bypass;
- refuses identical output paths;
- refuses to overwrite either existing output;
- checks both collisions before creating either artifact;
- stages normalized JSON and rendered DOCX as temporary sibling files;
- publishes final artifacts with exclusive creation;
- rolls back a final artifact created by the current attempt if publication is incomplete; and
- removes temporary siblings on success and failure.

## Independent Proposal Commands

Validate existing `ProposalInput` JSON:

```bash
python -m phoenix_office.cli proposal validate output/abby_hill_proposal_input.json
```

Inspect it without mutation or rendering:

```bash
python -m phoenix_office.cli proposal inspect output/abby_hill_proposal_input.json
```

Render an existing `ProposalInput` JSON independently:

```bash
python -m phoenix_office.cli proposal generate output/abby_hill_proposal_input.json output/abby_hill_proposal.docx --template tests/fixtures/templates/a1_proposal_template.docx
```

`proposal validate` validates JSON only. `proposal inspect` validates, loads, and summarizes JSON without rendering or mutation. `proposal generate` remains independently available and retains its separate legacy placeholder-bypass option; `records proposal-build` exposes no such bypass.

## Preserved Transparent Record-Backed Workflow

The explicit multi-command path remains supported:

```bash
python -m phoenix_office.cli records import customer examples/records/customer_abby_hill.json --db output/records.sqlite
python -m phoenix_office.cli records import job examples/records/job_abby_hill.json --db output/records.sqlite
python -m phoenix_office.cli records proposal-details validate examples/records/proposal_details_abby_hill.json
python -m phoenix_office.cli records proposal-input customer-abby-hill job-abby-hill examples/records/proposal_details_abby_hill.json output/abby_hill_proposal_input.json --db output/records.sqlite
python -m phoenix_office.cli proposal validate output/abby_hill_proposal_input.json
python -m phoenix_office.cli proposal inspect output/abby_hill_proposal_input.json
python -m phoenix_office.cli proposal generate output/abby_hill_proposal_input.json output/abby_hill_proposal.docx --template tests/fixtures/templates/a1_proposal_template.docx
```

Record import remains separate from proposal build. `RecordProposalDetails` remains the explicit business-detail source, and `ProposalInput` remains the deterministic renderer input.

For the full walkthrough, see the [proposal workflow runbook](proposal_workflow_runbook.md). For a condensed operator aid, see the [proposal workflow operator checklist](proposal_workflow_operator_checklist.md). For generated local file handling, see [output artifact conventions](output_artifact_conventions.md).

## Current Non-Goals

The records CLI does not provide:

- record edit, update, or delete commands;
- a web UI;
- natural-language intake or AI inference;
- automatic pricing, scope, notes, date, customer, job, description, company-data, or template decisions;
- an orchestrator or workflow execution framework;
- worker or plugin runtime execution;
- PDF generation through the record-backed proposal build;
- automatic review, approval, sending, email, upload, filing, or delivery; or
- unattended customer-facing operation.

`records proposal-build` is one deterministic local convenience over existing composition and rendering components. It is not record intake, automation, orchestration, approval, or delivery. Existing record import, list, show, and export behavior remains unchanged.
