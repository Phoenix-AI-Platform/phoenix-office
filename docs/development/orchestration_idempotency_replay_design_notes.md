# Orchestration Idempotency/Replay Design Notes

## Purpose

These notes define future expectations for orchestration idempotency and replay concepts before any orchestration execution could ever be considered.

This document does not implement idempotency or replay behavior. This document does not add CLI commands. This document does not modify models or schemas. This document does not approve execution. Phoenix Office still cannot execute orchestration plans.

## Current Boundary

Current orchestration behavior is inspection-only:

- `WorkflowPlan` JSON can be inspected.
- `WorkflowPlanReview` JSON can be inspected.
- Review fixtures can represent `approved`, `rejected`, and `needs_changes` decisions.
- Unsupported execution and mutation command shapes are tested and rejected.
- No execution, idempotency behavior, replay behavior, locks, hashes, fingerprints, audit persistence, scheduling, retries, queueing, artifact generation, or binding enforcement exists.

## Future Idempotency/Replay Goal

Future execution must avoid accidental duplicate artifacts, duplicate record mutations, duplicate approvals, or duplicate external side effects.

Future replay must not be assumed safe unless designed and approved. Future idempotency should consider explicit inputs, plan/review binding, output policy, operator confirmation, and result state if those concepts are separately approved.

## Candidate Future Concepts

Possible future concepts include:

- explicit idempotency keys if separately approved
- deterministic plan or input identity if separately approved
- output path and overwrite policy checks
- result-state checks before repeat attempts if result reporting is separately approved
- audit references if audit persistence is later approved
- explicit replay eligibility rules
- explicit duplicate-artifact prevention expectations
- explicit operator confirmation before any retry or replay if separately approved

These are design concepts only. They do not define a schema, API, CLI command, or runtime behavior.

## Non-Goals

This document does not:

- define a CLI command
- define replay commands
- define schemas
- choose hashing or fingerprinting rules
- change `WorkflowPlan` or `WorkflowPlanReview` models
- change JSON fixtures
- add execution
- add idempotency behavior
- add replay behavior
- add hashes, fingerprints, locks, or persistence
- add audit persistence
- add validation/preflight enforcement
- add output/artifact policy enforcement
- add operator confirmation enforcement
- add review mutation
- generate DOCX files

## Safety Expectations

- Future execution must avoid accidental duplicate artifacts, duplicate record mutations, duplicate approvals, or duplicate external side effects.
- Future replay must not be assumed safe unless designed and approved.
- Future idempotency must not infer approval, output policy, pricing, scope, notes, or retry intent.
- Repeated inspection must remain read-only.
- Generated artifacts must not be overwritten without explicit policy.
- Sanitized fixtures remain preferred for examples.

## Forbidden Shortcuts

Future work must not:

- assume replay is safe because inputs look similar
- infer idempotency from filenames alone
- overwrite artifacts during replay without explicit policy
- duplicate approvals or mutate review decisions during replay
- duplicate record mutations or external side effects
- hide execution behind replay or result-reporting commands
- add hashes, fingerprints, persistence, locks, or replay commands as a side effect
- bypass human review

## Relationship To Dry-Run/No-Write, Output Policy, Result Reporting, Cancellation/Rollback, And Audit Notes

The [orchestration dry-run/no-write design notes](orchestration_dry_run_no_write_design_notes.md) describe future no-write expectations that can help preview duplicate-risk conditions without acting.

The [orchestration output artifact policy design notes](orchestration_output_artifact_policy_design_notes.md) describe future output and overwrite expectations that idempotency must respect.

The [orchestration execution result design notes](orchestration_execution_result_design_notes.md) describe future result-state concepts that could inform repeat attempts if separately approved.

The [orchestration cancellation/rollback design notes](orchestration_cancellation_rollback_design_notes.md) describe future recovery expectations that must not promise replay safety without design.

The [orchestration audit logging design notes](orchestration_audit_logging_design_notes.md) describe future audit expectations if audit persistence is later approved.

Idempotency/replay design is a required future governance gate and must remain separate from execution, retry behavior, audit persistence, mutation, and artifact generation unless separately approved. These notes do not authorize execution, idempotency behavior, replay behavior, hashes, fingerprints, locks, persistence, validation/preflight enforcement, output/artifact policy enforcement, audit persistence, mutation, scheduling, retries, queueing, or artifact generation.
