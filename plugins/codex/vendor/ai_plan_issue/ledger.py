#!/usr/bin/env python3
"""AI Plan Issue ledger utilities.

The runtime intentionally uses only the Python standard library so a project can
adopt AI Plan Issue without installing a framework or service dependency.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import textwrap
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from . import events, exporter, store


SCHEMA_VERSION = store.SCHEMA_VERSION
API_VERSION = store.API_VERSION
DEFAULT_PREFIX = exporter.DEFAULT_PREFIX
DEFAULT_STATE_DIR = store.DEFAULT_STATE_DIR
LOCK_TIMEOUT_SECONDS = 30
LOCK_STALE_SECONDS = 300
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
TASK_RE = re.compile(
    r"^- \[[ xX]\]\s+(?P<id>T\d+)"
    r"(?:\s+\[P\])?"
    r"(?:\s+\[(?P<story>US\d+)\])?"
    r"\s+(?P<description>.+)$"
)


class ConflictError(RuntimeError):
    """Raised when a realtime write targets a stale issue revision."""


@dataclass
class ParsedTask:
    task_id: str
    description: str
    phase: str
    story: str | None


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def slugify(value: str, fallback: str = "issue") -> str:
    lowered = value.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug[:64].strip("-") or fallback


def project_root_from(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / DEFAULT_STATE_DIR).is_dir() or (candidate / "tasks.md").is_file():
            return candidate
    return current


state_root = store.state_root
issues_root = store.issues_root
index_path = store.index_path
write_lock_path = store.write_lock_path
path_is_relative_to = store.path_is_relative_to
database_path = store.database_path
token_path = store.token_path
get_project_token = store.get_project_token
connect_db = store.connect_db
init_realtime_db = store.init_realtime_db
realtime_issue_count = store.realtime_issue_count
json_dumps = store.json_dumps
issue_from_row = store.issue_from_row
issue_rows = store.issue_rows
realtime_index = store.realtime_index
default_index = exporter.default_index
load_index = exporter.load_index
write_json = exporter.write_json
save_index = exporter.save_index
id_path_fragment = exporter.id_path_fragment
issue_dir = exporter.issue_dir
append_jsonl = exporter.append_jsonl
append_activity = exporter.append_activity
read_jsonl = exporter.read_jsonl
make_issue_markdown = exporter.make_issue_markdown
sync_issue_markdown_metadata = exporter.sync_issue_markdown_metadata
ensure_issue_files = exporter.ensure_issue_files
refresh_board = exporter.refresh_board


@contextmanager
def issue_write_lock(project_root: Path):
    path = write_lock_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    fd: int | None = None

    while fd is None:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"pid={os.getpid()} ts={now_iso()}\n".encode("utf-8"))
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > LOCK_STALE_SECONDS:
                    path.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Timed out waiting for issue write lock: {path}")
            time.sleep(0.05)

    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def find_issue(index: dict, issue_id: str) -> dict:
    for issue in index.get("issues", []):
        if issue.get("id") == issue_id:
            return issue
    raise KeyError(f"Issue not found: {issue_id}")


def priority_for_group(group: str, story: str | None) -> str:
    text = f"{group} {story or ''}".lower()
    if "urgent" in text or "p0" in text:
        return "P0"
    if story == "US1" or "setup" in text or "foundation" in text:
        return "P1"
    if story == "US2" or "polish" not in text:
        return "P2"
    return "P3"


def module_for_group(group: str, story: str | None) -> str:
    if story:
        return story.lower()
    cleaned = re.sub(r"^phase\s+\d+\s*[:.-]\s*", "", group, flags=re.I)
    return slugify(cleaned, "module")


def category_for_group(group: str, story: str | None) -> str:
    text = f"{group} {story or ''}".lower()
    if story:
        return "feature"
    if any(token in text for token in ("setup", "foundation", "bootstrap", "schema", "migration")):
        return "foundation"
    if any(token in text for token in ("test", "qa", "review", "validate", "validation")):
        return "validation"
    if any(token in text for token in ("doc", "release", "deploy", "monitor", "ops")):
        return "operations"
    return "implementation"


def parse_tasks(tasks_path: Path) -> list[ParsedTask]:
    current_phase = "General"
    tasks: list[ParsedTask] = []
    for raw in tasks_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("## "):
            current_phase = line.lstrip("#").strip()
            current_phase = re.sub(r"^Phase\s+\d+\s*[:.-]\s*", "", current_phase, flags=re.I)
            continue
        match = TASK_RE.match(line)
        if match:
            tasks.append(
                ParsedTask(
                    task_id=match.group("id"),
                    story=match.group("story"),
                    description=match.group("description").strip(),
                    phase=current_phase or "General",
                )
            )
    return tasks


def latest_feature_dir(project_root: Path) -> Path:
    candidates = [
        project_root / "tasks.md",
        project_root / "docs" / "tasks.md",
        *list((project_root / "specs").glob("*/tasks.md")),
    ]
    candidates = [path for path in candidates if path.exists()]
    if not candidates:
        raise FileNotFoundError("No tasks.md found. Pass --tasks /path/to/tasks.md or create tasks.md in the project.")
    return max(candidates, key=lambda p: p.stat().st_mtime).parent


def task_group_key(task: ParsedTask) -> str:
    return task.story or task.phase


def next_parent_number(existing: list[dict], prefix: str = DEFAULT_PREFIX) -> int:
    found = 0
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    for issue in existing:
        match = pattern.match(issue.get("id", ""))
        if match:
            found = max(found, int(match.group(1)))
    return found + 1


def next_child_number(existing: list[dict], parent_id: str) -> int:
    found = 0
    pattern = re.compile(rf"^{re.escape(parent_id)}-(\d+)$")
    for issue in existing:
        match = pattern.match(issue.get("id", ""))
        if match:
            found = max(found, int(match.group(1)))
    return found + 1


def reset_issues(project_root: Path) -> None:
    root = issues_root(project_root)
    if not path_is_relative_to(root, project_root.resolve()):
        raise ValueError(f"refusing to reset state dir outside project root: {root}")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)


def generate_issues(
    project_root: Path,
    feature_dir: Path | None,
    force: bool,
    prefix: str = DEFAULT_PREFIX,
    tasks_file: Path | None = None,
) -> dict:
    with issue_write_lock(project_root):
        if tasks_file:
            tasks_path = tasks_file.resolve()
            feature_dir = tasks_path.parent
        else:
            feature_dir = feature_dir or latest_feature_dir(project_root)
            tasks_path = feature_dir / "tasks.md"
        if not tasks_path.exists():
            raise FileNotFoundError(f"Missing tasks.md: {tasks_path}")
        existing = load_index(project_root)
        if existing.get("issues") and not force:
            raise RuntimeError("Issues already exist. Use --force to regenerate.")
        if force:
            reset_issues(project_root)
        else:
            issues_root(project_root).mkdir(parents=True, exist_ok=True)

        tasks = parse_tasks(tasks_path)
        if not tasks:
            raise RuntimeError(f"No checklist tasks found in {tasks_path}")

        groups: dict[str, list[ParsedTask]] = {}
        for task in tasks:
            groups.setdefault(task_group_key(task), []).append(task)

        issues: list[dict] = []
        parent_number = next_parent_number([], prefix)
        for group_name, group_tasks in groups.items():
            story = group_tasks[0].story
            module = module_for_group(group_name, story)
            category = category_for_group(group_name, story)
            parent_id = f"{prefix}-{parent_number:03d}"
            parent_number += 1
            title = group_name.replace("_", " ").strip() or f"{module} work"
            task_ids = [task.task_id for task in group_tasks]
            priority = priority_for_group(group_name, story)
            parent_issue = {
                "id": parent_id,
                "slug": slugify(title),
                "path": f"{id_path_fragment(parent_id, prefix)}-{slugify(title)}",
                "title": title,
                    "summary": f"{len(group_tasks)} implementation tasks from {safe_relative(tasks_path, project_root)}.",
                "issue_type": "parent",
                "module": module,
                "category": category,
                "milestone": group_name,
                "order": parent_number - 1,
                "status": "todo",
                "priority": priority,
                "parent_id": None,
                "children": [],
                "depends_on": [],
                "source": {
                    "feature_dir": str(safe_relative(feature_dir, project_root)),
                    "task_ids": task_ids,
                },
                "assignee": None,
                "claimed_by": None,
                "claim_expires_at": None,
                "revision": 1,
                "external_refs": [],
                "labels": [module],
            }
            issues.append(parent_issue)

            for child_number, task in enumerate(group_tasks, start=1):
                child_id = f"{parent_id}-{child_number:02d}"
                child_title = task.description.rstrip(".")
                child_issue = {
                    "id": child_id,
                    "slug": slugify(child_title, f"task-{task.task_id.lower()}"),
                    "path": f"{id_path_fragment(child_id, prefix)}-{slugify(child_title, f'task-{task.task_id.lower()}')}",
                    "title": child_title,
                    "summary": f"Implements source task {task.task_id}.",
                    "issue_type": "step",
                    "module": module,
                    "category": category,
                    "milestone": task.phase,
                    "order": child_number,
                    "status": "todo",
                    "priority": priority,
                    "parent_id": parent_id,
                    "children": [],
                    "depends_on": [],
                    "source": {
                        "feature_dir": str(safe_relative(feature_dir, project_root)),
                        "task_ids": [task.task_id],
                    },
                    "assignee": None,
                    "claimed_by": None,
                    "claim_expires_at": None,
                    "revision": 1,
                    "external_refs": [],
                    "labels": [module, task.story.lower() if task.story else "task"],
                }
                parent_issue["children"].append(child_id)
                issues.append(child_issue)

        index = {"schema_version": SCHEMA_VERSION, "issues": issues}
        save_index(project_root, index)

        for issue in issues:
            if issue["issue_type"] == "parent":
                goal = issue["summary"]
                acceptance = [
                    "All child issues are completed or explicitly deferred.",
                    "Parent module satisfies the referenced design goal.",
                ]
            else:
                goal = issue["title"]
                acceptance = [f"Source task {issue['source']['task_ids'][0]} is implemented and validated."]
            ensure_issue_files(project_root, issue, goal, acceptance)
            append_activity(project_root, issue, "created", "Issue generated from tasks.md.")

        refresh_board(project_root, index)
        return index


def update_issue_fields(project_root: Path, issue_id: str, fields: dict, author: str = "system") -> dict:
    if not fields:
        raise ValueError("No editable issue fields provided.")
    with issue_write_lock(project_root):
        index = load_index(project_root)
        issue = find_issue(index, issue_id)
        before = {key: issue.get(key) for key in fields}
        for key, value in fields.items():
            if key == "status" and value not in VALID_STATUSES:
                raise ValueError(f"Invalid status: {value}")
            if key == "priority" and value not in VALID_PRIORITIES:
                raise ValueError(f"Invalid priority: {value}")
            issue[key] = value
        issue["revision"] = int(issue.get("revision", 1)) + 1
        save_index(project_root, index)
        sync_issue_markdown_metadata(project_root, issue)
        append_activity(
            project_root,
            issue,
            "updated",
            f"Updated fields {sorted(fields)} from {before} to {fields}.",
            author=author,
        )
        refresh_board(project_root, index)
        return issue


def append_comment(project_root: Path, issue_id: str, body: str, author: str) -> dict:
    with issue_write_lock(project_root):
        index = load_index(project_root)
        issue = find_issue(index, issue_id)
        payload = {
            "id": f"com-{uuid4().hex[:12]}",
            "ts": now_iso(),
            "author": author,
            "body": body,
        }
        append_jsonl(issue_dir(project_root, issue) / "comments.jsonl", payload)
        append_activity(project_root, issue, "commented", f"Comment added by {author}.", author=author)
        refresh_board(project_root, index)
        return payload


def create_manual_issue(
    project_root: Path,
    title: str,
    summary: str = "",
    status: str = "backlog",
    priority: str = "P2",
    parent_id: str | None = None,
    assignee: str | None = None,
    module: str | None = None,
    category: str | None = None,
) -> dict:
    with issue_write_lock(project_root):
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        if priority not in VALID_PRIORITIES:
            raise ValueError(f"Invalid priority: {priority}")
        index = load_index(project_root)
        prefix = DEFAULT_PREFIX
        issues = index.get("issues", [])
        if parent_id:
            parent = find_issue(index, parent_id)
            child_number = next_child_number(issues, parent_id)
            issue_id = f"{parent_id}-{child_number:02d}"
            issue_type = "step"
            module = module or parent.get("module")
            category = category or parent.get("category") or "implementation"
        else:
            issue_id = f"{prefix}-{next_parent_number(issues, prefix):03d}"
            issue_type = "parent"
            module = module or slugify(title, "module")
            category = category or "implementation"
        issue = {
            "id": issue_id,
            "slug": slugify(title),
            "path": f"{id_path_fragment(issue_id, prefix)}-{slugify(title)}",
            "title": title,
            "summary": summary,
            "issue_type": issue_type,
            "module": module,
            "category": category,
            "milestone": "manual",
            "order": len(issues) + 1,
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
        issues.append(issue)
        if parent_id:
            parent = find_issue(index, parent_id)
            parent.setdefault("children", []).append(issue_id)
            parent["revision"] = int(parent.get("revision", 1)) + 1
        save_index(project_root, index)
        ensure_issue_files(project_root, issue, summary or title)
        append_activity(project_root, issue, "created", "Issue created manually.")
        if parent_id:
            append_activity(project_root, parent, "split", f"Added child issue {issue_id}.")
        refresh_board(project_root, index)
        return issue


def split_issue(project_root: Path, parent_id: str, child_titles: list[str], author: str = "system") -> list[dict]:
    if not child_titles:
        raise ValueError("At least one child title is required.")
    created = [
        create_manual_issue(
            project_root,
            title=title,
            summary=f"Child issue split from {parent_id}.",
            status="todo",
            priority=find_issue(load_index(project_root), parent_id).get("priority", "P2"),
            parent_id=parent_id,
        )
        for title in child_titles
    ]
    index = load_index(project_root)
    parent = find_issue(index, parent_id)
    append_activity(
        project_root,
        parent,
        "split",
        f"Split into children: {', '.join(issue['id'] for issue in created)}.",
        author=author,
    )
    refresh_board(project_root, index)
    return created


def claim_issue(project_root: Path, issue_id: str, agent: str, ttl_minutes: int, force: bool = False) -> dict:
    agent = agent.strip()
    if not agent:
        raise ValueError("Claim agent is required.")
    if ttl_minutes <= 0:
        raise ValueError("Claim ttl_minutes must be positive.")
    with issue_write_lock(project_root):
        index = load_index(project_root)
        issue = find_issue(index, issue_id)
        current_claim = issue.get("claimed_by")
        expires_at = parse_iso(issue.get("claim_expires_at"))
        active = expires_at is not None and expires_at > datetime.now(timezone.utc)
        if current_claim and current_claim != agent and active and not force:
            raise ConflictError(f"Issue {issue_id} is already claimed by {current_claim} until {issue['claim_expires_at']}")
        issue["claimed_by"] = agent
        issue["claim_expires_at"] = (
            datetime.now(timezone.utc).replace(microsecond=0) + timedelta(minutes=ttl_minutes)
        ).isoformat()
        issue["status"] = "in_progress"
        issue["revision"] = int(issue.get("revision", 1)) + 1
        save_index(project_root, index)
        sync_issue_markdown_metadata(project_root, issue)
        append_activity(project_root, issue, "claimed", f"Issue claimed by {agent}.", author=agent)
        refresh_board(project_root, index)
        return issue


def assign_issue(project_root: Path, issue_id: str, assignee: str, author: str = "system") -> dict:
    return update_issue_fields(project_root, issue_id, {"assignee": assignee}, author=author)


def load_issue_detail(project_root: Path, issue_id: str) -> dict:
    index = load_index(project_root)
    issue = find_issue(index, issue_id)
    directory = issue_dir(project_root, issue)
    return {
        "issue": issue,
        "issue_md": (directory / "issue.md").read_text(encoding="utf-8") if (directory / "issue.md").exists() else "",
        "implementation_md": (directory / "implementation.md").read_text(encoding="utf-8") if (directory / "implementation.md").exists() else "",
        "comments": read_jsonl(directory / "comments.jsonl"),
        "activity": read_jsonl(directory / "activity.jsonl"),
    }


def upsert_issue_db(conn: sqlite3.Connection, issue: dict) -> None:
    revision = int(issue.get("revision", 1))
    issue["revision"] = revision
    conn.execute(
        """
        INSERT INTO issues (id, data, revision, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET data=excluded.data, revision=excluded.revision, updated_at=excluded.updated_at
        """,
        (issue["id"], json_dumps(issue), revision, now_iso()),
    )


def import_ledger_to_db(project_root: Path, force: bool = False) -> dict:
    init_realtime_db(project_root)
    with connect_db(project_root) as conn:
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
                return realtime_index(project_root)

        index = load_index(project_root)
        for issue in index.get("issues", []):
            issue.setdefault("revision", 1)
            upsert_issue_db(conn, issue)
            directory = issue_dir(project_root, issue)
            for comment in read_jsonl(directory / "comments.jsonl"):
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
                        json_dumps(comment),
                    ),
                )
            for activity_entry in read_jsonl(directory / "activity.jsonl"):
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
                        json_dumps(activity_entry),
                    ),
                )
        events.emit_event(conn, "board.exported", "system", None, None, {"mode": "import", "issues": len(index["issues"])})
        conn.execute("COMMIT")
    export_db_to_ledger(project_root)
    return realtime_index(project_root)


def export_db_to_ledger(project_root: Path) -> dict:
    init_realtime_db(project_root)
    index = realtime_index(project_root)
    issues_root(project_root).mkdir(parents=True, exist_ok=True)
    save_index(project_root, index)
    refresh_board(project_root, index)
    with connect_db(project_root) as conn:
        for issue in index.get("issues", []):
            ensure_issue_files(project_root, issue, issue.get("summary") or issue["title"])
            sync_issue_markdown_metadata(project_root, issue)
            directory = issue_dir(project_root, issue)
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
    init_realtime_db(project_root)
    get_project_token(project_root)
    if realtime_issue_count(project_root) == 0 and index_path(project_root).exists() and load_index(project_root).get("issues"):
        return import_ledger_to_db(project_root, force=False)
    if not index_path(project_root).exists():
        export_db_to_ledger(project_root)
    return realtime_index(project_root)


def realtime_load_index(project_root: Path) -> dict:
    ensure_realtime_store(project_root)
    return realtime_index(project_root)


def realtime_find_issue(project_root: Path, issue_id: str, conn: sqlite3.Connection | None = None) -> dict:
    close_conn = conn is None
    conn = conn or connect_db(project_root)
    try:
        row = conn.execute("SELECT data, revision FROM issues WHERE id = ?", (issue_id,)).fetchone()
        if not row:
            raise KeyError(f"Issue not found: {issue_id}")
        return issue_from_row(row)
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
    directory = issue_dir(project_root, issue)
    with connect_db(project_root) as conn:
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


def realtime_update_issue_fields(
    project_root: Path,
    issue_id: str,
    fields: dict,
    author: str = "system",
    expected_revision: int | None = None,
) -> dict:
    ensure_realtime_store(project_root)
    if not fields:
        raise ValueError("No editable issue fields provided.")
    with connect_db(project_root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        issue = realtime_find_issue(project_root, issue_id, conn)
        check_expected_revision(issue, expected_revision)
        before = {key: issue.get(key) for key in fields}
        for key, value in fields.items():
            if key == "status" and value not in VALID_STATUSES:
                raise ValueError(f"Invalid status: {value}")
            if key == "priority" and value not in VALID_PRIORITIES:
                raise ValueError(f"Invalid priority: {value}")
            issue[key] = value
        issue["revision"] = int(issue.get("revision", 1)) + 1
        upsert_issue_db(conn, issue)
        events.append_activity_db(conn, issue, "updated", f"Updated fields {sorted(fields)} from {before} to {fields}.", author)
        events.emit_event(conn, "issue.updated", author, issue_id, issue["revision"], issue)
        conn.execute("COMMIT")
    export_db_to_ledger(project_root)
    return issue


def realtime_append_comment(
    project_root: Path,
    issue_id: str,
    body: str,
    author: str,
    expected_revision: int | None = None,
) -> dict:
    ensure_realtime_store(project_root)
    if not body:
        raise ValueError("Comment body is required.")
    with connect_db(project_root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        issue = realtime_find_issue(project_root, issue_id, conn)
        check_expected_revision(issue, expected_revision)
        issue["revision"] = int(issue.get("revision", 1)) + 1
        upsert_issue_db(conn, issue)
        payload = {
            "id": f"com-{uuid4().hex[:12]}",
            "ts": now_iso(),
            "author": author,
            "body": body,
        }
        conn.execute(
            """
            INSERT INTO comments (id, issue_id, ts, author, body, data)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (payload["id"], issue_id, payload["ts"], author, body, json_dumps(payload)),
        )
        events.append_activity_db(conn, issue, "commented", f"Comment added by {author}.", author=author)
        events.emit_event(conn, "comment.created", author, issue_id, issue["revision"], payload)
        events.emit_event(conn, "issue.updated", author, issue_id, issue["revision"], issue)
        conn.execute("COMMIT")
    export_db_to_ledger(project_root)
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
    ensure_realtime_store(project_root)
    if not title:
        raise ValueError("Issue title is required.")
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status}")
    if priority not in VALID_PRIORITIES:
        raise ValueError(f"Invalid priority: {priority}")
    with connect_db(project_root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        current_index = {"schema_version": SCHEMA_VERSION, "issues": [issue_from_row(row) for row in conn.execute("SELECT data, revision FROM issues")]}
        issues = current_index["issues"]
        prefix = DEFAULT_PREFIX
        parent = None
        if parent_id:
            parent = find_issue(current_index, parent_id)
            check_expected_revision(parent, expected_parent_revision)
            child_number = next_child_number(issues, parent_id)
            issue_id = f"{parent_id}-{child_number:02d}"
            issue_type = "step"
            module = module or parent.get("module")
            category = category or parent.get("category") or "implementation"
            order = child_number
        else:
            issue_id = f"{prefix}-{next_parent_number(issues, prefix):03d}"
            issue_type = "parent"
            module = module or slugify(title, "module")
            category = category or "implementation"
            order = len([issue for issue in issues if issue.get("issue_type") == "parent"]) + 1
        issue = {
            "id": issue_id,
            "slug": slugify(title),
            "path": f"{id_path_fragment(issue_id, prefix)}-{slugify(title)}",
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
        upsert_issue_db(conn, issue)
        events.append_activity_db(conn, issue, "created", "Issue created manually.", author=author)
        events.emit_event(conn, "issue.created", author, issue_id, issue["revision"], issue)
        if parent:
            parent.setdefault("children", []).append(issue_id)
            parent["revision"] = int(parent.get("revision", 1)) + 1
            upsert_issue_db(conn, parent)
            events.append_activity_db(conn, parent, "split", f"Added child issue {issue_id}.", author=author)
            events.emit_event(conn, "issue.updated", author, parent["id"], parent["revision"], parent)
        conn.execute("COMMIT")
    export_db_to_ledger(project_root)
    return issue


def realtime_split_issue(
    project_root: Path,
    parent_id: str,
    child_titles: list[str],
    author: str = "system",
    expected_parent_revision: int | None = None,
) -> list[dict]:
    ensure_realtime_store(project_root)
    if not child_titles:
        raise ValueError("At least one child title is required.")
    with connect_db(project_root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        current_index = {
            "schema_version": SCHEMA_VERSION,
            "issues": [issue_from_row(row) for row in conn.execute("SELECT data, revision FROM issues")],
        }
        issues = current_index["issues"]
        parent = find_issue(current_index, parent_id)
        check_expected_revision(parent, expected_parent_revision)
        created: list[dict] = []
        for title in child_titles:
            child_number = next_child_number(issues, parent_id)
            issue_id = f"{parent_id}-{child_number:02d}"
            issue = {
                "id": issue_id,
                "slug": slugify(title),
                "path": f"{id_path_fragment(issue_id)}-{slugify(title)}",
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
            upsert_issue_db(conn, issue)
            events.append_activity_db(conn, issue, "created", f"Child issue split from {parent_id}.", author=author)
            events.emit_event(conn, "issue.created", author, issue_id, issue["revision"], issue)
            created.append(issue)
        parent["revision"] = int(parent.get("revision", 1)) + 1
        upsert_issue_db(conn, parent)
        events.append_activity_db(
            conn,
            parent,
            "split",
            f"Split into children: {', '.join(issue['id'] for issue in created)}.",
            author=author,
        )
        events.emit_event(conn, "issue.updated", author, parent_id, parent["revision"], parent)
        conn.execute("COMMIT")
    export_db_to_ledger(project_root)
    return created


def realtime_claim_issue(
    project_root: Path,
    issue_id: str,
    agent: str,
    ttl_minutes: int,
    force: bool = False,
    expected_revision: int | None = None,
) -> dict:
    ensure_realtime_store(project_root)
    agent = agent.strip()
    if not agent:
        raise ValueError("Claim agent is required.")
    if ttl_minutes <= 0:
        raise ValueError("Claim ttl_minutes must be positive.")
    with connect_db(project_root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        issue = realtime_find_issue(project_root, issue_id, conn)
        check_expected_revision(issue, expected_revision)
        current_claim = issue.get("claimed_by")
        expires_at = parse_iso(issue.get("claim_expires_at"))
        active = expires_at is not None and expires_at > datetime.now(timezone.utc)
        if current_claim and current_claim != agent and active and not force:
            raise ConflictError(f"Issue {issue_id} is already claimed by {current_claim} until {issue['claim_expires_at']}")
        issue["claimed_by"] = agent
        issue["claim_expires_at"] = (
            datetime.now(timezone.utc).replace(microsecond=0) + timedelta(minutes=ttl_minutes)
        ).isoformat()
        issue["status"] = "in_progress"
        issue["revision"] = int(issue.get("revision", 1)) + 1
        upsert_issue_db(conn, issue)
        events.append_activity_db(conn, issue, "claimed", f"Issue claimed by {agent}.", author=agent)
        events.emit_event(conn, "issue.updated", agent, issue_id, issue["revision"], issue)
        conn.execute("COMMIT")
    export_db_to_ledger(project_root)
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
        return f"{existing}\n\n## Update {now_iso()} by {author}\n\n{body.strip()}\n"
    return f"# Implementation Report: {issue['id']}\n\n{body.strip()}\n"


def write_implementation_notes(project_root: Path, issue: dict, body: str, author: str, append: bool = True) -> str:
    directory = issue_dir(project_root, issue)
    ensure_issue_files(project_root, issue, issue.get("summary") or issue["title"])
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
    ensure_realtime_store(project_root)
    if not body.strip():
        raise ValueError("Implementation note body is required.")
    with connect_db(project_root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        issue = realtime_find_issue(project_root, issue_id, conn)
        check_expected_revision(issue, expected_revision)
        directory = issue_dir(project_root, issue)
        ensure_issue_files(project_root, issue, issue.get("summary") or issue["title"])
        notes_path = directory / "implementation.md"
        previous_text = notes_path.read_text(encoding="utf-8") if notes_path.exists() else None
        next_text = build_implementation_notes(issue, body, author, previous_text, append=append)
        notes_path.write_text(next_text, encoding="utf-8")
        try:
            issue["revision"] = int(issue.get("revision", 1)) + 1
            upsert_issue_db(conn, issue)
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
    export_db_to_ledger(project_root)
    return realtime_find_issue(project_root, issue_id)


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
    detail = realtime_load_issue_detail(project_root, issue_id)
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


def safe_relative(path: Path, root: Path) -> Path:
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError:
        return path.resolve()
