"""Project-local paths, tokens, and SQLite storage helpers."""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
from pathlib import Path


SCHEMA_VERSION = "1.0"
API_VERSION = "1.0"
DEFAULT_STATE_DIR = ".ai-plan-issue"


class ClosingConnection(sqlite3.Connection):
    """SQLite connection that closes after context-manager use."""

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc_value, traceback))
        finally:
            self.close()


def path_is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def state_root(project_root: Path) -> Path:
    project_root = project_root.resolve()
    configured = os.environ.get("AI_PLAN_ISSUE_DIR")
    if configured:
        path = Path(configured)
        root = path.resolve() if path.is_absolute() else (project_root / path).resolve()
    else:
        root = (project_root / DEFAULT_STATE_DIR).resolve()

    if root == project_root:
        raise ValueError("refusing to use project root as AI Plan Issue state dir")
    if not path_is_relative_to(root, project_root) and os.environ.get("AI_PLAN_ISSUE_ALLOW_EXTERNAL_DIR") != "1":
        raise ValueError(f"AI_PLAN_ISSUE_DIR is outside project root: {root}")
    return root


def issues_root(project_root: Path) -> Path:
    return state_root(project_root)


def index_path(project_root: Path) -> Path:
    return issues_root(project_root) / "index.json"


def write_lock_path(project_root: Path) -> Path:
    return state_root(project_root) / "issues.lock"


def database_path(project_root: Path) -> Path:
    return issues_root(project_root) / "ai-plan-issue.db"


def token_path(project_root: Path) -> Path:
    return issues_root(project_root) / "ai-plan-issue.token"


def get_project_token(project_root: Path) -> str:
    path = token_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(32)
    path.write_text(token + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return token


def connect_db(project_root: Path) -> sqlite3.Connection:
    path = database_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, isolation_level=None, factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_realtime_db(project_root: Path) -> None:
    with connect_db(project_root) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS issues (
              id TEXT PRIMARY KEY,
              data TEXT NOT NULL,
              revision INTEGER NOT NULL DEFAULT 1,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS comments (
              id TEXT PRIMARY KEY,
              issue_id TEXT NOT NULL,
              ts TEXT NOT NULL,
              author TEXT NOT NULL,
              body TEXT NOT NULL,
              data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS activity (
              id TEXT PRIMARY KEY,
              issue_id TEXT NOT NULL,
              ts TEXT NOT NULL,
              author TEXT NOT NULL,
              action TEXT NOT NULL,
              body TEXT NOT NULL,
              data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
              seq INTEGER PRIMARY KEY AUTOINCREMENT,
              id TEXT UNIQUE NOT NULL,
              event_type TEXT NOT NULL,
              ts TEXT NOT NULL,
              actor TEXT NOT NULL,
              issue_id TEXT,
              revision INTEGER,
              payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS presence (
              actor TEXT PRIMARY KEY,
              display_name TEXT NOT NULL,
              kind TEXT NOT NULL,
              issue_id TEXT,
              updated_at TEXT NOT NULL
            );
            """
        )


def realtime_issue_count(project_root: Path) -> int:
    init_realtime_db(project_root)
    with connect_db(project_root) as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM issues").fetchone()
        return int(row["count"] if row else 0)


def json_dumps(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def issue_from_row(row: sqlite3.Row) -> dict:
    issue = json.loads(row["data"])
    issue["revision"] = int(row["revision"])
    return issue


def issue_rows(project_root: Path) -> list[dict]:
    init_realtime_db(project_root)
    with connect_db(project_root) as conn:
        rows = conn.execute("SELECT data, revision FROM issues ORDER BY id").fetchall()
    issues = [issue_from_row(row) for row in rows]
    return sorted(issues, key=lambda issue: ((issue.get("parent_id") or issue["id"]), issue.get("order", 0), issue["id"]))


def realtime_index(project_root: Path) -> dict:
    return {"schema_version": SCHEMA_VERSION, "api_version": API_VERSION, "issues": issue_rows(project_root)}
