# Formal Release Readiness

## Target

The current repository is a stable local-first baseline at `1.0.1`. The next
formal release should be treated as one of two tracks:

- `1.0.2`: stabilization-only release, with no new user-facing protocol.
- `1.1.0`: formal agent-tool release, adding context coordination as a first
  class CLI/API surface.

Recommended target: `1.1.0`, because the project goal now includes large-project
context coordination for Codex, Claude Code, and other agents.

## Current Status

Completed:

- Standalone package with no runtime dependency on Spec Kit.
- Codex plugin wrapper with vendored runtime.
- Local/LAN board server with REST writes and SSE updates.
- SQLite realtime source of truth with Markdown/JSONL exports.
- Project token auth, revision conflict handling, and SSE resume tests.
- Modular runtime architecture:
  - `planning.py`
  - `store.py`
  - `exporter.py`
  - `runtime.py`
  - `mutations.py`
  - `file_mutations.py`
  - `events.py`
  - `cli.py`
  - `board_server.py`
  - `web/`
- Architecture tests prevent core modules from importing the `ledger.py` facade.
- Release metadata test aligns package, plugin, and vendored runtime versions.

## P0: Must Finish Before Formal Release

1. Add a first-class context bundle command.

   Required shape:

   ```bash
   ai-plan-issue context ISSUE_ID --include plan,milestone,parent,children,dependencies,comments,activity,implementation
   ```

   It should return machine-readable JSON with issue data, related issue
   summaries, comments, activity, implementation notes, and human-readable file
   paths. This is the main bridge from issue board to agent tool.

2. Add `/api/v1/issues/{id}/context`.

   The Web board and remote/local agents need the same context contract as the
   CLI. It should use the same serializer as the CLI command.

3. Document the data contract.

   Add a public schema document for:

   - issue fields
   - context bundle fields
   - comments/activity records
   - SSE events
   - revision conflict behavior
   - auth requirements

4. Add packaging validation.

   Required checks:

   - build wheel/sdist locally
   - install into a clean temporary environment
   - run `ai-plan-issue --help`
   - run `ai-plan-issue-board --help`
   - verify package data includes `web/index.html`, `web/app.js`, and
     `web/styles.css`

5. Add plugin install validation.

   Required checks:

   - plugin manifest parses
   - required plugin files exist
   - plugin wrapper runs using only `plugins/codex/vendor`
   - `skills/ai-plan-issue/SKILL.md` mentions context loading, claim, run,
     note, status, and comments

6. Run browser acceptance before tagging.

   Required checks:

   - start local board
   - open authenticated URL
   - render board at desktop width
   - render board at narrow width
   - create/comment/claim/assign/status update from browser
   - verify another client receives SSE update
   - verify console has no errors

7. Final security and privacy sweep.

   Required checks:

   - no runtime database or token files tracked
   - no local absolute paths
   - no Bearer tokens or long token-like strings
   - no private key material
   - no upstream Spec Kit source files accidentally reintroduced

## P1: Should Finish For a Strong Formal Release

1. Make CLI and server import lower-level modules directly where practical.

   `ledger.py` is now a compatibility facade. New code should prefer
   `runtime.py`, `mutations.py`, `file_mutations.py`, and `exporter.py`.

2. Add focused tests for context coordination.

   Cover:

   - parent context
   - child issue context
   - dependencies
   - comments/activity ordering
   - implementation notes
   - missing parent/dependency handling

3. Add API tests for all documented endpoints.

   Current tests cover auth, empty patch, invalid claim TTL, revision conflict,
   and SSE resume. Add direct coverage for create issue, assign, import, export,
   detail, and the future context endpoint.

4. Add release archive validation.

   Confirm a user can download a fresh GitHub archive, run scripts, generate
   issues, and start the board without local developer state.

5. Update README for context coordination.

   The README should explain the formal agent workflow:

   - plan goal
   - generate issues
   - load context bundle
   - claim issue
   - implement
   - note/status/comment

6. Add a versioned changelog.

   Keep `CHANGELOG.md` or `docs/changelog.md` with `1.0.1` and the next formal
   release entry.

## P2: Can Be Deferred

- Claude Code-specific plugin packaging.
- GitHub Issues bidirectional sync.
- OAuth/account system.
- Cloud service mode.
- Postgres backend.
- WebSocket transport.
- Drag-and-drop board edits.
- Rich dependency graph visualization.

## Recommended Release Gate

Before tagging the next formal release:

```bash
python -m pytest tests
python -m py_compile src/ai_plan_issue/planning.py src/ai_plan_issue/store.py src/ai_plan_issue/exporter.py src/ai_plan_issue/runtime.py src/ai_plan_issue/mutations.py src/ai_plan_issue/file_mutations.py src/ai_plan_issue/ledger.py src/ai_plan_issue/events.py src/ai_plan_issue/board_server.py src/ai_plan_issue/cli.py
node --check src/ai_plan_issue/web/app.js
plugins/codex/scripts/ai_plan_issue.sh --help
diff -ru --exclude __pycache__ src/ai_plan_issue plugins/codex/vendor/ai_plan_issue
```

Then run:

```bash
python -m build
```

from a clean environment, install the built wheel, and repeat CLI smoke tests.

## Release Decision

Use `1.0.2` only if the next release is a stabilization release. Use `1.1.0` if
the release includes the context bundle CLI/API, because that is a new agent-tool
capability and should be visible as a minor version bump.
