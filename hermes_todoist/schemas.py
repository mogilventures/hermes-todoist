"""Tool schemas for the Hermes Todoist plugin.

These are the JSON Schemas the LLM sees. Each ``description`` should give
the model enough signal to decide when (and only when) to call the tool.
"""
from __future__ import annotations

LIST_TASKS = {
    "name": "todoist_list_tasks",
    "description": (
        "List open Todoist tasks. Optionally filter by project (id or name), "
        "section (id or name), parent task, label name, or a Todoist filter "
        'query like "today | overdue". Returns tasks with their IDs, content, '
        "due dates, labels, and priority. Use this to find tasks before "
        "updating or completing them."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project": {
                "type": "string",
                "description": "Project ID or exact (case-insensitive) project name.",
            },
            "section": {
                "type": "string",
                "description": "Section ID or exact (case-insensitive) section name within the project.",
            },
            "parent_id": {"type": "string", "description": "Only return sub-tasks of this parent task ID."},
            "label": {"type": "string", "description": "Filter to tasks with this label name."},
            "filter": {
                "type": "string",
                "description": 'Todoist filter query (e.g. "today", "overdue", "p1 & @work").',
            },
            "lang": {"type": "string", "description": "Language for the filter query (default 'en')."},
            "ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of specific task IDs to fetch.",
            },
            "limit": {"type": "integer", "description": "Max results per page (Todoist default: 50)."},
            "cursor": {"type": "string", "description": "Pagination cursor from a previous response."},
        },
    },
}

GET_TASK = {
    "name": "todoist_get_task",
    "description": "Fetch a single Todoist task by its ID, including full metadata.",
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "Todoist task ID."},
        },
        "required": ["task_id"],
    },
}

CREATE_TASK = {
    "name": "todoist_create_task",
    "description": (
        "Create a new Todoist task. The only required field is `content` (the "
        "task title). Optionally route by project/section name or ID; "
        "labels accept names. Due dates may be given as natural language "
        '("tomorrow 9am") via due_string, an ISO date via due_date, or '
        "a full datetime via due_datetime. Priority is 1 (normal) - 4 (highest)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Task title / what to do."},
            "description": {"type": "string", "description": "Longer description / notes."},
            "project": {"type": "string", "description": "Project ID or name (case-insensitive)."},
            "section": {"type": "string", "description": "Section ID or name within the project."},
            "parent_id": {"type": "string", "description": "Parent task ID (creates a sub-task)."},
            "labels": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Label names to attach.",
            },
            "priority": {
                "type": "integer",
                "enum": [1, 2, 3, 4],
                "description": "1 = normal, 4 = highest.",
            },
            "due_string": {"type": "string", "description": 'Natural language due ("tomorrow 9am").'},
            "due_date": {"type": "string", "description": "Due date YYYY-MM-DD."},
            "due_datetime": {"type": "string", "description": "ISO 8601 due datetime with timezone."},
            "due_lang": {"type": "string", "description": "Language for due_string parsing (default 'en')."},
            "assignee_id": {"type": "string", "description": "Assignee user ID (shared projects only)."},
            "duration": {"type": "integer", "description": "Duration value for calendar time-blocking."},
            "duration_unit": {
                "type": "string",
                "enum": ["minute", "day"],
                "description": "Unit for `duration`.",
            },
            "order": {"type": "integer", "description": "Display order within parent."},
        },
        "required": ["content"],
    },
}

UPDATE_TASK = {
    "name": "todoist_update_task",
    "description": (
        "Update fields on an existing Todoist task. Only provided fields are "
        "changed. To move a task between projects/sections/parents, use the "
        "dedicated move flow (this tool does not change routing)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "Todoist task ID."},
            "content": {"type": "string"},
            "description": {"type": "string"},
            "labels": {"type": "array", "items": {"type": "string"}},
            "priority": {"type": "integer", "enum": [1, 2, 3, 4]},
            "due_string": {"type": "string"},
            "due_date": {"type": "string"},
            "due_datetime": {"type": "string"},
            "due_lang": {"type": "string"},
            "assignee_id": {"type": "string"},
            "duration": {"type": "integer"},
            "duration_unit": {"type": "string", "enum": ["minute", "day"]},
        },
        "required": ["task_id"],
    },
}

COMPLETE_TASK = {
    "name": "todoist_complete_task",
    "description": "Mark a Todoist task as completed. Recurring tasks advance to their next occurrence.",
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
        },
        "required": ["task_id"],
    },
}

REOPEN_TASK = {
    "name": "todoist_reopen_task",
    "description": "Re-open a previously completed Todoist task.",
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
        },
        "required": ["task_id"],
    },
}

DELETE_TASK = {
    "name": "todoist_delete_task",
    "description": (
        "Permanently delete a Todoist task. This is irreversible — the caller "
        "MUST set `confirm: true`. Without confirmation the call returns a "
        "safety error and does not contact the API."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "confirm": {
                "type": "boolean",
                "description": "Must be true to actually delete. Omit or set false to abort.",
            },
        },
        "required": ["task_id", "confirm"],
    },
}

LIST_PROJECTS = {
    "name": "todoist_list_projects",
    "description": "List all Todoist projects the user can see, with IDs and names.",
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer"},
            "cursor": {"type": "string"},
        },
    },
}

LIST_SECTIONS = {
    "name": "todoist_list_sections",
    "description": "List sections, optionally filtered to a single project (id or name).",
    "parameters": {
        "type": "object",
        "properties": {
            "project": {"type": "string", "description": "Project ID or name."},
            "limit": {"type": "integer"},
            "cursor": {"type": "string"},
        },
    },
}

LIST_LABELS = {
    "name": "todoist_list_labels",
    "description": "List all personal labels the user has defined.",
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer"},
            "cursor": {"type": "string"},
        },
    },
}

ADD_COMMENT = {
    "name": "todoist_add_comment",
    "description": (
        "Add a comment to a Todoist task or project. Exactly one of "
        "`task_id` or `project` (id or name) is required."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "project": {"type": "string", "description": "Project ID or name."},
            "content": {"type": "string", "description": "Comment body (Markdown supported)."},
        },
        "required": ["content"],
    },
}

LIST_COMMENTS = {
    "name": "todoist_list_comments",
    "description": (
        "List comments for a task or a project. Exactly one of `task_id` or "
        "`project` (id or name) is required."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "project": {"type": "string"},
            "limit": {"type": "integer"},
            "cursor": {"type": "string"},
        },
    },
}

FIND_DUPLICATES = {
    "name": "todoist_find_duplicate_tasks",
    "description": (
        "Scan open Todoist tasks and group ones whose content (case- and "
        "whitespace-insensitive) is identical. Optionally restrict the scan "
        "to a single project or label. Use this before a bulk-create to "
        "spot tasks the user already has."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project": {"type": "string", "description": "Project ID or name to scope the scan."},
            "label": {"type": "string", "description": "Label name to scope the scan."},
        },
    },
}

CREATE_OR_UPDATE = {
    "name": "todoist_create_or_update_task",
    "description": (
        "Idempotent task upsert. Looks for an existing open task whose "
        "content (case- and whitespace-insensitive) matches the given "
        "`content`, within the same project (and label, if supplied). "
        "If found, applies any supplied due/description/labels/priority "
        "updates to that task and returns it with `action: 'updated'` (or "
        "`'noop'` if no update fields were provided). Otherwise creates a "
        "fresh task and returns it with `action: 'created'`. Prefer this "
        "over plain `todoist_create_task` when the user asks to ensure a "
        "task exists without creating duplicates."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Task title used for dedup matching."},
            "description": {"type": "string"},
            "project": {"type": "string", "description": "Project ID or name (also scopes dup search)."},
            "section": {"type": "string", "description": "Section ID or name."},
            "labels": {"type": "array", "items": {"type": "string"}},
            "label": {
                "type": "string",
                "description": "Label name to scope the duplicate search (separate from labels-to-set).",
            },
            "priority": {"type": "integer", "enum": [1, 2, 3, 4]},
            "due_string": {"type": "string"},
            "due_date": {"type": "string"},
            "due_datetime": {"type": "string"},
            "due_lang": {"type": "string"},
            "duration": {"type": "integer"},
            "duration_unit": {"type": "string", "enum": ["minute", "day"]},
        },
        "required": ["content"],
    },
}
