# Docs-Only Autopilot Eligibility

## Purpose

The docs-only autopilot eligibility check is a read-only GitHub Actions workflow for future Phoenix Office autopilot experiments.

It answers one mechanical question: if a PR explicitly requests docs-only autopilot eligibility checking, does the PR stay inside the narrow docs-only file boundary currently proposed for future automation?

It does not auto-merge, approve, label, comment, trigger Codex, run agents, invoke background workers, or mutate repository state.

## Workflow

The workflow is:

```text
.github/workflows/docs_only_autopilot_eligibility.yml
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
contents: read
pull-requests: read
```

It uses GitHub-supported Actions tooling only.

## Label Semantics

The label `phoenix-automerge-docs` requests eligibility checking only.

If the label is absent, the workflow exits successfully with a skipped/not-requested message.

If the label is present, the workflow fails closed unless every eligibility check passes.

Passing this workflow is not merge approval. It does not replace CI, PR body guard, assistant review, or human authority.

## Allowed File Patterns

When `phoenix-automerge-docs` is present, changed files must be Markdown files under these paths only:

```text
docs/process/**/*.md
docs/development/**/*.md
```

This intentionally excludes runtime code, tests, fixtures, templates, examples, workflows other than this one, scripts, package files, lock files, DOCX files, JSON fixtures, source files, and generated outputs.

## Failure Cases

When `phoenix-automerge-docs` is present, the check fails if:

- the PR is draft
- any changed file is outside `docs/process/**/*.md` or `docs/development/**/*.md`
- any changed file is not Markdown
- the PR includes generated outputs
- the PR includes runtime code
- the PR includes tests
- the PR includes fixtures
- the PR includes templates or examples
- the PR includes GitHub workflows other than this eligibility workflow PR itself
- the PR includes scripts
- the PR includes package files or lock files
- the PR includes DOCX files
- the PR includes JSON fixtures
- the PR includes source files

The workflow enforces these cases mechanically through the narrow allowed path and extension check.

## Fail-Closed Rationale

The check fails closed because docs-only autopilot is a future automation boundary, not current merge authority.

If the risk class is uncertain, changed files are broader than expected, or the PR is still draft, the PR must remain manual-review and manual-merge only.

## Non-Goals

This check does not add or authorize:

- auto-merge behavior
- automatic PR approval
- issue-to-Codex trigger behavior
- Codex invocation
- background workers
- repository write behavior
- label creation, removal, or mutation
- PR comments from the workflow
- runtime code changes
- CLI behavior changes
- proposal generation changes
- DOCX rendering changes
- execution behavior
- orchestration `execute`, `run`, `apply`, `approve`, or `reject`
- plan or review mutation
- output artifacts
- audit persistence
- queueing, scheduling, retries, API behavior, MCP behavior, server behavior, worker behavior, or background behavior

## Future Auto-Merge Boundary

Future auto-merge must be implemented only in a separate reviewed PR.

That later PR would need its own policy, tests, permissions review, failure-mode review, and explicit human approval. This eligibility check only prepares a read-only mechanical signal for that possible future path.
