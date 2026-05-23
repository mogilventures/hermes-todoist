---
name: todoist-official-mcp
description: How to drive Todoist via the official hosted MCP server (https://ai.todoist.net/mcp) from Hermes — lookup before acting, dedupe before creating, respect context separation, never delete without confirmation.
---

# Todoist (official MCP)

The user has connected Todoist to Hermes via Todoist's **official hosted MCP server** (`https://ai.todoist.net/mcp`). The tools you see are real, talking to a live Todoist account, syncing to every device the user owns the moment you call them. Treat Todoist as the user's **action layer with Hermes** — a shared queue between the two of you, not a scratch pad.

## Tool naming

Tools from this MCP are typically exposed to you with a host-derived prefix like `mcp_todoist_*` (e.g. `mcp_todoist_list_tasks`, `mcp_todoist_create_task`). The exact prefix and the exact tool surface depend on the Hermes host and on what Doist currently ships, and **both can change**. When this skill talks about "the list-tasks tool" or "the create-task tool," map that to whichever real tool name is present in your tool list.

Two practical consequences:

- **Always list your tools first** if you're not sure what's available. The official server's surface is broader than the small `todoist_*` set some users may have seen in older plugins, so do not assume "if I don't see it, it doesn't exist."
- **Prefer the narrowest tool for the job.** If there's both a generic `search` and a specific `list_tasks_by_project`, use the specific one — fewer ways to get a noisy match.

## The cardinal rules

1. **Look before you write.** When the user names a project, section, label, or task in natural language, resolve it first using a list/search/get tool. The official MCP returns rich payloads; reading them in context lets you spot ambiguity ("which 'Personal'?") and confirm you're about to modify the right item.
2. **Dedupe before creating.** Before creating a task, search/list within the target project (and label, if relevant) for an open task with the same intent. If one exists, **update it** instead of creating a second copy. Todoist as an action layer is only useful if it stays uncluttered.
3. **Never delete or archive without explicit confirmation.** The hosted MCP may not enforce a confirmation gate. You must. Before calling any delete/archive/remove tool, echo back what you're about to do ("I'm about to delete 'Old grocery list' from Personal — confirm?") and wait for the user to say yes. Completion is reversible; deletion is not.
4. **When the user wants something "off their list," default to completing, not deleting.** Completion preserves history and lets recurring tasks advance. Only delete when the user explicitly says delete/remove-completely.
5. **Prefer comments and status updates over new tasks for follow-ups.** If the user is responding to or progressing an existing task, add a comment or update its description / due date — don't create a parallel task that fragments the trail.

## Context separation

The user keeps multiple work streams strictly separated in Todoist — e.g. distinct projects (or workspaces) per context like `Twilio`, `Pennie`, `Mogil`, `Personal`, `Trading`. **Do not mix them.** Specifically:

- **Never move or copy a task across contexts** without the user explicitly asking.
- **Never create a task in a context the user did not name.** If the user says "add a task to follow up with Sam" without naming a project, ask which context it belongs to. Do not guess from content (a "trading" keyword does not authorize you to file something under the Trading project).
- **Never combine contexts in a single list/filter result you present to the user** unless they explicitly asked for a cross-context view. If you must query broadly to find something, narrow the result you show.
- **Default project for ambiguous personal items is `Personal`** only if the user has previously said so in this conversation; otherwise ask.

This separation is load-bearing for how the user works. Crossing the streams is worse than being slow.

## Standard flows

### Adding a task

1. Confirm the context (project / workspace) — ask if not stated.
2. List or search within that project for an open task with matching intent.
3. If a match exists: update it (due date, priority, labels, description) rather than creating a duplicate. Tell the user you updated rather than created.
4. If no match: create it. Pass natural-language due strings (`"tomorrow 9am"`, `"every monday"`) where the tool supports them; otherwise pass ISO dates.

### Finding tasks

- For "what's on my plate today / this week / overdue": use the list-tasks tool with a `today` / `7 days` / `overdue` filter (Todoist's filter syntax: `&`, `|`, `!`, `@label`, `p1`, `#project`).
- Scope to one context unless the user asked across all.
- Summarize, don't dump. Group by project, lead with overdue, and surface IDs only on request.

### Updating / completing

- Resolve the task by listing first, then act by ID. Don't call update/complete with name-only arguments and hope it matches — be sure.
- If multiple tasks match, list the candidates back to the user and ask which one.

### Deleting / archiving

- Echo the exact task name and project.
- Wait for an unambiguous yes.
- Then call the destructive tool.
- If the user is just "done with it," **complete instead.** Confirm that's what they want before deleting.

### Comments

- Use the comment tool for status notes, progress, links to artifacts, or any "FYI on this task" content. This is almost always better than creating a sibling task.
- When the user says "leave a note on task X," look up the task ID first.

## Priorities

Todoist's priorities are inverted between UI and API in a way that bites everyone once. **Memorize:** the API treats `priority: 4` as the highest priority (what the UI shows as "P1"), and `priority: 1` as the lowest. If the user says "make it P1," that's API `priority: 4`.

## Pagination

List tools return a cursor (`next_cursor` or similar) when more results exist. Paginate only when the task explicitly needs the full set. For "what's on my plate" style queries, the first page is almost always enough.

## When something goes wrong

The official MCP returns errors as MCP protocol errors and/or structured payloads. Common patterns:

- **`unauthorized` / 401** — OAuth token expired or revoked. Tell the user to re-run `hermes mcp add todoist --url https://ai.todoist.net/mcp --auth oauth`. Don't retry blindly.
- **`rate_limited` / 429** — back off; if the error includes a retry-after, respect it.
- **`not_found` / 404** — the ID or name doesn't exist. List and ask the user which one they meant.
- **5xx** — Todoist server hiccup. Retry once after a short delay; if it persists, surface to user.

If a tool you expected is missing from your tool list, don't substitute a destructive tool ("I'll use delete since I can't find archive"). Tell the user what's missing.

## Style

- After a successful action, give a one-line confirmation that names the task and project — "Updated 'Buy oat milk' in Personal: due tomorrow 9am, P2." Not the ID.
- Don't dump raw tool JSON unless asked. The user wants the summary.
- When you choose to update vs create, or complete vs delete, **say so** in your confirmation. The user is trusting you to dedupe and to prefer reversible operations; make that visible.

## If this server isn't what the user needs

A separate local fallback plugin exists (`hermes-todoist` Python package) that exposes a smaller `todoist_*` tool set with hard delete confirmation and idempotent upsert. Users who specifically need offline execution, personal-token auth, or deterministic upsert semantics can install it alongside or instead of this MCP. You do not need to recommend it unless the user explicitly hits one of those needs.
