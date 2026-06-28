# Agent Operating Manual

## Purpose

This manual defines the default operating rules for Codex and other AI workers contributing to Phoenix Office.

Phoenix Office is deterministic-core-first. Agents should preserve that boundary unless a task explicitly scopes a change beyond documentation, tests, or existing deterministic behavior.

## Required Operating Rules

- One branch, one PR, one narrow scope.
- Do not broaden scope beyond the prompt.
- Do not change generated output artifacts unless explicitly scoped.
- Do not change DOCX renderer behavior unless explicitly scoped.
- Do not add workflow automation, API, MCP, or execution behavior unless explicitly scoped.
- Do not modify schemas or models unless explicitly scoped.
- Do not use private customer data.
- Keep deterministic core first.
- Run existing validation if practical.
- Clearly report any validation not run.

## Scope Discipline

Before editing, identify whether the task is docs-only, tests-only, fixture-only, or runtime behavior. Keep the PR inside that category.

If a task would require execution behavior, automation, persistence, scheduling, retries, queueing, API/MCP behavior, model/schema changes, generated artifacts, DOCX renderer behavior, or private customer data, stop unless those changes are explicitly requested.

## Safe Current Agent Work

Safe agent tasks include:

- docs/process updates
- documentation navigation updates
- narrow tests for existing behavior
- fixture coverage for sanitized examples when explicitly scoped
- small maintenance changes that do not alter runtime behavior
- project-state updates after merged PRs when explicitly scoped

## Not Allowed Without Explicit Scope

Agents must not add or modify:

- orchestration execution
- approval or review mutation behavior
- workflow automation
- API or MCP behavior
- worker execution
- scheduling, retries, queues, or persistence
- DOCX renderer behavior
- proposal, record, or orchestration models/schemas
- generated output artifacts
- private customer data
- dependencies or CI behavior

## Validation Reporting

Every PR should state what validation was run. If validation was not practical, state why.

Preferred existing checks are:

```bash
python -m pytest
ruff check .
```

Do not invent new validation commands for a narrow docs/process task unless the prompt requests them.
