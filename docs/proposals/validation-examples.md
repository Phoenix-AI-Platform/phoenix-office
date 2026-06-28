# ProposalInput Validation Examples

## Purpose

This document shows the current `ProposalInput` validation commands for a valid proposal fixture and a sanitized invalid proposal fixture.

It documents existing behavior only. It does not change product code, tests, CI, dependencies, schemas, models, DOCX renderer behavior, generated output artifacts, or automation.

## Valid Fixture

Run validation against the current valid proposal example:

```bash
python -m phoenix_office.cli proposal validate examples/proposals/abby_hill.json
```

Expected result: the command exits successfully and prints that `ProposalInput` validation passed for the input path.

## Invalid Fixture

Run validation against the sanitized invalid proposal example:

```bash
python -m phoenix_office.cli proposal validate examples/proposals/invalid_proposal_input.json
```

This fixture is fake, sanitized test/support data. It intentionally fails `ProposalInput` validation for clear field-level reasons:

- empty `customer_name`
- empty `scope_items`
- `pricing.amount <= 0`

Expected result: the command exits nonzero and prints operator-facing field-level validation errors.

The error output should be readable without exposing Pydantic internals. The current style is:

```text
Error: invalid proposal input: examples/proposals/invalid_proposal_input.json
Validation errors:
- customer_name: ...
- scope_items: ...
- pricing.amount: ...
```

Exact validation wording may vary with the underlying validator, but the field paths should identify the failing `ProposalInput` fields.

## Related Docs

For how validated `ProposalInput` JSON maps into the A-1 DOCX template, see [A-1 Proposal Template Placeholders](template-placeholders.md).

## Boundaries

These examples do not generate DOCX files, infer pricing or scope, execute orchestration, enqueue work, schedule work, call APIs, or use private customer data.
