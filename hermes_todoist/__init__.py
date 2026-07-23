"""Hermes Todoist plugin.

Registers Todoist v1 API tools with the Hermes agent runtime. The plugin is
discoverable via the ``hermes_agent.plugins`` entry-point group, or by
dropping this directory under ``~/.hermes/plugins/todoist/``.
"""
from __future__ import annotations

import logging
from pathlib import Path

from . import schemas, tools
from .client import (
    TodoistAPIError,
    TodoistAuthError,
    TodoistClient,
    TodoistError,
    TodoistRateLimitError,
)

__version__ = "0.1.1"

__all__ = [
    "TodoistAPIError",
    "TodoistAuthError",
    "TodoistClient",
    "TodoistError",
    "TodoistRateLimitError",
    "register",
    "schemas",
    "tools",
]

logger = logging.getLogger(__name__)


def _find_skill_md() -> Path | None:
    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent / "skills" / "todoist" / "SKILL.md",  # repo / git-installed plugin
        here.parent / "skills" / "todoist" / "SKILL.md",  # bundled inside the package
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def register(ctx) -> None:  # type: ignore[no-untyped-def]
    """Register Todoist tools (and optionally the skill) with Hermes."""
    for entry in tools.TOOL_REGISTRY:
        ctx.register_tool(
            name=entry["name"],
            toolset="todoist",
            schema=entry["schema"],
            handler=entry["handler"],
        )

    skill_md = _find_skill_md()
    if skill_md is not None and hasattr(ctx, "register_skill"):
        try:
            ctx.register_skill("todoist", skill_md)
        except Exception as exc:  # don't break tool registration if the skill API differs
            logger.warning("hermes-todoist: failed to register skill: %s", exc)
