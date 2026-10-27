import pytest

from tracker import QuerySyntaxError, Tracker
from tracker.query import parse, tokenize


class Clock:
    def __init__(self):
        self.now = 0

    def __call__(self):
        self.now += 1
        return self.now


@pytest.fixture(scope="module")
def tracker(tmp_path_factory):
    t = Tracker(tmp_path_factory.mktemp("q") / "data.json", clock=Clock())
    for name in ("ana", "bob", "cara"):
        t.add_user(name, name.title())
    t.add_project("WEB", "Website")
    t.add_project("API", "Backend")
    t.create_issue("WEB", "Login page broken", reporter="ana", description="Users cannot sign in",
                   priority=3, labels=["bug", "ui"], assignee="ana")
    t.create_issue("WEB", "Add dark mode", reporter="ana", priority=1, labels=["ui"], assignee="bob")
    t.create_issue("WEB", "Crash on save", reporter="ana", priority=4, labels=["bug"])
    t.create_issue("API", "Rate limiting", reporter="bob", priority=2, labels=["backend"], assignee="ana")
    t.create_issue("API", "Fix login token", reporter="ana", priority=0, labels=["bug", "backend"], assignee="cara")
    t.transition("WEB-3", "wontfix")
    t.transition("API-2", "in_progress")
    return t


def keys(tracker, query):
    return [i.key for i in tracker.search(query)]


@pytest.mark.parametrize(
    "query, expected",
    [
        ("", ["API-1", "API-2", "WEB-1", "WEB-2", "WEB-3"]),
        ("label:bug", ["API-2", "WEB-1", "WEB-3"]),
        ("label:bug is:open", ["API-2", "WEB-1"]),
        ("is:closed", ["WEB-3"]),
        ("status:open,in_progress", ["API-1", "API-2", "WEB-1", "WEB-2"]),
        ("status:WONTFIX", ["WEB-3"]),
        ("assignee:none", ["WEB-3"]),
        ("assignee:ana,cara", ["API-1", "API-2", "WEB-1"]),
        ("reporter:bob", ["API-1"]),
        ("project:web", ["WEB-1", "WEB-2", "WEB-3"]),
        ("priority>=3", ["WEB-1", "WEB-3"]),
        ("priority<high", ["API-1", "API-2", "WEB-2"]),
        ("priority:urgent", ["WEB-3"]),
        ("priority=0", ["API-2"]),
        ("priority>2 priority<=3", ["WEB-1"]),
    ],
)
def test_field_filters(tracker, query, expected):
    assert keys(tracker, query) == expected


@pytest.mark.parametrize(
    "query, expected",
    [
        ("login", ["API-2", "WEB-1"]),
        ("LOGIN page", ["WEB-1"]),
        ('"sign in"', ["WEB-1"]),
        ('"dark mode" label:ui', ["WEB-2"]),
        ("nothing-matches", []),
    ],
)
def test_free_text_searches_title_and_description(tracker, query, expected):
    assert keys(tracker, query) == expected


@pytest.mark.parametrize(
    "query, expected",
    [
        ("-label:bug", ["API-1", "WEB-2"]),
        ("--label:bug", ["API-2", "WEB-1", "WEB-3"]),
        ("label:ui OR project:API", ["API-1", "API-2", "WEB-1", "WEB-2"]),
        ("label:ui assignee:bob OR label:backend", ["API-1", "API-2", "WEB-2"]),
        ("(label:ui OR label:backend) -assignee:ana", ["API-2", "WEB-2"]),
        ("-(label:bug OR label:ui)", ["API-1"]),
        ('-"login"', ["API-1", "WEB-2", "WEB-3"]),
    ],
)
def test_boolean_operators(tracker, query, expected):
    assert keys(tracker, query) == expected


@pytest.mark.parametrize(
    "query, expected",
    [
        ("label:bug sort:-priority", ["WEB-3", "WEB-1", "API-2"]),
        ("sort:priority", ["API-2", "WEB-2", "API-1", "WEB-1", "WEB-3"]),
        ("sort:status,-priority", ["WEB-1", "API-1", "WEB-2", "API-2", "WEB-3"]),
        ("sort:-created", ["API-2", "API-1", "WEB-3", "WEB-2", "WEB-1"]),
        ("sort:title", ["WEB-2", "WEB-3", "API-2", "WEB-1", "API-1"]),
        ("sort:-key label:ui", ["WEB-2", "WEB-1"]),
    ],
)
def test_sorting(tracker, query, expected):
    assert keys(tracker, query) == expected


def test_parse_collects_sort_keys():
    query = parse("label:bug sort:-priority,key")
    assert query.sort == (("priority", True), ("key", False))
    assert parse("").filter is None
    assert parse("sort:title").filter is None


def test_tokenize():
    tokens = tokenize('-(a OR "b c") x>=1')
    assert [t.kind for t in tokens] == ["NOT", "LPAREN", "TEXT", "OR", "TEXT", "RPAREN", "TERM"]
    assert tokens[4].value == "b c"
    assert tokens[6].value == ("x", ">=", "1")
    assert [t.pos for t in tokens] == [0, 1, 2, 4, 7, 12, 14]


@pytest.mark.parametrize(
    "query, message",
    [
        ("foo:bar", "unknown field 'foo'"),
        ('label:bug "abc', "unterminated quote"),
        ("(label:bug", "unbalanced parentheses"),
        ("label:bug)", "unbalanced parentheses"),
        ("priority>=huge", "invalid priority 'huge'"),
        ("label>2", "operator '>' is not allowed for 'label'"),
        ("status:closed", "unknown status 'closed'"),
        ("(sort:key)", "sort is only allowed at the top level"),
        ("-sort:key", "sort is only allowed at the top level"),
        ("sort:assignee", "unknown sort field 'assignee'"),
        ("label:bug OR", "expected a term"),
        ("OR label:bug", "expected a term"),
        ("()", "expected a term"),
        ("label:", "missing value for 'label'"),
        ("is:maybe", "invalid value 'maybe' for 'is'"),
    ],
)
def test_syntax_errors(tracker, query, message):
    with pytest.raises(QuerySyntaxError, match=message):
        tracker.search(query)


def test_error_positions():
    with pytest.raises(QuerySyntaxError) as info:
        parse('label:bug "abc')
    assert info.value.position == 10
    with pytest.raises(QuerySyntaxError) as info:
        parse("is:open foo:1")
    assert info.value.position == 8
