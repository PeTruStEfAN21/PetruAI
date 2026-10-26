import pytest

from tests.e2e.conftest import assert_checks_pass, assert_committed, project_file, run_demo


@pytest.mark.e2e
def test_typescript_express_api(live_agent, tmp_path):
    agent = live_agent(
        answers=[
            "Express with TypeScript",
            "in-memory array",
            "GET /notes, POST /notes, DELETE /notes/:id",
            "vitest with supertest",
            "yes",
        ]
    )
    run_demo(
        agent,
        "Build a small REST API for notes in TypeScript with tests. Ask me your design questions first.",
    )
    package = project_file(tmp_path, "package.json")
    assert package is not None and (package.parent / "tsconfig.json").exists()
    assert_checks_pass(tmp_path)
    assert_committed(tmp_path)
