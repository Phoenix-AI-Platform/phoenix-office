# Phoenix Architecture Roadmap

This roadmap turns the architecture manual into implementation phases. It is intentionally platform-level and not limited to Phoenix Office.

The platform direction is anchored by [ADR 0001](decisions/0001-phoenix-as-ai-operations-platform.md). Draft contract shapes live in [Contracts](contracts.md) and should be refined before runtime schemas are implemented.

## Phase 0: Architecture Baseline

Status: in progress

- Define Phoenix as an AI Operations Platform.
- Document worker, plugin, memory, orchestrator, and security models.
- Establish ChatGPT architect and Codex implementation workflow.
- Add architecture decision records for foundational platform choices.
- Draft concrete contract examples for task, worker, plugin, approval, and verification records.
- Keep application feature work paused while the platform direction is clarified.

## Phase 1: Contracts And Skeletons

- Refine TaskEnvelope from the contract sketch into a versioned runtime schema.
- Refine WorkerEvent from the contract sketch into a versioned runtime schema.
- Refine PluginCapability from the contract sketch into a versioned runtime schema.
- Refine ApprovalRequest and ApprovalRecord into versioned runtime schemas.
- Refine VerificationEvidence into a versioned runtime schema.
- Define memory event schema.
- Add minimal Phoenix Core package boundaries.

Expected output: contracts, tests, and a small runnable skeleton.

## Phase 2: GitHub And Codex Workflow

- Treat GitHub issues as task intake records.
- Treat PRs as implementation records.
- Record verification results as task evidence.
- Add issue-to-worker handoff conventions.
- Add architecture decision records.

Expected output: repeatable software task lifecycle.

## Phase 3: Phoenix Office As First Plugin

- Formalize Phoenix Office as an Office plugin.
- Map proposal generation to plugin capabilities.
- Preserve existing JSON -> model -> generator -> renderer flow.
- Add approval points for external communications or customer-impacting actions before they exist.

Expected output: one domain plugin aligned with the platform model.

## Phase 4: Infrastructure And Device Plugins

- UniFi observe/recommend/simulate workflow.
- Home Assistant read and safe automation workflow.
- Docker and Synology health checks and controlled actions.
- Windows and Linux local operations with approval gates.

Expected output: safe operational automation across local infrastructure.

## Phase 5: Multi-Worker Orchestration

- Coordinate Codex, local LLMs, Unity AI, browser workers, and infrastructure workers.
- Add worker selection policies.
- Add failure, retry, and escalation behavior.
- Add durable progress reporting.

Expected output: Phoenix can route tasks across multiple worker types.

## Phase 6: Memory And Scheduling

- Durable memory store for facts, events, decisions, artifacts, and preferences.
- Permission-aware memory retrieval.
- Recurring tasks and monitors.
- Audit-ready logs and verification records.

Expected output: Phoenix remembers and schedules operations safely.

## Phase 7: Human Operations Console

A console may eventually exist, but it should come after contracts are stable.

Possible surfaces:

- CLI.
- Web dashboard.
- Chat interface.
- GitHub issue/PR interface.
- Local desktop app integration.

Expected output: better visibility and approval UX, not a replacement for core contracts.

## Non-Goals For Now

- Building a monolithic AI model.
- Replacing all plugins with one giant service.
- Adding autonomous risky execution without approval.
- Moving domain business logic into the orchestrator.
- Building UI before the platform contracts are clear.
