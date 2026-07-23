---
name: todoist
description: How to drive Todoist from Hermes — lookup-then-act, dedup before create, never delete without confirmation.
---

# Todoist

You have Todoist tools (prefixed `todoist_*`) that talk to the real Todoist API for the user's account. Touch them carefully — every action is real, visible to the user in their Todoist clients, and most of them sync to multiple devices instantly.

## The cardinal rules

1. **Look before you write.** When the user names a project, section, or task in natural language, resolve it first with `todoist_list_projects` / `todoist_list_sections` / `todoist_list_tasks`. The tools accept names directly, but seeing the actual IDs and existing tasks in context lets you spot ambiguity ("which 'Personal'?") and avoid silent mismatches.
2. **Prefer `todoist_create_or_update_task` over `todoist_create_task`** unless the user explicitly says "make another one" or you're inside a deliberate bulk-create loop. The upsert variant looks for an open task with matching normalized content in the same project (and label, if you pass `label:`) and updates it instead of creating a duplicate.
3. **Never call a `todoist_delete_*` tool without `confirm: true`.** Every delete tool refuses without it and returns a safety error. Deleting a project or section also deletes its descendant tasks, so show the exact object and impact before asking for confirmation. Archive projects and sections when the user wants a reversible removal.
4. **When the user wants something "off their list," default to completing, not deleting.** Completion preserves history; deletion erases it. Only delete when the user explicitly says delete/remove-completely.

## Standard flows

### Adding a task
- If the user gave a project name: pass `project: "Project Name"` directly — the tools resolve names case-insensitively.
- For a natural-language due date, use `due_string: "tomorrow 9am"` (Todoist parses this server-side). For a fixed date use `due_date: "2026-06-15"`. For a precise datetime use `due_datetime`.
- Priority is **1 (normal) – 4 (highest)**. Don't invert this in your head — Todoist's UI shows P1 as highest, but the API maps P1 → `priority: 4`.

### Finding tasks
- For "what's on my plate today / this week / overdue": use `todoist_list_tasks` with `filter: "today"`, `"7 days"`, or `"overdue"`. Todoist's filter language supports `&`, `|`, `!`, `@label`, `p1`, `#project`, etc.
- For a specific project: `project: "Project Name"` (no filter needed).
- Do not combine `filter` with project, section, parent, label, or IDs. Todoist API v1 uses a dedicated filter endpoint; include those constraints in the filter expression instead.

### Bulk operations
- Before any bulk create, run `todoist_find_duplicate_tasks` scoped to the project (and label, if relevant). Resolve the duplicates with the user before adding more.
- Inside a loop where you're definitely creating fresh items, you can drop to `todoist_create_task` — but state that decision out loud first.

### Comments
- `todoist_add_comment` needs either `task_id` or `project` (not both). If the user says "leave a note on task X," look it up first to get the ID.

### Projects and sections
- A Todoist project is a task list; a section is a grouping inside a project.
- Use `todoist_create_project` or `todoist_create_section` when the user asks for a new list or grouping.
- Use the dedicated move tools to change hierarchy or ownership, and the reorder tools only for sibling objects that share the same parent.
- Prefer archive over delete for projects and sections unless the user explicitly requests permanent deletion.

## Pagination

List tools (`todoist_list_tasks`, `todoist_list_projects`, etc.) return a `next_cursor` field when more results are available. Pass it back as `cursor` to keep paginating. Most users have small enough datasets that the first page covers everything; only paginate when `next_cursor` is non-null and the task explicitly needs the full set.

## When something goes wrong

The tool result is always JSON. If `success: false`, the `code` field tells you what to do:

| `code` | What it means | What to do |
|---|---|---|
| `auth_error` | `TODOIST_API_TOKEN` missing or rejected | Tell the user to set the token; don't retry |
| `rate_limited` | Todoist returned 429 | Back off; the `retry_after` field gives seconds |
| `confirmation_required` | Delete called without `confirm: true` | Confirm with the user, then retry with `confirm: true` |
| `api_error` (4xx) | Bad request — wrong ID, missing required field, etc. | Read the message; usually a resolution issue |
| `api_error` (5xx) | Todoist server problem | Retry once after a short delay; otherwise surface to user |
| `client_error` | Name resolution failed (project / section not found) | List projects/sections and ask the user which one |

## Style

- After a successful action, give the user a one-line confirmation that names the task (not the ID) — "Added 'Buy milk' to Personal, due tomorrow 9am."
- Don't dump raw API JSON at the user unless they asked for it. The tools return rich payloads so you can reason; the user wants the summary.
