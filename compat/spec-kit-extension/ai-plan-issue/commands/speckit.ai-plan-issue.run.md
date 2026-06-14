---
description: "Run development for one AI plan issue using the issue protocol"
---

# Run AI Plan Issue

## User Input

```text
$ARGUMENTS
```

Expected shape:

```text
ISSUE_ID optional implementation guidance
```

## Required AI Protocol

You MUST NOT start coding until you have read:

- `.specify/issues/index.json`
- the target issue's `issue.md`
- the target issue's `comments.jsonl`
- the target issue's `activity.jsonl`
- the parent issue if `parent_id` exists
- all incomplete dependency issues in `depends_on`
- source `spec.md`, `plan.md`, and `tasks.md` when referenced by the issue source
- `.specify/memory/constitution.md` if it exists

## Steps

1. Claim the issue unless it is already safely claimed by you:

   ```bash
   sh .specify/extensions/ai-plan-issue/scripts/sh/ai_plan_issue.sh claim --agent codex-local ISSUE_ID
   ```

2. If dependencies are incomplete, set status to `blocked`, append a comment, and stop.
3. Implement only the scoped issue. If scope is too large or crosses modules, split or refine before coding.
4. Run focused validation relevant to the issue.
5. Write or update the target issue's `implementation.md` with:
   - files changed
   - behavior implemented
   - validation performed
   - residual risks or follow-up issues
6. Update status to `in_review` when implementation is ready for human or review-agent validation.
7. Append activity for every major state transition.

When the issue detail you read includes `revision`, pass it with `--expected-revision` on status, claim, assign, and comment writes. If the command exits non-zero because the revision is stale, reload the issue detail and reconcile the new comments/activity before continuing.

## Done When

- Code changes are scoped to the claimed issue.
- The issue status, activity, and implementation report are current.
- Any follow-up work is captured as child issues or comments.
