"""Task parsing and issue planning helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


DEFAULT_PREFIX = "AI"
TASK_RE = re.compile(
    r"^- \[[ xX]\]\s+(?P<id>T\d+)"
    r"(?:\s+\[P\])?"
    r"(?:\s+\[(?P<story>US\d+)\])?"
    r"\s+(?P<description>.+)$"
)


@dataclass
class ParsedTask:
    task_id: str
    description: str
    phase: str
    story: str | None


def slugify(value: str, fallback: str = "issue") -> str:
    lowered = value.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug[:64].strip("-") or fallback


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
