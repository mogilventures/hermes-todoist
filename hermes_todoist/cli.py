"""Robust local Todoist CLI for Hermes.

The CLI is intentionally token-based (direct environment value, mounted secret
file, or ``~/.config/todoist/env``), so Hermes can use Todoist without the
hosted OAuth MCP startup flow.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from . import __version__, tools
from .client import TodoistClient, TodoistError

Json = dict[str, Any]


def _print(obj: object) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False, default=str))


def _payload(raw: str) -> Json:
    return json.loads(raw)


def _emit(payload: Json) -> int:
    _print(payload)
    return 0 if payload.get("success", True) is True else 1


def _labels(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    out: list[str] = []
    for value in values:
        out.extend(part.strip() for part in value.split(",") if part.strip())
    return out or None


def _task_params(args: argparse.Namespace, *, include_content: bool = False) -> Json:
    params: Json = {
        "description": getattr(args, "description", None),
        "project": getattr(args, "project", None),
        "project_id": getattr(args, "project_id", None),
        "section": getattr(args, "section", None),
        "section_id": getattr(args, "section_id", None),
        "parent_id": getattr(args, "parent_id", None),
        "order": getattr(args, "order", None),
        "labels": _labels(getattr(args, "label", None)),
        "priority": getattr(args, "priority", None),
        "due": getattr(args, "due", None),
        "due_date": getattr(args, "due_date", None),
        "due_datetime": getattr(args, "due_datetime", None),
        "lang": getattr(args, "lang", None),
        "assignee_id": getattr(args, "assignee_id", None),
        "duration": getattr(args, "duration", None),
        "duration_unit": getattr(args, "duration_unit", None),
    }
    if include_content:
        params["content"] = args.content
    return {k: v for k, v in params.items() if v is not None}


def _cmd_ping(_args: argparse.Namespace) -> int:
    client = TodoistClient()
    resp = client.list_projects(limit=1)
    _print({"success": True, "raw": resp})
    return 0


def _cmd_tools(_args: argparse.Namespace) -> int:
    _print([entry["name"] for entry in tools.TOOL_REGISTRY])
    return 0


def _cmd_mcp(_args: argparse.Namespace) -> int:
    from . import mcp_server

    return mcp_server.main()


def _cmd_version(_args: argparse.Namespace) -> int:
    print(__version__)
    return 0


def _cmd_projects(args: argparse.Namespace) -> int:
    return _emit(_payload(tools.todoist_list_projects({"limit": args.limit, "cursor": args.cursor})))


def _cmd_project_add(args: argparse.Namespace) -> int:
    client = TodoistClient()
    project = client.create_project(
        {"name": args.name, "color": args.color, "parent_id": args.parent_id, "is_favorite": args.favorite}
    )
    return _emit({"success": True, "action": "created", "project": project})


def _cmd_project_update(args: argparse.Namespace) -> int:
    client = TodoistClient()
    project = client.update_project(
        args.project_id,
        {"name": args.name, "color": args.color, "is_favorite": args.favorite, "view_style": args.view_style},
    )
    return _emit({"success": True, "action": "updated", "project": project})


def _cmd_project_delete(args: argparse.Namespace) -> int:
    if not args.yes:
        return _emit(
            {
                "success": False,
                "code": "confirmation_required",
                "error": "Project delete refused: pass --yes after resolving the exact project ID.",
                "project_id": args.project_id,
            }
        )
    TodoistClient().delete_project(args.project_id)
    return _emit({"success": True, "action": "deleted", "project_id": args.project_id})


def _cmd_sections(args: argparse.Namespace) -> int:
    return _emit(
        _payload(
            tools.todoist_list_sections(
                {"project": args.project, "project_id": args.project_id, "limit": args.limit, "cursor": args.cursor}
            )
        )
    )


def _cmd_section_add(args: argparse.Namespace) -> int:
    project_id = args.project_id
    if not project_id and args.project:
        project_id, _ = tools._resolve_project(TodoistClient(), args.project)  # noqa: SLF001 - CLI glue
    if not project_id:
        return _emit({"success": False, "error": "project or project_id is required"})
    section = TodoistClient().create_section({"name": args.name, "project_id": project_id, "order": args.order})
    return _emit({"success": True, "action": "created", "section": section})


def _cmd_section_update(args: argparse.Namespace) -> int:
    section = TodoistClient().update_section(args.section_id, {"name": args.name})
    return _emit({"success": True, "action": "updated", "section": section})


def _cmd_section_delete(args: argparse.Namespace) -> int:
    if not args.yes:
        return _emit(
            {
                "success": False,
                "code": "confirmation_required",
                "error": "Section delete refused: pass --yes after resolving the exact section ID.",
                "section_id": args.section_id,
            }
        )
    TodoistClient().delete_section(args.section_id)
    return _emit({"success": True, "action": "deleted", "section_id": args.section_id})


def _cmd_labels(args: argparse.Namespace) -> int:
    return _emit(_payload(tools.todoist_list_labels({"limit": args.limit, "cursor": args.cursor})))


def _cmd_label_add(args: argparse.Namespace) -> int:
    label = TodoistClient().create_label(
        {"name": args.name, "color": args.color, "order": args.order, "is_favorite": args.favorite}
    )
    return _emit({"success": True, "action": "created", "label": label})


def _cmd_label_update(args: argparse.Namespace) -> int:
    label = TodoistClient().update_label(
        args.label_id,
        {"name": args.name, "color": args.color, "order": args.order, "is_favorite": args.favorite},
    )
    return _emit({"success": True, "action": "updated", "label": label})


def _cmd_label_delete(args: argparse.Namespace) -> int:
    if not args.yes:
        return _emit(
            {
                "success": False,
                "code": "confirmation_required",
                "error": "Label delete refused: pass --yes after resolving the exact label ID.",
                "label_id": args.label_id,
            }
        )
    TodoistClient().delete_label(args.label_id)
    return _emit({"success": True, "action": "deleted", "label_id": args.label_id})


def _cmd_list(args: argparse.Namespace) -> int:
    ids: list[str] | None = None
    if args.ids:
        ids = []
        for value in args.ids:
            ids.extend(part.strip() for part in value.split(",") if part.strip())
    return _emit(
        _payload(
            tools.todoist_list_tasks(
                {
                    "project": args.project,
                    "project_id": args.project_id,
                    "section": args.section,
                    "section_id": args.section_id,
                    "parent_id": args.parent_id,
                    "label": args.label,
                    "filter": args.filter,
                    "lang": args.lang,
                    "ids": ids,
                    "limit": args.limit,
                    "cursor": args.cursor,
                }
            )
        )
    )


def _cmd_get(args: argparse.Namespace) -> int:
    return _emit(_payload(tools.todoist_get_task({"task_id": args.task_id})))


def _cmd_add(args: argparse.Namespace) -> int:
    return _emit(_payload(tools.todoist_create_task(_task_params(args, include_content=True))))


def _cmd_upsert(args: argparse.Namespace) -> int:
    return _emit(_payload(tools.todoist_create_or_update_task(_task_params(args, include_content=True))))


def _cmd_quick(args: argparse.Namespace) -> int:
    text = args.text
    if args.due:
        text = f"{text} {args.due}"
    client = TodoistClient()
    task = client.quick_add_task(
        {
            "text": text,
            "note": args.note,
            "reminder": args.reminder,
            "auto_reminder": args.auto_reminder,
        }
    )
    return _emit({"success": True, "action": "quick_added", "task": task})


def _cmd_update(args: argparse.Namespace) -> int:
    params = _task_params(args, include_content=bool(args.content))
    params["task_id"] = args.task_id
    return _emit(_payload(tools.todoist_update_task(params)))


def _cmd_move(args: argparse.Namespace) -> int:
    payload = {"project_id": args.project_id, "section_id": args.section_id, "parent_id": args.parent_id}
    if sum(1 for v in payload.values() if v) != 1:
        return _emit({"success": False, "error": "Set exactly one of --project-id, --section-id, or --parent-id"})
    task = TodoistClient().move_task(args.task_id, payload)
    return _emit({"success": True, "action": "moved", "task": task})


def _cmd_complete(args: argparse.Namespace) -> int:
    return _emit(_payload(tools.todoist_complete_task({"task_id": args.task_id})))


def _cmd_reopen(args: argparse.Namespace) -> int:
    return _emit(_payload(tools.todoist_reopen_task({"task_id": args.task_id})))


def _cmd_delete(args: argparse.Namespace) -> int:
    return _emit(_payload(tools.todoist_delete_task({"task_id": args.task_id, "confirm": args.yes})))


def _cmd_comments(args: argparse.Namespace) -> int:
    return _emit(
        _payload(
            tools.todoist_list_comments(
                {"task_id": args.task_id, "project": args.project, "project_id": args.project_id, "limit": args.limit, "cursor": args.cursor}
            )
        )
    )


def _cmd_comment_add(args: argparse.Namespace) -> int:
    return _emit(
        _payload(
            tools.todoist_add_comment(
                {"task_id": args.task_id, "project": args.project, "project_id": args.project_id, "content": args.content}
            )
        )
    )


def _cmd_dups(args: argparse.Namespace) -> int:
    return _emit(_payload(tools.todoist_find_duplicate_tasks({"project": args.project, "project_id": args.project_id, "label": args.label})))


def _add_common_task_args(sp: argparse.ArgumentParser, *, content: bool) -> None:
    if content:
        sp.add_argument("content")
    sp.add_argument("--description")
    sp.add_argument("--project", help="Project name or ID")
    sp.add_argument("--project-id")
    sp.add_argument("--section", help="Section name or ID")
    sp.add_argument("--section-id")
    sp.add_argument("--parent-id")
    sp.add_argument("--order", type=int)
    sp.add_argument("--label", action="append", help="Label; may be repeated or comma-separated")
    sp.add_argument("--priority", type=int, choices=[1, 2, 3, 4], help="Todoist priority: 4 highest, 1 normal")
    sp.add_argument("--due", help='Natural language due date, e.g. "tomorrow 9am"')
    sp.add_argument("--due-date", help="YYYY-MM-DD due date")
    sp.add_argument("--due-datetime", help="RFC3339 due datetime")
    sp.add_argument("--lang", default="en")
    sp.add_argument("--assignee-id")
    sp.add_argument("--duration", type=int, help="Task duration for calendar time-blocking")
    sp.add_argument("--duration-unit", choices=["minute", "day"], help="Unit for --duration")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="todoist",
        description="Local token-based Todoist CLI for Hermes (no hosted MCP OAuth).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("ping", help="Verify token by calling /projects?limit=1")
    sp.set_defaults(func=_cmd_ping)

    sp = sub.add_parser("tools", help="List local plugin tool names")
    sp.set_defaults(func=_cmd_tools)

    sp = sub.add_parser("mcp", help="Run the local stdio MCP server")
    sp.set_defaults(func=_cmd_mcp)

    sp = sub.add_parser("version", help="Print package version")
    sp.set_defaults(func=_cmd_version)

    sp = sub.add_parser("projects")
    sp.add_argument("--limit", type=int)
    sp.add_argument("--cursor")
    sp.set_defaults(func=_cmd_projects)

    sp = sub.add_parser("project-add")
    sp.add_argument("name")
    sp.add_argument("--color")
    sp.add_argument("--parent-id")
    sp.add_argument("--favorite", action="store_true")
    sp.set_defaults(func=_cmd_project_add)

    sp = sub.add_parser("project-update")
    sp.add_argument("project_id")
    sp.add_argument("--name")
    sp.add_argument("--color")
    sp.add_argument("--favorite", action="store_true")
    sp.add_argument("--view-style", choices=["list", "board", "calendar"])
    sp.set_defaults(func=_cmd_project_update)

    sp = sub.add_parser("project-delete")
    sp.add_argument("project_id")
    sp.add_argument("--yes", action="store_true")
    sp.set_defaults(func=_cmd_project_delete)

    sp = sub.add_parser("sections")
    sp.add_argument("--project")
    sp.add_argument("--project-id")
    sp.add_argument("--limit", type=int)
    sp.add_argument("--cursor")
    sp.set_defaults(func=_cmd_sections)

    sp = sub.add_parser("section-add")
    sp.add_argument("name")
    sp.add_argument("--project")
    sp.add_argument("--project-id")
    sp.add_argument("--order", type=int)
    sp.set_defaults(func=_cmd_section_add)

    sp = sub.add_parser("section-update")
    sp.add_argument("section_id")
    sp.add_argument("--name", required=True)
    sp.set_defaults(func=_cmd_section_update)

    sp = sub.add_parser("section-delete")
    sp.add_argument("section_id")
    sp.add_argument("--yes", action="store_true")
    sp.set_defaults(func=_cmd_section_delete)

    sp = sub.add_parser("labels")
    sp.add_argument("--limit", type=int)
    sp.add_argument("--cursor")
    sp.set_defaults(func=_cmd_labels)

    sp = sub.add_parser("label-add")
    sp.add_argument("name")
    sp.add_argument("--color")
    sp.add_argument("--order", type=int)
    sp.add_argument("--favorite", action="store_true")
    sp.set_defaults(func=_cmd_label_add)

    sp = sub.add_parser("label-update")
    sp.add_argument("label_id")
    sp.add_argument("--name")
    sp.add_argument("--color")
    sp.add_argument("--order", type=int)
    sp.add_argument("--favorite", action="store_true")
    sp.set_defaults(func=_cmd_label_update)

    sp = sub.add_parser("label-delete")
    sp.add_argument("label_id")
    sp.add_argument("--yes", action="store_true")
    sp.set_defaults(func=_cmd_label_delete)

    sp = sub.add_parser("list")
    sp.add_argument("--project")
    sp.add_argument("--project-id")
    sp.add_argument("--section")
    sp.add_argument("--section-id")
    sp.add_argument("--parent-id")
    sp.add_argument("--label")
    sp.add_argument("--filter", help='Todoist filter, e.g. "today | overdue"')
    sp.add_argument("--lang", default="en")
    sp.add_argument("--ids", nargs="*")
    sp.add_argument("--limit", type=int)
    sp.add_argument("--cursor")
    sp.set_defaults(func=_cmd_list)

    sp = sub.add_parser("get")
    sp.add_argument("task_id")
    sp.set_defaults(func=_cmd_get)

    sp = sub.add_parser("add")
    _add_common_task_args(sp, content=True)
    sp.set_defaults(func=_cmd_add)

    sp = sub.add_parser("upsert", help="Create task or update same-content open duplicate")
    _add_common_task_args(sp, content=True)
    sp.set_defaults(func=_cmd_upsert)

    sp = sub.add_parser("quick", help="Use Todoist Quick Add parsing via /tasks/quick")
    sp.add_argument("text")
    sp.add_argument("--due", help="Optional natural-language due text appended to quick-add text")
    sp.add_argument("--note")
    sp.add_argument("--reminder")
    sp.add_argument("--auto-reminder", action="store_true")
    sp.set_defaults(func=_cmd_quick)

    sp = sub.add_parser("update")
    sp.add_argument("task_id")
    sp.add_argument("--content")
    _add_common_task_args(sp, content=False)
    sp.set_defaults(func=_cmd_update)

    sp = sub.add_parser("move")
    sp.add_argument("task_id")
    sp.add_argument("--project-id")
    sp.add_argument("--section-id")
    sp.add_argument("--parent-id")
    sp.set_defaults(func=_cmd_move)

    sp = sub.add_parser("complete")
    sp.add_argument("task_id")
    sp.set_defaults(func=_cmd_complete)

    sp = sub.add_parser("reopen")
    sp.add_argument("task_id")
    sp.set_defaults(func=_cmd_reopen)

    sp = sub.add_parser("delete")
    sp.add_argument("task_id")
    sp.add_argument("--yes", action="store_true", help="Required for irreversible delete")
    sp.set_defaults(func=_cmd_delete)

    sp = sub.add_parser("comments")
    target = sp.add_mutually_exclusive_group(required=True)
    target.add_argument("--task-id")
    target.add_argument("--project")
    sp.add_argument("--project-id")
    sp.add_argument("--limit", type=int)
    sp.add_argument("--cursor")
    sp.set_defaults(func=_cmd_comments)

    sp = sub.add_parser("comment-add")
    target = sp.add_mutually_exclusive_group(required=True)
    target.add_argument("--task-id")
    target.add_argument("--project")
    sp.add_argument("--project-id")
    sp.add_argument("content")
    sp.set_defaults(func=_cmd_comment_add)

    sp = sub.add_parser("dups")
    sp.add_argument("--project")
    sp.add_argument("--project-id")
    sp.add_argument("--label")
    sp.set_defaults(func=_cmd_dups)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except TodoistError as exc:
        _print({"success": False, "code": "client_error", "error": str(exc)})
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
