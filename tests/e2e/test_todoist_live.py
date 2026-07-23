"""Destructive, isolated end-to-end coverage for every Hermes Todoist tool."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable
from contextlib import suppress
from typing import Any

import pytest

from hermes_todoist import tools
from hermes_todoist.client import TodoistClient, TodoistError

pytestmark = pytest.mark.e2e


def _require_live_token() -> str:
    if os.environ.get("HERMES_TODOIST_E2E") != "1":
        pytest.skip("set HERMES_TODOIST_E2E=1 to run tests against a real account")
    token = os.environ.get("TODOIST_API_TOKEN", "").strip()
    if not token:
        pytest.fail("TODOIST_API_TOKEN is required when HERMES_TODOIST_E2E=1")
    return token


def _resource_id(payload: dict[str, Any], field: str) -> str:
    value = payload[field].get("id")
    assert value, f"Todoist response has no {field}.id: {payload}"
    return str(value)


def _cleanup(call: Callable[[], Any]) -> None:
    with suppress(TodoistError):
        call()


def test_every_registered_tool_against_todoist() -> None:
    """Run all registered tools and leave no test-owned resources behind."""
    client = TodoistClient(token=_require_live_token())
    tools._set_client(client)
    run_id = uuid.uuid4().hex[:12]
    prefix = f"hermes-todoist-e2e-{run_id}"
    project_ids: set[str] = set()
    label_ids: set[str] = set()
    called: set[str] = set()

    def invoke(name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        called.add(name)
        raw = tools.HANDLER_MAP[name](params or {})
        payload = json.loads(raw)
        assert payload.get("success") is True, f"{name} failed: {payload}"
        return payload

    def refuse_delete(name: str, params: dict[str, Any]) -> None:
        called.add(name)
        payload = json.loads(tools.HANDLER_MAP[name](params))
        assert payload.get("success") is False, payload
        assert payload.get("code") == "confirmation_required", payload

    try:
        invoke("todoist_list_projects", {"limit": 10})

        project_a = invoke(
            "todoist_create_project",
            {"name": f"{prefix}-a", "description": "E2E root A"},
        )
        project_a_id = _resource_id(project_a, "project")
        project_ids.add(project_a_id)

        project_b = invoke(
            "todoist_create_project",
            {"name": f"{prefix}-b", "description": "E2E root B"},
        )
        project_b_id = _resource_id(project_b, "project")
        project_ids.add(project_b_id)

        child_project = invoke(
            "todoist_create_project",
            {"name": f"{prefix}-child", "parent": project_a_id},
        )
        child_project_id = _resource_id(child_project, "project")
        project_ids.add(child_project_id)

        invoke("todoist_get_project", {"project_id": child_project_id})
        updated_project = invoke(
            "todoist_update_project",
            {
                "project_id": child_project_id,
                "name": f"{prefix}-child-updated",
                "description": "Updated by the E2E test",
                "view_style": "list",
            },
        )
        assert updated_project["project"]["name"] == f"{prefix}-child-updated"
        invoke(
            "todoist_move_project",
            {"project_id": child_project_id, "parent": project_b_id},
        )
        invoke(
            "todoist_reorder_projects",
            {
                "projects": [
                    {"project": project_a_id, "order": 1},
                    {"project": project_b_id, "order": 2},
                ]
            },
        )
        invoke("todoist_archive_project", {"project_id": child_project_id})
        invoke("todoist_unarchive_project", {"project_id": child_project_id})

        section_a1 = invoke(
            "todoist_create_section",
            {"name": f"{prefix}-section-a1", "project": project_a_id},
        )
        section_a1_id = _resource_id(section_a1, "section")
        section_a2 = invoke(
            "todoist_create_section",
            {"name": f"{prefix}-section-a2", "project": project_a_id},
        )
        section_a2_id = _resource_id(section_a2, "section")
        section_b = invoke(
            "todoist_create_section",
            {"name": f"{prefix}-section-b", "project": project_b_id},
        )
        section_b_id = _resource_id(section_b, "section")

        invoke("todoist_list_sections", {"project_id": project_a_id})
        invoke("todoist_get_section", {"section_id": section_a1_id})
        updated_section = invoke(
            "todoist_update_section",
            {
                "section_id": section_a1_id,
                "name": f"{prefix}-section-a1-updated",
            },
        )
        assert updated_section["section"]["name"] == f"{prefix}-section-a1-updated"
        invoke(
            "todoist_reorder_sections",
            {
                "sections": [
                    {"section": section_a1_id, "order": 1},
                    {"section": section_a2_id, "order": 2},
                ]
            },
        )
        invoke(
            "todoist_move_section",
            {"section_id": section_a2_id, "project": project_b_id},
        )
        invoke(
            "todoist_reorder_sections",
            {
                "sections": [
                    {"section": section_a2_id, "order": 1},
                    {"section": section_b_id, "order": 2},
                ]
            },
        )
        invoke("todoist_archive_section", {"section_id": section_a1_id})
        invoke("todoist_unarchive_section", {"section_id": section_a1_id})

        invoke("todoist_list_labels", {"limit": 10})
        label = invoke(
            "todoist_create_label",
            {"name": f"{prefix}-label", "is_favorite": False},
        )
        label_id = _resource_id(label, "label")
        label_ids.add(label_id)
        invoke("todoist_get_label", {"label_id": label_id})
        label_name = f"{prefix}-label-updated"
        updated_label = invoke(
            "todoist_update_label",
            {"label_id": label_id, "name": label_name},
        )
        assert updated_label["label"]["name"] == label_name

        task_1 = invoke(
            "todoist_create_task",
            {
                "content": f"{prefix} task one",
                "description": "Created by the E2E test",
                "project_id": project_a_id,
                "section_id": section_a1_id,
                "labels": [label_name],
                "priority": 2,
            },
        )
        task_1_id = _resource_id(task_1, "task")
        task_2 = invoke(
            "todoist_create_task",
            {
                "content": f"{prefix} task two",
                "project_id": project_a_id,
                "section_id": section_a1_id,
            },
        )
        task_2_id = _resource_id(task_2, "task")

        invoke("todoist_list_tasks", {"project_id": project_a_id})
        invoke("todoist_get_task", {"task_id": task_1_id})
        updated_task = invoke(
            "todoist_update_task",
            {
                "task_id": task_1_id,
                "content": f"{prefix} task one updated",
                "description": "Updated by the E2E test",
                "priority": 3,
            },
        )
        assert updated_task["task"]["content"] == f"{prefix} task one updated"
        invoke(
            "todoist_move_task",
            {
                "task_id": task_2_id,
                "section": section_a2_id,
                "section_project": project_b_id,
            },
        )

        upsert_content = f"{prefix} upsert task"
        upserted = invoke(
            "todoist_create_or_update_task",
            {
                "content": upsert_content,
                "project_id": project_a_id,
                "section_id": section_a1_id,
                "priority": 1,
            },
        )
        assert upserted["action"] == "created"
        upsert_task_id = _resource_id(upserted, "task")
        upserted_again = invoke(
            "todoist_create_or_update_task",
            {
                "content": upsert_content,
                "project_id": project_a_id,
                "priority": 4,
            },
        )
        assert upserted_again["action"] == "updated"
        assert str(upserted_again["task"]["id"]) == upsert_task_id

        duplicate_content = f"{prefix} duplicate task"
        duplicate_1 = invoke(
            "todoist_create_task",
            {"content": duplicate_content, "project_id": project_a_id},
        )
        duplicate_1_id = _resource_id(duplicate_1, "task")
        duplicate_2 = invoke(
            "todoist_create_task",
            {"content": duplicate_content, "project_id": project_a_id},
        )
        duplicate_2_id = _resource_id(duplicate_2, "task")
        duplicates = invoke(
            "todoist_find_duplicate_tasks",
            {"project_id": project_a_id},
        )
        assert any(
            {str(item["id"]) for item in group} >= {duplicate_1_id, duplicate_2_id}
            for group in duplicates["duplicate_groups"]
        )

        invoke(
            "todoist_reorder_tasks",
            {
                "tasks": [
                    {"task_id": duplicate_1_id, "order": 1},
                    {"task_id": duplicate_2_id, "order": 2},
                ]
            },
        )
        invoke("todoist_complete_task", {"task_id": task_1_id})
        invoke("todoist_reopen_task", {"task_id": task_1_id})

        comment = invoke(
            "todoist_add_comment",
            {"task_id": task_1_id, "content": f"{prefix} comment"},
        )
        comment_id = _resource_id(comment, "comment")
        listed_comments = invoke("todoist_list_comments", {"task_id": task_1_id})
        assert any(str(item["id"]) == comment_id for item in listed_comments["comments"])
        invoke("todoist_get_comment", {"comment_id": comment_id})
        updated_comment = invoke(
            "todoist_update_comment",
            {"comment_id": comment_id, "content": f"{prefix} comment updated"},
        )
        assert updated_comment["comment"]["content"] == f"{prefix} comment updated"
        refuse_delete("todoist_delete_comment", {"comment_id": comment_id})
        invoke("todoist_delete_comment", {"comment_id": comment_id, "confirm": True})

        refuse_delete("todoist_delete_task", {"task_id": duplicate_2_id})
        invoke("todoist_delete_task", {"task_id": duplicate_2_id, "confirm": True})
        refuse_delete("todoist_delete_section", {"section_id": section_b_id})
        invoke("todoist_delete_section", {"section_id": section_b_id, "confirm": True})
        refuse_delete("todoist_delete_label", {"label_id": label_id})
        invoke("todoist_delete_label", {"label_id": label_id, "confirm": True})
        label_ids.discard(label_id)
        refuse_delete("todoist_delete_project", {"project_id": child_project_id})
        invoke(
            "todoist_delete_project",
            {"project_id": child_project_id, "confirm": True},
        )
        project_ids.discard(child_project_id)

        expected = set(tools.HANDLER_MAP)
        assert called == expected, (
            f"tool coverage mismatch; missing={sorted(expected - called)}, "
            f"unexpected={sorted(called - expected)}"
        )
    finally:
        for project_id in project_ids:
            _cleanup(lambda value=project_id: client.unarchive_project(value))
            _cleanup(lambda value=project_id: client.delete_project(value))
        for label_id in label_ids:
            _cleanup(lambda value=label_id: client.delete_label(value))
        tools._set_client(None)
