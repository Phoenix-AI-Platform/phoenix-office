# Phoenix Office Project State

## Purpose

This document is a project-state handoff for Phoenix Office. It is intended to reduce duplicate work, clarify current capabilities, and preserve architecture boundaries across future PRs.

Use it as a repo-native source of truth for future development prompts, reviews, and planning.

For the recommended human-controlled development process, see [development loop runbook](development_loop_runbook.md).

For the advisory PR scope checklist, see [PR review guardrails](pr_review_guardrails.md).

For reusable project-state-aware Codex prompt templates, see [Codex prompt patterns](codex_prompt_patterns.md).

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
- `WorkflowPlan` JSON fixture exists.
- `WorkflowPlanReview` approval boundary exists.
- Approved, rejected, and `needs_changes` review JSON fixtures exist.
- Planning and approval contracts are non-executing.

Phoenix Office can describe a proposed A-1 workflow as a dry-run plan and represent human review decisions as JSON. Phoenix Office still cannot execute orchestration plans.

## Current Development-Process State

Phoenix Office now has repo-native process documentation for keeping future work narrow and project-state-aware:

- a project-state handoff
- a development loop runbook
- advisory PR review guardrails JSON/docs
- Codex prompt patterns for project-state-aware tasks

These process docs are guidance for human-controlled development and review. They do not add automation, execution, or enforcement behavior.

## Explicit Non-Capabilities

- No orchestration execution exists.
- No CLI workflow plan command exists.
- No CLI approval command exists.
- No natural-language intake exists.
- No worker execution exists.
- No plugin runtime execution exists.
- No scheduler or retry system exists.
- No automatic DOCX generation from orchestration exists.
- No automatic sending or filing exists.
- Pricing, scope, and notes are not inferred.

## Completed Items Not To Duplicate

Do not recreate these as new work:

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

- dry-run plan display/inspection helpers
- approval review display/inspection helpers
- read-only CLI commands for showing plans/reviews
- failed-CI repair prompt generator docs
- next-brick planning docs

Execution remains out of scope until explicitly approved in a later task.

## Guardrails

- No execution without human approval.
- No CLI execution command yet.
- No customer data in repo.
- No generated output artifacts committed.
- No pricing, scope, or notes inference.
- No DOCX renderer/template changes without a dedicated PR.
- One branch, one PR, one narrow scope.
