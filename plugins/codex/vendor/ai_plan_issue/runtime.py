"""Realtime SQLite runtime bootstrap and read helpers."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import uuid4

from . import events, exporter, store


SCHEMA_VERSION = store.SCHEMA_VERSION


class ConflictError(RuntimeError):
    """Raised when a realtime write targets a stale issue revision."""


def now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def find_issue(index: dict, issue_id: str) -> dict:
    for issue in index.get("issues", []):
        if issue.get("id") == issue_id:
            return issue
    raise KeyError(f"Issue not found: {issue_id}")


def upsert_issue_db(conn: sqlite3.Connection, issue: dict) -> None:
    revision = int(issue.get("revision", 1))
    issue["revision"] = revision
    conn.execute(
        """
        INSERT INTO issues (id, data, revision, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET data=excluded.data, revision=excluded.revision, updated_at=excluded.updated_at
        """,
        (issue["id"], store.json_dumps(issue), revision, now_iso()),
    )


def import_ledger_to_db(project_root: Path, force: bool = False) -> dict:
    store.init_realtime_db(project_root)
    with store.connect_db(project_root) as conn:
        if force:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM issues")
            conn.execute("DELETE FROM comments")
            conn.execute("DELETE FROM activity")
            conn.execute("DELETE FROM events")
            conn.execute("DELETE FROM presence")
        else:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT COUNT(*) AS count FROM issues").fetchone()
            if row and int(row["count"]) > 0:
                conn.execute("COMMIT")
                return store.realtime_index(project_root)

        index = exporter.load_index(project_root)
        for issue in index.get("issues", []):
            issue.setdefault("revision", 1)
            upsert_issue_db(conn, issue)
            directory = exporter.issue_dir(project_root, issue)
            for comment in exporter.read_jsonl(directory / "comments.jsonl"):
                comment.setdefault("id", f"com-{uuid4().hex[:12]}")
                comment.setdefault("ts", now_iso())
                comment.setdefault("author", "unknown")
                comment.setdefault("body", "")
                conn.execute(
                    """
                    INSERT OR IGNORE INTO comments (id, issue_id, ts, author, body, data)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        comment["id"],
                        issue["id"],
                        comment["ts"],
                        comment["author"],
                        comment["body"],
                        store.json_dumps(comment),
                    ),
                )
            for activity_entry in exporter.read_jsonl(directory / "activity.jsonl"):
                activity_entry.setdefault("id", f"act-{uuid4().hex[:12]}")
                activity_entry.setdefault("ts", now_iso())
                activity_entry.setdefault("author", "unknown")
                activity_entry.setdefault("action", "recorded")
                activity_entry.setdefault("body", "")
                conn.execute(
                    """
                    INSERT OR IGNORE INTO activity (id, issue_id, ts, author, action, body, data)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        activity_entry["id"],
                        issue["id"],
                        activity_entry["ts"],
                        activity_entry["author"],
                        activity_entry["action"],
                        activity_entry["body"],
                        store.json_dumps(activity_entry),
                    ),
                )
        events.emit_event(conn, "board.exported", "system", None, None, {"mode": "import", "issues": len(index["issues"])})
        conn.execute("COMMIT")
    export_db_to_ledger(project_root)
    return store.realtime_index(project_root)


def export_db_to_ledger(project_root: Path) -> dict:
    store.init_realtime_db(project_root)
    index = store.realtime_index(project_root)
    store.issues_root(project_root).mkdir(parents=True, exist_ok=True)
    exporter.save_index(project_root, index)
    exporter.refresh_board(project_root, index)
    with store.connect_db(project_root) as conn:
        for issue in index.get("issues", []):
            exporter.ensure_issue_files(project_root, issue, issue.get("summary") or issue["title"])
            exporter.sync_issue_markdown_metadata(project_root, issue)
            directory = exporter.issue_dir(project_root, issue)
            comment_rows = conn.execute(
                "SELECT data FROM comments WHERE issue_id = ? ORDER BY ts, id",
                (issue["id"],),
            ).fetchall()
            activity_rows = conn.execute(
                "SELECT data FROM activity WHERE issue_id = ? ORDER BY ts, id",
                (issue["id"],),
            ).fetchall()
            (directory / "comments.jsonl").write_text(
                "".join(row["data"] + "\n" for row in comment_rows),
                encoding="utf-8",
            )
            (directory / "activity.jsonl").write_text(
                "".join(row["data"] + "\n" for row in activity_rows),
                encoding="utf-8",
            )
    return index


def ensure_realtime_store(project_root: Path) -> dict:
    store.init_realtime_db(project_root)
    store.get_project_token(project_root)
    if (
        store.realtime_issue_count(project_root) == 0
        and store.index_path(project_root).exists()
        and exporter.load_index(project_root).get("issues")
    ):
        return import_ledger_to_db(project_root, force=False)
    if not store.index_path(project_root).exists():
        export_db_to_ledger(project_root)
    return store.realtime_index(project_root)


def realtime_load_index(project_root: Path) -> dict:
    ensure_realtime_store(project_root)
    return store.realtime_index(project_root)


def realtime_find_issue(project_root: Path, issue_id: str, conn: sqlite3.Connection | None = None) -> dict:
    close_conn = conn is None
    conn = conn or store.connect_db(project_root)
    try:
        row = conn.execute("SELECT data, revision FROM issues WHERE id = ?", (issue_id,)).fetchone()
        if not row:
            raise KeyError(f"Issue not found: {issue_id}")
        return store.issue_from_row(row)
    finally:
        if close_conn:
            conn.close()


def check_expected_revision(issue: dict, expected_revision: int | None) -> None:
    if expected_revision is None:
        return
    current = int(issue.get("revision", 1))
    if int(expected_revision) != current:
        raise ConflictError(f"Stale issue revision for {issue['id']}: expected {expected_revision}, current {current}")


def realtime_load_issue_detail(project_root: Path, issue_id: str) -> dict:
    ensure_realtime_store(project_root)
    issue = realtime_find_issue(project_root, issue_id)
    directory = exporter.issue_dir(project_root, issue)
    with store.connect_db(project_root) as conn:
        comments = [
            json.loads(row["data"])
            for row in conn.execute("SELECT data FROM comments WHERE issue_id = ? ORDER BY ts, id", (issue_id,))
        ]
        activity_entries = [
            json.loads(row["data"])
            for row in conn.execute("SELECT data FROM activity WHERE issue_id = ? ORDER BY ts, id", (issue_id,))
        ]
    return {
        "issue": issue,
        "issue_md": (directory / "issue.md").read_text(encoding="utf-8") if (directory / "issue.md").exists() else "",
        "implementation_md": (directory / "implementation.md").read_text(encoding="utf-8")
        if (directory / "implementation.md").exists()
        else "",
        "comments": comments,
        "activity": activity_entries,
    }
