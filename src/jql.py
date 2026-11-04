"""A subset of JQL with the semantics of the Jira Cloud site (design D8)."""

import re
from dataclasses import dataclass

from src.environment import PRIORITIES, STATUSES, Board, Issue, fold, key_number

UNBOUNDED = "Unbounded JQL queries are not allowed here. Please add a search restriction to your query."

FIELD_NAMES = {
    "project": "project", "key": "key", "issuekey": "key", "id": "key",
    "status": "status", "statuscategory": "statusCategory",
    "type": "type", "issuetype": "type", "priority": "priority",
    "assignee": "assignee", "reporter": "reporter", "labels": "labels", "label": "labels",
    "sprint": "sprint", "summary": "summary", "description": "description", "text": "text", "comment": "comment",
}
TEXT_FIELDS = ("summary", "description", "text", "comment")
ORDER_FIELDS = {"key": "key", "issuekey": "key", "created": "created", "updated": "updated",
                "priority": "priority", "status": "status"}
SPRINT_FUNCTIONS = {"opensprints": "active", "closedsprints": "closed", "futuresprints": "future"}
KEYWORDS = {"AND", "OR", "NOT", "IN", "IS", "EMPTY", "NULL", "ORDER", "BY", "ASC", "DESC"}

TOKEN_RE = re.compile(r"""
    \s*(?:
      (?P<string>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')
    | (?P<op>!=|!~|>=|<=|=|~|>|<)
    | (?P<punct>[(),])
    | (?P<word>[^\s"'(),=!~<>]+)
    )""", re.VERBOSE)
WORD_RE = re.compile(r"\w+")


class JQLError(ValueError):
    pass


def _error(text: str) -> JQLError:
    return JQLError(f"Error in JQL Query: {text}")


@dataclass
class Token:
    kind: str  # string, op, punct, word, end
    text: str

    @property
    def upper(self) -> str:
        return self.text.upper() if self.kind == "word" else ""


def tokenize(jql: str) -> list[Token]:
    tokens, pos = [], 0
    jql = jql.rstrip()
    while pos < len(jql):
        m = TOKEN_RE.match(jql, pos)
        if not m or m.end() == pos:
            raise _error(f"The character '{jql[pos]}' is a reserved JQL character. (line 1, character {pos + 1})")
        kind = m.lastgroup
        text = m.group(kind)
        if kind == "string":
            text = re.sub(r"\\(.)", r"\1", text[1:-1])
        tokens.append(Token(kind, text))
        pos = m.end()
    tokens.append(Token("end", ""))
    return tokens


# Syntax tree: ("and", [nodes]), ("or", [nodes]), ("not", node), ("clause", field, op, value)
# A value is ("text", str), ("list", [values]), ("func", name) or ("empty",).

class Parser:
    def __init__(self, jql: str):
        self.tokens = tokenize(jql)
        self.pos = 0

    @property
    def tok(self) -> Token:
        return self.tokens[self.pos]

    def take(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def parse(self):
        where = None
        if not (self.tok.kind == "end" or self.tok.upper == "ORDER"):
            where = self.or_expr()
        order = []
        if self.tok.upper == "ORDER":
            self.take()
            if self.take().upper != "BY":
                raise _error("Expecting 'BY' after 'ORDER'.")
            order = self.order_list()
        if self.tok.kind != "end":
            raise _error(f"Expecting either 'OR' or 'AND' but got '{self.tok.text}'.")
        return where, order

    def or_expr(self):
        nodes = [self.and_expr()]
        while self.tok.upper == "OR":
            self.take()
            nodes.append(self.and_expr())
        return nodes[0] if len(nodes) == 1 else ("or", nodes)

    def and_expr(self):
        nodes = [self.not_expr()]
        while self.tok.upper == "AND":
            self.take()
            nodes.append(self.not_expr())
        return nodes[0] if len(nodes) == 1 else ("and", nodes)

    def not_expr(self):
        if self.tok.upper == "NOT" or (self.tok.kind == "op" and self.tok.text == "!"):
            self.take()
            return ("not", self.not_expr())
        if self.tok.text == "(" and self.tok.kind == "punct":
            self.take()
            node = self.or_expr()
            if self.take().text != ")":
                raise _error("Expecting ')' before the end of the query.")
            return node
        return self.clause()

    def clause(self):
        tok = self.take()
        if tok.kind == "end":
            raise _error("Expecting a field name before the end of the query.")
        if tok.kind not in ("word", "string") or tok.upper in KEYWORDS:
            raise _error(f"Expecting a field name but got '{tok.text}'.")
        field = FIELD_NAMES.get(tok.text.lower().replace(" ", ""))
        if field is None:
            raise _error(f"Field '{tok.text}' does not exist or you do not have permission to view it.")
        op = self.operator()
        if op in ("is", "is not"):
            value = self.take()
            if value.upper not in ("EMPTY", "NULL"):
                raise _error("Expecting 'EMPTY' or 'NULL' after the 'IS' operator.")
            return ("clause", field, op, ("empty",))
        if op in ("in", "not in"):
            return ("clause", field, op, self.value_list())
        if op in (">", "<", ">=", "<="):
            raise _error(f"The operator '{op}' is not supported by the '{tok.text}' field.")
        return ("clause", field, op, self.value())

    def operator(self) -> str:
        tok = self.take()
        if tok.kind == "op":
            return tok.text
        if tok.upper == "IN":
            return "in"
        if tok.upper == "IS":
            if self.tok.upper == "NOT":
                self.take()
                return "is not"
            return "is"
        if tok.upper == "NOT" and self.tok.upper == "IN":
            self.take()
            return "not in"
        if tok.kind == "end":
            raise _error("Expecting operator before the end of the query.")
        raise _error(f"Expecting operator but got '{tok.text}'.")

    def value(self):
        tok = self.take()
        if tok.kind == "end":
            raise _error("Expecting either a value, list or function before the end of the query.")
        if tok.kind == "string":
            return ("text", tok.text)
        if tok.kind != "word" or tok.upper in KEYWORDS - {"EMPTY", "NULL"}:
            raise _error(f"Expecting either a value, list or function but got '{tok.text}'.")
        if tok.upper in ("EMPTY", "NULL"):
            return ("empty",)
        if self.tok.text == "(" and self.tok.kind == "punct":
            self.take()
            if self.take().text != ")":
                raise _error(f"The function '{tok.text}' does not take arguments.")
            return ("func", tok.text.lower())
        return ("text", tok.text)

    def value_list(self):
        if self.tok.text != "(":
            value = self.value()  # a function, for example "sprint in openSprints()"
            if value[0] != "func":
                raise _error("Expecting a list or a function after the 'IN' operator.")
            return ("list", [value])
        self.take()
        values = [self.value()]
        while self.tok.text == ",":
            self.take()
            values.append(self.value())
        if self.take().text != ")":
            raise _error("Expecting ')' before the end of the query.")
        return ("list", values)

    def order_list(self):
        order = []
        while True:
            tok = self.take()
            field = ORDER_FIELDS.get(tok.text.lower())
            if tok.kind not in ("word", "string") or field is None:
                raise _error(f"Field '{tok.text}' does not exist or you do not have permission to view it.")
            desc = False
            if self.tok.upper in ("ASC", "DESC"):
                desc = self.take().upper == "DESC"
            order.append((field, desc))
            if self.tok.text != ",":
                return order
            self.take()


# Evaluation

def _words(text: str) -> list[str]:
    return WORD_RE.findall(text.casefold())


def _contains_words(text: str, value: str) -> bool:
    """Each word of the value is a whole word of the text. A word with '*' at the end is a prefix."""
    words = set(_words(text))
    for part in value.casefold().split():
        if part.endswith("*") and _words(part[:-1]):
            prefix = _words(part[:-1])[0]
            if not any(w.startswith(prefix) for w in words):
                return False
        elif not all(w in words for w in _words(part)):
            return False
    return bool(_words(value))


def _person_matches(board: Board, account_id: str | None, value: str) -> bool:
    person = board.person(account_id)
    if person is None:
        return False
    if value.lower() == "currentuser()":
        return person.account_id == board.user.account_id
    v = fold(value)
    return person.account_id == value or fold(person.display_name) == v or fold(person.email) == v


def _field_values(board: Board, issue: Issue, field: str) -> list:
    """The values of a field for `=`. An empty list means that the field is empty."""
    if field == "project":
        return [board.project.key, board.project.name]
    if field == "status":
        return [issue.status]
    if field == "statusCategory":
        return [STATUSES[issue.status][0]]
    if field == "type":
        return [issue.issue_type]
    if field == "priority":
        return [issue.priority]
    if field in ("assignee", "reporter"):
        return [getattr(issue, field)] if getattr(issue, field) else []
    if field == "labels":
        return list(issue.labels)
    if field == "sprint":
        return [issue.sprint] if issue.sprint else []
    if field == "key":
        return [issue.key]
    if field == "summary":
        return [issue.summary]
    if field == "description":
        return [issue.description] if issue.description else []
    if field == "comment":
        return [c.body for c in issue.comments]
    if field == "text":
        return [issue.summary, issue.description or ""] + [c.body for c in issue.comments]
    raise AssertionError(field)


def _equal(board: Board, field: str, actual, value) -> bool:
    kind = value[0]
    if field == "sprint":
        sprint = board.sprint(actual)
        if kind == "func":
            return sprint is not None and sprint.state == SPRINT_FUNCTIONS.get(value[1].lower())
        return sprint is not None and (sprint.id == value[1].strip() or fold(sprint.name) == fold(value[1]))
    if kind == "func":
        if field in ("assignee", "reporter"):
            return _person_matches(board, actual, value[1] + "()")
        return False
    if field in ("assignee", "reporter"):
        return _person_matches(board, actual, value[1])
    return str(actual).casefold() == value[1].strip().casefold()


def _check_value(field: str, value, raw_field: str):
    if value[0] == "func":
        name = value[1].lower()
        allowed = {"sprint": SPRINT_FUNCTIONS, "assignee": {"currentuser"}, "reporter": {"currentuser"}}
        if name not in allowed.get(field, ()):
            raise _error(f"Unable to find JQL function '{value[1]}()'.")
    if value[0] == "list":
        for v in value[1]:
            _check_value(field, v, raw_field)


def _clause(board: Board, issue: Issue, field: str, op: str, value) -> bool:
    values = _field_values(board, issue, field)
    if op in ("is", "is not"):
        return (not values) == (op == "is")
    if field in TEXT_FIELDS:
        if op not in ("~", "!~"):
            raise _error(f"The operator '{op}' is not supported by the '{field}' field.")
        if value[0] != "text":
            raise _error(f"The operator '{op}' is not supported for this value of the '{field}' field.")
        found = any(_contains_words(v, value[1]) for v in values)
        return found if op == "~" else not found
    if op in ("~", "!~"):
        raise _error(f"The operator '{op}' is not supported by the '{field}' field.")
    if op in ("in", "not in"):
        options = value[1]
    else:
        options = [value]
    if any(o[0] == "empty" for o in options) and not values:
        hit = True
    else:
        hit = any(_equal(board, field, actual, o) for actual in values for o in options if o[0] != "empty")
    if op in ("=", "in"):
        return hit
    # Jira: "!=" and "NOT IN" do not find issues with an empty field.
    return bool(values) and not hit


def _evaluate(board: Board, issue: Issue, node) -> bool:
    kind = node[0]
    if kind == "and":
        return all(_evaluate(board, issue, n) for n in node[1])
    if kind == "or":
        return any(_evaluate(board, issue, n) for n in node[1])
    if kind == "not":
        return not _evaluate(board, issue, node[1])
    _, field, op, value = node
    return _clause(board, issue, field, op, value)


def _check_tree(node) -> None:
    if node[0] in ("and", "or"):
        for n in node[1]:
            _check_tree(n)
    elif node[0] == "not":
        _check_tree(node[1])
    else:
        _check_value(node[1], node[3], node[1])
        if node[1] in TEXT_FIELDS and node[2] not in ("~", "!~", "is", "is not"):
            raise _error(f"The operator '{node[2]}' is not supported by the '{node[1]}' field.")


def _sort_key(field: str, issue: Issue):
    if field == "key":
        return key_number(issue.key)
    if field == "priority":
        return len(PRIORITIES) - PRIORITIES.index(issue.priority)
    if field == "status":
        return list(STATUSES).index(issue.status)
    return getattr(issue, field)


def search(board: Board, jql: str) -> list[Issue]:
    """Return the issues of the board that match the query, in the order of the query."""
    where, order = Parser(jql).parse()
    if where is None:
        raise JQLError(UNBOUNDED)
    _check_tree(where)
    found = [i for i in board.issues if _evaluate(board, i, where)]
    # Without ORDER BY, the result starts with the highest key. This is also the last sort key.
    found.sort(key=lambda i: key_number(i.key), reverse=True)
    for field, desc in reversed(order):
        found.sort(key=lambda i, f=field: _sort_key(f, i), reverse=desc)
    return found
