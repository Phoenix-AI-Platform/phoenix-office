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

## Scope Guardrail

Runtime/orchestrator/worker execution should not be introduced unless the task explicitly asks for it.
