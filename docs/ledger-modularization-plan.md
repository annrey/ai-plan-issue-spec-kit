# Ledger Modularization Plan

## Goal

Reduce `src/ai_plan_issue/ledger.py` from an all-in-one module into smaller surfaces that are safer for future agent-tool expansion.

## Current Cut

The first pass moved command-line parsing and command handlers into `src/ai_plan_issue/cli.py`.

This pass moves event, activity, presence, and event replay helpers into `src/ai_plan_issue/events.py`.

The ledger module remains responsible for:

- issue parsing and generation
- project state paths
- SQLite storage
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

## Acceptance

- Existing CLI behavior remains compatible.
- `ai_plan_issue.cli.main` is the entrypoint used by tests and console scripts.
- `ledger.py` no longer contains `cmd_*`, `build_parser`, `main`, `emit_event`, `append_activity_db`, `realtime_update_presence`, `realtime_list_presence`, `realtime_events_since`, or `realtime_export`.
- Source and vendored Codex plugin runtime stay byte-for-byte aligned except ignored caches.
- Full test suite and syntax checks pass.
