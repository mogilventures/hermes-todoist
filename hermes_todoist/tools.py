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


def _resolve_project(client: TodoistClient, value: Any) -> tuple[str | None, str | None]:
    if value in (None, ""):
        return None, None
    needle = str(value)
    items, _ = _unpack(client.list_projects(limit=200))
    for proj in items:
        if str(proj.get("id")) == needle:
            return str(proj["id"]), proj.get("name")
    lower = needle.lower()
    for proj in items:
        if (proj.get("name") or "").lower() == lower:
            return str(proj["id"]), proj.get("name")
    if _looks_like_id(needle):
        return needle, None
    raise TodoistError(f"Project not found: {needle!r}")


def _resolve_section(
    client: TodoistClient, value: Any, project_id: str | None = None
) -> tuple[str | None, str | None]:
    if value in (None, ""):
        return None, None
    needle = str(value)
    items, _ = _unpack(client.list_sections(project_id=project_id, limit=200))
    for sec in items:
        if str(sec.get("id")) == needle:
            return str(sec["id"]), sec.get("name")
    lower = needle.lower()
    for sec in items:
        if (sec.get("name") or "").lower() == lower:
            return str(sec["id"]), sec.get("name")
    if _looks_like_id(needle):
        return needle, None
    raise TodoistError(f"Section not found: {needle!r}")


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
    {"name": "todoist_complete_task", "schema": schemas.COMPLETE_TASK, "handler": todoist_complete_task},
    {"name": "todoist_reopen_task", "schema": schemas.REOPEN_TASK, "handler": todoist_reopen_task},
    {"name": "todoist_delete_task", "schema": schemas.DELETE_TASK, "handler": todoist_delete_task},
    {"name": "todoist_list_projects", "schema": schemas.LIST_PROJECTS, "handler": todoist_list_projects},
    {"name": "todoist_list_sections", "schema": schemas.LIST_SECTIONS, "handler": todoist_list_sections},
    {"name": "todoist_list_labels", "schema": schemas.LIST_LABELS, "handler": todoist_list_labels},
    {"name": "todoist_add_comment", "schema": schemas.ADD_COMMENT, "handler": todoist_add_comment},
    {"name": "todoist_list_comments", "schema": schemas.LIST_COMMENTS, "handler": todoist_list_comments},
    {"name": "todoist_find_duplicate_tasks", "schema": schemas.FIND_DUPLICATES, "handler": todoist_find_duplicate_tasks},
    {"name": "todoist_create_or_update_task", "schema": schemas.CREATE_OR_UPDATE, "handler": todoist_create_or_update_task},
]

HANDLER_MAP: dict[str, Callable[..., str]] = {t["name"]: t["handler"] for t in TOOL_REGISTRY}
