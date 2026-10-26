import pytest

from tests.e2e.conftest import assert_committed


@pytest.mark.e2e
def test_python_todo_cli(live_task, tmp_path):
    result = live_task(
        "Build a small command-line todo app in Python with tests. Ask me your design questions first.",
        ["JSON file in the project folder", "add, list, done, remove", "pytest", "yes, commit when green"],
    )
    assert list(tmp_path.glob("*.py"))
    assert list(tmp_path.glob("test_*.py")) or list((tmp_path / "tests").glob("*.py"))
    assert result.passed, result.check_output
    assert_committed(tmp_path)
