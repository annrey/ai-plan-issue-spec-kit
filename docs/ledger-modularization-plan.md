# Ledger Modularization Plan

## Goal

Reduce `src/ai_plan_issue/ledger.py` from an all-in-one module into smaller surfaces that are safer for future agent-tool expansion.

## Current Cut

The first pass moved command-line parsing and command handlers into `src/ai_plan_issue/cli.py`.

This pass moves event, activity, presence, and event replay helpers into `src/ai_plan_issue/events.py`.

The current pass moves project state paths, token paths, SQLite connection setup, schema initialization, row conversion, and realtime index helpers into `src/ai_plan_issue/store.py`.

The ledger module remains responsible for:

- issue parsing and generation
- Markdown and JSONL export
- realtime mutation functions

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

## Acceptance

- Existing CLI behavior remains compatible.
- `ai_plan_issue.cli.main` is the entrypoint used by tests and console scripts.
- `ledger.py` no longer contains `cmd_*`, `build_parser`, `main`, `emit_event`, `append_activity_db`, `realtime_update_presence`, `realtime_list_presence`, `realtime_events_since`, `realtime_export`, `connect_db`, `init_realtime_db`, `realtime_issue_count`, `issue_from_row`, `issue_rows`, or `realtime_index`.
- Source and vendored Codex plugin runtime stay byte-for-byte aligned except ignored caches.
- Full test suite and syntax checks pass.
