#!/usr/bin/env python3
"""Realtime web board for AI Plan Issue."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlparse

from . import events, ledger


class BoardHandler(BaseHTTPRequestHandler):
    project_root: Path
    project_token: str
    web_root: Path
    read_requires_auth: bool

    server_version = "AIPlanIssueBoard/1.0"

    def handle(self) -> None:
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_json(
        self,
        payload: object,
        status: HTTPStatus = HTTPStatus.OK,
        headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message}, status=status)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        data = self.rfile.read(length)
        value = json.loads(data.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Expected JSON object")
        return value

    def _cookie_token(self) -> str | None:
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        cookie = SimpleCookie()
        cookie.load(raw)
        morsel = cookie.get("ai_plan_issue_token")
        return morsel.value if morsel else None

    def _auth_token(self, query: dict[str, list[str]] | None = None) -> str | None:
        authorization = self.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            return authorization.removeprefix("Bearer ").strip()
        if query and query.get("token"):
            return query["token"][0]
        return self._cookie_token()

    def _is_authenticated(self, query: dict[str, list[str]] | None = None) -> bool:
        return self._auth_token(query) == self.project_token

    def _require_read_auth(self, query: dict[str, list[str]] | None = None) -> bool:
        if not self.read_requires_auth:
            return True
        return self._is_authenticated(query)

    def _require_write_auth(self, query: dict[str, list[str]] | None = None) -> bool:
        return self._is_authenticated(query)

    def _maybe_accept_token(self, parsed) -> bool:
        query = parse_qs(parsed.query)
        if "token" not in query:
            return False
        if not self._is_authenticated(query):
            self._send_error(HTTPStatus.UNAUTHORIZED, "Invalid project token")
            return True

        clean_query = {key: value for key, value in query.items() if key != "token"}
        suffix = f"?{urlencode(clean_query, doseq=True)}" if clean_query else ""
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", f"{parsed.path or '/'}{suffix}")
        self.send_header(
            "Set-Cookie",
            "ai_plan_issue_token="
            + self.project_token
            + "; Path=/; SameSite=Strict; HttpOnly",
        )
        self.end_headers()
        return True

    def _api_path(self, path: str) -> str | None:
        if path.startswith("/api/v1"):
            return path.removeprefix("/api/v1") or "/"
        if path.startswith("/api"):
            return path.removeprefix("/api") or "/"
        return None

    def _expected_revision(self, payload: dict, key: str = "expected_revision") -> int | None:
        if payload.get(key) is None:
            return None
        return int(payload[key])

    def _serve_static(self, path: str) -> None:
        if path in ("", "/"):
            target = self.web_root / "index.html"
        else:
            relative = unquote(path.lstrip("/"))
            target = (self.web_root / relative).resolve()
            try:
                target.relative_to(self.web_root.resolve())
            except ValueError:
                self._send_error(HTTPStatus.FORBIDDEN, "Forbidden")
                return
        if not target.exists() or not target.is_file():
            self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        content = target.read_bytes()
        mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _session_payload(self, authenticated: bool) -> dict:
        return {
            "api_version": ledger.API_VERSION,
            "authenticated": authenticated,
            "read_requires_auth": self.read_requires_auth,
            "write_requires_auth": True,
            "events_url": "/api/v1/events",
            "actors": events.realtime_list_presence(self.project_root),
        }

    def _stream_events(self, last_event_id: str | None) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        current_id = last_event_id
        try:
            while True:
                stream_events = events.realtime_events_since(self.project_root, current_id, limit=100)
                if not stream_events:
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
                    time.sleep(1)
                    continue
                for event in stream_events:
                    current_id = event["id"]
                    body = json.dumps(event, ensure_ascii=False)
                    self.wfile.write(f"id: {event['id']}\n".encode("utf-8"))
                    self.wfile.write(f"event: {event['type']}\n".encode("utf-8"))
                    self.wfile.write(f"data: {body}\n\n".encode("utf-8"))
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if self._maybe_accept_token(parsed):
            return
        path = parsed.path
        query = parse_qs(parsed.query)
        api_path = self._api_path(path)
        try:
            if api_path is not None:
                if api_path == "/session":
                    self._send_json(self._session_payload(self._is_authenticated(query)))
                    return
                if not self._require_read_auth(query):
                    self._send_error(HTTPStatus.UNAUTHORIZED, "Project token required")
                    return
                if api_path == "/issues":
                    self._send_json(ledger.realtime_load_index(self.project_root))
                    return
                if api_path == "/events":
                    self._stream_events(self.headers.get("Last-Event-ID"))
                    return
                if api_path.startswith("/issues/"):
                    issue_id = unquote(api_path.removeprefix("/issues/"))
                    self._send_json(ledger.realtime_load_issue_detail(self.project_root, issue_id))
                    return
                self._send_error(HTTPStatus.NOT_FOUND, "Not found")
                return
            self._serve_static(path)
        except Exception as exc:  # noqa: BLE001
            self._handle_exception(exc)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        api_path = self._api_path(parsed.path)
        if api_path is None:
            self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        if not self._require_write_auth(query):
            self._send_error(HTTPStatus.UNAUTHORIZED, "Project token required")
            return
        try:
            payload = self._read_json()
            if api_path == "/issues":
                issue = ledger.realtime_create_manual_issue(
                    self.project_root,
                    title=str(payload.get("title", "")).strip(),
                    summary=str(payload.get("summary", "")).strip(),
                    status=str(payload.get("status", "backlog")),
                    priority=str(payload.get("priority", "P2")),
                    parent_id=payload.get("parent_id"),
                    assignee=payload.get("assignee"),
                    module=payload.get("module"),
                    category=payload.get("category"),
                    author=str(payload.get("author", "web-board")),
                    expected_parent_revision=self._expected_revision(payload, "expected_parent_revision"),
                )
                self._send_json(issue, status=HTTPStatus.CREATED)
                return
            if api_path == "/import":
                index = ledger.import_ledger_to_db(self.project_root, force=bool(payload.get("force", True)))
                self._send_json(index)
                return
            if api_path == "/export":
                index = events.realtime_export(self.project_root, author=str(payload.get("author", "web-board")))
                self._send_json(index)
                return
            if api_path == "/presence":
                presence = events.realtime_update_presence(
                    self.project_root,
                    actor=str(payload.get("actor", "web-user")),
                    display_name=str(payload.get("display_name", payload.get("actor", "web-user"))),
                    kind=str(payload.get("kind", "human")),
                    issue_id=payload.get("issue_id"),
                )
                self._send_json(presence)
                return
            if api_path.startswith("/issues/") and api_path.endswith("/comments"):
                issue_id = unquote(api_path[len("/issues/") : -len("/comments")])
                comment = ledger.realtime_append_comment(
                    self.project_root,
                    issue_id,
                    str(payload.get("body", "")).strip(),
                    str(payload.get("author", "user")),
                    expected_revision=self._expected_revision(payload),
                )
                self._send_json(comment, status=HTTPStatus.CREATED)
                return
            if api_path.startswith("/issues/") and api_path.endswith("/claim"):
                issue_id = unquote(api_path[len("/issues/") : -len("/claim")])
                issue = ledger.realtime_claim_issue(
                    self.project_root,
                    issue_id,
                    str(payload.get("agent", "agent")),
                    int(payload.get("ttl_minutes", 120)),
                    bool(payload.get("force", False)),
                    expected_revision=self._expected_revision(payload),
                )
                self._send_json(issue)
                return
            if api_path.startswith("/issues/") and api_path.endswith("/assign"):
                issue_id = unquote(api_path[len("/issues/") : -len("/assign")])
                issue = ledger.realtime_assign_issue(
                    self.project_root,
                    issue_id,
                    str(payload.get("assignee", "")),
                    author=str(payload.get("author", "user")),
                    expected_revision=self._expected_revision(payload),
                )
                self._send_json(issue)
                return
            self._send_error(HTTPStatus.NOT_FOUND, "Not found")
        except Exception as exc:  # noqa: BLE001
            self._handle_exception(exc)

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        api_path = self._api_path(parsed.path)
        if api_path is None:
            self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        if not self._require_write_auth(query):
            self._send_error(HTTPStatus.UNAUTHORIZED, "Project token required")
            return
        try:
            payload = self._read_json()
            if api_path.startswith("/issues/"):
                issue_id = unquote(api_path.removeprefix("/issues/"))
                allowed = {"status", "priority", "assignee", "module", "category"}
                fields = {key: payload[key] for key in allowed if key in payload}
                issue = ledger.realtime_update_issue_fields(
                    self.project_root,
                    issue_id,
                    fields,
                    author=str(payload.get("author", "user")),
                    expected_revision=self._expected_revision(payload),
                )
                self._send_json(issue)
                return
            self._send_error(HTTPStatus.NOT_FOUND, "Not found")
        except Exception as exc:  # noqa: BLE001
            self._handle_exception(exc)

    def _handle_exception(self, exc: Exception) -> None:
        if isinstance(exc, ledger.ConflictError):
            self._send_error(HTTPStatus.CONFLICT, str(exc))
            return
        if isinstance(exc, KeyError):
            self._send_error(HTTPStatus.NOT_FOUND, str(exc))
            return
        self._send_error(HTTPStatus.BAD_REQUEST, str(exc))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start the AI Plan Issue board.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--project-root")
    return parser


def read_requires_auth(host: str) -> bool:
    return host not in {"127.0.0.1", "localhost", "::1"}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = ledger.project_root_from(Path(args.project_root) if args.project_root else None)
    if not ledger.index_path(project_root).exists() and ledger.realtime_issue_count(project_root) == 0:
        print("ai-plan-issue: no issue ledger found. Run `ai-plan-issue generate` first.", file=sys.stderr)
        return 1

    index = ledger.ensure_realtime_store(project_root)
    token = ledger.get_project_token(project_root)
    BoardHandler.project_root = project_root
    BoardHandler.project_token = token
    BoardHandler.web_root = Path(__file__).resolve().parent / "web"
    BoardHandler.read_requires_auth = read_requires_auth(args.host)

    server = ThreadingHTTPServer((args.host, args.port), BoardHandler)
    url = f"http://{args.host}:{args.port}"
    token_url = f"{url}/?token={token}"
    print(f"AI Plan Issue board: {url}", flush=True)
    print(f"Authenticated URL: {token_url}", flush=True)
    print(f"Realtime store: {ledger.database_path(project_root)}", flush=True)
    print(f"Loaded {len(index.get('issues', []))} issues.", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
