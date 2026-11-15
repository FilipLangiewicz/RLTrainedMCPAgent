import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path

import pytest

from src.boards import build_all
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

SPLITS = ("test", "train", "validation")
# The train and validation solutions teach the model to find each value with a tool. The test solutions do not.
TAUGHT_SPLITS = ("train", "validation")
_BOARDS = {}
_REPLAYS = {}


def board(name):
    if name not in _BOARDS:
        _BOARDS[name] = load_board(board_path(name))
    return _BOARDS[name]


def replay(t):
    """Apply the reference calls of a task to a copy of its board. Return (initial, final, results)."""
    if t.id not in _REPLAYS:
        initial = board(t.board)
        final = initial.copy_board()
        _REPLAYS[t.id] = (initial, final, apply_calls(final, [c.model_dump() for c in t.calls]))
    return _REPLAYS[t.id]


@pytest.fixture(scope="module")
def tasks():
    return load_tasks("test")


@pytest.fixture(scope="module", params=SPLITS)
def split_tasks(request):
    return load_tasks(request.param)


# Loader

def test_load_test_set(tasks):
    assert len(tasks) == 200
    t = tasks[0]
    assert t.id == "test-001" and t.author and t.instruction and t.board and t.reference_answer
    query = next(t for t in tasks if t.category == "query")
    assert query.expected_answer is not None and query.changes is None


def test_load_train_and_validation_sets():
    assert len(load_tasks("train")) == 1000
    assert len(load_tasks("validation")) == 120


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

def test_counts(split_tasks):
    by_difficulty = Counter(t.difficulty for t in split_tasks)
    n = len(split_tasks)
    assert n >= 100
    assert by_difficulty["easy"] >= 0.3 * n
    assert by_difficulty["multi_step"] >= 0.4 * n
    assert by_difficulty["refusal"] >= 0.1 * n
    assert set(Counter(t.category for t in split_tasks)) == set(CATEGORIES)
    assert {t.refusal_kind for t in split_tasks if t.category == "refusal"} == set(REFUSAL_KINDS)


def test_categories_and_difficulties(split_tasks):
    for t in split_tasks:
        if t.category in ("bulk", "workflow"):
            assert t.difficulty == "multi_step", t.id
        assert (t.category == "refusal") == (t.difficulty == "refusal"), t.id


def test_refusal_solutions(split_tasks):
    for t in split_tasks:
        if t.category == "refusal":
            assert t.reference_answer.startswith("ODMOWA:"), t.id
            assert all(c.name in READ_TOOLS for c in t.calls), t.id


def test_author_belongs_to_board(split_tasks):
    split = split_tasks[0].id.rsplit("-", 1)[0]
    rows = json.loads((split_dir(split) / "personas.json").read_text(encoding="utf-8"))
    personas = {p["name"]: p["board"] for p in rows}
    assert all(personas[t.author] == t.board for t in split_tasks)


def test_keys_of_easy_tasks(split_tasks):
    """An easy task gives each existing issue key that it changes or reads."""
    for t in split_tasks:
        if t.difficulty != "easy":
            continue
        keys = {c["issue"] for c in t.changes or [] if "issue" in c}
        for call in t.calls:
            keys |= set(KEY_RE.findall(str(call.arguments.get("issue_key", ""))))
            keys |= set(KEY_RE.findall(str(call.arguments.get("issue_keys", ""))))
        keys = {k for k in keys if board(t.board).find_issue(k)}
        missing = {k for k in keys if not re.search(rf"\b{k}\b", t.instruction, re.IGNORECASE)}
        assert not missing, (t.id, missing)


def test_different_instructions(split_tasks):
    texts = Counter(t.instruction.strip().lower() for t in split_tasks)
    assert [text for text, n in texts.items() if n > 1] == []


def test_no_ids_in_instructions(split_tasks):
    for t in split_tasks:
        assert not any(p.account_id in t.instruction for p in board(t.board).persons), t.id
        assert not re.search(r"\bjira_\w+", t.instruction), t.id


@pytest.mark.parametrize("a,b", [("test", "train"), ("test", "validation"), ("train", "validation")])
def test_separate_splits(a, b):
    """No board, instruction, issue summary or person occurs in two splits."""
    one, two = load_tasks(a), load_tasks(b)
    boards = [{t.board for t in ts} for ts in (one, two)]
    assert not boards[0] & boards[1]
    assert not {t.instruction for t in one} & {t.instruction for t in two}
    summaries = [{i.summary.casefold() for name in bs for i in board(name).issues} for bs in boards]
    assert not summaries[0] & summaries[1]
    persons = [{p.display_name for name in bs for p in board(name).persons} for bs in boards]
    assert not persons[0] & persons[1]


def test_boards_from_companies():
    """The train and validation boards are the output of src/boards.py for data/companies/."""
    built = build_all()
    files = {p.stem for p in (DATA / "environments").glob("*.json") if not p.stem.startswith("test-")}
    assert {b.name for b in built} == files
    for b in built:
        assert b.model_dump() == board(b.name).model_dump(), b.name


# Reference solutions (D10)

def test_reference_solutions(split_tasks):
    for t in split_tasks:
        initial, final, results = replay(t)
        for call, result in zip(t.calls, results, strict=True):
            # The error of a read call shows that the entity of a missing_entity task does not exist.
            allowed = t.refusal_kind == "missing_entity" and call.name in READ_TOOLS
            assert not result.is_error or allowed, (t.id, call.name, result.text)
        g = grade(t, initial, final, t.reference_answer)
        assert g.grade in ("correct", "correct_refusal"), (t.id, g.reason)


ID_ARGUMENTS = ("issue_key", "issue_keys", "sprint_id", "transition_id", "project_key", "board_id")


def call_values(call):
    """The keys, ids, projects and persons that a call uses."""
    a = call.arguments
    values = [v.strip() for k in ID_ARGUMENTS if k in a for v in str(a[k]).split(",")]
    values += re.findall(r"project\s*=\s*(\w+)", a.get("jql", ""))
    if call.name in ("jira_update_issue", "jira_create_issue"):
        values += [x for x in (json.loads(a.get("fields") or "{}").get("assignee"), a.get("assignee")) if x]
    if call.name == "jira_transition_issue":
        values.remove(a["issue_key"])
    return values


def guessed_values(t):
    """Values in the calls that do not occur in the instruction or in an earlier tool result."""
    seen, guessed = t.instruction, []
    for call, result in zip(t.calls, replay(t)[2]):
        # A get_transitions call reads a key of the instruction or of a result. A missing_entity read tests a key.
        skip = call.name == "jira_get_transitions" or (t.refusal_kind == "missing_entity" and call.name == "jira_get_issue")
        for v in [] if skip else call_values(call):
            if not re.search(r"(?<![A-Za-z0-9])" + re.escape(v) + r"(?![A-Za-z0-9])", seen):
                guessed.append(f"{call.name}: {v}")
        seen += "\n" + result.text
    return guessed


@pytest.mark.parametrize("split", TAUGHT_SPLITS)
def test_no_guessed_values(split):
    """Each key, sprint id, transition id, project and person comes from the instruction or from a tool."""
    problems = {t.id: g for t in load_tasks(split) if (g := guessed_values(t))}
    assert problems == {}


def answer_problem(t):
    """Check the expected answer of a query task and the keys of an ambiguous refusal with the last tool result."""
    results = replay(t)[2]
    if not results:
        return None
    last, last_call = results[-1].text, t.calls[-1].name
    if t.expected_answer:
        kind, value = t.expected_answer.type, t.expected_answer.value
        if kind in ("keys", "number") and last_call == "jira_search":
            keys = [i["key"] for i in json.loads(last)["issues"]]
            if (kind == "keys" and set(value) != set(keys)) or (kind == "number" and value != len(keys)):
                return f"{kind} {value} differ from the last search {keys}"
        if kind in ("value", "person") and not re.search('"' + re.escape(str(value)) + '"', last):
            return f"{kind} '{value}' is not a field value in the last result"
        if kind == "time" and value != sum(w["time_spent_seconds"] for w in json.loads(last)["worklogs"]):
            return f"time {value} differs from the worklogs"
    if t.refusal_kind == "ambiguous" and last_call == "jira_search":
        keys = {i["key"] for i in json.loads(last)["issues"]}
        if keys != set(KEY_RE.findall(t.reference_answer)):
            return f"the answer does not name the issues of the last search {sorted(keys)}"
    return None


@pytest.mark.parametrize("split", TAUGHT_SPLITS)
def test_answers_agree_with_tools(split):
    problems = {t.id: p for t in load_tasks(split) if (p := answer_problem(t))}
    assert problems == {}


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
        # A checkout with core.autocrlf already has CRLF line ends.
        lf = (DATA / name).read_bytes().replace(b"\r\n", b"\n")
        (tmp_path / name).write_bytes(lf.replace(b"\n", b"\r\n"))
    want = checksums(DATA)
    assert changed_files(want, tmp_path) == []
    path = tmp_path / "tasks/test/queries.json"
    path.write_text(path.read_text(encoding="utf-8").replace("WEB-7", "WEB-8", 1), encoding="utf-8")
    assert changed_files(want, tmp_path) == ["tasks/test/queries.json"]
