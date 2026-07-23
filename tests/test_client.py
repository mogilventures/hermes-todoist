"""Tests for hermes_todoist.client."""
from __future__ import annotations

import io
import json
from unittest.mock import patch
from urllib import error, parse

import pytest

from hermes_todoist.client import (
    TodoistAPIError,
    TodoistAuthError,
    TodoistClient,
    TodoistError,
    TodoistRateLimitError,
)


class _FakeResponse:
    def __init__(self, body: bytes = b"null") -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _http_error(code: int, body: bytes = b"", headers: dict[str, str] | None = None) -> error.HTTPError:
    return error.HTTPError(
        url="https://api.todoist.com/api/v1/_",
        code=code,
        msg="err",
        hdrs=headers or {},  # type: ignore[arg-type]
        fp=io.BytesIO(body),
    )


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv("TODOIST_API_TOKEN", raising=False)
    monkeypatch.setenv("TODOIST_ENV_FILE", str(tmp_path / "missing-todoist-env"))


def test_missing_token_raises_auth_error() -> None:
    client = TodoistClient()
    with pytest.raises(TodoistAuthError):
        client._get_token()


def test_token_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TODOIST_API_TOKEN", "env-token")
    assert TodoistClient()._get_token() == "env-token"


def test_token_from_env_file(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    env_file = tmp_path / "todoist.env"
    env_file.write_text("# comment\nTODOIST_API_TOKEN='file token'\n", encoding="utf-8")
    monkeypatch.setenv("TODOIST_ENV_FILE", str(env_file))
    assert TodoistClient()._get_token() == "file token"


def test_explicit_token_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TODOIST_API_TOKEN", "env-token")
    assert TodoistClient(token="explicit")._get_token() == "explicit"


def test_get_builds_url_and_headers() -> None:
    client = TodoistClient(token="t")
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout):  # type: ignore[no-untyped-def]
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["headers"] = {k.lower(): v for k, v in req.header_items()}
        captured["data"] = req.data
        return _FakeResponse(b'{"results": [], "next_cursor": null}')

    with patch("hermes_todoist.client.request.urlopen", side_effect=fake_urlopen):
        out = client.list_projects(limit=5)

    assert out == {"results": [], "next_cursor": None}
    assert captured["method"] == "GET"
    assert captured["url"].startswith("https://api.todoist.com/api/v1/projects?")
    assert "limit=5" in captured["url"]
    assert captured["headers"]["authorization"] == "Bearer t"
    assert captured["data"] is None


def test_post_sends_json_body_and_strips_none() -> None:
    client = TodoistClient(token="t")
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout):  # type: ignore[no-untyped-def]
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["body"] = json.loads(req.data.decode())
        captured["headers"] = {k.lower(): v for k, v in req.header_items()}
        return _FakeResponse(b'{"id": "1", "content": "x"}')

    with patch("hermes_todoist.client.request.urlopen", side_effect=fake_urlopen):
        out = client.create_task({"content": "x", "description": None, "priority": 2})

    assert out == {"id": "1", "content": "x"}
    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.todoist.com/api/v1/tasks"
    assert captured["body"] == {"content": "x", "priority": 2}
    assert captured["headers"]["content-type"] == "application/json"
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers.get("x-request-id")


def test_quick_add_uses_quick_endpoint() -> None:
    client = TodoistClient(token="t")
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout):  # type: ignore[no-untyped-def]
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["body"] = json.loads(req.data.decode())
        return _FakeResponse(b'{"id": "1", "content": "call Sam"}')

    with patch("hermes_todoist.client.request.urlopen", side_effect=fake_urlopen):
        out = client.quick_add_task({"text": "call Sam tomorrow"})

    assert out["content"] == "call Sam"
    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.todoist.com/api/v1/tasks/quick"
    assert captured["body"] == {"text": "call Sam tomorrow"}


def test_filter_tasks_uses_dedicated_v1_endpoint() -> None:
    client = TodoistClient(token="t")
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout):  # type: ignore[no-untyped-def]
        captured["url"] = req.full_url
        return _FakeResponse(b'{"results": [], "next_cursor": null}')

    with patch("hermes_todoist.client.request.urlopen", side_effect=fake_urlopen):
        client.list_tasks(filter_query="today | overdue", lang="en", limit=20)

    assert captured["url"].startswith("https://api.todoist.com/api/v1/tasks/filter?")
    assert "query=today+%7C+overdue" in captured["url"]
    assert "lang=en" in captured["url"]
    assert "limit=20" in captured["url"]


def test_filter_tasks_rejects_silently_ignored_structured_filters() -> None:
    client = TodoistClient(token="t")
    with pytest.raises(TodoistError, match="cannot be combined"):
        client.list_tasks(filter_query="today", project_id="100")


def test_sync_command_posts_form_and_validates_status() -> None:
    client = TodoistClient(token="t")
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout):  # type: ignore[no-untyped-def]
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in req.header_items()}
        form = parse.parse_qs(req.data.decode())
        command = json.loads(form["commands"][0])[0]
        captured["command"] = command
        response = {"sync_status": {command["uuid"]: "ok"}}
        return _FakeResponse(json.dumps(response).encode())

    with patch("hermes_todoist.client.request.urlopen", side_effect=fake_urlopen):
        client.move_project("100", "200")

    assert captured["url"] == "https://api.todoist.com/api/v1/sync"
    assert captured["headers"]["content-type"] == "application/x-www-form-urlencoded"
    assert captured["command"]["type"] == "project_move"
    assert captured["command"]["args"] == {"id": "100", "parent_id": "200"}


def test_sync_command_error_becomes_client_error() -> None:
    client = TodoistClient(token="t")

    def fake_urlopen(req, timeout):  # type: ignore[no-untyped-def]
        form = parse.parse_qs(req.data.decode())
        command = json.loads(form["commands"][0])[0]
        response = {"sync_status": {command["uuid"]: {"error": "invalid_argument"}}}
        return _FakeResponse(json.dumps(response).encode())

    with patch("hermes_todoist.client.request.urlopen", side_effect=fake_urlopen), pytest.raises(
        TodoistError, match="project_reorder.*failed"
    ):
        client.reorder_projects([{"id": "100", "child_order": 1}])


def test_401_becomes_auth_error() -> None:
    client = TodoistClient(token="t")
    with patch(
        "hermes_todoist.client.request.urlopen",
        side_effect=_http_error(401, b"bad token"),
    ), pytest.raises(TodoistAuthError):
        client.list_projects()


def test_429_becomes_rate_limit_error_with_retry_after() -> None:
    client = TodoistClient(token="t")
    with patch(
        "hermes_todoist.client.request.urlopen",
        side_effect=_http_error(429, b"slow down", headers={"Retry-After": "12"}),
    ), pytest.raises(TodoistRateLimitError) as excinfo:
        client.list_projects()
    assert excinfo.value.retry_after == 12.0


def test_500_becomes_api_error() -> None:
    client = TodoistClient(token="t")
    with patch(
        "hermes_todoist.client.request.urlopen",
        side_effect=_http_error(500, b"boom"),
    ), pytest.raises(TodoistAPIError) as excinfo:
        client.list_projects()
    assert excinfo.value.status == 500
    assert "boom" in excinfo.value.body


def test_network_error_becomes_todoist_error() -> None:
    client = TodoistClient(token="t")
    with patch(
        "hermes_todoist.client.request.urlopen",
        side_effect=error.URLError("dns failure"),
    ), pytest.raises(TodoistError) as excinfo:
        client.list_projects()
    assert not isinstance(excinfo.value, TodoistAPIError)
    assert "dns failure" in str(excinfo.value)


def test_empty_body_returns_none() -> None:
    client = TodoistClient(token="t")
    with patch("hermes_todoist.client.request.urlopen", return_value=_FakeResponse(b"")):
        assert client.close_task("123") is None


def test_invalid_json_raises_todoist_error() -> None:
    client = TodoistClient(token="t")
    with patch(
        "hermes_todoist.client.request.urlopen",
        return_value=_FakeResponse(b"<<not json>>"),
    ), pytest.raises(TodoistError):
        client.list_projects()


def test_delete_path_uses_delete_verb() -> None:
    client = TodoistClient(token="t")
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout):  # type: ignore[no-untyped-def]
        captured["method"] = req.get_method()
        captured["url"] = req.full_url
        return _FakeResponse(b"")

    with patch("hermes_todoist.client.request.urlopen", side_effect=fake_urlopen):
        client.delete_task("abc")

    assert captured["method"] == "DELETE"
    assert captured["url"] == "https://api.todoist.com/api/v1/tasks/abc"


def test_token_is_not_in_repr() -> None:
    client = TodoistClient(token="super-secret-123")
    assert "super-secret-123" not in repr(client)
