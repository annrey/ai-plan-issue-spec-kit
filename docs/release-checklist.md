# Release Checklist

- [ ] `python -m py_compile src/ai_plan_issue/ledger.py src/ai_plan_issue/board_server.py`
- [ ] `PYTHONPATH=src python -m ai_plan_issue.cli --help`
- [ ] Generate issues from a sample `tasks.md`.
- [ ] Verify `ai-plan-issue run`, `note`, `status`, and JSON error output.
- [ ] Start the board and verify `/api/v1/session`.
- [ ] Confirm `.ai-plan-issue/` is ignored.
- [ ] Scan for local absolute paths and token-like secrets.
- [ ] Scan for unexpected upstream framework files.
- [ ] Confirm GitHub repository visibility before publishing.
