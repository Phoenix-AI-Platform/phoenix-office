# Docs-Only Auto-Merge Dry-Run Gate

## Purpose

The docs-only auto-merge dry-run gate is a read-only GitHub Actions workflow that evaluates whether a PR appears to satisfy the future docs-only auto-merge plan.

It does not merge, approve, label, comment, trigger Codex, write repository state, or start background work.

The workflow provides a mechanical preview of the future auto-merge decision without performing the mutation.

## Workflow

The workflow is:

```text
.github/workflows/docs_only_auto_merge_dry_run.yml
```

It runs on pull request events including:

- opened
- synchronize
- reopened
- labeled
- unlabeled
- ready_for_review

The workflow uses read-only permissions:

```yaml
checks: read
contents: read
pull-requests: read
statuses: read
```

It uses GitHub-supported Actions tooling only.

## Label Semantics

The label `phoenix-automerge-docs` requests the dry-run evaluation.

If the label is absent, the workflow exits successfully with a not-requested message.

If the label is present, the workflow fails closed unless every dry-run gate passes.

The label is not merge approval. Passing the dry-run gate is not merge approval.

## Dry-Run Gates

When `phoenix-automerge-docs` is present, the workflow checks:

- base branch is `main`
- head branch is not the same as the base branch
- PR is not draft
- PR body exists
- PR body includes the required headings
- PR body links to a Phoenix task issue
- changed files are Markdown files under `docs/process/` or `docs/development/`
- no current review requests changes
- required status checks are successful for the current head SHA
- GitHub reports the PR as mergeable after the workflow re-reads current PR state

Required status checks are:

- `Tests`
- `Pull request body guard`
- `Docs-only autopilot eligibility`

Each required check may be satisfied by either the workflow display name or the current GitHub check-run/job name:

- `Tests` or `Test and lint`
- `Pull request body guard` or `Validate PR body sections`
- `Docs-only autopilot eligibility` or `Check docs-only autopilot eligibility`

If a required check group is missing, the workflow logs the discovered check-run names and status contexts for debugging.

This alias matching does not weaken the gate. The dry-run workflow still fails closed when labeled and a required check group is missing, pending, stale, or failing.

## Required PR Body Headings

The workflow checks for these headings:

- `Summary`
- `Scope`
- `Changed files`
- `Out-of-scope confirmation`
- `Validation performed`
- `Risks`

## Allowed File Patterns

The allowed changed-file patterns are:

```text
docs/process/**/*.md
docs/development/**/*.md
```

All other files fail the dry-run gate.

## Failure Cases

The workflow fails closed if:

- the label is present and any dry-run gate fails
- the PR is draft
- the PR targets a branch other than `main`
- the PR body is missing a required heading
- the PR body does not link to a Phoenix task issue
- changed files leave the docs-only Markdown boundary
- a current review requests changes
- required checks are missing, pending, stale, or failing
- mergeability is false or unknown
- GitHub API reads fail

## Logging

The workflow may log:

- PR number
- base branch
- evaluated head SHA
- whether the label is present
- required check names and their read-only conclusions
- changed-file boundary failure summaries
- final dry-run decision

The workflow must not log:

- secrets or tokens
- private customer data
- full issue bodies
- raw credentials
- generated business output
- DOCX/proposal content

## Non-Goals

This dry-run gate does not add or authorize:

- auto-merge behavior
- automatic PR approval
- label creation, removal, or mutation
- PR comments from the workflow
- issue-to-Codex trigger behavior
- Codex invocation
- background workers
- repository write behavior
- runtime code changes
- CLI behavior changes
- proposal generation changes
- DOCX rendering changes
- test changes
- fixture changes
- execution behavior
- orchestration `execute`, `run`, `apply`, `approve`, or `reject`
- plan or review mutation
- output artifacts
- audit persistence
- queueing, scheduling, retries, API behavior, MCP behavior, server behavior, worker behavior, or background behavior

## Pilot Hardening Notes

The first docs-only auto-merge pilot validation surfaced two dry-run gate hardening needs:

- PR #158 taught the dry-run gate to accept actual GitHub check-run/job-name aliases when resolving required checks.
- PR #159 taught the dry-run gate to re-read current PR state before evaluating mergeability, avoiding stale webhook payload values.

Both fixes preserved the existing label gate and fail-closed behavior.

## Future Boundary

Future auto-merge behavior must still be implemented in a separate reviewed PR.

This dry-run gate is only a read-only signal. It prepares the repo to observe how often candidate docs-only PRs would pass the planned auto-merge rules before any merge mutation is introduced.
