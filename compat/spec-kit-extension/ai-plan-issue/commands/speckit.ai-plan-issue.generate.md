---
description: "Generate collaborative AI plan issues from the active Spec Kit feature documents"
---

# Generate AI Plan Issues

## User Input

```text
$ARGUMENTS
```

## Behavior

Generate a persistent parent/child issue ledger from the active Spec Kit feature. This command should be run after `/speckit.tasks`.

## Steps

1. From the repository root, run:

   ```bash
   sh .specify/extensions/ai-plan-issue/scripts/sh/ai_plan_issue.sh generate $ARGUMENTS
   ```

2. Report:
   - generated issue count
   - generated parent issue count
   - generated child issue count
   - path to `.specify/issues/index.json`
   - path to `.specify/issues/board.md`

3. If generation fails because issues already exist, do not overwrite silently. Ask whether to re-run with `--force` or refine the existing issues.

## Done When

- `.specify/issues/index.json` exists.
- Parent and child issue directories exist.
- `board.md` summarizes the board.
- The user knows they can run `/speckit.ai-plan-issue.web` to open the board.
