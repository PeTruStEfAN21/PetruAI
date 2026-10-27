from petru import cli
from petru.router import choose_tier, piece_tier, project_specialist, request_specialist


def touch(root, *names, text="x"):
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def test_the_project_files_name_the_specialist(tmp_path):
    flutter, rust, web = tmp_path / "f", tmp_path / "r", tmp_path / "w"
    touch(flutter, "pubspec.yaml", "lib/main.dart", "test/widget_test.dart")
    touch(rust, "Cargo.toml", "src/lib.rs")
    touch(
        web, "package.json", "src/app.ts", "src/view.tsx", "node_modules/x/index.py"
    )  # node_modules ignored
    assert project_specialist(flutter) == "flutter"
    assert project_specialist(rust) == "rust"
    assert project_specialist(web) == "web"
    assert project_specialist(tmp_path / "empty") is None


def test_python_projects_go_to_web_or_data_by_their_dependencies(tmp_path):
    web, data, plain = tmp_path / "web", tmp_path / "data", tmp_path / "plain"
    touch(web, "app.py")
    touch(web, "requirements.txt", text="Django==5.1\n")
    touch(data, "analysis.py")
    touch(data, "pyproject.toml", text='[project]\ndependencies = ["pandas", "scikit-learn"]\n')
    touch(plain, "tool.py")
    assert project_specialist(web) == "python-web"
    assert project_specialist(data) == "python-data"
    assert project_specialist(plain) == "python"


def test_a_new_project_is_routed_by_the_request():
    assert request_specialist("Create a small Flutter app with widget tests") == "flutter"
    assert request_specialist("Build a REST API in TypeScript with Express") == "web"
    assert request_specialist("Write a Rust CLI") == "rust"
    assert request_specialist("Do something") is None


def test_choose_tier_falls_back_when_the_specialist_is_missing(tmp_path):
    touch(tmp_path, "Cargo.toml", "src/lib.rs")
    assert choose_tier(tmp_path, {"tuned-rust": 1, "default": 1}, "default") == "tuned-rust"
    assert choose_tier(tmp_path, {"default": 1}, "default") == "default"
    py = tmp_path / "py"
    touch(py, "app.py")
    touch(py, "requirements.txt", text="flask\n")
    assert (
        choose_tier(py, {"tuned-python": 1, "default": 1}, "default") == "tuned-python"
    )  # no python-web yet
    assert choose_tier(tmp_path / "new", {"tuned-flutter": 1}, "default", "a Flutter app") == "tuned-flutter"


def test_cli_accepts_auto():
    assert cli.build_parser().parse_args(["--model", "auto"]).model == "auto"


def test_cli_auto_starts_the_specialist_tier(tmp_path, monkeypatch):
    from petru.config import Config, Tier, default_tiers
    from tests.fakes import result
    from tests.test_cli import FakeManager, patch_runtime

    patch_runtime(monkeypatch, tmp_path, [result(content="ok")])
    tiers = {**default_tiers(), "tuned-rust": Tier("tuned-rust", "specialists/rust.gguf", ctx=32768)}
    monkeypatch.setattr(
        cli, "load_config", lambda root: Config(root, root / "m", root / "s.exe", tiers=tiers)
    )
    touch(tmp_path / "proj", "Cargo.toml", "src/lib.rs")
    assert cli.main(["-p", "x", "--project", str(tmp_path / "proj"), "--model", "auto"]) == 0
    assert FakeManager.instances[-1].started == ["tuned-rust"]


def test_a_delegated_piece_goes_to_the_specialist_for_its_files(tmp_path):
    tiers = {"fast": 1, "tuned-go": 1, "tuned-python": 1}
    assert piece_tier(tmp_path, ["cmd/main.go", "cmd/util.go"], tiers, "fast") == "tuned-go"
    assert piece_tier(tmp_path, ["web/app.ts"], tiers, "fast") == "fast"  # no web specialist yet
    assert piece_tier(tmp_path, ["notes.md"], tiers, "fast") == "fast"
    (tmp_path / "requirements.txt").write_text("flask\n", encoding="utf-8")
    assert piece_tier(tmp_path, ["app/views.py"], tiers, "fast") == "tuned-python"  # stands in for web
