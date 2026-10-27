"""Tracker settings, read from the [tracker] table of a TOML file."""

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

from .errors import ValidationError
from .models.enums import parse_priority


@dataclass(frozen=True)
class Config:
    default_priority: int = 2
    wip_limit: int | None = None
    require_unblocked: bool = True


def load_config(path) -> Config:
    """A missing file gives the defaults; unknown keys and wrong types raise ValidationError."""
    path = Path(path)
    if not path.exists():
        return Config()
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError:
        raise ValidationError(f"invalid config file '{path.name}'") from None
    known = {f.name for f in fields(Config)}
    values = {}
    for name, value in data.get("tracker", {}).items():
        if name not in known:
            raise ValidationError(f"unknown config key '{name}'")
        values[name] = _check(name, value)
    return Config(**values)


def _check(name, value):
    if name == "default_priority":
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise ValidationError(f"config key '{name}' must be a priority")
        return parse_priority(value)
    if name == "wip_limit":
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValidationError(f"config key '{name}' must be a positive integer")
        return value
    if not isinstance(value, bool):
        raise ValidationError(f"config key '{name}' must be a boolean")
    return value
