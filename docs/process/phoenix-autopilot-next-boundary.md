# Phoenix Autopilot Next Boundary

## Purpose

This note defines the next safe Phoenix autopilot expansion boundary after the successful docs-only auto-merge pilot.

It is documentation only. It does not implement workflow behavior, CI behavior, issue-to-Codex automation, Codex invocation, comments, labels, approvals, branch updates, merge behavior, runtime behavior, persistence, or background work.

## Current Baseline

Phoenix Office has proven a narrow docs-only auto-merge path:

- PR #156 completed the first successful human-controlled docs-only auto-merge pilot.
- PR #158 hardened required-check detection with actual GitHub check-run/job-name aliases.
- PR #159 hardened mergeability handling by re-reading PR state.
- PR #161 documented the pilot result and lessons learned.

The proven boundary remains narrow: eligible Markdown files only, explicit `phoenix-automerge-docs` label, required checks, no requested-changes review, fresh mergeability, and no side effects beyond the eligible merge.

## Boundary Principles

Any next expansion must preserve:

- human-controlled trigger points
- deterministic, inspectable gates
- narrow file/path eligibility
- no private customer data
- no proposal generation side effects
- no approval or rejection mutation
- no automatic branch updates
- no hidden retries or background workers
- no API, MCP, server, worker, or background behavior unless explicitly approved in a future issue

## Options Compared

### Issue-To-Codex Preparation Handoff

This option would define a structured, human-readable handoff from a Phoenix task issue to a Codex-ready task prompt without automatically invoking Codex.

It could standardize what an operator copies from GitHub into Codex, including scope, changed-file boundaries, validation, out-of-scope constraints, and PR body expectations.

Safety properties:

- human still decides when to start Codex work
- no GitHub Action invokes Codex
- no issue body is executed as instructions by automation
- no labels, comments, approvals, branches, or merges are mutated
- no private customer data is required
- output is inspectable before a human uses it

Residual risk:

- poorly written issue content could still produce a weak manual prompt
- future implementation must avoid treating issue text as authority to mutate the repo

### PR Status Summarization

This option would summarize PR status for operators without approvals, comments, labels, or merge mutation.

It could help humans decide whether a PR is ready to review, label, or merge.

Safety properties:

- read-only if implemented locally or as an inspect-only command
- no merge or approval authority
- no eligible-path expansion

Residual risk:

- if implemented in GitHub Actions, it may create pressure to add PR comments or status comments later
- summaries can be mistaken for review approval if the boundary is not explicit

### Auto-Merge Audit Logging

This option would add documentation or a future read-only report around auto-merge decisions without changing merge eligibility or adding runtime persistence.

Safety properties:

- can improve traceability of already completed decisions
- does not need to widen merge eligibility
- can remain documentation-only or local-only at first

Residual risk:

- true audit logging usually implies persistence, artifacts, or workflow output retention policy
- persistence and artifacts require a separate reviewed boundary because they can create data-retention and privacy questions

### Additional Docs-Only Guardrails

This option would add more docs-only guardrails without widening eligible paths.

Safety properties:

- keeps the proven docs-only auto-merge surface intact
- can improve precision around documentation scope
- avoids runtime and proposal behavior

Residual risk:

- additional gates may make the existing pilot harder to operate without advancing the larger autopilot loop
- guardrail expansion can become workflow behavior if not kept documentation-only

## Recommended Next Boundary

The recommended next boundary is issue-to-Codex preparation handoff, without automatically invoking Codex.

This boundary is safer than the alternatives because it removes manual prompt assembly work while keeping every consequential trigger under human control. It does not require GitHub Actions write permissions, PR comments, label mutation, merge mutation, branch updates, runtime code, persistence, or background workers.

The next implementation, if separately approved, should produce or document a deterministic Codex-ready handoff shape from a Phoenix task issue. A human must still choose when to give that handoff to Codex.

## Non-Implementation Boundary

This note does not add:

- workflow behavior changes
- CI behavior changes
- issue-to-Codex automation
- Codex invocation from GitHub Actions
- auto-approval behavior
- new auto-merge eligibility paths
- label mutation behavior
- PR comments or status comments
- branch update behavior
- runtime code or CLI behavior
- proposal generation or DOCX rendering behavior
- tests or fixtures
- orchestration execution, approval, rejection, apply, run, queueing, scheduling, retries, persistence, API behavior, MCP behavior, server behavior, worker behavior, or background behavior

Future expansion beyond this recommendation requires a separate reviewed issue and PR.
