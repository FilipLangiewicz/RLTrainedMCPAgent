from pathlib import Path

import pytest

from src.environment import (
    Board,
    BoardError,
    diff,
    format_time,
    load_board,
    parse_time,
    save_board,
)

ROOT = Path(__file__).resolve().parents[1]
BOARDS = sorted((ROOT / "data" / "environments").glob("test-*.json"))


@pytest.fixture
def web() -> Board:
    return load_board(ROOT / "data" / "environments" / "test-web.json")


def test_five_test_boards():
    assert [p.stem for p in BOARDS] == ["test-api", "test-app", "test-data", "test-ops", "test-web"]


@pytest.mark.parametrize("path", BOARDS, ids=lambda p: p.stem)
def test_board_loads(path):
    board = load_board(path)
    assert board.issues and board.persons and board.sprints
    assert all(p.email.endswith("@example.com") for p in board.persons)
    issue = board.issues[0]
    for field in ("id", "key", "summary", "description", "issue_type", "status", "priority", "assignee",
                  "reporter", "labels", "sprint", "created", "updated", "comments", "worklogs"):
        assert hasattr(issue, field)


def test_save_and_load(web, tmp_path):
    save_board(web, tmp_path / "b.json")
    assert load_board(tmp_path / "b.json") == web


# Allowed values

def test_translated_type(web):
    with pytest.raises(BoardError, match="Specify a valid issue type"):
        web.create_issue("x", "Zadanie")
    assert diff(load_board(ROOT / "data/environments/test-web.json"), web) == []


def test_unknown_priority(web):
    before = web.copy_board()
    with pytest.raises(BoardError, match=r"Specify the Priority \(name\) in the string format"):
        web.update_fields("WEB-7", {"priority": {"name": "Wysoki"}})
    assert web == before


def test_closed_sprint(web):
    closed = next(s for s in web.sprints if s.state == "closed")
    with pytest.raises(BoardError, match="closed"):
        web.add_to_sprint(closed.id, ["WEB-7"])


def test_unknown_sprint(web):
    with pytest.raises(BoardError, match="We could not find the sprint"):
        web.add_to_sprint("999", ["WEB-7"])


def test_unknown_issue(web):
    before = web.copy_board()
    with pytest.raises(BoardError, match="Issue does not exist"):
        web.update_fields("WEB-999", {"summary": "x"})
    assert web == before


# Operations

def test_new_issue(web):
    issue = web.create_issue("Nowy bug", "bug")
    assert issue.key == "WEB-41"
    assert (issue.status, issue.priority, issue.issue_type) == ("Backlog", "Medium", "Bug")
    assert issue.reporter == web.user.account_id
    assert issue.created == web.now


def test_new_issue_unknown_assignee(web):
    issue = web.create_issue("x", "Task", assignee="Ewa")
    assert issue.assignee is None


def test_transition(web):
    web.update_fields("WEB-7", {"status": "In Progress"})
    assert web.transition("WEB-7", "51").status == "Done"
    with pytest.raises(BoardError, match="Transition id '999' is not valid for this issue."):
        web.transition("WEB-7", "999")


def test_labels_replace(web):
    assert web.update_fields("WEB-14", {"labels": ["frontend"]}).labels == ["frontend"]


@pytest.mark.parametrize("text,seconds", [
    ("1h 30m", 5400), ("90m", 5400), ("2h", 7200), ("1d", 28800), ("1w", 144000), ("45M", 2700),
    ("półtorej godziny", 60), ("1,5h", 60), ("", 60),
])
def test_parse_time(text, seconds):
    assert parse_time(text) == seconds


def test_format_time():
    assert format_time(5400) == "1h 30m"
    assert format_time(60) == "1m"


def test_same_calls_give_same_board(web):
    def run(board):
        board.create_issue("x", "Task", assignee="Ewa Mazur")
        board.add_comment("WEB-41", "komentarz")
        board.add_worklog("WEB-5", "1h 30m")
        board.add_to_sprint("43", ["WEB-41"])
        return board

    assert run(web.copy_board()) == run(web.copy_board())


# Persons

def test_person_without_polish_letters():
    board = load_board(ROOT / "data/environments/test-data.json")
    lukasz = next(p for p in board.persons if p.display_name == "Łukasz Ostrowski")
    assert board.find_person("lukasz ostrowski") == lukasz
    assert board.find_person("LUKASZ.OSTROWSKI@example.com") == lukasz


def test_first_name_only(web):
    assert web.find_person("Ewa") is None
    with pytest.raises(BoardError, match="Could not find account ID for user: Ewa"):
        web.update_fields("WEB-7", {"assignee": "Ewa"})


def test_prefix_search(web):
    assert {p.display_name for p in web.search_persons("Ann")} == {"Anna Wróbel", "Anna Sikora"}
    assert [p.display_name for p in web.search_persons("Rud")] == ["Rudolf Igor"]
    assert [p.display_name for p in web.search_persons("wrob")] == ["Anna Wróbel"]


def test_inactive_person(web):
    assert web.search_persons("Paweł") == []
    assert web.find_person("Paweł Jasiński") is None
    with pytest.raises(BoardError, match="Could not find account ID"):
        web.update_fields("WEB-7", {"assignee": "Paweł Jasiński"})


# Difference

def test_no_change(web):
    assert diff(web, web.copy_board()) == []


def test_diff_assignee(web):
    final = web.copy_board()
    final.update_fields("WEB-7", {"assignee": "Ewa Mazur"})
    assert diff(web, final) == [{"issue": "WEB-7", "field": "assignee", "value": "Ewa Mazur"}]


def test_diff_comment(web):
    final = web.copy_board()
    final.add_comment("WEB-6", "Czekamy na review")
    assert diff(web, final) == [{"issue": "WEB-6", "comment": "Czekamy na review"}]


def test_diff_worklog(web):
    final = web.copy_board()
    final.add_worklog("WEB-5", "1h 30m")
    assert diff(web, final) == [{"issue": "WEB-5", "worklog": {"seconds": 5400, "comment": ""}}]


def test_diff_sprint_by_name(web):
    final = web.copy_board()
    final.add_to_sprint("43", ["WEB-10"])
    assert diff(web, final) == [{"issue": "WEB-10", "field": "sprint", "value": "WEB Sprint 16"}]


def test_diff_new_issue_with_comment(web):
    final = web.copy_board()
    final.create_issue("Checklista", "Task", assignee="Anna Wróbel")
    final.add_comment("WEB-41", "Do piątku.")
    assert diff(web, final) == [{"new_issue": {
        "summary": "Checklista", "description": None, "issue_type": "Task", "status": "Backlog",
        "priority": "Medium", "assignee": "Anna Wróbel", "labels": [], "sprint": None, "comments": ["Do piątku."],
    }}]
