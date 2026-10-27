from .codec import State, decode, encode
from .jsonfile import read_json, write_json_atomic
from .migrations import SCHEMA_VERSION, migrate


def load_state(path) -> State:
    """A missing file is an empty tracker; older schemas are migrated in memory."""
    data = read_json(path)
    if data is None:
        return State()
    return decode(migrate(data))


def save_state(path, state: State) -> None:
    write_json_atomic(path, encode(state))


__all__ = ["SCHEMA_VERSION", "State", "decode", "encode", "load_state", "migrate", "save_state"]
