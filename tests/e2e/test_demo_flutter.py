import pytest

from tests.e2e.conftest import assert_checks_pass, assert_committed, project_file, run_demo


@pytest.mark.e2e
def test_flutter_counter_app(live_agent, tmp_path):
    agent = live_agent(
        answers=[
            "counter with a reset button and a history list",
            "setState, no packages",
            "widget tests",
            "yes",
        ]
    )
    run_demo(
        agent,
        "Create a small Flutter app from scratch with widget tests. Ask me your design questions first.",
    )
    pubspec = project_file(tmp_path, "pubspec.yaml")
    assert pubspec is not None and (pubspec.parent / "lib" / "main.dart").exists()
    assert_checks_pass(tmp_path)  # dart analyze + flutter test
    assert_committed(tmp_path)
