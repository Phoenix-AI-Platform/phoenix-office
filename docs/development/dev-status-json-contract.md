# Dev Status JSON Contract

## Purpose

This document defines the machine-readable output contract for the read-only Phoenix Office development status command:

```bash
python -m phoenix_office.cli dev status --json
```

The JSON output is intended to be safe for future Phoenix dev-assistant consumption. It summarizes local project-state documentation in a deterministic format without granting any permission to mutate repository, GitHub, workflow, proposal, or generated artifact state.

## Read-Only Behavior

The command is local-only, read-only, and deterministic.

It does:

- read local `docs/development/project_state.md` only
- print a deterministic JSON summary to stdout
- print a clear error to stderr when the project-state file is missing

It does not:

- call GitHub APIs
- read remote services
- mutate files
- run workers
- trigger workflows
- execute orchestration
- generate proposal artifacts

## JSON Fields

The stdout JSON object contains these stable fields:

- `project_name`: string
- `status_source_path`: string
- `project_state_exists`: boolean
- `latest_recorded_pr_entry`: string or null

## Success Behavior

When `docs/development/project_state.md` exists:

- the command exits `0`
- stdout is valid deterministic JSON
- `project_state_exists` is `true`
- `latest_recorded_pr_entry` is the latest recorded PR entry from the project-state verified spine, or `null` if no entry is found

## Missing Project-State Behavior

When `docs/development/project_state.md` is missing:

- the command exits nonzero
- stdout remains valid deterministic JSON
- `project_state_exists` is `false`
- `latest_recorded_pr_entry` is `null`
- stderr contains a clear missing-file message

## Consumer Guidance

Future agents may read this JSON output as advisory local development state.

Future agents must not treat this output as permission to:

- mutate repository files
- call GitHub APIs
- edit GitHub issues or pull requests
- trigger workflows
- change product code
- change schemas or models
- change proposal behavior
- change DOCX renderer behavior
- change record-backed proposal composition behavior
- create generated output artifacts
- execute orchestration, MCP, API, worker, or background behavior

Any mutation still requires an explicit user request and a dedicated narrow PR.

## Stability Note

Field additions require focused tests and documentation updates. Existing fields should remain backward compatible unless a dedicated contract-change PR is reviewed.
