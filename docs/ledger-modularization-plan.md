# Ledger Modularization Plan

## Goal

Reduce `src/ai_plan_issue/ledger.py` from an all-in-one module into smaller surfaces that are safer for future agent-tool expansion.

## Current Cut

This pass moves command-line parsing and command handlers into `src/ai_plan_issue/cli.py`.

The ledger module remains responsible for:

- issue parsing and generation
- project state paths
- SQLite storage
- Markdown and JSONL export
- realtime mutation functions
- event and presence helpers

The CLI module becomes responsible for:

- `argparse` parser construction
- command handler functions
- machine-readable CLI error mapping
- `main(argv)`

## Acceptance

- Existing CLI behavior remains compatible.
- `ai_plan_issue.cli.main` is the entrypoint used by tests and console scripts.
- `ledger.py` no longer contains `cmd_*`, `build_parser`, or `main`.
- Source and vendored Codex plugin runtime stay byte-for-byte aligned except ignored caches.
- Full test suite and syntax checks pass.
