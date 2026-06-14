---
description: "Assign an AI plan issue to a human or agent"
---

# Assign AI Plan Issue

## User Input

```text
$ARGUMENTS
```

Expected shape:

```text
ISSUE_ID ASSIGNEE_ID
```

## Steps

Run:

```bash
sh .specify/extensions/ai-plan-issue/scripts/sh/ai_plan_issue.sh assign $ARGUMENTS
```

Assignment is a planning signal. It does not claim the issue for active work; use `/speckit.ai-plan-issue.claim` before execution.

Use `--expected-revision <n>` when assigning from a loaded issue snapshot. The command writes to the SQLite realtime store and exports `.specify/issues/index.json`, `board.md`, and the issue files.

## Done When

- `assignee` is updated in `.specify/issues/index.json`.
- Activity is appended to the issue.
