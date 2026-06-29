# Docs-Only Auto-Merge Pilot

## Purpose

The docs-only auto-merge pilot is a narrowly scoped GitHub Actions workflow that can remove the human merge click for the safest Phoenix Office documentation PR class.

It only considers PRs explicitly labeled `phoenix-automerge-docs` and only merges after every documented gate passes.

This pilot does not approve PRs, create or mutate labels, post comments, trigger Codex, update branches, upload artifacts, or start background work.

## Workflow

The workflow is:

```text
.github/workflows/docs_only_auto_merge.yml
```

It runs on pull request events including:

- opened
- synchronize
- reopened
- labeled
- unlabeled
- ready_for_review

If `phoenix-automerge-docs` is absent, the workflow exits successfully without action.

## Permission Model

The workflow uses the minimum permissions needed for reading PR state and performing the final merge mutation:

```yaml
checks: read
contents: write
pull-requests: write
statuses: read
```

The workflow uses the built-in GitHub token. It does not use custom secrets or a personal access token.

`contents: write` and `pull-requests: write` are required because the final eligible squash merge mutates repository state.

## Eligibility Class

The pilot only considers PRs that satisfy all of these conditions:

- PR has the `phoenix-automerge-docs` label
- PR is open
- PR targets `main`
- PR is not a draft
- PR head branch is not `main`
- changed files are Markdown files under `docs/process/` or `docs/development/`
- PR body contains the required headings
- PR body links to a Phoenix task issue
- no current latest review state is `CHANGES_REQUESTED`
- required checks are successful for the current head SHA
- GitHub reports the PR as mergeable
- the PR head SHA is unchanged after the workflow re-reads the PR immediately before merge

## Required Checks

The pilot requires these checks to pass before merging:

- `Tests`
- `Pull request body guard`
- `Docs-only autopilot eligibility`
- `Docs-only auto-merge dry-run`

Pending or missing checks defer the merge without failing the workflow.

Failed required checks fail closed and do not merge.

## Required PR Body Headings

The PR body must include these headings:

- `Summary`
- `Scope`
- `Changed files`
- `Out-of-scope confirmation`
- `Validation performed`
- `Risks`

The PR body must also link to a Phoenix task issue using a closing keyword, direct issue URL, or `Issue: #123` style reference.

## Allowed Files

The allowed changed-file patterns are:

```text
docs/process/**/*.md
docs/development/**/*.md
```

Any changed file outside those Markdown paths fails closed.

## Single Allowed Mutation

The only mutation this workflow may perform is the final squash merge of the eligible PR.

The workflow must not:

- approve PRs
- create, remove, or mutate labels
- post comments
- trigger Codex
- update branches
- create commits other than GitHub's squash merge commit for the eligible PR
- upload artifacts
- persist audit logs
- enqueue, schedule, retry, or run background work

## Deferred Behavior

The workflow defers without merging when:

- `phoenix-automerge-docs` is absent
- required checks are pending or missing
- GitHub mergeability is unknown
- the label is removed before merge
- GitHub no longer reports the PR as mergeable immediately before merge

Deferred outcomes are safe no-ops.

## Fail-Closed Behavior

The workflow fails closed when:

- the PR is not open
- the PR is draft
- the PR targets a branch other than `main`
- the head branch is `main`
- changed files leave the allowed docs-only boundary
- the PR body is missing required headings
- the PR body does not link to a Phoenix task issue
- a current latest review requests changes
- a required check fails
- GitHub reports the PR is not mergeable
- the head SHA changes between evaluation and merge
- branch conditions change before merge
- GitHub API reads or merge calls fail

Failing closed means no merge is performed.

## Logging

The workflow may log:

- PR number
- base branch
- evaluated head SHA
- required check names and read-only conclusions
- changed-file boundary failure summaries
- whether the decision was skipped, deferred, failed closed, or merged

The workflow must not log:

- secrets or tokens
- private customer data
- full issue bodies
- raw credentials
- generated business output
- DOCX/proposal content

## Difference From Dry-Run

The dry-run gate evaluates the future merge rules and never mutates repository state.

The pilot uses the same narrow gates but may perform one mutation: squash-merging an eligible docs-only PR after all required checks pass.

## Rollback And Revert

If a docs-only auto-merge is later found incorrect, the expected response is a normal human-reviewed revert PR or GitHub revert operation.

The pilot workflow does not attempt automatic rollback.

## Future Boundary

Future expansion requires a separate reviewed PR.

This pilot does not authorize auto-merge for runtime code, CLI behavior, tests, fixtures, examples, templates, generated outputs, DOCX files, proposal/business-output behavior, JSON fixtures, package files, lock files, scripts, API/MCP/server/worker/background behavior, execution behavior, or approval/rejection/plan/review mutation.
