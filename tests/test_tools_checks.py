from petru.tools import checks
from petru.tools.base import ToolContext, ToolResult
from petru.tools.checks import detect_checks, run_checks


def test_detect_checks_python_plain_and_uv(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    assert detect_checks(tmp_path) == ["python -m pytest -q"]
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    assert detect_checks(tmp_path) == ["uv run pytest -q"]


def test_detect_checks_python_from_tests_dir_with_py_files(tmp_path):
    (tmp_path / "tests").mkdir()
    assert detect_checks(tmp_path) == []  # an empty tests/ folder is not evidence of pytest
    (tmp_path / "tests" / "test_x.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    assert detect_checks(tmp_path) == ["python -m pytest -q"]


def test_detect_checks_node_with_test_script_and_tsconfig(tmp_path):
    (tmp_path / "package.json").write_text('{"scripts": {"test": "vitest run"}}', encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")
    assert detect_checks(tmp_path) == ["npm test --silent", "npx tsc --noEmit -p ."]


def test_detect_checks_node_without_test_script(tmp_path):
    (tmp_path / "package.json").write_text('{"name": "x"}', encoding="utf-8")
    assert detect_checks(tmp_path) == []


def test_detect_checks_flutter_and_dart(tmp_path):
    (tmp_path / "pubspec.yaml").write_text("dependencies:\n  flutter:\n    sdk: flutter\n", encoding="utf-8")
    assert detect_checks(tmp_path) == ["dart analyze", "flutter test"]
    (tmp_path / "pubspec.yaml").write_text("dependencies:\n  http: ^1.0.0\n", encoding="utf-8")
    assert detect_checks(tmp_path) == ["dart analyze", "dart test"]


def test_detect_checks_empty_project(tmp_path):
    assert detect_checks(tmp_path) == []


def test_run_checks_reports_fail_when_any_command_fails(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")
    calls = []

    def fake_run(cmd, cwd, timeout_s=120, max_chars=20000):
        calls.append((cmd, cwd, timeout_s))
        if "pytest" in cmd:
            return ToolResult("3 passed\nexit code: 0")
        return ToolResult("error TS2322: boom\nexit code: 2", True)

    monkeypatch.setattr(checks, "run_shell", fake_run)
    r = run_checks.run({}, ToolContext(tmp_path, False))
    assert r.is_error
    assert "[PASS] python -m pytest -q" in r.output and "[FAIL] npx tsc --noEmit -p ." in r.output
    assert "boom" in r.output
    assert [c[0] for c in calls] == ["python -m pytest -q", "npx tsc --noEmit -p ."]
    assert all(c[1] == tmp_path and c[2] == 600 for c in calls)


def test_run_checks_with_nothing_detected(tmp_path):
    r = run_checks.run({}, ToolContext(tmp_path, False))
    assert not r.is_error and "No checks detected" in r.output
    assert run_checks.mutating is False and run_checks.name == "run_checks"


def test_detect_checks_finds_single_nested_project(tmp_path):
    from petru.tools.checks import find_project_dirs

    (tmp_path / ".git").mkdir()
    nested = tmp_path / "counter_app"
    nested.mkdir()
    (nested / "pubspec.yaml").write_text(
        "name: x\ndependencies:\n  flutter:\n    sdk: flutter\n", encoding="utf-8"
    )
    assert find_project_dirs(tmp_path) == [nested]
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    assert find_project_dirs(tmp_path) == [tmp_path]


def test_run_checks_runs_in_nested_project(tmp_path):
    from petru.tools.base import ToolContext
    from petru.tools.checks import run_checks

    nested = tmp_path / "app"
    (nested / "tests").mkdir(parents=True)
    (nested / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    result = run_checks.run({}, ToolContext(tmp_path, False))
    assert not result.is_error and "[PASS] app: python -m pytest -q" in result.output


def test_detect_checks_python_test_files_in_the_root(tmp_path):
    (tmp_path / "stats.py").write_text("x = 1\n", encoding="utf-8")
    assert detect_checks(tmp_path) == []
    (tmp_path / "test_stats.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    assert detect_checks(tmp_path) == ["python -m pytest -q"]
    (tmp_path / "test_stats.py").rename(tmp_path / "stats_test.py")
    assert detect_checks(tmp_path) == ["python -m pytest -q"]


def test_check_output_keeps_the_first_failure_and_the_summary():
    from petru.tools.checks import summarize_output

    lines = ["EXCEPTION CAUGHT", "Expected: one widget", "  Actual: none"] + [
        f"#{i} frame" for i in range(100)
    ]
    lines += ["?????????????????????????????", "Some tests failed."]
    out = summarize_output("\n".join(lines)).splitlines()
    assert out[:3] == lines[:3] and out[-1] == "Some tests failed." and any("omitted" in line for line in out)
    assert "?????????????????????????????" not in out and len(out) < 70
    assert summarize_output("1 passed") == "1 passed"


def test_detect_checks_for_go_rust_cmake_dotnet_and_maven(tmp_path):
    cases = {
        "go.mod": ["go test ./..."],
        "Cargo.toml": ["cargo test --quiet"],
        "CMakeLists.txt": [
            'cmake -S . -B build -G "MinGW Makefiles"',
            "cmake --build build",
            "ctest --test-dir build --output-on-failure",
        ],
        "app.csproj": ["dotnet test --nologo"],
        "pom.xml": ["mvn -q test"],
    }
    for marker, expected in cases.items():
        project = tmp_path / marker.replace(".", "_")
        project.mkdir()
        (project / marker).write_text("x", encoding="utf-8")
        assert detect_checks(project) == expected, marker


def touch(root, *names):
    for name in names:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("x", encoding="utf-8")


def test_detect_checks_ruby_minitest_files_or_rake(tmp_path):
    plain, rake = tmp_path / "plain", tmp_path / "rake"
    touch(plain, "isogram.rb", "isogram_test.rb", "test/test_helper_x.rb", "test/unit/parser_test.rb")
    touch(rake, "lib/a.rb", "test/a_test.rb")
    (rake / "Rakefile").write_text("require 'rake/testtask'\nRake::TestTask.new(:test)\n", encoding="utf-8")
    assert detect_checks(plain) == ["ruby -Itest isogram_test.rb", "ruby -Itest test/unit/parser_test.rb"]
    assert detect_checks(rake) == ["rake test"]


def test_detect_checks_phpunit(tmp_path):
    loose, configured, vendored = tmp_path / "loose", tmp_path / "configured", tmp_path / "vendored"
    touch(loose, "Isogram.php", "IsogramTest.php")
    touch(configured, "src/A.php", "tests/ATest.php", "phpunit.xml")
    touch(vendored, "src/A.php", "tests/ATest.php", "phpunit.xml.dist", "vendor/bin/phpunit")
    assert detect_checks(loose) == ["phpunit ."]
    assert detect_checks(configured) == ["phpunit"]
    assert detect_checks(vendored) == ["php vendor/bin/phpunit"]


def test_detect_checks_r_testthat(tmp_path):
    loose, package = tmp_path / "loose", tmp_path / "package"
    touch(loose, "isogram.R", "test_isogram.R")
    touch(package, "R/a.R", "tests/testthat/test-a.R")
    assert detect_checks(loose) == ["Rscript test_isogram.R"]
    assert detect_checks(package) == [
        "Rscript -e \"testthat::test_dir('tests/testthat', stop_on_failure = TRUE)\""
    ]


def test_detect_checks_gradle_prefers_the_wrapper(tmp_path, monkeypatch):
    wrapped, bare = tmp_path / "wrapped", tmp_path / "bare"
    touch(wrapped, "build.gradle.kts", "gradlew", "gradlew.bat", "src/main/kotlin/A.kt")
    touch(bare, "build.gradle", "src/main/java/A.java")
    monkeypatch.setattr(checks.sys, "platform", "win32")
    assert detect_checks(wrapped) == [r".\gradlew.bat test --console=plain"]
    assert detect_checks(bare) == ["gradle test --console=plain"]
    monkeypatch.setattr(checks.sys, "platform", "linux")
    assert detect_checks(wrapped) == ["./gradlew test --console=plain"]
