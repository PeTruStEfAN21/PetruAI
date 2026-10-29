import pytest

from petru.tools.base import ToolContext
from petru.tools.git import GitTool, ensure_repo, git
from petru.tools.shell import classify_command, run_shell, shell


@pytest.mark.parametrize(
    "cmd,kind",
    [
        ("git status", "safe"),
        ("git diff --stat", "safe"),
        ("pytest -q", "safe"),
        ("python -m pytest tests -q", "safe"),
        ("flutter analyze", "safe"),
        ("npx tsc --noEmit", "safe"),
        ("Get-ChildItem -Recurse", "safe"),
        ("rm -rf build", "dangerous"),
        ("rm -r build", "dangerous"),
        ("Remove-Item -Recurse -Force x", "dangerous"),
        ("remove-item x -recurse", "dangerous"),
        ("git push origin main", "dangerous"),
        ("git reset --hard HEAD~1", "dangerous"),
        ("git clean -fdx", "dangerous"),
        ("npm install express", "unknown"),
        ("python app.py", "unknown"),
        ("git status; rm -rf x", "dangerous"),
        ("git status | Out-File log.txt", "unknown"),
    ],
)
def test_classify_command(cmd, kind):
    assert classify_command(cmd) == kind


@pytest.mark.timeout(30)
def test_shell_runs_powershell_in_cwd(tmp_path):
    r = run_shell("Get-Location | Select-Object -ExpandProperty Path", tmp_path)
    assert str(tmp_path.resolve()).lower() in r.output.lower()
    assert "exit code: 0" in r.output and not r.is_error


@pytest.mark.timeout(30)
def test_shell_nonzero_exit_is_error(tmp_path):
    r = run_shell("exit 3", tmp_path)
    assert r.is_error and "exit code: 3" in r.output


@pytest.mark.timeout(30)
def test_shell_timeout_kills_process(tmp_path):
    r = run_shell("Start-Sleep -Seconds 30", tmp_path, timeout_s=1)
    assert r.is_error and "timed out after 1s" in r.output


@pytest.mark.timeout(60)
def test_shell_output_truncated(tmp_path):
    r = run_shell("1..20000 | ForEach-Object { 'line ' + $_ }", tmp_path, max_chars=2000)
    assert len(r.output) < 2600 and "[truncated" in r.output
    assert "line 1\n" in r.output and "line 20000" in r.output


@pytest.mark.timeout(30)
def test_shell_decodes_utf8_output(tmp_path):
    r = run_shell("Write-Output 'Țară și învățare'", tmp_path)
    assert "Țară și învățare" in r.output


@pytest.mark.timeout(30)
def test_shell_tool_schema_and_run(tmp_path):
    assert shell.name == "shell" and shell.mutating is True
    assert shell.parameters["required"] == ["command"]
    r = shell.run({"command": "Write-Output hello"}, ToolContext(tmp_path, False))
    assert "hello" in r.output and not r.is_error


@pytest.fixture
def no_global_git_identity(tmp_path, monkeypatch):
    empty = tmp_path / "empty-gitconfig"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.mark.timeout(60)
def test_ensure_repo_inits_and_sets_identity(tmp_path, no_global_git_identity):
    repo = tmp_path / "proj"
    repo.mkdir()
    ensure_repo(repo)
    assert (repo / ".git").is_dir()
    assert "PetruAI" in run_shell("git config user.name", repo).output
    ensure_repo(repo)  # idempotent


@pytest.mark.timeout(60)
def test_git_status_commit_and_log(tmp_path, no_global_git_identity):
    repo = tmp_path / "proj"
    repo.mkdir()
    ensure_repo(repo)
    (repo / "a.txt").write_text("x", encoding="utf-8")
    ctx = ToolContext(repo, False)
    assert "a.txt" in git.run({"action": "status"}, ctx).output
    r = git.run({"action": "commit"}, ctx)
    assert r.is_error and "message" in r.output
    r2 = git.run({"action": "commit", "message": "add a"}, ctx)
    assert not r2.is_error
    assert "add a" in git.run({"action": "log"}, ctx).output
    assert git.run({"action": "status"}, ctx).output == "(clean)"
    assert git.run({"action": "diff"}, ctx).output == "(no changes)"


def test_git_action_classification_and_unknown_action(tmp_path):
    assert GitTool.is_mutating({"action": "commit"}) and GitTool.is_mutating({"action": "add"})
    assert not GitTool.is_mutating({"action": "status"})
    r = git.run({"action": "push"}, ToolContext(tmp_path, False))
    assert r.is_error and "push" in r.output


def test_project_env_drops_virtualenvs_of_other_projects(tmp_path):
    import os

    from petru.tools.shell import project_env

    def venv(root):
        (root / "Scripts").mkdir(parents=True)
        (root / "pyvenv.cfg").write_text("home = x\n", encoding="utf-8")
        return root

    agent = venv(tmp_path / "petru" / ".venv")
    own = venv(tmp_path / "proj" / ".venv")
    system = str(tmp_path / "python")
    environ = {
        "PATH": os.pathsep.join([str(agent / "Scripts"), str(own / "Scripts"), system]),
        "VIRTUAL_ENV": str(agent),
        "HOME": "h",
    }
    env = project_env(tmp_path / "proj" / "app", environ)
    assert env["PATH"].split(os.pathsep) == [str(own / "Scripts"), system]
    assert "VIRTUAL_ENV" not in env and env["HOME"] == "h"
    assert project_env(tmp_path / "proj", {**environ, "VIRTUAL_ENV": str(own)})["VIRTUAL_ENV"] == str(own)


def test_shell_commands_do_not_run_inside_the_agents_virtualenv(tmp_path, monkeypatch):
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / "agent" / ".venv"))
    (tmp_path / "agent" / ".venv").mkdir(parents=True)
    (tmp_path / "agent" / ".venv" / "pyvenv.cfg").write_text("home = x\n", encoding="utf-8")
    (tmp_path / "proj").mkdir()
    r = run_shell('Write-Output "venv=[$env:VIRTUAL_ENV]"', tmp_path / "proj")
    assert "venv=[]" in r.output


def test_shell_output_has_no_terminal_color_codes(tmp_path):
    r = run_shell(
        'Write-Output "$([char]27)[33mwarn$([char]27)[39m $([char]27)[7m$([char]27)[1mRUN$([char]27)[22m"',
        tmp_path,
    )
    assert "warn RUN" in r.output and "[33m" not in r.output and "\x1b" not in r.output


def test_python_programs_can_print_romanian_text(tmp_path):
    (tmp_path / "salut.py").write_text('print("Bună ziua, țară și șosea")\n', encoding="utf-8")
    r = run_shell("python salut.py", tmp_path)
    assert not r.is_error and "Bună ziua, țară și șosea" in r.output


SPIN_TEST = """def test_spin():
    while True:
        pass
"""


def test_a_hanging_python_test_shows_where_it_hung(tmp_path, monkeypatch):
    import sys

    import petru.tools.shell as shell_module

    monkeypatch.setattr(shell_module, "HANG_DUMP_S", 2)
    (tmp_path / "test_spin.py").write_text(SPIN_TEST, encoding="utf-8")
    result = run_shell(f'& "{sys.executable}" -m pytest -q -p no:cacheprovider', tmp_path, timeout_s=8)
    assert "timed out" in result.output  # the model learns its code hung, and where
    assert 'test_spin.py", line' in result.output


def test_kill_running_stops_a_command_and_its_children(tmp_path):
    import subprocess
    import threading
    import time

    from petru.tools.shell import kill_running

    command = (
        "$p = Start-Process powershell -ArgumentList '-NoProfile','-Command','Start-Sleep 60' -PassThru "
        "-NoNewWindow; $p.Id | Out-File -Encoding ascii child.pid; $p.WaitForExit()"
    )
    out = {}
    thread = threading.Thread(target=lambda: out.setdefault("r", run_shell(command, tmp_path)), daemon=True)
    thread.start()
    pid_file = tmp_path / "child.pid"
    deadline = time.monotonic() + 30
    while not (pid_file.is_file() and pid_file.read_text().strip()) and time.monotonic() < deadline:
        time.sleep(0.1)
    child = pid_file.read_text().strip()
    assert kill_running() == 1
    thread.join(10)
    assert not thread.is_alive()
    assert "stopped by the user" in out["r"].output and out["r"].is_error
    listing = subprocess.run(["tasklist", "/FI", f"PID eq {child}"], capture_output=True, text=True).stdout
    assert child not in listing
