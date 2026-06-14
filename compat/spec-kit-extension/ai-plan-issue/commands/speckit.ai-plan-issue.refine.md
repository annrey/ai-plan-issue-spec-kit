---
description: "Refine AI plan issues from comments, activity, and design documents"
---

# Refine AI Plan Issue

## User Input

```text
$ARGUMENTS
```

Expected shape:

```text
ISSUE_ID optional refinement instruction
```

## AI Protocol

When refining an issue, you MUST read:

- `.specify/issues/index.json`
- the target issue's `issue.md`
- the parent issue if `parent_id` exists
- dependency issues listed in `depends_on`
- `comments.jsonl`
- `activity.jsonl`
- the source feature `spec.md`, `plan.md`, and `tasks.md` when available

## Steps

1. Identify comments or activity that require issue changes.
2. Update the issue scope only when the change is grounded in:
   - user comments
   - design documents
   - implementation activity
   - discovered dependency gaps
3. If the issue is too large, run `/speckit.ai-plan-issue.split`.
4. If the issue is blocked, set status to `blocked` or `needs_review` and append a comment explaining the decision.

## Done When

- Important decisions are written into issue files, not only chat.
- `activity.jsonl` records what changed and why.
- Parent and child issue relationships remain consistent.

