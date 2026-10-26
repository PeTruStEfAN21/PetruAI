import os

import pytest

from petru_train.isolate import run_isolated


def test_runs_the_function_in_another_process_and_returns_its_json_result():
    result = run_isolated("petru_train.isolate:selftest", {"value": 21})
    assert result["doubled"] == 42 and result["pid"] != os.getpid()


def test_child_failure_becomes_a_runtime_error_naming_the_target():
    with pytest.raises(RuntimeError, match="petru_train.isolate:selftest"):
        run_isolated("petru_train.isolate:selftest", {"value": 21, "fail": True})
