import json

from petru.agent.context import build_system_prompt, compact_if_needed, estimate_tokens
from petru.agent.decisions import append_decisions
from petru.agent.prompts import BASE_SYSTEM_PROMPT, BUILD_PHASE_PROMPT, DESIGN_PHASE_PROMPT
from petru.agent.state import Plan, Session
from petru.offline import is_online, load_offline_manifest
from petru.providers.base import ChatResult
from tests.fakes import FakeProvider

SYSTEM = {"role": "system", "content": "sys"}


def many_turns_with_tool_calls(n_turns, payload_chars):
    msgs = []
    for i in range(n_turns):
        msgs.append({"role": "user", "content": f"task {i}"})
        msgs.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"c{i}",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path": "a"}'},
                    }
                ],
            }
        )
        msgs.append({"role": "tool", "tool_call_id": f"c{i}", "content": "x" * payload_chars})
        msgs.append({"role": "assistant", "content": f"done {i}"})
    return msgs


def test_estimate_tokens_is_chars_over_four():
    assert estimate_tokens("a" * 400) == 100 and estimate_tokens("") == 0


def test_base_prompt_under_1500_tokens():
    assert estimate_tokens(BASE_SYSTEM_PROMPT + DESIGN_PHASE_PROMPT) <= 1500
    assert estimate_tokens(BASE_SYSTEM_PROMPT + BUILD_PHASE_PROMPT) <= 1500


def test_system_prompt_includes_phase_decisions_and_offline_rules(tmp_path):
    (tmp_path / "AGENTS.md").write_text("Project rules here", encoding="utf-8")
    append_decisions(tmp_path, ["db -> SQLite"])
    s = Session(tmp_path)
    s.start_turn("x")
    p = build_system_prompt(s, repo_root=tmp_path, online=False)
    assert "ask_user" in p and "Project rules here" in p and "db -> SQLite" in p
    assert "no internet" in p.lower()


def test_system_prompt_build_phase_mentions_checks_and_plan(tmp_path):
    s = Session(tmp_path)
    s.start_turn("x", quick=True)
    s.plan = Plan("Todo", ["write cli.py", "add tests"], ["db -> SQLite"], confirmed=True)
    p = build_system_prompt(s, repo_root=tmp_path, online=True)
    assert "run_checks" in p and "write cli.py" in p and "Todo" in p
    assert "no internet" not in p.lower() and "ask 2" not in p.lower()


def test_offline_rules_list_manifest_packages(tmp_path):
    (tmp_path / "infra" / "offline").mkdir(parents=True)
    (tmp_path / "infra" / "offline" / "manifest.toml").write_text(
        '[python]\npackages = ["fastapi", "pytest"]\n[node]\npackages = ["express"]\n', encoding="utf-8"
    )
    s = Session(tmp_path)
    s.start_turn("x")
    p = build_system_prompt(s, repo_root=tmp_path, online=False)
    assert "fastapi" in p and "express" in p


def test_load_offline_manifest_missing_and_present(tmp_path):
    assert load_offline_manifest(tmp_path) == {}
    (tmp_path / "infra" / "offline").mkdir(parents=True)
    (tmp_path / "infra" / "offline" / "manifest.toml").write_text(
        '[python]\npackages = ["fastapi"]\n[flutter]\npackages = ["dio"]\ndocs_repos = ["x"]\n',
        encoding="utf-8",
    )
    assert load_offline_manifest(tmp_path) == {"python": ["fastapi"], "flutter": ["dio"]}


def test_agents_md_is_capped_at_2000_tokens(tmp_path):
    (tmp_path / "AGENTS.md").write_text("y" * 40000, encoding="utf-8")
    s = Session(tmp_path)
    s.start_turn("x")
    p = build_system_prompt(s, repo_root=tmp_path, online=True)
    assert "y" * 8000 in p and "y" * 8001 not in p


def test_is_online_uses_injected_connector():
    assert is_online(connect=lambda host, port, timeout: None) is True

    def refuse(host, port, timeout):
        raise OSError("no route")

    assert is_online(connect=refuse) is False


def test_compact_keeps_tool_pairs_intact(tmp_path):
    s = Session(tmp_path)
    original = [SYSTEM, *many_turns_with_tool_calls(20, 8000)]
    s.messages = list(original)
    fake = FakeProvider([ChatResult("SUMMARY OF OLD TURNS", [], "stop", None, None)])
    assert compact_if_needed(s, fake, ctx_tokens=16384) is True
    assert s.messages[0] == SYSTEM
    assert s.messages[1]["role"] == "user" and s.messages[1]["content"].startswith(
        "[Summary of earlier conversation]"
    )
    assert "SUMMARY OF OLD TURNS" in s.messages[1]["content"]
    assert s.messages[-1] == original[-1]
    for i, m in enumerate(s.messages):
        if m["role"] == "tool":
            ids = {
                c["id"]
                for prev in s.messages[:i]
                if prev["role"] == "assistant"
                for c in prev.get("tool_calls") or []
            }
            assert m["tool_call_id"] in ids
    assert estimate_tokens(json.dumps(s.messages)) <= 16384 - 4096
    summarize_request = fake.calls[0]["messages"]
    assert "task 0" in json.dumps(summarize_request) and fake.calls[0]["tools"] is None


def test_no_compaction_when_under_budget(tmp_path):
    s = Session(tmp_path)
    s.messages = [SYSTEM, {"role": "user", "content": "hi"}]
    fake = FakeProvider([])
    assert compact_if_needed(s, fake, ctx_tokens=16384) is False
    assert fake.calls == [] and len(s.messages) == 2


def test_phase_prompts_force_tool_questions_and_honest_verification():
    assert "ask_user" in DESIGN_PHASE_PROMPT and "ends your turn" in DESIGN_PHASE_PROMPT
    assert "run_checks" in BUILD_PHASE_PROMPT and "actually ran" in BUILD_PHASE_PROMPT


def test_base_prompt_says_build_in_the_current_directory():
    assert "nested" in BASE_SYSTEM_PROMPT


def test_base_prompt_requires_strict_json_arguments():
    assert "escape" in BASE_SYSTEM_PROMPT and "strict JSON" in BASE_SYSTEM_PROMPT
