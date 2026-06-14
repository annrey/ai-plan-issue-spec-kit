# Architecture

AI Plan Issue has nine layers:

1. `src/ai_plan_issue/planning.py`
   - Parses checklist tasks.
   - Infers issue priority, category, module, and grouping.
   - Owns slug and issue-number helper rules.

2. `src/ai_plan_issue/store.py`
   - Resolves project-local state paths.
   - Owns token and database paths.
   - Opens SQLite connections and initializes schema.
   - Converts database rows into issue dictionaries.

3. `src/ai_plan_issue/exporter.py`
   - Reads and writes Markdown, JSON, and JSONL ledger files.
   - Creates issue directories and issue Markdown.
   - Refreshes the human-readable board export.

4. `src/ai_plan_issue/runtime.py`
   - Bootstraps the realtime SQLite state from file ledgers.
   - Exports realtime state back to Markdown and JSONL.
   - Owns realtime read helpers, issue detail loading, and revision conflict checks.

5. `src/ai_plan_issue/ledger.py`
   - Coordinates issue generation from parsed tasks.
   - Creates parent and child issues.
   - Owns issue/comment mutations, claims, and assignment.

6. `src/ai_plan_issue/events.py`
   - Writes SSE event records.
   - Writes activity records.
   - Owns presence state and event replay helpers.

7. `src/ai_plan_issue/cli.py`
   - Builds the command-line parser.
   - Maps CLI commands to ledger operations.
   - Owns machine-readable JSON error output and CLI exit codes.

8. `src/ai_plan_issue/board_server.py`
   - Serves the board UI.
   - Exposes `/api/v1/*`.
   - Pushes updates with Server-Sent Events.
   - Enforces project token auth.

9. `src/ai_plan_issue/web/`
   - Browser board UI.
   - Reads REST APIs and subscribes to `/api/v1/events`.
   - Shows workflow columns, issue hierarchy, details, comments, activity, claim, and assignment state.

Default state root is `.ai-plan-issue/`. Set `AI_PLAN_ISSUE_DIR` to override it.

For large projects, the plan, milestone, module, parent issue, child issue,
dependency, comment, and activity records are also a context coordination layer.
Agents should treat them as the project map before editing code: plan documents
hold intent, milestones define delivery slices, parent issues define domain
boundaries, child issues define executable steps, and activity/comments preserve
local decisions that are expensive to rediscover.
