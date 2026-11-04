import json
from pathlib import Path

import pytest

from src.environment import STATUSES, load_board
from src.jql import UNBOUNDED, JQLError, Parser, search

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def web():
    return load_board(ROOT / "data" / "environments" / "test-web.json")


def keys(board, jql):
    return [i.key for i in search(board, jql)]


def expect(board, predicate):
    """The keys of the issues that match `predicate`, highest key first."""
    return [i.key for i in sorted(board.issues, key=lambda i: -int(i.key.split("-")[1])) if predicate(i)]


# Parser

def test_parse_tree():
    where, order = Parser('project = WEB AND (status = "In Progress" OR NOT labels in (a, b)) ORDER BY key DESC').parse()
    assert where[0] == "and"
    assert where[1][1][0] == "or"
    assert where[1][1][1][1] == ("not", ("clause", "labels", "in", ("list", [("text", "a"), ("text", "b")])))
    assert order == [("key", True)]


@pytest.mark.parametrize("jql,message", [
    ("project = WEB AND (status = ", "Expecting either a value, list or function before the end of the query."),
    ("project = WEB AND foo = 1", "Field 'foo' does not exist"),
    ("project = WEB AND summary = x", "The operator '=' is not supported by the 'summary' field."),
    ("project = WEB status = Done", "Expecting either 'OR' or 'AND'"),
    ("project = WEB AND sprint in nextSprints()", "Unable to find JQL function"),
])
def test_syntax_errors(web, jql, message):
    with pytest.raises(JQLError, match="^Error in JQL Query: ") as e:
        search(web, jql)
    assert message in str(e.value)


def test_query_without_condition(web):
    with pytest.raises(JQLError) as e:
        search(web, "ORDER BY created DESC")
    assert str(e.value) == UNBOUNDED


# Fields and operators

def test_project(web):
    assert len(keys(web, "project = WEB")) == 40
    assert keys(web, "project = APP") == []
    assert len(keys(web, 'project = "JayWalk - sklep internetowy"')) == 40


def test_key(web):
    assert keys(web, "key = WEB-7") == ["WEB-7"]
    assert keys(web, "issuekey in (WEB-1, web-2)") == ["WEB-2", "WEB-1"]


@pytest.mark.parametrize("field,attr,value", [
    ("status", "status", "Done"), ("type", "issue_type", "Bug"), ("issuetype", "issue_type", "Story"),
    ("priority", "priority", "High"),
])
def test_simple_fields(web, field, attr, value):
    assert keys(web, f'project = WEB AND {field} = "{value.lower()}"') == expect(web, lambda i: getattr(i, attr) == value)
    assert keys(web, f'project = WEB AND {field} != "{value}"') == expect(web, lambda i: getattr(i, attr) != value)


def test_in_and_not_in(web):
    statuses = ("Backlog", "In Progress")
    assert keys(web, 'project = WEB AND status in (Backlog, "In Progress")') == expect(web, lambda i: i.status in statuses)
    assert keys(web, 'project = WEB AND status not in (Backlog, "In Progress")') == expect(
        web, lambda i: i.status not in statuses)


def test_assignee(web):
    ewa = next(p for p in web.persons if p.display_name == "Ewa Mazur")
    want = expect(web, lambda i: i.assignee == ewa.account_id)
    assert want
    assert keys(web, 'project = WEB AND assignee = "Ewa Mazur"') == want
    assert keys(web, "project = WEB AND assignee = ewa.mazur@example.com") == want
    assert keys(web, f'project = WEB AND assignee = "{ewa.account_id}"') == want
    # Jira: "!=" does not find issues without an assignee.
    assert keys(web, 'project = WEB AND assignee != "Ewa Mazur"') == expect(
        web, lambda i: i.assignee and i.assignee != ewa.account_id)


def test_reporter_and_current_user(web):
    me = web.user.account_id
    assert keys(web, "project = WEB AND reporter = currentUser()") == expect(web, lambda i: i.reporter == me)


def test_unassigned(web):
    want = expect(web, lambda i: i.assignee is None)
    assert want
    assert keys(web, "project = WEB AND assignee IS EMPTY") == want
    assert keys(web, "project = WEB AND assignee is null") == want
    assert keys(web, "project = WEB AND assignee IS NOT EMPTY") == expect(web, lambda i: i.assignee is not None)


def test_labels(web):
    assert keys(web, "project = WEB AND labels = frontend AND type = Bug") == expect(
        web, lambda i: "frontend" in i.labels and i.issue_type == "Bug")
    assert keys(web, "project = WEB AND labels is EMPTY") == expect(web, lambda i: not i.labels)


def test_sprint_by_id_and_name(web):
    want = expect(web, lambda i: i.sprint == "43")
    assert keys(web, "project = WEB AND sprint = 43") == want
    assert keys(web, 'project = WEB AND sprint = "WEB Sprint 16"') == want
    assert keys(web, "project = WEB AND sprint is EMPTY") == expect(web, lambda i: i.sprint is None)


def test_logic(web):
    a = set(keys(web, "project = WEB AND type = Bug"))
    b = set(keys(web, "project = WEB AND priority = High"))
    assert set(keys(web, "project = WEB AND (type = Bug OR priority = High)")) == a | b
    assert set(keys(web, "project = WEB AND NOT (type = Bug OR priority = High)")) == set(keys(web, "project = WEB")) - (a | b)
    assert set(keys(web, "project = WEB AND type = Bug AND priority = High")) == a & b


def test_order_by(web):
    assert keys(web, "project = WEB ORDER BY key")[:3] == ["WEB-1", "WEB-2", "WEB-3"]
    by_priority = search(web, "project = WEB ORDER BY priority DESC")
    assert by_priority[0].priority == "Highest" and by_priority[-1].priority in ("Low", "Lowest")
    by_status = search(web, "project = WEB ORDER BY status ASC, key DESC")
    assert by_status[0].status == "Backlog"
    created = [i.created for i in search(web, "project = WEB ORDER BY created ASC")]
    assert created == sorted(created)


# Semantics of the Jira Cloud site

def test_highest_key_first(web):
    assert keys(web, "project = WEB")[:2] == ["WEB-40", "WEB-39"]


def test_open_sprints_only_active(web):
    active = next(s.id for s in web.sprints if s.state == "active")
    assert keys(web, "project = WEB AND sprint in openSprints()") == expect(web, lambda i: i.sprint == active)
    future = {s.id for s in web.sprints if s.state == "future"}
    assert keys(web, "project = WEB AND sprint in futureSprints()") == expect(web, lambda i: i.sprint in future)


def test_whole_words(web):
    found = search(web, 'project = WEB AND summary ~ "dostawy"')
    assert found and all("dostawy" in i.summary.lower().split() for i in found)
    assert keys(web, 'project = WEB AND summary ~ "dostawa"') == expect(
        web, lambda i: "dostawa" in i.summary.lower().replace(",", " ").split())
    assert keys(web, 'project = WEB AND summary ~ "dost*"') == expect(
        web, lambda i: any(w.startswith("dost") for w in i.summary.lower().split()))


def test_text_finds_comments(web):
    issue = next(i for i in web.issues if i.comments)
    word = max(issue.comments[0].body.split(), key=len).strip(".,:;!?")
    assert issue.key in keys(web, f'project = WEB AND text ~ "{word}"')


def test_cancelled_is_not_done(web):
    cancelled = [i.key for i in web.issues if i.status == "Cancelled"]
    assert cancelled
    assert set(cancelled) <= set(keys(web, "project = WEB AND statusCategory != Done"))
    assert STATUSES["Cancelled"][0] == "In Progress"


def test_name_that_does_not_exist(web):
    assert keys(web, 'project = WEB AND status = "W toku"') == []
    assert keys(web, "project = WEB AND labels = nieistniejaca") == []
    assert keys(web, 'project = WEB AND assignee = "Nikt Taki"') == []


def test_reference_queries():
    """Each JQL query of the reference solutions runs on its board without an error."""
    data = ROOT / "data" / "tasks" / "test"
    boards = {e["id"]: e["board"] for e in json.loads((data / "expected.json").read_text(encoding="utf-8"))}
    loaded = {}
    n = 0
    for solution in json.loads((data / "solutions.json").read_text(encoding="utf-8")):
        for call in solution["calls"]:
            if call["name"] == "jira_search":
                name = boards[solution["id"]]
                board = loaded.setdefault(name, load_board(ROOT / "data" / "environments" / f"{name}.json"))
                search(board, call["arguments"]["jql"])
                n += 1
    assert n >= 80
