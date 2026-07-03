# Phoenix Examples

This directory contains inspectable Phoenix platform artifacts. These examples are documentation and contract fixtures only; they do not execute proposal generation, start an orchestrator, run workers, or register plugin runtime behavior.

## Artifacts

- `examples/plugins/office_generate_proposal_capability.json` shows the registered `office.generate_proposal` `PluginCapability` metadata for Phoenix Office proposal generation.
- `examples/tasks/proposal_generation_task.json` shows a serialized `TaskEnvelope` for a requested proposal-generation unit of work that references `office.generate_proposal`.
- `examples/tasks/codex_handoff_package.json` shows a serialized `CodexHandoffPackage` that wraps a `TaskEnvelope` with manual Codex workspace, prompt, PR, review, and invocation metadata.
- `examples/proposals/abby_hill.json` is a real proposal input example used by Phoenix Office tests and examples.
- `examples/records/customer_abby_hill.json` shows a serialized `CustomerRecord` for Abby Hill using the records JSON codec shape.
- `examples/records/job_abby_hill.json` shows a serialized `JobRecord` linked to the Abby Hill customer example.

The task example refers to `output/abby_hill_proposal.docx` as the intended output artifact path. The example does not create that file.

## Relationship

`PluginCapability` is capability metadata: it describes what a plugin can do, what permissions it needs, and how its output can be verified.

`TaskEnvelope` is requested work: it captures who requested the work, what refs are in scope, which capability is allowed, and what evidence should verify completion.

`CodexHandoffPackage` is preparation metadata: it wraps a `TaskEnvelope` with the workspace, prompt, expected PR, review, and manual invocation boundaries needed for a Codex handoff. It does not invoke Codex or authorize merge behavior.

`CustomerRecord` and `JobRecord` are business record examples for future fixtures, imports, exports, and intake surfaces. They are inspectable data only and do not create database rows or execute workflows.

Current platform artifact flow:

```text
architecture docs
  -> Python contracts
  -> plugin capability metadata
  -> registry
  -> task factory
  -> JSON examples
```

These examples are meant for inspection, tests, and architecture alignment. Runtime orchestration, worker execution, proposal generation, and DOCX rendering remain outside this examples layer.
