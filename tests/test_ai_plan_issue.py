from __future__ import annotations

import json
from pathlib import Path

from ai_plan_issue import ledger


TASKS_MD = """# Tasks

## Phase 1: Board foundation

- [ ] T001 Create issue data model
- [ ] T002 Build local board server

## Phase 2: Agent workflow

- [ ] T003 Add claim command
"""


def test_generate_uses_standalone_state_dir(tmp_path: Path) -> None:
    tasks = tmp_path / "tasks.md"
    tasks.write_text(TASKS_MD, encoding="utf-8")

    index = ledger.generate_issues(tmp_path, None, force=True, tasks_file=tasks)
    ledger.import_ledger_to_db(tmp_path, force=True)

    assert (tmp_path / ".ai-plan-issue" / "index.json").exists()
    assert (tmp_path / ".ai-plan-issue" / "board.md").exists()
    assert (tmp_path / ".ai-plan-issue" / "ai-plan-issue.db").exists()
    assert len(index["issues"]) == 5
    assert {issue["issue_type"] for issue in index["issues"]} == {"parent", "step"}


def test_realtime_mutations_update_revision_and_exports(tmp_path: Path) -> None:
    tasks = tmp_path / "tasks.md"
    tasks.write_text(TASKS_MD, encoding="utf-8")
    ledger.generate_issues(tmp_path, None, force=True, tasks_file=tasks)
    ledger.import_ledger_to_db(tmp_path, force=True)

    issue = ledger.realtime_claim_issue(tmp_path, "AI-001-01", "codex-local", ttl_minutes=30)
    assert issue["status"] == "in_progress"
    assert issue["claimed_by"] == "codex-local"

    comment = ledger.realtime_append_comment(
        tmp_path,
        "AI-001-01",
        "Ready for review.",
        "codex-local",
        expected_revision=issue["revision"],
    )
    assert comment["body"] == "Ready for review."

    updated = ledger.realtime_update_issue_fields(
        tmp_path,
        "AI-001-01",
        {"status": "in_review"},
        author="codex-local",
    )
    assert updated["status"] == "in_review"

    exported = json.loads((tmp_path / ".ai-plan-issue" / "index.json").read_text(encoding="utf-8"))
    exported_issue = next(issue for issue in exported["issues"] if issue["id"] == "AI-001-01")
    assert exported_issue["status"] == "in_review"


def test_revision_conflict_is_rejected(tmp_path: Path) -> None:
    tasks = tmp_path / "tasks.md"
    tasks.write_text(TASKS_MD, encoding="utf-8")
    ledger.generate_issues(tmp_path, None, force=True, tasks_file=tasks)
    ledger.import_ledger_to_db(tmp_path, force=True)

    issue = ledger.realtime_claim_issue(tmp_path, "AI-001-01", "codex-local", ttl_minutes=30)

    try:
        ledger.realtime_append_comment(
            tmp_path,
            "AI-001-01",
            "stale",
            "codex-local",
            expected_revision=issue["revision"] - 1,
        )
    except ledger.ConflictError as exc:
        assert "stale issue revision" in str(exc).lower()
    else:
        raise AssertionError("Expected ConflictError")
