---
description: "Claim one AI plan issue for a human or agent"
---

# Claim AI Plan Issue

## User Input

```text
$ARGUMENTS
```

Expected shape:

```text
--agent codex-local ISSUE_ID
```

## Steps

Run:

```bash
sh .specify/extensions/ai-plan-issue/scripts/sh/ai_plan_issue.sh claim $ARGUMENTS
```

If the issue is already claimed by another active agent, stop and report the current claim instead of overwriting it.

Use `--expected-revision <n>` when the claim is based on a loaded issue snapshot. The command writes to the SQLite realtime store and exports the Markdown/JSONL ledger after the mutation.

## Done When

- `claimed_by` and `claim_expires_at` are updated.
- `activity.jsonl` records the claim.
