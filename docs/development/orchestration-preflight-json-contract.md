# Orchestration Preflight JSON Contract

## Purpose

This document defines the machine-readable output contract for the read-only orchestration preflight inspection command:

```bash
python -m phoenix_office.cli orchestration preflight inspect PLAN.json REVIEW.json --json
```

The JSON output lets reviewers and future tooling inspect a `WorkflowPlan` and `WorkflowPlanReview` pair deterministically before any future execution capability exists. It is advisory inspection output only.

## Inputs

The command accepts two explicit local JSON file paths:

- `PLAN.json`: a serialized `WorkflowPlan`
- `REVIEW.json`: a serialized `WorkflowPlanReview`

Both files must exist, be regular files, contain valid JSON, and validate against the existing models.

## Output

When structurally valid input is provided:

- the command exits `0`
- stdout is valid deterministic JSON
- stdout contains the current `PreflightReport` serialized with sorted, indented JSON
- stderr is empty

Blocking preflight issues are represented inside the JSON report. They do not make the command fail when both input files are structurally valid.

## Stable Fields

Current top-level fields emitted by `PreflightReport` are:

- `plan_workflow_name`: string
- `plan_fingerprint`: string
- `reviewed_plan_fingerprint`: string or null
- `plan_fingerprint_matches_review`: boolean or null
- `review_workflow_name`: string
- `review_decision`: string
- `approved_for_execution`: boolean
- `plan_valid`: boolean
- `review_valid`: boolean
- `execution_available`: boolean
- `execution_message`: string
- `safe_to_consider_for_future_execution`: boolean
- `issues`: array

`plan_fingerprint` is a lowercase SHA-256 hex digest of the loaded `WorkflowPlan` serialized from normalized JSON using sorted keys and compact separators. The same plan content produces the same fingerprint across runs, and meaningful plan content changes should change the fingerprint.

`reviewed_plan_fingerprint` is the optional SHA-256 fingerprint carried by the `WorkflowPlanReview` to identify the exact plan content reviewed by the human.

`plan_fingerprint_matches_review` is `true` when `reviewed_plan_fingerprint` is present and matches the computed `plan_fingerprint`, `false` when it is present but different, and `null` when the review does not carry a fingerprint.

`plan_valid` and `review_valid` currently indicate that the loaded model objects were structurally valid before preflight reporting.

## Issues

The `issues` array contains zero or more issue objects. Each issue has:

- `code`: stable string issue code
- `message`: human-readable issue text
- `blocking`: boolean indicating whether the issue blocks considering the pair for future execution

Known current blocking issue codes include:

- `review_not_approved`
- `review_not_marked_approved_for_execution`
- `workflow_name_mismatch`
- `review_plan_fingerprint_missing`
- `review_plan_fingerprint_mismatch`

Consumers should prefer `code` for deterministic checks and treat `message` as operator-facing text.

## Execution Availability

`execution_available` is currently always `false`.

This means Phoenix Office can inspect the plan/review pair but still cannot execute orchestration plans. A report with no blocking issues is not permission to execute, enqueue, schedule, retry, approve, mutate, or generate artifacts.

## Future Execution Consideration

`safe_to_consider_for_future_execution` is `true` only when the current preflight checks find no blocking issues.

This field means the pair passed the current read-only preflight checks. It does not mean execution exists, is authorized, or should occur. Future execution remains unavailable unless explicitly implemented and reviewed in later dedicated PRs.

`plan_fingerprint` is a stable identifier for the exact plan content being inspected.

`reviewed_plan_fingerprint` and `plan_fingerprint_matches_review` let preflight report whether the review appears to identify the same plan content being inspected. A matching fingerprint is not an approval signal, execution authorization, audit record, or mutation permission.

## Read-Only Behavior

The command loads explicit local files, runs read-only preflight inspection, and prints a report.

It does not:

- execute orchestration
- approve, reject, or mutate plans or reviews
- enqueue, schedule, retry, or run anything
- persist audit logs
- write output artifacts
- generate DOCX files
- change proposal data
- infer pricing, scope, notes, or customer data
- call GitHub APIs
- call external services
- start API, MCP, server, worker, or background behavior

## Exit Codes

Structurally valid input returns `0`, even when the preflight report contains blocking issues.

The command returns nonzero for input failures, including:

- missing plan or review files
- directory paths instead of files
- invalid JSON
- invalid `WorkflowPlan` model data
- invalid `WorkflowPlanReview` model data

On failure, errors are written to stderr and no partial JSON report is emitted.

## Consumer Guidance

Consumers may inspect, display, summarize, or block future workflow consideration based on report fields.

Consumers may show `plan_fingerprint`, `reviewed_plan_fingerprint`, and `plan_fingerprint_matches_review` to help operators identify whether the current `WorkflowPlan` matches the content identified by the review. Consumers must not treat matching fingerprints as proof of approval or permission to act.

Consumers must not treat this JSON as permission to:

- execute orchestration
- mutate plans or reviews
- approve or reject anything
- render DOCX files
- write generated output artifacts
- submit, email, file, enqueue, schedule, or retry anything
- infer pricing, scope, notes, item descriptions, or customer data
- call GitHub APIs, external services, API/MCP servers, workers, or background behavior

Any mutation or execution capability requires an explicit user request and a dedicated narrow reviewed PR.

## Stability Note

New fields may be added later as the preflight report grows. Consumers should tolerate additional fields.

Existing field meanings should remain stable unless a deliberate versioned contract-change PR is reviewed and this document is updated.
