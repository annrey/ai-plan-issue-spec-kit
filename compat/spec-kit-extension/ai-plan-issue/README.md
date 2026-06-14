# AI Plan Issue Extension

AI Plan Issue turns Spec Kit feature documents into a collaborative issue ledger and local web board. It is designed for human and AI agent collaboration: design goals stay in `spec.md` and `plan.md`, while implementation work happens through parent and child issues under `.specify/issues/`.

## What It Adds

- Parent and child issue generation from `tasks.md`.
- A local Kanban-style web board for issue review, hierarchy navigation, and updates.
- Board categories, milestones, module filters, parent-child progress, and review/claimed filters.
- A realtime SQLite-backed board server with `/api/v1/*`, Server-Sent Events, and project token auth.
- Realtime CLI writes for agent commands, so Codex, Claude Code, and the web board mutate the same SQLite source.
- Persistent comments in `comments.jsonl`.
- Persistent activity in `activity.jsonl`.
- Agent collaboration fields such as `assignee`, `claimed_by`, `claim_expires_at`, and `revision`.
- Commands that Codex, Claude Code, and other Spec Kit integrations can use as skills.

## Commands

| Command | Purpose |
| --- | --- |
| `speckit.ai-plan-issue.generate` | Generate `.specify/issues/` from the active feature documents |
| `speckit.ai-plan-issue.comment` | Append a persistent comment to an issue |
| `speckit.ai-plan-issue.split` | Split a parent issue into child issues |
| `speckit.ai-plan-issue.refine` | Refine issue scope from comments and activity |
| `speckit.ai-plan-issue.run` | Execute one issue using the AI issue protocol |
| `speckit.ai-plan-issue.claim` | Claim one issue for an agent or human |
| `speckit.ai-plan-issue.assign` | Assign an issue to an agent or human |
| `speckit.ai-plan-issue.web` | Start the local web board |

## Data Layout

```text
.specify/issues/
├── index.json
├── board.md
├── 001-auth-foundation/
│   ├── issue.md
│   ├── comments.jsonl
│   ├── activity.jsonl
│   └── implementation.md
└── 001-01-create-user-model/
    ├── issue.md
    ├── comments.jsonl
    ├── activity.jsonl
    └── implementation.md
```

## AI Execution Rule

When this extension is active, AI agents should not jump straight into code. They should select or claim a concrete issue, read the design documents, read the parent and dependency issues, execute only the scoped work, and then update status, activity, and implementation notes.

## Local Web Board

Run:

```bash
sh .specify/extensions/ai-plan-issue/scripts/sh/board_server.sh
```

Then open the printed URL. The web board reads and writes `.specify/issues/` through a local HTTP server.

The board includes:

- Seven workflow columns: backlog, todo, in progress, blocked, needs review, in review, and done.
- Summary metrics for total issues, parent issues, child steps, active work, review work, blocked work, and done percentage.
- Module filtering and a left-side module list.
- Parent-child hierarchy navigation with progress indicators.
- Rich issue cards with issue type, category, milestone, source tasks, module, priority, parent linkage, and child count.
- A detail drawer with editable status, priority, category, assignee, module, relations, comments, activity, quick child creation, and a copyable run command.
- Live updates through `/api/v1/events` without refreshing the page.
- Online actor presence for humans and agents.

The server prints an authenticated URL such as:

```text
Authenticated URL: http://127.0.0.1:8768/?token=<project-token>
```

Open that URL when browser write actions are needed. Localhost reads do not require a token, but writes require the project token. LAN-bound boards require the token for reads and writes.

## Realtime Storage

The realtime board uses SQLite at `.specify/issues/ai-plan-issue.db`. The first server launch imports the existing file ledger when `.specify/issues/index.json` already exists. After every write, the server exports back to:

- `.specify/issues/index.json`
- `.specify/issues/board.md`
- per-issue `issue.md`
- per-issue `comments.jsonl`
- per-issue `activity.jsonl`

SQLite is the runtime state source. Markdown and JSONL remain the reviewable Spec Kit record.

The CLI uses the same realtime store for agent-facing writes:

```bash
sh .specify/extensions/ai-plan-issue/scripts/sh/ai_plan_issue.sh claim --agent codex-local AI-001-01
sh .specify/extensions/ai-plan-issue/scripts/sh/ai_plan_issue.sh status --author codex-local AI-001-01 in_review
sh .specify/extensions/ai-plan-issue/scripts/sh/ai_plan_issue.sh comment --author codex-local AI-001-01 "Ready for review."
sh .specify/extensions/ai-plan-issue/scripts/sh/ai_plan_issue.sh split --author codex-local AI-001 "Add missing validation step"
```

Use `--expected-revision <n>` on `status`, `comment`, `claim`, and `assign` when an agent is acting from a loaded issue snapshot. Use `--expected-parent-revision <n>` on `split`. A stale revision exits non-zero and leaves the issue unchanged.

## Codex Plugin

The repository also includes a Codex plugin wrapper under `plugins/ai-plan-issue/`. The plugin provides a Codex skill plus wrapper scripts that call the installed Spec Kit extension in a project, or this repository's bundled extension during development.

Validate it with:

```bash
python "$HOME/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py" plugins/ai-plan-issue
```

`plugins/ai-plan-issue/assets/screenshot-board.png` is generated from the running realtime board and is used by the Codex plugin manifest.

## Validation

Run the default extension and plugin checks:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/extensions/ai_plan_issue/test_ai_plan_issue_extension.py
node --check extensions/ai-plan-issue/web/app.js
python "$HOME/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py" plugins/ai-plan-issue
```

Run the localhost HTTP integration tests when socket access is available:

```bash
AI_PLAN_ISSUE_HTTP_TESTS=1 PYTHONPATH=src .venv/bin/python -m pytest tests/extensions/ai_plan_issue/test_ai_plan_issue_extension.py::TestRealtimeBoardServer
```

The shell launchers use `SPECIFY_PYTHON` when set, then project-local `.venv`, then a working system Python. Example:

```bash
SPECIFY_PYTHON=/path/to/python sh .specify/extensions/ai-plan-issue/scripts/sh/ai_plan_issue.sh generate
```

When a wrapper is launched from outside the target project, set `AI_PLAN_ISSUE_PROJECT_ROOT`:

```bash
AI_PLAN_ISSUE_PROJECT_ROOT=/path/to/project sh plugins/ai-plan-issue/scripts/ai_plan_issue.sh detail AI-001
```
