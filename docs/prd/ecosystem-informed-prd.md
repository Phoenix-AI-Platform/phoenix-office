# Phoenix AI Platform — Ecosystem-Informed PRD

## Product Summary

Phoenix AI Platform is an AI operations platform for coordinating deterministic business workflows, human approval gates, plugin capabilities, and AI-assisted workers across office, infrastructure, home automation, and future operational domains.

Phoenix is not a single monolithic AI model. It is not only a UniFi optimizer. It is not only an office automation application. It is a platform spine that should let humans define, review, approve, and audit work performed by deterministic software and AI-assisted workers.

The near-term Phoenix Office work proves the platform direction through proposal generation, record-backed data flow, explicit proposal details, dry-run workflow plans, and approval boundary contracts.

## Problem

Small operators and technical teams increasingly need AI help across many tools: documents, records, networks, home automation, infrastructure, repositories, and cloud services. Existing AI agent products often move quickly from prompt to action, but they can be hard to inspect, hard to test, and hard to constrain.

Phoenix needs to solve a narrower, safer problem first: make operational work explicit, reviewable, repeatable, and auditable before any autonomous execution layer exists.

The platform must help users answer:

- What work is being requested?
- Which plugin or capability would perform it?
- What data and permissions are involved?
- What would happen before anything executes?
- Who approved it?
- What evidence proves the result?
- What stayed out of scope?

## Product Vision

Phoenix should become a human-controlled AI worker operating system for operational tasks.

The platform should coordinate:

- AI workers
- deterministic plugins
- tool access
- repositories
- local and cloud infrastructure
- human approval gates
- audit trails
- verification evidence

The core workflow should remain:

```text
Observe -> Analyze -> Recommend -> Simulate -> Approve -> Execute -> Verify
```

Phoenix should let users move from manual explicit workflows to reviewed automation gradually. The system should prefer dry-run plans, structured contracts, and explicit approval records before any execution behavior is added.

## Current MVP Foundation

Phoenix Office already provides a useful MVP foundation:

- proposal data models and DOCX rendering
- record models for customers and jobs
- in-memory and SQLite-backed record repositories
- JSON codecs and examples for records and proposal details
- CLI commands for record import/list/show/export
- CLI commands for composing explicit `ProposalInput` JSON
- CLI commands for validating and inspecting proposal inputs/details
- smoke-tested record-backed proposal workflow
- plugin capability metadata for proposal generation
- contract-only TaskEnvelope examples
- dry-run orchestration plan model and JSON fixture
- approval boundary model and review JSON fixtures
- architecture, process, guardrail, and runbook documentation

This foundation is intentionally explicit. Records do not infer pricing or scope. Orchestration plans do not execute. Approval reviews do not approve or execute anything by themselves. DOCX generation remains a separate explicit command.

## Competitive / Ecosystem Landscape

Phoenix exists in an ecosystem that includes:

- General agent frameworks such as LangChain, AutoGen, CrewAI, Semantic Kernel, and OpenAI Agents SDK.
- Tool and connector standards such as MCP.
- Automation platforms such as Zapier, Make, n8n, Home Assistant, and Node-RED.
- Infrastructure control surfaces such as Docker, Kubernetes, Synology, cloud APIs, UniFi, and local Windows/Linux tools.
- Enterprise workflow and RPA systems that emphasize process, approvals, and auditability.
- Local LLM runners and model gateways that make model choice increasingly interchangeable.

The ecosystem suggests Phoenix should not compete by becoming another broad agent framework. Phoenix should instead own the operational control plane: contracts, permissions, plugin boundaries, approvals, evidence, and human review.

Phoenix can borrow from agent frameworks and connector protocols later, but only behind stable contracts and policy boundaries.

## Product Principles

- Human approval before risky execution.
- Deterministic contracts before autonomous behavior.
- Explicit inputs before inference.
- Dry-run plans before execution.
- Plugin boundaries before plugin runtime behavior.
- Audit records before background automation.
- Small, reviewable PRs before broad platform changes.
- Testable core logic before AI-assisted convenience layers.
- Local/private data protection before integrations.
- Clear non-capabilities are as important as capabilities.

## MVP Scope

The MVP should focus on making existing manual workflows explicit and inspectable.

In scope:

- Continue hardening the Phoenix Office proposal workflow.
- Keep records, proposal details, and proposal input composition explicit.
- Add read-only inspection helpers where useful.
- Expand sanitized examples and docs.
- Maintain plugin capability metadata and contract examples.
- Maintain dry-run orchestration and approval boundary contracts.
- Improve operator and developer runbooks.

Out of scope for MVP:

- autonomous workflow execution
- worker execution
- plugin runtime execution
- natural-language intake that performs business decisions
- inferred pricing, scope, or notes
- automatic DOCX generation from orchestration
- background schedulers or retries
- CRM/email/PDF/cloud integrations unless separately approved

## Near-Term Requirements

Near-term work should strengthen reviewability and explicit composition:

- Keep project-state documentation current after verified PRs.
- Add read-only inspection for dry-run plans and approval reviews before any execution path.
- Continue adding sanitized JSON examples for core contracts.
- Keep CLI commands narrow and explicit.
- Preserve separate steps for records import, proposal input composition, validation, inspection, and DOCX generation.
- Add documentation for future task prompts, CI repair, and next-brick planning.
- Avoid new dependencies unless there is a clear and reviewed need.

Near-term success means a human can understand the current system state, inspect a proposed workflow, and review artifacts without trusting hidden execution behavior.

## Medium-Term Requirements

Medium-term work can introduce more platform shape after the contracts are stable:

- Define a plugin manifest and capability registry pattern across domains.
- Add richer permission models for local files, network access, secrets, and destructive operations.
- Add persistent audit records for task requests, approval decisions, and verification evidence.
- Add API surfaces for reading metadata and submitting explicit requests.
- Add MCP surfaces only where contracts and permissions are clear.
- Introduce worker adapters for Codex, local LLMs, Unity AI, and future agents as external workers coordinated by Phoenix.
- Add simulation and verification layers before any execution layer.
- Expand to Office, UniFi, Unity, Home Assistant, Docker, Windows, Linux, Synology, cloud, and future plugins using the same contract discipline.

## Security Requirements

Phoenix must treat operations as high-trust, high-risk work.

Security requirements:

- Require explicit approval before risky or destructive actions.
- Keep secrets out of repository files, examples, logs, and generated artifacts.
- Avoid private customer data in committed examples.
- Represent permissions clearly before execution is possible.
- Separate read, write, execute, network, and destructive permissions.
- Keep audit records for approvals and future execution attempts.
- Preserve verification evidence for completed work.
- Fail closed when permissions, approval, or contract validation are unclear.
- Treat local filesystem, shell, network, and infrastructure access as privileged capabilities.

## Architecture Recommendation

Phoenix should keep a deterministic, testable core that coordinates contracts, plugin metadata, permissions, approval boundaries, and verification evidence.

The recommended architecture is layered:

```text
Phoenix Core contracts
  -> plugin capability metadata
  -> registries and task envelopes
  -> dry-run workflow plans
  -> human approval records
  -> verification evidence
  -> future execution adapters
  -> optional API/MCP/AI interfaces
```

Phoenix should not become a general AI agent framework. It should keep a deterministic, testable core and add API/MCP/AI layers only after plugin boundaries, approval gates, and audit/security controls are clear.

AI models and agent frameworks should be treated as external workers or optional interfaces, not as the platform core.

## Build / Buy / Borrow Decisions

Build:

- Phoenix Core contracts and task lifecycle models.
- Plugin capability metadata and registries.
- Approval, permission, and audit boundaries.
- Domain-specific plugins where deterministic business rules matter.
- Operator/developer documentation and review guardrails.

Buy or integrate later:

- Commodity identity, secret storage, and observability infrastructure when Phoenix needs production-grade deployment.
- External model providers and local model runtimes.
- Existing automation tools when they can sit behind Phoenix approvals and audit records.

Borrow carefully:

- MCP for tool/interface interoperability.
- Agent SDKs for worker adapters and model orchestration experiments.
- Established workflow concepts from RPA and infrastructure automation.
- Existing libraries for document, records, and infrastructure APIs when they do not blur Phoenix boundaries.

Do not borrow patterns that bypass reviewability, permissions, or deterministic contracts.

## Roadmap

Phase 0: Manual explicit workflows

- Maintain record-backed proposal workflow.
- Keep examples sanitized and reviewable.
- Continue docs/process guardrails.

Phase 1: Contract and inspection hardening

- Add read-only plan and review inspection helpers.
- Expand approval, verification, and audit examples.
- Refine capability metadata and permission sketches.

Phase 2: API and interface preparation

- Add read-only API/MCP surfaces for metadata and contract inspection.
- Define request submission paths that still require explicit approval.
- Add stronger validation and audit persistence.

Phase 3: Controlled execution experiments

- Add one narrowly scoped execution adapter behind approval gates.
- Require dry-run, approval, execution, and verification evidence.
- Keep rollback and failure behavior explicit.

Phase 4: Multi-domain platform expansion

- Add more plugins across Office, UniFi, Unity, Home Assistant, Docker, Windows, Linux, Synology, cloud, and future domains.
- Standardize worker lifecycle, retries, progress events, and verification across domains.

## Risks

- Expanding into execution too early could weaken trust and safety.
- Becoming a generic agent framework would dilute the product and duplicate better-funded ecosystems.
- Adding too many dependencies could make the core harder to test and reason about.
- Poor permission boundaries could expose customer data, local files, infrastructure, or secrets.
- Inference-heavy workflows could create business-risk errors in pricing, scope, or customer communications.
- Documentation drift could cause future tasks to duplicate completed work or cross architecture boundaries.

## Open Questions

- Which plugin should be the first controlled execution experiment, if any?
- What approval record is sufficient for local-only low-risk actions versus higher-risk infrastructure actions?
- What persistent audit store should Phoenix use when JSON examples are no longer enough?
- Which API or MCP surfaces should be read-only first?
- How should Phoenix represent organization, user, and role permissions?
- Which external worker should be integrated first: Codex, local LLMs, Unity AI, or another agent?
- What verification evidence is required for each plugin category?

## Recommendation

Continue building Phoenix as an AI operations platform with a deterministic, testable core.

Do not turn Phoenix into a general AI agent framework. Keep AI workers, MCP tools, APIs, and agent SDKs outside the core until the platform has clear plugin boundaries, approval gates, permission rules, audit records, and verification evidence.

The next best product moves are documentation, inspection, contract hardening, and small reviewable helpers that make the current manual workflow safer and more legible. Execution should remain out of scope until explicitly approved through a dedicated architecture and safety review.
