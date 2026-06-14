---
description: "Append a persistent comment to an AI plan issue"
---

# Comment On AI Plan Issue

## User Input

```text
$ARGUMENTS
```

Expected shape:

```text
ISSUE_ID comment text...
```

Optional:

```text
--author codex-local ISSUE_ID comment text...
```

## Steps

1. Parse the target issue id and comment body from the user input.
2. Append the comment:

   ```bash
   sh .specify/extensions/ai-plan-issue/scripts/sh/ai_plan_issue.sh comment $ARGUMENTS
   ```

3. If the comment changes scope, dependencies, priority, or acceptance criteria, recommend running `/speckit.ai-plan-issue.refine ISSUE_ID`.

Use `--expected-revision <n>` when commenting from a loaded issue snapshot. The command writes to the SQLite realtime store, emits realtime events, and exports the append-only `comments.jsonl` ledger.

## Done When

- The target issue's `comments.jsonl` has a new append-only entry.
- The board summary is refreshed.
