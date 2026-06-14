# Context Coordination for Large Projects

AI Plan Issue should coordinate development context for large projects, not only
track task status.

## Context Layers

1. Plan documents define product intent, constraints, architecture direction,
   and acceptance boundaries.
2. Milestones define delivery slices that can be reviewed independently.
3. Modules define product or codebase domains.
4. Parent issues define stable context boundaries for a feature, subsystem, or
   workstream.
5. Child issues define executable steps that one human or agent can claim.
6. Dependencies define safe sequencing and unblock relationships.
7. Comments preserve discussion and corrections.
8. Activity records preserve what changed, when, and by which actor.
9. Implementation notes preserve code decisions, touched files, validation, and
   residual risk.

## Agent Context Contract

Before editing code, an agent should load:

- the active plan or design document
- the target issue
- the parent issue when present
- child issues when the target is a parent issue
- dependencies and blockers
- comments and activity
- implementation notes
- related milestone and module context

The goal is to let multiple agents coordinate through explicit project context
instead of reconstructing intent from the repository every time.

## Future Tool Surface

A future agent tool should expose a single context bundle command, for example:

```bash
ai-plan-issue context ISSUE_ID --include plan,milestone,parent,children,dependencies,comments,activity,implementation
```

The response should be machine-readable JSON by default, with paths to the
human-readable Markdown records. This keeps the same source of truth usable by
Codex, Claude Code, local scripts, and human reviewers.
