import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path

import pytest

from src.environment import load_board
from src.tasks import (
    CATEGORIES,
    REFUSAL_KINDS,
    TaskFileError,
    board_path,
    load_tasks,
    split_dir,
)
from src.tools import READ_TOOLS, apply_calls
from src.verifier import grade

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
KEY_RE = re.compile(r"\b[A-Z][A-Z0-9_]+-\d+\b")


@pytest.fixture(scope="module")
def tasks():
    return load_tasks("test")


# Loader

def test_load_test_set(tasks):
    assert len(tasks) == 200
    t = tasks[0]
    assert t.id == "test-001" and t.author and t.instruction and t.board and t.reference_answer
    query = next(t for t in tasks if t.category == "query")
    assert query.expected_answer is not None and query.changes is None


def test_missing_train_split(tmp_path):
    assert load_tasks("train", tmp_path) == []


def broken_copy(tmp_path, edit):
    """Copy the test split and the boards to tmp_path and change one file with `edit(name, rows)`."""
    shutil.copytree(DATA / "environments", tmp_path / "environments")
    folder = tmp_path / "tasks" / "test"
    shutil.copytree(split_dir("test"), folder)
    for name in ("queries.json", "solutions.json", "expected.json", "personas.json"):
        rows = json.loads((folder / name).read_text(encoding="utf-8"))
        edit(name, rows)
        (folder / name).write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def test_missing_solution(tmp_path):
    def edit(name, rows):
        if name == "queries.json":
            rows.append({"id": "test-201", "author": "Ewa Mazur", "instruction": "x"})
    with pytest.raises(TaskFileError, match="test-201"):
        load_tasks("test", broken_copy(tmp_path, edit))


@pytest.mark.parametrize("key,value,message", [
    ("board", "test-xyz", "unknown board"),
    ("category", "delete", "category"),
    ("difficulty", "hard", "difficulty"),
    ("answer", {"type": "date", "value": "x"}, "answer type"),
])
def test_values_not_allowed(tmp_path, key, value, message):
    def edit(name, rows):
        if name == "expected.json":
            rows[0][key] = value
    with pytest.raises(TaskFileError, match=f"test-001: .*{message}"):
        load_tasks("test", broken_copy(tmp_path, edit))


def test_unknown_author_and_refusal_kind(tmp_path):
    def edit(name, rows):
        if name == "queries.json":
            rows[1]["author"] = "Nikt"
    with pytest.raises(TaskFileError, match="test-002: unknown author"):
        load_tasks("test", broken_copy(tmp_path / "a", edit))

    def edit2(name, rows):
        if name == "expected.json":
            next(r for r in rows if r["category"] == "refusal")["refusal_kind"] = "rude"
    with pytest.raises(TaskFileError, match="refusal kind 'rude'"):
        load_tasks("test", broken_copy(tmp_path / "b", edit2))


# Rules of the task set

def test_counts(tasks):
    by_difficulty = Counter(t.difficulty for t in tasks)
    n = len(tasks)
    assert n >= 150
    assert by_difficulty["easy"] >= 0.3 * n
    assert by_difficulty["multi_step"] >= 0.4 * n
    assert by_difficulty["refusal"] >= 0.1 * n
    assert set(Counter(t.category for t in tasks)) == set(CATEGORIES)
    assert {t.refusal_kind for t in tasks if t.category == "refusal"} == set(REFUSAL_KINDS)


def test_categories_and_difficulties(tasks):
    for t in tasks:
        if t.category in ("bulk", "workflow"):
            assert t.difficulty == "multi_step", t.id
        assert (t.category == "refusal") == (t.difficulty == "refusal"), t.id


def test_refusal_solutions(tasks):
    for t in tasks:
        if t.category == "refusal":
            assert t.reference_answer.startswith("ODMOWA:"), t.id
            assert all(c.name in READ_TOOLS for c in t.calls), t.id


def test_author_belongs_to_board(tasks):
    personas = {p["name"]: p["board"] for p in json.loads((split_dir("test") / "personas.json").read_text(encoding="utf-8"))}
    assert all(personas[t.author] == t.board for t in tasks)


def test_keys_of_easy_tasks(tasks):
    """An easy task gives each existing issue key that it changes or reads."""
    for t in tasks:
        if t.difficulty != "easy":
            continue
        board = load_board(board_path(t.board))
        keys = {c["issue"] for c in t.changes or [] if "issue" in c}
        for call in t.calls:
            keys |= set(KEY_RE.findall(str(call.arguments.get("issue_key", ""))))
            keys |= set(KEY_RE.findall(str(call.arguments.get("issue_keys", ""))))
        keys = {k for k in keys if board.find_issue(k)}
        missing = {k for k in keys if not re.search(rf"\b{k}\b", t.instruction, re.IGNORECASE)}
        assert not missing, (t.id, missing)


def test_different_instructions(tasks):
    texts = Counter(t.instruction.strip().lower() for t in tasks)
    assert [text for text, n in texts.items() if n > 1] == []


def test_no_ids_in_instructions(tasks):
    for t in tasks:
        board = load_board(board_path(t.board))
        assert not any(p.account_id in t.instruction for p in board.persons), t.id
        assert not re.search(r"\bjira_\w+", t.instruction), t.id


def test_separate_splits(tasks):
    train = load_tasks("train")
    test_boards = {t.board for t in tasks}
    train_boards = {t.board for t in train}
    assert not test_boards & train_boards
    assert not {t.instruction for t in tasks} & {t.instruction for t in train}
    summaries = [{i.summary for b in boards for i in load_board(board_path(b)).issues}
                 for boards in (test_boards, train_boards)]
    assert not summaries[0] & summaries[1]


# Reference solutions (D10)

def test_reference_solutions(tasks):
    for t in tasks:
        initial = load_board(board_path(t.board))
        board = initial.copy_board()
        results = apply_calls(board, [c.model_dump() for c in t.calls])
        for call, result in zip(t.calls, results, strict=True):
            # The error of a read call shows that the entity of a missing_entity task does not exist.
            allowed = t.refusal_kind == "missing_entity" and call.name in READ_TOOLS
            assert not result.is_error or allowed, (t.id, call.name, result.text)
        g = grade(t, initial, board, t.reference_answer)
        assert g.grade in ("correct", "correct_refusal"), (t.id, g.reason)


# Frozen test set

# The test set was frozen on 2026-11-05. A change of these files needs a new run of all variants.
FROZEN: dict[str, str] = {
    "tasks/test/queries.json": "b93f77c47ee99eb77a0abbbc9d5fd947c546c8bdbf0f238d651a23a1c35a0ccd",
    "tasks/test/solutions.json": "743ebc80477915d57a7592874aa10c882283670b915dff4089efbf06c089592f",
    "tasks/test/expected.json": "d0850f62dafa8f24e169982cab448dcbc2c437a82a55de6a4e2cab10ca700b06",
    "environments/test-web.json": "194bb74800847c21b1905de7d88ea466d4ce298ef4528b88bdbfa3f6837c4c2e",
    "environments/test-app.json": "5bc82435043b2d4cfaf361b8736bdc87ddbf4d722fbb1c89784fffe51d2c648d",
    "environments/test-api.json": "e4755a881b389e69cf43ee1661fe914e4e103c4ece698475e94f3dc9234a73be",
    "environments/test-data.json": "c3ea7d8710c63d88ca38583aad4db68a8f1968867e0370e5235353d23c7e7253",
    "environments/test-ops.json": "b0bad77e4ab86dba5afe3f274130ab2f9e249f653b6090feb60cfcdd60a8b891",
}
FROZEN_FILES = [f"tasks/test/{n}" for n in ("queries.json", "solutions.json", "expected.json")] + [
    f"environments/test-{b}.json" for b in ("web", "app", "api", "data", "ops")]


def checksums(data_dir: Path) -> dict[str, str]:
    """SHA-256 of each frozen file. The line ends do not matter."""
    return {name: hashlib.sha256((data_dir / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for name in FROZEN_FILES}


def changed_files(want: dict[str, str], data_dir: Path) -> list[str]:
    got = checksums(data_dir)
    return [name for name in FROZEN_FILES if want.get(name) != got[name]]


@pytest.mark.skipif(not FROZEN, reason="test set not frozen yet")
def test_frozen_test_set():
    assert changed_files(FROZEN, DATA) == []


def test_checksum_finds_a_change(tmp_path):
    for name in FROZEN_FILES:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes((DATA / name).read_bytes().replace(b"\n", b"\r\n"))
    want = checksums(DATA)
    assert changed_files(want, tmp_path) == []
    path = tmp_path / "tasks/test/queries.json"
    path.write_text(path.read_text(encoding="utf-8").replace("WEB-7", "WEB-8", 1), encoding="utf-8")
    assert changed_files(want, tmp_path) == ["tasks/test/queries.json"]
