"""Generator of the train and validation boards from the hand-written content of a company (data/companies/*.json).

The content gives the persons, the sprint goals and the issues. The generator adds the ids, the account ids,
the e-mail addresses, the dates, the sprints and the assignees, and it checks the rules of docs/TASKS.md.
Run: python -m src.boards
"""

import json
import random
import sys
import unicodedata
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from src.environment import POLISH, STATUSES, Board, load_board, save_board

ROOT = Path(__file__).resolve().parent.parent
COMPANIES = ROOT / "data" / "companies"
ENVIRONMENTS = ROOT / "data" / "environments"

SITE = "https://example.atlassian.net"
SPRINT_SLOTS = ("closed", "active", "next", "later")
# The status of an issue must agree with the state of its sprint.
ALLOWED = {
    "closed": {"Done", "Cancelled"},
    "active": set(STATUSES),
    "next": {"Backlog"},
    "later": {"Backlog"},
    None: {"Backlog"},
}
WORKING = {"In Progress", "In review", "Done"}
ACCOUNT_NS = uuid.UUID("6f1c2a52-4b7e-4c1e-9d8a-2f0b6c1e7a10")


def _jira_time(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S.000+0100")


def _sprint_time(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _email(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name.translate(POLISH)).encode("ascii", "ignore").decode()
    return ".".join(ascii_name.casefold().replace("'", "").split()) + "@example.com"


def _account_id(company: str, name: str) -> str:
    return "712020:" + str(uuid.uuid5(ACCOUNT_NS, f"{company}/{name}"))


def build_board(company: dict, spec: dict, board_id: int, seed: int) -> Board:
    """Build one board from the content `spec` of one project of `company`."""
    rng = random.Random(f"{seed}/{spec['key']}")
    now = datetime.fromisoformat(company["now"]).replace(tzinfo=None)
    active_start = datetime(now.year, now.month, now.day, 9) - timedelta(days=7)

    persons = [{"account_id": _account_id(company["name"], name), "display_name": name,
                "email": _email(name), "active": active} for name, active in spec["persons"]]
    by_name = {p["display_name"]: p["account_id"] for p in persons}
    active_ids = [p["account_id"] for p in persons if p["active"]]
    inactive_ids = [p["account_id"] for p in persons if not p["active"]]

    first = spec["first_sprint"]
    sprint_ids = {slot: str(board_id * 10 + n + 1) for n, slot in enumerate(SPRINT_SLOTS)}
    starts = {"closed": active_start - timedelta(days=14), "active": active_start}
    sprints = [{"id": sprint_ids[slot], "name": f"{spec['key']} Sprint {first + n}", "state": slot if slot in ("closed", "active") else "future",
                "start_date": _sprint_time(starts[slot]) if slot in starts else None,
                "end_date": _sprint_time(starts[slot] + timedelta(days=14)) if slot in starts else None,
                "goal": goal} for n, (slot, goal) in enumerate(zip(SPRINT_SLOTS, spec["sprint_goals"]))]

    rows = spec["issues"]
    span = timedelta(days=61)
    issues = []
    for n, row in enumerate(rows, start=1):
        status, slot = row.get("status", "Backlog"), row.get("sprint")
        if status not in ALLOWED[slot]:
            raise ValueError(f"{spec['key']}-{n}: status {status} is not allowed in the sprint {slot}")
        issue_id = board_id * 1000 + n
        created = active_start - timedelta(days=1) - span * (len(rows) - n) / (len(rows) - 1)
        created = created.replace(hour=rng.randint(8, 17), minute=rng.choice((0, 15, 30, 45)), second=0, microsecond=0)
        if "assignee" in row:
            assignee = by_name[row["assignee"]] if row["assignee"] else None
        elif status == "Cancelled" or (status not in WORKING and rng.random() < 0.5):
            assignee = None
        else:
            assignee = rng.choice(active_ids)
        reporter = by_name[row["reporter"]] if "reporter" in row else rng.choice(active_ids)
        comments = [{"id": str(issue_id * 10 + k + 1), "author": assignee or reporter, "body": body,
                     "created": _jira_time(created + timedelta(days=k + 1))} for k, body in enumerate(row.get("comments", []))]
        worklogs = [{"id": str(issue_id * 10 + 5 + k), "author": assignee or rng.choice(active_ids),
                     "time_spent_seconds": int(hours * 3600), "comment": text,
                     "started": _jira_time((created + timedelta(days=k + 2)).replace(hour=0))}
                    for k, (hours, text) in enumerate(row.get("worklogs", []))]
        issues.append({"id": str(issue_id), "key": f"{spec['key']}-{n}", "summary": row["summary"],
                       "description": row.get("description"), "issue_type": row.get("type", "Task"), "status": status,
                       "priority": row.get("priority", "Medium"), "assignee": assignee, "reporter": reporter,
                       "labels": row.get("labels", []), "sprint": sprint_ids[slot] if slot else None,
                       "created": _jira_time(created), "updated": _jira_time(created + timedelta(days=3)),
                       "comments": comments, "worklogs": worklogs})

    # The former employee keeps one old issue, as on the test boards.
    old = [i for i in issues if i["status"] == "Done" and "assignee" not in rows[int(i["key"].rsplit("-", 1)[1]) - 1]]
    if inactive_ids and old:
        rng.choice(old)["assignee"] = inactive_ids[0]

    return Board.model_validate({
        "name": f"{company['split']}-{spec['key'].lower()}", "site": SITE, "now": company["now"],
        "project": {"key": spec["key"], "name": f"{company['name']} - {spec['name']}"},
        "board": {"id": str(board_id), "name": f"{spec['key']} board", "type": "scrum"},
        "persons": persons, "sprints": sprints, "issues": issues,
    })


def check_board(board: Board) -> list[str]:
    """The traps of each board (docs/TASKS.md). The result lists the rules that the board breaks."""
    errors = []
    if not board.persons[0].active:
        errors.append("the first person is the account of the agent and must be active")
    if not any(not p.active for p in board.persons):
        errors.append("no person is inactive")
    first_names = [p.display_name.split()[0] for p in board.persons if p.active]
    if len(first_names) == len(set(first_names)):
        errors.append("no two active persons have the same first name")
    if sum(i.status == "Cancelled" for i in board.issues) != 1:
        errors.append("the board must have exactly one Cancelled issue")
    polish = [any(c in i.summary for c in "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ") for i in board.issues]
    if all(polish) or not any(polish):
        errors.append("the summaries must be in Polish and in English")
    if len({i.summary for i in board.issues}) != len(board.issues):
        errors.append("two issues have the same summary")
    return [f"{board.name}: {e}" for e in errors]


def build_all(seed: int = 2026) -> list[Board]:
    """Build the boards of all companies. Stop if a rule fails or if a board repeats a name or a summary of another board."""
    boards, errors = [], []
    for path in sorted(COMPANIES.glob("*.json")):
        company = json.loads(path.read_text(encoding="utf-8"))
        # A fixed first id keeps the ids of a company when a new company file comes before it.
        for n, spec in enumerate(company["boards"]):
            boards.append(build_board(company, spec, company["first_board_id"] + n, seed))
    test = [load_board(p) for p in sorted(ENVIRONMENTS.glob("test-*.json"))]
    ids = [b.board.id for b in test + boards]
    if len(ids) != len(set(ids)):
        raise ValueError(f"two boards have the same board id: {sorted(ids)}")
    seen_keys, seen_summaries, seen_names = {}, {}, {}
    for b in test + boards:
        errors += check_board(b) if b not in test else []
        for value, seen in ((b.project.key, seen_keys), *((i.summary.casefold(), seen_summaries) for i in b.issues),
                            *((p.display_name, seen_names) for p in b.persons)):
            if value in seen and seen[value] != b.name:
                errors.append(f"{b.name}: '{value}' is also on {seen[value]}")
            seen.setdefault(value, b.name)
    if errors:
        raise ValueError("\n".join(errors))
    return boards


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    for board in build_all(seed):
        save_board(board, ENVIRONMENTS / f"{board.name}.json")
        print(f"{board.name}: {len(board.issues)} issues, {len(board.persons)} persons")


if __name__ == "__main__":
    main()
