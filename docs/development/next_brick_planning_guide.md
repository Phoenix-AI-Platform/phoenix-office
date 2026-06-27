# Next-Brick Planning Guide

## Purpose

This guide helps Phoenix Office contributors choose the next narrow PR while preserving architecture discipline.

Use it after reading [project state](project_state.md) and before creating a branch. The goal is to keep each change reviewable, deterministic, and inside the current non-execution boundaries.

## What Makes A Safe Next Brick

A safe next brick is small, isolated, and easy to verify. Good examples include:

- docs-only clarification
- tests-only guardrail
- fixture coverage for existing behavior
- read-only inspection helper
- validation or preflight around existing deterministic inputs
- project state update after several merged PRs

Prefer work that strengthens an existing boundary before adding new surface area.

## What Is Not Safe Without Explicit Approval

These are not safe next bricks unless the prompt explicitly asks for them:

- orchestration execution
- worker execution
- scheduling
- retries
- persistence or queues
- approval or rejection mutation behavior
- automatic DOCX generation from plans
- inferred pricing, scope, or notes
- new integrations
- broad refactors
- schema or model changes bundled with unrelated work

Inspection, validation, and documentation must not quietly become execution or mutation.

## Decision Checklist

Before starting a PR, ask:

- Does this change runtime behavior?
- Does it change contracts, models, or schemas?
- Does it add execution, mutation, persistence, scheduling, retries, queueing, or artifact generation?
- Can it be tested in isolation?
- Is it one branch, one PR, one narrow scope?
- Does `docs/development/project_state.md` need updating now, or only after a small cluster of PRs?

If the answer suggests a larger boundary change, stop and get explicit approval.

## Worker Routing

Current preferred routing:

- Codex: narrow repo code/test changes with CI.
- Copilot: docs-only updates, navigation, mechanical test additions, and low-risk cleanup.
- Gemini: second-opinion review, research, and architecture critique. Do not use it as the primary repo implementer unless explicitly approved.

Human and ChatGPT review still decide whether a PR is ready to merge.

## Example Next-Brick Categories

Examples of safe categories:

- Add tests for existing validation behavior.
- Add docs for an existing command.
- Update project state after several merged PRs.
- Add a read-only inspection command.

Examples of unsafe category drift:

- Do not add execution behind an inspection command.
- Do not infer pricing or scope while adding validation.
- Do not bundle schema changes with unrelated docs or tests.

## Stop Conditions

Codex or Copilot should stop and ask if the task requires:

- runtime behavior beyond the prompt
- changing models or schemas
- changing fixtures
- adding automation
- interpreting private or customer data
- inferring proposal pricing or scope
- generating outputs
- changing GitHub Actions

Stopping early is better than crossing an architecture boundary by accident.

## Human Review Remains Required

Every PR still requires human or ChatGPT review before merge.

The current Phoenix Office loop remains:

```text
one branch
  -> one PR
  -> one narrow scope
  -> CI must pass
  -> human review before merge
  -> human merges
```

This guide does not add automation, execution behavior, approval mutation, scheduling, retries, persistence, queueing, or artifact generation.
