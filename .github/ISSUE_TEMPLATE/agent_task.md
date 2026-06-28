---
name: Agent task
description: Define a narrow, safe task for Codex or another AI worker.
title: "[Agent task]: "
labels: []
assignees: []
---

## Goal

Describe the single outcome the agent should produce.

## In scope

- 

## Out of scope

- 

## Acceptance criteria

- 

## Validation

List expected validation, or explain why validation is not practical for this task.

- [ ] `python -m pytest`
- [ ] `ruff check .`
- [ ] Other:

## Risk level

Choose one and explain briefly.

- [ ] Low: docs/process, navigation, or tests for existing behavior only
- [ ] Medium: narrow runtime behavior within existing contracts
- [ ] High: requires explicit human approval before assignment

Risk notes:

## Agent guardrails

- One branch, one PR, one narrow scope.
- Do not broaden scope beyond this issue.
- Do not use private customer data.
- Do not change generated artifacts, DOCX renderer behavior, models, schemas, dependencies, CI, automation, API, MCP, or execution behavior unless listed in scope above.
