import pytest

from petru.agent.permissions import DESIGN_ALLOWED, Decision, decide
from petru.agent.state import Phase, Plan, Session
from petru.tools.base import Tool, ToolResult
from petru.tools.fs import EditFileTool, ReadFileTool, WriteFileTool
from petru.tools.git import GitTool
from petru.tools.shell import ShellTool


class DummyTool(Tool):
    name = "dummy"

    def run(self, args, ctx):
        return ToolResult("ok")


def build_session(root, **kwargs) -> Session:
    s = Session(root, **kwargs)
    s.start_turn("x")
    s.plan = Plan("t", ["step"], [])
    s.confirm_plan()
    return s


def test_prompt_in_idle_enters_design_and_blocks_writes(tmp_path):
    s = Session(tmp_path)
    s.start_turn("make an app")
    assert s.phase is Phase.DESIGN
    assert s.messages[-1] == {"role": "user", "content": "make an app"}
    d = decide(WriteFileTool(), {"path": "a", "content": ""}, s)
    assert d.kind == "deny" and "plan" in d.reason
    assert decide(ShellTool(), {"command": "git status"}, s).kind == "deny"
    assert decide(DummyTool(), {}, s).kind == "deny"
    assert decide(ReadFileTool(), {"path": "a"}, s).kind == "allow"


def test_design_allowed_set_matches_spec():
    assert DESIGN_ALLOWED == {
        "read_file", "list_dir", "glob", "grep", "ask_user", "plan",
        "remember", "recall", "search_code", "search_docs", "choose_mode",
    }  # fmt: skip
    assert not DESIGN_ALLOWED & {"write_file", "edit_file", "shell", "git", "run_checks"}


def test_quick_and_yolo_skip_design(tmp_path):
    s = Session(tmp_path)
    s.start_turn("fix typo", quick=True)
    assert s.phase is Phase.BUILD
    y = Session(tmp_path, yolo=True)
    y.start_turn("x")
    assert y.phase is Phase.BUILD
    assert decide(ShellTool(), {"command": "rm -rf build"}, y).kind == "allow"


def test_build_phase_shell_classification(tmp_path):
    s = build_session(tmp_path)
    assert decide(ShellTool(), {"command": "pytest -q"}, s).kind == "allow"
    d = decide(ShellTool(), {"command": "npm install zod"}, s)
    assert d.kind == "ask" and "unknown" in d.reason
    d2 = decide(ShellTool(), {"command": "git push"}, s)
    assert d2.kind == "ask" and "dangerous" in d2.reason


def test_outside_project_write_asks_but_inside_allows(tmp_path):
    s = build_session(tmp_path)
    d = decide(WriteFileTool(), {"path": "..\\x.txt", "content": "x"}, s)
    assert d.kind == "ask" and "outside" in d.reason
    assert decide(EditFileTool(), {"path": "src/a.py", "old": "a", "new": "b"}, s).kind == "allow"
    assert decide(WriteFileTool(), {"path": "a.py", "content": ""}, s).kind == "allow"


def test_git_and_plain_tools_allowed_in_build(tmp_path):
    s = build_session(tmp_path)
    assert decide(GitTool(), {"action": "commit", "message": "m"}, s).kind == "allow"
    assert decide(DummyTool(), {}, s).kind == "allow"


def test_always_allow_skips_unknown_but_not_dangerous(tmp_path):
    s = build_session(tmp_path)
    s.always_allow.add("shell")
    assert decide(ShellTool(), {"command": "npm install zod"}, s).kind == "allow"
    assert decide(ShellTool(), {"command": "git push"}, s).kind == "ask"


def test_plan_confirm_requires_plan_and_moves_to_build(tmp_path):
    s = Session(tmp_path)
    s.start_turn("x")
    with pytest.raises(ValueError):
        s.confirm_plan()
    s.plan = Plan("t", ["a"], ["d"])
    s.confirm_plan()
    assert s.phase is Phase.BUILD and s.plan.confirmed


def test_complete_returns_to_idle_and_rearms_design(tmp_path):
    s = build_session(tmp_path)
    s.pending_decisions.append("x -> y")
    s.complete()
    assert s.phase is Phase.IDLE and s.plan is None and s.pending_decisions == []
    s.start_turn("next feature")
    assert s.phase is Phase.DESIGN


def test_follow_up_prompt_in_build_stays_in_build(tmp_path):
    s = build_session(tmp_path)
    s.turn_tool_iterations = 7
    s.start_turn("also add logging")
    assert s.phase is Phase.BUILD and s.turn_tool_iterations == 0
    assert len(s.messages) == 2


def test_quick_during_design_jumps_to_build(tmp_path):
    s = Session(tmp_path)
    s.start_turn("make an app")
    s.start_turn("just fix the typo", quick=True)
    assert s.phase is Phase.BUILD


def test_decision_is_a_simple_record():
    d = Decision("allow", "")
    assert d.kind == "allow" and d.reason == ""
