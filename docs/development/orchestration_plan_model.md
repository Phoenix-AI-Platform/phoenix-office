# Orchestration Plan Model

## Purpose

This document describes the first orchestration groundwork in Phoenix Office: a dry-run workflow plan model.

The model defines proposed workflow plans before human approval. It is a contract-only representation that future orchestration code may produce and present for review.

## Dry-Run Planning Only

A workflow plan describes what would happen. It does not perform the work.

The current model can represent:

- workflow name and description
- dry-run status
- whether human approval is required
- ordered proposed steps
- proposed command argument arrays
- whether a step would write an artifact
- expected artifact paths
- whether a step requires human review

Command arrays in a plan are proposed commands only. They are not executed by the plan model.

## A-1 Proposal Workflow Use Case

The first planned use case is the current manual A-1 proposal workflow. A dry-run plan can describe these intended steps:

```text
records proposal-details validate
records proposal-input
proposal validate
proposal inspect
proposal generate
```

This mirrors the accepted manual workflow without running it.

## Human Approval Boundary

Human approval remains required before any future execution layer. The plan model exists so Phoenix can eventually show an operator the proposed workflow before anything risky happens.

The current planning code does not implement approvals, execution, scheduling, worker assignment, or retries.

## Explicit Non-Behavior

The orchestration plan model does not:

- execute commands
- call subprocess
- call CLI `main()`
- open SQLite
- read or write customer/job records
- compose `ProposalInput`
- validate actual input files
- inspect actual `ProposalInput` files
- generate DOCX
- infer pricing, scope, or notes
- add natural-language intake
- add worker execution
- add plugin runtime execution
- add a one-command proposal workflow

## Relationship To Current Workflow Docs

Use this document for the dry-run plan contract. Use the existing proposal workflow docs for actual manual operation:

- [A-1 proposal MVP acceptance](a1_proposal_mvp_acceptance.md)
- [Proposal workflow operator checklist](proposal_workflow_operator_checklist.md)
- [Proposal workflow runbook](proposal_workflow_runbook.md)
- [Records CLI workflow](records_cli.md)
