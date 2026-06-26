# Development Process

Phoenix development is issue-driven and architecture-led. ChatGPT acts as architect and planning partner. Codex acts as implementation worker.

## Roles

ChatGPT architect:

- Clarifies goals and constraints.
- Writes architecture direction.
- Creates GitHub issues with acceptance criteria.
- Reviews tradeoffs and sequencing.
- Keeps Phoenix aligned as an AI Operations Platform.

Codex implementation worker:

- Reads issues and repository context.
- Implements scoped changes.
- Runs tests and linters.
- Opens PRs.
- Reports verification and residual risk.

Human owner:

- Sets direction.
- Approves risky work.
- Reviews PRs and architecture changes.
- Decides priorities.

## Standard Workflow

```text
Human intent
   |
   v
ChatGPT architecture / issue definition
   |
   v
GitHub issue with acceptance criteria
   |
   v
Codex implementation branch
   |
   v
Tests, lint, docs, verification
   |
   v
Draft PR -> review -> ready -> merge
   |
   v
Memory and roadmap update
```

## Issue Quality

A Phoenix issue should include:

- Goal.
- Non-goals.
- Architecture rules.
- Acceptance criteria.
- Test expectations.
- Risk and approval notes.
- Files or modules likely affected.

Small issues are preferred. Architecture issues should be documentation-first before runtime implementation.

## PR Quality

A PR should include:

- Summary of changes.
- Verification commands and results.
- Scope boundaries.
- Links to issues.
- Known limitations or follow-up work.

PRs should avoid unrelated code churn.

## Test Expectations

Implementation PRs should run relevant tests. For Python code in this repository, the baseline is:

```bash
python -m pytest
ruff check .
```

Documentation-only PRs should still be reviewed for clarity, consistency, and architectural fit.

## Architecture Change Process

Architecture changes should be documented before implementation. A good architecture PR should:

- Define terms.
- Identify boundaries.
- Describe contracts.
- Include diagrams when useful.
- State what is intentionally out of scope.
- Create roadmap items for implementation.

## Release Discipline

Phoenix should grow through verified increments:

1. Document the contract.
2. Add minimal runtime support.
3. Add tests and audit events.
4. Integrate one plugin or worker.
5. Verify the loop end to end.
6. Generalize only after repeated use.
