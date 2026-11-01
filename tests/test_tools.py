import asyncio
import json
import sys
from pathlib import Path

import mcp
import pytest
from mcp import StdioServerParameters

from src.environment import generate_board, save_board
from src.tools import build_server

ROOT = Path(__file__).resolve().parents[1]
TOOL_NAMES = {"list_users", "list_sprints", "search_issues", "get_issue", "create_issue", "update_issue", "add_comment"}


@pytest.fixture
def board():
    return generate_board("test-x", "WEB", seed=3)


def call(server, name, args=None):
    async def go():
        async with mcp.Client(server) as client:
            return await client.call_tool(name, args or {})
    return asyncio.run(go())


def data(result):
    assert not result.is_error, result.content[0].text
    return json.loads(result.content[0].text)


def test_list_tools(board):
    async def go():
        async with mcp.Client(build_server(board)) as client:
            return (await client.list_tools()).tools
    tools = asyncio.run(go())
    assert {t.name for t in tools} == TOOL_NAMES
    for t in tools:
        assert t.description
        assert t.input_schema["type"] == "object"


def test_read_tools(board):
    server = build_server(board)
    assert data(call(server, "list_users"))["users"][0] == {"id": "u1", "name": board.persons[0].name}
    assert [s["state"] for s in data(call(server, "list_sprints"))["sprints"]] == ["closed", "active", "future", "future"]
    found = data(call(server, "search_issues"))
    assert found["total"] == len(board.issues)
    assert set(found["issues"][0]) == {"key", "title", "type", "status", "priority", "assignee", "labels", "sprint"}
    board.add_comment("WEB-7", "Test")
    issue = data(call(server, "get_issue", {"key": "WEB-7"}))
    assert issue["key"] == "WEB-7" and issue["comments"][-1] == {"text": "Test"}
    assert "description" in issue


def test_search_filters(board):
    found = data(call(build_server(board), "search_issues", {"type": "bug", "assignee": "unassigned"}))
    assert {i["key"] for i in found["issues"]} == {i.key for i in board.search(type="bug", assignee="unassigned")}


def test_create_issue(board):
    n = len(board.issues)
    result = data(call(build_server(board), "create_issue",
                       {"title": "Nowy bug", "type": "bug", "assignee": "u2", "sprint": "s2", "labels": ["ui"]}))
    assert result["key"] == f"WEB-{n + 1}"
    assert board.issue(result["key"]).sprint == "s2"


def test_update_two_fields(board):
    result = data(call(build_server(board), "update_issue", {"key": "WEB-3", "status": "in_progress", "assignee": "u2"}))
    assert result["status"] == "in_progress" and result["assignee"] == "u2"
    assert board.issue("WEB-3").status == "in_progress"


def test_move_to_backlog_and_clear_assignee(board):
    board.issue("WEB-3").sprint = "s2"
    data(call(build_server(board), "update_issue", {"key": "WEB-3", "sprint": "none", "assignee": "none"}))
    assert board.issue("WEB-3").sprint is None
    assert board.issue("WEB-3").assignee is None


def test_add_comment(board):
    data(call(build_server(board), "add_comment", {"key": "WEB-4", "text": "Czekamy na review"}))
    assert board.issue("WEB-4").comments[-1].text == "Czekamy na review"


def test_unknown_key_then_normal_call(board):
    server = build_server(board)

    async def go():
        async with mcp.Client(server) as client:
            bad = await client.call_tool("get_issue", {"key": "WEB-999"})
            good = await client.call_tool("get_issue", {"key": "WEB-1"})
            return bad, good
    bad, good = asyncio.run(go())
    assert bad.is_error and "WEB-999" in bad.content[0].text
    assert not good.is_error


@pytest.mark.parametrize("args", [
    {"key": "WEB-1", "status": "closed"},
    {"key": "WEB-1", "assignee": "u99"},
    {"key": "WEB-1", "sprint": "s1"},
    {"key": "WEB-1"},
    {"status": "done"},
])
def test_update_errors(board, args):
    before = board.copy_board()
    result = call(build_server(board), "update_issue", args)
    assert result.is_error
    assert result.content[0].text.startswith("Error executing tool update_issue")
    assert board == before


def test_error_message_tells_cause(board):
    result = call(build_server(board), "update_issue", {"key": "WEB-1", "assignee": "u99"})
    assert "u99" in result.content[0].text


def test_separate_boards():
    a, b = generate_board("a", "WEB", seed=1), generate_board("a", "WEB", seed=1)
    call(build_server(a), "update_issue", {"key": "WEB-1", "priority": "critical", "title": "Zmiana"})
    assert a.issue("WEB-1").title == "Zmiana"
    assert b.issue("WEB-1").title != "Zmiana"


def test_stdio_server(board, tmp_path):
    path = tmp_path / "board.json"
    save_board(board, path)
    params = StdioServerParameters(command=sys.executable, args=["-m", "src.tools", str(path)], cwd=str(ROOT))

    async def go():
        async with mcp.Client(params) as client:
            return (await client.list_tools()).tools
    assert {t.name for t in asyncio.run(go())} == TOOL_NAMES
