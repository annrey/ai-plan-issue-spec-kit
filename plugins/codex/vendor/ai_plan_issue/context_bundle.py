"""Agent execution context bundles for issues."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from . import exporter, runtime, store


CONTEXT_VERSION = "1.0"
DEFAULT_INCLUDE = {
    "activity",
    "children",
    "comments",
    "dependencies",
    "files",
    "implementation",
    "issue",
    "milestone",
    "module",
    "parent",
}
VALID_INCLUDE = DEFAULT_INCLUDE | {"dependents"}


def parse_include(value: str | Iterable[str] | None = None) -> set[str]:
    if value is None:
        return set(DEFAULT_INCLUDE)
    if isinstance(value, str):
        requested = {part.strip() for part in value.split(",") if part.strip()}
    else:
        requested = {str(part).strip() for part in value if str(part).strip()}
    if not requested:
        return set(DEFAULT_INCLUDE)
    unknown = requested - VALID_INCLUDE
    if unknown:
        raise ValueError(f"Unknown context include values: {sorted(unknown)}")
    return requested


def issue_summary(issue: dict) -> dict:
    keys = (
        "id",
        "title",
        "summary",
        "issue_type",
        "status",
        "priority",
        "module",
        "category",
        "milestone",
        "parent_id",
        "children",
        "depends_on",
        "assignee",
        "claimed_by",
        "claim_expires_at",
        "revision",
        "path",
        "labels",
    )
    return {key: issue.get(key) for key in keys if key in issue}


def _relative_path(project_root: Path, path: Path) -> str:
    root = project_root.resolve()
    resolved = path.resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _issue_files(project_root: Path, issue: dict) -> dict:
    directory = exporter.issue_dir(project_root, issue)
    return {
        "directory": _relative_path(project_root, directory),
        "issue_md": _relative_path(project_root, directory / "issue.md"),
        "implementation_md": _relative_path(project_root, directory / "implementation.md"),
        "comments_jsonl": _relative_path(project_root, directory / "comments.jsonl"),
        "activity_jsonl": _relative_path(project_root, directory / "activity.jsonl"),
    }


def _summaries_for_ids(issues_by_id: dict[str, dict], issue_ids: Iterable[str]) -> tuple[list[dict], list[str]]:
    summaries: list[dict] = []
    missing: list[str] = []
    for issue_id in issue_ids:
        issue = issues_by_id.get(issue_id)
        if issue is None:
            missing.append(issue_id)
        else:
            summaries.append(issue_summary(issue))
    return summaries, missing


def _summaries_matching(issues: list[dict], key: str, value: object) -> list[dict]:
    if value in (None, ""):
        return []
    return [issue_summary(issue) for issue in issues if issue.get(key) == value]


def build_context_bundle(project_root: Path, issue_id: str, include: str | Iterable[str] | None = None) -> dict:
    include_set = parse_include(include)
    index = runtime.realtime_load_index(project_root)
    detail = runtime.realtime_load_issue_detail(project_root, issue_id)
    issue = detail["issue"]
    issues = list(index.get("issues", []))
    issues_by_id = {item["id"]: item for item in issues}

    bundle: dict = {
        "api_version": store.API_VERSION,
        "context_version": CONTEXT_VERSION,
        "issue_id": issue_id,
        "include": sorted(include_set),
        "issue": issue,
    }

    if "parent" in include_set:
        parent_id = issue.get("parent_id")
        bundle["parent"] = issue_summary(issues_by_id[parent_id]) if parent_id in issues_by_id else None

    if "children" in include_set:
        children, missing_children = _summaries_for_ids(issues_by_id, issue.get("children", []))
        bundle["children"] = children
        bundle["missing_child_ids"] = missing_children

    if "dependencies" in include_set:
        dependencies, missing_dependencies = _summaries_for_ids(issues_by_id, issue.get("depends_on", []))
        bundle["dependencies"] = dependencies
        bundle["missing_dependency_ids"] = missing_dependencies

    if "dependents" in include_set:
        bundle["dependents"] = [
            issue_summary(candidate)
            for candidate in issues
            if issue_id in set(candidate.get("depends_on", []))
        ]

    if "comments" in include_set:
        bundle["comments"] = detail.get("comments", [])

    if "activity" in include_set:
        bundle["activity"] = detail.get("activity", [])

    if "implementation" in include_set:
        bundle["issue_md"] = detail.get("issue_md", "")
        bundle["implementation_md"] = detail.get("implementation_md", "")

    if "files" in include_set:
        bundle["files"] = _issue_files(project_root, issue)

    if "module" in include_set:
        bundle["module"] = {
            "name": issue.get("module"),
            "issues": _summaries_matching(issues, "module", issue.get("module")),
        }

    if "milestone" in include_set:
        bundle["milestone"] = {
            "name": issue.get("milestone"),
            "issues": _summaries_matching(issues, "milestone", issue.get("milestone")),
        }

    bundle["agent_protocol"] = {
        "read_order": [
            "issue",
            "parent",
            "dependencies",
            "comments",
            "activity",
            "implementation_md",
        ],
        "write_after_execution": [
            "implementation notes",
            "comments or activity",
            "status",
        ],
    }
    return bundle
