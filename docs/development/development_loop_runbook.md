# Phoenix Development Loop Runbook

## Purpose

This document describes the recommended development loop for Phoenix Office: read project state, create one narrow branch, open one PR, verify CI, review scope, merge only after approval, and update project state when needed.

The loop is human-controlled. It is meant to help future Codex tasks and human reviewers move safely without duplicating completed work or crossing architecture boundaries.

## Current Loop

```text
Read docs/development/project_state.md
  -> choose the next safe brick
  -> create one fresh branch
  -> make one narrow change
  -> open one PR
  -> inspect changed files and diff
  -> verify CI
  -> human merge/no-merge decision
  -> merge
  -> update project state when the verified spine changes
```

## One Branch / One PR Rule

- One branch.
- One PR.
- One narrow scope.
- No bundled unrelated work.

A PR should be easy to review from its changed files alone. If a task grows into multiple concerns, split it into separate future PRs.

## Project-State-Aware Prompt Pattern

Future Codex prompts should start by reading:

```text
docs/development/project_state.md
```

Then check whether the requested task is:

- already completed
- a follow-up fixture/docs/test layer
- a new safe brick
- a duplicate to avoid

Approval boundary contract and approval review JSON fixtures are different tasks. Compare requested filenames and acceptance criteria, not only topic names.

## PR Review Loop

For every PR, review should confirm:

- PR title, branch, and base branch
- changed files
- diff content
- CI status
- scope guardrails
- no generated outputs or private data
- merge/no-merge call

The reviewer should inspect whether the PR did exactly what the prompt asked and avoided adjacent runtime behavior.

## Failed CI Repair Loop

When CI fails:

1. Read the failing workflow/job output.
2. Identify the smallest likely cause.
3. Create a focused repair prompt.
4. Make only the repair.
5. Rerun CI.
6. Review again.

A CI repair should not expand scope. Do not bundle cleanup, refactors, new behavior, or extra features into the repair unless the failure requires it.

## Controlled Parallelism

Parallel PRs are usually safe when they are:

- independent
- small
- mostly additive
- not touching overlapping files
- not changing shared models
- not changing CLI or execution behavior

Parallel PRs are not safe when they involve:

- shared model changes
- CLI changes
- orchestration execution changes
- DOCX renderer/template changes
- proposal or record schema changes

Only one active PR at a time may touch core orchestration model files.

## Human Approval Gates

Codex may propose and implement narrow PRs.

ChatGPT and human review decide merge/no-merge.

Humans merge.

No auto-merge loop exists.

No autonomous development loop exists yet.

## Scope Guardrails

- No execution behavior unless explicitly scoped later.
- No CLI execution command.
- No natural-language intake.
- No customer data in repo.
- No generated output artifacts committed.
- No pricing, scope, or notes inference.
- No DOCX renderer/template changes without dedicated PR.
- No broad refactors mixed with feature work.

## Links

- [Project state](project_state.md)
- [Phoenix development workflow](workflow.md)
- [Orchestration plan model](orchestration_plan_model.md)
- [Orchestration approval boundary](orchestration_approval_boundary.md)
