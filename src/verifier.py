"""Grade of one task from the initial board, the final board and the final answer. RL (E3) uses it as the reward."""

import json
import re
from collections import Counter
from typing import Literal

from pydantic import BaseModel

from src.environment import Board, diff

REFUSAL_MARKER = "odmowa:"
QUOTES = "\"'„”“«»`"


class Grade(BaseModel):
    grade: Literal["correct", "incorrect", "correct_refusal"]
    reason: str


def normalize_text(text: str) -> str:
    text = "".join(ch for ch in text if ch not in QUOTES)
    text = " ".join(text.lower().split())
    return text.rstrip(". ").strip()


def _canonical(entry: dict, ignore_description: bool) -> str:
    entry = json.loads(json.dumps(entry))
    if entry["op"] == "comment":
        entry["text"] = normalize_text(entry["text"])
    elif entry["op"] == "update":
        if entry["field"] == "title":
            entry["value"] = normalize_text(entry["value"])
        elif entry["field"] == "labels":
            entry["value"] = sorted(set(entry["value"]))
    else:
        fields = entry["fields"]
        fields["title"] = normalize_text(fields["title"])
        fields["labels"] = sorted(set(fields["labels"]))
        fields["comments"] = [normalize_text(c) for c in fields.get("comments", [])]
        # A task without a description for a new issue does not check the description.
        if ignore_description:
            fields.pop("description", None)
    return json.dumps(entry, ensure_ascii=False, sort_keys=True)


def _canonical_all(changes: list[dict], ignore_description: bool) -> Counter:
    return Counter(_canonical(c, ignore_description) for c in changes)


def is_refusal(answer: str | None) -> bool:
    return (answer or "").lstrip().lower().startswith(REFUSAL_MARKER)


def grade(task, initial_board: Board, final_board: Board, final_answer: str | None) -> Grade:
    """Grade a task. `task` has the fields `difficulty` and `expected` (see src/tasks.py)."""
    actual = diff(initial_board, final_board)
    if task.difficulty == "refusal":
        if actual:
            return Grade(grade="incorrect", reason=f"refusal task, but the board changed: {_show(actual)}")
        if not is_refusal(final_answer):
            return Grade(grade="incorrect", reason="refusal task, but the answer does not start with ODMOWA:")
        return Grade(grade="correct_refusal", reason="no change and the answer starts with ODMOWA:")

    ignore_description = all(
        c["fields"].get("description", "") == "" for c in task.expected if c["op"] == "create"
    )
    expected = _canonical_all(task.expected, ignore_description)
    got = _canonical_all(actual, ignore_description)
    missing = expected - got
    additional = got - expected
    if not missing and not additional:
        return Grade(grade="correct", reason=f"all {len(task.expected)} expected changes")
    parts = []
    if missing:
        parts.append(f"missing: {_show_keys(missing)}")
    if additional:
        parts.append(f"additional: {_show_keys(additional)}")
    return Grade(grade="incorrect", reason="; ".join(parts))


def _show(changes: list[dict]) -> str:
    return _show_keys(Counter(json.dumps(c, ensure_ascii=False, sort_keys=True) for c in changes))


def _show_keys(counter: Counter) -> str:
    return ", ".join(re.sub(r"\s+", " ", k) for k in sorted(counter.elements()))
