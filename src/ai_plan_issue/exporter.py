"""Markdown, JSON, and JSONL export helpers for AI Plan Issue."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from . import store


SCHEMA_VERSION = store.SCHEMA_VERSION
DEFAULT_PREFIX = "AI"
BOARD_STATUSES = ["backlog", "todo", "in_progress", "blocked", "needs_review", "in_review", "done"]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_index() -> dict:
    return {"schema_version": SCHEMA_VERSION, "issues": []}


def load_index(project_root: Path) -> dict:
    path = store.index_path(project_root)
    if not path.exists():
        return default_index()
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid index JSON: {path}")
    data.setdefault("schema_version", SCHEMA_VERSION)
    data.setdefault("issues", [])
    return data


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def save_index(project_root: Path, index: dict) -> None:
    write_json(store.index_path(project_root), index)


def id_path_fragment(issue_id: str, prefix: str = DEFAULT_PREFIX) -> str:
    fragment = issue_id
    if fragment.startswith(prefix + "-"):
        fragment = fragment[len(prefix) + 1 :]
    return fragment.lower()


def issue_dir(project_root: Path, issue: dict) -> Path:
    path = issue.get("path")
    if not path:
        path = f"{id_path_fragment(issue['id'])}-{issue['slug']}"
    raw_path = Path(str(path))
    if raw_path.is_absolute() or any(part in {"..", ""} for part in raw_path.parts):
        raise ValueError(f"Unsafe issue path for {issue.get('id', 'unknown')}: {path}")
    root = store.issues_root(project_root).resolve()
    target = (root / raw_path).resolve()
    if not store.path_is_relative_to(target, root):
        raise ValueError(f"Unsafe issue path for {issue.get('id', 'unknown')}: {path}")
    return target


def append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def append_activity(project_root: Path, issue: dict, action: str, body: str, author: str = "system") -> None:
    append_jsonl(
        issue_dir(project_root, issue) / "activity.jsonl",
        {
            "id": f"act-{uuid4().hex[:12]}",
            "ts": now_iso(),
            "author": author,
            "action": action,
            "body": body,
        },
    )


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    entries: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            value = {"id": f"invalid-{uuid4().hex[:8]}", "body": line}
        if isinstance(value, dict):
            entries.append(value)
    return entries


def make_issue_markdown(issue: dict, goal: str, acceptance: list[str] | None = None) -> str:
    acceptance = acceptance or []
    children = ", ".join(issue.get("children", [])) or "none"
    depends = ", ".join(issue.get("depends_on", [])) or "none"
    parent = issue.get("parent_id") or "none"
    source = issue.get("source", {})
    task_ids = ", ".join(source.get("task_ids", [])) or "none"
    feature_dir = source.get("feature_dir", "none")
    lines = [
        f"# {issue['id']} {issue['title']}",
        "",
        f"Status: {issue['status']}",
        f"Priority: {issue['priority']}",
        f"Assignee: {issue.get('assignee') or 'none'}",
        f"Claimed by: {issue.get('claimed_by') or 'none'}",
        f"Category: {issue.get('category') or 'none'}",
        f"Milestone: {issue.get('milestone') or 'none'}",
        f"Type: {issue['issue_type']}",
        f"Module: {issue.get('module') or 'none'}",
        f"Parent: {parent}",
        f"Children: {children}",
        f"Depends on: {depends}",
        f"Source: {feature_dir} ({task_ids})",
        "",
        "## Goal",
        "",
        goal.strip() or issue.get("summary") or issue["title"],
        "",
        "## Acceptance Criteria",
        "",
    ]
    if acceptance:
        lines.extend(f"- [ ] {item}" for item in acceptance)
    else:
        lines.append("- [ ] Work satisfies the issue goal and source tasks.")
    lines.extend(
        [
            "",
            "## Implementation Notes",
            "",
            "Record design decisions, changed files, validation, and risks here during execution.",
            "",
        ]
    )
    return "\n".join(lines)


def sync_issue_markdown_metadata(project_root: Path, issue: dict) -> None:
    path = issue_dir(project_root, issue) / "issue.md"
    if not path.exists():
        return

    source = issue.get("source") or {}
    task_ids = ", ".join(source.get("task_ids", [])) or "none"
    feature_dir = source.get("feature_dir", "manual" if source.get("manual") else "none")
    metadata = {
        "Status": issue["status"],
        "Priority": issue["priority"],
        "Assignee": issue.get("assignee") or "none",
        "Claimed by": issue.get("claimed_by") or "none",
        "Category": issue.get("category") or "none",
        "Milestone": issue.get("milestone") or "none",
        "Type": issue.get("issue_type") or "step",
        "Module": issue.get("module") or "none",
        "Parent": issue.get("parent_id") or "none",
        "Children": ", ".join(issue.get("children", [])) or "none",
        "Depends on": ", ".join(issue.get("depends_on", [])) or "none",
        "Source": f"{feature_dir} ({task_ids})",
    }
    seen: set[str] = set()
    lines = path.read_text(encoding="utf-8").splitlines()
    updated: list[str] = []
    insert_after = -1

    for line in lines:
        replaced = False
        for key, value in metadata.items():
            if line.startswith(f"{key}:"):
                updated.append(f"{key}: {value}")
                seen.add(key)
                replaced = True
                if key == "Priority":
                    insert_after = len(updated) - 1
                break
        if not replaced:
            updated.append(line)

    missing = [
        f"{key}: {metadata[key]}"
        for key in (
            "Assignee",
            "Claimed by",
            "Category",
            "Milestone",
            "Type",
            "Module",
            "Parent",
            "Children",
            "Depends on",
            "Source",
        )
        if key not in seen
    ]
    if missing:
        if insert_after >= 0:
            updated[insert_after + 1:insert_after + 1] = missing
        else:
            updated[1:1] = ["", *missing]

    path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def ensure_issue_files(project_root: Path, issue: dict, goal: str, acceptance: list[str] | None = None) -> None:
    directory = issue_dir(project_root, issue)
    directory.mkdir(parents=True, exist_ok=True)
    issue_md = directory / "issue.md"
    if not issue_md.exists():
        issue_md.write_text(make_issue_markdown(issue, goal, acceptance), encoding="utf-8")
    for name in ("comments.jsonl", "activity.jsonl"):
        path = directory / name
        if not path.exists():
            path.write_text("", encoding="utf-8")
    implementation = directory / "implementation.md"
    if not implementation.exists():
        implementation.write_text(
            f"# Implementation Report: {issue['id']}\n\nNot started.\n",
            encoding="utf-8",
        )


def refresh_board(project_root: Path, index: dict | None = None) -> None:
    index = index or load_index(project_root)
    grouped: dict[str, list[dict]] = {status: [] for status in BOARD_STATUSES}
    for issue in index.get("issues", []):
        grouped.setdefault(issue.get("status", "todo"), []).append(issue)

    lines = ["# AI Plan Issue Board", ""]
    for status in BOARD_STATUSES:
        issues = grouped.get(status, [])
        lines.append(f"## {status.replace('_', ' ').title()} ({len(issues)})")
        lines.append("")
        if not issues:
            lines.append("_No issues._")
            lines.append("")
            continue
        for issue in issues:
            parent = f" parent={issue['parent_id']}" if issue.get("parent_id") else ""
            assignee = f" assignee={issue['assignee']}" if issue.get("assignee") else ""
            lines.append(f"- `{issue['id']}` {issue['title']} [{issue['priority']}]{parent}{assignee}")
        lines.append("")
    (store.issues_root(project_root) / "board.md").write_text("\n".join(lines), encoding="utf-8")
