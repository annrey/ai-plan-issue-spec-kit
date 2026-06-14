# AI Plan Issue Codex Plugin

This Codex plugin teaches Codex to work through AI Plan Issue: generate issue trees, open the realtime board, claim scoped work, and update status, comments, and activity after implementation.

## Runtime Model

- Source of truth: SQLite store under `.ai-plan-issue/ai-plan-issue.db`.
- Reviewable export: `.ai-plan-issue/index.json`, `board.md`, per-issue `issue.md`, `comments.jsonl`, and `activity.jsonl`.
- Web API: local board server with `/api/v1/*`, project token auth, and SSE events.
- Wrapper scripts call the standalone Python package in this repository.

## Commands

```bash
plugins/codex/scripts/ai_plan_issue.sh generate --tasks tasks.md
plugins/codex/scripts/board_server.sh --port 8768
plugins/codex/scripts/ai_plan_issue.sh claim --agent codex-local AI-001-01
plugins/codex/scripts/ai_plan_issue.sh status --author codex-local --expected-revision 1 AI-001-01 in_review
plugins/codex/scripts/ai_plan_issue.sh comment --author codex-local AI-001-01 "Ready for review."
```

Open the authenticated URL printed by the server to enable write actions from the browser.

When running the plugin wrapper from outside the target project, set `AI_PLAN_ISSUE_PROJECT_ROOT`:

```bash
AI_PLAN_ISSUE_PROJECT_ROOT=/path/to/project plugins/codex/scripts/ai_plan_issue.sh detail AI-001
```
