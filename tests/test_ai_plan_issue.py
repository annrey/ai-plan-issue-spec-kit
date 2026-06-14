from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from ai_plan_issue import cli
from ai_plan_issue import events
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


def test_external_state_dir_is_rejected_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outside = tmp_path.parent / "outside-state"
    monkeypatch.setenv("AI_PLAN_ISSUE_DIR", str(outside))

    with pytest.raises(ValueError, match="outside project root"):
        ledger.issues_root(tmp_path)


def test_force_never_deletes_project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tasks = tmp_path / "tasks.md"
    keep = tmp_path / "keep.txt"
    tasks.write_text(TASKS_MD, encoding="utf-8")
    keep.write_text("do not delete", encoding="utf-8")
    monkeypatch.setenv("AI_PLAN_ISSUE_DIR", ".")

    with pytest.raises(ValueError, match="refusing to use project root"):
        ledger.generate_issues(tmp_path, None, force=True, tasks_file=tasks)

    assert keep.read_text(encoding="utf-8") == "do not delete"


def test_issue_path_traversal_is_rejected(tmp_path: Path) -> None:
    issue = {"id": "AI-999", "slug": "escape", "path": "../escape"}

    with pytest.raises(ValueError, match="Unsafe issue path"):
        ledger.issue_dir(tmp_path, issue)


def test_implementation_note_updates_detail_and_revision(tmp_path: Path) -> None:
    tasks = tmp_path / "tasks.md"
    tasks.write_text(TASKS_MD, encoding="utf-8")
    ledger.generate_issues(tmp_path, None, force=True, tasks_file=tasks)
    ledger.import_ledger_to_db(tmp_path, force=True)

    before = ledger.realtime_find_issue(tmp_path, "AI-001-01")
    updated = ledger.realtime_update_implementation_notes(
        tmp_path,
        "AI-001-01",
        "Changed files:\n- src/example.py",
        author="codex-local",
        expected_revision=before["revision"],
    )

    assert updated["revision"] == before["revision"] + 1
    detail = ledger.realtime_load_issue_detail(tmp_path, "AI-001-01")
    assert "Changed files:" in detail["implementation_md"]
    assert "src/example.py" in detail["implementation_md"]


def test_prepare_run_claims_issue_and_returns_context(tmp_path: Path) -> None:
    tasks = tmp_path / "tasks.md"
    tasks.write_text(TASKS_MD, encoding="utf-8")
    ledger.generate_issues(tmp_path, None, force=True, tasks_file=tasks)
    ledger.import_ledger_to_db(tmp_path, force=True)

    context = ledger.realtime_prepare_run(tmp_path, "AI-001-01", agent="codex-local", ttl_minutes=30)

    assert context["issue"]["id"] == "AI-001-01"
    assert context["issue"]["claimed_by"] == "codex-local"
    assert context["protocol"]["next_steps"][0] == "Read issue_md and implementation_md before editing code."


def test_cli_json_error_contract(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    exit_code = cli.main(["detail", "--project-root", str(tmp_path), "--json", "AI-404"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 4
    assert payload["ok"] is False
    assert payload["error"]["code"] == "not_found"
    assert "AI-404" in payload["error"]["message"]


def test_cli_json_claim_conflict_contract(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    tasks = tmp_path / "tasks.md"
    tasks.write_text(TASKS_MD, encoding="utf-8")
    ledger.generate_issues(tmp_path, None, force=True, tasks_file=tasks)
    ledger.import_ledger_to_db(tmp_path, force=True)
    ledger.realtime_claim_issue(tmp_path, "AI-001-01", "agent-a", ttl_minutes=30)

    exit_code = cli.main(
        [
            "claim",
            "--project-root",
            str(tmp_path),
            "--json",
            "--agent",
            "agent-b",
            "AI-001-01",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 3
    assert payload["ok"] is False
    assert payload["error"]["code"] == "conflict"
    assert "already claimed by agent-a" in payload["error"]["message"]


def test_cli_entrypoint_is_separate_from_ledger() -> None:
    root = Path(__file__).resolve().parents[1]
    ledger_source = (root / "src" / "ai_plan_issue" / "ledger.py").read_text(encoding="utf-8")
    cli_source = (root / "src" / "ai_plan_issue" / "cli.py").read_text(encoding="utf-8")

    assert "def cmd_" not in ledger_source
    assert "def build_parser" not in ledger_source
    assert "def main(" not in ledger_source
    assert "def build_parser" in cli_source
    assert "def main(" in cli_source


def test_event_runtime_is_separate_from_ledger() -> None:
    root = Path(__file__).resolve().parents[1]
    ledger_source = (root / "src" / "ai_plan_issue" / "ledger.py").read_text(encoding="utf-8")
    events_source = (root / "src" / "ai_plan_issue" / "events.py").read_text(encoding="utf-8")

    assert "def emit_event" not in ledger_source
    assert "def append_activity_db" not in ledger_source
    assert "def realtime_update_presence" not in ledger_source
    assert "def realtime_list_presence" not in ledger_source
    assert "def realtime_events_since" not in ledger_source
    assert "def realtime_export" not in ledger_source
    assert "def emit_event" in events_source
    assert "def realtime_events_since" in events_source
    assert callable(events.realtime_events_since)


def test_codex_plugin_runs_when_copied_without_repository_root(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "plugins" / "codex"
    plugin = tmp_path / "codex-plugin"
    shutil.copytree(source, plugin)

    result = subprocess.run(
        [str(plugin / "scripts" / "ai_plan_issue.sh"), "--help"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Manage the AI Plan Issue ledger" in result.stdout
