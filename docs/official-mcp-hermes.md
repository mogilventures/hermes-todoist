# Using the official Todoist MCP with Hermes

Todoist now maintains an official hosted MCP server at:

```
https://ai.todoist.net/mcp
```

It speaks HTTP MCP with OAuth. Hermes Agent supports both, so the integration is a one-line `hermes mcp add` plus a browser OAuth handshake.

This document covers:

- Setting it up
- The OAuth flow
- How to test that it's working
- What the tool names look like once connected
- When to fall back to this repo's local plugin

## Why this is the recommended path

- **Doist owns it.** New endpoints, schema changes, and account-level behavior land there first.
- **Broader surface area** than the 14-tool local plugin. Expect more verbs (workspaces, sharing, viewing completed items, etc.) and richer payloads.
- **OAuth** — no personal token sitting in an env var, no per-machine setup.
- **Zero local runtime.** Nothing to install, nothing to keep running.

The trade-off: you get whatever safety semantics Doist ships. If you need a hard `confirm: true` gate on deletes or idempotent upsert by normalized content, see [Falling back to the local plugin](#falling-back-to-the-local-plugin) below.

## Setup

### 1. Add the server to Hermes

```bash
hermes mcp add todoist --url https://ai.todoist.net/mcp --auth oauth
```

This registers the MCP server under the name `todoist`. Pick a different name (e.g. `todoist-work`) if you want to wire up multiple Todoist accounts.

### 2. Complete the OAuth flow

When Hermes first needs the server (next agent run, or run `hermes mcp test todoist` to force it), it will open a browser window for the Todoist OAuth consent screen. Approve the requested scopes; Hermes stores the resulting token in its standard MCP credential store.

You will not see the token, and it should not appear in any file you check in. If you ever need to revoke access, do it from Todoist → Settings → Integrations → Connected Apps.

### 3. Install the Hermes skill

```bash
hermes skills install \
  https://raw.githubusercontent.com/mogilventures/hermes-todoist/main/skills/todoist-official-mcp/SKILL.md \
  --category productivity
```

This installs only [`skills/todoist-official-mcp/SKILL.md`](../skills/todoist-official-mcp/SKILL.md) — not the Python plugin. The skill teaches Hermes the rules of the road: look up before acting, dedupe before creating, confirm before deleting, respect context separation.

## Testing it works

After setup, run a low-risk read-only request:

```
"List my Todoist projects."
```

Hermes should call a tool that looks like `mcp_todoist_list_projects` (or similar — the exact name depends on Doist's schema and Hermes's MCP prefix convention). You'll see the project names in the response.

If you want a CLI-level check that doesn't go through the agent:

```bash
hermes mcp test todoist          # health check + list tools
hermes mcp login todoist         # force/retry OAuth if needed
```

If `hermes mcp test todoist` fails:

- **`unauthorized` / `401`** — the OAuth token expired or was revoked. Re-run `hermes mcp add todoist --url https://ai.todoist.net/mcp --auth oauth` to re-auth.
- **`connection refused` / DNS error** — confirm `https://ai.todoist.net/mcp` is reachable from your network. The endpoint is HTTPS-only.
- **`tool not found`** — the tool naming may have shifted; re-list with `hermes mcp test todoist` and update the skill if the rename is permanent.

## Tool naming

The official MCP server registers tools under names that Doist controls. Hermes typically exposes them to the model with a host-derived prefix, so they show up looking like:

```
mcp_todoist_list_tasks
mcp_todoist_get_task
mcp_todoist_create_task
mcp_todoist_update_task
mcp_todoist_complete_task
mcp_todoist_delete_task
mcp_todoist_add_comment
...
```

(Exact names vary — list them with `hermes mcp test todoist` after install.)

The skill in this repo is written to be **prefix-agnostic**: it refers to capabilities ("the list-tasks tool", "the create-task tool") rather than exact identifiers, so it keeps working if Hermes's prefix convention changes or Doist renames a tool. If you author your own follow-on skills, do the same.

### Expect a broader surface than the local plugin

The local plugin in this repo intentionally exposes 14 curated tools. The official MCP will likely expose more — including things the local plugin does not (workspaces, completed-task views, richer search, etc.). When you see a tool you don't recognize, default to listing/reading from it before writing, and prefer the most narrowly-scoped tool for the job.

## Falling back to the local plugin

Use this repo's Python plugin (`hermes_todoist/`) instead of — or alongside — the official MCP when you need:

- **Local / offline execution.** Stdlib `urllib` only, no hosted dependency.
- **Personal-token auth.** Pipelines, scripts, or CI where OAuth doesn't fit.
- **Hard delete confirmation.** `todoist_delete_task` refuses without `confirm: true`. The official server may delete on first call.
- **Idempotent create-or-update.** `todoist_create_or_update_task` matches by normalized content and updates in place — useful for automations that re-run.
- **Stable native tool names.** `todoist_*` instead of host-prefixed `mcp_todoist_*`. Easier to write deterministic skills/tests against.
- **Duplicate detection.** `todoist_find_duplicate_tasks` groups open tasks by normalized content.

You can install both at once. If Hermes ends up with overlapping capabilities, the skill that's most specific (or installed most recently, depending on Hermes's resolution rules) usually wins; verify in your environment before relying on tie-breaking.

See the main [README](../README.md#local-fallback-plugin) for local-plugin setup.

## Removing the official MCP

```bash
hermes mcp remove todoist
```

Then revoke the OAuth grant from Todoist → Settings → Integrations → Connected Apps so the stored refresh token can't be reused.
