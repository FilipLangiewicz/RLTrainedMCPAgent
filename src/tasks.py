"""Task format, task templates, the task generator, and load and save of task files."""

import argparse
import json
import random
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from src.environment import (
    FIRST_NAMES,
    LABELS,
    PRIORITIES,
    PROJECT_KEYS,
    SURNAMES,
    TITLE_OBJECTS,
    TITLE_TEMPLATES,
    Board,
    diff,
    generate_board,
    key_number,
    name_forms,
    save_board,
)
from src.tools import apply_calls
from src.verifier import grade

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

BOARDS = {
    "test": [f"test-{n:02d}" for n in range(1, 6)],
    "train": [f"train-{n:02d}" for n in range(1, 21)],
}
COUNTS = {
    "test": {"easy": 70, "multi_step": 100, "refusal": 30},
    "train": {"easy": 350, "multi_step": 500, "refusal": 150},
}


class ToolCall(BaseModel):
    name: str
    arguments: dict


class Task(BaseModel):
    id: str
    split: Literal["train", "test"]
    category: str
    difficulty: Literal["easy", "multi_step", "refusal"]
    board: str
    instruction: str
    solution: list[ToolCall]
    expected: list[dict]


def tasks_path(split: str, data_dir: Path = DATA_DIR) -> Path:
    return Path(data_dir) / "tasks" / split / "tasks.jsonl"


def board_path(name: str, data_dir: Path = DATA_DIR) -> Path:
    return Path(data_dir) / "environments" / f"{name}.json"


def save_tasks(tasks: list[Task], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(json.dumps(task.model_dump(), ensure_ascii=False) + "\n" for task in tasks)


def load_tasks(split: str, data_dir: Path = DATA_DIR) -> list[Task]:
    lines = tasks_path(split, data_dir).read_text(encoding="utf-8").splitlines()
    return [Task.model_validate_json(line) for line in lines if line.strip()]


# Polish words of a user

STATUS_TEXTS = {
    "to_do": ("Cofnij {key} do zrobienia.", "Przywróć {key} do statusu „do zrobienia”.",
              "Zmień status {key} na do zrobienia."),
    "in_progress": ("Oznacz {key} jako w toku.", "Ustaw {key} na w trakcie.", "Zmień status {key} na „w toku”.",
                    "Ruszyliśmy z {key}, zmień status na w toku."),
    "done": ("Zamknij {key}.", "{key} jest zrobione, oznacz je jako zakończone.", "Zmień status {key} na zrobione.",
             "Oznacz {key} jako gotowe."),
}
PRIORITY_ADJ = {"low": "niski", "medium": "średni", "high": "wysoki", "critical": "krytyczny"}
PRIORITY_INS = {"low": "niskim", "medium": "średnim", "high": "wysokim", "critical": "krytycznym"}
TYPE_ACC = {"bug": ("bug", "błąd"), "task": ("zadanie", "task"), "story": ("story", "historyjkę")}
TYPE_PLURAL = {"bug": ("bugi", "błędy"), "task": ("zadania", "taski"), "story": ("story", "historyjki")}
COMMENT_TEXTS = (
    "Czekamy na review", "Poprawka jest na branchu develop", "Klient potwierdził problem",
    "Do sprawdzenia po wdrożeniu", "Potrzebne dodatkowe testy", "Blokuje nas brak dostępu do API",
    "Przesunięte po rozmowie z klientem", "Zrobione, proszę o weryfikację",
)


def _call(name: str, **arguments) -> dict:
    return {"name": name, "arguments": arguments}


def _open(board: Board) -> list:
    return [i for i in board.issues if i.status != "done"]


def _persons(board: Board) -> list:
    return [(p, name_forms(p)) for p in board.persons]


def _new_title(board: Board, rng: random.Random, type_: str) -> str | None:
    existing = {i.title for i in board.issues}
    options = [t.format(o) for t in TITLE_TEMPLATES[type_] for o in TITLE_OBJECTS]
    options = [t for t in options if t not in existing]
    return rng.choice(options) if options else None


# Templates. Each template gets a board, a random generator and the split.
# It returns (instruction, reference solution) or None when the board has no good target.

def assign_issue(board, rng, split):
    issue = rng.choice(_open(board))
    person, f = rng.choice([(p, f) for p, f in _persons(board) if p.id != issue.assignee])
    text = rng.choice(("Przypisz {key} {dat}.", "Daj {key} {dat}.", "Niech {nom} weźmie {key}.",
                       "Przekaż {key} {dat}, proszę.", "{nom} zajmie się {key}, przypisz to."))
    return text.format(key=issue.key, **f), [_call("update_issue", key=issue.key, assignee=person.id)]


def change_status(board, rng, split):
    issue = rng.choice(board.issues)
    status = rng.choice([s for s in STATUS_TEXTS if s != issue.status])
    text = rng.choice(STATUS_TEXTS[status])
    return text.format(key=issue.key), [_call("update_issue", key=issue.key, status=status)]


def change_priority(board, rng, split):
    issue = rng.choice(board.issues)
    priority = rng.choice([p for p in PRIORITIES if p != issue.priority])
    texts = ["Zmień priorytet {key} na {adj}.", "Ustaw {key} priorytet {adj}.", "{key} ma mieć priorytet {adj}."]
    if PRIORITIES.index(priority) > PRIORITIES.index(issue.priority):
        texts.append("Podnieś priorytet {key} na {adj}.")
    else:
        texts.append("Obniż priorytet {key} na {adj}.")
    text = rng.choice(texts).format(key=issue.key, adj=PRIORITY_ADJ[priority])
    return text, [_call("update_issue", key=issue.key, priority=priority)]


def add_label(board, rng, split):
    issue = rng.choice(board.issues)
    label = rng.choice([label for label in LABELS if label not in issue.labels])
    text = rng.choice(("Dodaj etykietę {label} do {key}.", "Otaguj {key} jako {label}.",
                       "Dorzuć label {label} do {key}.", "Dodaj do {key} etykietę {label}."))
    return text.format(key=issue.key, label=label), [_call("update_issue", key=issue.key, add_labels=[label])]


def add_comment(board, rng, split):
    issue = rng.choice(board.issues)
    comment = rng.choice(COMMENT_TEXTS)
    text = rng.choice(("Dodaj komentarz do {key}: „{c}”.", "Napisz w {key} komentarz: {c}.",
                       "Skomentuj {key}: „{c}”.", "Zostaw w {key} notkę: {c}."))
    return text.format(key=issue.key, c=comment), [_call("add_comment", key=issue.key, text=comment)]


def move_issue(board, rng, split):
    active, nxt = board.active_sprint(), board.next_sprint()
    others = [s for s in board.sprints if s.state == "future" and s.id != nxt.id]
    target = rng.choice(["active", "next", "backlog"] + (["other"] if others else []))
    sprint_id = {"active": active.id, "next": nxt.id, "backlog": None}.get(target)
    if target == "other":
        sprint = rng.choice(others)
        sprint_id = sprint.id
    issues = [i for i in _open(board) if i.sprint != sprint_id]
    if not issues:
        return None
    issue = rng.choice(issues)
    texts = {
        "active": ("Przenieś {key} do bieżącego sprintu.", "Wrzuć {key} do aktualnego sprintu."),
        "next": ("Wrzuć {key} do następnego sprintu.", "Przesuń {key} na następny sprint."),
        "backlog": ("Przenieś {key} do backlogu.", "Wyrzuć {key} ze sprintu do backlogu."),
        "other": ("Przenieś {key} do sprintu {n}.",),
    }[target]
    n = sprint_id[1:] if sprint_id else ""
    text = rng.choice(texts).format(key=issue.key, n=n)
    return text, [_call("update_issue", key=issue.key, sprint=sprint_id or "none")]


def _create_extra(rng, args):
    extra = rng.choice(("", "priority", "label", "both"))
    parts = []
    if extra in ("priority", "both"):
        args["priority"] = rng.choice(("low", "high", "critical"))
        parts.append(f"z {PRIORITY_INS[args['priority']]} priorytetem")
    if extra in ("label", "both"):
        args["labels"] = [rng.choice(LABELS)]
        parts.append(f"{'i ' if parts else 'z '}etykietą {args['labels'][0]}")
    return (" " + " ".join(parts)) if parts else ""


def create_issue(board, rng, split):
    type_ = rng.choice(("bug", "task", "story"))
    title = _new_title(board, rng, type_)
    if title is None:
        return None
    args = {"title": title, "type": type_}
    extra = _create_extra(rng, args)
    text = rng.choice(("Utwórz {t} „{title}”{extra}.", "Załóż {t} o tytule „{title}”{extra}.",
                       "Dodaj {t} „{title}”{extra}.", "Potrzebuję nowego zgłoszenia ({tw}): „{title}”{extra}."))
    text = text.format(t=rng.choice(TYPE_ACC[type_]), tw=TYPE_ACC[type_][0], title=title, extra=extra)
    return text, [_call("create_issue", **args)]


def assign_filtered(board, rng, split):
    person, f = rng.choice(_persons(board))
    type_ = rng.choice(("bug", "task", "story"))
    if rng.random() < 0.5:
        label = rng.choice(LABELS)
        matching = [i for i in _open(board) if i.type == type_ and label in i.labels]
        texts = ("Przypisz {dat} wszystkie otwarte {types} z etykietą {label}.",
                 "Wszystkie otwarte {types} z labelem {label} daj {dat}.",
                 "Niech {nom} weźmie wszystkie otwarte {types} oznaczone jako {label}.")
        values = {"label": label}
    else:
        priority = rng.choice(PRIORITIES)
        matching = [i for i in _open(board) if i.type == type_ and i.priority == priority]
        texts = ("Przypisz {dat} wszystkie otwarte {types} o {prio} priorytecie.",
                 "Daj {dat} wszystkie otwarte {types} z priorytetem {adj}.")
        values = {"prio": PRIORITY_INS[priority], "adj": PRIORITY_ADJ[priority]}
    change = [i for i in matching if i.assignee != person.id]
    if len(change) < 2:
        return None
    text = rng.choice(texts).format(types=rng.choice(TYPE_PLURAL[type_]), **values, **f)
    return text, [_call("update_issue", key=i.key, assignee=person.id) for i in change]


def move_bugs_next_sprint(board, rng, split):
    person, f = rng.choice(_persons(board))
    label = rng.choice(LABELS)
    nxt = board.next_sprint()
    calls = []
    for i in _open(board):
        if i.type == "bug" and label in i.labels:
            args = {}
            if i.sprint != nxt.id:
                args["sprint"] = nxt.id
            if i.assignee != person.id:
                args["assignee"] = person.id
            if args:
                calls.append(_call("update_issue", key=i.key, **args))
    if len(calls) < 2:
        return None
    text = rng.choice(("Przenieś otwarte bugi z etykietą {label} do następnego sprintu i przypisz je {dat}.",
                       "Wszystkie otwarte błędy z labelem {label} wrzuć do następnego sprintu i daj {dat}.",
                       "Otwarte bugi oznaczone jako {label} przesuń na następny sprint. Niech zajmie się nimi {nom}."))
    return text.format(label=label, **f), calls


def close_person_sprint(board, rng, split):
    person, f = rng.choice(_persons(board))
    active = board.active_sprint()
    issues = [i for i in _open(board) if i.assignee == person.id and i.sprint == active.id]
    if len(issues) < 2:
        return None
    female = f["gender"] == "f"
    text = rng.choice(("Zamknij wszystkie otwarte zgłoszenia {gen} w bieżącym sprincie.",
                       "{nom} skończył{a} pracę w bieżącym sprincie, oznacz wszystkie {pron} zgłoszenia jako zrobione.",
                       "Oznacz jako zrobione wszystko, co {nom} ma w bieżącym sprincie."))
    text = text.format(a="a" if female else "", pron="jej" if female else "jego", **f)
    return text, [_call("update_issue", key=i.key, status="done") for i in issues]


def reassign_person(board, rng, split):
    (a, fa), (b, fb) = rng.sample(_persons(board), 2)
    issues = [i for i in _open(board) if i.assignee == a.id]
    if len(issues) < 2:
        return None
    text = rng.choice(("Przekaż wszystkie otwarte zgłoszenia {a_gen} {b_dat}.",
                       "{a_nom} idzie na urlop, daj wszystkie {pron} otwarte tickety {b_dat}.",
                       "Wszystko, co {a_nom} ma otwarte, przepisz na {b_acc}."))
    text = text.format(a_gen=fa["gen"], a_nom=fa["nom"], b_dat=fb["dat"], b_acc=fb["acc"],
                       pron="jej" if fa["gender"] == "f" else "jego")
    return text, [_call("update_issue", key=i.key, assignee=b.id) for i in issues]


def create_in_sprint(board, rng, split):
    type_ = rng.choice(("bug", "task", "story"))
    title = _new_title(board, rng, type_)
    if title is None:
        return None
    person, f = rng.choice(_persons(board))
    sprint, loc, gen = rng.choice((
        (board.active_sprint(), "bieżącym sprincie", "bieżącego sprintu"),
        (board.next_sprint(), "następnym sprincie", "następnego sprintu"),
    ))
    text = rng.choice(("Utwórz {t} „{title}” w {loc} i przypisz {dat}.",
                       "Załóż {t} „{title}” dla {gen}, dodaj do {sgen}.",
                       "Dodaj do {sgen} nowe zgłoszenie ({tw}) „{title}” i daj je {dat}."))
    text = text.format(t=rng.choice(TYPE_ACC[type_]), tw=TYPE_ACC[type_][0], title=title,
                       loc=loc, sgen=gen, **f)
    return text, [_call("create_issue", title=title, type=type_, assignee=person.id, sprint=sprint.id)]


def start_unassigned_bugs(board, rng, split):
    options = [(("high",), "o wysokim priorytecie"), (("critical",), "o krytycznym priorytecie"),
               (("high", "critical"), "o wysokim lub krytycznym priorytecie")]
    rng.shuffle(options)
    person, f = rng.choice(_persons(board))
    for priorities, words in options:
        issues = [i for i in _open(board) if i.type == "bug" and i.assignee is None and i.priority in priorities]
        if len(issues) >= 2:
            break
    else:
        return None
    text = rng.choice(("Wszystkie otwarte, nieprzypisane bugi {prio} ustaw na w toku i przypisz {dat}.",
                       "Weź otwarte nieprzypisane błędy {prio}, zmień ich status na w trakcie i daj je {dat}.",
                       "Niech {nom} zacznie wszystkie otwarte, nieprzypisane bugi {prio}. Przypisz je i ustaw status w toku."))
    calls = []
    for i in issues:
        args = {"assignee": person.id}
        if i.status != "in_progress":
            args["status"] = "in_progress"
        calls.append(_call("update_issue", key=i.key, **args))
    return text.format(prio=words, **f), calls


# Refusal texts. The test split and the train split use separate lists.

REFUSAL_TEXTS = {
    "test": {
        "out_of_domain": ("Jaka będzie jutro pogoda {city}?", "Ile to jest {a} razy {b}?",
                          "Wyślij {dat} maila z podsumowaniem sprintu.", "Jaki jest dzisiaj kurs euro?",
                          "Napisz krótki wiersz o sprincie {n}."),
        "no_tool": ("Usuń zgłoszenie {key}.", "Usuń sprint {n} z projektu.", "Zmień moje hasło do systemu.",
                    "Usuń {acc} z projektu.", "Zarchiwizuj cały projekt {project}."),
        "missing_entity": ("Przypisz {key} {missing_dat}.", "Zmień priorytet {missing_key} na wysoki.",
                           "Dodaj komentarz do {missing_key}: „Do sprawdzenia”."),
        "cities": ("w Krakowie", "w Gdańsku", "w Poznaniu", "we Wrocławiu"),
    },
    "train": {
        "out_of_domain": ("Czy jutro {city} będzie padać?", "Policz {a} plus {b}.",
                          "Wyślij e-mail do {gen} z listą zadań.", "Przetłumacz na angielski tytuł {key}.",
                          "Zarezerwuj salę na spotkanie o {hour}:00."),
        "no_tool": ("Skasuj {key}, już niepotrzebne.", "Skasuj sprint {n}.", "Zresetuj hasło {gen}.",
                    "Dodaj nowego użytkownika: {full}.", "Zmień nazwę projektu {project} na {project}2."),
        "missing_entity": ("Daj {key} {missing_dat}.", "Zamknij {missing_key}.",
                           "Przenieś {missing_key} do następnego sprintu."),
        "cities": ("w Łodzi", "w Lublinie", "w Szczecinie", "w Katowicach"),
    },
}


def _refusal(category):
    def template(board, rng, split):
        texts = REFUSAL_TEXTS[split]
        _, f = rng.choice(_persons(board))
        on_board = {p.name.split()[0] for p in board.persons}
        missing = rng.choice(sorted(set(FIRST_NAMES) - on_board))
        gender = FIRST_NAMES[missing][0]
        last = rng.choice(SURNAMES)[0 if gender == "m" else 1]
        values = {
            **f,
            "city": rng.choice(texts["cities"]),
            "a": rng.randint(12, 99), "b": rng.randint(12, 99), "hour": rng.randint(8, 17),
            "n": rng.choice(board.sprints).id[1:],
            "key": rng.choice(board.issues).key,
            "project": board.project,
            "missing_dat": FIRST_NAMES[missing][3],
            "missing_key": f"{board.project}-{max(key_number(i.key) for i in board.issues) + rng.randint(5, 200)}",
            "full": f"{missing} {last}",
        }
        return rng.choice(texts[category]).format(**values), []
    template.__name__ = category
    return template


TEMPLATES = {
    "easy": [assign_issue, change_status, change_priority, add_label, add_comment, move_issue, create_issue],
    "multi_step": [assign_filtered, move_bugs_next_sprint, close_person_sprint, reassign_person,
                   create_in_sprint, start_unassigned_bugs],
    "refusal": [_refusal("out_of_domain"), _refusal("no_tool"), _refusal("missing_entity")],
}


# Generator

def make_task(template, difficulty: str, board: Board, rng: random.Random, split: str) -> Task | None:
    draft = template(board, rng, split)
    if draft is None:
        return None
    instruction, calls = draft
    final = board.copy_board()
    apply_calls(final, calls)
    return Task(id="", split=split, category=template.__name__, difficulty=difficulty, board=board.name,
                instruction=instruction, solution=calls, expected=diff(board, final))


def generate_boards(seed: int) -> dict[str, Board]:
    names = BOARDS["test"] + BOARDS["train"]
    return {name: generate_board(name, key, seed) for name, key in zip(names, PROJECT_KEYS)}


def generate_tasks(boards: dict[str, Board], split: str, seed: int, seen: set[str]) -> list[Task]:
    """Make the tasks of one split. `seen` has the instructions of the other split; the function adds its own."""
    names = BOARDS[split]
    tasks = []

    def attempt(template, difficulty: str, n: int) -> bool:
        board = boards[names[n % len(names)]]
        rng = random.Random(f"{seed}-{split}-{difficulty}-{template.__name__}-{n}")
        task = make_task(template, difficulty, board, rng, split)
        if task is None or task.instruction in seen:
            return False
        if difficulty != "refusal" and not task.expected:
            return False
        seen.add(task.instruction)
        tasks.append(task)
        return True

    for difficulty, target in COUNTS[split].items():
        templates = TEMPLATES[difficulty]
        # First each category gets an equal quota. A category without enough targets leaves a rest.
        attempts = dict.fromkeys(range(len(templates)), 0)
        made = 0
        for k, template in enumerate(templates):
            quota = target // len(templates) + (k < target % len(templates))
            count = 0
            while count < quota and attempts[k] < 50 * quota:
                count += attempt(template, difficulty, attempts[k])
                attempts[k] += 1
            made += count
        # Then the categories fill the rest in turn.
        k = 0
        while made < target:
            if sum(attempts.values()) > 200 * target:
                raise RuntimeError(f"cannot make {target} {difficulty} tasks for {split}")
            made += attempt(templates[k], difficulty, attempts[k])
            attempts[k] += 1
            k = (k + 1) % len(templates)
    random.Random(f"{seed}-{split}-order").shuffle(tasks)
    return [t.model_copy(update={"id": f"{split}-{n:04d}"}) for n, t in enumerate(tasks, start=1)]


def check_reference(task: Task, board: Board) -> None:
    final = board.copy_board()
    apply_calls(final, [c.model_dump() for c in task.solution])
    result = grade(task, board, final, "ODMOWA: brak narzędzia" if task.difficulty == "refusal" else "Gotowe.")
    if result.grade not in ("correct", "correct_refusal"):
        raise RuntimeError(f"reference solution of {task.id} is not correct: {result.reason}")


def generate_all(seed: int, data_dir: Path = DATA_DIR) -> dict[str, list[Task]]:
    boards = generate_boards(seed)
    for board in boards.values():
        save_board(board, board_path(board.name, data_dir))
    seen: set[str] = set()
    result = {}
    for split in ("test", "train"):
        tasks = generate_tasks(boards, split, seed, seen)
        for task in tasks:
            check_reference(task, boards[task.board])
        save_tasks(tasks, tasks_path(split, data_dir))
        result[split] = tasks
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Make all boards and both task files.")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--data", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    for split, tasks in generate_all(args.seed, args.data).items():
        counts = Counter(t.difficulty for t in tasks)
        categories = Counter(t.category for t in tasks)
        print(f"{split}: {len(tasks)} tasks, {dict(counts)}")
        print(f"  categories: {dict(sorted(categories.items()))}")


if __name__ == "__main__":
    main()
