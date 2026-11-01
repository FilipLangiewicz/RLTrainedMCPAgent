from types import SimpleNamespace

import pytest

from src.environment import diff, generate_board
from src.verifier import grade, normalize_text


@pytest.fixture
def board():
    return generate_board("test-x", "WEB", seed=5)


def make_task(board, change, difficulty="easy"):
    after = board.copy_board()
    change(after)
    return SimpleNamespace(difficulty=difficulty, expected=diff(board, after))


def other_person(board, key):
    return next(p.id for p in board.persons if p.id != board.issue(key).assignee)


def assign_three(board):
    keys = ["WEB-1", "WEB-2", "WEB-3"]
    return keys, {k: other_person(board, k) for k in keys}


def test_all_expected_changes(board):
    keys, people = assign_three(board)
    task = make_task(board, lambda b: [b.update_issue(k, assignee=people[k]) for k in keys], "multi_step")
    final = board.copy_board()
    for k in keys:
        final.update_issue(k, assignee=people[k])
    result = grade(task, board, final, "Gotowe.")
    assert result.grade == "correct"
    assert result.reason


def test_other_order(board):
    keys, people = assign_three(board)
    task = make_task(board, lambda b: [b.update_issue(k, assignee=people[k]) for k in keys], "multi_step")
    final = board.copy_board()
    for k in reversed(keys):
        final.update_issue(k, assignee=people[k])
    assert grade(task, board, final, "ok").grade == "correct"


def test_additional_change(board):
    task = make_task(board, lambda b: b.update_issue("WEB-1", assignee=other_person(board, "WEB-1")))
    final = board.copy_board()
    final.update_issue("WEB-1", assignee=other_person(board, "WEB-1"))
    final.update_issue("WEB-9", priority="critical" if board.issue("WEB-9").priority != "critical" else "low")
    result = grade(task, board, final, "ok")
    assert result.grade == "incorrect"
    assert "additional" in result.reason and "WEB-9" in result.reason and "priority" in result.reason


def test_missing_change(board):
    keys, people = assign_three(board)
    task = make_task(board, lambda b: [b.update_issue(k, assignee=people[k]) for k in keys], "multi_step")
    final = board.copy_board()
    for k in keys[:2]:
        final.update_issue(k, assignee=people[k])
    result = grade(task, board, final, "ok")
    assert result.grade == "incorrect"
    assert "missing" in result.reason and "WEB-3" in result.reason


def test_correct_refusal(board):
    task = SimpleNamespace(difficulty="refusal", expected=[])
    result = grade(task, board, board.copy_board(), "ODMOWA: nie mam narzędzia do usunięcia projektu")
    assert result.grade == "correct_refusal"
    assert grade(task, board, board.copy_board(), "  odmowa: nie mogę").grade == "correct_refusal"


def test_refusal_without_marker(board):
    task = SimpleNamespace(difficulty="refusal", expected=[])
    assert grade(task, board, board.copy_board(), "Nie mogę tego zrobić.").grade == "incorrect"


def test_change_instead_of_refusal(board):
    task = SimpleNamespace(difficulty="refusal", expected=[])
    final = board.copy_board()
    final.add_comment("WEB-1", "x")
    assert grade(task, board, final, "ODMOWA: nie").grade == "incorrect"


def test_comment_other_case(board):
    task = make_task(board, lambda b: b.add_comment("WEB-2", "Czekamy na review"))
    final = board.copy_board()
    final.add_comment("WEB-2", "czekamy  na „review”.")
    assert grade(task, board, final, "ok").grade == "correct"


def test_labels_as_sets(board):
    task = make_task(board, lambda b: b.update_issue("WEB-2", add_labels=["zzz", "aaa"]))
    final = board.copy_board()
    final.update_issue("WEB-2", add_labels=["aaa"])
    final.update_issue("WEB-2", add_labels=["zzz"])
    assert grade(task, board, final, "ok").grade == "correct"


def test_new_issue_by_fields(board):
    task = make_task(board, lambda b: b.create_issue("Błąd eksportu", "bug", sprint="s2", assignee="u1"))
    final = board.copy_board()
    final.issues.append(final.issues[0].model_copy(deep=True))  # a key that the expected issue does not have
    final.issues[-1].key = "WEB-500"
    final.issues[-1].title, final.issues[-1].description = "błąd eksportu.", "Opis od agenta"
    final.issues[-1].type, final.issues[-1].status, final.issues[-1].priority = "bug", "to_do", "medium"
    final.issues[-1].assignee, final.issues[-1].sprint, final.issues[-1].labels = "u1", "s2", []
    final.issues[-1].comments = []
    assert grade(task, board, final, "ok").grade == "correct"
    final.issues[-1].sprint = "s3"
    assert grade(task, board, final, "ok").grade == "incorrect"


def test_normalize_text():
    assert normalize_text(' "Czekamy   na Review." ') == "czekamy na review"
