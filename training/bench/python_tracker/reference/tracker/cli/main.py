"""Command line entry point: tracker [--db PATH] [--config PATH] [--as USER] <command> ..."""

import argparse
import os
import sys

from ..config import load_config
from ..core.service import Tracker
from ..errors import TrackerError
from .commands import COMMANDS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tracker")
    parser.add_argument("--db", help="data file (default: $TRACKER_DB or tracker.json)")
    parser.add_argument("--config", help="TOML file with a [tracker] table")
    parser.add_argument("--as", dest="actor", default="system", help="who makes the change")
    sub = parser.add_subparsers(dest="command", required=True)

    user = sub.add_parser("user").add_subparsers(dest="action", required=True)
    add = user.add_parser("add")
    add.add_argument("username")
    add.add_argument("name")
    add.add_argument("--email")
    user.add_parser("list")

    project = sub.add_parser("project").add_subparsers(dest="action", required=True)
    add = project.add_parser("add")
    add.add_argument("key")
    add.add_argument("name")
    project.add_parser("list")

    new = sub.add_parser("new")
    new.add_argument("project")
    new.add_argument("title")
    new.add_argument("--priority")
    new.add_argument("--label", action="append", default=[])
    new.add_argument("--assignee")
    new.add_argument("--description", default="")

    for name, second in (("assign", "user"), ("move", "status"), ("comment", "body")):
        cmd = sub.add_parser(name)
        cmd.add_argument("key")
        cmd.add_argument(second)

    for name, second in (("label", "label"), ("depend", "other")):
        cmd = sub.add_parser(name)
        cmd.add_argument("key")
        cmd.add_argument(second)
        cmd.add_argument("--remove", action="store_true")

    sub.add_parser("show").add_argument("key")
    sub.add_parser("list").add_argument("query", nargs="*")
    sub.add_parser("order").add_argument("project")

    report = sub.add_parser("report")
    report.add_argument("kind", choices=["assignees", "labels", "status"])
    report.add_argument("--project")

    export = sub.add_parser("export")
    export.add_argument("format", choices=["csv", "markdown"])
    export.add_argument("query", nargs="*")
    export.add_argument("--output")

    sub.add_parser("log").add_argument("key", nargs="?")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    db = args.db or os.environ.get("TRACKER_DB", "tracker.json")
    try:
        config = load_config(args.config) if args.config else None
        tracker = Tracker(db, config=config)
        output = COMMANDS[args.command](tracker, args)
    except TrackerError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    if output:
        print(output)
    return 0
