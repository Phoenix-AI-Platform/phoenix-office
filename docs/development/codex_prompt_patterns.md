# Codex Prompt Patterns

## Purpose

This document provides project-state-aware prompt patterns for Codex tasks. It helps future tasks avoid duplicate work, keep one branch and one PR per scope, and preserve Phoenix Office architecture boundaries.

## Required Preflight For Every Codex Task

Read first:

- `docs/development/project_state.md`
- `docs/development/development_loop_runbook.md`
- `docs/development/pr_review_guardrails.md`

Then confirm:

- current branch
- base branch
- requested task
- expected changed files
- whether the task is already completed
- whether the task is a follow-up layer
- whether the task is a duplicate to avoid

## Duplicate Vs Follow-Up Decision Pattern

Do not decide a task is duplicate based only on topic words.

Compare:

- requested filenames
- acceptance criteria
- intended layer

Example:

- PR #62 added the approval boundary contract.
- PR #63 added approval review JSON fixtures.
- Both mention approval, but they are different layers.

## New Feature Prompt Pattern

```text
Repo:
Base branch:
Fresh branch:
Open PR:

Context:
Current project state:
Task:
Files to inspect:
Files to add/update:
Test requirements:
Documentation requirements:
Scope guardrails:
Acceptance:
Review instructions:
```

Keep the task narrow. Name the expected files and the explicit non-goals.

## Docs-Only Prompt Pattern

```text
Repo:
Base branch:
Fresh branch:
Open PR:

Task:
Add/update documentation only.

Files to inspect:
Files to add/update:
Link updates:
Scope guardrails:
Acceptance:
Review instructions:
```

Docs-only PRs should state:

- no code files
- no tests unless explicitly requested
- no behavior changes
- no generated outputs

## Fixture/Test-Layer Prompt Pattern

```text
Repo:
Base branch:
Fresh branch:
Open PR:

Context:
Existing model or feature:
Task:
Fixture files to add:
Tests to add/update:
Scope guardrails:
Acceptance:
Review instructions:
```

A fixture/test-layer PR verifies or illustrates an existing model or feature. It should not recreate the model or feature it tests.

## Failed-CI Repair Prompt Pattern

```text
PR:
Failing check:
Relevant log excerpt:
Expected repair scope:
```

Repair loop:

1. Read failing workflow/job output.
2. Identify the smallest likely cause.
3. Make only the repair.
4. Do not expand scope.
5. Rerun CI.

## Parallel PR Prompt Pattern

Parallel tasks are safe only when they are:

- independent
- additive
- non-overlapping

Do not run parallel PRs when they involve:

- shared model changes
- CLI changes
- execution changes

Only one active PR may touch core orchestration models.

## Standard Guardrail Block

```text
Do not add workflow execution.
Do not add worker execution.
Do not add plugin runtime execution.
Do not add CLI shortcut commands.
Do not call subprocess.
Do not call CLI main.
Do not open SQLite from orchestration.
Do not read/write records from orchestration.
Do not compose ProposalInput from orchestration.
Do not generate DOCX from orchestration.
Do not infer pricing, scope, or notes.
Do not add private customer data.
Do not add generated output artifacts.
Do not make unrelated changes.
```

## Links

- [Project state](project_state.md)
- [Development loop runbook](development_loop_runbook.md)
- [PR review guardrails](pr_review_guardrails.md)
- [Phoenix development workflow](workflow.md)
