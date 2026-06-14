"""Realtime issue mutation operations."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from . import events, exporter, planning, runtime, store


SCHEMA_VERSION = store.SCHEMA_VERSION
DEFAULT_PREFIX = exporter.DEFAULT_PREFIX
VALID_STATUSES = {
    "backlog",
    "todo",
    "in_progress",
    "blocked",
    "needs_review",
    "in_review",
    "done",
}
VALID_PRIORITIES = {"P0", "P1", "P2", "P3", "none"}


def realtime_update_issue_fields(
    project_root: Path,
    issue_id: str,
    fields: dict,
    author: str = "system",
    expected_revision: int | None = None,
) -> dict:
    runtime.ensure_realtime_store(project_root)
    if not fields:
        raise ValueError("No editable issue fields provided.")
    with store.connect_db(project_root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        issue = runtime.realtime_find_issue(project_root, issue_id, conn)
        runtime.check_expected_revision(issue, expected_revision)
        before = {key: issue.get(key) for key in fields}
        for key, value in fields.items():
            if key == "status" and value not in VALID_STATUSES:
                raise ValueError(f"Invalid status: {value}")
            if key == "priority" and value not in VALID_PRIORITIES:
                raise ValueError(f"Invalid priority: {value}")
            issue[key] = value
        issue["revision"] = int(issue.get("revision", 1)) + 1
        runtime.upsert_issue_db(conn, issue)
        events.append_activity_db(conn, issue, "updated", f"Updated fields {sorted(fields)} from {before} to {fields}.", author)
        events.emit_event(conn, "issue.updated", author, issue_id, issue["revision"], issue)
        conn.execute("COMMIT")
    runtime.export_db_to_ledger(project_root)
    return issue


def realtime_append_comment(
    project_root: Path,
    issue_id: str,
    body: str,
    author: str,
    expected_revision: int | None = None,
) -> dict:
    runtime.ensure_realtime_store(project_root)
    if not body:
        raise ValueError("Comment body is required.")
    with store.connect_db(project_root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        issue = runtime.realtime_find_issue(project_root, issue_id, conn)
        runtime.check_expected_revision(issue, expected_revision)
        issue["revision"] = int(issue.get("revision", 1)) + 1
        runtime.upsert_issue_db(conn, issue)
        payload = {
            "id": f"com-{uuid4().hex[:12]}",
            "ts": events.now_iso(),
            "author": author,
            "body": body,
        }
        conn.execute(
            """
            INSERT INTO comments (id, issue_id, ts, author, body, data)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (payload["id"], issue_id, payload["ts"], author, body, store.json_dumps(payload)),
        )
        events.append_activity_db(conn, issue, "commented", f"Comment added by {author}.", author=author)
        events.emit_event(conn, "comment.created", author, issue_id, issue["revision"], payload)
        events.emit_event(conn, "issue.updated", author, issue_id, issue["revision"], issue)
        conn.execute("COMMIT")
    runtime.export_db_to_ledger(project_root)
    return payload


def realtime_create_manual_issue(
    project_root: Path,
    title: str,
    summary: str = "",
    status: str = "backlog",
    priority: str = "P2",
    parent_id: str | None = None,
    assignee: str | None = None,
    module: str | None = None,
    category: str | None = None,
    author: str = "web-board",
    expected_parent_revision: int | None = None,
) -> dict:
    runtime.ensure_realtime_store(project_root)
    if not title:
        raise ValueError("Issue title is required.")
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status}")
    if priority not in VALID_PRIORITIES:
        raise ValueError(f"Invalid priority: {priority}")
    with store.connect_db(project_root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        current_index = {
            "schema_version": SCHEMA_VERSION,
            "issues": [store.issue_from_row(row) for row in conn.execute("SELECT data, revision FROM issues")],
        }
        issues = current_index["issues"]
        prefix = DEFAULT_PREFIX
        parent = None
        if parent_id:
            parent = runtime.find_issue(current_index, parent_id)
            runtime.check_expected_revision(parent, expected_parent_revision)
            child_number = planning.next_child_number(issues, parent_id)
            issue_id = f"{parent_id}-{child_number:02d}"
            issue_type = "step"
            module = module or parent.get("module")
            category = category or parent.get("category") or "implementation"
            order = child_number
        else:
            issue_id = f"{prefix}-{planning.next_parent_number(issues, prefix):03d}"
            issue_type = "parent"
            module = module or planning.slugify(title, "module")
            category = category or "implementation"
            order = len([issue for issue in issues if issue.get("issue_type") == "parent"]) + 1
        issue = {
            "id": issue_id,
            "slug": planning.slugify(title),
            "path": f"{exporter.id_path_fragment(issue_id, prefix)}-{planning.slugify(title)}",
            "title": title,
            "summary": summary,
            "issue_type": issue_type,
            "module": module,
            "category": category,
            "milestone": "manual",
            "order": order,
            "status": status,
            "priority": priority,
            "parent_id": parent_id,
            "children": [],
            "depends_on": [],
            "source": {"manual": True},
            "assignee": assignee,
            "claimed_by": None,
            "claim_expires_at": None,
            "revision": 1,
            "external_refs": [],
            "labels": [module] if module else [],
        }
        runtime.upsert_issue_db(conn, issue)
        events.append_activity_db(conn, issue, "created", "Issue created manually.", author=author)
        events.emit_event(conn, "issue.created", author, issue_id, issue["revision"], issue)
        if parent:
            parent.setdefault("children", []).append(issue_id)
            parent["revision"] = int(parent.get("revision", 1)) + 1
            runtime.upsert_issue_db(conn, parent)
            events.append_activity_db(conn, parent, "split", f"Added child issue {issue_id}.", author=author)
            events.emit_event(conn, "issue.updated", author, parent["id"], parent["revision"], parent)
        conn.execute("COMMIT")
    runtime.export_db_to_ledger(project_root)
    return issue


def realtime_split_issue(
    project_root: Path,
    parent_id: str,
    child_titles: list[str],
    author: str = "system",
    expected_parent_revision: int | None = None,
) -> list[dict]:
    runtime.ensure_realtime_store(project_root)
    if not child_titles:
        raise ValueError("At least one child title is required.")
    with store.connect_db(project_root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        current_index = {
            "schema_version": SCHEMA_VERSION,
            "issues": [store.issue_from_row(row) for row in conn.execute("SELECT data, revision FROM issues")],
        }
        issues = current_index["issues"]
        parent = runtime.find_issue(current_index, parent_id)
        runtime.check_expected_revision(parent, expected_parent_revision)
        created: list[dict] = []
        for title in child_titles:
            child_number = planning.next_child_number(issues, parent_id)
            issue_id = f"{parent_id}-{child_number:02d}"
            issue = {
                "id": issue_id,
                "slug": planning.slugify(title),
                "path": f"{exporter.id_path_fragment(issue_id)}-{planning.slugify(title)}",
                "title": title,
                "summary": f"Child issue split from {parent_id}.",
                "issue_type": "step",
                "module": parent.get("module"),
                "category": parent.get("category") or "implementation",
                "milestone": parent.get("milestone") or "manual",
                "order": child_number,
                "status": "todo",
                "priority": parent.get("priority", "P2"),
                "parent_id": parent_id,
                "children": [],
                "depends_on": [],
                "source": {"manual": True, "split_from": parent_id},
                "assignee": None,
                "claimed_by": None,
                "claim_expires_at": None,
                "revision": 1,
                "external_refs": [],
                "labels": [parent.get("module")] if parent.get("module") else [],
            }
            issues.append(issue)
            parent.setdefault("children", []).append(issue_id)
            runtime.upsert_issue_db(conn, issue)
            events.append_activity_db(conn, issue, "created", f"Child issue split from {parent_id}.", author=author)
            events.emit_event(conn, "issue.created", author, issue_id, issue["revision"], issue)
            created.append(issue)
        parent["revision"] = int(parent.get("revision", 1)) + 1
        runtime.upsert_issue_db(conn, parent)
        events.append_activity_db(
            conn,
            parent,
            "split",
            f"Split into children: {', '.join(issue['id'] for issue in created)}.",
            author=author,
        )
        events.emit_event(conn, "issue.updated", author, parent_id, parent["revision"], parent)
        conn.execute("COMMIT")
    runtime.export_db_to_ledger(project_root)
    return created


def realtime_claim_issue(
    project_root: Path,
    issue_id: str,
    agent: str,
    ttl_minutes: int,
    force: bool = False,
    expected_revision: int | None = None,
) -> dict:
    runtime.ensure_realtime_store(project_root)
    agent = agent.strip()
    if not agent:
        raise ValueError("Claim agent is required.")
    if ttl_minutes <= 0:
        raise ValueError("Claim ttl_minutes must be positive.")
    with store.connect_db(project_root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        issue = runtime.realtime_find_issue(project_root, issue_id, conn)
        runtime.check_expected_revision(issue, expected_revision)
        current_claim = issue.get("claimed_by")
        expires_at = events.parse_iso(issue.get("claim_expires_at"))
        active = expires_at is not None and expires_at > datetime.now(timezone.utc)
        if current_claim and current_claim != agent and active and not force:
            raise runtime.ConflictError(f"Issue {issue_id} is already claimed by {current_claim} until {issue['claim_expires_at']}")
        issue["claimed_by"] = agent
        issue["claim_expires_at"] = (
            datetime.now(timezone.utc).replace(microsecond=0) + timedelta(minutes=ttl_minutes)
        ).isoformat()
        issue["status"] = "in_progress"
        issue["revision"] = int(issue.get("revision", 1)) + 1
        runtime.upsert_issue_db(conn, issue)
        events.append_activity_db(conn, issue, "claimed", f"Issue claimed by {agent}.", author=agent)
        events.emit_event(conn, "issue.updated", agent, issue_id, issue["revision"], issue)
        conn.execute("COMMIT")
    runtime.export_db_to_ledger(project_root)
    return issue


def realtime_assign_issue(
    project_root: Path,
    issue_id: str,
    assignee: str,
    author: str = "system",
    expected_revision: int | None = None,
) -> dict:
    return realtime_update_issue_fields(
        project_root,
        issue_id,
        {"assignee": assignee},
        author=author,
        expected_revision=expected_revision,
    )


def build_implementation_notes(issue: dict, body: str, author: str, existing: str | None, append: bool = True) -> str:
    if append and existing is not None:
        existing = existing.rstrip()
        return f"{existing}\n\n## Update {events.now_iso()} by {author}\n\n{body.strip()}\n"
    return f"# Implementation Report: {issue['id']}\n\n{body.strip()}\n"


def write_implementation_notes(project_root: Path, issue: dict, body: str, author: str, append: bool = True) -> str:
    directory = exporter.issue_dir(project_root, issue)
    exporter.ensure_issue_files(project_root, issue, issue.get("summary") or issue["title"])
    path = directory / "implementation.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    next_text = build_implementation_notes(issue, body, author, existing, append=append)
    path.write_text(next_text, encoding="utf-8")
    return next_text


def realtime_update_implementation_notes(
    project_root: Path,
    issue_id: str,
    body: str,
    author: str = "system",
    expected_revision: int | None = None,
    append: bool = True,
) -> dict:
    runtime.ensure_realtime_store(project_root)
    if not body.strip():
        raise ValueError("Implementation note body is required.")
    with store.connect_db(project_root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        issue = runtime.realtime_find_issue(project_root, issue_id, conn)
        runtime.check_expected_revision(issue, expected_revision)
        directory = exporter.issue_dir(project_root, issue)
        exporter.ensure_issue_files(project_root, issue, issue.get("summary") or issue["title"])
        notes_path = directory / "implementation.md"
        previous_text = notes_path.read_text(encoding="utf-8") if notes_path.exists() else None
        next_text = build_implementation_notes(issue, body, author, previous_text, append=append)
        notes_path.write_text(next_text, encoding="utf-8")
        try:
            issue["revision"] = int(issue.get("revision", 1)) + 1
            runtime.upsert_issue_db(conn, issue)
            events.append_activity_db(conn, issue, "implementation.updated", f"Implementation notes updated by {author}.", author=author)
            events.emit_event(conn, "issue.updated", author, issue_id, issue["revision"], issue)
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            if previous_text is None:
                notes_path.unlink(missing_ok=True)
            else:
                notes_path.write_text(previous_text, encoding="utf-8")
            raise
    runtime.export_db_to_ledger(project_root)
    return runtime.realtime_find_issue(project_root, issue_id)


def realtime_prepare_run(
    project_root: Path,
    issue_id: str,
    agent: str,
    ttl_minutes: int = 120,
    force: bool = False,
    expected_revision: int | None = None,
    claim: bool = True,
) -> dict:
    if claim:
        realtime_claim_issue(
            project_root,
            issue_id,
            agent,
            ttl_minutes,
            force=force,
            expected_revision=expected_revision,
        )
    detail = runtime.realtime_load_issue_detail(project_root, issue_id)
    detail["protocol"] = {
        "agent": agent,
        "next_steps": [
            "Read issue_md and implementation_md before editing code.",
            "Read parent, dependency, comments, and activity context when present.",
            "Keep edits scoped to this issue.",
            "Update implementation notes, comments or activity, and status after work.",
        ],
        "write_commands": {
            "note": f"ai-plan-issue note --author {agent} {issue_id} <summary>",
            "status": f"ai-plan-issue status --author {agent} {issue_id} in_review",
            "comment": f"ai-plan-issue comment --author {agent} {issue_id} <comment>",
        },
    }
    return detail
