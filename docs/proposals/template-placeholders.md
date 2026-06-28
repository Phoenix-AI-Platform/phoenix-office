# A-1 Proposal Template Placeholders

## Purpose

This document describes the current A-1 proposal DOCX template placeholder contract.

It documents existing behavior only. It does not change product code, tests, CI, schemas, models, DOCX renderer behavior, generated output artifacts, or dependencies.

## Current Rendering Contract

The current DOCX renderer accepts a validated `ProposalInput` JSON file and a DOCX template. The template may contain placeholder tokens in the form `{{field_name}}`.

The CLI command loads `ProposalInput`, prepares rendered proposal text fields, replaces supported placeholders in the DOCX template, and writes the generated DOCX to the requested output path.

Supported placeholder replacement currently works in:

- normal document paragraphs
- table-cell paragraphs
- header paragraphs
- footer paragraphs
- placeholders split across Word runs inside the same paragraph

The renderer does not add new sections, tables, images, or business logic. It replaces supported text placeholders with rendered strings.

## Supported Placeholders

The currently supported proposal placeholders are:

| Placeholder | Source / rendering behavior |
| --- | --- |
| `{{customer_name}}` | `ProposalInput.customer_name` |
| `{{street_address}}` | `ProposalInput.street_address` |
| `{{city_state_zip}}` | `ProposalInput.city_state_zip` |
| `{{proposal_date}}` | `ProposalInput.proposal_date`, formatted as `Month D, YYYY` |
| `{{item_description}}` | `ProposalInput.item_description` |
| `{{scope_block}}` | `ProposalInput.scope_items`, rendered as numbered lines joined by newlines |
| `{{total_line}}` | `ProposalInput.pricing` plus `company_config`, rendered as a total line |
| `{{pricing_note}}` | `ProposalInput.pricing.pricing_note`, or an empty string when absent |
| `{{notes}}` | `ProposalInput.notes`, joined by newlines |

No other placeholders are part of the current supported contract.

## Proposal JSON To DOCX Mapping

The current record-backed workflow composes `ProposalInput` JSON before DOCX generation. The renderer consumes the composed `ProposalInput`; it does not read customer records, job records, or proposal details directly.

Current mapping:

- `customer_name` renders into `{{customer_name}}`.
- `street_address` renders into `{{street_address}}`.
- `city_state_zip` renders into `{{city_state_zip}}`.
- `proposal_date` renders into `{{proposal_date}}` as `June 25, 2026` style text.
- `item_description` renders into `{{item_description}}`.
- `scope_items` renders into `{{scope_block}}` as:

```text
1. First scope item
2. Second scope item
```

- `pricing.amount`, `pricing.is_starting_at`, `company_config.total_label`, and `company_config.starting_at_label` render into `{{total_line}}`.
- `pricing.pricing_note` renders into `{{pricing_note}}`.
- `notes` renders into `{{notes}}` as newline-joined note text.

Example total-line behavior:

```text
TOTAL: $1,500.00
TOTAL: Starting at $3,000.00
```

Pricing, scope, item description, and notes are not inferred by the DOCX renderer. They must already be present in validated `ProposalInput` JSON.

## Current CLI Generation Command

The current known DOCX generation command is:

```bash
python -m phoenix_office.cli proposal generate output/abby_hill_proposal_input.json output/abby_hill_proposal.docx --template tests/fixtures/templates/a1_proposal_template.docx
```

This command:

- reads `output/abby_hill_proposal_input.json`
- validates it as `ProposalInput`
- reads the DOCX template passed with `--template`
- writes the generated DOCX to `output/abby_hill_proposal.docx`

This command does not compose `ProposalInput`, import records, infer pricing or scope, send proposals, enqueue work, schedule work, or run orchestration.

## Safe Template Editing Guidance

When editing the A-1 DOCX template:

- Keep supported placeholders spelled exactly as listed above.
- Keep placeholders inside a single paragraph or table cell.
- Prefer plain text placeholders such as `{{customer_name}}` over visually edited fragments.
- Do not introduce new placeholders unless renderer support is explicitly scoped in a separate product-code PR.
- Do not rely on the renderer to infer missing pricing, scope, item descriptions, notes, or company terms.
- Keep generated proposal outputs under local `output/` paths and do not commit real customer output artifacts.
- Use sanitized data for committed examples and fixtures.
- Review the generated DOCX manually before sending it to a customer.

Changing template wording or layout can affect generated proposal appearance even when renderer behavior does not change. Treat template edits as reviewable proposal-content changes.

## Troubleshooting

### Placeholder remains visible in generated DOCX

Check that the placeholder name is supported and spelled exactly, including braces. For example, use `{{customer_name}}`, not `{customer_name}` or `{{ customer_name }}`.

If the placeholder is new, the current renderer will not replace it until product code is explicitly updated to support it.

### Expected text is missing

Validate the input JSON before generation:

```bash
python -m phoenix_office.cli proposal validate output/abby_hill_proposal_input.json
```

Then inspect the input summary:

```bash
python -m phoenix_office.cli proposal inspect output/abby_hill_proposal_input.json
```

If the value is absent from `ProposalInput`, the renderer cannot place it in the DOCX.

### Scope or notes formatting looks unexpected

`{{scope_block}}` and `{{notes}}` are newline-joined text blocks. Word template paragraph spacing and line-break handling may affect how the block appears visually.

Check the template paragraph containing the placeholder and review the generated DOCX manually.

### Total line looks unexpected

`{{total_line}}` is controlled by:

- `pricing.amount`
- `pricing.is_starting_at`
- `company_config.total_label`
- `company_config.starting_at_label`

Confirm those fields in the composed `ProposalInput` JSON.

### Template path fails

If the CLI reports that the DOCX template file does not exist, confirm the `--template` path is correct relative to the current working directory.

### Output path is missing parent folders

The current renderer creates output parent directories when writing the generated DOCX. If output is still not where expected, confirm the exact output path passed to `proposal generate`.

## Boundaries

This document does not add or approve:

- product-code changes
- test changes
- CI changes
- dependency changes
- schema or model changes
- DOCX renderer behavior changes
- generated output artifact changes
- workflow automation
- orchestration execution
- API or MCP behavior
