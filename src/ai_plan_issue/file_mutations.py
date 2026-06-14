"""Legacy Markdown/JSONL issue mutation helpers."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from . import events, exporter, planning, runtime, store


DEFAULT_PREFIX = exporter.DEFAULT_PREFIX
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
LockFactory = Callable[[Path], Iterator[object]]


@contextmanager
def issue_write_lock(project_root: Path):
    path = store.write_lock_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    fd: int | None = None

    while fd is None:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"pid={os.getpid()} ts={events.now_iso()}\n".encode("utf-8"))
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


def _lock(project_root: Path, lock_factory: LockFactory | None):
    return lock_factory(project_root) if lock_factory else issue_write_lock(project_root)


def update_issue_fields(
    project_root: Path,
    issue_id: str,
    fields: dict,
    author: str = "system",
    lock_factory: LockFactory | None = None,
) -> dict:
    if not fields:
        raise ValueError("No editable issue fields provided.")
    with _lock(project_root, lock_factory):
        index = exporter.load_index(project_root)
        issue = runtime.find_issue(index, issue_id)
        before = {key: issue.get(key) for key in fields}
        for key, value in fields.items():
            if key == "status" and value not in VALID_STATUSES:
                raise ValueError(f"Invalid status: {value}")
            if key == "priority" and value not in VALID_PRIORITIES:
                raise ValueError(f"Invalid priority: {value}")
            issue[key] = value
        issue["revision"] = int(issue.get("revision", 1)) + 1
        exporter.save_index(project_root, index)
        exporter.sync_issue_markdown_metadata(project_root, issue)
        exporter.append_activity(
            project_root,
            issue,
            "updated",
            f"Updated fields {sorted(fields)} from {before} to {fields}.",
            author=author,
        )
        exporter.refresh_board(project_root, index)
        return issue


def append_comment(
    project_root: Path,
    issue_id: str,
    body: str,
    author: str,
    lock_factory: LockFactory | None = None,
) -> dict:
    with _lock(project_root, lock_factory):
        index = exporter.load_index(project_root)
        issue = runtime.find_issue(index, issue_id)
        payload = {
            "id": f"com-{uuid4().hex[:12]}",
            "ts": events.now_iso(),
            "author": author,
            "body": body,
        }
        exporter.append_jsonl(exporter.issue_dir(project_root, issue) / "comments.jsonl", payload)
        exporter.append_activity(project_root, issue, "commented", f"Comment added by {author}.", author=author)
        exporter.refresh_board(project_root, index)
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
    lock_factory: LockFactory | None = None,
) -> dict:
    with _lock(project_root, lock_factory):
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        if priority not in VALID_PRIORITIES:
            raise ValueError(f"Invalid priority: {priority}")
        index = exporter.load_index(project_root)
        prefix = DEFAULT_PREFIX
        issues = index.get("issues", [])
        if parent_id:
            parent = runtime.find_issue(index, parent_id)
            child_number = planning.next_child_number(issues, parent_id)
            issue_id = f"{parent_id}-{child_number:02d}"
            issue_type = "step"
            module = module or parent.get("module")
            category = category or parent.get("category") or "implementation"
        else:
            issue_id = f"{prefix}-{planning.next_parent_number(issues, prefix):03d}"
            issue_type = "parent"
            module = module or planning.slugify(title, "module")
            category = category or "implementation"
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
            parent = runtime.find_issue(index, parent_id)
            parent.setdefault("children", []).append(issue_id)
            parent["revision"] = int(parent.get("revision", 1)) + 1
        exporter.save_index(project_root, index)
        exporter.ensure_issue_files(project_root, issue, summary or title)
        exporter.append_activity(project_root, issue, "created", "Issue created manually.")
        if parent_id:
            exporter.append_activity(project_root, parent, "split", f"Added child issue {issue_id}.")
        exporter.refresh_board(project_root, index)
        return issue


def split_issue(
    project_root: Path,
    parent_id: str,
    child_titles: list[str],
    author: str = "system",
    lock_factory: LockFactory | None = None,
) -> list[dict]:
    if not child_titles:
        raise ValueError("At least one child title is required.")
    created = [
        create_manual_issue(
            project_root,
            title=title,
            summary=f"Child issue split from {parent_id}.",
            status="todo",
            priority=runtime.find_issue(exporter.load_index(project_root), parent_id).get("priority", "P2"),
            parent_id=parent_id,
            lock_factory=lock_factory,
        )
        for title in child_titles
    ]
    index = exporter.load_index(project_root)
    parent = runtime.find_issue(index, parent_id)
    exporter.append_activity(
        project_root,
        parent,
        "split",
        f"Split into children: {', '.join(issue['id'] for issue in created)}.",
        author=author,
    )
    exporter.refresh_board(project_root, index)
    return created


def claim_issue(
    project_root: Path,
    issue_id: str,
    agent: str,
    ttl_minutes: int,
    force: bool = False,
    lock_factory: LockFactory | None = None,
) -> dict:
    agent = agent.strip()
    if not agent:
        raise ValueError("Claim agent is required.")
    if ttl_minutes <= 0:
        raise ValueError("Claim ttl_minutes must be positive.")
    with _lock(project_root, lock_factory):
        index = exporter.load_index(project_root)
        issue = runtime.find_issue(index, issue_id)
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
        exporter.save_index(project_root, index)
        exporter.sync_issue_markdown_metadata(project_root, issue)
        exporter.append_activity(project_root, issue, "claimed", f"Issue claimed by {agent}.", author=agent)
        exporter.refresh_board(project_root, index)
        return issue


def assign_issue(
    project_root: Path,
    issue_id: str,
    assignee: str,
    author: str = "system",
    lock_factory: LockFactory | None = None,
) -> dict:
    return update_issue_fields(
        project_root,
        issue_id,
        {"assignee": assignee},
        author=author,
        lock_factory=lock_factory,
    )


def load_issue_detail(project_root: Path, issue_id: str) -> dict:
    index = exporter.load_index(project_root)
    issue = runtime.find_issue(index, issue_id)
    directory = exporter.issue_dir(project_root, issue)
    return {
        "issue": issue,
        "issue_md": (directory / "issue.md").read_text(encoding="utf-8") if (directory / "issue.md").exists() else "",
        "implementation_md": (directory / "implementation.md").read_text(encoding="utf-8") if (directory / "implementation.md").exists() else "",
        "comments": exporter.read_jsonl(directory / "comments.jsonl"),
        "activity": exporter.read_jsonl(directory / "activity.jsonl"),
    }
