# hermes-todoist

Hermes Agent guidance and a local, personal-token Todoist integration.

> **Noah/Hermes default:** use the local wrapper at `/root/.local/bin/todoist` and keep the official hosted Todoist MCP disabled unless explicitly needed. The hosted MCP is richer, but it can trigger repeated OAuth prompts at Hermes startup. The local path uses `TODOIST_API_TOKEN` from env or `~/.config/todoist/env`, avoids startup OAuth entirely, and includes deterministic safety rails.

## Quick start: local wrapper + Hermes

```bash
# 1. Store a personal Todoist API token locally (one-time)
/root/.local/bin/set-todoist-token

# 2. Use the OAuth-free local wrapper
/root/.local/bin/todoist ping
/root/.local/bin/todoist list --filter "today | overdue" --limit 10
```

The official hosted MCP remains useful for broad Todoist coverage, but keep it disabled by default on this host to avoid startup OAuth prompts:

```bash
hermes config set mcp_servers.todoist.enabled false
```

## Official MCP setup (optional)

```bash
# 1. Add the official Todoist MCP server to Hermes (one-time, OAuth in browser)
hermes mcp add todoist --url https://ai.todoist.net/mcp --auth oauth

# 2. Install the Hermes skill that teaches the agent how to drive it safely
hermes skills install \
  https://raw.githubusercontent.com/mogilventures/hermes-todoist/main/skills/todoist-official-mcp/SKILL.md \
  --category productivity
```

That's it. Hermes will surface Todoist tools (typically prefixed `mcp_todoist_*`) and the skill teaches it to look up before acting, dedupe before creating, and confirm destructive operations.

Full setup, OAuth flow, tool-naming notes, and troubleshooting are in [docs/official-mcp-hermes.md](./docs/official-mcp-hermes.md).

## Official MCP vs. local fallback plugin

| | **Official Todoist MCP** (recommended) | **Local plugin** (this repo's Python package) |
|---|---|---|
| Auth | OAuth via Hermes MCP host | `TODOIST_API_TOKEN` env var |
| Runtime | Hosted by Doist | Local Python process / stdio MCP |
| Surface | Broad — whatever Doist exposes & maintains | 14 curated tools, intentionally small |
| Tool names | Host-prefixed (e.g. `mcp_todoist_*`) | Native Hermes (`todoist_*`) |
| Delete safety | Whatever Doist ships | Hard refuse without `confirm: true` |
| Idempotent create | Not guaranteed | `todoist_create_or_update_task` upserts by normalized content |
| Name resolution | Per Doist | Project/section names resolved case-insensitively client-side |
| Network requirement | Internet + OAuth | Internet to api.todoist.com only |
| Dependencies | None (host handles it) | stdlib `urllib` only |
| Best for | Day-to-day use | Air-gapped envs, scripts that need deterministic upsert, tests, automation pipelines that own their own token |

**Rule of thumb:** start with the official MCP. Reach for this plugin only if you specifically need one of the local-fallback properties on the right.

## Repository layout

```
docs/
  official-mcp-hermes.md      # Setup guide for the recommended path
skills/
  todoist/                    # Skill that ships with the local plugin (todoist_* tools)
  todoist-official-mcp/       # Skill for the official hosted MCP (mcp_todoist_* tools)
hermes_todoist/               # Local fallback plugin (Python, stdlib-only)
tests/                        # Unit tests for the local plugin
```

You can install either skill on its own — `skills/todoist-official-mcp/` is the new "primary" skill and does not depend on this Python package being installed.

---

# Local fallback plugin

Everything below documents the Python plugin in `hermes_todoist/`. Use it only if you specifically need a Hermes-native, local, personal-token integration with deterministic safety rails.

Choose it when you want:

- **Native Hermes tools + bundled skill** — tool names are direct (`todoist_*`) and the skill teaches Hermes the safe operating pattern.
- **Zero runtime dependencies** — stdlib `urllib` only.
- **Local personal-token auth** — read from `TODOIST_API_TOKEN`, never logged, never written to disk by this package.
- **Safety rails** — `todoist_delete_task` refuses without `confirm: true`; `todoist_create_or_update_task` deduplicates by normalized content.
- **Resolves names** — projects and sections can be passed by exact (case-insensitive) name or by ID; labels are passed by Todoist label name.

## Tools

| Tool | What it does |
|------|--------------|
| `todoist_list_tasks` | List open tasks; filter by project / section / label / Todoist filter query |
| `todoist_get_task` | Fetch a single task by ID |
| `todoist_create_task` | Create a task (project / labels accepted as names) |
| `todoist_update_task` | Patch any subset of fields on a task |
| `todoist_complete_task` | Mark complete (recurring tasks advance) |
| `todoist_reopen_task` | Un-complete a task |
| `todoist_delete_task` | **Requires `confirm: true`** — irreversible |
| `todoist_list_projects` | List all projects |
| `todoist_list_sections` | List sections, optionally scoped to a project |
| `todoist_list_labels` | List personal labels |
| `todoist_add_comment` | Comment on a task or a project |
| `todoist_list_comments` | List comments on a task or a project |
| `todoist_find_duplicate_tasks` | Group open tasks with identical normalized content |
| `todoist_create_or_update_task` | Idempotent upsert by normalized content |

Every handler returns a JSON string of the form `{"success": true, ...}` or `{"success": false, "error": "...", "code": "..."}`. Errors never raise — the wrapper guarantees a JSON response. List endpoints preserve `next_cursor` for pagination.

## Install

### As a Hermes plugin

```bash
hermes plugins install mogilventures/hermes-todoist --enable
```

The installer prompts for `TODOIST_API_TOKEN` (Todoist → Settings → Integrations → Developer → API token) and stores it via the standard Hermes plugin install flow.

### As a pip package

```bash
pip install hermes-todoist
hermes plugins enable todoist
```

The package registers under the `hermes_agent.plugins` entry-point group, so Hermes auto-discovers it on next start.

### From a clone

```bash
git clone https://github.com/mogilventures/hermes-todoist ~/.hermes/plugins/todoist
hermes plugins enable todoist
export TODOIST_API_TOKEN=...
```

## Configuration

The plugin reads exactly one environment variable:

| Var | Required | Description |
|-----|----------|-------------|
| `TODOIST_API_TOKEN` | yes | Your personal Todoist API token. |

The token is loaded lazily on the first HTTP call, so importing the package or running `hermes plugins list` does not require it.

## Usage examples

Once enabled, talk to Hermes the way you'd talk to a Todoist-savvy assistant — the bundled skill tells the model which tool to pick and how to dedupe before creating.

> **You:** Add "Buy oat milk" to Personal, due tomorrow 9am, priority 3.
>
> Hermes calls `todoist_create_or_update_task(content="Buy oat milk", project="Personal", due_string="tomorrow 9am", priority=3)`. If the task already exists in Personal, the due date and priority are applied to the existing task instead of creating a duplicate.

> **You:** What's overdue?
>
> Hermes calls `todoist_list_tasks(filter="overdue")` and summarizes the result.

> **You:** Mark "Write report" done.
>
> Hermes calls `todoist_list_tasks(filter="@work")` (or by project) to find the ID, then `todoist_complete_task(task_id="…")`.

> **You:** Delete the "Old grocery list" task.
>
> Hermes resolves the ID, then calls `todoist_delete_task(task_id="…", confirm=true)`. The `confirm` flag is required — without it the tool refuses and returns `code: "confirmation_required"`.

### Calling tools directly

```python
import json
from hermes_todoist import tools

print(json.loads(tools.todoist_list_tasks({"filter": "today"})))
print(json.loads(tools.todoist_create_task({"content": "Ship hermes-todoist", "project": "Work"})))
```

### Helper CLI

```bash
hermes-todoist version          # 0.1.0
hermes-todoist tools            # list registered tool names
hermes-todoist ping             # GET /projects?limit=1 — verifies token + connectivity
hermes-todoist mcp              # run the stdio MCP server (see below)
```

## MCP server (local stdio)

`hermes_todoist.mcp_server` is a stdlib-only stdio MCP server that exposes the same 14 tools as native MCP tools. This is **not** the recommended path for Hermes — use the official hosted MCP for that. Use this stdio server from Claude Desktop, mcp-cli, or any other MCP host that does not support hosted/OAuth MCP.

Claude Desktop `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "todoist": {
      "command": "hermes-todoist",
      "args": ["mcp"],
      "env": { "TODOIST_API_TOKEN": "your-token-here" }
    }
  }
}
```

Or via plain Python:

```json
{
  "mcpServers": {
    "todoist": {
      "command": "python",
      "args": ["-m", "hermes_todoist.mcp_server"],
      "env": { "TODOIST_API_TOKEN": "your-token-here" }
    }
  }
}
```

The server speaks the `2024-11-05` revision of the protocol — `initialize`, `tools/list`, `tools/call`, and `ping` are implemented; notifications are accepted and ignored.

## Development

```bash
git clone https://github.com/mogilventures/hermes-todoist
cd hermes-todoist
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest              # 55 unit tests, no token required (all HTTP is mocked)
ruff check hermes_todoist tests
```

Recommended CI is the same command sequence on Python 3.10, 3.11, and 3.12: install `.[dev]`, run `ruff check hermes_todoist tests`, then run `pytest -v`.

### If pytest is unavailable

The test suite uses only `unittest.mock` plus the `pytest` framework — no other plugins. If `pip install pytest` is blocked in your environment, you can still smoke-test with stdlib only:

```bash
python -c "import hermes_todoist; from hermes_todoist import tools; \
  ctx = type('C',(),{'register_tool':lambda self,**k:None,'register_skill':lambda self,*a:None})(); \
  hermes_todoist.register(ctx); print('ok,', len(tools.TOOL_REGISTRY), 'tools')"
```

### Optional: live API smoke test

Tests in CI do not touch the real Todoist API. If you want to verify against a real account locally:

```bash
export TODOIST_API_TOKEN=your-token
export HERMES_TODOIST_LIVE=1
hermes-todoist ping
```

The `hermes-todoist ping` command performs `GET /projects?limit=1` and prints the response — minimal traffic, but enough to confirm the token works. **Do not** enable this in CI; the rate-limit and side-effect risks are not worth it.

## Design notes

- **API base.** `https://api.todoist.com/api/v1`. The plugin sets `User-Agent: hermes-todoist/<version>`.
- **Token loading.** Lazy. `TodoistClient()` succeeds without a token; the token is required only when a request is actually made. This makes `import hermes_todoist` safe inside test runners and CI.
- **Pagination.** Todoist returns `{"results": [...], "next_cursor": "..." | null}` for paginated endpoints. The plugin normalizes both shapes (`results` envelope and bare list) and surfaces `next_cursor` in every list response.
- **Name resolution.** Projects and sections are resolved by exact case-insensitive name match against the full list (`limit=200`). Numeric IDs are passed through without a lookup. If a name doesn't match, the tool returns `code: "client_error"` rather than guessing.
- **Duplicate detection.** Normalization is `lower(strip(collapse_whitespace(content)))`. `todoist_create_or_update_task` updates `description`, `due_*`, `labels`, `priority`, `duration`, and `duration_unit` on the matched task when supplied; otherwise creates a new one. `todoist_find_duplicate_tasks` reports groups of size ≥ 2.
- **Error codes.** `auth_error`, `rate_limited` (with `retry_after`), `api_error` (with HTTP status), `client_error`, `confirmation_required`, `unexpected_error`.

## License

MIT — see [LICENSE](./LICENSE).
