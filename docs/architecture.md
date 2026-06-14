# Architecture

AI Plan Issue has three layers:

1. `src/ai_plan_issue/ledger.py`
   - Parses `tasks.md`.
   - Creates parent and child issues.
   - Owns SQLite schema, JSONL comments, JSONL activity, exports, claims, assignment, and revision conflicts.

2. `src/ai_plan_issue/board_server.py`
   - Serves the board UI.
   - Exposes `/api/v1/*`.
   - Pushes updates with Server-Sent Events.
   - Enforces project token auth.

3. `src/ai_plan_issue/web/`
   - Browser board UI.
   - Reads REST APIs and subscribes to `/api/v1/events`.
   - Shows workflow columns, issue hierarchy, details, comments, activity, claim, and assignment state.

Default state root is `.ai-plan-issue/`. Set `AI_PLAN_ISSUE_DIR` to override it.

