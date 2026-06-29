# Phoenix Autopilot Loop

## Purpose

This document defines the first repo-native Phoenix autopilot loop for Phoenix Office.

The goal is to reduce repeated human copy/paste between ChatGPT, Codex, GitHub issues, pull requests, and review while preserving human authority over execution-adjacent and business-impacting changes.

Phoenix automation may remove busywork. It must not remove human authority for risky changes, policy changes, generated business output, customer-impacting behavior, or execution capability.

## Current Manual Loop

The current Phoenix Office loop is human-driven and prompt-copying-heavy:

1. Assistant proposes the next task.
2. User copies the task to Codex.
3. Codex opens one narrow PR.
4. User asks the assistant to review the PR.
5. User manually merges after review.
6. Assistant verifies the merge and proposes the next task.

This loop preserves human control but creates repeated handoff work.

## Target Issue-Driven Loop

The target loop should make GitHub issues the task queue and source of truth:

1. A merged PR triggers or motivates the next GitHub issue.
2. The issue contains the Codex-ready task prompt and guardrails.
3. Codex or another agent works from the issue.
4. The resulting PR links back to the issue.
5. CI and the PR body guard run.
6. The assistant reviews the PR directly for scope and architecture.
7. Low-risk docs-only PRs may become eligible for auto-merge later.
8. Runtime, execution, and business-impacting PRs remain human-merge only.

This loop is a process target. It does not add automation, auto-merge, execution, scheduling, background work, or GitHub Actions behavior.

## Roles

- GitHub issue: task queue item and source of truth for the Codex-ready prompt, scope, guardrails, and acceptance criteria.
- Pull request: proposed change for one narrow issue or task.
- CI and PR body guard: mechanical validation that checks tests, lint, and required PR body structure.
- Assistant review: architectural and scope review that checks whether the PR followed the issue, preserved boundaries, and avoided hidden behavior.
- Human: authority for risky merges, policy changes, execution-adjacent changes, business-impacting changes, and any disputed judgment call.

## Risk Classes

Phoenix Office changes should be classified before merge policy is considered:

- docs-only
- tests-only
- fixtures/examples
- CLI/read-only
- runtime/model/schema
- execution/API/MCP/server/background
- DOCX/proposal/business-output

If the risk class is uncertain, treat the PR as manual-merge-only.

## Auto-Merge Eligibility Proposal

Auto-merge should not be implemented yet. If proposed later, the first eligible class should be docs-only PRs with strict gates:

- PR is non-draft.
- CI passes.
- PR body guard passes.
- Changed files are limited to docs/process/development Markdown only.
- Explicit assistant approval label or comment is present.
- No generated files are changed.
- No private customer data is present.

Any later auto-merge implementation must be a dedicated reviewed PR. This document does not add auto-merge behavior.

## Manual-Merge-Only Categories

The following categories must remain human-merge-only unless a later dedicated policy PR explicitly changes that boundary:

- execution behavior
- approval mutation
- API, MCP, server, worker, or background behavior
- DOCX rendering or generation behavior
- proposal pricing, scope, or notes inference
- persistence, audit, or write behavior
- schema or model changes unless explicitly approved

Manual-merge-only means automation may assist with review, but the human retains merge authority.

## Future Operator Phrases

Future operators should be able to use concise phrases that map to clear repo-native actions:

- `review latest Phoenix Office PR`
- `verify latest Phoenix Office merge`
- `create next Phoenix issue`
- `block autopilot`

These phrases are process language only. They do not create command surfaces or automation in this PR.

## Failure Behavior

The autopilot loop must fail closed:

- Duplicate issue detection should prevent creating repeated task issues for already-covered work.
- If there is no safe next task, no issue should be created.
- If risk classification is uncertain, the PR must be manual-review and manual-merge only.
- If CI, body guard, assistant review, or scope review fails, the PR must not auto-merge.
- If generated files or private customer data appear unexpectedly, the PR must be blocked for human review.

## Explicit Non-Goals

This document does not add or authorize:

- orchestration execution
- automatic business output generation
- hidden background work
- bypassing human authority
- auto-merge behavior
- GitHub Actions workflows
- API, MCP, server, worker, scheduling, retry, or queue behavior
- DOCX generation or rendering changes
- proposal generation changes
- pricing, scope, notes, item description, or customer data inference
- plan or review mutation
- audit persistence or write behavior

Phoenix Office remains deterministic-core-first. The autopilot loop is a review-gated process direction, not an execution system.
