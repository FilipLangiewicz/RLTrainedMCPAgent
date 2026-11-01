import pytest

from src.environment import (
    FIRST_NAMES,
    SURNAMES,
    Board,
    BoardError,
    Issue,
    diff,
    generate_board,
    load_board,
    name_forms,
    save_board,
)


@pytest.fixture
def board() -> Board:
    return generate_board("test-x", "WEB", seed=1)


def test_round_trip(board, tmp_path):
    path = tmp_path / "board.json"
    save_board(board, path)
    assert load_board(path) == board


def test_issue_fields(board):
    issue = board.issues[0]
    assert set(Issue.model_fields) == {
        "key", "title", "description", "type", "status", "priority", "assignee", "labels", "sprint", "comments"
    }
    assert issue.key.startswith("WEB-")


def test_board_size(board):
    assert len(board.persons) == 6
    assert [s.state for s in board.sprints] == ["closed", "active", "future", "future"]
    assert 30 <= len(board.issues) <= 40


def test_same_seed_same_board():
    assert generate_board("b", "WEB", seed=7) == generate_board("b", "WEB", seed=7)
    assert generate_board("b", "WEB", seed=7) != generate_board("b", "WEB", seed=8)


@pytest.mark.parametrize("seed", range(20))
def test_unique_first_names(seed):
    board = generate_board("b", "WEB", seed=seed)
    firsts = [p.name.split()[0] for p in board.persons]
    assert len(set(firsts)) == len(firsts)


def test_names_from_fixed_list(board):
    surnames = {s for pair in SURNAMES for s in pair}
    for p in board.persons:
        first, last = p.name.split()
        assert first in FIRST_NAMES and last in surnames
        assert set(name_forms(p)) == {"gender", "nom", "gen", "dat", "acc", "ins"}


def test_value_not_allowed(board):
    before = board.copy_board()
    with pytest.raises(BoardError, match="to_do, in_progress, done"):
        board.update_issue("WEB-1", status="closed")
    assert board == before


def test_unknown_person(board):
    before = board.copy_board()
    with pytest.raises(BoardError, match="u99"):
        board.update_issue("WEB-1", assignee="u99", status="done")
    assert board == before


def test_closed_sprint(board):
    with pytest.raises(BoardError, match="closed"):
        board.update_issue("WEB-1", sprint="s1")


def test_unknown_issue(board):
    before = board.copy_board()
    with pytest.raises(BoardError, match="WEB-999"):
        board.update_issue("WEB-999", status="done")
    with pytest.raises(BoardError, match="WEB-999"):
        board.add_comment("WEB-999", "x")
    assert board == before


def test_search_two_filters(board):
    found = board.search(label="frontend", type="bug")
    expected = [i for i in board.issues if i.type == "bug" and "frontend" in i.labels]
    assert found == expected


def test_search_unassigned_and_backlog(board):
    assert all(i.assignee is None for i in board.search(assignee="unassigned"))
    assert all(i.sprint is None for i in board.search(sprint="backlog"))
    assert len(board.search(assignee="unassigned")) == sum(i.assignee is None for i in board.issues)


def test_search_text_and_order(board):
    issue = board.issues[5]
    word = issue.title.split()[-1].upper()
    found = board.search(text=word)
    assert issue in found
    numbers = [int(i.key.split("-")[1]) for i in board.search()]
    assert numbers == sorted(numbers)


def test_search_bad_filter(board):
    with pytest.raises(BoardError):
        board.search(priority="urgent")


def test_new_issue_key(board):
    board.issues = [i for i in board.issues if int(i.key.split("-")[1]) <= 40]
    board.issues[-1].key = "WEB-40"
    issue = board.create_issue("Nowe zadanie", "task")
    assert issue.key == "WEB-41"
    assert issue.status == "to_do"


def test_labels(board):
    board.update_issue("WEB-2", add_labels=["docs", "api"], remove_labels=["docs"])
    assert "api" in board.issue("WEB-2").labels
    assert "docs" not in board.issue("WEB-2").labels


def test_diff_empty(board):
    assert diff(board, board.copy_board()) == []


def test_diff_assignee(board):
    after = board.copy_board()
    after.issue("WEB-12").assignee = "u4" if board.issue("WEB-12").assignee == "u3" else "u3"
    value = after.issue("WEB-12").assignee
    assert diff(board, after) == [{"op": "update", "key": "WEB-12", "field": "assignee", "value": value}]


def test_diff_all_kinds(board):
    after = board.copy_board()
    after.add_comment("WEB-3", "Czekamy na review")
    after.update_issue("WEB-2", add_labels=["zzz"])
    new = after.create_issue("Nowy bug", "bug", sprint="s2")
    changes = diff(board, after)
    assert [c["op"] for c in changes] == ["update", "comment", "create"]
    assert changes[0]["value"] == sorted(set(board.issue("WEB-2").labels) | {"zzz"})
    assert changes[1] == {"op": "comment", "key": "WEB-3", "text": "Czekamy na review"}
    assert "key" not in changes[2]["fields"]
    assert changes[2]["fields"]["title"] == new.title
