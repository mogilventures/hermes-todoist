"""Tests for hermes_todoist.tools — handlers, name resolution, and dedup."""
from __future__ import annotations

import json
from typing import Any

import pytest

from hermes_todoist import tools
from hermes_todoist.client import TodoistAPIError


class FakeClient:
    """In-memory stand-in for TodoistClient. Records calls and serves data."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.projects: list[dict[str, Any]] = []
        self.sections: list[dict[str, Any]] = []
        self.labels: list[dict[str, Any]] = []
        self.tasks: list[dict[str, Any]] = []
        self.comments: list[dict[str, Any]] = []
        self._next_id = 1000

    def _mint_id(self) -> str:
        self._next_id += 1
        return str(self._next_id)

    def list_projects(self, limit: int | None = None, cursor: str | None = None) -> dict[str, Any]:
        self.calls.append(("list_projects", {"limit": limit, "cursor": cursor}))
        return {"results": list(self.projects), "next_cursor": None}

    def get_project(self, project_id: str) -> dict[str, Any]:
        self.calls.append(("get_project", {"project_id": project_id}))
        return next(p for p in self.projects if str(p["id"]) == str(project_id))

    def create_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("create_project", payload))
        project = {"id": self._mint_id(), **{k: v for k, v in payload.items() if v is not None}}
        self.projects.append(project)
        return project

    def update_project(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("update_project", {"project_id": project_id, **payload}))
        project = self.get_project(project_id)
        project.update(payload)
        return project

    def move_project(self, project_id: str, parent_id: str | None) -> None:
        self.calls.append(("move_project", {"project_id": project_id, "parent_id": parent_id}))

    def reorder_projects(self, projects: list[dict[str, Any]]) -> None:
        self.calls.append(("reorder_projects", {"projects": projects}))

    def archive_project(self, project_id: str) -> dict[str, Any]:
        self.calls.append(("archive_project", {"project_id": project_id}))
        return {"id": project_id, "is_archived": True}

    def unarchive_project(self, project_id: str) -> dict[str, Any]:
        self.calls.append(("unarchive_project", {"project_id": project_id}))
        return {"id": project_id, "is_archived": False}

    def delete_project(self, project_id: str) -> None:
        self.calls.append(("delete_project", {"project_id": project_id}))
        self.projects = [p for p in self.projects if str(p["id"]) != str(project_id)]

    def list_sections(
        self,
        project_id: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(("list_sections", {"project_id": project_id, "limit": limit, "cursor": cursor}))
        items = [
            s for s in self.sections
            if project_id is None or str(s.get("project_id")) == str(project_id)
        ]
        return {"results": items, "next_cursor": None}

    def get_section(self, section_id: str) -> dict[str, Any]:
        self.calls.append(("get_section", {"section_id": section_id}))
        return next(s for s in self.sections if str(s["id"]) == str(section_id))

    def create_section(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("create_section", payload))
        section = {"id": self._mint_id(), **{k: v for k, v in payload.items() if v is not None}}
        self.sections.append(section)
        return section

    def update_section(self, section_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("update_section", {"section_id": section_id, **payload}))
        section = self.get_section(section_id)
        section.update(payload)
        return section

    def move_section(self, section_id: str, project_id: str) -> None:
        self.calls.append(("move_section", {"section_id": section_id, "project_id": project_id}))

    def reorder_sections(self, sections: list[dict[str, Any]]) -> None:
        self.calls.append(("reorder_sections", {"sections": sections}))

    def archive_section(self, section_id: str) -> dict[str, Any]:
        self.calls.append(("archive_section", {"section_id": section_id}))
        return {"id": section_id, "is_archived": True}

    def unarchive_section(self, section_id: str) -> dict[str, Any]:
        self.calls.append(("unarchive_section", {"section_id": section_id}))
        return {"id": section_id, "is_archived": False}

    def delete_section(self, section_id: str) -> None:
        self.calls.append(("delete_section", {"section_id": section_id}))
        self.sections = [s for s in self.sections if str(s["id"]) != str(section_id)]

    def list_labels(self, limit: int | None = None, cursor: str | None = None) -> dict[str, Any]:
        self.calls.append(("list_labels", {"limit": limit, "cursor": cursor}))
        return {"results": list(self.labels), "next_cursor": None}

    def get_label(self, label_id: str) -> dict[str, Any]:
        self.calls.append(("get_label", {"label_id": label_id}))
        return next(label for label in self.labels if str(label["id"]) == str(label_id))

    def create_label(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("create_label", payload))
        label = {"id": self._mint_id(), **{k: v for k, v in payload.items() if v is not None}}
        self.labels.append(label)
        return label

    def update_label(self, label_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("update_label", {"label_id": label_id, **payload}))
        label = self.get_label(label_id)
        label.update(payload)
        return label

    def delete_label(self, label_id: str) -> None:
        self.calls.append(("delete_label", {"label_id": label_id}))
        self.labels = [label for label in self.labels if str(label["id"]) != str(label_id)]

    def list_tasks(
        self,
        *,
        project_id: str | None = None,
        section_id: str | None = None,
        parent_id: str | None = None,
        label: str | None = None,
        filter_query: str | None = None,
        lang: str | None = None,
        ids: list[str] | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append((
            "list_tasks",
            {
                "project_id": project_id, "section_id": section_id, "parent_id": parent_id,
                "label": label, "filter": filter_query, "ids": ids, "limit": limit, "cursor": cursor,
            },
        ))
        items = self.tasks
        if project_id:
            items = [t for t in items if str(t.get("project_id")) == str(project_id)]
        if section_id:
            items = [t for t in items if str(t.get("section_id")) == str(section_id)]
        if label:
            items = [t for t in items if label in (t.get("labels") or [])]
        if ids:
            items = [t for t in items if str(t.get("id")) in {str(i) for i in ids}]
        return {"results": items, "next_cursor": None}

    def get_task(self, task_id: str) -> dict[str, Any]:
        self.calls.append(("get_task", {"task_id": task_id}))
        for t in self.tasks:
            if str(t.get("id")) == str(task_id):
                return t
        raise TodoistAPIError(404, "Not found")

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("create_task", payload))
        task = {"id": self._mint_id(), "is_completed": False}
        for k, v in payload.items():
            if v is not None:
                task[k] = v
        self.tasks.append(task)
        return task

    def update_task(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("update_task", {"task_id": task_id, **payload}))
        for t in self.tasks:
            if str(t.get("id")) == str(task_id):
                for k, v in payload.items():
                    if v is not None:
                        t[k] = v
                return t
        raise TodoistAPIError(404, "Not found")

    def move_task(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("move_task", {"task_id": task_id, **payload}))
        task = self.get_task(task_id)
        task.update(payload)
        return task

    def reorder_tasks(self, tasks: list[dict[str, Any]]) -> None:
        self.calls.append(("reorder_tasks", {"tasks": tasks}))

    def close_task(self, task_id: str) -> None:
        self.calls.append(("close_task", {"task_id": task_id}))
        for t in self.tasks:
            if str(t.get("id")) == str(task_id):
                t["is_completed"] = True

    def reopen_task(self, task_id: str) -> None:
        self.calls.append(("reopen_task", {"task_id": task_id}))
        for t in self.tasks:
            if str(t.get("id")) == str(task_id):
                t["is_completed"] = False

    def delete_task(self, task_id: str) -> None:
        self.calls.append(("delete_task", {"task_id": task_id}))
        self.tasks = [t for t in self.tasks if str(t.get("id")) != str(task_id)]

    def create_comment(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("create_comment", payload))
        comment = {"id": self._mint_id()}
        for k, v in payload.items():
            if v is not None:
                comment[k] = v
        self.comments.append(comment)
        return comment

    def list_comments(
        self,
        *,
        task_id: str | None = None,
        project_id: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(("list_comments", {"task_id": task_id, "project_id": project_id, "limit": limit, "cursor": cursor}))
        items = self.comments
        if task_id:
            items = [c for c in items if str(c.get("task_id")) == str(task_id)]
        if project_id:
            items = [c for c in items if str(c.get("project_id")) == str(project_id)]
        return {"results": items, "next_cursor": None}

    def get_comment(self, comment_id: str) -> dict[str, Any]:
        self.calls.append(("get_comment", {"comment_id": comment_id}))
        return next(c for c in self.comments if str(c["id"]) == str(comment_id))

    def update_comment(self, comment_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("update_comment", {"comment_id": comment_id, **payload}))
        comment = self.get_comment(comment_id)
        comment.update(payload)
        return comment

    def delete_comment(self, comment_id: str) -> None:
        self.calls.append(("delete_comment", {"comment_id": comment_id}))
        self.comments = [c for c in self.comments if str(c["id"]) != str(comment_id)]


@pytest.fixture
def fake() -> FakeClient:
    client = FakeClient()
    client.projects = [
        {"id": "100", "name": "Personal"},
        {"id": "200", "name": "Work"},
    ]
    client.sections = [
        {"id": "10", "project_id": "200", "name": "Inbox"},
        {"id": "11", "project_id": "200", "name": "Doing"},
    ]
    client.labels = [{"id": "1", "name": "urgent"}, {"id": "2", "name": "home"}]
    client.tasks = [
        {"id": "1", "content": "Buy milk", "project_id": "100", "labels": ["home"], "is_completed": False},
        {"id": "2", "content": "Write report", "project_id": "200", "labels": ["urgent"], "is_completed": False},
        {"id": "3", "content": "buy   milk", "project_id": "100", "labels": ["home"], "is_completed": False},
        {"id": "4", "content": "Ship hermes-todoist", "project_id": "200", "labels": ["urgent"], "is_completed": False},
    ]
    tools._set_client(client)  # type: ignore[arg-type]
    yield client
    tools._set_client(None)


def _decode(s: str) -> dict[str, Any]:
    return json.loads(s)


def test_list_projects(fake: FakeClient) -> None:
    out = _decode(tools.todoist_list_projects({}))
    assert out["success"] is True
    assert out["count"] == 2
    assert {p["name"] for p in out["projects"]} == {"Personal", "Work"}
    assert out["next_cursor"] is None


def test_list_sections_resolves_project_name(fake: FakeClient) -> None:
    out = _decode(tools.todoist_list_sections({"project": "Work"}))
    assert out["success"] is True
    assert out["count"] == 2
    assert all(s["project_id"] == "200" for s in out["sections"])
    list_sections_call = [c for c in fake.calls if c[0] == "list_sections"][0]
    assert list_sections_call[1]["project_id"] == "200"


def test_list_sections_case_insensitive(fake: FakeClient) -> None:
    out = _decode(tools.todoist_list_sections({"project": "wOrK"}))
    assert out["success"] is True
    assert out["count"] == 2


def test_list_sections_unknown_project_errors(fake: FakeClient) -> None:
    out = _decode(tools.todoist_list_sections({"project": "Nonexistent"}))
    assert out["success"] is False
    assert "not found" in out["error"].lower()
    assert out["code"] == "client_error"


def test_ambiguous_project_name_returns_candidates(fake: FakeClient) -> None:
    fake.projects.append({"id": "300", "name": "Work"})
    out = _decode(tools.todoist_get_project({"project": "Work"}))
    assert out["success"] is False
    assert out["code"] == "client_error"
    assert "200" in out["error"] and "300" in out["error"]


def test_project_name_resolution_paginates(fake: FakeClient) -> None:
    class PaginatedProjects:
        def list_projects(self, limit=None, cursor=None):  # type: ignore[no-untyped-def]
            if cursor is None:
                return {"results": [{"id": "100", "name": "First"}], "next_cursor": "next"}
            return {"results": [{"id": "200", "name": "Second"}], "next_cursor": None}

        def get_project(self, project_id: str) -> dict[str, Any]:
            return {"id": project_id, "name": "Second"}

    tools._set_client(PaginatedProjects())  # type: ignore[arg-type]
    try:
        out = _decode(tools.todoist_get_project({"project": "Second"}))
        assert out["success"] is True
        assert out["project"]["id"] == "200"
    finally:
        tools._set_client(fake)  # type: ignore[arg-type]


def test_list_tasks_passes_through_filter(fake: FakeClient) -> None:
    out = _decode(tools.todoist_list_tasks({"filter": "today | overdue", "lang": "en"}))
    assert out["success"] is True
    list_tasks_call = [c for c in fake.calls if c[0] == "list_tasks"][0]
    assert list_tasks_call[1]["filter"] == "today | overdue"


def test_list_tasks_resolves_project(fake: FakeClient) -> None:
    out = _decode(tools.todoist_list_tasks({"project": "Personal"}))
    assert out["count"] == 2
    assert {t["id"] for t in out["tasks"]} == {"1", "3"}


def test_get_task_requires_id(fake: FakeClient) -> None:
    out = _decode(tools.todoist_get_task({}))
    assert out["success"] is False
    assert "task_id" in out["error"]


def test_get_task_returns_task(fake: FakeClient) -> None:
    out = _decode(tools.todoist_get_task({"task_id": "1"}))
    assert out["success"] is True
    assert out["task"]["content"] == "Buy milk"


def test_create_task_requires_content(fake: FakeClient) -> None:
    out = _decode(tools.todoist_create_task({}))
    assert out["success"] is False
    assert "content" in out["error"]


def test_create_task_resolves_project_name(fake: FakeClient) -> None:
    out = _decode(
        tools.todoist_create_task(
            {"content": "New thing", "project": "Personal", "due": "tomorrow", "priority": 3}
        )
    )
    assert out["success"] is True
    assert out["action"] == "created"
    create_call = [c for c in fake.calls if c[0] == "create_task"][0]
    payload = create_call[1]
    assert payload["content"] == "New thing"
    assert payload["project_id"] == "100"
    assert payload["due_string"] == "tomorrow"
    assert payload["priority"] == 3


def test_create_task_with_labels_list(fake: FakeClient) -> None:
    _decode(
        tools.todoist_create_task({"content": "x", "labels": ["urgent", "home"]})
    )
    payload = [c for c in fake.calls if c[0] == "create_task"][0][1]
    assert payload["labels"] == ["urgent", "home"]


def test_create_task_with_labels_string(fake: FakeClient) -> None:
    _decode(tools.todoist_create_task({"content": "x", "labels": "urgent, home"}))
    payload = [c for c in fake.calls if c[0] == "create_task"][0][1]
    assert payload["labels"] == ["urgent", "home"]


def test_update_task(fake: FakeClient) -> None:
    out = _decode(
        tools.todoist_update_task({"task_id": "1", "content": "Buy oat milk", "priority": 4})
    )
    assert out["success"] is True
    assert out["task"]["content"] == "Buy oat milk"
    update_call = [c for c in fake.calls if c[0] == "update_task"][0]
    assert "project_id" not in update_call[1] or update_call[1].get("project_id") is None


def test_update_task_requires_id(fake: FakeClient) -> None:
    out = _decode(tools.todoist_update_task({"content": "x"}))
    assert out["success"] is False
    assert "task_id" in out["error"]


def test_move_task_resolves_destination_project(fake: FakeClient) -> None:
    out = _decode(tools.todoist_move_task({"task_id": "1", "project": "Work"}))
    assert out["success"] is True
    assert out["task"]["project_id"] == "200"
    assert ("move_task", {"task_id": "1", "project_id": "200"}) in fake.calls


def test_move_task_rejects_multiple_destinations(fake: FakeClient) -> None:
    out = _decode(
        tools.todoist_move_task({"task_id": "1", "project": "Work", "parent_id": "2"})
    )
    assert out["success"] is False
    assert out["code"] == "client_error"


def test_reorder_tasks_translates_order_fields(fake: FakeClient) -> None:
    out = _decode(
        tools.todoist_reorder_tasks(
            {"tasks": [{"task_id": "1", "order": 2}, {"task_id": "3", "order": 1}]}
        )
    )
    assert out["success"] is True
    assert fake.calls[-1] == (
        "reorder_tasks",
        {"tasks": [{"id": "1", "child_order": 2}, {"id": "3", "child_order": 1}]},
    )


def test_complete_task(fake: FakeClient) -> None:
    out = _decode(tools.todoist_complete_task({"task_id": "1"}))
    assert out["success"] is True
    assert out["action"] == "completed"
    assert any(c[0] == "close_task" for c in fake.calls)


def test_reopen_task(fake: FakeClient) -> None:
    out = _decode(tools.todoist_reopen_task({"task_id": "1"}))
    assert out["success"] is True
    assert out["action"] == "reopened"


def test_delete_requires_confirm(fake: FakeClient) -> None:
    out = _decode(tools.todoist_delete_task({"task_id": "1"}))
    assert out["success"] is False
    assert out["code"] == "confirmation_required"
    assert not any(c[0] == "delete_task" for c in fake.calls)


def test_delete_with_confirm_false_blocked(fake: FakeClient) -> None:
    out = _decode(tools.todoist_delete_task({"task_id": "1", "confirm": False}))
    assert out["success"] is False
    assert out["code"] == "confirmation_required"


def test_delete_with_confirm_true(fake: FakeClient) -> None:
    out = _decode(tools.todoist_delete_task({"task_id": "1", "confirm": True}))
    assert out["success"] is True
    assert out["action"] == "deleted"
    assert any(c[0] == "delete_task" for c in fake.calls)


def test_project_crud_and_lifecycle(fake: FakeClient) -> None:
    created = _decode(
        tools.todoist_create_project(
            {"name": "Launch", "parent": "Work", "description": "Release work"}
        )
    )
    project_id = created["project"]["id"]
    assert created["project"]["parent_id"] == "200"

    updated = _decode(
        tools.todoist_update_project({"project": project_id, "name": "Launch 2"})
    )
    assert updated["project"]["name"] == "Launch 2"
    assert _decode(tools.todoist_get_project({"project": project_id}))["project"]["id"] == project_id

    moved = _decode(tools.todoist_move_project({"project": project_id, "parent": None}))
    assert moved["parent_id"] is None
    assert _decode(tools.todoist_archive_project({"project": project_id}))["action"] == "archived"
    assert (
        _decode(tools.todoist_unarchive_project({"project_id": project_id}))["action"]
        == "unarchived"
    )

    blocked = _decode(tools.todoist_delete_project({"project": project_id}))
    assert blocked["code"] == "confirmation_required"
    deleted = _decode(
        tools.todoist_delete_project({"project": project_id, "confirm": True})
    )
    assert deleted["action"] == "deleted"


def test_reorder_projects_resolves_names(fake: FakeClient) -> None:
    out = _decode(
        tools.todoist_reorder_projects(
            {"projects": [{"project": "Personal", "order": 2}, {"project": "Work", "order": 1}]}
        )
    )
    assert out["success"] is True
    assert fake.calls[-1][1]["projects"] == [
        {"id": "100", "child_order": 2},
        {"id": "200", "child_order": 1},
    ]


def test_section_crud_and_lifecycle(fake: FakeClient) -> None:
    created = _decode(
        tools.todoist_create_section(
            {"name": "Review", "project": "Work", "description": "Review queue"}
        )
    )
    section_id = created["section"]["id"]
    assert created["section"]["project_id"] == "200"

    updated = _decode(
        tools.todoist_update_section(
            {"section": section_id, "name": "Final review", "is_collapsed": True}
        )
    )
    assert updated["section"]["name"] == "Final review"
    assert _decode(tools.todoist_get_section({"section": section_id}))["section"]["id"] == section_id

    moved = _decode(tools.todoist_move_section({"section": section_id, "project": "Personal"}))
    assert moved["project_id"] == "100"
    assert _decode(tools.todoist_archive_section({"section": section_id}))["action"] == "archived"
    assert (
        _decode(tools.todoist_unarchive_section({"section_id": section_id}))["action"]
        == "unarchived"
    )

    blocked = _decode(tools.todoist_delete_section({"section": section_id}))
    assert blocked["code"] == "confirmation_required"
    assert (
        _decode(tools.todoist_delete_section({"section": section_id, "confirm": True}))["action"]
        == "deleted"
    )


def test_reorder_sections_resolves_names(fake: FakeClient) -> None:
    out = _decode(
        tools.todoist_reorder_sections(
            {"sections": [{"section": "Inbox", "order": 2}, {"section": "Doing", "order": 1}]}
        )
    )
    assert out["success"] is True
    assert fake.calls[-1][1]["sections"] == [
        {"id": "10", "section_order": 2},
        {"id": "11", "section_order": 1},
    ]


def test_label_crud_requires_delete_confirmation(fake: FakeClient) -> None:
    created = _decode(tools.todoist_create_label({"name": "blocked", "color": "red"}))
    label_id = created["label"]["id"]
    assert _decode(tools.todoist_get_label({"label": label_id}))["label"]["name"] == "blocked"
    updated = _decode(tools.todoist_update_label({"label": label_id, "name": "waiting"}))
    assert updated["label"]["name"] == "waiting"
    assert _decode(tools.todoist_delete_label({"label": label_id}))["code"] == "confirmation_required"
    assert (
        _decode(tools.todoist_delete_label({"label": label_id, "confirm": True}))["action"]
        == "deleted"
    )


def test_add_comment_requires_target(fake: FakeClient) -> None:
    out = _decode(tools.todoist_add_comment({"content": "hi"}))
    assert out["success"] is False
    assert "task_id" in out["error"] or "project" in out["error"]


def test_add_comment_requires_content(fake: FakeClient) -> None:
    out = _decode(tools.todoist_add_comment({"task_id": "1"}))
    assert out["success"] is False
    assert "content" in out["error"]


def test_add_comment_on_task(fake: FakeClient) -> None:
    out = _decode(tools.todoist_add_comment({"task_id": "1", "content": "hi"}))
    assert out["success"] is True
    assert out["comment"]["content"] == "hi"


def test_list_comments_requires_target(fake: FakeClient) -> None:
    out = _decode(tools.todoist_list_comments({}))
    assert out["success"] is False


def test_list_comments_on_task(fake: FakeClient) -> None:
    fake.comments = [{"id": "c1", "task_id": "1", "content": "x"}]
    out = _decode(tools.todoist_list_comments({"task_id": "1"}))
    assert out["success"] is True
    assert out["count"] == 1


def test_comment_get_update_delete(fake: FakeClient) -> None:
    fake.comments = [{"id": "c1", "task_id": "1", "content": "old"}]
    assert _decode(tools.todoist_get_comment({"comment_id": "c1"}))["comment"]["content"] == "old"
    updated = _decode(
        tools.todoist_update_comment({"comment_id": "c1", "content": "new"})
    )
    assert updated["comment"]["content"] == "new"
    assert _decode(tools.todoist_delete_comment({"comment_id": "c1"}))["code"] == "confirmation_required"
    assert (
        _decode(
            tools.todoist_delete_comment({"comment_id": "c1", "confirm": True})
        )["action"]
        == "deleted"
    )


def test_find_duplicate_tasks(fake: FakeClient) -> None:
    out = _decode(tools.todoist_find_duplicate_tasks({"project": "Personal"}))
    assert out["success"] is True
    assert out["group_count"] == 1  # "Buy milk" appears twice
    assert out["duplicate_count"] == 1
    group = out["duplicate_groups"][0]
    assert {t["id"] for t in group} == {"1", "3"}


def test_find_duplicate_tasks_no_dups(fake: FakeClient) -> None:
    out = _decode(tools.todoist_find_duplicate_tasks({"project": "Work"}))
    assert out["success"] is True
    assert out["group_count"] == 0


def test_create_or_update_updates_existing(fake: FakeClient) -> None:
    out = _decode(
        tools.todoist_create_or_update_task(
            {"content": "Buy milk", "project": "Personal", "due": "tomorrow"}
        )
    )
    assert out["success"] is True
    assert out["action"] == "updated"
    assert out["matched_existing"] in {"1", "3"}
    update_call = [c for c in fake.calls if c[0] == "update_task"][-1]
    assert update_call[1]["due_string"] == "tomorrow"


def test_create_or_update_noop_when_nothing_to_change(fake: FakeClient) -> None:
    out = _decode(
        tools.todoist_create_or_update_task({"content": "Buy milk", "project": "Personal"})
    )
    assert out["success"] is True
    assert out["action"] == "noop"


def test_create_or_update_creates_when_no_match(fake: FakeClient) -> None:
    out = _decode(
        tools.todoist_create_or_update_task(
            {"content": "Brand new task", "project": "Personal", "due": "friday"}
        )
    )
    assert out["success"] is True
    assert out["action"] == "created"
    create_call = [c for c in fake.calls if c[0] == "create_task"][-1]
    assert create_call[1]["content"] == "Brand new task"
    assert create_call[1]["project_id"] == "100"


def test_create_or_update_matches_whitespace_and_case(fake: FakeClient) -> None:
    out = _decode(
        tools.todoist_create_or_update_task(
            {"content": "  BUY    MILK ", "project": "Personal", "description": "from grocery"}
        )
    )
    assert out["action"] == "updated"
    update_call = [c for c in fake.calls if c[0] == "update_task"][-1]
    assert update_call[1]["description"] == "from grocery"


def test_response_is_valid_json_string(fake: FakeClient) -> None:
    raw = tools.todoist_list_projects({})
    assert isinstance(raw, str)
    payload = json.loads(raw)
    assert payload["success"] is True


def test_handler_never_raises_on_unexpected_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class Boom:
        def list_projects(self, **_kw: Any) -> Any:
            raise RuntimeError("kaboom")

    tools._set_client(Boom())  # type: ignore[arg-type]
    try:
        out = _decode(tools.todoist_list_projects({}))
        assert out["success"] is False
        assert out["code"] == "unexpected_error"
    finally:
        tools._set_client(None)
