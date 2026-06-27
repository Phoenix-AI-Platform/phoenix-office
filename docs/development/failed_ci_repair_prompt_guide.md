# Failed CI Repair Prompt Guide

## Purpose

This guide describes how to repair failed CI in Phoenix Office without expanding PR scope. It is a prompt guide for Codex and human reviewers, not an automated repair system.

Use it when a pull request has already been opened and a check fails. The goal is to create the smallest focused repair prompt that fixes the failure while preserving the original PR boundaries.

## Repair Loop

```text
read failing workflow/job output
  -> identify the smallest likely cause
  -> write a focused repair prompt
  -> change only what is needed
  -> rerun CI
  -> review the PR again
```

A repair should fix the failure. It should not turn into cleanup, refactoring, architecture changes, or new feature work.

## Required Repair Preflight

Before writing or acting on a repair prompt, Codex should confirm:

- PR number
- failing workflow/check name
- failing command
- relevant log excerpt
- files changed by the original PR
- whether the failure is caused by the PR or unrelated infrastructure
- smallest proposed fix
- files expected to change

If the available information does not identify a narrow fix, stop and ask for review.

## Repair Prompt Template

```text
Repo:
PR:
Branch:
Failing check:
Relevant log excerpt:
Likely cause:
Allowed files to change:
Repair task:
Scope guardrails:
Acceptance:
Review instructions:
```

The prompt should name the exact files that may change whenever possible. It should also say which adjacent changes are out of scope.

## What Repair PRs Must Not Do

- Do not add unrelated cleanup.
- Do not refactor adjacent code.
- Do not add new behavior unless required to fix the failure.
- Do not modify unrelated docs.
- Do not change architecture.
- Do not silence tests without explaining why.
- Do not delete tests to make CI pass.
- Do not loosen guardrails.

## Common Repair Types

Safe repair categories include:

- formatting/lint fix
- import/path fix
- fixture expectation fix
- documentation link fix
- test assertion correction
- small type/model validation correction

Each repair should be the smallest possible change that plausibly fixes the observed failure.

## When To Stop And Ask

Codex should stop and ask for review if:

- the fix requires architecture changes
- the fix touches orchestration execution
- the fix touches DOCX rendering/templates
- the fix changes proposal or record schemas
- the failure appears unrelated to the PR
- the repair would require broad refactoring

When in doubt, preserve scope and ask before changing files.

## Human Review Remains Required

This guide does not approve repairs automatically.

It does not run CI.

It does not inspect GitHub by itself.

It does not merge PRs.

Human review remains authoritative.

## Links

- [Project state](project_state.md)
- [Development loop runbook](development_loop_runbook.md)
- [Codex prompt patterns](codex_prompt_patterns.md)
- [PR review guardrails](pr_review_guardrails.md)
- [Phoenix development workflow](workflow.md)
