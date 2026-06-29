# Docs-Only Auto-Merge Implementation Plan

## Purpose

This document defines the implementation plan, permission model, and failure-mode checklist for a possible future docs-only auto-merge workflow.

It does not implement auto-merge. It is a planning document for a later dedicated PR.

The future workflow, if approved, should only consider the safest docs-only PR class that already passes the read-only `Docs-only autopilot eligibility` check.

## Eligible PR Class

The first possible auto-merge class should be limited to docs-only PRs that meet every condition below:

- the PR targets the repository default branch, currently `main`
- the PR source branch is not `main`
- the PR is not a draft
- the PR has the `phoenix-automerge-docs` label
- all changed files are Markdown files under `docs/process/` or `docs/development/`
- the PR links to a Phoenix task issue
- the PR body contains the required headings
- required status checks pass
- no review is in a requested-changes state
- GitHub reports the PR is mergeable and up to date enough to merge safely

Any uncertainty should make the workflow fail closed without merging.

## Required Label

The required label should be:

```text
phoenix-automerge-docs
```

The label should request consideration for docs-only auto-merge only. It must not be treated as approval by itself.

The future implementation must not create, remove, or mutate labels unless a later dedicated PR explicitly scopes that behavior.

## Branch And Base Conditions

The later implementation should require:

- base branch is `main`
- head branch is not `main`
- PR is open
- PR is not draft
- PR is not already merged
- PR is not from an unknown or unsupported source context

If branch protection requires the branch to be current with `main`, the workflow should require GitHub to report that state before merging. It should not update branches unless a later dedicated PR explicitly scopes that mutation.

## Changed-File Boundary

The changed-file boundary should match the existing eligibility check:

```text
docs/process/**/*.md
docs/development/**/*.md
```

The workflow should reject any changed file outside those Markdown paths.

This boundary intentionally excludes runtime code, CLI behavior, tests, fixtures, examples, templates, generated outputs, DOCX files, proposal/business-output behavior, JSON fixtures, package files, lock files, scripts, source files, and GitHub workflow changes.

## Required Status Checks

The future auto-merge workflow should require these checks to pass before merging:

- `Tests`
- `Pull request body guard`
- `Docs-only autopilot eligibility`

The workflow should also verify that the required checks correspond to the current head SHA. Stale checks should fail closed.

The auto-merge implementation should not replace those checks. It should consume their results.

## Required PR Body Headings

The PR body should contain these exact headings:

- `Summary`
- `Scope`
- `Changed files`
- `Out-of-scope confirmation`
- `Validation performed`
- `Risks`

The future workflow may rely on the existing PR body guard status instead of reparsing the body, but the implementation plan should still treat these headings as required.

## Phoenix Task Issue Link

The PR must link to a Phoenix task issue.

Acceptable future checks may include:

- a closing keyword such as `Closes #123`
- a direct issue URL
- an explicit `Issue: #123` style reference

The linked issue should be a Phoenix task issue containing the expected scope, guardrails, validation, and PR title. If no issue link is present, or the issue link is ambiguous, auto-merge must fail closed.

## Review State Requirement

The workflow must not merge if any current review requests changes.

The implementation should inspect current PR review state through GitHub-supported APIs and fail closed if:

- any latest review state is `CHANGES_REQUESTED`
- review state cannot be read
- reviewer state is ambiguous
- there is a pending unresolved policy concern

Passing auto-merge eligibility is not a substitute for human review policy. It is only a mechanical gate for a narrow docs-only class.

## Mergeability Requirement

Before merging, the workflow should confirm that GitHub reports the PR as mergeable.

The workflow should fail closed if:

- mergeability is `false`
- mergeability is unknown
- the branch is stale when branch protection requires freshness
- required checks are pending, skipped unexpectedly, failing, or tied to an older head SHA
- concurrent updates changed the head SHA during evaluation

The implementation should compare the evaluated head SHA with the head SHA at merge time.

## Merge Method

Recommended merge method:

```text
squash
```

Use squash merge if repository policy allows it. If repository settings disallow squash merge, the workflow must fail closed or use only a merge method explicitly approved in the later implementation PR.

## Permission Model

A later auto-merge workflow would require write permission because merging a PR mutates repository state.

The implementation should minimize permissions:

```yaml
permissions:
  contents: write
  pull-requests: write
```

Do not request broader permissions unless the implementation PR justifies them explicitly.

The workflow should not require issue write permission, actions write permission, checks write permission, packages write permission, deployments write permission, or repository administration permission.

## Secrets Policy

The workflow should not require custom secrets.

It should use the built-in GitHub token with the minimum required permissions. No personal access token should be used unless a later implementation PR proves the built-in token cannot satisfy branch protection and documents the additional risk.

Secrets must not appear in:

- issue bodies
- PR bodies
- workflow logs
- artifacts
- comments
- commit messages

## Logging

The workflow should log:

- PR number
- base branch
- evaluated head SHA
- whether the required label is present
- changed-file eligibility summary
- required status check names and conclusions
- whether a requested-changes review exists
- mergeability result
- final decision, such as skipped, failed closed, or merged

The workflow must never log:

- secrets or tokens
- private customer data
- full issue bodies containing sensitive content
- raw API credentials
- generated business output
- DOCX/proposal content

## Duplicate And Concurrent Attempts

Duplicate or concurrent auto-merge attempts should fail closed.

The implementation should:

- use a concurrency group scoped to the PR number
- cancel or block duplicate attempts
- re-read the PR head SHA immediately before merge
- fail if the head SHA changed after eligibility evaluation
- fail if required checks changed state after evaluation

The workflow should not retry merges blindly.

## Rollback And Revert Expectations

If a docs-only auto-merge is later found incorrect, the expected response is a normal revert PR or GitHub revert operation reviewed by a human.

The auto-merge workflow should not attempt automatic rollback.

The repo should preserve enough workflow log context to understand why the merge was allowed, without logging sensitive content.

## Hard Exclusions

The future auto-merge workflow must exclude:

- runtime code
- CLI behavior
- tests
- fixtures
- examples
- templates
- generated outputs
- DOCX files
- proposal/business-output behavior
- JSON fixtures
- package files
- lock files
- scripts
- any GitHub workflow changes except a dedicated reviewed implementation PR
- API, MCP, server, worker, or background behavior
- execution behavior
- approval, rejection, plan, or review mutation

If any excluded file or behavior appears in the PR, auto-merge must fail closed.

## Minimum Implementation Checklist

A later implementation PR must satisfy this checklist:

- separate dedicated PR
- explicit human approval before merge
- isolated workflow file
- least-privilege permissions
- no issue-to-Codex trigger in the same PR
- no expansion beyond docs-only
- fail-closed tests or clearly documented dry-run validation
- branch protection and required status-check compatibility reviewed
- no custom secrets unless separately justified
- no repository mutation except the final merge action
- clear logs without sensitive content
- documented rollback/revert process

## Non-Goals

This plan does not add or authorize:

- auto-merge behavior
- automatic PR approval
- issue-to-Codex trigger behavior
- Codex invocation
- background workers
- repository write behavior
- label creation, removal, or mutation
- PR comments from a workflow
- runtime code changes
- CLI behavior changes
- proposal generation changes
- DOCX rendering changes
- test changes
- fixture changes
- execution behavior
- orchestration `execute`, `run`, `apply`, `approve`, or `reject`
- plan or review mutation
- DOCX generation
- output artifacts
- audit persistence
- queueing, scheduling, retries, API behavior, MCP behavior, server behavior, worker behavior, or background behavior
