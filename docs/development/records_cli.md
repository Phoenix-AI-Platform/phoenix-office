# Records CLI Workflow

The records CLI is a developer/internal tool for working with SQLite-backed customer and job records in Phoenix Office. It is intended for local inspection, fixture loading, smoke testing, and early data workflow development.

Records are stored in a local SQLite database file. Missing database files are initialized automatically when a command opens the store.

## Supported Commands

Current import commands:

```bash
python -m phoenix_office.cli records import customer examples/records/customer_abby_hill.json --db output/records.sqlite
python -m phoenix_office.cli records import job examples/records/job_abby_hill.json --db output/records.sqlite
python -m phoenix_office.cli records import customers path/to/customers.json --db output/records.sqlite
python -m phoenix_office.cli records import jobs path/to/jobs.json --db output/records.sqlite
```

Current read-only inspection commands:

```bash
python -m phoenix_office.cli records list customers --db output/records.sqlite
python -m phoenix_office.cli records list jobs --db output/records.sqlite
python -m phoenix_office.cli records show customer customer-abby-hill --db output/records.sqlite
python -m phoenix_office.cli records show job job-abby-hill --db output/records.sqlite
```

Current export commands:

```bash
python -m phoenix_office.cli records export customers output/customers.json --db output/records.sqlite
python -m phoenix_office.cli records export jobs output/jobs.json --db output/records.sqlite
```

The `list` and `show` commands are read-only. They open the SQLite-backed record store and print existing records without modifying them.

The `export` commands write JSON files. They export all customer or job records from the SQLite store and create parent directories through the existing file export helpers.

## Abby Hill Example

The repository includes example records that can be imported into a local development database:

```bash
python -m phoenix_office.cli records import customer examples/records/customer_abby_hill.json --db output/records.sqlite
python -m phoenix_office.cli records import job examples/records/job_abby_hill.json --db output/records.sqlite
```

After import, inspect the records:

```bash
python -m phoenix_office.cli records list customers --db output/records.sqlite
python -m phoenix_office.cli records list jobs --db output/records.sqlite
python -m phoenix_office.cli records show customer customer-abby-hill --db output/records.sqlite
python -m phoenix_office.cli records show job job-abby-hill --db output/records.sqlite
```

Export the records back to JSON:

```bash
python -m phoenix_office.cli records export customers output/records_customers.json --db output/records.sqlite
python -m phoenix_office.cli records export jobs output/records_jobs.json --db output/records.sqlite
```

`examples/records/proposal_details_abby_hill.json` is a preparation artifact for future record-backed proposal input workflows. It is not currently accepted by a records CLI proposal command.

## Current Non-Goals

The records CLI does not currently provide:

- edit, delete, or update commands
- web UI
- natural language intake
- orchestrator behavior
- worker execution
- proposal generation from records

Proposal generation still uses the existing proposal input and DOCX rendering flow. Records are not wired into proposal generation yet.
