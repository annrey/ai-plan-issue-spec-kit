---
description: "Split a large AI plan issue into child issues"
---

# Split AI Plan Issue

## User Input

```text
$ARGUMENTS
```

Expected shape:

```text
PARENT_ID "Child issue title" "Another child issue title"
```

## Steps

1. Read `.specify/issues/index.json`.
2. Read the parent issue's `issue.md`, `comments.jsonl`, and `activity.jsonl`.
3. Create child issues:

   ```bash
   sh .specify/extensions/ai-plan-issue/scripts/sh/ai_plan_issue.sh split $ARGUMENTS
   ```

   Use `--expected-parent-revision <n>` when splitting from a loaded parent snapshot.

4. Confirm:
   - parent `children` list was updated
   - child issue directories were created
   - split activity was appended to the parent

The command writes to the SQLite realtime store and exports the parent/child Markdown files, `index.json`, `board.md`, comments, and activity after the mutation.

## Done When

- The parent issue remains the module/epic boundary.
- New child issues are concrete, independently executable steps.
