# Agent Protocol

When AI Plan Issue is active, agents should not jump directly from a broad request into code.

Required flow:

1. Read project guidance and relevant design docs.
2. Load the issue index.
3. Select a concrete issue.
4. Read the issue detail, parent issue, dependencies, comments, and activity.
5. Claim the issue.
6. Keep code changes scoped to the issue.
7. Add comments or mark the issue blocked when human input is required.
8. After implementation, update status, activity, and implementation notes.

Use `--expected-revision` when writing from a loaded issue snapshot.

Common commands:

```bash
ai-plan-issue run --agent codex-local AI-001-01
ai-plan-issue note --author codex-local AI-001-01 "Changed files, validation, and risks."
ai-plan-issue status --author codex-local AI-001-01 in_review
ai-plan-issue comment --author codex-local AI-001-01 "Ready for review."
```
