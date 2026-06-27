# Output Artifact Conventions

## Purpose

This document describes recommended locations and handling for generated local artifacts from the current manual A-1 proposal workflow.

These conventions are for operator and developer hygiene only. They do not change CLI behavior or add automation.

## Recommended Local Output Layout

Use `output/` for local generated files. A simple layout is:

```text
output/
  records.sqlite
  proposals/
    <job-or-customer-slug>/
      proposal_input.json
      proposal.docx
```

Current examples in docs and tests also use these flat paths:

```text
output/records.sqlite
output/abby_hill_proposal_input.json
output/abby_hill_proposal.docx
```

## Artifact Types

- `records.sqlite`: local SQLite working database for imported customer/job records.
- `proposal_input.json`: composed deterministic renderer input created by `records proposal-input`.
- `proposal.docx`: generated customer-facing proposal document created by `proposal generate`.
- Temporary operator output folders: local workspace folders used while preparing or reviewing proposal output.

## Commit Policy

- `examples/records/*.json` fixtures may be committed when they are sanitized or intentionally public.
- `tests/fixtures/templates/*.docx` may be committed when intentionally used as test/template fixtures.
- Generated `output/` files should normally stay local and should not be committed.
- Real customer/private proposal outputs should not be committed.

## Privacy Warning

Generated proposal files may contain customer names, addresses, pricing, and job notes.

Do not commit real private customer output files. Use sanitized fixtures for repository examples and tests.

## Current Workflow Relationship

These conventions do not change the current workflow:

```text
records import
records proposal-details validate
records proposal-input
proposal validate
proposal inspect
proposal generate
```

They only describe where to place generated local files and how to handle them in version control.

## Boundaries

- No automation or orchestration is added.
- No shortcut workflow command is added.
- No CLI behavior is changed.
- No output cleanup behavior is added.
- No generated files are committed by this convention.
