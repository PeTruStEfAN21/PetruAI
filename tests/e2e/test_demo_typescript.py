import pytest

from tests.e2e.conftest import assert_committed, project_file


@pytest.mark.e2e
def test_typescript_express_api(live_task, tmp_path):
    result = live_task(
        "Build a small REST API for notes in TypeScript with tests. Ask me your design questions first.",
        [
            "Express with TypeScript",
            "in-memory array",
            "GET /notes, POST /notes, DELETE /notes/:id",
            "vitest with supertest",
            "yes",
        ],
    )
    package = project_file(tmp_path, "package.json")
    assert package is not None and (package.parent / "tsconfig.json").exists()
    assert result.passed, result.check_output
    assert_committed(tmp_path)
