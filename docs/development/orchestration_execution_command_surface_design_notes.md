# Orchestration Execution Command Surface Design Notes

## Purpose

These notes define future expectations for any orchestration execution command surface before execution could ever be considered.

This document does not add CLI commands. This document does not implement execution. This document does not modify models or schemas. This document does not approve execution. Phoenix Office still cannot execute orchestration plans.

## Current Boundary

Current orchestration CLI behavior is inspection-only:

- `WorkflowPlan` JSON can be inspected.
- `WorkflowPlanReview` JSON can be inspected.
- Existing unsupported execution and mutation command shapes are tested and rejected.
- Inspect commands are read-only and non-executing.
- No execution command surface, validation/preflight enforcement, review mutation, audit persistence, scheduling, retries, queueing, artifact generation, or binding enforcement exists.

## Future Command-Surface Goal

If execution is ever explicitly approved, the execution command surface must be explicit and separate from inspect, validation, review mutation, and proposal generation commands.

Inspect commands must remain read-only. Validation/preflight commands must remain read-only unless separately approved.

Future command names are not defined here. This document does not prescribe exact CLI syntax.

## Candidate Future Command Design Constraints

Possible future constraints include:

- require a clearly named execution-specific command only after execution is separately approved
- keep plan inspection separate from execution
- keep review inspection separate from review mutation and execution
- keep validation/preflight read-only unless separately approved
- keep proposal generation commands separate from orchestration execution commands
- require explicit plan/review binding validation if such a future concept is approved
- require explicit operator confirmation if such a future concept is approved
- require explicit output/artifact policy if such a future concept is approved
- preserve unsupported command-shape tests until a replacement command surface is explicitly approved

These are design concepts only. They do not define a schema, API, CLI command, or runtime behavior.

## Non-Goals

This document does not:

- define future command names
- prescribe exact CLI syntax
- add CLI commands
- add execution
- define schemas
- change `WorkflowPlan` or `WorkflowPlanReview` models
- change JSON fixtures
- add validation/preflight enforcement
- add operator confirmation enforcement
- add output/artifact policy enforcement
- add plan/review binding enforcement
- add audit persistence
- add review mutation
- generate DOCX files

## Safety Expectations

- Inspect commands must remain read-only.
- Future validation/preflight commands must remain read-only unless separately approved.
- Future execution commands must not be hidden behind inspection, validation, review, or proposal generation commands.
- Any future command surface must make execution intent explicit.
- Any future command surface must not infer pricing, scope, notes, approval, output paths, or artifact policy.

## Forbidden Shortcuts

Future work must not:

- add execution behind existing inspect commands
- add execution behind validation/preflight commands
- add execution behind proposal generation commands
- mutate reviews from inspect commands
- treat approved-looking review JSON as an execution command
- define command names casually in docs and treat them as approved
- add queues, scheduling, retries, persistence, or background jobs as a side effect
- bypass human review

## Relationship To Non-Execution CLI Tests And Execution Readiness Checklist

Existing tests reject unsupported orchestration execution and mutation command shapes, including `orchestration execute/run/apply`, `orchestration plan execute/run`, and `orchestration review approve/reject/apply`.

The [orchestration execution readiness checklist](orchestration_execution_readiness_checklist.md) defines documentation-only gates that must be addressed before future execution work may be considered.

Execution command-surface design is a required future gate and must remain separate from inspection, validation, review mutation, proposal generation, and execution unless separately approved. These notes do not authorize execution, CLI behavior, validation/preflight enforcement, operator confirmation enforcement, output/artifact policy enforcement, binding enforcement, audit persistence, mutation, scheduling, retries, queueing, or artifact generation.
