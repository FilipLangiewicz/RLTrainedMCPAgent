import hashlib
import random
import re
import shutil
from collections import Counter
from pathlib import Path

import pytest

from src.environment import LABELS, PROJECT_KEYS, generate_board, load_board
from src.tasks import (
    BOARDS,
    COUNTS,
    DATA_DIR,
    TEMPLATES,
    Task,
    board_path,
    check_reference,
    generate_all,
    load_tasks,
    make_task,
    save_tasks,
    tasks_path,
)
from src.tools import apply_calls
from src.verifier import grade

# SHA-256 of the frozen test set (E1). The hash ignores the line ends, because git can change them on checkout.
FROZEN = {
    "tasks/test/tasks.jsonl": "e7d101d3a47cc34cb5cd46bccd17859bb1c6ca418011527a579aaa04ad365530",
    "environments/test-01.json": "4fd7d7048ba0f3ad095c4d583cef2d00605f15a67fd5ea2979946f6652181222",
    "environments/test-02.json": "b19bc038995c2e319586dd8f599d70f72e4c5a722996eb5ed78cbec493e0ab4f",
    "environments/test-03.json": "cc435c8799b7e2dd3690de46a4faac3668af1ca503b44c17f225299dcb749ce1",
    "environments/test-04.json": "700e8627b7bbd0fde99aea2c1353af64c197bc8b5b3dc225db70fbf4bc86e610",
    "environments/test-05.json": "6e40368d675ab51f5ee1914c8248ef0874461c408b1d9ef1ddd0dc889ec8260b",
}
TOOL_WORDS = ("update_issue", "create_issue", "add_comment", "in_progress", "to_do", "assignee")


def checksum(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


@pytest.fixture(scope="module")
def test_tasks():
    return load_tasks("test")


@pytest.fixture(scope="module")
def train_tasks():
    return load_tasks("train")


def template_cases(difficulty):
    return [(t, seed) for t in TEMPLATES[difficulty] for seed in range(8)]


def run_template(template, difficulty, seed):
    board = generate_board("test-x", PROJECT_KEYS[seed % 5], seed)
    for n in range(30):
        task = make_task(template, difficulty, board, random.Random(f"{seed}-{n}"), "test")
        if task is not None:
            break
    else:
        pytest.skip("no target on this board")
    final = board.copy_board()
    apply_calls(final, [c.model_dump() for c in task.solution])
    return task, board, final


@pytest.mark.parametrize(("template", "seed"), template_cases("easy"), ids=lambda x: getattr(x, "__name__", x))
def test_easy_template(template, seed):
    task, board, final = run_template(template, "easy", seed)
    assert task.expected
    assert grade(task, board, final, "Gotowe.").grade == "correct"


@pytest.mark.parametrize(("template", "seed"), template_cases("multi_step"), ids=lambda x: getattr(x, "__name__", x))
def test_multi_step_template(template, seed):
    task, board, final = run_template(template, "multi_step", seed)
    assert task.expected
    assert grade(task, board, final, "Gotowe.").grade == "correct"


@pytest.mark.parametrize(("template", "seed"), template_cases("refusal"), ids=lambda x: getattr(x, "__name__", x))
def test_refusal_template(template, seed):
    task, board, final = run_template(template, "refusal", seed)
    assert task.solution == [] and task.expected == []
    assert grade(task, board, final, "ODMOWA: nie mogę").grade == "correct_refusal"


def test_refusal_tasks_in_files(test_tasks, train_tasks):
    refusals = [t for t in test_tasks + train_tasks if t.difficulty == "refusal"]
    assert refusals
    assert all(t.solution == [] and t.expected == [] for t in refusals)
    assert {t.category for t in refusals} == {"out_of_domain", "no_tool", "missing_entity"}


def test_task_format(test_tasks):
    assert set(Task.model_fields) == {
        "id", "split", "category", "difficulty", "board", "instruction", "solution", "expected"
    }
    assert len({t.id for t in test_tasks}) == len(test_tasks)
    assert all(t.split == "test" for t in test_tasks)
    assert all(t.expected for t in test_tasks if t.difficulty != "refusal")


def test_save_and_load(test_tasks, tmp_path):
    save_tasks(test_tasks[:5], tasks_path("test", tmp_path))
    assert load_tasks("test", tmp_path) == test_tasks[:5]


def test_counts(test_tasks, train_tasks):
    counts = Counter(t.difficulty for t in test_tasks)
    n = len(test_tasks)
    assert n >= 150
    assert counts["easy"] >= 0.3 * n and counts["multi_step"] >= 0.4 * n and counts["refusal"] >= 0.1 * n
    assert dict(counts) == COUNTS["test"]
    assert dict(Counter(t.difficulty for t in train_tasks)) == COUNTS["train"]


def test_each_category_has_more_than_one_text(test_tasks):
    variants = {}
    for t in test_tasks:
        # Replace keys, titles, numbers, names and labels, so that only the text template is left.
        text = re.sub(r"[A-Z]+-\d+", "K", t.instruction)
        text = re.sub(r"„[^”]*”", "Q", text)
        text = re.sub(r"\d+", "#", text)
        text = " ".join("N" if w[0].isupper() else w for w in text.split()[1:])
        text = re.sub(r"\b(" + "|".join(LABELS) + r")\b", "L", text)
        variants.setdefault(t.category, set()).add(text)
    assert all(len(v) > 1 for v in variants.values()), variants


def test_words_of_a_user(test_tasks, train_tasks):
    for t in test_tasks + train_tasks:
        assert not re.search(r"\bu\d\b|\bs\d\b", t.instruction), t.instruction
        assert not any(word in t.instruction for word in TOOL_WORDS), t.instruction


def test_separate_splits(test_tasks, train_tasks):
    assert {t.board for t in test_tasks} <= set(BOARDS["test"])
    assert {t.board for t in train_tasks} <= set(BOARDS["train"])
    assert not {t.board for t in test_tasks} & {t.board for t in train_tasks}
    assert not {t.instruction for t in test_tasks} & {t.instruction for t in train_tasks}
    assert len({t.instruction for t in test_tasks}) == len(test_tasks)
    test_keys = {load_board(board_path(b)).project for b in BOARDS["test"]}
    train_keys = {load_board(board_path(b)).project for b in BOARDS["train"]}
    assert not test_keys & train_keys


def test_reference_solutions_of_test_set(test_tasks):
    boards = {name: load_board(board_path(name)) for name in BOARDS["test"]}
    for task in test_tasks:
        check_reference(task, boards[task.board])


def test_same_output_from_two_runs(tmp_path):
    generate_all(2026, tmp_path / "a")
    generate_all(2026, tmp_path / "b")
    files = sorted(p.relative_to(tmp_path / "a") for p in (tmp_path / "a").rglob("*") if p.is_file())
    assert len(files) == 27
    for f in files:
        assert (tmp_path / "a" / f).read_bytes() == (tmp_path / "b" / f).read_bytes(), f


@pytest.mark.parametrize("name", sorted(FROZEN))
def test_frozen_test_set(name):
    assert checksum(DATA_DIR / name) == FROZEN[name], f"{name} changed. The test set is frozen since E1."


def test_checksum_finds_a_change(tmp_path):
    copy = tmp_path / "tasks.jsonl"
    shutil.copy(DATA_DIR / "tasks/test/tasks.jsonl", copy)
    lines = copy.read_text(encoding="utf-8").splitlines(keepends=True)
    lines[10] = lines[10].replace("„", '"', 1) if "„" in lines[10] else lines[10].replace(".", "!", 1)
    copy.write_text("".join(lines), encoding="utf-8", newline="\n")
    assert checksum(copy) != FROZEN["tasks/test/tasks.jsonl"]
