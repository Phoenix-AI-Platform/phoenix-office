# Proposal Inspect JSON Contract

## Purpose

This document defines the machine-readable output contract for inspecting an explicit `ProposalInput` JSON file:

```bash
python -m phoenix_office.cli proposal inspect output/abby_hill_proposal_input.json --json
```

The command emits normalized `ProposalInput` JSON for deterministic reviewer tooling and regression tests. It is an inspection command only; it does not render a proposal or change any stored data.

## Inputs

The command accepts one explicit `ProposalInput` JSON file path.

It does not:

- look up customer records
- look up job records
- read SQLite databases
- read DOCX templates
- infer pricing, scope, notes, or item descriptions

## Output

When valid input is provided:

- the command exits `0`
- stdout is valid deterministic JSON
- stdout contains normalized `ProposalInput` JSON
- stderr is empty

The JSON output is suitable for reviewer tooling and regression tests that need to inspect exactly what would be passed to rendering later.

## Stable Fields For Consumers

Current fields useful to consumers include:

- `customer_name`
- `street_address`
- `city_state_zip`
- `proposal_date`
- `item_description`
- `scope_items`
- `pricing`
- `notes`
- `company`, if present in input

Consumers should read only the fields they need and tolerate additional fields when the underlying `ProposalInput` contract intentionally grows.

## Read-Only Behavior

The command validates and loads `ProposalInput` JSON, then prints normalized JSON.

It does not:

- render DOCX
- mutate records
- change proposal data
- call GitHub APIs
- trigger workflows
- execute workers
- start background behavior
- submit, email, approve, or file anything

## Failure Behavior

When the input file is invalid JSON or does not match the `ProposalInput` shape:

- the command exits nonzero
- errors are written to stderr
- no files are mutated
- no records are mutated
- no DOCX is rendered

## Consumer Guidance

Consumers may use this output to review exactly what would be rendered later by `proposal generate`.

Consumers must not treat this output as permission to render, mutate, submit, email, approve, or otherwise act on a proposal. Rendering still requires an explicit `proposal generate` command and any human review required by the workflow.

## Stability Note

Field additions or schema changes require focused tests and a dedicated reviewed PR. This document should be updated with any intentional contract changes.
