---
name: ai-plan-issue
description: Use when a user asks Codex to turn a large goal, feature plan, or project plan into collaborative issues; open or manage the AI Plan Issue board; claim/run an issue; or coordinate human and AI development through issue comments, status, and activity.
---

# AI Plan Issue

AI Plan Issue makes Codex work from a persistent issue tree instead of jumping straight from a broad request into code. Use this skill for large development goals, project plans, issue-board collaboration, or requests to open/run/update the AI Plan Issue board.

## Project Detection

1. Work from the user's current project root.
2. Prefer a directory containing `.ai-plan-issue/`, `tasks.md`, `docs/tasks.md`, or source files for the target project.
3. Use `AI_PLAN_ISSUE_PROJECT_ROOT=/path/to/project` when the plugin wrapper is launched from outside the target project.
4. If no issue ledger exists yet, generate one from `tasks.md` or create parent/child issues from the user's stated goal.

## Commands

Use the wrapper scripts in this plugin:

```bash
plugins/codex/scripts/ai_plan_issue.sh generate
plugins/codex/scripts/ai_plan_issue.sh claim --agent codex-local AI-001
plugins/codex/scripts/ai_plan_issue.sh detail AI-001
plugins/codex/scripts/board_server.sh --port 8768
```

The board server prints both a normal URL and an authenticated URL. Open the authenticated URL when browser write actions are needed.

Agent write commands use the SQLite realtime store and export back to Markdown/JSONL after each mutation. When acting from a previously loaded issue detail, include the known revision:

```bash
plugins/codex/scripts/ai_plan_issue.sh status --author codex-local --expected-revision 3 AI-001 in_review
plugins/codex/scripts/ai_plan_issue.sh comment --author codex-local --expected-revision 4 AI-001 "Ready for review."
```

A stale `--expected-revision` exits non-zero; reload the issue detail before retrying. Omit the expected revision only when deliberately acting as an agent CLI that accepts latest-write semantics.

When invoking the plugin wrapper from outside the target project directory, set `AI_PLAN_ISSUE_PROJECT_ROOT=/path/to/project` so the SQLite database and exported issue files are resolved from the intended project.

## Execution Protocol

Before editing code for a large request:

1. Generate or refresh issues from `tasks.md` when needed.
2. Select a concrete issue, not just a broad goal.
3. Read the issue detail, parent issue, dependencies, comments, activity, source `spec.md`, source `plan.md`, source `tasks.md`, and project guidance when present.
4. Claim the issue before implementation.
5. Keep edits scoped to the issue and its acceptance criteria.
6. After work, update status, comments/activity, and implementation notes.

For multi-agent work, do not overwrite another active claim unless the user explicitly asks for a force claim.
