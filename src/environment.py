"""Simulator of one Jira Cloud project in memory: the board file, the operations and the difference of two states."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

# The values of the Jira Cloud site with the English language (docs/TASKS.md).
TYPES = ("Task", "Bug", "Story")
PRIORITIES = ("Highest", "High", "Medium", "Low", "Lowest")
SPRINT_STATES = ("closed", "active", "future")
# Status: (category, color in results, transition id). On this site the category of Cancelled is In Progress.
STATUSES = {
    "Backlog": ("To Do", "blue-gray", 11),
    "In Progress": ("In Progress", "yellow", 21),
    "In review": ("In Progress", "yellow", 31),
    "Cancelled": ("In Progress", "yellow", 41),
    "Done": ("Done", "green", 51),
}
TRANSITIONS = {tid: name for name, (_, _, tid) in STATUSES.items()}
STATUS_CATEGORIES = ("To Do", "In Progress", "Done")

# Jira time units: 1 week = 5 days, 1 day = 8 hours.
TIME_UNITS = {"w": 5 * 8 * 3600, "d": 8 * 3600, "h": 3600, "m": 60}
TIME_RE = re.compile(r"\s*(\d+)\s*([wdhm])\s*", re.IGNORECASE)
UNREADABLE_TIME_SECONDS = 60

POLISH = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")

NO_ISSUE = "Issue does not exist or you do not have permission to see it."


def fold(text: str) -> str:
    """Lower case without Polish letters. Real Jira compares person names in this way."""
    return " ".join(text.translate(POLISH).casefold().split())


def key_number(key: str) -> int:
    return int(key.rsplit("-", 1)[1])


class BoardError(ValueError):
    """An operation is not possible. The message is the message of real Jira."""


class Project(BaseModel):
    key: str
    name: str


class AgileBoard(BaseModel):
    id: str
    name: str
    type: Literal["scrum", "kanban", "simple"]


class Person(BaseModel):
    account_id: str
    display_name: str
    email: str
    active: bool


class Sprint(BaseModel):
    id: str
    name: str
    state: Literal["closed", "active", "future"]
    start_date: str | None
    end_date: str | None
    goal: str = ""


class Comment(BaseModel):
    id: str
    author: str
    body: str
    created: str


class Worklog(BaseModel):
    id: str
    author: str
    time_spent_seconds: int
    comment: str
    started: str


class Issue(BaseModel):
    id: str
    key: str
    summary: str
    description: str | None
    issue_type: Literal["Task", "Bug", "Story"]
    status: Literal["Backlog", "In Progress", "In review", "Done", "Cancelled"]
    priority: Literal["Highest", "High", "Medium", "Low", "Lowest"]
    assignee: str | None
    reporter: str | None
    labels: list[str] = Field(default_factory=list)
    sprint: str | None
    created: str
    updated: str
    comments: list[Comment] = Field(default_factory=list)
    worklogs: list[Worklog] = Field(default_factory=list)


class Board(BaseModel):
    name: str
    site: str
    now: str
    project: Project
    board: AgileBoard
    persons: list[Person]
    sprints: list[Sprint]
    issues: list[Issue]
    # Real Jira does not use the number of a deleted issue again. The contract test sets it.
    _last_number: int = PrivateAttr(default=0)

    def copy_board(self) -> "Board":
        return self.model_copy(deep=True)

    # Lookups

    @property
    def user(self) -> Person:
        """The account of the agent: the first active person. It is the author of new issues, comments and worklogs."""
        return next(p for p in self.persons if p.active)

    def person(self, account_id: str | None) -> Person | None:
        return next((p for p in self.persons if p.account_id == account_id), None)

    def display_name(self, account_id: str | None) -> str | None:
        p = self.person(account_id)
        return p.display_name if p else None

    def find_issue(self, key: str) -> Issue | None:
        key = str(key).strip().upper()
        return next((i for i in self.issues if i.key == key), None)

    def issue(self, key: str) -> Issue:
        issue = self.find_issue(key)
        if issue is None:
            raise BoardError(NO_ISSUE)
        return issue

    def sprint(self, sprint_id: str | None) -> Sprint | None:
        return next((s for s in self.sprints if s.id == str(sprint_id).strip()), None)

    def sprint_name(self, sprint_id: str | None) -> str | None:
        s = self.sprint(sprint_id)
        return s.name if s else None

    # Persons (D7)

    def find_person(self, value: str) -> Person | None:
        """Find an active person by the full display name, the e-mail or the account id."""
        value = str(value).strip()
        if value.lower().startswith("accountid:"):
            value = value.split(":", 1)[1]
        for p in self.persons:
            if p.active and (p.account_id == value or fold(p.display_name) == fold(value) or fold(p.email) == fold(value)):
                return p
        return None

    def search_persons(self, query: str) -> list[Person]:
        """Active persons with a word of the display name or the e-mail that starts with a word of the query.

        The server sends the query in the URL without encoding, so "+" is a space. The recording of "user+anna"
        found all six persons with "user" in the name, so one word of the query is sufficient.
        """
        full = fold(query)
        queries = [q for q in re.split(r"[\s+]+", full) if q]
        found = []
        for p in self.persons:
            name, email = fold(p.display_name), fold(p.email)
            words = re.split(r"[\s+.@_-]+", name) + re.split(r"[\s+.@_-]+", email)
            if p.active and queries and (name.startswith(full) or email.startswith(full)
                                         or any(w.startswith(q) for q in queries for w in words if w)):
                found.append(p)
        return found

    # Checks. Each check raises BoardError before a change, so a failed operation does not change the board.

    def check_type(self, value) -> str:
        name = value.get("name") if isinstance(value, dict) else value
        match = next((t for t in TYPES if isinstance(name, str) and t.lower() == name.strip().lower()), None)
        if match is None:
            raise BoardError("Specify a valid issue type")
        return match

    def check_priority(self, value) -> str:
        name = value.get("name") if isinstance(value, dict) else value
        match = next((p for p in PRIORITIES if isinstance(name, str) and p.lower() == name.strip().lower()), None)
        if match is None:
            raise BoardError("Specify the Priority (name) in the string format")
        return match

    def check_assignee(self, value) -> str | None:
        if value is None:
            return None
        if isinstance(value, dict):
            value = value.get("accountId") or value.get("account_id") or value.get("name") or value.get("emailAddress")
        person = self.find_person(str(value)) if value else None
        if person is None:
            raise BoardError(f"Could not update assignee: Could not find account ID for user: {value}")
        return person.account_id

    def check_sprint(self, sprint_id) -> Sprint:
        sprint = self.sprint(sprint_id)
        if sprint is None:
            raise BoardError("We could not find the sprint")
        if sprint.state == "closed":
            raise BoardError(f"Sprint with id {sprint.id} is closed. Issues cannot be added to a closed sprint.")
        return sprint

    @staticmethod
    def check_labels(labels) -> list[str]:
        if isinstance(labels, str):
            labels = [labels]
        if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels):
            raise BoardError("The labels field must be a list of texts.")
        clean = [x.strip() for x in labels]
        if any(not x or " " in x for x in clean):
            raise BoardError("The label must not contain spaces.")
        return list(dict.fromkeys(clean))

    # Clock and ids

    def _next_id(self, items) -> str:
        return str(max((int(x.id) for x in items), default=10000) + 1)

    def _next_issue(self) -> tuple[str, str]:
        number = max([key_number(i.key) for i in self.issues] + [self._last_number]) + 1
        self._last_number = number
        return self._next_id(self.issues), f"{self.project.key}-{number}"

    # Operations

    def create_issue(self, summary: str, issue_type, description: str | None = None, assignee: str | None = None,
                     priority=None, labels=None) -> Issue:
        """Create an issue. An unknown assignee gives no error: real Jira creates the issue without an assignee."""
        issue_type = self.check_type(issue_type)
        priority = self.check_priority(priority) if priority is not None else "Medium"
        labels = self.check_labels(labels) if labels is not None else []
        if not isinstance(summary, str) or not summary.strip():
            raise BoardError("You must specify a summary of the issue.")
        person = self.find_person(assignee) if assignee else None
        issue_id, key = self._next_issue()
        issue = Issue(
            id=issue_id, key=key, summary=summary.strip(), description=description or None,
            issue_type=issue_type, status="Backlog", priority=priority,
            assignee=person.account_id if person else None, reporter=self.user.account_id,
            labels=labels, sprint=None, created=self.now, updated=self.now,
        )
        self.issues.append(issue)
        return issue

    def update_fields(self, key: str, fields: dict) -> Issue:
        """Change the fields of an issue. The labels replace the old list. Unknown fields are ignored."""
        issue = self.issue(key)
        changes = {}
        for name, value in fields.items():
            if name == "summary":
                if not isinstance(value, str) or not value.strip():
                    raise BoardError("You must specify a summary of the issue.")
                changes["summary"] = value.strip()
            elif name == "description":
                changes["description"] = value or None
            elif name == "priority":
                changes["priority"] = self.check_priority(value)
            elif name == "assignee":
                changes["assignee"] = self.check_assignee(value)
            elif name == "labels":
                changes["labels"] = self.check_labels(value)
            elif name in ("issuetype", "issue_type"):
                changes["issue_type"] = self.check_type(value)
            elif name == "status":
                status = value.get("name") if isinstance(value, dict) else value
                match = next((s for s in STATUSES if isinstance(status, str) and s.lower() == status.strip().lower()), None)
                if match is None:
                    raise BoardError(f"Status '{status}' not found among the available transitions.")
                changes["status"] = match
        for name, value in changes.items():
            setattr(issue, name, value)
        if changes:
            issue.updated = self.now
        return issue

    def transition(self, key: str, transition_id) -> Issue:
        issue = self.issue(key)
        try:
            status = TRANSITIONS[int(str(transition_id).strip())]
        except (KeyError, ValueError):
            raise BoardError(f"Transition id '{transition_id}' is not valid for this issue.") from None
        issue.status = status
        issue.updated = self.now
        return issue

    def add_comment(self, key: str, body: str) -> Comment:
        issue = self.issue(key)
        if not isinstance(body, str) or not body.strip():
            raise BoardError("Comment body can not be empty!")
        comment = Comment(id=self._next_id([c for i in self.issues for c in i.comments]),
                          author=self.user.account_id, body=body, created=self.now)
        issue.comments.append(comment)
        issue.updated = self.now
        return comment

    def add_worklog(self, key: str, time_spent: str, comment: str | None = None) -> Worklog:
        issue = self.issue(key)
        worklog = Worklog(id=self._next_id([w for i in self.issues for w in i.worklogs]),
                          author=self.user.account_id, time_spent_seconds=parse_time(time_spent),
                          comment=comment or "", started=self.now)
        issue.worklogs.append(worklog)
        issue.updated = self.now
        return worklog

    def add_to_sprint(self, sprint_id, keys: list[str]) -> list[Issue]:
        sprint = self.check_sprint(sprint_id)
        issues = [self.issue(k) for k in keys]
        for issue in issues:
            issue.sprint = sprint.id
            issue.updated = self.now
        return issues

    def move_to_backlog(self, keys: list[str]) -> list[Issue]:
        issues = [self.issue(k) for k in keys]
        for issue in issues:
            issue.sprint = None
            issue.updated = self.now
        return issues


# Time of a worklog

def parse_time(text) -> int:
    """Seconds of a Jira time such as '1h 30m'. Real Jira logs one minute for a text that it cannot read."""
    text = str(text or "")
    parts = TIME_RE.findall(text)
    if not parts or TIME_RE.sub("", text).strip():
        return UNREADABLE_TIME_SECONDS
    seconds = sum(int(n) * TIME_UNITS[u.lower()] for n, u in parts)
    return seconds or UNREADABLE_TIME_SECONDS


def format_time(seconds: int) -> str:
    parts = []
    for unit, size in TIME_UNITS.items():
        n, seconds = divmod(seconds, size)
        if n:
            parts.append(f"{n}{unit}")
    return " ".join(parts) or "0m"


def parse_date(text: str) -> datetime:
    return datetime.strptime(text.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S.%f%z")


# Difference of two states (D9)

FIELDS = ("summary", "description", "issue_type", "status", "priority", "assignee", "labels", "sprint")


def _field_value(board: Board, issue: Issue, field: str):
    value = getattr(issue, field)
    if field in ("assignee", "reporter"):
        return board.display_name(value)
    if field == "sprint":
        return board.sprint_name(value)
    return value


def diff(initial: Board, final: Board) -> list[dict]:
    """List the changes from `initial` to `final` in the format of the changes in `expected.json`."""
    old = {i.key: i for i in initial.issues}
    changes = []
    for issue in sorted(final.issues, key=lambda i: key_number(i.key)):
        prev = old.get(issue.key)
        if prev is None:
            new = {f: _field_value(final, issue, f) for f in FIELDS}
            new["comments"] = [c.body for c in issue.comments]
            changes.append({"new_issue": new})
            prev_comments, prev_worklogs = {c.id for c in issue.comments}, set()
        else:
            for field in FIELDS:
                a, b = _field_value(initial, prev, field), _field_value(final, issue, field)
                if a != b:
                    changes.append({"issue": issue.key, "field": field, "value": b})
            prev_comments, prev_worklogs = {c.id for c in prev.comments}, {w.id for w in prev.worklogs}
        changes += [{"issue": issue.key, "comment": c.body} for c in issue.comments if c.id not in prev_comments]
        changes += [{"issue": issue.key, "worklog": {"seconds": w.time_spent_seconds, "comment": w.comment}}
                    for w in issue.worklogs if w.id not in prev_worklogs]
    return changes


# Save and load

def save_board(board: Board, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(board.model_dump(), ensure_ascii=False, indent=2) + "\n")


def load_board(path: Path) -> Board:
    return Board.model_validate_json(Path(path).read_text(encoding="utf-8"))
