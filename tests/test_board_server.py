from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import error, request

import pytest

from ai_plan_issue import board_server, ledger


TASKS_MD = """# Tasks

## Phase 1: Board foundation

- [ ] T001 Create issue data model
"""


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


@pytest.fixture()
def board(tmp_path: Path):
    tasks = tmp_path / "tasks.md"
    tasks.write_text(TASKS_MD, encoding="utf-8")
    ledger.generate_issues(tmp_path, None, force=True, tasks_file=tasks)
    ledger.import_ledger_to_db(tmp_path, force=True)
    token = ledger.get_project_token(tmp_path)

    class TestHandler(board_server.BoardHandler):
        pass

    TestHandler.project_root = tmp_path
    TestHandler.project_token = token
    TestHandler.web_root = Path(board_server.__file__).resolve().parent / "web"
    TestHandler.read_requires_auth = True

    server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {
            "base": f"http://127.0.0.1:{server.server_port}",
            "token": token,
            "project_root": tmp_path,
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def request_json(base: str, path: str, *, method: str = "GET", token: str | None = None, payload: dict | None = None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(base + path, data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_http_token_auth_and_cookie_login(board) -> None:
    base = board["base"]
    token = board["token"]

    status, session = request_json(base, "/api/v1/session")
    assert status == 200
    assert session["authenticated"] is False
    assert session["read_requires_auth"] is True

    status, payload = request_json(base, "/api/v1/issues")
    assert status == 401
    assert payload["error"] == "Project token required"

    opener = request.build_opener(NoRedirect)
    try:
        opener.open(f"{base}/?token={token}", timeout=5)
    except error.HTTPError as exc:
        assert exc.code == 302
        assert "ai_plan_issue_token=" in exc.headers["Set-Cookie"]
        assert exc.headers["Location"] == "/"
    else:
        raise AssertionError("Expected token login redirect")

    status, payload = request_json(base, "/api/v1/issues", token=token)
    assert status == 200
    assert payload["api_version"] == "1.0"
    assert len(payload["issues"]) == 2

    status, payload = request_json(
        base,
        "/api/v1/issues/AI-001-01/comments",
        method="POST",
        payload={"body": "unauthorized"},
    )
    assert status == 401
    assert payload["error"] == "Project token required"


def test_http_rejects_empty_patch_invalid_claim_ttl_and_revision_conflicts(board) -> None:
    base = board["base"]
    token = board["token"]

    before = ledger.realtime_find_issue(board["project_root"], "AI-001-01")
    status, payload = request_json(base, "/api/v1/issues/AI-001-01", method="PATCH", token=token, payload={})
    after = ledger.realtime_find_issue(board["project_root"], "AI-001-01")
    assert status == 400
    assert payload["error"] == "No editable issue fields provided."
    assert after["revision"] == before["revision"]

    status, payload = request_json(
        base,
        "/api/v1/issues/AI-001-01/claim",
        method="POST",
        token=token,
        payload={"agent": "codex-local", "ttl_minutes": 0},
    )
    issue = ledger.realtime_find_issue(board["project_root"], "AI-001-01")
    assert status == 400
    assert payload["error"] == "Claim ttl_minutes must be positive."
    assert issue["claimed_by"] is None

    status, payload = request_json(
        base,
        "/api/v1/issues/AI-001-01/comments",
        method="POST",
        token=token,
        payload={"body": "stale", "expected_revision": issue["revision"] - 1},
    )
    assert status == 409
    assert "Stale issue revision" in payload["error"]


def test_sse_resumes_after_last_event_id(board) -> None:
    project_root = board["project_root"]
    token = board["token"]
    base = board["base"]
    last_id = ledger.realtime_events_since(project_root)[-1]["id"]

    ledger.realtime_append_comment(project_root, "AI-001-01", "SSE update", "codex-local")

    req = request.Request(base + "/api/v1/events", headers={"Authorization": f"Bearer {token}", "Last-Event-ID": last_id})
    with request.urlopen(req, timeout=5) as response:
        chunks: list[str] = []
        while True:
            line = response.readline().decode("utf-8")
            chunks.append(line)
            if line == "\n" and any("event: comment.created" in item for item in chunks):
                break

    stream = "".join(chunks)
    assert "event: comment.created" in stream
    assert "SSE update" in stream
