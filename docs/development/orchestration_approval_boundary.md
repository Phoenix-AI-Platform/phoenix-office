# Orchestration Approval Boundary

## Purpose

This document describes the contract-only human approval boundary for dry-run workflow plans.

Human approval is the boundary between dry-run planning and any future execution layer. A plan may be reviewed before anything is allowed to run.

## Review Decisions

A workflow plan review can be:

- `approved`
- `rejected`
- `needs_changes`

Only `approved` means `approved_for_execution` is true.

`rejected` and `needs_changes` must not be executable.

## Current Behavior

The current system still does not execute anything. The approval boundary only records a human review decision for a proposed dry-run plan.

No CLI command exists for approval yet.

No worker, plugin runtime, scheduler, retry system, or autonomous execution exists.

## Non-Behavior

Approval does not:

- execute commands
- call CLI `main()`
- open SQLite
- read or write records
- compose `ProposalInput`
- validate proposal files
- inspect proposal input files
- generate DOCX
- infer pricing, scope, or notes
- send proposals
- file proposals

## Relationship To Planning

Use [orchestration plan model](orchestration_plan_model.md) for the dry-run plan contract and JSON example.

Use this document for the human approval/rejection/needs-changes boundary that must be satisfied before any future execution layer can be considered.
