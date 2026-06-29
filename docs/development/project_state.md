# Phoenix Office Project State

## Purpose

This document is a project-state handoff for Phoenix Office. It is intended to reduce duplicate work, clarify current capabilities, and preserve architecture boundaries across future PRs.

Use it as a repo-native source of truth for future development prompts, reviews, and planning.

For a visual overview of completed capabilities, the Mermaid roadmap, guardrails, and next work lanes, see [development progress dashboard](progress_dashboard.md).

For the recommended human-controlled development process, see [development loop runbook](development_loop_runbook.md).

For the repo-native issue-driven autopilot process direction, see [Phoenix autopilot loop](../process/phoenix-autopilot-loop.md).

For Phoenix task issue classification guidance, see [Phoenix task labels](../process/phoenix-task-labels.md).

For the issue-to-Codex trigger evaluation, see [issue-to-Codex trigger evaluation](../process/issue-to-codex-trigger-evaluation.md).

For docs-only autopilot eligibility guidance, see [docs-only autopilot eligibility](../process/docs-only-autopilot-eligibility.md).

For the docs-only auto-merge implementation plan, see [docs-only auto-merge implementation plan](../process/docs-only-auto-merge-implementation-plan.md).

For the docs-only auto-merge dry-run gate, see [docs-only auto-merge dry-run gate](../process/docs-only-auto-merge-dry-run.md).

For the docs-only auto-merge pilot, see [docs-only auto-merge pilot](../process/docs-only-auto-merge-pilot.md).

For choosing the next narrow PR, see [next-brick planning guide](next_brick_planning_guide.md).

For documentation-only gates before any future orchestration execution work may be considered, see [orchestration execution readiness checklist](orchestration_execution_readiness_checklist.md).

For documentation-only future audit/logging expectations, see [orchestration audit logging design notes](orchestration_audit_logging_design_notes.md).

For documentation-only future plan/review binding expectations, see [orchestration plan/review binding design notes](orchestration_plan_review_binding_design_notes.md).

For documentation-only future validation/preflight expectations, see [orchestration validation/preflight design notes](orchestration_validation_preflight_design_notes.md).

For the read-only orchestration preflight JSON output contract, see [orchestration preflight JSON contract](orchestration-preflight-json-contract.md).

For documentation-only future operator confirmation expectations, see [orchestration operator confirmation design notes](orchestration_operator_confirmation_design_notes.md).

For documentation-only future output/artifact policy expectations, see [orchestration output/artifact policy design notes](orchestration_output_artifact_policy_design_notes.md).

For documentation-only future dry-run/no-write expectations, see [orchestration dry-run/no-write design notes](orchestration_dry_run_no_write_design_notes.md).

For documentation-only future execution result/reporting expectations, see [orchestration execution result design notes](orchestration_execution_result_design_notes.md).

For documentation-only future execution command-surface expectations, see [orchestration execution command surface design notes](orchestration_execution_command_surface_design_notes.md).

For documentation-only future cancellation/rollback expectations, see [orchestration cancellation/rollback design notes](orchestration_cancellation_rollback_design_notes.md).

For documentation-only future input provenance expectations, see [orchestration input provenance design notes](orchestration_input_provenance_design_notes.md).

For documentation-only future private-data/secrets expectations, see [orchestration private data/secrets design notes](orchestration_private_data_secrets_design_notes.md).

For documentation-only future permission/capability boundary expectations, see [orchestration permission/capability boundary design notes](orchestration_permission_capability_boundary_design_notes.md).

For documentation-only future idempotency/replay expectations, see [orchestration idempotency/replay design notes](orchestration_idempotency_replay_design_notes.md).

For the advisory PR scope checklist, see [PR review guardrails](pr_review_guardrails.md).

For reusable project-state-aware Codex prompt templates, see [Codex prompt patterns](codex_prompt_patterns.md).

For focused repair prompts after CI fails, see [failed CI repair prompt guide](failed_ci_repair_prompt_guide.md).

For the ecosystem-informed Phoenix AI Platform product direction, see [ecosystem-informed PRD](../prd/ecosystem-informed-prd.md).

## Current Verified Spine

```text
#2  Proposal data model and generator foundation
#4  DOCX template renderer
#5  A-1 proposal template fixture and Abby Hill verified DOCX test
#6  GitHub Actions workflow running pytest and ruff
#7  CLI command to generate proposal DOCX from JSON

#16 Phoenix master architecture documentation
#17 Phoenix Core contract skeletons
#18 Phoenix Office proposal capability metadata
#19 Metadata-only plugin capability registry
#20 Contract-only proposal TaskEnvelope factory
#21 Proposal TaskEnvelope JSON example
#22 Office proposal PluginCapability JSON example
#23 Examples index docs
#24 PR template
#25 Issue templates + workflow docs

#26 Read-only capabilities list CLI
#27 Read-only TaskEnvelope show CLI
#28 Read-only TaskEnvelope validation CLI

#29 CustomerRecord and JobRecord model skeletons
#30 In-memory records repositories
#31 SQLite records repositories
#32 RecordStore facade/factories
#33 Record JSON codec helpers
#34 Record JSON example fixtures
#35 RecordStore JSON import/export helpers
#36 RecordStore JSON file helpers
#37 records import CLI
#38 records list CLI
#39 records show CLI
#40 records export CLI
#41 records CLI docs + smoke test
#42 Record-to-ProposalInput adapter
#43 RecordProposalDetails model + helpers
#44 Compose ProposalInput from records + details
#45 records proposal-input CLI
#46 Record-backed proposal workflow smoke test
#47 Proposal workflow runbook
#48 Proposal workflow runbook links
#49 Proposal details validation CLI
#50 ProposalInput validation CLI
#51 Validation preflights added to proposal workflow smoke test
#52 Proposal workflow operator checklist
#53 ProposalInput inspect CLI command
#54 Proposal inspect added to record-backed workflow smoke test
#55 Proposal workflow documentation navigation
#56 RecordProposalDetails starter template
#57 Second sanitized A-1 proposal workflow fixture
#58 Output artifact conventions
#59 A-1 proposal MVP acceptance document
#60 Dry-run orchestration plan model skeleton
#61 Dry-run orchestration plan JSON fixture
#62 Orchestration approval boundary contract
#63 Approval review JSON fixtures
#64 Project state verified spine doc
#65 Phoenix development loop runbook
#66 PR review guardrails JSON
#67 Codex prompt patterns documentation
#69 Failed CI repair prompt guide
#70 Ecosystem-informed Phoenix AI Platform PRD
#72 Read-only WorkflowPlan inspect CLI
#73 Project state update through PR #72
#74 Read-only WorkflowPlanReview inspect CLI
#75 Project state update through PR #74
#76 Orchestration inspection CLI guide
#77 Orchestration inspection CLI help tests
#78 WorkflowPlanReview inspect fixture coverage
#79 Orchestration inspection path error tests
#81 Next-brick planning guide
#82 Project state update through PR #81
#83 Orchestration CLI non-execution surface tests
#85 Orchestration execution readiness checklist
#87 Orchestration audit logging design notes
#89 Orchestration plan/review binding design notes
#91 Orchestration validation/preflight design notes
#93 Orchestration operator confirmation design notes
#95 Orchestration output/artifact policy design notes
#96 Batched orchestration execution gate design notes
#101 cli: improve proposal validation error readability (operator-facing invalid ProposalInput errors + focused tests)
#103 test: add invalid ProposalInput fixture (sanitized invalid fixture reused in focused validation-error tests)
#105 docs: add ProposalInput validation examples (valid/invalid validation commands + operator-facing field-level errors)
#107 ci: add pull request body section guard (read-only PR body guard workflow + required-section script)
#109 process: add project state entry checker (read-only local helper for checking project_state.md PR entries)
#112 test: add deterministic proposal inspect regression coverage (focused assertions for Abby Hill stable summary lines + tmp_path-backed Company/Notes conditional case)
#114 test: strengthen deterministic record-backed proposal workflow regression assertions (Abby Hill + Sample North Prairie composed ProposalInput fields and inspect output)
#116 cli: add optional JSON output to proposal inspect (deterministic `proposal inspect --json` emits normalized ProposalInput JSON; default text inspect output remains unchanged)
#118 chore: fix E501 in project state guard script (wrapped project-state checker PR-number argument definition so full repo ruff lint passes cleanly again)
#120 feat: add read-only dev status command (`python -m phoenix_office.cli dev status` reads project_state.md and reports the latest recorded PR entry)
#122 feat: add JSON output to dev status (`python -m phoenix_office.cli dev status --json` emits deterministic machine-readable JSON for the read-only local dev status command)
#124 docs: document dev status JSON contract (`docs/development/dev-status-json-contract.md` documents the read-only `dev status --json` output contract and consumer safety boundaries)
#126 test: cover record-backed proposal inspect JSON (deterministic regression coverage proves Abby Hill and Sample North Prairie composed ProposalInput output can be inspected through `proposal inspect --json`)
#128 docs: clarify record-backed proposal inspection (documents human-readable and machine-readable `proposal inspect` review commands after record-backed ProposalInput composition; rendering still requires explicit `proposal generate`)
#129 docs: document proposal inspect JSON contract (adds `docs/proposals/proposal-inspect-json-contract.md` describing read-only `proposal inspect --json` inputs, normalized JSON output, failure behavior, consumer guidance, and stability expectations)
#130 test: cover proposal inspect JSON optional fields (adds deterministic `proposal inspect --json` coverage for `company_config`, provided notes, and omitted notes defaulting to an empty list)
#134 feat: add non-executing orchestration preflight skeleton (adds read-only WorkflowPlan/WorkflowPlanReview preflight reports with blocking issues for rejected or needs_changes reviews; execution remains unavailable)
#135 cli: add read-only orchestration preflight inspect (`orchestration preflight inspect` prints deterministic non-executing WorkflowPlan/WorkflowPlanReview preflight summaries; execution remains unavailable)
#136 cli: add JSON output to orchestration preflight inspect (`orchestration preflight inspect --json` emits deterministic read-only PreflightReport JSON; execution remains unavailable)
#137 docs: document orchestration preflight JSON contract (adds `docs/development/orchestration-preflight-json-contract.md` describing read-only preflight JSON fields, issues, exit behavior, consumer guidance, and compatibility expectations)
#138 feat: add deterministic plan fingerprint to orchestration preflight (adds SHA-256 WorkflowPlan fingerprints to read-only PreflightReport output, human preflight inspect output, and JSON preflight inspect output; execution remains unavailable)
#139 feat: bind orchestration reviews to plan fingerprints (adds optional reviewed WorkflowPlan fingerprints to WorkflowPlanReview fixtures and read-only preflight reports, with blocking issues for missing or mismatched bindings; execution remains unavailable)
#142 docs/process: define Phoenix autopilot loop (adds `docs/process/phoenix-autopilot-loop.md` documenting the issue-driven, review-gated Phoenix autopilot process direction; no automation or execution behavior added)
#144 chore: add Phoenix task issue template (updates `.github/ISSUE_TEMPLATE/phoenix_task.yml` and adds `docs/process/phoenix-task-labels.md` for repo-native Phoenix task intake, risk classification, and merge-authority guidance; no automation behavior added)
#146 docs/process: evaluate issue-to-Codex trigger path (adds `docs/process/issue-to-codex-trigger-evaluation.md` documenting candidate issue-to-Codex trigger paths, observed access separation, safety gates, and manual fallback recommendation; no trigger behavior added)
#148 ci: add docs-only autopilot eligibility check (adds read-only `.github/workflows/docs_only_autopilot_eligibility.yml` and `docs/process/docs-only-autopilot-eligibility.md` for future docs-only eligibility signaling; no auto-merge or mutation behavior added)
#150 docs/process: define docs-only auto-merge implementation plan (adds `docs/process/docs-only-auto-merge-implementation-plan.md` documenting the future docs-only auto-merge eligible class, permission model, checks, fail-closed behavior, and implementation checklist; no auto-merge behavior added)
#152 ci: add docs-only auto-merge dry-run gate (adds read-only `.github/workflows/docs_only_auto_merge_dry_run.yml` and `docs/process/docs-only-auto-merge-dry-run.md` to evaluate future docs-only auto-merge gates without merge, approval, labels, comments, or repository writes)
#154 ci: implement docs-only auto-merge pilot workflow (adds `.github/workflows/docs_only_auto_merge.yml` and `docs/process/docs-only-auto-merge-pilot.md` for label-gated docs-only squash merge after required gates pass; no approval, label, comment, branch-update, trigger, or background behavior added)
#158 ci: fix docs-only auto-merge required check detection (updates docs-only dry-run and pilot workflows to resolve required checks by accepted workflow/check-run aliases while preserving fail-closed and defer behavior; docs updated for alias diagnostics)
```

## Current Manual A-1 Proposal Workflow

Phoenix Office can manually generate A-1 proposal DOCX files from explicit records and details through CLI commands.

```text
CustomerRecord / JobRecord JSON
  -> import into SQLite RecordStore
  -> validate explicit RecordProposalDetails JSON
  -> compose deterministic ProposalInput JSON
  -> validate ProposalInput JSON
  -> inspect ProposalInput summary
  -> generate DOCX proposal
```

This workflow is accepted for internal manual v0.1 use, subject to human review.

## Current Orchestration State

- `WorkflowPlan` model exists.
- `WorkflowPlan` dry-run JSON fixture exists.
- `WorkflowPlanReview` approval boundary exists.
- Approved, rejected, and `needs_changes` review JSON fixtures exist.
- Read-only `WorkflowPlan` inspect CLI exists.
- Read-only `WorkflowPlanReview` inspect CLI exists.
- Orchestration inspection CLI guide exists.
- Help/discoverability tests protect the read-only orchestration inspection command surface.
- `WorkflowPlanReview` inspect is covered for approved, rejected, and `needs_changes` review fixtures.
- `WorkflowPlan` and `WorkflowPlanReview` inspect path error handling is covered for missing files and directory paths.
- Unsupported orchestration execution/mutation command shapes are tested and rejected, including `orchestration execute/run/apply`, `orchestration plan execute/run`, and `orchestration review approve/reject/apply`.
- Planning and approval contracts are non-executing.

Phoenix Office can describe a proposed A-1 workflow as a dry-run plan and represent human review decisions as JSON. Phoenix Office still cannot execute orchestration plans.

For command usage and operator sequence details, see [Orchestration inspection CLI](orchestration_inspection_cli.md).

Current read-only plan inspection command:

```bash
python -m phoenix_office.cli orchestration plan inspect examples/orchestration/a1_proposal_dry_run_plan.json
```

This command parses an existing `WorkflowPlan` JSON file and prints a human-readable summary. It does not execute, approve, reject, mutate, persist, enqueue, schedule, retry, or generate artifacts.

Current read-only review inspection command:

```bash
python -m phoenix_office.cli orchestration review inspect examples/orchestration/a1_proposal_review_approved.json
```

This command parses an existing `WorkflowPlanReview` JSON file and prints a human-readable summary. It is read-only and non-executing. It does not approve, reject, or mutate reviews, and it does not execute, persist, enqueue, schedule, retry, or generate artifacts.

## Current Development-Process State

Phoenix Office now has repo-native process documentation for keeping future work narrow and project-state-aware:

- a project-state handoff
- a development loop runbook
- a Phoenix autopilot loop process direction
- Phoenix task issue classification guidance
- an issue-to-Codex trigger evaluation
- docs-only autopilot eligibility guidance
- a docs-only auto-merge implementation plan
- a docs-only auto-merge dry-run gate
- a docs-only auto-merge pilot workflow
- a next-brick planning guide
- an orchestration execution readiness checklist
- orchestration audit logging design notes
- orchestration plan/review binding design notes
- orchestration validation/preflight design notes
- orchestration operator confirmation design notes
- orchestration output/artifact policy design notes
- orchestration dry-run/no-write design notes
- orchestration execution result design notes
- orchestration execution command surface design notes
- orchestration cancellation/rollback design notes
- orchestration input provenance design notes
- orchestration private data/secrets design notes
- orchestration permission/capability boundary design notes
- orchestration idempotency/replay design notes
- advisory PR review guardrails JSON/docs
- Codex prompt patterns for project-state-aware tasks
- a failed CI repair prompt guide

The orchestration execution readiness checklist is documentation only. It does not approve or implement execution.

The orchestration audit logging design notes are documentation only. They do not implement audit persistence or approve execution.

The orchestration plan/review binding design notes are documentation only. They do not implement binding enforcement, modify models, or approve execution.

The orchestration validation/preflight design notes are documentation only. They do not implement validation/preflight enforcement, add CLI commands, modify models, or approve execution.

The orchestration operator confirmation design notes are documentation only. They do not implement operator confirmation enforcement, add CLI commands, modify models or schemas, or approve execution.

The orchestration output/artifact policy design notes are documentation only. They do not implement output/artifact policy enforcement, generate artifacts, add CLI commands, modify models or schemas, or approve execution.

The orchestration dry-run/no-write, execution result, execution command surface, and cancellation/rollback design notes are documentation only. They do not implement behavior, add CLI commands, modify models or schemas, create persistence or mutation, generate artifacts, or approve execution.

The orchestration input provenance, private data/secrets, permission/capability boundary, and idempotency/replay design notes are documentation only. They do not implement behavior, add CLI commands, modify models or schemas, create enforcement, create persistence or mutation, generate artifacts, add authorization/redaction/secret scanning, or approve execution.

These process docs are guidance for human-controlled development and review. They do not add automation, execution, or enforcement behavior.

## Current Product Direction

The ecosystem-informed Phoenix AI Platform PRD exists at [docs/prd/ecosystem-informed-prd.md](../prd/ecosystem-informed-prd.md).

The current product direction is deterministic-core-first: Phoenix should not become a general AI agent framework. Phoenix should keep a deterministic, testable core and add API/MCP/AI layers only after plugin boundaries, approval gates, and audit/security controls are clear.

## Explicit Non-Capabilities

- No orchestration execution exists.
- No CLI workflow execution command exists.
- No CLI approval command exists.
- No natural-language intake exists.
- No audit persistence exists.
- No plan/review binding enforcement exists.
- No validation/preflight enforcement exists.
- No operator confirmation enforcement exists.
- No output/artifact policy enforcement exists.
- No dry-run/no-write enforcement exists.
- No execution result reporting exists.
- No execution command surface exists.
- No cancellation or rollback behavior exists.
- No input provenance enforcement exists.
- No private-data or secrets enforcement exists.
- No permission or capability enforcement exists.
- No idempotency or replay behavior exists.
- No worker execution exists.
- No plugin runtime execution exists.
- No scheduler or retry system exists.
- No automatic DOCX generation from orchestration exists.
- No automatic sending or filing exists.
- Pricing, scope, and notes are not inferred.

## Completed Items Not To Duplicate

Do not recreate these as new work:

- orchestration dry-run/no-write design notes from PR #96
- orchestration execution result design notes from PR #96
- orchestration execution command surface design notes from PR #96
- orchestration cancellation/rollback design notes from PR #96
- orchestration output/artifact policy design notes from PR #95
- orchestration operator confirmation design notes from PR #93
- orchestration validation/preflight design notes from PR #91
- orchestration plan/review binding design notes from PR #89
- orchestration audit logging design notes from PR #87
- orchestration execution readiness checklist from PR #85
- orchestration CLI non-execution surface tests from PR #83
- project state update through PR #82
- next-brick planning guide from PR #81
- orchestration inspection CLI guide from PR #76
- orchestration inspection CLI help tests from PR #77
- WorkflowPlanReview inspect fixture coverage from PR #78
- orchestration inspection path error tests from PR #79
- project state update through PR #75
- read-only WorkflowPlanReview inspect CLI from PR #74
- project state update through PR #73
- read-only WorkflowPlan inspect CLI from PR #72
- ecosystem-informed Phoenix AI Platform PRD from PR #70
- failed CI repair prompt guide from PR #69
- project-state verified spine doc from PR #64
- development loop runbook from PR #65
- PR review guardrails JSON/docs from PR #66
- Codex prompt patterns doc from PR #67
- approval boundary contract from PR #62
- approval review JSON fixtures from PR #63
- dry-run plan model from PR #60
- dry-run plan JSON fixture from PR #61
- MVP acceptance doc from PR #59
- output artifact conventions from PR #58

## Next Safe Development Lanes

These are safe future lanes to consider, without implementing them here:

- additional tests or docs that clarify existing behavior without changing runtime behavior

Execution remains out of scope until explicitly approved in a later task.

## Guardrails

- No execution without human approval.
- No CLI execution command yet.
- No customer data in repo.
- No generated output artifacts committed.
- No pricing, scope, or notes inference.
- No DOCX renderer/template changes without a dedicated PR.
- One branch, one PR, one narrow scope.
