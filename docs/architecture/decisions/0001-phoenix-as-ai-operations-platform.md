# ADR 0001: Phoenix As An AI Operations Platform

## Status

Accepted

## Date

2026-06-26

## Context

Phoenix has active work in office automation, proposal generation, AI-assisted development, and future operational domains such as UniFi, Unity, Home Assistant, Docker, Windows, Linux, Synology, cloud, and local AI workers.

Without an explicit platform decision, Phoenix could drift into one of several narrower identities:

- A monolithic AI model that tries to contain all intelligence and execution internally.
- A UniFi-only optimizer focused on network recommendations and configuration.
- An Office-only application focused on proposal and document automation.
- A loose collection of scripts without durable contracts, approvals, or worker boundaries.

The desired long-term system is broader: a governed AI operations layer that coordinates workers, plugins, tools, repositories, infrastructure, and human approval.

## Decision

Phoenix is defined as an AI Operations Platform and AI worker operating system.

Phoenix coordinates external and internal workers through explicit task, plugin, approval, memory, event, and verification contracts. Phoenix Core provides orchestration services such as memory, event bus, configuration, secrets, permissions, logging, scheduling, and policy enforcement.

Phoenix is not itself a single monolithic AI model. Codex, Unity AI, local LLMs, browser agents, future agents, and specialized automation services are workers coordinated by Phoenix. Office, UniFi, Unity, Home Assistant, Docker, Windows, Linux, Synology, cloud, GitHub, and future integrations are plugins or plugin families.

## Alternatives Considered

- Monolithic AI model: rejected because Phoenix needs to coordinate many tools, environments, and approval boundaries rather than concentrate all behavior inside one model.
- UniFi-only optimizer: rejected because network optimization is one important plugin domain, not the platform identity.
- Office-only application: rejected because proposal generation is an early plugin workflow, not the full architecture.
- Script collection: rejected because Phoenix needs durable task lifecycle, auditability, permissions, memory, and verification.

## Consequences

Positive consequences:

- Phoenix can support many domains without redefining itself for each one.
- Workers and plugins can evolve independently behind consistent contracts.
- Human approval and verification become platform rules instead of ad hoc habits.
- GitHub issues and PRs can act as first-class task lifecycle artifacts.

Tradeoffs:

- Platform contracts must be documented before broad runtime expansion.
- Early feature work may slow while architecture boundaries are clarified.
- Plugins need capability metadata, permissions, and verification plans rather than raw scripts only.

Follow-up work:

- Define draft contracts for task envelopes, worker events, plugin capabilities, approvals, and verification evidence.
- Create ADRs for major future boundary decisions.
- Keep Phoenix Office as an early plugin while Phoenix Core contracts mature.

## Links

- Related docs: [Phoenix Architecture Manual](../PHOENIX_ARCHITECTURE_MANUAL.md)
- Related docs: [Contracts](../contracts.md)
- Related docs: [Roadmap](../roadmap.md)
