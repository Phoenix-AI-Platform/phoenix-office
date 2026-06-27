# A-1 Proposal MVP Acceptance

## Purpose

This document defines the readiness criteria for Phoenix Office v0.1 as an internal manual A-1 proposal generation workflow.

It is the acceptance checklist for the current deterministic, record-backed A-1 proposal workflow. It does not define autonomous execution, natural-language intake, or customer-facing unattended use.

## Current Supported Workflow

```text
CustomerRecord / JobRecord JSON
  -> import into SQLite RecordStore
  -> validate RecordProposalDetails JSON
  -> compose ProposalInput JSON
  -> validate ProposalInput JSON
  -> inspect ProposalInput summary
  -> generate DOCX proposal
```

## Required Operator-Authored Inputs

- `CustomerRecord` JSON
- `JobRecord` JSON
- `RecordProposalDetails` JSON
- DOCX template
- SQLite database path
- output `ProposalInput` JSON path
- output DOCX path

`RecordProposalDetails` remains the source of operator-authored proposal business details, including proposal date, item description, scope, pricing, notes, and company configuration.

## Verified Examples

The repository currently includes these proposal details examples:

- `examples/records/proposal_details_abby_hill.json`
- `examples/records/proposal_details_sample_north_prairie.json`
- `examples/records/proposal_details_template.json`

The Abby Hill and Sample North Prairie workflows are covered by CLI workflow smoke tests.

## MVP Acceptance Checklist

- [ ] Customer and job records can be imported into SQLite.
- [ ] `RecordProposalDetails` JSON can be validated before composition.
- [ ] `ProposalInput` JSON can be composed from records plus explicit details.
- [ ] `ProposalInput` JSON can be validated.
- [ ] `ProposalInput` JSON can be inspected in human-readable form.
- [ ] DOCX proposal can be generated from `ProposalInput` and template.
- [ ] Generated DOCX opens successfully.
- [ ] Operator verifies customer name, site address, scope, pricing, notes, company information, payment terms, and acceptance/signature area.
- [ ] Generated artifacts are kept under `output/` or another local non-committed location.
- [ ] Real private customer outputs are not committed.

## Test Coverage Summary

Current coverage includes:

- Abby Hill record-backed proposal workflow smoke coverage.
- Sample North Prairie record-backed proposal workflow smoke coverage.
- `RecordProposalDetails` validation and helper coverage.
- `ProposalInput` validation CLI coverage.
- `ProposalInput` inspect CLI coverage.
- Template and DOCX renderer fixture coverage.

## Known Boundaries

- This is a manual CLI workflow.
- No natural-language intake exists.
- No orchestrator exists.
- No worker execution exists.
- No plugin runtime execution exists.
- No one-command proposal workflow exists.
- Pricing is not inferred from records.
- Scope is not inferred from records.
- Notes are not inferred from records.
- Records are not edited or deleted by this workflow.
- Generated outputs are not automatically reviewed or sent.

## Ready / Not Ready

Ready for:

- internal manual proposal workflow trials using sanitized or real local-only data
- deterministic DOCX generation after human review

Not ready for:

- autonomous execution
- customer-facing unattended use
- natural-language proposal intake
- automatic pricing or scope decisions
- automatic sending or filing

## Links

- [Project state](project_state.md)
- [Orchestration plan model](orchestration_plan_model.md)
- [Orchestration approval boundary](orchestration_approval_boundary.md)
- [Proposal workflow operator checklist](proposal_workflow_operator_checklist.md)
- [Proposal workflow runbook](proposal_workflow_runbook.md)
- [Records CLI workflow](records_cli.md)
- [Output artifact conventions](output_artifact_conventions.md)
