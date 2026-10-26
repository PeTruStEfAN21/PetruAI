import pytest

from tests.e2e.conftest import assert_committed, project_file


@pytest.mark.e2e
def test_flutter_counter_app(live_task, tmp_path):
    result = live_task(
        "Create a small Flutter app from scratch with widget tests. Ask me your design questions first.",
        ["counter with a reset button and a history list", "setState, no packages", "widget tests", "yes"],
    )
    pubspec = project_file(tmp_path, "pubspec.yaml")
    assert pubspec is not None and (pubspec.parent / "lib" / "main.dart").exists()
    assert result.passed, result.check_output  # dart analyze + flutter test
    assert_committed(tmp_path)
