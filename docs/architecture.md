# Architecture

AI Plan Issue has seven layers:

1. `src/ai_plan_issue/store.py`
   - Resolves project-local state paths.
   - Owns token and database paths.
   - Opens SQLite connections and initializes schema.
   - Converts database rows into issue dictionaries.

2. `src/ai_plan_issue/exporter.py`
   - Reads and writes Markdown, JSON, and JSONL ledger files.
   - Creates issue directories and issue Markdown.
   - Refreshes the human-readable board export.

3. `src/ai_plan_issue/ledger.py`
   - Parses `tasks.md`.
   - Creates parent and child issues.
   - Owns issue/comment mutations, claims, assignment, and revision conflicts.

4. `src/ai_plan_issue/events.py`
   - Writes SSE event records.
   - Writes activity records.
   - Owns presence state and event replay helpers.

5. `src/ai_plan_issue/cli.py`
   - Builds the command-line parser.
   - Maps CLI commands to ledger operations.
   - Owns machine-readable JSON error output and CLI exit codes.

6. `src/ai_plan_issue/board_server.py`
   - Serves the board UI.
   - Exposes `/api/v1/*`.
   - Pushes updates with Server-Sent Events.
   - Enforces project token auth.

7. `src/ai_plan_issue/web/`
   - Browser board UI.
   - Reads REST APIs and subscribes to `/api/v1/events`.
   - Shows workflow columns, issue hierarchy, details, comments, activity, claim, and assignment state.

Default state root is `.ai-plan-issue/`. Set `AI_PLAN_ISSUE_DIR` to override it.
