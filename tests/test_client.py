"""Tests for hermes_todoist.client."""
from __future__ import annotations

import io
import json
from unittest.mock import patch
from urllib import error

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
    monkeypatch.delenv("TODOIST_API_TOKEN_FILE", raising=False)
    monkeypatch.setenv("TODOIST_ENV_FILE", str(tmp_path / "missing-todoist-env"))


def test_missing_token_raises_auth_error() -> None:
    client = TodoistClient()
    with pytest.raises(TodoistAuthError):
        client._get_token()


def test_token_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TODOIST_API_TOKEN", "env-token")
    assert TodoistClient()._get_token() == "env-token"


def test_token_from_indirect_env_reference(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    token_file = tmp_path / "todoist-token"
    token_file.write_text("mounted-secret\n", encoding="utf-8")
    monkeypatch.setenv("TODOIST_API_TOKEN", f"@{token_file}")
    assert TodoistClient()._get_token() == "mounted-secret"


def test_token_from_explicit_file_variable(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    token_file = tmp_path / "todoist-token"
    token_file.write_text("file-secret\n", encoding="utf-8")
    monkeypatch.setenv("TODOIST_API_TOKEN_FILE", str(token_file))
    assert TodoistClient()._get_token() == "file-secret"


def test_direct_token_takes_precedence_over_file(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    token_file = tmp_path / "todoist-token"
    token_file.write_text("file-secret\n", encoding="utf-8")
    monkeypatch.setenv("TODOIST_API_TOKEN", "direct-secret")
    monkeypatch.setenv("TODOIST_API_TOKEN_FILE", str(token_file))
    assert TodoistClient()._get_token() == "direct-secret"


def test_token_file_requires_absolute_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TODOIST_API_TOKEN", "@relative/token")
    with pytest.raises(TodoistAuthError, match="absolute path"):
        TodoistClient()._get_token()


def test_token_file_rejects_multiple_lines(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    token_file = tmp_path / "todoist-token"
    token_file.write_text("first\nsecond\n", encoding="utf-8")
    monkeypatch.setenv("TODOIST_API_TOKEN_FILE", str(token_file))
    with pytest.raises(TodoistAuthError, match="one line"):
        TodoistClient()._get_token()


def test_token_file_rejects_unexpected_size(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    token_file = tmp_path / "todoist-token"
    token_file.write_text("x" * (16 * 1024 + 1), encoding="utf-8")
    monkeypatch.setenv("TODOIST_API_TOKEN_FILE", str(token_file))
    with pytest.raises(TodoistAuthError, match="unexpectedly large"):
        TodoistClient()._get_token()


def test_env_file_requires_absolute_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TODOIST_ENV_FILE", "relative/todoist.env")
    with pytest.raises(TodoistAuthError, match="absolute path"):
        TodoistClient()._get_token()


def test_token_file_error_does_not_expose_secret_path_contents(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    token_file = tmp_path / "todoist-token"
    secret = "first-secret\nsecond-secret"
    token_file.write_text(secret, encoding="utf-8")
    monkeypatch.setenv("TODOIST_API_TOKEN_FILE", str(token_file))
    with pytest.raises(TodoistAuthError) as excinfo:
        TodoistClient()._get_token()
    assert "first-secret" not in str(excinfo.value)
    assert "second-secret" not in str(excinfo.value)


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
