# Orchestration Inspection CLI (Read-Only)

## Purpose

This guide documents the current read-only orchestration inspection commands for Phoenix Office.

These commands are for human review of existing sanitized JSON fixtures and contract data.

Phoenix Office still cannot execute orchestration plans.

## WorkflowPlan inspection

```bash
python -m phoenix_office.cli orchestration plan inspect examples/orchestration/a1_proposal_dry_run_plan.json
```

The plan inspect command:

- parses an existing `WorkflowPlan` JSON file
- validates it using the existing model
- prints a human-readable summary

It does not execute, approve, reject, mutate, persist, enqueue, schedule, retry, or generate artifacts.

## WorkflowPlanReview inspection

```bash
python -m phoenix_office.cli orchestration review inspect examples/orchestration/a1_proposal_review_approved.json
```

The review inspect command:

- parses an existing `WorkflowPlanReview` JSON file
- validates it using the existing model
- prints a human-readable summary

It does not approve, reject, mutate reviews, execute, persist, enqueue, schedule, retry, or generate artifacts.

## Operator review sequence

1. Inspect the dry-run plan.
2. Inspect the human review JSON.
3. Confirm the plan/review are understandable.
4. Stop. No execution path exists.

## Non-execution and non-mutation boundaries

- Commands are inspection-only and read-only.
- No orchestration execution behavior exists.
- No review mutation behavior exists.
- No persistence, queueing, scheduling, retries, or artifact generation occurs.
