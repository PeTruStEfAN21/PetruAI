import pytest

from tests.e2e.conftest import assert_checks_pass, assert_committed, run_demo


@pytest.mark.e2e
def test_python_todo_cli(live_agent, tmp_path):
    agent = live_agent(
        answers=[
            "JSON file in the project folder",
            "add, list, done, remove",
            "pytest",
            "yes, commit when green",
        ]
    )
    run_demo(
        agent, "Build a small command-line todo app in Python with tests. Ask me your design questions first."
    )
    assert list(tmp_path.glob("*.py"))
    assert list(tmp_path.glob("test_*.py")) or list((tmp_path / "tests").glob("*.py"))
    assert_checks_pass(tmp_path)
    assert_committed(tmp_path)
