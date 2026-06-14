# AI Plan Issue v1.0.1 Stabilization Plan

## Goal

Ship a safer v1.0.1 release after the public v1.0.0 baseline. This release focuses on agent-tool reliability and release hygiene, not large architecture rewrites.

## Scope

- Add HTTP integration tests for token-gated reads and writes.
- Add SSE resume coverage using `Last-Event-ID`.
- Reject empty issue PATCH requests so clients cannot create no-op revisions.
- Reject empty claim agents and non-positive claim TTL values.
- Align package, Codex plugin, and vendored runtime versions at `1.0.1`.
- Add GitHub Actions CI for Python tests, Python compilation, and browser JavaScript syntax checks.

## Out of Scope

- Splitting `ledger.py` into smaller modules.
- Cloud hosting, OAuth, Postgres, or public internet deployment.
- Removing the optional Spec Kit compatibility layer.

## Acceptance

- `python -m pytest tests` passes.
- `python -m py_compile src/ai_plan_issue/ledger.py src/ai_plan_issue/board_server.py src/ai_plan_issue/cli.py` passes.
- `node --check src/ai_plan_issue/web/app.js` passes.
- `plugins/codex/scripts/ai_plan_issue.sh --help` lists `run` and `note`.
- No local absolute paths, project tokens, Bearer tokens, or private key material are present in tracked files.
