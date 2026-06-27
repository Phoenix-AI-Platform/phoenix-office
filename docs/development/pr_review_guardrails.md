# PR Review Guardrails

## Purpose

`pr_review_guardrails.json` is a machine-readable review checklist for Phoenix Office pull request scope.

It helps humans and future tools evaluate whether a PR stayed inside its requested boundaries.

## Advisory Only

The JSON file is not an enforcement system.

It does not:

- run CI
- inspect GitHub by itself
- block merges
- execute workflows
- call CLI commands
- modify repository files

Human review remains authoritative.

## How To Use It

Use the JSON checklist during PR review to confirm:

- title, branch, and base branch are correct
- changed files match the requested scope
- diff content is inspected
- CI has been verified when applicable
- generated outputs and private customer data are absent
- scope guardrails were respected
- the reviewer can give a merge/no-merge call

For docs-only PRs, confirm no code files, test files, or behavior changes were included.

For code PRs, confirm tests and docs were updated when behavior or operator workflows changed.

## Links

- [PR review guardrails JSON](pr_review_guardrails.json)
- [Development loop runbook](development_loop_runbook.md)
- [Project state](project_state.md)
- [Phoenix development workflow](workflow.md)
