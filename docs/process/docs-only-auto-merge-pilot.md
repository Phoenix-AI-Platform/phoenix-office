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

It runs after the `Docs-only auto-merge dry-run` workflow completes.

The pilot proceeds only when the dry-run workflow completed and its eligibility confirmation job succeeded. It resolves the associated PR from the dry-run workflow event or, when GitHub omits that payload link, from the completed dry-run head SHA. It then re-reads current PR state and confirms the PR still has `phoenix-automerge-docs` before evaluating merge gates.

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
- GitHub reports the PR as mergeable after the workflow re-reads current PR state
- the PR head SHA is unchanged after the workflow re-reads the PR immediately before merge

## Required Checks

The pilot is triggered only by a successful `Docs-only auto-merge dry-run` workflow for the same PR head SHA.

It then requires these non-dry-run checks to pass before merging:

- `Tests`
- `Pull request body guard`
- `Docs-only autopilot eligibility`

Each required check may be satisfied by either the workflow display name or the current GitHub check-run/job name:

- `Tests` or `Test and lint`
- `Pull request body guard` or `Validate PR body sections`
- `Docs-only autopilot eligibility` or `Check docs-only autopilot eligibility`

If a required check group is missing, the workflow logs the discovered check-run names and status contexts for debugging.

This alias matching does not weaken the gate. The pilot still defers safely when required groups are missing or pending, and fails closed when a matched required check fails.

Pending or missing non-dry-run checks defer the merge without failing the workflow.

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

- the dry-run workflow did not conclude successfully
- `phoenix-automerge-docs` is absent
- required non-dry-run checks are pending or missing
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

The pilot no longer races the dry-run from the same pull request event. It runs only after a dry-run workflow completion with confirmed eligibility, resolves the PR from the workflow-run payload or dry-run head SHA, then re-reads current PR state and confirms the head SHA, label, mergeability, and non-dry-run checks before the final eligible squash merge.

The pilot uses the same narrow gates but may perform one mutation: squash-merging an eligible docs-only PR after all required checks pass.

## Rollback And Revert

If a docs-only auto-merge is later found incorrect, the expected response is a normal human-reviewed revert PR or GitHub revert operation.

The pilot workflow does not attempt automatic rollback.

## Pilot Validation Notes

The first validation PR for this pilot should be intentionally small, documentation-only, and initially unlabeled.

Reviewers should confirm the PR changes only eligible Markdown paths, verify all checks pass, and then decide manually whether to apply `phoenix-automerge-docs` as the pilot test switch.

Applying the label remains a human-controlled decision.

## Pilot Result

PR #156 completed the first successful human-controlled docs-only auto-merge pilot.

The PR remained gated by the `phoenix-automerge-docs` label. A human reviewed the docs-only PR, left the label off during normal validation, and then used the label as the explicit test switch for the pilot path.

The workflow performed only the eligible docs-only squash merge. It did not add approvals, comments, labels, branch updates, artifacts, runtime behavior, proposal generation, DOCX rendering, execution behavior, queueing, scheduling, retries, API/MCP/server/worker/background behavior, or other side effects.

Two hardening fixes were required before the pilot completed cleanly:

- PR #158 fixed required-check detection by accepting actual GitHub check-run/job-name aliases instead of matching only workflow display names.
- PR #159 fixed stale webhook mergeability by re-reading current PR state before evaluating mergeability.

## Sequencing Hardening

PR #164 changed the pilot sequence so the human-applied label remains the trigger switch, the dry-run can re-evaluate automatically after prerequisite checks complete, and the pilot only runs after a successful dry-run for the same PR head SHA.

PR #168 made the label-triggered path self-contained for already-green docs-only PRs by letting the pilot resolve the PR from the successful dry-run head SHA when the workflow-run payload does not include a PR link. The pilot still merges only after the successful dry-run, label, head SHA, mergeability, requested-review, required-check, and docs-only file gates pass.

PR #172 made pending required checks a dry-run defer state instead of a hard failure. Deferred dry-runs do not run the eligibility confirmation job, so the pilot can distinguish a safe wait from a true eligibility pass.

PR #173 was the workflow fix for pending-check defer and eligibility confirmation sequencing after PR #172.

PR #175 (Issue #174) is the live docs-only validation PR after PR #173, validating that the pilot correctly gates on the eligibility confirmation job from the dry-run.

## Future Boundary

Future expansion requires a separate reviewed PR.

This pilot does not authorize auto-merge for runtime code, CLI behavior, tests, fixtures, examples, templates, generated outputs, DOCX files, proposal/business-output behavior, JSON fixtures, package files, lock files, scripts, API/MCP/server/worker/background behavior, execution behavior, or approval/rejection/plan/review mutation.
