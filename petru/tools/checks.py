"""Detect and run the project's test and analysis commands."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from petru.tools.base import Tool, ToolContext, ToolResult
from petru.tools.shell import run_shell

CHECK_TIMEOUT_S = 600


def _ruby_checks(root: Path) -> list[str]:
    rakefile = root / "Rakefile"
    if rakefile.is_file() and "test" in rakefile.read_text(encoding="utf-8", errors="replace").lower():
        return ["rake test"]
    files = sorted({*root.glob("*_test.rb"), *root.glob("test_*.rb"), *root.glob("test/**/*_test.rb")})
    return [f"ruby -Itest {f.relative_to(root).as_posix()}" for f in files]


def _php_checks(root: Path) -> list[str]:
    configured = (root / "phpunit.xml").is_file() or (root / "phpunit.xml.dist").is_file()
    if (root / "vendor" / "bin" / "phpunit").is_file():
        return ["php vendor/bin/phpunit"]
    if configured:
        return ["phpunit"]
    if any(root.glob("*Test.php")):
        return ["phpunit ."]
    return ["phpunit tests"] if any(root.glob("tests/**/*Test.php")) else []


def _r_checks(root: Path) -> list[str]:
    if (root / "tests" / "testthat").is_dir():
        return ["Rscript -e \"testthat::test_dir('tests/testthat', stop_on_failure = TRUE)\""]
    return [f"Rscript {f.name}" for f in sorted(root.glob("test_*.R"))]


def _gradle_checks(root: Path) -> list[str]:
    if not any((root / name).is_file() for name in ("build.gradle", "build.gradle.kts")):
        return []
    if sys.platform == "win32" and (root / "gradlew.bat").is_file():
        return [r".\gradlew.bat test --console=plain"]
    if sys.platform != "win32" and (root / "gradlew").is_file():
        return ["./gradlew test --console=plain"]
    return ["gradle test --console=plain"]


def _has_python_tests(root: Path) -> bool:
    if (root / "pyproject.toml").is_file() or (root / "pytest.ini").is_file():
        return True
    tests = root / "tests"
    if tests.is_dir() and any(tests.rglob("*.py")):
        return True
    return any(root.glob("test_*.py")) or any(root.glob("*_test.py"))  # pytest's default discovery


def detect_checks(root: Path) -> list[str]:
    commands: list[str] = []
    if _has_python_tests(root):
        commands.append("uv run pytest -q" if (root / "uv.lock").is_file() else "python -m pytest -q")
    package = root / "package.json"
    if package.is_file():
        try:
            scripts = json.loads(package.read_text(encoding="utf-8")).get("scripts", {})
        except json.JSONDecodeError, OSError, AttributeError:
            scripts = {}
        if "test" in scripts:
            commands.append("npm test --silent")
    if (root / "tsconfig.json").is_file():
        commands.append("npx tsc --noEmit -p .")
    pubspec = root / "pubspec.yaml"
    if pubspec.is_file():
        text = pubspec.read_text(encoding="utf-8", errors="replace")
        commands.append("dart analyze")
        commands.append("flutter test" if "sdk: flutter" in text else "dart test")
    if (root / "go.mod").is_file():
        commands.append("go test ./...")
    if (root / "Cargo.toml").is_file():
        commands.append("cargo test --quiet")
    if (root / "CMakeLists.txt").is_file():  # C/C++ with GCC (WinLibs); tests registered with add_test
        commands += [
            'cmake -S . -B build -G "MinGW Makefiles"',
            "cmake --build build",
            "ctest --test-dir build --output-on-failure",
        ]
    if any(root.glob("*.sln")) or any(root.glob("*.csproj")):
        commands.append("dotnet test --nologo")
    if (root / "pom.xml").is_file():
        commands.append("mvn -q test")
    commands += _gradle_checks(root) + _ruby_checks(root) + _php_checks(root) + _r_checks(root)
    return commands


SKIP_DIRS = {".git", ".petru", "node_modules", ".venv", ".dart_tool", "build", "dist", "__pycache__"}


def find_project_dirs(root: Path) -> list[Path]:
    """The root when it has checks, else its direct children that do (project scaffolded in a subfolder)."""
    if detect_checks(root):
        return [root]
    children = sorted(p for p in root.iterdir() if p.is_dir() and p.name not in SKIP_DIRS)
    return [child for child in children if detect_checks(child)]


def _is_decoration(line: str) -> bool:
    """A rule of box-drawing characters, or what a console code page left of one ('????')."""
    text = line.strip()
    return len(text) >= 10 and set(text) <= set("?=-─═╡╞│ ")


def summarize_output(text: str, head: int = 25, tail: int = 35) -> str:
    """The start and the end of a check's output: the first failure (flutter test and pytest print the
    expectation that broke first) and the final summary, without decorative rules."""
    lines = [line for line in text.splitlines() if not _is_decoration(line)]
    if len(lines) <= head + tail:
        return "\n".join(lines)
    omitted = len(lines) - head - tail
    return "\n".join([*lines[:head], f"... {omitted} lines omitted ...", *lines[-tail:]])


class RunChecksTool(Tool):
    name = "run_checks"
    description = (
        "Detect and run the project's checks (pytest, npm test, tsc, dart analyze, flutter test, go test, "
        "cargo test, cmake + ctest, dotnet test, mvn test, gradle test, minitest/rake, phpunit, testthat) "
        "and report PASS/FAIL per command. Run it after every change."
    )
    parameters = {"type": "object", "properties": {}, "additionalProperties": False}

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        project_dirs = find_project_dirs(ctx.project_root)
        if not project_dirs:
            return ToolResult(
                "No checks detected: no pyproject.toml, pytest.ini, tests/*.py or test_*.py, "
                "no package.json test script, no tsconfig.json, no pubspec.yaml, go.mod, Cargo.toml, "
                "CMakeLists.txt, .csproj, pom.xml, build.gradle, *_test.rb, *Test.php or test_*.R."
            )
        reports, failed = [], False
        for project in project_dirs:
            label = "" if project == ctx.project_root else f"{project.name}: "
            for cmd in detect_checks(project):
                result = run_shell(cmd, project, timeout_s=CHECK_TIMEOUT_S)
                summary = summarize_output(result.output)
                reports.append(f"[{'FAIL' if result.is_error else 'PASS'}] {label}{cmd}\n{summary}")
                failed = failed or result.is_error
        return ToolResult("\n\n".join(reports), failed)


run_checks = RunChecksTool()
