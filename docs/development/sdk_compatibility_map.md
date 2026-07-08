# Phoenix Office SDK Compatibility Map

## Purpose

This document maps the current Phoenix Office proposal workflow to the initial `phoenix-sdk` contract without changing runtime behavior.

It is a planning document for future integration work.

## Status

Current status: Draft mapping

Behavior impact: None

Code impact: None

## Canonical SDK Contract

Phoenix SDK currently defines:

- `PluginManifest`
- `ExecutionContext`
- `CommandRequest`
- `RequiresApproval`
- `ArtifactMetadata`
- `CommandResult`
- `ResultStatus`
- `PluginCommand`
- `PhoenixPlugin`

## Current Phoenix Office Workflow

The current manual proposal workflow is:

```text
CustomerRecord / JobRecord JSON
  -> import into SQLite RecordStore
  -> validate explicit RecordProposalDetails JSON
  -> compose deterministic ProposalInput JSON
  -> validate ProposalInput JSON
  -> inspect ProposalFields
  -> render DOCX from template
```

The deterministic generation path must remain unchanged until an SDK adapter is introduced and tested separately.

## Proposed Plugin Manifest Mapping

Future `PluginManifest` for Phoenix Office:

```text
plugin_id: phoenix.office
name: Phoenix Office
version: repository/package version
description: Contractor office automation plugin for Phoenix
commands:
  - proposal.generate_docx
  - proposal.prepare_fields
```

Initial command exposure should be conservative. Do not expose broader workflow automation until deterministic boundaries are stable.

## Proposed Command Mapping

### proposal.prepare_fields

Purpose:

Prepare deterministic proposal fields from a validated `ProposalInput`.

Current implementation:

- `ProposalGenerator().prepare(proposal)`

SDK mapping:

- `CommandRequest.command`: `proposal.prepare_fields`
- `CommandRequest.payload`: serialized proposal input
- `CommandResult.status`: `success` or `failed`
- `CommandResult.data`: serialized `ProposalFields`
- `CommandResult.artifacts`: none

### proposal.generate_docx

Purpose:

Render a DOCX proposal from validated proposal input and an explicit template path.

Current implementation:

- `DocxProposalRenderer().render(...)`
- CLI proposal generation path

SDK mapping:

- `CommandRequest.command`: `proposal.generate_docx`
- `CommandRequest.payload`: proposal input, template path, output path
- `CommandResult.status`: `success`, `failed`, or `requires_approval`
- `CommandResult.artifacts`: generated DOCX metadata
- `CommandResult.approval`: required before sending customer-facing output, if the command is later used in an automated flow

## Approval Boundary

Generating a local DOCX file from explicit input can remain deterministic.

Sending, emailing, filing, or otherwise delivering customer-facing output should require explicit human approval.

Future SDK adapters should treat document delivery as separate from document generation.

## Artifact Mapping

Generated DOCX output should eventually map to `ArtifactMetadata`:

```text
artifact_id: stable generated artifact id
name: output file name
media_type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
uri: local path or managed artifact URI
metadata:
  customer_name
  proposal_date
  source_template
```

## Integration Constraints

- Do not change proposal output formatting while adding SDK compatibility.
- Do not introduce Phoenix Core dependencies into Phoenix Office.
- Do not allow AI-generated content inside deterministic proposal generation.
- Keep SDK integration behind a thin adapter layer.
- Preserve existing CLI behavior.
- Add tests before routing existing workflows through SDK interfaces.

## Recommended Adapter Shape

A future adapter should be introduced under a clearly isolated module, for example:

```text
src/phoenix_office/sdk_adapter.py
```

That adapter should implement `PhoenixPlugin` without moving existing proposal business logic.

## Recommended Next PR

Add a thin, tested SDK adapter that exposes Phoenix Office as a `PhoenixPlugin` while preserving existing behavior.

Suggested scope:

- Add `phoenix-sdk` as a development or package dependency.
- Add `PhoenixOfficePlugin` adapter.
- Add command metadata only.
- Add tests that the adapter satisfies `PhoenixPlugin`.
- Do not execute proposal generation through the adapter yet.

## Out of Scope

- Replacing the CLI.
- Moving proposal generation logic.
- Changing DOCX rendering.
- Adding Phoenix Core orchestration.
- Adding automated customer delivery.
- Changing proposal schemas.
