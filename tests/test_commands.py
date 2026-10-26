import pytest

from petru.tui.commands import HELP_TEXT, Command, parse_command


@pytest.mark.parametrize(
    "line,expected",
    [
        ("/quick fix the typo", Command("quick", "fix the typo")),
        ("/model quality", Command("model", "quality")),
        ("/done", Command("done", "")),
        ("  /status  ", Command("status", "")),
        ("hello there", None),
        ("", None),
        ("/unknown", Command("unknown", "")),
    ],
)
def test_parse_command(line, expected):
    assert parse_command(line) == expected


def test_help_lists_every_command():
    for name in ("/help", "/model", "/plan", "/quick", "/done", "/yolo", "/status", "/exit"):
        assert name in HELP_TEXT
