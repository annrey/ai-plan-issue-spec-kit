# Ledger Modularization Plan

## Goal

Reduce `src/ai_plan_issue/ledger.py` from an all-in-one module into smaller surfaces that are safer for future agent-tool expansion.

## Current Cut

The first pass moved command-line parsing and command handlers into `src/ai_plan_issue/cli.py`.

This pass moves event, activity, presence, and event replay helpers into `src/ai_plan_issue/events.py`.

The current pass moves project state paths, token paths, SQLite connection setup, schema initialization, row conversion, and realtime index helpers into `src/ai_plan_issue/store.py`.

The latest pass moves Markdown, JSON, JSONL, issue directory, issue file, and board export helpers into `src/ai_plan_issue/exporter.py`.

The planning pass moves checklist parsing, slug generation, priority/category/module inference, and issue-number helpers into `src/ai_plan_issue/planning.py`.

The runtime pass moves realtime SQLite bootstrap, file-ledger import/export,
issue detail reads, and revision conflict checks into `src/ai_plan_issue/runtime.py`.

The mutation pass moves realtime write transactions into
`src/ai_plan_issue/mutations.py`.

The ledger module remains responsible for:

- issue generation orchestration
- legacy file-ledger mutation helpers
- compatibility aliases for stable public imports

The CLI module becomes responsible for:

- `argparse` parser construction
- command handler functions
- machine-readable CLI error mapping
- `main(argv)`

The events module becomes responsible for:

- creating SSE event rows
- creating activity rows
- updating and listing presence
- replaying events from `Last-Event-ID`
- emitting board export events

The store module becomes responsible for:

- resolving state, index, database, token, and lock paths
- creating and opening the SQLite database
- initializing tables and WAL mode
- reading issue rows and building realtime indexes
- issuing or reading the project token

The exporter module becomes responsible for:

- loading and saving `index.json`
- resolving issue directory paths
- creating issue Markdown, comments/activity JSONL, and implementation reports
- refreshing `board.md`
- appending file-ledger comments and activity records

The planning module becomes responsible for:

- parsing Spec-style checklist tasks
- deriving issue group keys
- inferring priority, category, and module defaults
- generating slugs and parent/child issue numbers

The runtime module becomes responsible for:

- importing Markdown/JSONL ledgers into SQLite
- exporting SQLite state back to Markdown/JSONL
- loading realtime issue indexes and issue details
- checking expected revisions for optimistic concurrency
- exposing `ConflictError` for CLI and server error mapping

The mutations module becomes responsible for:

- updating issue fields
- appending comments
- creating parent and child issues
- splitting parent issues
- claiming and assigning issues
- writing implementation notes
- preparing agent run context

## Large Project Context Goal

For large projects, AI Plan Issue should act as a context coordination system,
not only a task board. Plan documents capture intent and constraints; milestones
group delivery slices; modules map product or architecture domains; parent issues
provide stable context boundaries; child issues define executable units;
dependencies preserve sequencing; comments and activity preserve local decisions.

Agent tools should be able to load that layered context before code edits so
multiple agents can coordinate without re-reading the whole repository or losing
why a step exists.

## Acceptance

- Existing CLI behavior remains compatible.
- `ai_plan_issue.cli.main` is the entrypoint used by tests and console scripts.
- `ledger.py` no longer contains `cmd_*`, `build_parser`, `main`, `emit_event`, `append_activity_db`, `realtime_update_presence`, `realtime_list_presence`, `realtime_events_since`, `realtime_export`, `connect_db`, `init_realtime_db`, `realtime_issue_count`, `issue_from_row`, `issue_rows`, `realtime_index`, `load_index`, `save_index`, `issue_dir`, `append_jsonl`, `append_activity`, `read_jsonl`, `ensure_issue_files`, `refresh_board`, `slugify`, `parse_tasks`, `latest_feature_dir`, `priority_for_group`, `module_for_group`, `category_for_group`, `task_group_key`, `next_parent_number`, `next_child_number`, `upsert_issue_db`, `import_ledger_to_db`, `export_db_to_ledger`, `ensure_realtime_store`, `realtime_load_index`, `realtime_find_issue`, `check_expected_revision`, `realtime_load_issue_detail`, `realtime_update_issue_fields`, `realtime_append_comment`, `realtime_create_manual_issue`, `realtime_split_issue`, `realtime_claim_issue`, `realtime_assign_issue`, `realtime_update_implementation_notes`, or `realtime_prepare_run`.
- Core modules do not import the `ledger.py` facade.
- Source and vendored Codex plugin runtime stay byte-for-byte aligned except ignored caches.
- Full test suite and syntax checks pass.
