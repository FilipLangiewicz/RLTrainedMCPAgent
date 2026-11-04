import asyncio
import json
from pathlib import Path

import mcp
import pytest

from src.environment import Board, load_board
from src.tools import TOOL_DEFS, apply_calls, build_server, make_tools

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def web() -> Board:
    return load_board(ROOT / "data" / "environments" / "test-web.json")


def call(board, name, **arguments):
    result = apply_calls(board, [{"name": name, "arguments": arguments}])[0]
    return result.is_error, (result.text if result.is_error else json.loads(result.text))


def ok(board, name, **arguments):
    is_error, value = call(board, name, **arguments)
    assert not is_error, value
    return value


def error(board, name, **arguments):
    before = board.copy_board()
    is_error, text = call(board, name, **arguments)
    assert is_error, text
    assert board == before
    return text


# Server

def test_tool_list(web):
    async def go():
        async with mcp.Client(build_server(web)) as client:
            return (await client.list_tools()).tools

    tools = asyncio.run(go())
    assert len(tools) == 14
    for tool, want in zip(tools, TOOL_DEFS, strict=True):
        assert tool.name == want["name"]
        assert tool.description == want["description"]
        assert tool.input_schema == want["inputSchema"]


def test_call_through_client(web):
    async def go():
        async with mcp.Client(build_server(web)) as client:
            bad = await client.call_tool("jira_get_issue", {"issue_key": "WEB-999"})
            good = await client.call_tool("jira_get_issue", {"issue_key": "WEB-6"})
            return bad, good

    bad, good = asyncio.run(go())
    assert bad.is_error
    assert bad.content[0].text == "Error calling tool 'get_issue': Issue WEB-999 not found. Verify the issue key and project access."
    assert not good.is_error
    assert json.loads(good.content[0].text)["key"] == "WEB-6"


def test_argument_errors(web):
    assert "is a required property" in error(web, "jira_get_issue")
    assert "Additional properties are not allowed" in error(web, "jira_get_issue", issue_key="WEB-6", foo=1)
    assert "is not of type 'string'" in error(web, "jira_update_issue", issue_key="WEB-7", fields={"summary": "x"})
    is_error, _ = call(web, "jira_search", jql="project = WEB", limit="5", fields=None)
    assert not is_error


# Read tools

def test_search(web):
    result = ok(web, "jira_search", jql="project = WEB", limit=10)
    assert list(result) == ["total", "start_at", "max_results", "issues"]
    assert result["total"] == -1
    assert len(result["issues"]) == 10
    issue = result["issues"][0]
    assert issue["key"] == "WEB-40"
    assert list(issue)[:4] == ["id", "key", "summary", "browse_url"]
    assert {"status", "issue_type", "priority", "assignee", "reporter", "created", "updated"} <= set(issue)
    assert issue["status"]["category"] and issue["status"]["color"]


def test_search_fields_and_pages(web):
    result = ok(web, "jira_search", jql="project = WEB", fields="summary,status", limit=5, start_at=5)
    assert [i["key"] for i in result["issues"]] == ["WEB-35", "WEB-34", "WEB-33", "WEB-32", "WEB-31"]
    assert set(result["issues"][0]) == {"id", "key", "summary", "browse_url", "status"}
    assert ok(web, "jira_search", jql="project = WEB", limit=100)["max_results"] == 50


def test_search_error(web):
    text = error(web, "jira_search", jql="ORDER BY created DESC")
    assert text == ("Error calling tool 'search': Unbounded JQL queries are not allowed here. "
                    "Please add a search restriction to your query.")


def test_get_issue(web):
    unassigned = next(i for i in web.issues if i.assignee is None and i.comments)
    result = ok(web, "jira_get_issue", issue_key=unassigned.key, comment_limit=5)
    assert result["assignee"] == {"display_name": "Unassigned"}
    assert result["comments"][0]["body"] == unassigned.comments[0].body
    assert set(result["comments"][0]) == {"id", "body", "author", "created", "updated"}
    assert "comments" not in ok(web, "jira_get_issue", issue_key=unassigned.key, comment_limit=0)
    assert set(ok(web, "jira_get_issue", issue_key="WEB-5", fields="labels")) - {"comments"} == {"id", "key", "labels"}


def test_assignable_users(web):
    result = ok(web, "jira_search_assignable_users", query="Ann", project_key="WEB")
    assert result["success"] is True and result["count"] == 2
    assert {u["display_name"] for u in result["users"]} == {"Anna Wróbel", "Anna Sikora"}
    assert set(result["users"][0]) == {"account_id", "display_name", "name", "email", "avatar_url"}
    assert ok(web, "jira_search_assignable_users", query="Paweł", project_key="WEB")["count"] == 0


def test_boards_and_sprints(web):
    assert ok(web, "jira_get_agile_boards", project_key="WEB") == [{"id": "11", "name": "WEB board", "type": "scrum"}]
    assert ok(web, "jira_get_agile_boards", project_key="APP") == []
    sprints = ok(web, "jira_get_sprints_from_board", board_id="11")
    assert [s["state"] for s in sprints] == ["closed", "active", "future", "future"]
    assert "goal" not in sprints[3] and "start_date" not in sprints[3]
    assert [s["id"] for s in ok(web, "jira_get_sprints_from_board", board_id="11", state="future")] == ["43", "44"]


def test_transitions(web):
    result = ok(web, "jira_get_transitions", issue_key="WEB-1")
    assert result == [{"id": 11, "name": "Backlog"}, {"id": 21, "name": "In Progress"}, {"id": 31, "name": "In review"},
                      {"id": 41, "name": "Cancelled"}, {"id": 51, "name": "Done"}]


def test_worklogs(web):
    result = ok(web, "jira_get_worklog", issue_key="WEB-1")
    assert result["worklogs"][0]["time_spent_seconds"] == 21600
    assert result["worklogs"][0]["time_spent"] == "6h"
    assert set(result["worklogs"][0]) == {"id", "comment", "created", "updated", "started", "time_spent",
                                          "time_spent_seconds", "author"}


def test_read_tools_do_not_change_board(web):
    before = web.copy_board()
    for name in ("jira_get_issue", "jira_get_transitions", "jira_get_worklog"):
        ok(web, name, issue_key="WEB-6")
    ok(web, "jira_search", jql="project = WEB")
    assert web == before


# Write tools

def test_two_fields(web):
    result = ok(web, "jira_update_issue", issue_key="WEB-7",
                fields='{"assignee": "Ewa Mazur", "priority": {"name": "Highest"}}')
    assert result["message"] == "Issue updated successfully"
    issue = web.find_issue("WEB-7")
    assert web.display_name(issue.assignee) == "Ewa Mazur" and issue.priority == "Highest"
    assert list(result["issue"])[:4] == ["id", "key", "summary", "url"]


def test_update_return_fields(web):
    result = ok(web, "jira_update_issue", issue_key="WEB-7", fields='{"labels": ["frontend"]}', return_fields="key,labels")
    assert result["issue"] == {"id": web.find_issue("WEB-7").id, "key": "WEB-7", "labels": ["frontend"]}


def test_labels_replace(web):
    assert "ui" in web.find_issue("WEB-14").labels
    ok(web, "jira_update_issue", issue_key="WEB-14", fields='{"labels": ["frontend"]}')
    assert web.find_issue("WEB-14").labels == ["frontend"]


def test_update_errors(web):
    prefix = "Error calling tool 'update_issue': Failed to update issue WEB-7: Failed to update issue WEB-7: "
    assert error(web, "jira_update_issue", issue_key="WEB-7", fields='{"priority": {"name": "Wysoki"}}') == (
        prefix + "Specify the Priority (name) in the string format")
    assert error(web, "jira_update_issue", issue_key="WEB-7", fields='{"assignee": "Ewa"}') == (
        prefix + "Could not update assignee: Could not find account ID for user: Ewa")
    # The valid priority in the same call does not change the board.
    error(web, "jira_update_issue", issue_key="WEB-7", fields='{"priority": {"name": "Low"}, "assignee": "Ewa"}')
    assert "Issue does not exist" in error(web, "jira_update_issue", issue_key="WEB-999", fields='{"summary": "x"}')
    assert "Invalid JSON" in error(web, "jira_update_issue", issue_key="WEB-7", fields="{assignee: Ewa}")


def test_assignee_without_polish_letters():
    board = load_board(ROOT / "data" / "environments" / "test-data.json")
    key = board.issues[0].key
    ok(board, "jira_update_issue", issue_key=key, fields='{"assignee": "lukasz ostrowski"}')
    assert board.display_name(board.find_issue(key).assignee) == "Łukasz Ostrowski"


def test_create_issue(web):
    result = ok(web, "jira_create_issue", project_key="WEB", summary="Nowy bug", issue_type="Bug",
                additional_fields='{"priority": {"name": "High"}, "labels": ["frontend"]}')
    assert result["message"] == "Issue created successfully"
    assert result["issue"]["key"] == "WEB-41"
    issue = web.find_issue("WEB-41")
    assert (issue.priority, issue.labels, issue.status) == ("High", ["frontend"], "Backlog")


def test_create_hidden_error(web):
    result = ok(web, "jira_create_issue", project_key="WEB", summary="x", issue_type="Task", assignee="Ewa")
    assert result["message"] == "Issue created successfully"
    assert result["issue"]["assignee"] == {"display_name": "Unassigned"}


def test_create_errors(web):
    assert error(web, "jira_create_issue", project_key="WEB", summary="x", issue_type="Zadanie") == (
        "Error calling tool 'create_issue': Specify a valid issue type")


def test_transition(web):
    result = ok(web, "jira_transition_issue", issue_key="WEB-32", transition_id="51")
    assert result["message"] == "Issue WEB-32 transitioned successfully"
    assert result["issue"]["status"]["name"] == "Done"
    assert ok(web, "jira_transition_issue", issue_key="WEB-32", transition_id=21)["issue"]["status"]["name"] == "In Progress"
    assert error(web, "jira_transition_issue", issue_key="WEB-32", transition_id="999") == (
        "Error calling tool 'transition_issue': Transition id '999' is not valid for this issue.")


def test_comment(web):
    result = ok(web, "jira_add_comment", issue_key="WEB-6", body="Czekamy na review")
    assert set(result) == {"id", "body", "created", "author"}
    assert result["author"] == web.user.display_name
    assert web.find_issue("WEB-6").comments[-1].body == "Czekamy na review"
    assert error(web, "jira_add_comment", issue_key="WEB-999", body="x") == (
        "Error calling tool 'add_comment': Error adding comment: Issue does not exist or you do not have permission to see it.")


def test_worklog(web):
    result = ok(web, "jira_add_worklog", issue_key="WEB-12", time_spent="1h 30m", comment="analiza")
    assert result["message"] == "Worklog added successfully"
    assert (result["worklog"]["time_spent"], result["worklog"]["time_spent_seconds"]) == ("1h 30m", 5400)


def test_worklog_hidden_error(web):
    result = ok(web, "jira_add_worklog", issue_key="WEB-12", time_spent="półtorej godziny")
    assert result["message"] == "Worklog added successfully"
    assert result["worklog"]["time_spent_seconds"] == 60


def test_sprint_and_backlog(web):
    result = ok(web, "jira_add_issues_to_sprint", sprint_id="42", issue_keys="WEB-1, WEB-2")
    assert result == {"message": "Successfully added 2 issue(s) to sprint", "sprint_id": "42", "issue_keys": ["WEB-1", "WEB-2"]}
    assert web.find_issue("WEB-1").sprint == web.find_issue("WEB-2").sprint == "42"
    result = ok(web, "jira_move_issues_to_backlog", issue_keys="WEB-14")
    assert result == {"message": "Successfully moved 1 issue(s) to backlog", "issue_keys": ["WEB-14"]}
    assert web.find_issue("WEB-14").sprint is None
    assert error(web, "jira_add_issues_to_sprint", sprint_id="999", issue_keys="WEB-1") == (
        "Error calling tool 'add_issues_to_sprint': We could not find the sprint")
    error(web, "jira_add_issues_to_sprint", sprint_id="43", issue_keys="WEB-1,WEB-999")


def test_error_does_not_stop_the_next_call(web):
    results = apply_calls(web, [
        {"name": "jira_get_issue", "arguments": {"issue_key": "WEB-999"}},
        {"name": "jira_get_issue", "arguments": {"issue_key": "WEB-6"}},
        {"name": "jira_unknown", "arguments": {}},
    ])
    assert [r.is_error for r in results] == [True, False, True]


def test_all_tools_exist(web):
    assert sorted(make_tools(web)) == sorted(t["name"] for t in TOOL_DEFS)


# Contract test (D11): the recorded calls of real Jira on a board with the content of the site.

RECORDING = json.loads((ROOT / "data" / "jira_recorded_results.json").read_text(encoding="utf-8"))
IGNORED_KEYS = {"id", "created", "updated", "started", "url", "browse_url", "avatar_url", "start_date", "end_date",
                "email", "account_id"}
# Keys whose texts real Jira changes from Markdown to the Jira format. The simulator stores the text as it is.
TEXT_KEYS = {"body", "description"}
# Recorded calls with a known difference: (index, path of the value or None for the full result, reason).
EXCEPTIONS = {
    (0, "priority"): "The issues SCRUM-1 to SCRUM-4 have no priority on the site; each issue of the simulator has one.",
    (2, "priority"): "The issues SCRUM-1 to SCRUM-4 have no priority on the site; each issue of the simulator has one.",
    (15, None): "The project SCRUM has no type Bug; the test boards have it, so the simulator accepts it.",
    (23, "customfield_*"): "Real Jira adds the custom fields of the site to the full issue; the simulator has none.",
}


def scrum_board() -> Board:
    def person(name, email=""):
        return {"account_id": f"712020:{name}", "display_name": name, "email": email, "active": True}

    def issue(n, summary, status, sprint, issue_type="Task"):
        return {"id": str(9999 + n), "key": f"SCRUM-{n}", "summary": summary, "description": None,
                "issue_type": issue_type, "status": status, "priority": "Medium", "assignee": None,
                "reporter": "712020:Kombajn", "labels": [], "sprint": sprint, "created": "2026-11-02T23:55:34.000+0100",
                "updated": "2026-11-02T23:55:36.000+0100", "comments": [], "worklogs": []}

    invited = ["anna.kowalczyk", "katarzyna.wisniewska", "piotr.nowak", "tomasz.zielinski", "james.miller", "laura.schmidt"]
    board = Board.model_validate({
        "name": "scrum", "site": "https://example.atlassian.net", "now": "2026-11-03T21:14:28.000+0100",
        "project": {"key": "SCRUM", "name": "CombAIns Team"},
        "board": {"id": "1", "name": "SCRUM board", "type": "simple"},
        "persons": [person("CombAIns Assistant", "assistant@example.com"), person("Kombajn")]
                   + [person(f"user+{n}") for n in invited],
        "sprints": [
            {"id": "2", "name": "SCRUM Sprint 0", "state": "active", "start_date": "2026-11-02T22:55:36.361Z",
             "end_date": "2026-11-16T22:55:36.361Z", "goal": ""},
            {"id": "1", "name": "SCRUM Sprint 1", "state": "future", "start_date": None, "end_date": None, "goal": ""},
        ],
        "issues": [issue(1, "Zadanie 1", "Backlog", "2"), issue(2, "Zadanie 2", "In Progress", "2"),
                   issue(3, "Zadanie 3", "In Progress", None), issue(4, "Zadania podrzędne 2.1", "Backlog", None)],
    })
    board._last_number = 9  # The site made SCRUM-5 to SCRUM-9 before the recording and deleted them.
    return board


def _excepted(index: int, path: str) -> bool:
    name = path.rsplit(".", 1)[-1]
    return any(i == index and p is not None and (p == name or (p.endswith("*") and name.startswith(p[:-1])))
               for i, p in EXCEPTIONS)


def compare(index: int, want, got, path: str = "") -> list[str]:
    """The differences in the key structure and in the values, without the ignored keys."""
    if isinstance(want, dict) and isinstance(got, dict):
        problems = []
        for key in sorted(set(want) | set(got)):
            sub = f"{path}.{key}" if path else key
            if _excepted(index, sub):
                continue
            if key not in got or key not in want:
                problems.append(f"{sub}: only in {'recording' if key in want else 'simulator'}")
            elif key not in IGNORED_KEYS and key not in TEXT_KEYS:
                problems += compare(index, want[key], got[key], sub)
        return problems
    if isinstance(want, list) and isinstance(got, list):
        if len(want) != len(got):
            return [f"{path}: {len(want)} items in the recording, {len(got)} in the simulator"]
        return [p for k, (w, g) in enumerate(zip(want, got)) for p in compare(index, w, g, f"{path}[{k}]")]
    return [] if want == got else [f"{path}: recording {want!r}, simulator {got!r}"]


def test_contract():
    board = scrum_board()
    tools = make_tools(board)
    assert tools
    problems = []
    for index, rec in enumerate(RECORDING["calls"]):
        result = apply_calls(board, [{"name": rec["tool"], "arguments": rec["args"]}])[0]
        if (index, None) in EXCEPTIONS:
            continue
        if result.is_error != rec["is_error"]:
            problems.append(f"call {index} {rec['tool']}: error flag {result.is_error}, recorded {rec['is_error']}: {result.text}")
        elif rec["is_error"]:
            if result.text != rec["text"]:
                problems.append(f"call {index} {rec['tool']}: message {result.text!r}, recorded {rec['text']!r}")
        else:
            problems += [f"call {index} {rec['tool']}: {p}"
                         for p in compare(index, json.loads(rec["text"]), json.loads(result.text))]
    assert problems == []


def test_contract_exceptions_have_reasons():
    assert all(reason.strip() for reason in EXCEPTIONS.values())


def test_contract_transition_error():
    board = scrum_board()
    rec = next(c for c in RECORDING["calls"] if c["tool"] == "jira_transition_issue" and c["is_error"])
    board.create_issue("x", "Task")
    result = apply_calls(board, [{"name": rec["tool"], "arguments": rec["args"]}])[0]
    assert result.is_error and result.text == rec["text"]
