"""MCP server that gives the operations of one board to a model as tools."""

import functools
import sys
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from src.environment import Board, BoardError, load_board

MAX_SEARCH_RESULTS = 50

IssueType = Literal["bug", "task", "story"]
Status = Literal["to_do", "in_progress", "done"]
Priority = Literal["low", "medium", "high", "critical"]


def _none(value: str | None) -> str | None:
    return None if value is None or value.lower() == "none" else value


def make_tools(board: Board) -> dict:
    """Return the tool functions for `board`. The functions raise ToolError for an expected error."""

    def tool(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except BoardError as e:
                raise ToolError(str(e)) from e
        return wrapper

    @tool
    def list_users() -> dict:
        """List all persons of the project with their id and display name. Use the id as the assignee."""
        return {"users": [p.model_dump() for p in board.persons]}

    @tool
    def list_sprints() -> dict:
        """List all sprints with their id, name and state (closed, active, future)."""
        return {"sprints": [s.model_dump() for s in board.sprints]}

    @tool
    def search_issues(
        status: Annotated[Status | None, Field(description="Issue status.")] = None,
        assignee: Annotated[str | None, Field(description="Person id, or 'unassigned' for issues without an assignee.")] = None,
        label: Annotated[str | None, Field(description="One label that the issue has.")] = None,
        type: Annotated[IssueType | None, Field(description="Issue type.")] = None,
        priority: Annotated[Priority | None, Field(description="Issue priority.")] = None,
        sprint: Annotated[str | None, Field(description="Sprint id, or 'backlog' for issues without a sprint.")] = None,
        text: Annotated[str | None, Field(description="Text that the title contains.")] = None,
    ) -> dict:
        """Find issues. All filters are optional and all given filters must match. Returns the short form of at most 50 issues and the total number."""
        found = board.search(status=status, assignee=assignee, label=label, type=type,
                             priority=priority, sprint=sprint, text=text)
        return {"total": len(found), "issues": [i.short() for i in found[:MAX_SEARCH_RESULTS]]}

    @tool
    def get_issue(key: Annotated[str, Field(description="Issue key, for example 'WEB-7'.")]) -> dict:
        """Get all fields of one issue, with its comments."""
        return board.issue(key).model_dump()

    @tool
    def create_issue(
        title: Annotated[str, Field(description="Title of the new issue.")],
        type: Annotated[IssueType, Field(description="Issue type.")],
        description: Annotated[str, Field(description="Description.")] = "",
        priority: Annotated[Priority, Field(description="Priority.")] = "medium",
        assignee: Annotated[str | None, Field(description="Person id, or 'none'.")] = None,
        labels: Annotated[list[str] | None, Field(description="Labels.")] = None,
        sprint: Annotated[str | None, Field(description="Sprint id, or 'none' for the backlog.")] = None,
    ) -> dict:
        """Create a new issue with the status to_do. Returns the short form of the new issue with its key."""
        issue = board.create_issue(title=title, type=type, description=description, priority=priority,
                                   assignee=_none(assignee), labels=labels, sprint=_none(sprint))
        return issue.short()

    @tool
    def update_issue(
        key: Annotated[str, Field(description="Issue key, for example 'WEB-7'.")],
        title: Annotated[str | None, Field(description="New title.")] = None,
        description: Annotated[str | None, Field(description="New description.")] = None,
        type: Annotated[IssueType | None, Field(description="New type.")] = None,
        status: Annotated[Status | None, Field(description="New status.")] = None,
        priority: Annotated[Priority | None, Field(description="New priority.")] = None,
        assignee: Annotated[str | None, Field(description="Person id, or 'none' to remove the assignee.")] = None,
        sprint: Annotated[str | None, Field(description="Sprint id, or 'none' to move the issue to the backlog.")] = None,
        add_labels: Annotated[list[str] | None, Field(description="Labels to add.")] = None,
        remove_labels: Annotated[list[str] | None, Field(description="Labels to remove.")] = None,
    ) -> dict:
        """Change one or more fields of an issue. Give only the fields to change. Returns the short form of the issue."""
        fields = {name: value for name, value in (
            ("title", title), ("description", description), ("type", type),
            ("status", status), ("priority", priority),
        ) if value is not None}
        if assignee is not None:
            fields["assignee"] = _none(assignee)
        if sprint is not None:
            fields["sprint"] = _none(sprint)
        return board.update_issue(key, add_labels=add_labels, remove_labels=remove_labels, **fields).short()

    @tool
    def add_comment(
        key: Annotated[str, Field(description="Issue key, for example 'WEB-7'.")],
        text: Annotated[str, Field(description="Comment text.")],
    ) -> dict:
        """Add a comment to an issue."""
        issue = board.add_comment(key, text)
        return {"key": issue.key, "comments": len(issue.comments)}

    return {fn.__name__: fn for fn in (list_users, list_sprints, search_issues, get_issue,
                                        create_issue, update_issue, add_comment)}


def build_server(board: Board) -> MCPServer:
    server = MCPServer(f"environment-{board.name}", log_level="WARNING")
    for fn in make_tools(board).values():
        server.add_tool(fn)
    return server


def apply_calls(board: Board, calls: list[dict]) -> list:
    """Run tool calls ({"name": ..., "arguments": {...}}) on `board` without an MCP client. The task generator uses it."""
    tools = make_tools(board)
    return [tools[c["name"]](**c["arguments"]) for c in calls]


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m src.tools <board.json>")
    build_server(load_board(sys.argv[1])).run("stdio")
