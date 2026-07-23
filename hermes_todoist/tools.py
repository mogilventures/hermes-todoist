"""Tool handlers for the Hermes Todoist plugin.

Each handler accepts a `params` dict, returns a JSON-encoded string of the
shape `{"success": bool, ...}`, and never raises — errors are converted to
`{"success": false, "error": "..."}` responses.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from . import schemas
from .client import (
    TodoistAPIError,
    TodoistAuthError,
    TodoistClient,
    TodoistError,
    TodoistRateLimitError,
)

_client_instance: TodoistClient | None = None


def _client() -> TodoistClient:
    global _client_instance
    if _client_instance is None:
        _client_instance = TodoistClient()
    return _client_instance


def _set_client(client: TodoistClient | None) -> None:
    """Test seam: install (or clear) a client instance for the module."""
    global _client_instance
    _client_instance = client


def _ok(**fields: Any) -> str:
    payload: dict[str, Any] = {"success": True}
    payload.update(fields)
    return json.dumps(payload, ensure_ascii=False, default=str)


def _err(message: str, **extra: Any) -> str:
    payload: dict[str, Any] = {"success": False, "error": message}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False, default=str)


def _wrap(fn: Callable[[dict[str, Any]], str]) -> Callable[..., str]:
    """Decorator: catch known + unknown errors, return JSON-string errors."""

    def wrapper(params: dict[str, Any] | None = None, **kwargs: Any) -> str:
        del kwargs  # forward-compat
        try:
            return fn(params or {})
        except TodoistAuthError as exc:
            return _err(str(exc), code="auth_error")
        except TodoistRateLimitError as exc:
            return _err(str(exc), code="rate_limited", retry_after=exc.retry_after)
        except TodoistAPIError as exc:
            return _err(str(exc), code="api_error", status=exc.status)
        except TodoistError as exc:
            return _err(str(exc), code="client_error")
        except Exception as exc:  # final safety net — handlers must never raise
            return _err(f"unexpected error: {exc}", code="unexpected_error")

    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


def _unpack(resp: Any) -> tuple[list[Any], str | None]:
    """Normalize a Todoist response into (items, next_cursor)."""
    if isinstance(resp, dict) and isinstance(resp.get("results"), list):
        return list(resp["results"]), resp.get("next_cursor")
    if isinstance(resp, list):
        return list(resp), None
    if resp is None:
        return [], None
    return [resp], None


def _normalize_content(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _looks_like_id(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    v = value.strip()
    return bool(v) and v.isdigit()


def _collect_pages(
    fetch_page: Callable[[str | None], Any], *, max_pages: int = 20
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(max_pages):
        page, cursor = _unpack(fetch_page(cursor))
        items.extend(page)
        if not cursor:
            return items
    raise TodoistError(f"Lookup exceeded the safety limit of {max_pages} pages")


def _resolve_project(client: TodoistClient, value: Any) -> tuple[str | None, str | None]:
    if value in (None, ""):
        return None, None
    needle = str(value)
    items = _collect_pages(lambda cursor: client.list_projects(limit=200, cursor=cursor))
    for proj in items:
        if str(proj.get("id")) == needle:
            return str(proj["id"]), proj.get("name")
    lower = needle.lower()
    matches = [proj for proj in items if (proj.get("name") or "").lower() == lower]
    if len(matches) == 1:
        return str(matches[0]["id"]), matches[0].get("name")
    if len(matches) > 1:
        ids = ", ".join(str(proj.get("id")) for proj in matches)
        raise TodoistError(f"Project name is ambiguous: {needle!r} matches IDs {ids}")
    if _looks_like_id(needle):
        return needle, None
    raise TodoistError(f"Project not found: {needle!r}")


def _resolve_section(
    client: TodoistClient, value: Any, project_id: str | None = None
) -> tuple[str | None, str | None]:
    if value in (None, ""):
        return None, None
    needle = str(value)
    items = _collect_pages(
        lambda cursor: client.list_sections(project_id=project_id, limit=200, cursor=cursor)
    )
    for sec in items:
        if str(sec.get("id")) == needle:
            return str(sec["id"]), sec.get("name")
    lower = needle.lower()
    matches = [sec for sec in items if (sec.get("name") or "").lower() == lower]
    if len(matches) == 1:
        return str(matches[0]["id"]), matches[0].get("name")
    if len(matches) > 1:
        ids = ", ".join(str(sec.get("id")) for sec in matches)
        raise TodoistError(f"Section name is ambiguous: {needle!r} matches IDs {ids}")
    if _looks_like_id(needle):
        return needle, None
    raise TodoistError(f"Section not found: {needle!r}")


def _resolve_label(client: TodoistClient, value: Any) -> tuple[str | None, str | None]:
    if value in (None, ""):
        return None, None
    needle = str(value)
    items = _collect_pages(lambda cursor: client.list_labels(limit=200, cursor=cursor))
    for label in items:
        if str(label.get("id")) == needle:
            return str(label["id"]), label.get("name")
    lower = needle.lower()
    matches = [label for label in items if (label.get("name") or "").lower() == lower]
    if len(matches) == 1:
        return str(matches[0]["id"]), matches[0].get("name")
    if len(matches) > 1:
        ids = ", ".join(str(label.get("id")) for label in matches)
        raise TodoistError(f"Label name is ambiguous: {needle!r} matches IDs {ids}")
    if _looks_like_id(needle):
        return needle, None
    raise TodoistError(f"Label not found: {needle!r}")


def _require_confirmation(params: dict[str, Any], object_type: str, object_id: str) -> str | None:
    if params.get("confirm") is True:
        return None
    return _err(
        f"Delete refused: confirmation required for {object_type}. Pass confirm=true to delete.",
        code="confirmation_required",
        object_type=object_type,
        object_id=object_id,
    )


def _coerce_labels(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    return [str(value)]


def _build_task_payload(
    client: TodoistClient, params: dict[str, Any], *, include_routing: bool = True
) -> dict[str, Any]:
    """Translate user-facing params into a Todoist task payload."""
    project_id: str | None = None
    section_id: str | None = None
    if include_routing:
        project_in = params.get("project_id") or params.get("project")
        if project_in:
            if _looks_like_id(project_in):
                project_id = project_in
            else:
                project_id, _ = _resolve_project(client, project_in)
        section_in = params.get("section_id") or params.get("section")
        if section_in:
            if _looks_like_id(section_in):
                section_id = section_in
            else:
                section_id, _ = _resolve_section(client, section_in, project_id=project_id)

    payload: dict[str, Any] = {
        "content": params.get("content"),
        "description": params.get("description"),
        "labels": _coerce_labels(params.get("labels")),
        "priority": params.get("priority"),
        "due_string": params.get("due_string") or params.get("due"),
        "due_date": params.get("due_date"),
        "due_datetime": params.get("due_datetime"),
        "due_lang": params.get("due_lang") or params.get("lang"),
        "assignee_id": params.get("assignee_id"),
        "duration": params.get("duration"),
        "duration_unit": params.get("duration_unit"),
        "order": params.get("order"),
    }
    if include_routing:
        payload["project_id"] = project_id
        payload["section_id"] = section_id
        payload["parent_id"] = params.get("parent_id")
    return payload


# ---------- tool handlers ----------


@_wrap
def todoist_list_projects(params: dict[str, Any]) -> str:
    items, cursor = _unpack(
        _client().list_projects(limit=params.get("limit"), cursor=params.get("cursor"))
    )
    return _ok(projects=items, next_cursor=cursor, count=len(items))


@_wrap
def todoist_list_sections(params: dict[str, Any]) -> str:
    project_in = params.get("project_id") or params.get("project")
    project_id: str | None = None
    if project_in:
        if _looks_like_id(project_in):
            project_id = project_in
        else:
            project_id, _ = _resolve_project(_client(), project_in)
    items, cursor = _unpack(
        _client().list_sections(
            project_id=project_id, limit=params.get("limit"), cursor=params.get("cursor")
        )
    )
    return _ok(sections=items, next_cursor=cursor, count=len(items))


@_wrap
def todoist_list_labels(params: dict[str, Any]) -> str:
    items, cursor = _unpack(
        _client().list_labels(limit=params.get("limit"), cursor=params.get("cursor"))
    )
    return _ok(labels=items, next_cursor=cursor, count=len(items))


@_wrap
def todoist_get_label(params: dict[str, Any]) -> str:
    value = params.get("label_id") or params.get("label")
    if not value:
        return _err("label is required")
    label_id, _ = _resolve_label(_client(), value)
    return _ok(label=_client().get_label(str(label_id)))


@_wrap
def todoist_create_label(params: dict[str, Any]) -> str:
    if not params.get("name"):
        return _err("name is required")
    payload = {
        "name": params["name"],
        "order": params.get("order"),
        "color": params.get("color"),
        "is_favorite": params.get("is_favorite"),
    }
    return _ok(label=_client().create_label(payload), action="created")


@_wrap
def todoist_update_label(params: dict[str, Any]) -> str:
    value = params.get("label_id") or params.get("label")
    if not value:
        return _err("label is required")
    label_id, _ = _resolve_label(_client(), value)
    payload = {
        key: params.get(key)
        for key in ("name", "order", "color", "is_favorite")
        if key in params
    }
    if not payload:
        return _err("at least one label field is required", code="client_error")
    return _ok(label=_client().update_label(str(label_id), payload), action="updated")


@_wrap
def todoist_delete_label(params: dict[str, Any]) -> str:
    value = params.get("label_id") or params.get("label")
    if not value:
        return _err("label is required")
    label_id, name = _resolve_label(_client(), value)
    refusal = _require_confirmation(params, "label", str(label_id))
    if refusal:
        return refusal
    _client().delete_label(str(label_id))
    return _ok(label_id=str(label_id), label_name=name, action="deleted")


@_wrap
def todoist_list_tasks(params: dict[str, Any]) -> str:
    project_in = params.get("project_id") or params.get("project")
    project_id: str | None = None
    if project_in:
        if _looks_like_id(project_in):
            project_id = project_in
        else:
            project_id, _ = _resolve_project(_client(), project_in)

    section_in = params.get("section_id") or params.get("section")
    section_id: str | None = None
    if section_in:
        if _looks_like_id(section_in):
            section_id = section_in
        else:
            section_id, _ = _resolve_section(_client(), section_in, project_id=project_id)

    ids = params.get("ids")
    if isinstance(ids, str):
        ids = [s.strip() for s in ids.split(",") if s.strip()]

    items, cursor = _unpack(
        _client().list_tasks(
            project_id=project_id,
            section_id=section_id,
            parent_id=params.get("parent_id"),
            label=params.get("label"),
            filter_query=params.get("filter"),
            lang=params.get("lang"),
            ids=ids,
            limit=params.get("limit"),
            cursor=params.get("cursor"),
        )
    )
    return _ok(tasks=items, next_cursor=cursor, count=len(items))


@_wrap
def todoist_get_task(params: dict[str, Any]) -> str:
    task_id = params.get("task_id") or params.get("id")
    if not task_id:
        return _err("task_id is required")
    task = _client().get_task(str(task_id))
    return _ok(task=task)


@_wrap
def todoist_create_task(params: dict[str, Any]) -> str:
    content = params.get("content")
    if not content:
        return _err("content is required")
    payload = _build_task_payload(_client(), params)
    task = _client().create_task(payload)
    return _ok(task=task, action="created")


@_wrap
def todoist_update_task(params: dict[str, Any]) -> str:
    task_id = params.get("task_id") or params.get("id")
    if not task_id:
        return _err("task_id is required")
    payload = _build_task_payload(_client(), params, include_routing=False)
    task = _client().update_task(str(task_id), payload)
    return _ok(task=task, action="updated")


@_wrap
def todoist_move_task(params: dict[str, Any]) -> str:
    task_id = params.get("task_id") or params.get("id")
    if not task_id:
        return _err("task_id is required")
    destinations = [
        key for key in ("project", "section", "parent_id") if params.get(key) not in (None, "")
    ]
    if len(destinations) != 1:
        return _err(
            "exactly one of project, section, or parent_id is required",
            code="client_error",
        )
    payload: dict[str, Any] = {}
    if params.get("project"):
        project_id, _ = _resolve_project(_client(), params["project"])
        payload["project_id"] = project_id
    elif params.get("section"):
        project_scope = params.get("section_project")
        project_id = None
        if project_scope:
            project_id, _ = _resolve_project(_client(), project_scope)
        section_id, _ = _resolve_section(_client(), params["section"], project_id=project_id)
        payload["section_id"] = section_id
    else:
        payload["parent_id"] = str(params["parent_id"])
    task = _client().move_task(str(task_id), payload)
    return _ok(task=task, action="moved")


@_wrap
def todoist_reorder_tasks(params: dict[str, Any]) -> str:
    entries = params.get("tasks")
    if not isinstance(entries, list) or not entries:
        return _err("tasks must be a non-empty list", code="client_error")
    tasks: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("task_id") or "order" not in entry:
            return _err(
                "each task must contain task_id and order",
                code="client_error",
            )
        tasks.append({"id": str(entry["task_id"]), "child_order": entry["order"]})
    _client().reorder_tasks(tasks)
    return _ok(tasks=tasks, action="reordered")


@_wrap
def todoist_complete_task(params: dict[str, Any]) -> str:
    task_id = params.get("task_id") or params.get("id")
    if not task_id:
        return _err("task_id is required")
    _client().close_task(str(task_id))
    return _ok(task_id=str(task_id), action="completed")


@_wrap
def todoist_reopen_task(params: dict[str, Any]) -> str:
    task_id = params.get("task_id") or params.get("id")
    if not task_id:
        return _err("task_id is required")
    _client().reopen_task(str(task_id))
    return _ok(task_id=str(task_id), action="reopened")


@_wrap
def todoist_delete_task(params: dict[str, Any]) -> str:
    task_id = params.get("task_id") or params.get("id")
    if not task_id:
        return _err("task_id is required")
    if not params.get("confirm"):
        return _err(
            "Delete refused: confirmation required. Pass confirm=true to delete this task.",
            code="confirmation_required",
            task_id=str(task_id),
        )
    _client().delete_task(str(task_id))
    return _ok(task_id=str(task_id), action="deleted")


@_wrap
def todoist_get_project(params: dict[str, Any]) -> str:
    value = params.get("project_id") or params.get("project")
    if not value:
        return _err("project is required")
    project_id, _ = _resolve_project(_client(), value)
    return _ok(project=_client().get_project(str(project_id)))


@_wrap
def todoist_create_project(params: dict[str, Any]) -> str:
    if not params.get("name"):
        return _err("name is required")
    parent_id = None
    if params.get("parent"):
        parent_id, _ = _resolve_project(_client(), params["parent"])
    payload = {
        "name": params["name"],
        "description": params.get("description"),
        "parent_id": parent_id,
        "color": params.get("color"),
        "is_favorite": params.get("is_favorite"),
        "view_style": params.get("view_style"),
    }
    return _ok(project=_client().create_project(payload), action="created")


@_wrap
def todoist_update_project(params: dict[str, Any]) -> str:
    value = params.get("project_id") or params.get("project")
    if not value:
        return _err("project is required")
    project_id, _ = _resolve_project(_client(), value)
    payload = {
        key: params.get(key)
        for key in ("name", "description", "color", "is_favorite", "view_style")
        if key in params
    }
    if not payload:
        return _err("at least one project field is required", code="client_error")
    project = _client().update_project(str(project_id), payload)
    return _ok(project=project, action="updated")


@_wrap
def todoist_move_project(params: dict[str, Any]) -> str:
    value = params.get("project_id") or params.get("project")
    if not value:
        return _err("project is required")
    if "parent" not in params:
        return _err("parent is required; use null to move to the root", code="client_error")
    project_id, _ = _resolve_project(_client(), value)
    parent_id = None
    if params.get("parent"):
        parent_id, _ = _resolve_project(_client(), params["parent"])
    _client().move_project(str(project_id), parent_id)
    return _ok(project_id=str(project_id), parent_id=parent_id, action="moved")


@_wrap
def todoist_reorder_projects(params: dict[str, Any]) -> str:
    entries = params.get("projects")
    if not isinstance(entries, list) or not entries:
        return _err("projects must be a non-empty list", code="client_error")
    projects: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("project") or "order" not in entry:
            return _err(
                "each project must contain project and order",
                code="client_error",
            )
        project_id, _ = _resolve_project(_client(), entry["project"])
        projects.append({"id": project_id, "child_order": entry["order"]})
    _client().reorder_projects(projects)
    return _ok(projects=projects, action="reordered")


@_wrap
def todoist_archive_project(params: dict[str, Any]) -> str:
    value = params.get("project_id") or params.get("project")
    if not value:
        return _err("project is required")
    project_id, _ = _resolve_project(_client(), value)
    project = _client().archive_project(str(project_id))
    return _ok(project=project, project_id=str(project_id), action="archived")


@_wrap
def todoist_unarchive_project(params: dict[str, Any]) -> str:
    project_id = params.get("project_id") or params.get("id")
    if not project_id:
        return _err("project_id is required for archived projects")
    project = _client().unarchive_project(str(project_id))
    return _ok(project=project, project_id=str(project_id), action="unarchived")


@_wrap
def todoist_delete_project(params: dict[str, Any]) -> str:
    value = params.get("project_id") or params.get("project")
    if not value:
        return _err("project is required")
    project_id, name = _resolve_project(_client(), value)
    refusal = _require_confirmation(params, "project", str(project_id))
    if refusal:
        return refusal
    _client().delete_project(str(project_id))
    return _ok(project_id=str(project_id), project_name=name, action="deleted")


@_wrap
def todoist_get_section(params: dict[str, Any]) -> str:
    value = params.get("section_id") or params.get("section")
    if not value:
        return _err("section is required")
    project_id = None
    if params.get("project"):
        project_id, _ = _resolve_project(_client(), params["project"])
    section_id, _ = _resolve_section(_client(), value, project_id=project_id)
    return _ok(section=_client().get_section(str(section_id)))


@_wrap
def todoist_create_section(params: dict[str, Any]) -> str:
    if not params.get("name"):
        return _err("name is required")
    if not params.get("project"):
        return _err("project is required")
    project_id, _ = _resolve_project(_client(), params["project"])
    payload = {
        "name": params["name"],
        "project_id": project_id,
        "order": params.get("order"),
        "description": params.get("description"),
    }
    return _ok(section=_client().create_section(payload), action="created")


@_wrap
def todoist_update_section(params: dict[str, Any]) -> str:
    value = params.get("section_id") or params.get("section")
    if not value:
        return _err("section is required")
    project_id = None
    if params.get("project"):
        project_id, _ = _resolve_project(_client(), params["project"])
    section_id, _ = _resolve_section(_client(), value, project_id=project_id)
    payload = {
        key: params.get(key)
        for key in ("name", "description", "section_order", "is_collapsed")
        if key in params
    }
    if not payload:
        return _err("at least one section field is required", code="client_error")
    section = _client().update_section(str(section_id), payload)
    return _ok(section=section, action="updated")


@_wrap
def todoist_move_section(params: dict[str, Any]) -> str:
    value = params.get("section_id") or params.get("section")
    destination = params.get("project")
    if not value or not destination:
        return _err("section and destination project are required")
    section_id, _ = _resolve_section(_client(), value)
    project_id, _ = _resolve_project(_client(), destination)
    _client().move_section(str(section_id), str(project_id))
    return _ok(section_id=str(section_id), project_id=str(project_id), action="moved")


@_wrap
def todoist_reorder_sections(params: dict[str, Any]) -> str:
    entries = params.get("sections")
    if not isinstance(entries, list) or not entries:
        return _err("sections must be a non-empty list", code="client_error")
    sections: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("section") or "order" not in entry:
            return _err(
                "each section must contain section and order",
                code="client_error",
            )
        section_id, _ = _resolve_section(_client(), entry["section"])
        sections.append({"id": section_id, "section_order": entry["order"]})
    _client().reorder_sections(sections)
    return _ok(sections=sections, action="reordered")


@_wrap
def todoist_archive_section(params: dict[str, Any]) -> str:
    value = params.get("section_id") or params.get("section")
    if not value:
        return _err("section is required")
    section_id, _ = _resolve_section(_client(), value)
    section = _client().archive_section(str(section_id))
    return _ok(section=section, section_id=str(section_id), action="archived")


@_wrap
def todoist_unarchive_section(params: dict[str, Any]) -> str:
    section_id = params.get("section_id") or params.get("id")
    if not section_id:
        return _err("section_id is required for archived sections")
    section = _client().unarchive_section(str(section_id))
    return _ok(section=section, section_id=str(section_id), action="unarchived")


@_wrap
def todoist_delete_section(params: dict[str, Any]) -> str:
    value = params.get("section_id") or params.get("section")
    if not value:
        return _err("section is required")
    section_id, name = _resolve_section(_client(), value)
    refusal = _require_confirmation(params, "section", str(section_id))
    if refusal:
        return refusal
    _client().delete_section(str(section_id))
    return _ok(section_id=str(section_id), section_name=name, action="deleted")


@_wrap
def todoist_add_comment(params: dict[str, Any]) -> str:
    task_id = params.get("task_id")
    project_in = params.get("project_id") or params.get("project")
    content = params.get("content")
    if not content:
        return _err("content is required")
    if bool(task_id) == bool(project_in):
        return _err("exactly one of task_id or project is required", code="client_error")
    project_id: str | None = None
    if project_in:
        if _looks_like_id(project_in):
            project_id = project_in
        else:
            project_id, _ = _resolve_project(_client(), project_in)
    payload = {
        "task_id": str(task_id) if task_id else None,
        "project_id": project_id,
        "content": content,
    }
    comment = _client().create_comment(payload)
    return _ok(comment=comment)


@_wrap
def todoist_list_comments(params: dict[str, Any]) -> str:
    task_id = params.get("task_id")
    project_in = params.get("project_id") or params.get("project")
    if bool(task_id) == bool(project_in):
        return _err("exactly one of task_id or project is required", code="client_error")
    project_id: str | None = None
    if project_in:
        if _looks_like_id(project_in):
            project_id = project_in
        else:
            project_id, _ = _resolve_project(_client(), project_in)
    items, cursor = _unpack(
        _client().list_comments(
            task_id=str(task_id) if task_id else None,
            project_id=project_id,
            limit=params.get("limit"),
            cursor=params.get("cursor"),
        )
    )
    return _ok(comments=items, next_cursor=cursor, count=len(items))


@_wrap
def todoist_get_comment(params: dict[str, Any]) -> str:
    comment_id = params.get("comment_id") or params.get("id")
    if not comment_id:
        return _err("comment_id is required")
    return _ok(comment=_client().get_comment(str(comment_id)))


@_wrap
def todoist_update_comment(params: dict[str, Any]) -> str:
    comment_id = params.get("comment_id") or params.get("id")
    if not comment_id:
        return _err("comment_id is required")
    if not params.get("content"):
        return _err("content is required")
    comment = _client().update_comment(str(comment_id), {"content": params["content"]})
    return _ok(comment=comment, action="updated")


@_wrap
def todoist_delete_comment(params: dict[str, Any]) -> str:
    comment_id = params.get("comment_id") or params.get("id")
    if not comment_id:
        return _err("comment_id is required")
    refusal = _require_confirmation(params, "comment", str(comment_id))
    if refusal:
        return refusal
    _client().delete_comment(str(comment_id))
    return _ok(comment_id=str(comment_id), action="deleted")


def _collect_open_tasks(
    client: TodoistClient,
    *,
    project_id: str | None,
    label: str | None,
    max_pages: int = 20,
    page_size: int = 200,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(max_pages):
        items, cursor = _unpack(
            client.list_tasks(
                project_id=project_id, label=label, limit=page_size, cursor=cursor
            )
        )
        out.extend(items)
        if not cursor:
            break
    return out


@_wrap
def todoist_find_duplicate_tasks(params: dict[str, Any]) -> str:
    client = _client()
    project_in = params.get("project_id") or params.get("project")
    project_id: str | None = None
    if project_in:
        if _looks_like_id(project_in):
            project_id = project_in
        else:
            project_id, _ = _resolve_project(client, project_in)

    label = params.get("label")
    tasks = _collect_open_tasks(client, project_id=project_id, label=label)

    groups: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        if task.get("is_completed"):
            continue
        key = _normalize_content(task.get("content"))
        if not key:
            continue
        groups.setdefault(key, []).append(task)

    dups = [items for items in groups.values() if len(items) > 1]
    return _ok(
        duplicate_groups=dups,
        group_count=len(dups),
        duplicate_count=sum(len(g) - 1 for g in dups),
        scanned=len(tasks),
    )


_UPDATE_FIELD_SOURCES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("description", ("description",)),
    ("due_string", ("due_string", "due")),
    ("due_date", ("due_date",)),
    ("due_datetime", ("due_datetime",)),
    ("due_lang", ("due_lang", "lang")),
    ("priority", ("priority",)),
    ("labels", ("labels",)),
    ("duration", ("duration",)),
    ("duration_unit", ("duration_unit",)),
)


@_wrap
def todoist_create_or_update_task(params: dict[str, Any]) -> str:
    client = _client()
    content = params.get("content")
    if not content:
        return _err("content is required")

    project_in = params.get("project_id") or params.get("project")
    project_id: str | None = None
    if project_in:
        if _looks_like_id(project_in):
            project_id = project_in
        else:
            project_id, _ = _resolve_project(client, project_in)

    dup_label = params.get("label")
    tasks = _collect_open_tasks(client, project_id=project_id, label=dup_label)

    target_key = _normalize_content(content)
    matches = [
        t
        for t in tasks
        if not t.get("is_completed") and _normalize_content(t.get("content")) == target_key
    ]

    if matches:
        existing = matches[0]
        update_payload: dict[str, Any] = {}
        for target_field, source_keys in _UPDATE_FIELD_SOURCES:
            for src in source_keys:
                if src in params and params[src] not in (None, ""):
                    val = params[src]
                    if target_field == "labels":
                        val = _coerce_labels(val)
                    update_payload[target_field] = val
                    break
        if update_payload:
            updated = client.update_task(str(existing["id"]), update_payload)
            return _ok(
                action="updated",
                task=updated,
                matched_existing=str(existing.get("id")),
                duplicates_found=len(matches),
            )
        return _ok(
            action="noop",
            task=existing,
            matched_existing=str(existing.get("id")),
            duplicates_found=len(matches),
            note="A task with matching content already exists; no fields supplied to update.",
        )

    payload = _build_task_payload(client, params)
    # `dup_label` is the dup-search scope; if user only set `label` (singular)
    # and no `labels`, propagate it onto the new task so it appears under the
    # same filter they searched within.
    if payload.get("labels") is None and dup_label:
        payload["labels"] = [dup_label]
    created = client.create_task(payload)
    return _ok(action="created", task=created)


# ---------- registry ----------

TOOL_REGISTRY: list[dict[str, Any]] = [
    {"name": "todoist_list_tasks", "schema": schemas.LIST_TASKS, "handler": todoist_list_tasks},
    {"name": "todoist_get_task", "schema": schemas.GET_TASK, "handler": todoist_get_task},
    {"name": "todoist_create_task", "schema": schemas.CREATE_TASK, "handler": todoist_create_task},
    {"name": "todoist_update_task", "schema": schemas.UPDATE_TASK, "handler": todoist_update_task},
    {"name": "todoist_move_task", "schema": schemas.MOVE_TASK, "handler": todoist_move_task},
    {"name": "todoist_reorder_tasks", "schema": schemas.REORDER_TASKS, "handler": todoist_reorder_tasks},
    {"name": "todoist_complete_task", "schema": schemas.COMPLETE_TASK, "handler": todoist_complete_task},
    {"name": "todoist_reopen_task", "schema": schemas.REOPEN_TASK, "handler": todoist_reopen_task},
    {"name": "todoist_delete_task", "schema": schemas.DELETE_TASK, "handler": todoist_delete_task},
    {"name": "todoist_list_projects", "schema": schemas.LIST_PROJECTS, "handler": todoist_list_projects},
    {"name": "todoist_get_project", "schema": schemas.GET_PROJECT, "handler": todoist_get_project},
    {"name": "todoist_create_project", "schema": schemas.CREATE_PROJECT, "handler": todoist_create_project},
    {"name": "todoist_update_project", "schema": schemas.UPDATE_PROJECT, "handler": todoist_update_project},
    {"name": "todoist_move_project", "schema": schemas.MOVE_PROJECT, "handler": todoist_move_project},
    {"name": "todoist_reorder_projects", "schema": schemas.REORDER_PROJECTS, "handler": todoist_reorder_projects},
    {"name": "todoist_archive_project", "schema": schemas.ARCHIVE_PROJECT, "handler": todoist_archive_project},
    {"name": "todoist_unarchive_project", "schema": schemas.UNARCHIVE_PROJECT, "handler": todoist_unarchive_project},
    {"name": "todoist_delete_project", "schema": schemas.DELETE_PROJECT, "handler": todoist_delete_project},
    {"name": "todoist_list_sections", "schema": schemas.LIST_SECTIONS, "handler": todoist_list_sections},
    {"name": "todoist_get_section", "schema": schemas.GET_SECTION, "handler": todoist_get_section},
    {"name": "todoist_create_section", "schema": schemas.CREATE_SECTION, "handler": todoist_create_section},
    {"name": "todoist_update_section", "schema": schemas.UPDATE_SECTION, "handler": todoist_update_section},
    {"name": "todoist_move_section", "schema": schemas.MOVE_SECTION, "handler": todoist_move_section},
    {"name": "todoist_reorder_sections", "schema": schemas.REORDER_SECTIONS, "handler": todoist_reorder_sections},
    {"name": "todoist_archive_section", "schema": schemas.ARCHIVE_SECTION, "handler": todoist_archive_section},
    {"name": "todoist_unarchive_section", "schema": schemas.UNARCHIVE_SECTION, "handler": todoist_unarchive_section},
    {"name": "todoist_delete_section", "schema": schemas.DELETE_SECTION, "handler": todoist_delete_section},
    {"name": "todoist_list_labels", "schema": schemas.LIST_LABELS, "handler": todoist_list_labels},
    {"name": "todoist_get_label", "schema": schemas.GET_LABEL, "handler": todoist_get_label},
    {"name": "todoist_create_label", "schema": schemas.CREATE_LABEL, "handler": todoist_create_label},
    {"name": "todoist_update_label", "schema": schemas.UPDATE_LABEL, "handler": todoist_update_label},
    {"name": "todoist_delete_label", "schema": schemas.DELETE_LABEL, "handler": todoist_delete_label},
    {"name": "todoist_add_comment", "schema": schemas.ADD_COMMENT, "handler": todoist_add_comment},
    {"name": "todoist_list_comments", "schema": schemas.LIST_COMMENTS, "handler": todoist_list_comments},
    {"name": "todoist_get_comment", "schema": schemas.GET_COMMENT, "handler": todoist_get_comment},
    {"name": "todoist_update_comment", "schema": schemas.UPDATE_COMMENT, "handler": todoist_update_comment},
    {"name": "todoist_delete_comment", "schema": schemas.DELETE_COMMENT, "handler": todoist_delete_comment},
    {"name": "todoist_find_duplicate_tasks", "schema": schemas.FIND_DUPLICATES, "handler": todoist_find_duplicate_tasks},
    {"name": "todoist_create_or_update_task", "schema": schemas.CREATE_OR_UPDATE, "handler": todoist_create_or_update_task},
]

HANDLER_MAP: dict[str, Callable[..., str]] = {t["name"]: t["handler"] for t in TOOL_REGISTRY}
