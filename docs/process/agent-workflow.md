# Agent Workflow

## Purpose

This document describes the safe workflow for Codex and other AI workers contributing to Phoenix Office.

It is process guidance only. It does not add automation, execution behavior, API behavior, MCP behavior, dependencies, CI changes, or product-code behavior.

## Required Flow

1. A human assigns one narrow task.
2. The agent creates one branch for that task.
3. The agent opens one PR for that task.
4. CI must pass before merge.
5. ChatGPT reviews before merge.
6. A human merges after review.

There is no autonomous merge. Agents must not merge their own PRs.

## Current Safe Agent Tasks

Agents may handle narrow tasks such as:

- docs/process updates
- documentation navigation updates
- project-state updates when explicitly scoped
- tests for existing behavior when explicitly scoped
- sanitized fixture coverage when explicitly scoped
- small cleanup that does not change runtime behavior

These tasks should preserve the deterministic core and existing human-review loop.

## Tasks Not Allowed Yet

Agents must not add or change these areas unless a task explicitly scopes them:

- orchestration execution
- workflow automation
- API behavior
- MCP behavior
- worker execution
- scheduling, retries, queues, or persistence
- approval or review mutation behavior
- DOCX renderer behavior
- generated output artifacts
- product schemas or models
- private customer data
- dependencies
- CI configuration

## PR Expectations

Each agent PR should include:

- summary of the change
- explicit scope statement
- changed files
- out-of-scope confirmation
- validation performed, or a clear explanation for validation not run
- risks and reviewer notes

## Stop Conditions

Stop and ask for human direction if the task requires crossing the scoped boundary, using private customer data, changing generated artifacts, modifying models or schemas, adding execution, or changing automation/CI behavior.
