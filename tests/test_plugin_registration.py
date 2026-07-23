"""Tests that ``register(ctx)`` registers the expected tools + skill."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import hermes_todoist
from hermes_todoist import tools


class FakeCtx:
    def __init__(self) -> None:
        self.tools: list[dict[str, Any]] = []
        self.skills: list[tuple[str, Path]] = []

    def register_tool(
        self, *, name: str, toolset: str, schema: dict[str, Any], handler: Any
    ) -> None:
        self.tools.append({
            "name": name, "toolset": toolset, "schema": schema, "handler": handler,
        })

    def register_skill(self, name: str, path: Path) -> None:
        self.skills.append((name, Path(path)))


EXPECTED_TOOLS = {
    "todoist_list_tasks",
    "todoist_get_task",
    "todoist_create_task",
    "todoist_update_task",
    "todoist_move_task",
    "todoist_reorder_tasks",
    "todoist_complete_task",
    "todoist_reopen_task",
    "todoist_delete_task",
    "todoist_list_projects",
    "todoist_get_project",
    "todoist_create_project",
    "todoist_update_project",
    "todoist_move_project",
    "todoist_reorder_projects",
    "todoist_archive_project",
    "todoist_unarchive_project",
    "todoist_delete_project",
    "todoist_list_sections",
    "todoist_get_section",
    "todoist_create_section",
    "todoist_update_section",
    "todoist_move_section",
    "todoist_reorder_sections",
    "todoist_archive_section",
    "todoist_unarchive_section",
    "todoist_delete_section",
    "todoist_list_labels",
    "todoist_get_label",
    "todoist_create_label",
    "todoist_update_label",
    "todoist_delete_label",
    "todoist_add_comment",
    "todoist_list_comments",
    "todoist_get_comment",
    "todoist_update_comment",
    "todoist_delete_comment",
    "todoist_find_duplicate_tasks",
    "todoist_create_or_update_task",
}


def test_register_registers_all_expected_tools() -> None:
    ctx = FakeCtx()
    hermes_todoist.register(ctx)
    names = {t["name"] for t in ctx.tools}
    assert names == EXPECTED_TOOLS


def test_all_tools_use_todoist_toolset() -> None:
    ctx = FakeCtx()
    hermes_todoist.register(ctx)
    assert all(t["toolset"] == "todoist" for t in ctx.tools)


def test_each_schema_has_name_description_parameters() -> None:
    for entry in tools.TOOL_REGISTRY:
        schema = entry["schema"]
        assert isinstance(schema, dict)
        assert schema.get("name") == entry["name"]
        assert isinstance(schema.get("description"), str)
        assert schema["description"].strip(), f"{entry['name']} schema missing description"
        params = schema.get("parameters")
        assert isinstance(params, dict)
        assert params.get("type") == "object"
        assert isinstance(params.get("properties"), dict)


def test_handlers_are_callable_and_return_strings() -> None:
    for entry in tools.TOOL_REGISTRY:
        assert callable(entry["handler"])
        # Calling with empty params should never raise; we don't care about
        # the actual content here — just that the wrapper guarantees a str.
        try:
            result = entry["handler"]({"task_id": "1", "confirm": True, "content": "x", "id": "1"})
        except Exception as exc:
            raise AssertionError(f"{entry['name']} raised {exc!r}") from exc
        assert isinstance(result, str)
        json.loads(result)  # parse-able JSON


def test_handler_map_matches_registry() -> None:
    assert set(tools.HANDLER_MAP) == EXPECTED_TOOLS
    for entry in tools.TOOL_REGISTRY:
        assert tools.HANDLER_MAP[entry["name"]] is entry["handler"]


def test_skill_registered_when_ctx_supports_it() -> None:
    ctx = FakeCtx()
    hermes_todoist.register(ctx)
    # Skill file lives at repo root in this checkout; register_skill should
    # have been called exactly once.
    assert len(ctx.skills) == 1
    skill_name, skill_path = ctx.skills[0]
    assert skill_name == "todoist"
    assert skill_path.name == "SKILL.md"
    assert skill_path.exists()


def test_register_ignores_missing_register_skill() -> None:
    """Plugins without register_skill (older Hermes versions) still load."""

    class OldCtx:
        def __init__(self) -> None:
            self.tools: list[str] = []

        def register_tool(self, *, name: str, **_kw: Any) -> None:
            self.tools.append(name)

    ctx = OldCtx()
    hermes_todoist.register(ctx)
    assert set(ctx.tools) == EXPECTED_TOOLS


def test_plugin_yaml_lists_match_registry() -> None:
    """Sanity-check that plugin.yaml's provides_tools matches the registry."""
    import re

    plugin_yaml = Path(hermes_todoist.__file__).resolve().parent.parent / "plugin.yaml"
    text = plugin_yaml.read_text()
    listed = set(re.findall(r"^\s*-\s+(todoist_\w+)$", text, re.MULTILINE))
    assert listed == EXPECTED_TOOLS
