# Orchestration Audit Logging Design Notes

## Purpose

These notes define audit/logging expectations for any future orchestration execution design.

This document does not implement audit logging. This document does not approve execution. Phoenix Office still cannot execute orchestration plans.

## Current Boundary

Current orchestration behavior is inspection-only:

- `WorkflowPlan` JSON can be inspected.
- `WorkflowPlanReview` JSON can be inspected.
- Review fixtures can represent `approved`, `rejected`, and `needs_changes` decisions.
- Unsupported execution and mutation command shapes are tested and rejected.
- No execution, audit persistence, scheduling, retries, queueing, or artifact generation exists.

## Audit Trail Goals

Future audit/logging design should aim to:

- make operator decisions traceable
- bind review decisions to exact plan content
- preserve deterministic inputs and outputs
- support failure review
- avoid relying on mutable or inferred state
- protect private/customer data

## Minimum Audit Fields For Future Design

Candidate fields for any future audit model or log record include:

- audit record id
- timestamp
- actor/operator identity
- command or workflow name
- plan id or plan fingerprint
- review id or review fingerprint
- review decision
- approved-for-execution value
- explicit operator confirmation indicator
- input file references or safe identifiers
- output/artifact policy
- result status
- failure reason, if any
- non-sensitive summary
- Phoenix Office version or relevant capability metadata version, if available

These are design notes only. They do not define a runtime schema.

## Plan/Review Binding Expectations

Future execution must not rely only on an approved-looking review JSON file.

Any future execution design must include a deterministic strategy for proving that the reviewed plan is the same plan being acted on.

## Privacy And Customer-Data Expectations

Future audit logs should avoid storing unnecessary private/customer data.

Proposal pricing, scope, and notes must not be inferred. Sensitive input paths or contents should be handled deliberately. Sanitized fixtures remain preferred for examples.

## Failure/Result Expectations

Any future audit strategy should distinguish outcomes such as:

- not attempted
- rejected before execution
- blocked by validation
- operator cancelled
- execution succeeded
- execution failed
- partial/compensated outcome, if applicable

These statuses are not implemented here.

## Forbidden Shortcuts

Future work must not:

- execute without an audit strategy
- mutate review decisions from an inspect command
- execute from an approved-looking JSON alone
- silently generate DOCX files
- store unnecessary customer/private data in logs
- add audit persistence, queues, scheduling, retries, or background jobs as a side effect
- bypass human review

## Relationship To Readiness Checklist

The [orchestration execution readiness checklist](orchestration_execution_readiness_checklist.md) identifies audit/logging as a required gate before future execution can be proposed.

These notes expand that gate at a design level only. They do not authorize execution, audit persistence, mutation, scheduling, retries, queueing, or artifact generation.
