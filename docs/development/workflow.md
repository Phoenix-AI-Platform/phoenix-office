# Phoenix Development Workflow

## Roles

- ChatGPT acts as architect/reviewer.
- Codex and Copilot act as implementation workers.

## Pull Request Process

- Keep work in small, scoped pull requests.
- Each PR should include:
  - Summary
  - Scope
  - Verification
  - Risk
  - Reviewer notes
- Every PR should run:
  - `python -m pytest`
  - `ruff check .`

## Current Safe Platform Spine

```text
architecture docs
  -> Python contracts
  -> plugin capability metadata
  -> capability registry
  -> TaskEnvelope factory
  -> JSON examples
  -> examples index
  -> PR template
```

`TaskEnvelope` and `PluginCapability` should remain the stable contract boundary for workflow and review alignment.

## Developer Workflows

- [Development progress dashboard](progress_dashboard.md) provides a visual summary of completed capabilities, current guardrails, the Mermaid roadmap, and next work lanes.
- [Project state](project_state.md) records the verified Phoenix Office implementation spine, current capabilities, non-capabilities, and guardrails for future PRs.
- [Development loop runbook](development_loop_runbook.md) documents the human-controlled branch, PR, CI, review, and merge loop for future Phoenix Office work.
- [Next-brick planning guide](next_brick_planning_guide.md) helps choose the next narrow PR without crossing execution, mutation, persistence, or automation boundaries.
- [Orchestration execution readiness checklist](orchestration_execution_readiness_checklist.md) defines documentation-only gates that must be addressed before future orchestration execution work may be considered.
- [Orchestration audit logging design notes](orchestration_audit_logging_design_notes.md) document future audit/logging expectations as design guidance only, without implementing audit persistence or execution.
- [Orchestration plan/review binding design notes](orchestration_plan_review_binding_design_notes.md) document future binding expectations as design guidance only, without implementing binding enforcement or changing models.
- [Orchestration validation/preflight design notes](orchestration_validation_preflight_design_notes.md) document future read-only validation/preflight expectations as design guidance only, without implementing validation/preflight enforcement or adding CLI commands.
- [Orchestration operator confirmation design notes](orchestration_operator_confirmation_design_notes.md) document future explicit operator confirmation expectations as design guidance only, without implementing operator confirmation enforcement, execution, or CLI commands.
- [Orchestration output artifact policy design notes](orchestration_output_artifact_policy_design_notes.md) document future output/artifact policy expectations as design guidance only, without implementing output/artifact policy enforcement, generating artifacts, or adding CLI commands.
- [Orchestration dry-run/no-write design notes](orchestration_dry_run_no_write_design_notes.md) document future no-write dry-run expectations as design guidance only, without implementing dry-run enforcement, CLI behavior, persistence, mutation, queueing, or artifact generation.
- [Orchestration execution result design notes](orchestration_execution_result_design_notes.md) document future result/reporting expectations as design guidance only, without implementing result reporting, persistence, mutation, or artifact generation.
- [Orchestration execution command surface design notes](orchestration_execution_command_surface_design_notes.md) document future command-surface expectations as design guidance only, without implementing execution, CLI behavior, models, schemas, scheduling, retries, or queueing.
- [Orchestration cancellation/rollback design notes](orchestration_cancellation_rollback_design_notes.md) document future cancellation and rollback expectations as design guidance only, without implementing cancellation, rollback, persistence, mutation, or artifact generation.
- [Orchestration input provenance design notes](orchestration_input_provenance_design_notes.md) document future input provenance expectations as design guidance only, without implementing provenance behavior, enforcement, CLI commands, models, schemas, persistence, mutation, or execution.
- [Orchestration private data/secrets design notes](orchestration_private_data_secrets_design_notes.md) document future private-data and secrets expectations as design guidance only, without implementing redaction, secret scanning, enforcement, persistence, mutation, or execution.
- [Orchestration permission/capability boundary design notes](orchestration_permission_capability_boundary_design_notes.md) document future permission and capability boundary expectations as design guidance only, without implementing authorization, runtime capability checks, enforcement, or execution.
- [Orchestration idempotency/replay design notes](orchestration_idempotency_replay_design_notes.md) document future idempotency and replay expectations as design guidance only, without implementing hashes, fingerprints, locks, persistence, replay commands, retries, queueing, mutation, or execution.
- [PR review guardrails](pr_review_guardrails.md) documents the advisory machine-readable checklist for evaluating PR scope.
- [Codex prompt patterns](codex_prompt_patterns.md) documents reusable project-state-aware prompt templates for future Codex tasks.
- [Failed CI repair prompt guide](failed_ci_repair_prompt_guide.md) documents how to create narrow repair prompts after CI fails without expanding PR scope.
- [Records CLI workflow](records_cli.md) documents the current SQLite-backed customer/job record import, list, show, and export commands.
- [A-1 proposal MVP acceptance](a1_proposal_mvp_acceptance.md) defines readiness criteria for the current internal manual A-1 proposal workflow.
- [Orchestration plan model](orchestration_plan_model.md) documents the dry-run planning contract for proposed workflow steps before human approval; see `examples/orchestration/a1_proposal_dry_run_plan.json` for a sanitized reviewable JSON example.
- [Orchestration approval boundary](orchestration_approval_boundary.md) documents contract-only approved, rejected, and needs-changes decisions before any future execution layer; see `examples/orchestration/a1_proposal_review_approved.json`, `examples/orchestration/a1_proposal_review_rejected.json`, and `examples/orchestration/a1_proposal_review_needs_changes.json` for reviewable examples that do not execute anything.
- [Orchestration inspection CLI](orchestration_inspection_cli.md) documents the read-only `orchestration plan inspect` and `orchestration review inspect` commands for plan/review visibility without execution or mutation.
- [Proposal workflow operator checklist](proposal_workflow_operator_checklist.md) is the short checklist for running the current manual A-1 record-backed proposal workflow.
- [Proposal workflow runbook](proposal_workflow_runbook.md) documents the current manual record-backed proposal command chain from records import through DOCX generation.
- [Output artifact conventions](output_artifact_conventions.md) documents where generated local workflow artifacts should go and what should not be committed.

## Scope Guardrail

Runtime/orchestrator/worker execution should not be introduced unless the task explicitly asks for it.
