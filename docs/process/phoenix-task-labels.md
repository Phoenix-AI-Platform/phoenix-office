# Phoenix Task Labels

## Purpose

This document defines the first Phoenix task issue classification guidance for the issue-driven autopilot loop.

Phoenix task issues should make scope, risk, validation, and merge authority explicit before an agent opens a PR. The labels and risk classes are process guidance only. They do not add GitHub Actions workflows, auto-merge behavior, issue-to-Codex trigger behavior, execution behavior, or repository mutation behavior.

## Issue Template

Use the Phoenix Task issue form for scoped repo-native work:

```text
.github/ISSUE_TEMPLATE/phoenix_task.yml
```

The issue should include:

- task title or summary
- task type or risk class
- source or preceding PR/issue
- intended changed files or allowed paths
- explicit out-of-scope guardrails
- validation commands
- expected PR title
- required PR body headings
- Codex-ready implementation notes
- human-merge-only risk reminders

## Risk Classes

Phoenix task issues should use the same risk classes as the autopilot loop process:

- docs-only
- tests-only
- fixtures/examples
- CLI/read-only
- runtime/model/schema
- execution/API/MCP/server/background
- DOCX/proposal/business-output

If the correct risk class is uncertain, treat the task as manual-review and manual-merge only.

## Auto-Merge Boundary

Docs-only work is the first potential future auto-merge candidate, but no auto-merge behavior exists yet.

Any future auto-merge implementation must be a dedicated reviewed PR with its own policy, tests, and safeguards. A Phoenix task issue must not be treated as permission to auto-merge.

## Manual-Merge-Only Categories

The following categories remain manual-merge-only:

- uncertain risk classification
- execution behavior
- approval mutation
- API, MCP, server, worker, or background behavior
- DOCX rendering or generation behavior
- proposal pricing, scope, or notes inference
- persistence, audit, or write behavior
- schema or model changes unless explicitly approved
- DOCX/proposal/business-output behavior

Human merge authority remains required for risky changes and policy changes.

## Process Expectations

A Phoenix task issue should be specific enough that Codex can open one narrow PR without relying on an ad-hoc pasted prompt.

The resulting PR should link back to the issue, keep changed files inside the allowed paths, preserve the out-of-scope guardrails, run or explain validation, and use the required PR body headings.

The issue form supports the issue-driven loop. It does not create automation, trigger background work, run agents, schedule work, mutate records, generate business output, or bypass human authority.
