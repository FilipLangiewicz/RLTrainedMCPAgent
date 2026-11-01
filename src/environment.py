"""Simulator of a project management system: one board in memory."""

import json
import random
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

TYPES = ("bug", "task", "story")
STATUSES = ("to_do", "in_progress", "done")
PRIORITIES = ("low", "medium", "high", "critical")
SPRINT_STATES = ("closed", "active", "future")
LABELS = ("frontend", "backend", "api", "ui", "database", "security", "docs", "performance")

# The test boards use the first 5 keys, the train boards use the next 20 keys.
PROJECT_KEYS = (
    "WEB", "APP", "API", "SHOP", "CRM",
    "ERP", "HR", "PAY", "CMS", "BI", "DOC", "OPS", "LOG", "MAIL", "CHAT",
    "MAP", "GAME", "EDU", "BANK", "CAR", "FOOD", "TRIP", "CLUB", "NEWS", "CARE",
)

# Invented persons: the first name, the gender, and the Polish forms that the
# instructions use: nominative, genitive, dative, accusative, instrumental.
FIRST_NAMES = {
    "Anna": ("f", "Ania", "Ani", "Ani", "Anię", "Anią"),
    "Katarzyna": ("f", "Kasia", "Kasi", "Kasi", "Kasię", "Kasią"),
    "Magdalena": ("f", "Magda", "Magdy", "Magdzie", "Magdę", "Magdą"),
    "Agnieszka": ("f", "Agnieszka", "Agnieszki", "Agnieszce", "Agnieszkę", "Agnieszką"),
    "Zofia": ("f", "Zosia", "Zosi", "Zosi", "Zosię", "Zosią"),
    "Ewa": ("f", "Ewa", "Ewy", "Ewie", "Ewę", "Ewą"),
    "Marta": ("f", "Marta", "Marty", "Marcie", "Martę", "Martą"),
    "Joanna": ("f", "Asia", "Asi", "Asi", "Asię", "Asią"),
    "Piotr": ("m", "Piotrek", "Piotrka", "Piotrkowi", "Piotrka", "Piotrkiem"),
    "Tomasz": ("m", "Tomek", "Tomka", "Tomkowi", "Tomka", "Tomkiem"),
    "Michał": ("m", "Michał", "Michała", "Michałowi", "Michała", "Michałem"),
    "Krzysztof": ("m", "Krzysiek", "Krzyśka", "Krzyśkowi", "Krzyśka", "Krzyśkiem"),
    "Paweł": ("m", "Paweł", "Pawła", "Pawłowi", "Pawła", "Pawłem"),
    "Marek": ("m", "Marek", "Marka", "Markowi", "Marka", "Markiem"),
    "Jakub": ("m", "Kuba", "Kuby", "Kubie", "Kubę", "Kubą"),
    "Łukasz": ("m", "Łukasz", "Łukasza", "Łukaszowi", "Łukasza", "Łukaszem"),
}
CASES = ("nom", "gen", "dat", "acc", "ins")
SURNAMES = (  # (male, female)
    ("Kowalski", "Kowalska"), ("Wiśniewski", "Wiśniewska"), ("Zieliński", "Zielińska"),
    ("Lewandowski", "Lewandowska"), ("Kamiński", "Kamińska"), ("Dąbrowski", "Dąbrowska"),
    ("Nowak", "Nowak"), ("Kowalczyk", "Kowalczyk"), ("Wójcik", "Wójcik"),
    ("Mazur", "Mazur"), ("Krawczyk", "Krawczyk"), ("Sikora", "Sikora"),
)

TITLE_TEMPLATES = {
    "bug": (
        "Błąd walidacji {}", "Awaria {} po wdrożeniu", "Wolne ładowanie {}",
        "Niepoprawne wyświetlanie {}", "Brak tłumaczeń {}",
    ),
    "task": (
        "Refaktoryzacja {}", "Dodanie testów {}", "Aktualizacja dokumentacji {}",
        "Optymalizacja zapytań {}", "Migracja {} do nowej wersji",
    ),
    "story": (
        "Nowy widok {}", "Eksport {} do CSV", "Personalizacja {}",
        "Uproszczenie {}", "Wersja mobilna {}",
    ),
}
TITLE_OBJECTS = (  # genitive case
    "formularza logowania", "koszyka", "panelu administratora", "wyszukiwarki",
    "raportu sprzedaży", "profilu użytkownika", "listy zamówień", "strony głównej",
    "modułu płatności", "rejestracji konta", "powiadomień", "kalendarza",
    "historii zamówień", "ustawień konta", "katalogu produktów",
)
DESCRIPTIONS = (
    "Zgłoszenie z przeglądu sprintu.",
    "Problem zgłosił zespół wsparcia.",
    "Szczegóły są w notatkach ze spotkania.",
    "Do ustalenia zakres z właścicielem produktu.",
    "Prośba od klienta.",
)
COMMENTS = (
    "Sprawdzę to jutro.",
    "Mamy logi z produkcji.",
    "Potrzebny dostęp do środowiska testowego.",
    "Zależy od zmian w API.",
    "Omówione na daily.",
)


class BoardError(ValueError):
    """An operation is not possible. The message tells the cause."""


class Person(BaseModel):
    id: str
    name: str


class Sprint(BaseModel):
    id: str
    name: str
    state: Literal["closed", "active", "future"]


class Comment(BaseModel):
    text: str


class Issue(BaseModel):
    key: str
    title: str
    description: str = ""
    type: Literal["bug", "task", "story"]
    status: Literal["to_do", "in_progress", "done"] = "to_do"
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    assignee: str | None = None
    labels: list[str] = Field(default_factory=list)
    sprint: str | None = None
    comments: list[Comment] = Field(default_factory=list)

    def short(self) -> dict:
        return self.model_dump(include={"key", "title", "type", "status", "priority", "assignee", "labels", "sprint"})


def key_number(key: str) -> int:
    return int(key.rsplit("-", 1)[1])


class Board(BaseModel):
    name: str
    project: str
    persons: list[Person]
    sprints: list[Sprint]
    issues: list[Issue]

    def copy_board(self) -> "Board":
        return self.model_copy(deep=True)

    def person(self, person_id: str) -> Person:
        for p in self.persons:
            if p.id == person_id:
                return p
        raise BoardError(f"Unknown person '{person_id}'. Known person ids: {', '.join(p.id for p in self.persons)}.")

    def sprint(self, sprint_id: str) -> Sprint:
        for s in self.sprints:
            if s.id == sprint_id:
                return s
        raise BoardError(f"Unknown sprint '{sprint_id}'. Known sprint ids: {', '.join(s.id for s in self.sprints)}.")

    def issue(self, key: str) -> Issue:
        for i in self.issues:
            if i.key == key:
                return i
        raise BoardError(f"Issue '{key}' does not exist.")

    def active_sprint(self) -> Sprint:
        return next(s for s in self.sprints if s.state == "active")

    def next_sprint(self) -> Sprint:
        return min((s for s in self.sprints if s.state == "future"), key=lambda s: int(s.id[1:]))

    # Validation. Each check raises BoardError before a change, so a failed operation does not change the board.

    def _check(self, field: str, value: str | None) -> None:
        allowed = {"type": TYPES, "status": STATUSES, "priority": PRIORITIES}
        if field in allowed:
            if value not in allowed[field]:
                raise BoardError(f"Value '{value}' is not allowed for {field}. Allowed values: {', '.join(allowed[field])}.")
        elif field == "assignee":
            if value is not None:
                self.person(value)
        elif field == "sprint":
            if value is not None and self.sprint(value).state == "closed":
                raise BoardError(f"Sprint '{value}' is closed. Use an active or a future sprint.")
        elif field == "title" and (not value or not value.strip()):
            raise BoardError("The title must not be empty.")

    @staticmethod
    def _clean_labels(labels: list[str]) -> list[str]:
        clean = [label.strip() for label in labels]
        if any(not label or " " in label for label in clean):
            raise BoardError("A label must be one word without spaces.")
        return clean

    # Operations

    def search(
        self,
        status: str | None = None,
        assignee: str | None = None,
        label: str | None = None,
        type: str | None = None,
        priority: str | None = None,
        sprint: str | None = None,
        text: str | None = None,
    ) -> list[Issue]:
        for field, value in (("status", status), ("type", type), ("priority", priority)):
            if value is not None:
                self._check(field, value)
        if assignee not in (None, "unassigned"):
            self.person(assignee)
        if sprint not in (None, "backlog"):
            self.sprint(sprint)
        found = []
        for i in self.issues:
            if status is not None and i.status != status:
                continue
            if type is not None and i.type != type:
                continue
            if priority is not None and i.priority != priority:
                continue
            if label is not None and label not in i.labels:
                continue
            if assignee is not None and i.assignee != (None if assignee == "unassigned" else assignee):
                continue
            if sprint is not None and i.sprint != (None if sprint == "backlog" else sprint):
                continue
            if text is not None and text.lower() not in i.title.lower():
                continue
            found.append(i)
        return sorted(found, key=lambda i: key_number(i.key))

    def create_issue(
        self,
        title: str,
        type: str,
        description: str = "",
        priority: str = "medium",
        assignee: str | None = None,
        labels: list[str] | None = None,
        sprint: str | None = None,
    ) -> Issue:
        for field, value in (("title", title), ("type", type), ("priority", priority),
                             ("assignee", assignee), ("sprint", sprint)):
            self._check(field, value)
        number = max((key_number(i.key) for i in self.issues), default=0) + 1
        issue = Issue(
            key=f"{self.project}-{number}",
            title=title.strip(),
            description=description,
            type=type,
            priority=priority,
            assignee=assignee,
            labels=sorted(set(self._clean_labels(labels or []))),
            sprint=sprint,
        )
        self.issues.append(issue)
        return issue

    def update_issue(self, key: str, add_labels: list[str] | None = None,
                     remove_labels: list[str] | None = None, **fields) -> Issue:
        """Change the fields of an issue. `fields` can have: title, description, type, status, priority, assignee, sprint."""
        issue = self.issue(key)
        allowed = {"title", "description", "type", "status", "priority", "assignee", "sprint"}
        unknown = set(fields) - allowed
        if unknown:
            raise BoardError(f"Unknown fields: {', '.join(sorted(unknown))}.")
        if not fields and not add_labels and not remove_labels:
            raise BoardError("Give at least one field to change.")
        for field, value in fields.items():
            self._check(field, value)
        add = self._clean_labels(add_labels or [])
        remove = self._clean_labels(remove_labels or [])
        for field, value in fields.items():
            setattr(issue, field, value.strip() if field == "title" else value)
        issue.labels = sorted((set(issue.labels) | set(add)) - set(remove))
        return issue

    def add_comment(self, key: str, text: str) -> Issue:
        issue = self.issue(key)
        if not text or not text.strip():
            raise BoardError("The comment text must not be empty.")
        issue.comments.append(Comment(text=text.strip()))
        return issue


# Difference of two states

FIELDS = ("title", "description", "type", "status", "priority", "assignee", "labels", "sprint")


def _entry_order(entry: dict) -> tuple:
    if entry["op"] == "create":
        return (1, 0, "", json.dumps(entry, ensure_ascii=False, sort_keys=True))
    return (0, key_number(entry["key"]), entry["op"] + entry.get("field", ""),
            json.dumps(entry, ensure_ascii=False, sort_keys=True))


def sort_changes(changes: list[dict]) -> list[dict]:
    return sorted(changes, key=_entry_order)


def diff(before: Board, after: Board) -> list[dict]:
    """List the changes from `before` to `after` in the format of design.md."""
    old = {i.key: i for i in before.issues}
    changes = []
    for issue in after.issues:
        prev = old.get(issue.key)
        if prev is None:
            fields = issue.model_dump(include=set(FIELDS))
            fields["labels"] = sorted(fields["labels"])
            fields["comments"] = [c.text for c in issue.comments]
            changes.append({"op": "create", "fields": fields})
            continue
        for field in FIELDS:
            a, b = getattr(prev, field), getattr(issue, field)
            if field == "labels":
                a, b = sorted(a), sorted(b)
            if a != b:
                changes.append({"op": "update", "key": issue.key, "field": field, "value": b})
        for c in issue.comments[len(prev.comments):]:
            changes.append({"op": "comment", "key": issue.key, "text": c.text})
    return sort_changes(changes)


# Save and load

def save_board(board: Board, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(board.model_dump(), ensure_ascii=False, indent=2) + "\n")


def load_board(path: Path) -> Board:
    return Board.model_validate_json(Path(path).read_text(encoding="utf-8"))


# Generator

def name_forms(person: Person) -> dict:
    """Return the gender and the Polish case forms of the first name of a person."""
    gender, *forms = FIRST_NAMES[person.name.split()[0]]
    return {"gender": gender, **dict(zip(CASES, forms))}


def generate_board(name: str, project: str, seed: int, n_persons: int = 6,
                   n_sprints: int = 4, n_issues: tuple[int, int] = (30, 40)) -> Board:
    rng = random.Random(f"{seed}-{name}-{project}")
    first_names = rng.sample(sorted(FIRST_NAMES), n_persons)
    persons = []
    for idx, first in enumerate(first_names, start=1):
        male, female = rng.choice(SURNAMES)
        last = male if FIRST_NAMES[first][0] == "m" else female
        persons.append(Person(id=f"u{idx}", name=f"{first} {last}"))

    states = ["closed", "active"] + ["future"] * (n_sprints - 2)
    sprints = [Sprint(id=f"s{n}", name=f"Sprint {n}", state=state) for n, state in enumerate(states, start=1)]
    closed = [s.id for s in sprints if s.state == "closed"]
    active = [s.id for s in sprints if s.state == "active"]
    future = [s.id for s in sprints if s.state == "future"]

    count = rng.randint(*n_issues)
    titles = set()
    issues = []
    while len(issues) < count:
        type_ = rng.choices(TYPES, weights=(40, 40, 20))[0]
        title = rng.choice(TITLE_TEMPLATES[type_]).format(rng.choice(TITLE_OBJECTS))
        if title in titles:
            continue
        titles.add(title)
        place = rng.choices(("closed", "active", "future", "backlog"), weights=(20, 35, 20, 25))[0]
        if place == "closed":
            sprint, status = rng.choice(closed), "done"
        elif place == "active":
            sprint, status = active[0], rng.choices(STATUSES, weights=(40, 35, 25))[0]
        elif place == "future":
            sprint, status = rng.choice(future), "to_do"
        else:
            sprint, status = None, rng.choices(("to_do", "in_progress"), weights=(85, 15))[0]
        priority_weights = (15, 35, 35, 15) if type_ == "bug" else (25, 45, 22, 8)
        issues.append(Issue(
            key=f"{project}-{len(issues) + 1}",
            title=title,
            description=rng.choice(DESCRIPTIONS),
            type=type_,
            status=status,
            priority=rng.choices(PRIORITIES, weights=priority_weights)[0],
            assignee=None if rng.random() < 0.25 else rng.choice(persons).id,
            labels=sorted(rng.sample(LABELS, rng.choices((0, 1, 2), weights=(20, 50, 30))[0])),
            sprint=sprint,
            comments=[Comment(text=t) for t in rng.sample(COMMENTS, rng.choices((0, 1, 2), weights=(60, 30, 10))[0])],
        ))
    return Board(name=name, project=project, persons=persons, sprints=sprints, issues=issues)
