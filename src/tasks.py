"""Loader of the task files of a split: queries.json, solutions.json and expected.json (design D10)."""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

CATEGORIES = ("query", "update", "log", "create", "sprint", "bulk", "workflow", "refusal")
CHANGE_CATEGORIES = ("update", "log", "create", "sprint", "bulk", "workflow")
DIFFICULTIES = ("easy", "multi_step", "refusal")
ANSWER_TYPES = ("keys", "number", "person", "time", "value")
REFUSAL_KINDS = ("no_tool", "missing_entity", "ambiguous", "out_of_domain")
TASK_FILES = ("queries.json", "solutions.json", "expected.json")


class TaskFileError(ValueError):
    """The task files of a split do not agree. The message names the task id."""


class ToolCall(BaseModel):
    name: str
    arguments: dict = Field(default_factory=dict)


class Answer(BaseModel):
    type: Literal["keys", "number", "person", "time", "value"]
    value: list[str] | int | str


class Task(BaseModel):
    id: str
    author: str
    instruction: str
    calls: list[ToolCall]
    reference_answer: str
    board: str
    category: Literal["query", "update", "log", "create", "sprint", "bulk", "workflow", "refusal"]
    difficulty: Literal["easy", "multi_step", "refusal"]
    changes: list[dict] | None = None
    expected_answer: Answer | None = None
    refusal_kind: Literal["no_tool", "missing_entity", "ambiguous", "out_of_domain"] | None = None


def split_dir(split: str, data_dir: Path = DATA_DIR) -> Path:
    return Path(data_dir) / "tasks" / split


def board_path(name: str, data_dir: Path = DATA_DIR) -> Path:
    return Path(data_dir) / "environments" / f"{name}.json"


def _read(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _by_id(rows: list[dict], file: str) -> dict[str, dict]:
    result = {}
    for row in rows:
        if row.get("id") in result:
            raise TaskFileError(f"{row['id']}: the id occurs two times in {file}")
        result[row.get("id")] = row
    return result


def _check(task_id: str, exp: dict) -> None:
    """Check the allowed values and the key of the expected result. Stop with an error that names the task id."""
    for key, allowed in (("category", CATEGORIES), ("difficulty", DIFFICULTIES)):
        if exp.get(key) not in allowed:
            raise TaskFileError(f"{task_id}: {key} '{exp.get(key)}' is not allowed ({', '.join(allowed)})")
    category = exp["category"]
    if category == "query":
        answer = exp.get("answer")
        if not isinstance(answer, dict) or answer.get("type") not in ANSWER_TYPES:
            raise TaskFileError(f"{task_id}: the answer type of a query task must be one of {', '.join(ANSWER_TYPES)}")
    elif category == "refusal":
        if exp.get("refusal_kind") not in REFUSAL_KINDS:
            raise TaskFileError(f"{task_id}: refusal kind '{exp.get('refusal_kind')}' is not allowed "
                                f"({', '.join(REFUSAL_KINDS)})")
    elif not isinstance(exp.get("changes"), list) or not exp["changes"]:
        raise TaskFileError(f"{task_id}: a task of the category {category} must have a list of changes")
    if (category == "refusal") != (exp["difficulty"] == "refusal"):
        raise TaskFileError(f"{task_id}: only the category refusal has the difficulty refusal")
    if category in ("bulk", "workflow") and exp["difficulty"] != "multi_step":
        raise TaskFileError(f"{task_id}: a task of the category {category} must be multi_step")


def load_tasks(split: str, data_dir: Path = DATA_DIR) -> list[Task]:
    """Load the tasks of a split in the order of queries.json. A split without task files gives an empty list."""
    folder = split_dir(split, data_dir)
    if not any((folder / f).exists() for f in TASK_FILES):
        return []
    queries, solutions, expected = (_by_id(_read(folder / f), f) for f in TASK_FILES)
    personas_file = folder / "personas.json"
    authors = {p["name"] for p in _read(personas_file)} if personas_file.exists() else None
    for name, rows in (("solutions.json", solutions), ("expected.json", expected)):
        for task_id in sorted(set(queries) ^ set(rows)):
            where = name if task_id in queries else "queries.json"
            raise TaskFileError(f"{task_id}: the id is not in {where}")
    tasks = []
    for task_id, q in queries.items():
        s, e = solutions[task_id], expected[task_id]
        _check(task_id, e)
        if authors is not None and q.get("author") not in authors:
            raise TaskFileError(f"{task_id}: unknown author '{q.get('author')}'")
        if not board_path(e.get("board", ""), data_dir).exists():
            raise TaskFileError(f"{task_id}: unknown board '{e.get('board')}'")
        try:
            tasks.append(Task(
                id=task_id, author=q["author"], instruction=q["instruction"],
                calls=s["calls"], reference_answer=s["answer"], board=e["board"],
                category=e["category"], difficulty=e["difficulty"], changes=e.get("changes"),
                expected_answer=e.get("answer") if e["category"] == "query" else None,
                refusal_kind=e.get("refusal_kind"),
            ))
        except (KeyError, ValidationError) as err:
            raise TaskFileError(f"{task_id}: {err}") from None
    return tasks
