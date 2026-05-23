"""Small helper CLI for hermes-todoist.

Mostly useful for sanity-checking install, listing the tools the plugin
exposes, and launching the stdio MCP server.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__, tools
from .client import TodoistClient, TodoistError


def _print(obj: object) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True, default=str))


def _cmd_ping(_args: argparse.Namespace) -> int:
    client = TodoistClient()
    resp = client.list_projects(limit=1)
    _print({"ok": True, "raw": resp})
    return 0


def _cmd_tools(_args: argparse.Namespace) -> int:
    _print([entry["name"] for entry in tools.TOOL_REGISTRY])
    return 0


def _cmd_mcp(_args: argparse.Namespace) -> int:
    from . import mcp_server

    return mcp_server.main()


def _cmd_version(_args: argparse.Namespace) -> int:
    print(__version__)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hermes-todoist",
        description="Hermes Todoist plugin helper CLI",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("ping", help="Verify TODOIST_API_TOKEN by calling /projects?limit=1")
    sp.set_defaults(func=_cmd_ping)

    sp = sub.add_parser("tools", help="List the tool names this plugin registers")
    sp.set_defaults(func=_cmd_tools)

    sp = sub.add_parser("mcp", help="Run the stdio MCP server")
    sp.set_defaults(func=_cmd_mcp)

    sp = sub.add_parser("version", help="Print the package version")
    sp.set_defaults(func=_cmd_version)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except TodoistError as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
