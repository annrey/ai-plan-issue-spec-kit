---
description: "Start the local AI plan issue web board"
---

# Open AI Plan Issue Web Board

## User Input

```text
$ARGUMENTS
```

Optional arguments are passed to the board server, for example:

```text
--port 8765
```

## Steps

1. Ensure `.specify/issues/index.json` exists. If not, run `/speckit.ai-plan-issue.generate` first.
2. Start the board server:

   ```bash
   sh .specify/extensions/ai-plan-issue/scripts/sh/board_server.sh $ARGUMENTS
   ```

3. Open the printed authenticated URL when the browser should write issue updates:

   ```text
   Authenticated URL: http://127.0.0.1:<port>/?token=<project-token>
   ```

   Localhost reads can use the plain URL. Browser writes, agent writes, and LAN access require the project token.

## Done When

- The local board is running.
- The realtime SQLite store is available at `.specify/issues/ai-plan-issue.db`.
- The user can view columns, open issue details, add comments, change status, create issues, see online actors, and copy agent commands.
