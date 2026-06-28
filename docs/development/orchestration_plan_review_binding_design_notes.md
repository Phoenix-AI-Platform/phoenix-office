# Orchestration Plan/Review Binding Design Notes

## Purpose

These notes define future expectations for binding a human review decision to the exact `WorkflowPlan` it reviewed.

This document does not implement plan/review binding. This document does not modify models or schemas. This document does not approve execution. Phoenix Office still cannot execute orchestration plans.

## Current Boundary

Current orchestration behavior is inspection-only:

- `WorkflowPlan` JSON can be inspected.
- `WorkflowPlanReview` JSON can be inspected.
- Review fixtures can represent `approved`, `rejected`, and `needs_changes` decisions.
- Unsupported execution and mutation command shapes are tested and rejected.
- No execution, audit persistence, scheduling, retries, queueing, artifact generation, or binding enforcement exists.

## Binding Goal

A future execution design must be able to prove that the reviewed plan is the same plan being acted on.

Future design should avoid relying on filenames, user memory, timestamps alone, or approved-looking JSON.

## Candidate Binding Concepts

Possible future concepts include:

- deterministic plan fingerprint
- deterministic review fingerprint
- canonical plan serialization
- reviewed plan fingerprint copied into review data
- operator confirmation against the fingerprint
- audit record recording both plan and review identifiers
- validation/preflight that checks the review decision and plan binding before execution

These are design concepts only. They do not define a schema or runtime behavior.

## Non-Goals

This document does not:

- choose a hashing algorithm
- define canonical JSON rules
- change `WorkflowPlan` or `WorkflowPlanReview` models
- change JSON fixtures
- add CLI validation
- add execution
- add audit persistence
- add review mutation
- generate DOCX files

## Privacy And Determinism Expectations

Binding should avoid embedding unnecessary customer/private data in identifiers.

Fingerprints should be derived from deterministic plan content, not inferred state. Pricing, scope, and notes must not be inferred. Sanitized fixtures remain preferred for examples.

## Forbidden Shortcuts

Future work must not:

- execute from an approved-looking review JSON alone
- trust filenames as proof of binding
- rely on timestamps alone as proof of binding
- mutate review decisions from inspect commands
- add binding enforcement behind existing inspect commands
- silently generate DOCX files
- bypass human review

## Relationship To Readiness And Audit Notes

The [orchestration execution readiness checklist](orchestration_execution_readiness_checklist.md) identifies deterministic plan identity and clear binding between reviewed and executed plans as required gates before future execution can be proposed.

The [orchestration audit logging design notes](orchestration_audit_logging_design_notes.md) describe future audit expectations for recording plan and review identifiers.

Plan/review binding is a required gate before future execution can be proposed and should be reflected in any future audit strategy. These notes do not authorize execution, binding enforcement, audit persistence, mutation, scheduling, retries, queueing, or artifact generation.
