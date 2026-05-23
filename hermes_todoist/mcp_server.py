"""Minimal stdio MCP server exposing hermes-todoist tools.

This is a small, stdlib-only implementation of the
`Model Context Protocol <https://modelcontextprotocol.io>`_ over stdio. It
speaks just enough of the protocol — ``initialize``, ``tools/list``,
``tools/call`` — to let any MCP client (Claude Desktop, mcp-cli, etc.) call
the same handlers that Hermes uses.

Run it directly:

.. code-block:: bash

    python -m hermes_todoist.mcp_server
    # or
    hermes-todoist mcp
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any

from . import tools

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "hermes-todoist"
SERVER_VERSION = "0.1.0"

logger = logging.getLogger(__name__)


def _write(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _build_tools_list() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in tools.TOOL_REGISTRY:
        schema = entry["schema"]
        out.append(
            {
                "name": entry["name"],
                "description": schema.get("description", ""),
                "inputSchema": schema.get("parameters", {"type": "object", "properties": {}}),
            }
        )
    return out


def _handle(msg: dict[str, Any]) -> dict[str, Any] | None:
    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": _build_tools_list()},
        }

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        handler = tools.HANDLER_MAP.get(name)
        if handler is None:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Unknown tool: {name}"},
            }
        result_text = handler(arguments)
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"content": [{"type": "text", "text": result_text}]},
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    if isinstance(method, str) and method.startswith("notifications/"):
        return None  # notifications are fire-and-forget

    if msg_id is None:
        return None  # other notifications get no response

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main(argv: list[str] | None = None) -> int:
    del argv  # no flags yet
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                }
            )
            continue
        try:
            response = _handle(msg)
        except Exception as exc:  # never crash the server on a bad request
            logger.exception("hermes-todoist mcp: handler crashed")
            response = {
                "jsonrpc": "2.0",
                "id": msg.get("id"),
                "error": {"code": -32603, "message": f"Internal error: {exc}"},
            }
        if response is not None:
            _write(response)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
