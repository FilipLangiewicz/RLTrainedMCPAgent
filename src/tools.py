"""MCP server that gives one board to a model with the 14 tools of mcp-atlassian 0.23.1 (design D4 to D6)."""

import asyncio
import hashlib
import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import NamedTuple

import jsonschema
import mcp_types as types
from mcp.server.lowlevel import Server

from src.environment import (
    NO_ISSUE,
    STATUSES,
    TRANSITIONS,
    Board,
    BoardError,
    Issue,
    Person,
    format_time,
    load_board,
    parse_date,
)
from src.jql import JQLError, search

ROOT = Path(__file__).resolve().parents[1]
TOOL_DEFS = json.loads((ROOT / "data" / "mcp_atlassian_tools.json").read_text(encoding="utf-8"))
TOOL_NAMES = [t["name"] for t in TOOL_DEFS]
SCHEMAS = {t["name"]: t["inputSchema"] for t in TOOL_DEFS}
READ_TOOLS = {t["name"] for t in TOOL_DEFS if t.get("annotations", {}).get("readOnlyHint")}
DEFAULT_FIELDS = "assignee,labels,issuetype,reporter,summary,description,created,updated,versions,priority,status"
MAX_SEARCH = 50
TIME_ZONES = {timedelta(hours=1): "CET", timedelta(hours=2): "CEST", timedelta(0): "UTC"}

# The order of the keys in an issue of a real result.
FIELD_KEYS = {
    "summary": "summary", "description": "description", "status": "status", "issuetype": "issue_type",
    "issue_type": "issue_type", "priority": "priority", "project": "project", "worklog": "worklog",
    "assignee": "assignee", "reporter": "reporter", "labels": "labels", "created": "created", "updated": "updated",
}
KEY_ORDER = ("summary", "description", "status", "issue_type", "priority", "project", "worklog",
             "assignee", "reporter", "labels", "created", "updated")


class ToolError(Exception):
    """An error result of a tool. The message is the message of the real server."""


class ToolResult(NamedTuple):
    text: str
    is_error: bool


# Formats of the results (D5)

def issue_date(text: str) -> str:
    dt = parse_date(text)
    return f"{dt:%Y-%m-%d %H:%M:%S} {TIME_ZONES.get(dt.utcoffset(), dt.strftime('%z'))}"


def event_date(text: str) -> str:
    return parse_date(text).isoformat(sep=" ", timespec="microseconds")


def person_dict(person: Person) -> dict:
    avatar = hashlib.md5(person.account_id.encode()).hexdigest()
    return {"account_id": person.account_id, "display_name": person.display_name, "name": person.display_name,
            "email": person.email, "avatar_url": f"https://secure.gravatar.com/avatar/{avatar}?d=identicon"}


def worklog_dict(board: Board, w) -> dict:
    return {"id": w.id, "comment": w.comment, "created": event_date(w.started), "updated": event_date(w.started),
            "started": event_date(w.started), "time_spent": format_time(w.time_spent_seconds),
            "time_spent_seconds": w.time_spent_seconds, "author": board.display_name(w.author)}


def _requested(fields: str | None) -> set[str]:
    names = {f.strip().lower() for f in (fields or DEFAULT_FIELDS).split(",") if f.strip()}
    if "*all" in names:
        return set(KEY_ORDER)
    return {FIELD_KEYS[n] for n in names if n in FIELD_KEYS}


def issue_dict(board: Board, issue: Issue, fields: str | None = None, link: str = "browse_url") -> dict:
    """An issue in the format of `JiraIssue.to_simplified_dict()`. Empty fields are left out, as in the real results."""
    keys = _requested(fields)
    values = {
        "summary": issue.summary,
        "description": issue.description,
        "status": {"name": issue.status, "category": STATUSES[issue.status][0], "color": STATUSES[issue.status][1]},
        "issue_type": {"name": issue.issue_type},
        "priority": {"name": issue.priority},
        "project": {"key": board.project.key, "name": board.project.name,
                    "avatar_url": f"{board.site}/rest/api/2/universal_avatar/view/type/project/avatar/10402"},
        "worklog": {"startAt": 0, "maxResults": 20, "total": len(issue.worklogs),
                    "worklogs": [worklog_dict(board, w) for w in issue.worklogs]},
        "assignee": person_dict(board.person(issue.assignee)) if issue.assignee else {"display_name": "Unassigned"},
        "reporter": person_dict(board.person(issue.reporter)) if issue.reporter else None,
        "labels": sorted(issue.labels),
        "created": issue_date(issue.created),
        "updated": issue_date(issue.updated),
    }
    result = {"id": issue.id, "key": issue.key}
    for key in KEY_ORDER:
        if key in keys and values[key] not in (None, "", []):
            result[key] = values[key]
            if key == "summary":
                result[link] = (f"{board.site}/browse/{issue.key}" if link == "browse_url"
                                else f"{board.site}/rest/api/2/issue/{issue.id}")
    return result


def _keys(text: str) -> list[str]:
    return [k.strip().upper() for k in str(text).split(",") if k.strip()]


def _json_object(text: str | None, name: str) -> dict:
    if text is None or text == "":
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError as e:
        raise ToolError(f"Invalid JSON in {name}: {e.msg}") from None
    if not isinstance(value, dict):
        raise ToolError(f"{name} must be a JSON object.")
    return value


def make_tools(board: Board) -> dict:
    """Return the tool functions for `board`. A function returns a JSON-compatible value or raises ToolError."""

    def get_issue_or_error(key: str) -> Issue:
        issue = board.find_issue(key)
        if issue is None:
            raise ToolError(f"Issue {key} not found. Verify the issue key and project access.")
        return issue

    def jira_search(jql, fields=DEFAULT_FIELDS, limit=10, start_at=0, projects_filter=None, expand=None,
                    page_token=None, **_):
        try:
            found = search(board, jql)
        except JQLError as e:
            raise ToolError(str(e)) from None
        if projects_filter and board.project.key not in _keys(projects_filter):
            found = []
        limit = max(1, min(int(limit), MAX_SEARCH))
        page = found[int(start_at): int(start_at) + limit]
        return {"total": -1, "start_at": int(start_at), "max_results": limit,
                "issues": [issue_dict(board, i, fields) for i in page]}

    def jira_get_issue(issue_key, fields=DEFAULT_FIELDS, comment_limit=10, **_):
        issue = get_issue_or_error(issue_key)
        result = issue_dict(board, issue, fields)
        comments = issue.comments[: int(comment_limit or 0)]
        if comments:
            result["comments"] = [{"id": c.id, "body": c.body, "author": person_dict(board.person(c.author)),
                                   "created": c.created, "updated": c.created} for c in comments]
        return result

    def jira_search_assignable_users(query, project_key=None, issue_key=None, limit=20):
        users = [person_dict(p) for p in board.search_persons(query)][: int(limit)]
        return {"success": True, "count": len(users), "users": users}

    def jira_get_agile_boards(board_name=None, project_key=None, board_type=None, start_at=0, limit=10):
        b = board.board
        if ((project_key and project_key.upper() != board.project.key)
                or (board_name and board_name.lower() not in b.name.lower())
                or (board_type and board_type.lower() != b.type)):
            return []
        return [{"id": b.id, "name": b.name, "type": b.type}][int(start_at): int(start_at) + int(limit)]

    def jira_get_sprints_from_board(board_id, state=None, start_at=0, limit=10):
        if str(board_id).strip() != board.board.id:
            raise ToolError("The requested board cannot be viewed because it either does not exist "
                            "or you do not have permission to view it.")
        states = {s.strip().lower() for s in state.split(",")} if state else None
        order = {"closed": 0, "active": 1, "future": 2}
        sprints = sorted((s for s in board.sprints if states is None or s.state in states),
                         key=lambda s: (order[s.state], int(s.id)))
        result = []
        for s in sprints[int(start_at): int(start_at) + int(limit)]:
            item = {"id": s.id, "name": s.name, "state": s.state, "start_date": s.start_date, "end_date": s.end_date}
            item = {k: v for k, v in item.items() if v is not None}
            if s.goal:
                item["goal"] = s.goal
            result.append(item)
        return result

    def jira_get_transitions(issue_key):
        get_issue_or_error(issue_key)
        return [{"id": tid, "name": name} for tid, name in TRANSITIONS.items()]

    def jira_get_worklog(issue_key):
        issue = get_issue_or_error(issue_key)
        return {"worklogs": [worklog_dict(board, w) for w in issue.worklogs]}

    def jira_create_issue(project_key, summary, issue_type, assignee=None, description=None, components=None,
                          additional_fields=None):
        if project_key.upper() != board.project.key:
            raise ToolError("Specify a valid project ID or key")
        extra = _json_object(additional_fields, "additional_fields")
        issue = board.create_issue(summary, issue_type, description=description, assignee=assignee,
                                   priority=extra.get("priority"), labels=extra.get("labels"))
        return {"message": "Issue created successfully", "issue": issue_dict(board, issue, "*all", link="url")}

    def jira_update_issue(issue_key, fields, additional_fields=None, components=None, attachments=None,
                          return_fields="*all"):
        prefix = f"Failed to update issue {issue_key}: Failed to update issue {issue_key}: "
        try:
            values = {**_json_object(fields, "fields"), **_json_object(additional_fields, "additional_fields")}
            issue = board.update_fields(issue_key, values)
        except (BoardError, ToolError) as e:
            raise ToolError(prefix + str(e)) from None
        return {"message": "Issue updated successfully", "issue": issue_dict(board, issue, return_fields, link="url")}

    def jira_transition_issue(issue_key, transition_id, fields=None, comment=None):
        values = _json_object(fields, "fields")
        issue = board.transition(issue_key, transition_id)
        board.update_fields(issue_key, values)
        if comment:
            board.add_comment(issue_key, comment)
        return {"message": f"Issue {issue.key} transitioned successfully", "issue": issue_dict(board, issue)}

    def jira_add_comment(issue_key, body, visibility=None, public=None):
        try:
            c = board.add_comment(issue_key, body)
        except BoardError as e:
            raise ToolError(f"Error adding comment: {e}") from None
        return {"id": c.id, "body": c.body, "created": event_date(c.created), "author": board.display_name(c.author)}

    def jira_add_worklog(issue_key, time_spent, comment=None, started=None, original_estimate=None,
                         remaining_estimate=None):
        try:
            w = board.add_worklog(issue_key, time_spent, comment)
        except BoardError as e:
            raise ToolError(f"Error adding worklog: {e}") from None
        return {"message": "Worklog added successfully",
                "worklog": {**worklog_dict(board, w), "original_estimate_updated": False,
                            "remaining_estimate_updated": False}}

    def jira_add_issues_to_sprint(sprint_id, issue_keys):
        issues = board.add_to_sprint(sprint_id, _keys(issue_keys))
        return {"message": f"Successfully added {len(issues)} issue(s) to sprint", "sprint_id": str(sprint_id),
                "issue_keys": [i.key for i in issues]}

    def jira_move_issues_to_backlog(issue_keys):
        issues = board.move_to_backlog(_keys(issue_keys))
        return {"message": f"Successfully moved {len(issues)} issue(s) to backlog", "issue_keys": [i.key for i in issues]}

    tools = {name: fn for name, fn in locals().items() if name.startswith("jira_")}
    assert sorted(tools) == sorted(TOOL_NAMES)
    return tools


# Arguments

def _coerce(arguments: dict, schema: dict) -> dict:
    """Drop null values and convert numbers in text and texts as numbers, as the type conversion of the real server."""
    result = {}
    for name, value in arguments.items():
        if value is None:
            continue
        kind = schema.get("properties", {}).get(name, {}).get("type")
        if kind == "string" and isinstance(value, int | float) and not isinstance(value, bool):
            value = str(value)
        elif kind == "integer" and isinstance(value, str) and value.strip().lstrip("-").isdigit():
            value = int(value)
        result[name] = value
    return result


def call_tool(board: Board, tools: dict, name: str, arguments: dict | None) -> ToolResult:
    """Run one tool. An error result has the text of the real server. A failed call does not change the board."""
    short = name.removeprefix("jira_")
    if name not in tools:
        return ToolResult(f"Unknown tool: {name}", True)
    arguments = _coerce(arguments or {}, SCHEMAS[name])
    try:
        jsonschema.validate(arguments, SCHEMAS[name])
    except jsonschema.ValidationError as e:
        return ToolResult(f"Error calling tool '{short}': Input validation error: {e.message}", True)
    saved = None if name in READ_TOOLS else board.copy_board()
    try:
        value = tools[name](**arguments)
    except (ToolError, BoardError) as e:
        if saved is not None:
            _restore(board, saved)
        message = str(e)
        if isinstance(e, BoardError) and message == NO_ISSUE and name == "jira_transition_issue":
            message = f"Issue {arguments.get('issue_key')} not found. Verify the issue key and project access."
        return ToolResult(f"Error calling tool '{short}': {message}", True)
    return ToolResult(json.dumps(value, ensure_ascii=False, indent=2), False)


def _restore(board: Board, saved: Board) -> None:
    for field in Board.model_fields:
        setattr(board, field, getattr(saved, field))
    board._last_number = saved._last_number


def apply_calls(board: Board, calls: list[dict]) -> list[ToolResult]:
    """Run tool calls ({"name": ..., "arguments": {...}}) on `board` without an MCP client."""
    tools = make_tools(board)
    return [call_tool(board, tools, c["name"], c.get("arguments")) for c in calls]


def build_server(board: Board) -> Server:
    """A low-level MCP server with the exact names, descriptions and schemas of `data/mcp_atlassian_tools.json`."""
    tools = make_tools(board)
    listed = [types.Tool.model_validate(t) for t in TOOL_DEFS]

    async def on_list_tools(ctx, params) -> types.ListToolsResult:
        return types.ListToolsResult(tools=listed)

    async def on_call_tool(ctx, params) -> types.CallToolResult:
        result = call_tool(board, tools, params.name, params.arguments)
        return types.CallToolResult(content=[types.TextContent(type="text", text=result.text)],
                                    is_error=result.is_error)

    return Server(f"environment-{board.name}", on_list_tools=on_list_tools, on_call_tool=on_call_tool)


async def _serve_stdio(board: Board) -> None:
    from mcp.server.stdio import stdio_server

    server = build_server(board)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m src.tools <board.json>")
    asyncio.run(_serve_stdio(load_board(sys.argv[1])))
