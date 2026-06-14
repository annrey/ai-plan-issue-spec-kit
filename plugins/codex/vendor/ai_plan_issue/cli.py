"""Command-line entrypoint for AI Plan Issue."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import ledger


def print_json(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_generate(args: argparse.Namespace) -> int:
    root = ledger.project_root_from(Path(args.project_root) if args.project_root else None)
    feature_dir = Path(args.feature_dir).resolve() if args.feature_dir else None
    tasks_file = Path(args.tasks).resolve() if args.tasks else None
    index = ledger.generate_issues(root, feature_dir, args.force, args.prefix, tasks_file=tasks_file)
    ledger.import_ledger_to_db(root, force=True)
    parents = [i for i in index["issues"] if i["issue_type"] == "parent"]
    children = [i for i in index["issues"] if i.get("parent_id")]
    print(f"Generated {len(index['issues'])} issues ({len(parents)} parent, {len(children)} child).")
    print(f"Index: {ledger.index_path(root)}")
    print(f"Board: {ledger.issues_root(root) / 'board.md'}")
    print(f"Database: {ledger.database_path(root)}")
    return 0


def cmd_comment(args: argparse.Namespace) -> int:
    root = ledger.project_root_from(Path(args.project_root) if args.project_root else None)
    body = " ".join(args.body).strip()
    if not body:
        raise ValueError("Comment body is required.")
    payload = ledger.realtime_append_comment(root, args.issue_id, body, args.author, expected_revision=args.expected_revision)
    print_json(payload)
    return 0


def cmd_split(args: argparse.Namespace) -> int:
    root = ledger.project_root_from(Path(args.project_root) if args.project_root else None)
    created = ledger.realtime_split_issue(
        root,
        args.parent_id,
        args.child_titles,
        args.author,
        expected_parent_revision=args.expected_parent_revision,
    )
    print_json({"created": created})
    return 0


def cmd_claim(args: argparse.Namespace) -> int:
    root = ledger.project_root_from(Path(args.project_root) if args.project_root else None)
    issue = ledger.realtime_claim_issue(
        root,
        args.issue_id,
        args.agent,
        args.ttl_minutes,
        args.force,
        expected_revision=args.expected_revision,
    )
    print_json(issue)
    return 0


def cmd_assign(args: argparse.Namespace) -> int:
    root = ledger.project_root_from(Path(args.project_root) if args.project_root else None)
    issue = ledger.realtime_assign_issue(root, args.issue_id, args.assignee, author=args.author, expected_revision=args.expected_revision)
    print_json(issue)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    root = ledger.project_root_from(Path(args.project_root) if args.project_root else None)
    issue = ledger.realtime_update_issue_fields(
        root,
        args.issue_id,
        {"status": args.status},
        author=args.author,
        expected_revision=args.expected_revision,
    )
    print_json(issue)
    return 0


def cmd_note(args: argparse.Namespace) -> int:
    root = ledger.project_root_from(Path(args.project_root) if args.project_root else None)
    body = " ".join(args.body).strip()
    issue = ledger.realtime_update_implementation_notes(
        root,
        args.issue_id,
        body,
        author=args.author,
        expected_revision=args.expected_revision,
        append=not args.replace,
    )
    print_json(issue)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    root = ledger.project_root_from(Path(args.project_root) if args.project_root else None)
    detail = ledger.realtime_prepare_run(
        root,
        args.issue_id,
        agent=args.agent,
        ttl_minutes=args.ttl_minutes,
        force=args.force,
        expected_revision=args.expected_revision,
        claim=not args.no_claim,
    )
    print_json(detail)
    return 0


def cmd_detail(args: argparse.Namespace) -> int:
    root = ledger.project_root_from(Path(args.project_root) if args.project_root else None)
    print_json(ledger.realtime_load_issue_detail(root, args.issue_id))
    return 0


def add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", dest="json_output", help="Emit machine-readable JSON errors.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the AI Plan Issue ledger.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="Generate issues from tasks.md")
    add_json_flag(generate)
    generate.add_argument("--project-root")
    generate.add_argument("--feature-dir")
    generate.add_argument("--tasks", help="Path to a tasks.md file. Overrides --feature-dir.")
    generate.add_argument("--force", action="store_true")
    generate.add_argument("--prefix", default=ledger.DEFAULT_PREFIX)
    generate.set_defaults(func=cmd_generate)

    comment = subparsers.add_parser("comment", help="Append a comment")
    add_json_flag(comment)
    comment.add_argument("--project-root")
    comment.add_argument("--author", default="user")
    comment.add_argument("--expected-revision", type=int)
    comment.add_argument("issue_id")
    comment.add_argument("body", nargs=argparse.REMAINDER)
    comment.set_defaults(func=cmd_comment)

    split = subparsers.add_parser("split", help="Split an issue into children")
    add_json_flag(split)
    split.add_argument("--project-root")
    split.add_argument("--author", default="system")
    split.add_argument("--expected-parent-revision", type=int)
    split.add_argument("parent_id")
    split.add_argument("child_titles", nargs="+")
    split.set_defaults(func=cmd_split)

    claim = subparsers.add_parser("claim", help="Claim an issue")
    add_json_flag(claim)
    claim.add_argument("--project-root")
    claim.add_argument("--agent", required=True)
    claim.add_argument("--ttl-minutes", type=int, default=120)
    claim.add_argument("--force", action="store_true")
    claim.add_argument("--expected-revision", type=int)
    claim.add_argument("issue_id")
    claim.set_defaults(func=cmd_claim)

    assign = subparsers.add_parser("assign", help="Assign an issue")
    add_json_flag(assign)
    assign.add_argument("--project-root")
    assign.add_argument("--author", default="system")
    assign.add_argument("--expected-revision", type=int)
    assign.add_argument("issue_id")
    assign.add_argument("assignee")
    assign.set_defaults(func=cmd_assign)

    status = subparsers.add_parser("status", help="Update issue status")
    add_json_flag(status)
    status.add_argument("--project-root")
    status.add_argument("--author", default="system")
    status.add_argument("--expected-revision", type=int)
    status.add_argument("issue_id")
    status.add_argument("status", choices=sorted(ledger.VALID_STATUSES))
    status.set_defaults(func=cmd_status)

    note = subparsers.add_parser("note", help="Append implementation notes")
    add_json_flag(note)
    note.add_argument("--project-root")
    note.add_argument("--author", default="system")
    note.add_argument("--expected-revision", type=int)
    note.add_argument("--replace", action="store_true", help="Replace implementation notes instead of appending.")
    note.add_argument("issue_id")
    note.add_argument("body", nargs=argparse.REMAINDER)
    note.set_defaults(func=cmd_note)

    run = subparsers.add_parser("run", help="Prepare an issue for agent execution")
    add_json_flag(run)
    run.add_argument("--project-root")
    run.add_argument("--agent", default="codex-local")
    run.add_argument("--ttl-minutes", type=int, default=120)
    run.add_argument("--force", action="store_true")
    run.add_argument("--no-claim", action="store_true")
    run.add_argument("--expected-revision", type=int)
    run.add_argument("issue_id")
    run.set_defaults(func=cmd_run)

    detail = subparsers.add_parser("detail", help="Print issue detail")
    add_json_flag(detail)
    detail.add_argument("--project-root")
    detail.add_argument("issue_id")
    detail.set_defaults(func=cmd_detail)

    return parser


def exception_to_error(exc: Exception) -> tuple[int, str]:
    if isinstance(exc, ledger.ConflictError):
        return 3, "conflict"
    if isinstance(exc, KeyError):
        return 4, "not_found"
    if isinstance(exc, (ValueError, FileNotFoundError)):
        return 2, "invalid_request"
    return 1, "runtime_error"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001 - CLI should print concise failures.
        exit_code, code = exception_to_error(exc)
        if getattr(args, "json_output", False):
            print_json(
                {
                    "ok": False,
                    "error": {
                        "code": code,
                        "type": exc.__class__.__name__,
                        "message": str(exc),
                    },
                }
            )
        else:
            print(f"ai-plan-issue: {exc}", file=sys.stderr)
        return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
