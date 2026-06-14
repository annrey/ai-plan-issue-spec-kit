"""Realtime events, activity records, and presence helpers."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from . import store


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def json_dumps(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def emit_event(
    conn: sqlite3.Connection,
    event_type: str,
    actor: str,
    issue_id: str | None,
    revision: int | None,
    payload: dict,
) -> dict:
    event = {
        "id": f"evt-{uuid4().hex[:12]}",
        "ts": now_iso(),
        "actor": actor,
        "issue_id": issue_id,
        "revision": revision,
        "payload": payload,
        "type": event_type,
    }
    conn.execute(
        """
        INSERT INTO events (id, event_type, ts, actor, issue_id, revision, payload)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event["id"],
            event_type,
            event["ts"],
            actor,
            issue_id,
            revision,
            json_dumps(payload),
        ),
    )
    return event


def append_activity_db(
    conn: sqlite3.Connection,
    issue: dict,
    action: str,
    body: str,
    author: str = "system",
) -> dict:
    payload = {
        "id": f"act-{uuid4().hex[:12]}",
        "ts": now_iso(),
        "author": author,
        "action": action,
        "body": body,
    }
    conn.execute(
        """
        INSERT INTO activity (id, issue_id, ts, author, action, body, data)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload["id"],
            issue["id"],
            payload["ts"],
            author,
            action,
            body,
            json_dumps(payload),
        ),
    )
    emit_event(conn, "activity.created", author, issue["id"], int(issue.get("revision", 1)), payload)
    return payload


def realtime_update_presence(
    project_root: Path,
    actor: str,
    display_name: str,
    kind: str = "human",
    issue_id: str | None = None,
) -> dict:
    from . import runtime

    runtime.ensure_realtime_store(project_root)
    payload = {
        "actor": actor,
        "display_name": display_name or actor,
        "kind": kind,
        "issue_id": issue_id,
        "updated_at": now_iso(),
    }
    with store.connect_db(project_root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            INSERT INTO presence (actor, display_name, kind, issue_id, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(actor) DO UPDATE SET
              display_name=excluded.display_name,
              kind=excluded.kind,
              issue_id=excluded.issue_id,
              updated_at=excluded.updated_at
            """,
            (actor, payload["display_name"], kind, issue_id, payload["updated_at"]),
        )
        emit_event(conn, "presence.updated", actor, issue_id, None, payload)
        conn.execute("COMMIT")
    return payload


def realtime_list_presence(project_root: Path, max_age_seconds: int = 180) -> list[dict]:
    from . import runtime

    runtime.ensure_realtime_store(project_root)
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
    actors: list[dict] = []
    with store.connect_db(project_root) as conn:
        rows = conn.execute("SELECT * FROM presence ORDER BY updated_at DESC").fetchall()
    for row in rows:
        updated = parse_iso(row["updated_at"])
        if updated and updated >= cutoff:
            actors.append(
                {
                    "actor": row["actor"],
                    "display_name": row["display_name"],
                    "kind": row["kind"],
                    "issue_id": row["issue_id"],
                    "updated_at": row["updated_at"],
                }
            )
    return actors


def realtime_events_since(project_root: Path, last_event_id: str | None = None, limit: int = 100) -> list[dict]:
    from . import runtime

    runtime.ensure_realtime_store(project_root)
    with store.connect_db(project_root) as conn:
        since_seq = 0
        if last_event_id:
            row = conn.execute("SELECT seq FROM events WHERE id = ?", (last_event_id,)).fetchone()
            if row:
                since_seq = int(row["seq"])
        rows = conn.execute(
            """
            SELECT id, event_type, ts, actor, issue_id, revision, payload
            FROM events
            WHERE seq > ?
            ORDER BY seq
            LIMIT ?
            """,
            (since_seq, limit),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "type": row["event_type"],
            "ts": row["ts"],
            "actor": row["actor"],
            "issue_id": row["issue_id"],
            "revision": row["revision"],
            "payload": json.loads(row["payload"]),
        }
        for row in rows
    ]


def realtime_export(project_root: Path, author: str = "system") -> dict:
    from . import runtime

    index = runtime.export_db_to_ledger(project_root)
    with store.connect_db(project_root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        emit_event(conn, "board.exported", author, None, None, {"mode": "export", "issues": len(index["issues"])})
        conn.execute("COMMIT")
    return index
