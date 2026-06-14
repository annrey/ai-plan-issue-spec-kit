#!/usr/bin/env python3
"""AI Plan Issue ledger utilities.

The runtime intentionally uses only the Python standard library so a project can
adopt AI Plan Issue without installing a framework or service dependency.
"""

from __future__ import annotations

import os
import shutil
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import context_bundle, exporter, file_mutations, mutations, planning, runtime, store


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

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


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
ParsedTask = planning.ParsedTask
slugify = planning.slugify
priority_for_group = planning.priority_for_group
module_for_group = planning.module_for_group
category_for_group = planning.category_for_group
parse_tasks = planning.parse_tasks
latest_feature_dir = planning.latest_feature_dir
task_group_key = planning.task_group_key
next_parent_number = planning.next_parent_number
next_child_number = planning.next_child_number
ConflictError = runtime.ConflictError
upsert_issue_db = runtime.upsert_issue_db
import_ledger_to_db = runtime.import_ledger_to_db
export_db_to_ledger = runtime.export_db_to_ledger
ensure_realtime_store = runtime.ensure_realtime_store
realtime_load_index = runtime.realtime_load_index
realtime_find_issue = runtime.realtime_find_issue
check_expected_revision = runtime.check_expected_revision
realtime_load_issue_detail = runtime.realtime_load_issue_detail
realtime_load_context = context_bundle.build_context_bundle
realtime_update_issue_fields = mutations.realtime_update_issue_fields
realtime_append_comment = mutations.realtime_append_comment
realtime_create_manual_issue = mutations.realtime_create_manual_issue
realtime_split_issue = mutations.realtime_split_issue
realtime_claim_issue = mutations.realtime_claim_issue
realtime_assign_issue = mutations.realtime_assign_issue
build_implementation_notes = mutations.build_implementation_notes
write_implementation_notes = mutations.write_implementation_notes
realtime_update_implementation_notes = mutations.realtime_update_implementation_notes
realtime_prepare_run = mutations.realtime_prepare_run
update_issue_fields = file_mutations.update_issue_fields
append_comment = file_mutations.append_comment
create_manual_issue = file_mutations.create_manual_issue
split_issue = file_mutations.split_issue
claim_issue = file_mutations.claim_issue
assign_issue = file_mutations.assign_issue
load_issue_detail = file_mutations.load_issue_detail


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


def safe_relative(path: Path, root: Path) -> Path:
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError:
        return path.resolve()
