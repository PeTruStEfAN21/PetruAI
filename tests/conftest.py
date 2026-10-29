import pytest

from petru.tools.shell import allow_commands


@pytest.fixture(autouse=True)
def _commands_allowed():
    """A test that presses Esc must not leave the shell refusing commands in the tests after it."""
    allow_commands()
    yield
    allow_commands()
