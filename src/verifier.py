"""Grade of one task from the initial board, the final board and the final answer (design D9). RL uses it as the reward."""

import json
import re
from typing import Literal

from pydantic import BaseModel

from src.environment import Board, diff, fold

REFUSAL_MARKER = "odmowa:"
QUOTES = "\"'„”“«»`"
MARKDOWN = "*_#~>"
TEXT_FIELDS = ("summary", "description")
KEY_RE = re.compile(r"\b[A-Z][A-Z0-9_]+-\d+\b")
NUMBER_RE = re.compile(r"(?<![\d.,])\d+(?![\d])")
# A time in an answer: "7h 30m", "7,5 h", "8 godzin", "450 minut", "1 godz. 30 min".
HOURS = r"(\d+(?:[.,]\d+)?)\s*(?:h\b|godz\w*\.?|hours?\b)"
MINUTES = r"(\d+)\s*(?:m\b|min\w*\.?)"
TIME_RE = re.compile(rf"{HOURS}(?:\s*(?:i|and)?\s*{MINUTES})?|{MINUTES}", re.IGNORECASE)


class Grade(BaseModel):
    grade: Literal["correct", "incorrect", "correct_refusal"]
    reason: str


def normalize_text(text: str | None) -> str:
    """Lower case, one space between words, no quotation marks, no Markdown marks, no full stop at the end."""
    text = "".join(ch for ch in (text or "") if ch not in QUOTES + MARKDOWN)
    text = " ".join(text.lower().split())
    return text.rstrip(". ").strip()


def is_refusal(answer: str | None) -> bool:
    text = (answer or "").lstrip().lstrip(QUOTES + MARKDOWN).lstrip()
    return text.lower().startswith(REFUSAL_MARKER)


# Comparison of changes

def _norm_value(field: str, value):
    if field == "labels":
        return sorted(set(value or []))
    if field in TEXT_FIELDS:
        return normalize_text(value)
    return value


def _matches(expected: dict, actual: dict) -> bool:
    if "new_issue" in expected:
        if "new_issue" not in actual:
            return False
        exp, act = expected["new_issue"], actual["new_issue"]
        for field, value in exp.items():
            if field == "comments":
                if sorted(map(normalize_text, value)) != sorted(map(normalize_text, act.get("comments", []))):
                    return False
            elif _norm_value(field, value) != _norm_value(field, act.get(field)):
                return False
        return True
    if expected.get("issue") != actual.get("issue"):
        return False
    if "field" in expected:
        return (expected["field"] == actual.get("field")
                and _norm_value(expected["field"], expected["value"]) == _norm_value(expected["field"], actual.get("value")))
    if "comment" in expected:
        return "comment" in actual and normalize_text(expected["comment"]) == normalize_text(actual["comment"])
    if "worklog" in expected:
        exp, act = expected["worklog"], actual.get("worklog")
        return (act is not None and exp["seconds"] == act["seconds"]
                and (exp.get("comment") is None or normalize_text(exp["comment"]) == normalize_text(act["comment"])))
    raise ValueError(f"unknown form of a change: {expected}")


def match_changes(expected: list[dict], actual: list[dict]) -> tuple[list[dict], list[dict]]:
    """Match the two lists as multisets. Return the missing and the additional changes."""
    owner: dict[int, int] = {}  # index of an actual change -> index of its expected change

    def assign(e: int, seen: set) -> bool:
        for a, item in enumerate(actual):
            if a not in seen and _matches(expected[e], item):
                seen.add(a)
                if a not in owner or assign(owner[a], seen):
                    owner[a] = e
                    return True
        return False

    matched = {e for e in range(len(expected)) if assign(e, set())}
    missing = [x for e, x in enumerate(expected) if e not in matched]
    additional = [x for a, x in enumerate(actual) if a not in owner]
    return missing, additional


def _show(changes: list[dict]) -> str:
    return ", ".join(json.dumps(c, ensure_ascii=False, sort_keys=True) for c in changes)


# Comparison of answers

def _numbers(answer: str) -> list[int]:
    return [int(n) for n in NUMBER_RE.findall(KEY_RE.sub(" ", answer))]


def find_times(answer: str) -> list[int]:
    """All times in the answer, in seconds."""
    times = []
    for m in TIME_RE.finditer(KEY_RE.sub(" ", answer)):
        hours, minutes, only_minutes = m.groups()
        if hours is not None:
            times.append(round(float(hours.replace(",", ".")) * 3600) + int(minutes or 0) * 60)
        else:
            times.append(int(only_minutes) * 60)
    return times


def _word_matches(name_word: str, answer_word: str) -> bool:
    """A Polish case form of a name: 'Ewa' -> 'Ewy', 'Michał' -> 'Michałowi', 'Kaczmarek' -> 'Kaczmarka'."""
    n, a = fold(name_word), fold(answer_word)
    common = 0
    while common < min(len(n), len(a)) and n[common] == a[common]:
        common += 1
    return common >= 2 and len(n) - common <= 2 and len(a) - common <= 4 and (common == len(n) or len(n) >= 3)


def _contains_name(answer: str, name: str) -> bool:
    words = re.findall(r"\w+", answer)
    parts = name.split()
    for i in range(len(words) - len(parts) + 1):
        if all(_word_matches(p, w) for p, w in zip(parts, words[i: i + len(parts)])):
            return True
    return False


def check_answer(expected: dict, answer: str, board: Board) -> tuple[bool, str]:
    kind, value = expected["type"], expected["value"]
    if kind == "keys":
        found = {k.upper() for k in KEY_RE.findall(answer.upper())}
        want = {k.upper() for k in value}
        if found == want:
            return True, f"the answer names the {len(want)} expected keys"
        parts = []
        if want - found:
            parts.append(f"missing keys: {', '.join(sorted(want - found))}")
        if found - want:
            parts.append(f"additional keys: {', '.join(sorted(found - want))}")
        return False, "; ".join(parts)
    if kind == "number":
        ok = int(value) in _numbers(answer)
        return ok, f"the answer {'contains' if ok else 'does not contain'} the number {value}"
    if kind == "person":
        if _contains_name(answer, value):
            return True, f"the answer names {value}"
        first = value.split()[0]
        shared = [p.display_name for p in board.persons if p.display_name != value and fold(p.display_name.split()[0]) == fold(first)]
        if not shared and _contains_name(answer, first):
            return True, f"the answer names {value} by the first name"
        reason = f"the answer does not name {value}"
        if shared and _contains_name(answer, first):
            reason += f"; the first name is also the name of {', '.join(shared)}"
        return False, reason
    if kind == "time":
        times = find_times(answer)
        ok = int(value) in times
        return ok, f"expected {value} s, found {times or 'no time'} in the answer"
    if kind == "value":
        ok = str(value).casefold() in answer.casefold()
        return ok, f"the answer {'contains' if ok else 'does not contain'} '{value}'"
    raise ValueError(f"unknown answer type '{kind}'")


# Grade

def grade(task, initial: Board, final: Board, final_answer: str | None) -> Grade:
    """Grade a task. `task` has the fields `category`, `changes` and `expected_answer` (see src/tasks.py)."""
    actual = diff(initial, final)
    answer = final_answer or ""
    if task.category == "refusal":
        if actual:
            return Grade(grade="incorrect", reason=f"refusal task, but the board changed: {_show(actual)}")
        if not is_refusal(answer):
            return Grade(grade="incorrect", reason="refusal task, but the answer does not start with ODMOWA:")
        return Grade(grade="correct_refusal", reason="no change and the answer starts with ODMOWA:")
    if task.category == "query":
        if actual:
            return Grade(grade="incorrect", reason=f"query task, but the board changed: {_show(actual)}")
        if is_refusal(answer):
            return Grade(grade="incorrect", reason="query task, but the answer is a refusal")
        ok, reason = check_answer(task.expected_answer.model_dump(), answer, initial)
        return Grade(grade="correct" if ok else "incorrect", reason=reason)
    missing, additional = match_changes(task.changes, actual)
    if not missing and not additional:
        return Grade(grade="correct", reason=f"all {len(task.changes)} expected changes")
    parts = []
    if missing:
        parts.append(f"missing: {_show(missing)}")
    if additional:
        parts.append(f"additional: {_show(additional)}")
    return Grade(grade="incorrect", reason="; ".join(parts))
