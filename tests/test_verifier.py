from pathlib import Path

import pytest

from src.environment import load_board
from src.tasks import Task, board_path, load_tasks
from src.verifier import (
    check_answer,
    find_times,
    grade,
    is_refusal,
    match_changes,
    normalize_text,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def web():
    return load_board(ROOT / "data" / "environments" / "test-web.json")


def task(category="update", changes=None, answer=None):
    difficulty = {"refusal": "refusal", "bulk": "multi_step", "workflow": "multi_step"}.get(category, "easy")
    return Task(id="t", author="a", instruction="i", calls=[], reference_answer="", board="test-web",
                category=category, difficulty=difficulty, changes=changes, expected_answer=answer,
                refusal_kind="no_tool" if category == "refusal" else None)


def assignee(key, name):
    return {"issue": key, "field": "assignee", "value": name}


# Normal tasks

def test_all_expected_changes(web):
    final = web.copy_board()
    final.update_fields("WEB-7", {"assignee": "Ewa Mazur"})
    g = grade(task(changes=[assignee("WEB-7", "Ewa Mazur")]), web, final, "OK")
    assert g.grade == "correct"


def test_additional_change(web):
    final = web.copy_board()
    final.update_fields("WEB-7", {"assignee": "Ewa Mazur"})
    final.update_fields("WEB-8", {"priority": "Lowest"})
    g = grade(task(changes=[assignee("WEB-7", "Ewa Mazur")]), web, final, "OK")
    assert g.grade == "incorrect"
    assert "additional" in g.reason and "WEB-8" in g.reason and "Lowest" in g.reason


def test_missing_change(web):
    final = web.copy_board()
    final.update_fields("WEB-7", {"assignee": "Ewa Mazur"})
    final.update_fields("WEB-8", {"assignee": "Ewa Mazur"})
    expected = [assignee(k, "Ewa Mazur") for k in ("WEB-7", "WEB-8", "WEB-9")]
    g = grade(task(category="bulk", changes=expected), web, final, "OK")
    assert g.grade == "incorrect"
    assert g.reason.startswith("missing") and "WEB-9" in g.reason and "additional" not in g.reason


def test_no_change(web):
    g = grade(task(changes=[assignee("WEB-7", "Ewa Mazur")]), web, web.copy_board(), "OK")
    assert g.grade == "incorrect"


def test_hidden_error_of_create(web):
    final = web.copy_board()
    final.create_issue("Checklista", "Task", assignee="Ewa")
    expected = [{"new_issue": {"summary": "Checklista", "issue_type": "Task", "priority": "Medium",
                               "assignee": "Ewa Mazur", "labels": [], "sprint": None}}]
    g = grade(task(category="create", changes=expected), web, final, "OK")
    assert g.grade == "incorrect"
    assert '"assignee": "Ewa Mazur"' in g.reason and '"assignee": null' in g.reason


def test_new_issue_by_fields(web):
    final = web.copy_board()
    final.create_issue("Kalkulator rat pokazuje złą kwotę.", "Bug", priority={"name": "High"})
    expected = [{"new_issue": {"summary": "kalkulator rat pokazuje złą kwotę", "issue_type": "Bug", "priority": "High",
                               "assignee": None, "labels": [], "sprint": None}}]
    assert grade(task(category="create", changes=expected), web, final, "OK").grade == "correct"


def test_new_issue_with_comments(web):
    expected = [{"new_issue": {"summary": "Checklista", "issue_type": "Task", "comments": ["Do piątku."]}}]
    final = web.copy_board()
    final.create_issue("Checklista", "Task")
    assert grade(task(category="create", changes=expected), web, final, "OK").grade == "incorrect"
    final.add_comment("WEB-41", "do piątku")
    assert grade(task(category="create", changes=expected), web, final, "OK").grade == "correct"


# Comparison of values

def test_comment_with_other_case(web):
    final = web.copy_board()
    final.add_comment("WEB-6", "czekamy na **review**.")
    g = grade(task(category="log", changes=[{"issue": "WEB-6", "comment": "Czekamy na review"}]), web, final, "OK")
    assert g.grade == "correct"


def test_worklog_other_format(web):
    final = web.copy_board()
    final.add_worklog("WEB-12", "90m", "analiza")
    expected = [{"issue": "WEB-12", "worklog": {"seconds": 5400, "comment": "Analiza."}}]
    assert grade(task(category="log", changes=expected), web, final, "OK").grade == "correct"
    expected = [{"issue": "WEB-12", "worklog": {"seconds": 5400, "comment": "inny opis"}}]
    assert grade(task(category="log", changes=expected), web, final, "OK").grade == "incorrect"


def test_worklog_without_expected_comment(web):
    final = web.copy_board()
    final.add_worklog("WEB-12", "1h 30m", "jakiś opis")
    expected = [{"issue": "WEB-12", "worklog": {"seconds": 5400, "comment": None}}]
    assert grade(task(category="log", changes=expected), web, final, "OK").grade == "correct"


def test_labels_as_set(web):
    final = web.copy_board()
    final.update_fields("WEB-14", {"labels": ["b", "a"]})
    expected = [{"issue": "WEB-14", "field": "labels", "value": ["a", "b"]}]
    assert grade(task(changes=expected), web, final, "OK").grade == "correct"


def test_matching_prefers_specific_worklog():
    expected = [{"issue": "X-1", "worklog": {"seconds": 60, "comment": None}},
                {"issue": "X-1", "worklog": {"seconds": 60, "comment": "a"}}]
    actual = [{"issue": "X-1", "worklog": {"seconds": 60, "comment": "a"}},
              {"issue": "X-1", "worklog": {"seconds": 60, "comment": "b"}}]
    assert match_changes(expected, actual) == ([], [])


def test_normalize_text():
    assert normalize_text('  „Czekamy"  na   **review**. ') == "czekamy na review"


# Refusals

def test_refusal(web):
    assert grade(task(category="refusal"), web, web.copy_board(), "ODMOWA: nie mam takiego narzędzia.").grade == "correct_refusal"
    assert grade(task(category="refusal"), web, web.copy_board(), "**Odmowa:** nie mogę.").grade == "correct_refusal"
    assert grade(task(category="refusal"), web, web.copy_board(), "Nie mogę tego zrobić.").grade == "incorrect"
    final = web.copy_board()
    final.add_comment("WEB-6", "x")
    g = grade(task(category="refusal"), web, final, "ODMOWA: nie.")
    assert g.grade == "incorrect" and "changed" in g.reason


def test_is_refusal():
    assert is_refusal(" odmowa: x")
    assert not is_refusal("Wykonano. ODMOWA: x")


# Query tasks

def query(kind, value):
    return task(category="query", answer={"type": kind, "value": value})


def test_correct_number(web):
    assert grade(query("number", 3), web, web.copy_board(), "W backlogu są 3 takie bugi.").grade == "correct"
    assert grade(query("number", 3), web, web.copy_board(), "Są takie bugi: WEB-3 i WEB-13.").grade == "incorrect"


def test_change_in_query_task(web):
    final = web.copy_board()
    final.add_comment("WEB-6", "x")
    assert grade(query("number", 3), web, final, "Są 3.").grade == "incorrect"


def test_refusal_in_query_task(web):
    assert grade(query("number", 3), web, web.copy_board(), "ODMOWA: 3").grade == "incorrect"


def test_additional_key(web):
    g = grade(query("keys", ["WEB-5", "WEB-6"]), web, web.copy_board(), "WEB-5, WEB-6 i WEB-35.")
    assert g.grade == "incorrect" and "WEB-35" in g.reason
    assert grade(query("keys", ["WEB-5", "WEB-6"]), web, web.copy_board(), "web-6 oraz WEB-5").grade == "correct"


@pytest.mark.parametrize("answer,seconds", [
    ("Razem 7,5 h", 27000), ("7h 30m", 27000), ("7 h 30 min", 27000), ("450 minut", 27000),
    ("8 godzin", 28800), ("Zalogowano 1,5 godziny", 5400), ("7 godzin i 30 minut", 27000), ("30m", 1800),
])
def test_time(web, answer, seconds):
    assert seconds in find_times(answer)
    assert grade(query("time", seconds), web, web.copy_board(), answer).grade == "correct"


def test_wrong_time(web):
    assert grade(query("time", 27000), web, web.copy_board(), "Razem 7 h").grade == "incorrect"
    assert find_times("WEB-12 ma 2h") == [7200]


def test_person(web):
    assert check_answer({"type": "person", "value": "Ewa Mazur"}, "WEB-6 ma Ewa Mazur.", web)[0]
    assert check_answer({"type": "person", "value": "Ewa Mazur"}, "WEB-6 jest przypisane do Ewy Mazur.", web)[0]
    assert check_answer({"type": "person", "value": "Ewa Mazur"}, "Zajmuje się tym ewa.", web)[0]
    assert check_answer({"type": "person", "value": "Michał Krawczyk"}, "Daj to Michałowi Krawczykowi", web)[0]
    assert not check_answer({"type": "person", "value": "Ewa Mazur"}, "Zajmuje się tym Daniel Brooks.", web)[0]


def test_person_with_shared_first_name(web):
    g = grade(query("person", "Anna Sikora"), web, web.copy_board(), "Zajmuje się tym Anna")
    assert g.grade == "incorrect" and "Anna Wróbel" in g.reason
    assert grade(query("person", "Anna Sikora"), web, web.copy_board(), "Zajmuje się tym Anna Sikora").grade == "correct"


def test_value(web):
    assert grade(query("value", "In review"), web, web.copy_board(), "Status: in review.").grade == "correct"
    assert grade(query("value", "High"), web, web.copy_board(), "Priorytet Medium.").grade == "incorrect"


def test_reference_answers_of_query_tasks():
    tasks = [t for t in load_tasks("test") if t.category == "query"]
    assert len(tasks) == 30
    boards = {}
    for t in tasks:
        board = boards.setdefault(t.board, load_board(board_path(t.board)))
        g = grade(t, board, board.copy_board(), t.reference_answer)
        assert g.grade == "correct", (t.id, t.reference_answer, g.reason)
