import json
import math
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from petru_train.env import MODEL_DIR
from petru_train.evaluate import EvalResult, gate, task_pass, tool_validity
from petru_train.server import server_command

REQUESTS = Path(__file__).resolve().parents[1] / "eval" / "tool_requests.json"


def test_gate_inputs_take_both_losses_from_the_same_training_run():
    from petru_train.evaluate import gate_inputs

    base = EvalResult(loss=float("nan"), tool_validity=0.9, task_pass=0.5, details={})
    cand = EvalResult(loss=float("nan"), tool_validity=0.85, task_pass=0.5, details={})
    report = {"base_eval_loss": 1.2, "eval_loss": 0.8}
    b, c = gate_inputs(base, cand, report)
    assert (b.loss, c.loss) == (1.2, 0.8) and (b.tool_validity, c.tool_validity) == (0.9, 0.85)
    assert gate(b, c)[0]


def test_gate_inputs_keep_the_task_signatures():
    from petru_train.evaluate import gate_inputs

    base = EvalResult(float("nan"), 0.9, 0.5, {}, signature="old")
    cand = EvalResult(float("nan"), 0.9, 0.5, {}, signature="new")
    b, c = gate_inputs(base, cand, {"base_eval_loss": 1.2, "eval_loss": 0.8})
    assert (b.signature, c.signature) == ("old", "new") and not gate(b, c)[0]


def test_tasks_signature_tracks_the_evaluated_tasks(tmp_path):
    from petru_train.evaluate import tasks_signature

    tasks = tmp_path / "tasks"
    tasks.mkdir()
    for name in ("a", "b", "c"):
        (tasks / f"{name}.toml").write_text(f'prompt = "{name}"\n', encoding="utf-8")
    requests = tmp_path / "req.json"
    requests.write_text("[]", encoding="utf-8")
    first = tasks_signature(tasks, requests, limit=2)
    (tasks / "c.toml").write_text('prompt = "changed"\n', encoding="utf-8")
    assert tasks_signature(tasks, requests, limit=2) == first  # c is not among the first two
    (tasks / "a.toml").write_text('prompt = "changed"\n', encoding="utf-8")
    assert tasks_signature(tasks, requests, limit=2) != first
    assert tasks_signature(tasks, requests, limit=3) != tasks_signature(tasks, requests, limit=2)


def test_old_results_without_a_signature_still_load(tmp_path):
    path = tmp_path / "eval_base.json"
    path.write_text(
        json.dumps({"loss": 1.0, "tool_validity": 1.0, "task_pass": 0.5, "details": {}}), encoding="utf-8"
    )
    assert EvalResult.load(path).signature == ""


def test_gate_rejects_results_measured_on_different_task_sets():
    base = EvalResult(1.0, 0.9, 0.5, {}, signature="aaa")
    ok, why = gate(base, EvalResult(0.9, 0.9, 0.5, {}, signature="bbb"))
    assert not ok and "different" in why
    assert gate(base, EvalResult(0.9, 0.9, 0.5, {}, signature="aaa"))[0]
    assert gate(EvalResult(1.0, 0.9, 0.5, {}), EvalResult(0.9, 0.9, 0.5, {}, signature="bbb"))[
        0
    ]  # unknown: allowed


def test_gate_rejects_a_missing_loss():
    nan = float("nan")
    good = EvalResult(loss=1.0, tool_validity=0.9, task_pass=0.5, details={})
    ok, why = gate(EvalResult(nan, 0.9, 0.5, {}), good)
    assert not ok and "loss" in why
    ok, why = gate(good, EvalResult(nan, 0.9, 0.5, {}))
    assert not ok and "loss" in why


def test_gate_rejects_regression():
    base = EvalResult(loss=1.0, tool_validity=0.9, task_pass=0.5, details={})
    ok, why = gate(base, EvalResult(1.1, 0.9, 0.5, {}))
    assert not ok and "loss" in why
    ok, why = gate(base, EvalResult(1.0, 0.8, 0.5, {}))
    assert not ok and "tool" in why
    ok, why = gate(base, EvalResult(1.0, 0.9, 0.4, {}))
    assert not ok and "task" in why
    assert gate(base, EvalResult(1.0, 0.86, 0.5, {}))[0]  # within the 0.05 tolerance
    assert gate(base, EvalResult(1.0, 0.9, 0.5, {}))[0]
    assert gate(base, EvalResult(0.9, 0.9, 0.5, {}))[0]


def tool_call(name: str, arguments: str) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {"id": "c1", "type": "function", "function": {"name": name, "arguments": arguments}}
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ]
    }


def text_answer(text: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}]}


class FakeChatServer:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.requests: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append(body)
                payload = json.dumps(outer.responses.pop(0)).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/v1"


def test_tool_validity_counts_valid_native_calls(tmp_path):
    requests_file = tmp_path / "req.json"
    requests_file.write_text(
        json.dumps(
            [
                {"id": 1, "prompt": "read a", "expected_tool": "read_file", "should_call_tool": True},
                {"id": 2, "prompt": "write b", "expected_tool": "write_file", "should_call_tool": True},
                {"id": 3, "prompt": "edit c", "expected_tool": "edit_file", "should_call_tool": True},
                {"id": 4, "prompt": "hi", "expected_tool": None, "should_call_tool": False},
            ]
        ),
        encoding="utf-8",
    )
    fake = FakeChatServer(
        [
            tool_call("read_file", '{"path": "a"}'),
            tool_call("write_file", "{not json"),
            tool_call("nope", "{}"),
            text_answer("Hello!"),
        ]
    )
    score, details = tool_validity(fake.base_url, requests_file)
    assert score == 0.5 and [d["valid"] for d in details] == [True, False, False, True]
    first = fake.requests[0]
    assert first["stream"] is False and first["chat_template_kwargs"] == {"enable_thinking": False}
    assert [t["function"]["name"] for t in first["tools"]][:2] == ["read_file", "write_file"]
    assert first["messages"][-1] == {"role": "user", "content": "read a"}


def test_committed_requests_file_is_well_formed():
    data = json.loads(REQUESTS.read_text(encoding="utf-8"))
    assert len(data) == 20 and all(
        {"id", "prompt", "expected_tool", "should_call_tool"} <= set(d) for d in data
    )


def test_task_pass_runs_the_first_tasks_sorted_by_name(tmp_path):
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    for name in ["python_b", "flutter_a", "ts_c"]:
        (tasks / f"{name}.toml").write_text(f'name = "{name}"\nprompt = "p"\n', encoding="utf-8")
    seen = []

    def runner(task_path: Path, base_url: str, ctx_tokens: int) -> dict:
        seen.append(task_path.stem)
        return {"name": task_path.stem, "passed": task_path.stem.startswith("flutter"), "seconds": 1.0}

    rate, details = task_pass("http://x/v1", tasks, ctx_tokens=16384, limit=2, runner=runner)
    assert seen == ["flutter_a", "python_b"] and rate == 0.5
    assert [d["passed"] for d in details] == [True, False]


def test_start_server_creates_the_log_folder(tmp_path, monkeypatch):
    from petru_train import server

    started = []
    monkeypatch.setattr(server.subprocess, "Popen", lambda cmd, **kw: started.append(kw) or "proc")
    log = tmp_path / "runs" / "baseline" / "server.log"
    assert server.start_server(Path("m.gguf"), log=log) == "proc"
    assert log.parent.is_dir() and started


def test_server_command_uses_the_tier_flags():
    cmd = server_command(Path("C:/m/cand.gguf"), port=8081, ctx=16384)
    assert cmd[0].endswith("llama-server.exe") and "--jinja" in cmd and "-c" in cmd and "16384" in cmd
    assert cmd[cmd.index("--port") + 1] == "8081" and cmd[cmd.index("-m") + 1] == "C:/m/cand.gguf"
    assert "--cache-type-k" in cmd and "--flash-attn" in cmd


def test_assistant_spans_cover_each_reply_through_its_end_marker():
    from petru_train.evaluate import assistant_spans

    text = (
        "<|im_start|>system\nS<|im_end|>\n<|im_start|>user\nU<|im_end|>\n"
        "<|im_start|>assistant\nA1<|im_end|>\n<|im_start|>user\nU2<|im_end|>\n"
        "<|im_start|>assistant\nA2<|im_end|>\n"
    )
    spans = assistant_spans(text)
    assert [text[a:b] for a, b in spans] == ["A1<|im_end|>", "A2<|im_end|>"]


def test_label_mask_keeps_only_tokens_inside_spans():
    from petru_train.evaluate import label_mask

    offsets = [(0, 5), (5, 8), (8, 10), (10, 14), (14, 14)]  # the last one is a zero-width special token
    assert label_mask(offsets, [(8, 14)]) == [False, False, True, True, False]
    assert label_mask(offsets, []) == [False] * 5


@pytest.mark.gpu
def test_held_out_loss_is_finite(tmp_path):
    from petru_train.evaluate import held_out_loss
    from petru_train.samples import write_jsonl
    from tests.test_train import tiny_samples

    write_jsonl(tmp_path / "eval.jsonl", tiny_samples(4))
    loss = held_out_loss(MODEL_DIR, None, tmp_path / "eval.jsonl", max_seq_len=512)
    assert 0 < loss < 20


def test_task_details_keep_the_tail_of_the_check_output(tmp_path, monkeypatch):
    from petru_train import evaluate

    def fake_run(cmd, **kw):
        out = Path(cmd[cmd.index("--out") + 1])
        result = {
            "name": "t",
            "passed": False,
            "messages": [{}] * 50,
            "tools": [{}],
            "check_output": "x" * 5000 + "END",
        }
        out.write_text(json.dumps(result), encoding="utf-8")

    monkeypatch.setattr(evaluate.subprocess, "run", fake_run)
    data = evaluate.run_task_cli(tmp_path / "t.toml", "http://x/v1", 16384)
    assert "messages" not in data and "tools" not in data and data["turns"] == 50
    assert data["check_output"].endswith("END") and len(data["check_output"]) <= 2000


def test_tasks_signature_changes_with_the_harness_pass_rule(tmp_path, monkeypatch):
    from petru_train import evaluate

    (tmp_path / "a.toml").write_text('prompt = "a"\n', encoding="utf-8")
    before = evaluate.tasks_signature(tmp_path, tmp_path / "none.json", 6)
    monkeypatch.setattr(evaluate, "HARNESS_VERSION", evaluate.HARNESS_VERSION + 1)
    assert evaluate.tasks_signature(tmp_path, tmp_path / "none.json", 6) != before


def test_eval_tasks_are_taken_in_turn_from_every_stack(tmp_path):
    from petru_train.evaluate import select_eval_tasks

    for name in ["flutter_a", "flutter_b", "flutter_c", "python_a", "python_b", "ts_a", "ts_b", "ts_c"]:
        (tmp_path / f"{name}.toml").write_text('prompt = "p"\n', encoding="utf-8")
    picked = [p.stem for p in select_eval_tasks(tmp_path, 6)]
    assert picked == ["flutter_a", "flutter_b", "python_a", "python_b", "ts_a", "ts_b"]
    assert len(select_eval_tasks(tmp_path, 100)) == 8


def test_an_explicit_task_list_is_measured_and_signed(tmp_path):
    from petru_train.evaluate import tasks_signature

    for name in ["python_a", "python_b", "ts_a"]:
        (tmp_path / f"{name}.toml").write_text('prompt = "p"\n', encoding="utf-8")
    chosen = [tmp_path / "python_a.toml", tmp_path / "python_b.toml"]
    seen = []
    rate, _ = task_pass(
        "http://x/v1",
        tmp_path,
        16384,
        tasks=chosen,
        runner=lambda t, u, c: seen.append(t.stem) or {"passed": True},
    )
    assert seen == ["python_a", "python_b"] and rate == 1.0
    requests = tmp_path / "r.json"
    assert tasks_signature(tmp_path, requests, 6, tasks=chosen) != tasks_signature(tmp_path, requests, 6)
    assert math.isnan(task_pass("http://x/v1", tmp_path, 16384, tasks=[], runner=lambda t, u, c: {})[0])


def test_the_gate_judges_a_specialist_without_tasks_on_loss_and_tools():
    nan = float("nan")
    ok, why = gate(EvalResult(1.0, 0.9, nan, {}), EvalResult(0.9, 0.9, nan, {}))
    assert ok, why
    assert not gate(EvalResult(1.0, 0.9, 0.5, {}), EvalResult(0.9, 0.9, nan, {}))[0]


def test_tasks_marked_eval_false_stay_out_of_the_balanced_set(tmp_path):
    from petru_train.evaluate import select_eval_tasks

    (tmp_path / "python_a.toml").write_text('prompt = "p"\n', encoding="utf-8")
    (tmp_path / "go_a.toml").write_text('prompt = "p"\neval = false\n', encoding="utf-8")
    assert [p.stem for p in select_eval_tasks(tmp_path, 6)] == ["python_a"]


def test_held_out_exercism_tasks_join_the_evaluation_one_per_language(tmp_path, monkeypatch):
    import json as _json

    from petru_train import evaluate as ev
    from petru_train.exercism import held_out

    held = sorted(s for s in (f"s{i}" for i in range(300)) if held_out("", s))
    train = next(s for s in (f"s{i}" for i in range(300)) if not held_out("", s))
    pool = tmp_path / "pool"
    manifest = {}
    for name, passed in [
        (f"go_ex_{held[1]}", True), (f"go_ex_{held[0]}", True), (f"rust_ex_{held[2]}", True),
        (f"rust_ex_{train}", True), (f"c_ex_{held[3]}", False),
    ]:  # fmt: skip
        (pool / name).mkdir(parents=True)
        (pool / name / "task.toml").write_text('prompt = "p"\n', encoding="utf-8")
        manifest[name] = {"track": name.split("_")[0], "commit": "", "passed": passed}
    (pool / "validated.json").write_text(_json.dumps(manifest), encoding="utf-8")
    assert [p.parent.name for p in ev.held_out_tasks(pool)] == [f"go_ex_{held[0]}", f"rust_ex_{held[2]}"]
    harness = tmp_path / "tasks"
    harness.mkdir()
    (harness / "python_x.toml").write_text('prompt = "p"\n', encoding="utf-8")
    monkeypatch.setattr(ev, "EVAL_POOL", pool)
    chosen = ev.select_eval_tasks(harness)
    assert [p.name for p in chosen] == ["python_x.toml", "task.toml", "task.toml"]


def test_the_signature_names_the_list_whether_chosen_now_or_frozen_earlier(tmp_path):
    from petru_train.evaluate import select_eval_tasks, tasks_signature

    (tmp_path / "python_a.toml").write_text('prompt = "p"\n', encoding="utf-8")
    (tmp_path / "ts_b.toml").write_text('prompt = "p"\n', encoding="utf-8")
    requests = tmp_path / "requests.json"
    requests.write_text("[]", encoding="utf-8")
    frozen = select_eval_tasks(tmp_path, 6)
    assert tasks_signature(tmp_path, requests, 6) == tasks_signature(tmp_path, requests, 6, tasks=frozen)


def test_server_command_caps_the_host_prompt_cache():
    # two servers with the default 8 GB caches filled the 32 GB laptop during the team bench
    cmd = server_command(Path("C:/m/cand.gguf"))
    assert cmd[cmd.index("--cache-ram") + 1] == "1024"
