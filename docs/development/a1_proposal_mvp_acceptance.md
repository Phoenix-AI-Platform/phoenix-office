# A-1 Proposal MVP Acceptance

## Purpose

This document defines the readiness criteria for Phoenix Office v0.1 as an internal manual A-1 proposal generation workflow.

It covers the deterministic, record-backed workflow already implemented in Phoenix Office. It does not define autonomous execution, natural-language intake, or customer-facing unattended use.

## Current Supported Workflows

Phoenix Office supports two manual paths. Both preserve explicit operator-authored business details, a reviewable `ProposalInput`, human review, and manual sending.

### Optional Convenience Path After Records Exist

```text
existing CustomerRecord / JobRecord in SQLite
  -> explicit RecordProposalDetails JSON
  -> records proposal-build
  -> normalized ProposalInput JSON
  -> matching DOCX
  -> human review
  -> manual sending
```

Command contract:

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

The command requires the customer and job records to exist already. It opens the existing database through non-initializing immutable repositories, composes one in-memory `ProposalInput`, and uses that same proposal for normalized JSON and DOCX output. It prints the established proposal-inspection summary and both final paths, and succeeds only after both final artifacts exist.

### Preserved Transparent Path

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

The commands remain independently available:

```text
records proposal-details validate
records proposal-input
proposal validate
proposal inspect
proposal generate
```

Record import remains a separate prerequisite when the selected customer and job do not already exist in SQLite. Normal writable record commands may initialize a missing database, and existing record import, list, show, and export behavior remains unchanged. `records proposal-input` writes JSON only, `proposal validate` validates JSON only, `proposal inspect` is read-only, and `proposal generate` remains independently available for rendering an existing `ProposalInput` JSON file. The legacy placeholder bypass on the separate `proposal generate` command is unchanged and is not available on `records proposal-build`.

## Required Operator-Authored Inputs

- explicit customer ID
- explicit job ID
- explicit `RecordProposalDetails` JSON
- existing SQLite database containing the selected records
- explicit DOCX template
- explicit output `ProposalInput` JSON path
- explicit output DOCX path

When records are not already stored, the operator must separately provide and import `CustomerRecord` and `JobRecord` JSON first.

`RecordProposalDetails` remains the source of operator-authored proposal business details, including proposal date, item description, scope, pricing, notes, and company configuration. Phoenix Office does not infer those values, the customer or job identity, or the template.

## Verified Examples

The repository includes these sanitized proposal-details examples:

- `examples/records/proposal_details_abby_hill.json`
- `examples/records/proposal_details_sample_north_prairie.json`
- `examples/records/proposal_details_template.json`

The Abby Hill and Sample North Prairie workflows are covered by the record-backed proposal workflow tests.

## Implemented And Verified Capabilities

- [x] Customer and job record import into SQLite.
- [x] Explicit `RecordProposalDetails` validation before composition.
- [x] Deterministic `ProposalInput` composition from records plus explicit details.
- [x] `ProposalInput` JSON validation.
- [x] Read-only human-readable `ProposalInput` inspection.
- [x] Independent DOCX generation from `ProposalInput` and a template.
- [x] Optional `records proposal-build` after records already exist.
- [x] Normalized `ProposalInput` JSON and a matching DOCX from the same in-memory proposal.
- [x] Unresolved-placeholder rejection with no build-command bypass.
- [x] Identical-path and existing-output collision refusal.
- [x] Staged output publication, partial-publication rollback, and temporary-sibling cleanup.
- [x] Non-initializing immutable database reads and record non-mutation.
- [x] Fail-closed handling of existing WAL, SHM, or rollback-journal sidecars without deletion or repair.

## Per-Proposal Operator Requirements

These checks recur for every proposal and are not permanently completed platform capabilities:

- [ ] Customer name reviewed.
- [ ] Site address reviewed.
- [ ] Scope reviewed.
- [ ] Pricing reviewed.
- [ ] Notes reviewed.
- [ ] Company information reviewed.
- [ ] Payment terms reviewed.
- [ ] Acceptance/signature area reviewed.
- [ ] Generated DOCX opens successfully.
- [ ] Operator has made the manual send decision.
- [ ] Generated artifacts remain under `output/` or another local non-committed location.
- [ ] Real private customer outputs are not committed.

## Database And Output Safety

`records proposal-build` requires an existing database and does not import records, initialize missing tables, update records, or mutate records. It resolves the database target, rejects existing `-wal`, `-shm`, or `-journal` state, and then reads through SQLite URI `mode=ro&immutable=1`. Existing sidecars are never deleted, repaired, or altered.

`immutable=1` assumes the database is not being modified by another process during the build. Concurrent database modification is unsupported; the command adds no lock, snapshot service, recovery path, or repair behavior.

The build refuses identical output paths and refuses to overwrite either existing output. It stages both artifacts, publishes them exclusively, rolls back an artifact created by the attempt if final publication fails, and removes temporary siblings. It sends, uploads, files, approves, or otherwise delivers neither artifact.

## Test Coverage Summary

Current verified coverage includes:

- 45 focused record-backed proposal workflow tests.
- 1,312 full Phoenix Office tests.
- Immutable-read, resolved-target sidecar, record-non-mutation, collision, output-staging, rollback, cleanup, and preserved multi-command workflow coverage.

## Known Boundaries

- This is a manual local CLI workflow.
- No natural-language intake exists.
- No orchestrator exists.
- No worker or plugin runtime execution exists.
- No pricing, scope, notes, date, customer, job, description, company data, or template inference exists.
- Records are not imported or mutated by `records proposal-build`.
- No PDF generation exists in this workflow.
- Generated outputs are not automatically reviewed, approved, sent, uploaded, or filed.
- Immutable proposal builds do not support concurrent database mutation.

## Ready / Not Ready

Ready for:

- internal manual proposal workflow trials using sanitized or real local-only data
- deterministic JSON and DOCX generation followed by human review
- optional convenience builds after records already exist

Not ready for:

- autonomous execution
- customer-facing unattended use
- natural-language proposal intake
- automatic pricing, scope, or note decisions
- automatic approval
- automatic sending or filing

## Links

- [Project state](project_state.md)
- [Orchestration plan model](orchestration_plan_model.md)
- [Orchestration approval boundary](orchestration_approval_boundary.md)
- [Proposal workflow operator checklist](proposal_workflow_operator_checklist.md)
- [Proposal workflow runbook](proposal_workflow_runbook.md)
- [Records CLI workflow](records_cli.md)
- [Output artifact conventions](output_artifact_conventions.md)
