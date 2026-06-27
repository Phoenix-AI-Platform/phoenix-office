# Proposal Workflow Operator Checklist

## Purpose

This is the current manual operator checklist for generating an A-1 proposal from stored customer/job records and explicit proposal details.

Use it before generating a DOCX proposal to confirm the record data, proposal business details, command inputs, and final proposal review steps are intentional.

## Required Files

Prepare or choose these files and paths before running the workflow:

- `CustomerRecord` JSON
- `JobRecord` JSON
- `RecordProposalDetails` JSON
- DOCX template
- SQLite database path
- output `ProposalInput` JSON path
- output DOCX path

Operators may copy `examples/records/proposal_details_template.json` as a starter `RecordProposalDetails` file for a new job. Replace all placeholder values before sending a proposal.

Example paths used by the current Abby Hill workflow:

- `examples/records/customer_abby_hill.json`
- `examples/records/job_abby_hill.json`
- `examples/records/proposal_details_abby_hill.json`
- `tests/fixtures/templates/a1_proposal_template.docx`
- `output/records.sqlite`
- `output/abby_hill_proposal_input.json`
- `output/abby_hill_proposal.docx`

Additional sanitized sample proposal details are available at `examples/records/proposal_details_sample_north_prairie.json`.

## Preflight Checklist

- [ ] Customer information reviewed
- [ ] Job/site address reviewed
- [ ] Proposal details reviewed
- [ ] Scope items intentionally authored
- [ ] Pricing lines intentionally authored
- [ ] Notes intentionally authored
- [ ] Template path selected
- [ ] Output paths selected

## Command Checklist

Run the current manual command chain in order:

```bash
python -m phoenix_office.cli records import customer examples/records/customer_abby_hill.json --db output/records.sqlite

python -m phoenix_office.cli records import job examples/records/job_abby_hill.json --db output/records.sqlite

python -m phoenix_office.cli records proposal-details validate examples/records/proposal_details_abby_hill.json

python -m phoenix_office.cli records proposal-input customer-abby-hill job-abby-hill examples/records/proposal_details_abby_hill.json output/abby_hill_proposal_input.json --db output/records.sqlite

python -m phoenix_office.cli proposal validate output/abby_hill_proposal_input.json

python -m phoenix_office.cli proposal inspect output/abby_hill_proposal_input.json

python -m phoenix_office.cli proposal generate output/abby_hill_proposal_input.json output/abby_hill_proposal.docx --template tests/fixtures/templates/a1_proposal_template.docx
```

## Review Checklist Before Sending Proposal

- [ ] Generated DOCX opens successfully
- [ ] Customer name is correct
- [ ] Site address is correct
- [ ] Scope item wording is correct
- [ ] Pricing is correct
- [ ] Notes are correct
- [ ] Company information is correct
- [ ] Payment terms are correct
- [ ] Acceptance/signature area is present

## Explicit Boundaries

- This checklist does not describe automation or orchestration.
- The workflow is manual CLI operation only.
- `proposal inspect` validates and summarizes `ProposalInput` JSON only.
- Pricing is not inferred from records.
- Scope is not inferred from records.
- Proposal notes are not inferred from records.
- DOCX rendering remains the existing `proposal generate` command.
- `RecordProposalDetails` is the operator-authored business detail source.
- `ProposalInput` is the deterministic renderer input.

## Links

- [Proposal workflow runbook](proposal_workflow_runbook.md)
- [Records CLI workflow](records_cli.md)
