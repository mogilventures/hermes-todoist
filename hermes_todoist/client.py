"""Minimal stdlib-only HTTP client for the Todoist API v1.

The token is read from the ``TODOIST_API_TOKEN`` environment variable. It is
never logged, never echoed, and never written to disk by this module.
"""
from __future__ import annotations

import json
import os
import shlex
import uuid
from pathlib import Path
from typing import Any
from urllib import error, parse, request

API_BASE = "https://api.todoist.com/api/v1"
DEFAULT_TIMEOUT = 30
USER_AGENT = "hermes-todoist/0.1.0"
DEFAULT_ENV_PATH = Path.home() / ".config" / "todoist" / "env"


class TodoistError(Exception):
    """Base class for all Todoist client errors."""


class TodoistAuthError(TodoistError):
    """Missing or invalid Todoist API token."""


class TodoistRateLimitError(TodoistError):
    """The Todoist API returned HTTP 429."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class TodoistAPIError(TodoistError):
    """Non-2xx response from the Todoist API."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"Todoist API error {status}: {body[:500]}")
        self.status = status
        self.body = body


def _parse_env_assignment(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return ""
    if stripped.startswith(("'", '"')):
        try:
            parts = shlex.split(stripped, posix=True)
        except ValueError:
            return stripped.strip("'\"")
        return parts[0] if parts else ""
    return stripped


def _load_token_from_env_file(path: Path | None = None) -> str:
    env_path = path or Path(os.environ.get("TODOIST_ENV_FILE", "") or DEFAULT_ENV_PATH)
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return ""
    except OSError as exc:
        raise TodoistAuthError(f"Could not read Todoist token file {env_path}: {exc}") from None

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == "TODOIST_API_TOKEN":
            return _parse_env_assignment(value)
    return ""


def _load_token_from_env() -> str:
    token = os.environ.get("TODOIST_API_TOKEN", "").strip()
    if token:
        return token
    token = _load_token_from_env_file().strip()
    if token:
        return token
    raise TodoistAuthError(
        "Missing TODOIST_API_TOKEN. Generate one at "
        "Todoist Settings → Integrations → Developer → API token, then set "
        "TODOIST_API_TOKEN or run /root/.local/bin/set-todoist-token."
    )


class TodoistClient:
    """Thin wrapper around the Todoist v1 REST API.

    Tokens are loaded lazily, so constructing a client without
    ``TODOIST_API_TOKEN`` set is safe — the error is only raised when an
    actual HTTP call is made.
    """

    def __init__(
        self,
        token: str | None = None,
        base_url: str = API_BASE,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get_token(self) -> str:
        if self._token:
            return self._token
        return _load_token_from_env()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        url = self.base_url + path
        if params:
            cleaned_params = {k: v for k, v in params.items() if v is not None}
            if cleaned_params:
                url += "?" + parse.urlencode(cleaned_params, doseq=True)

        data: bytes | None = None
        headers = {
            "Authorization": f"Bearer {self._get_token()}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        if json_body is not None:
            cleaned_body = {k: v for k, v in json_body.items() if v is not None}
            data = json.dumps(cleaned_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if method.upper() in {"POST", "DELETE"}:
            headers["X-Request-Id"] = str(uuid.uuid4())

        req = request.Request(url, data=data, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except error.HTTPError as exc:
            try:
                body_text = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body_text = ""
            if exc.code in (401, 403):
                raise TodoistAuthError(
                    f"Authentication failed ({exc.code}). Check TODOIST_API_TOKEN."
                ) from None
            if exc.code == 429:
                retry_after_header = None
                if exc.headers is not None:
                    retry_after_header = exc.headers.get("Retry-After")
                retry_after: float | None = None
                if retry_after_header:
                    try:
                        retry_after = float(retry_after_header)
                    except ValueError:
                        retry_after = None
                raise TodoistRateLimitError(
                    f"Rate limited by Todoist API (Retry-After={retry_after_header}).",
                    retry_after=retry_after,
                ) from None
            raise TodoistAPIError(exc.code, body_text) from None
        except error.URLError as exc:
            raise TodoistError(f"Network error contacting Todoist: {exc.reason}") from None

        body = raw.decode("utf-8") if raw else ""
        if not body:
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise TodoistError(f"Invalid JSON in Todoist response: {exc}") from None

    # ---- generic verbs ----
    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, json_body: dict[str, Any] | None = None) -> Any:
        return self._request("POST", path, json_body=json_body or {})

    def delete(self, path: str) -> Any:
        return self._request("DELETE", path)

    # ---- domain endpoints ----
    def list_projects(self, limit: int | None = None, cursor: str | None = None) -> Any:
        return self.get("/projects", params={"limit": limit, "cursor": cursor})

    def list_sections(
        self,
        project_id: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Any:
        return self.get(
            "/sections",
            params={"project_id": project_id, "limit": limit, "cursor": cursor},
        )

    def create_project(self, payload: dict[str, Any]) -> Any:
        return self.post("/projects", json_body=payload)

    def update_project(self, project_id: str, payload: dict[str, Any]) -> Any:
        return self.post(f"/projects/{project_id}", json_body=payload)

    def delete_project(self, project_id: str) -> Any:
        return self.delete(f"/projects/{project_id}")

    def list_labels(self, limit: int | None = None, cursor: str | None = None) -> Any:
        return self.get("/labels", params={"limit": limit, "cursor": cursor})

    def create_section(self, payload: dict[str, Any]) -> Any:
        return self.post("/sections", json_body=payload)

    def update_section(self, section_id: str, payload: dict[str, Any]) -> Any:
        return self.post(f"/sections/{section_id}", json_body=payload)

    def delete_section(self, section_id: str) -> Any:
        return self.delete(f"/sections/{section_id}")

    def create_label(self, payload: dict[str, Any]) -> Any:
        return self.post("/labels", json_body=payload)

    def update_label(self, label_id: str, payload: dict[str, Any]) -> Any:
        return self.post(f"/labels/{label_id}", json_body=payload)

    def delete_label(self, label_id: str) -> Any:
        return self.delete(f"/labels/{label_id}")

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
    ) -> Any:
        params: dict[str, Any] = {
            "project_id": project_id,
            "section_id": section_id,
            "parent_id": parent_id,
            "label": label,
            "filter": filter_query,
            "lang": lang,
            "limit": limit,
            "cursor": cursor,
        }
        if ids:
            params["ids"] = ",".join(ids)
        return self.get("/tasks", params=params)

    def get_task(self, task_id: str) -> Any:
        return self.get(f"/tasks/{task_id}")

    def create_task(self, payload: dict[str, Any]) -> Any:
        return self.post("/tasks", json_body=payload)

    def quick_add_task(self, payload: dict[str, Any]) -> Any:
        return self.post("/tasks/quick", json_body=payload)

    def update_task(self, task_id: str, payload: dict[str, Any]) -> Any:
        return self.post(f"/tasks/{task_id}", json_body=payload)

    def close_task(self, task_id: str) -> Any:
        return self.post(f"/tasks/{task_id}/close", json_body={})

    def reopen_task(self, task_id: str) -> Any:
        return self.post(f"/tasks/{task_id}/reopen", json_body={})

    def delete_task(self, task_id: str) -> Any:
        return self.delete(f"/tasks/{task_id}")

    def move_task(self, task_id: str, payload: dict[str, Any]) -> Any:
        return self.post(f"/tasks/{task_id}/move", json_body=payload)

    def list_comments(
        self,
        *,
        task_id: str | None = None,
        project_id: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Any:
        return self.get(
            "/comments",
            params={
                "task_id": task_id,
                "project_id": project_id,
                "limit": limit,
                "cursor": cursor,
            },
        )

    def create_comment(self, payload: dict[str, Any]) -> Any:
        return self.post("/comments", json_body=payload)
