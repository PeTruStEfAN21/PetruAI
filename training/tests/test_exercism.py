import json
import tomllib

from petru_train import exercism


def make_exercise(root, track, slug, files, solution, test, example, practice_status="active"):
    """A miniature Exercism track: config.json, one practice exercise with its .meta and .docs."""
    base = root / track
    ex = base / "exercises" / "practice" / slug
    for rel, text in files.items():
        (ex / rel).parent.mkdir(parents=True, exist_ok=True)
        (ex / rel).write_text(text, encoding="utf-8")
    (ex / ".docs").mkdir(parents=True, exist_ok=True)
    (ex / ".docs" / "instructions.md").write_text("# Instructions\n\nDetermine if a word is an isogram.\n")
    meta = {"files": {"solution": solution, "test": test, "example": example}}
    (ex / ".meta").mkdir(parents=True, exist_ok=True)
    (ex / ".meta" / "config.json").write_text(json.dumps(meta), encoding="utf-8")
    config = {"exercises": {"practice": [{"slug": slug, "name": slug.title(), "status": practice_status}]}}
    (base / "config.json").write_text(json.dumps(config), encoding="utf-8")
    return base


RUST_TEST = "#[test]\nfn empty() {}\n\n#[test]\n#[ignore]\nfn longest() {}\n"


def rust_track(tmp_path):
    files = {
        "Cargo.toml": '[package]\nname = "isogram"\n',
        "src/lib.rs": "pub fn check(_: &str) -> bool { todo!() }\n",
        "tests/isogram.rs": RUST_TEST,
        ".meta/example.rs": "pub fn check(_: &str) -> bool { true }\n",
        ".approaches/x/content.md": "an approach",
    }
    return make_exercise(
        tmp_path,
        "rust",
        "isogram",
        files,
        ["src/lib.rs", "Cargo.toml"],
        ["tests/isogram.rs"],
        [".meta/example.rs"],
    )


def test_an_exercise_becomes_a_seeded_task_with_every_test_enabled(tmp_path):
    track = rust_track(tmp_path)
    [ex] = exercism.load_exercises(track)
    task_toml = exercism.write_task(ex, tmp_path / "tasks")
    data = tomllib.loads(task_toml.read_text(encoding="utf-8"))
    assert task_toml.parent.name == "rust_ex_isogram" and data["name"] == "rust_ex_isogram"
    assert data["seed"] == "seed" and data["protect"] == ["tests/isogram.rs"]
    assert "Determine if a word is an isogram." in data["prompt"] and "Rust" in data["prompt"]
    assert "src/lib.rs" in data["prompt"] and data["answers"]
    seed = task_toml.parent / "seed"
    assert (seed / "src" / "lib.rs").is_file() and (seed / "Cargo.toml").is_file()
    assert (
        not (seed / ".meta").exists()
        and not (seed / ".approaches").exists()
        and not (seed / ".docs").exists()
    )
    assert "#[ignore]" not in (seed / "tests" / "isogram.rs").read_text(encoding="utf-8")
    assert data["split"] in ("train", "eval")


def test_the_reference_solution_lands_on_the_solution_files(tmp_path):
    track = rust_track(tmp_path)
    [ex] = exercism.load_exercises(track)
    exercism.solution_overlay(ex, tmp_path / "overlay")
    assert (tmp_path / "overlay" / "src" / "lib.rs").read_text(encoding="utf-8").strip().endswith("{ true }")
    assert not (tmp_path / "overlay" / "Cargo.toml").exists()  # only what the example provides


def test_java_reference_files_map_from_the_reference_tree_to_main(tmp_path):
    files = {
        "build.gradle": "plugins {}\n",
        "src/main/java/IsogramChecker.java": "class IsogramChecker {}\n",
        "src/test/java/IsogramCheckerTest.java": '@Disabled("Remove to run test")\n@Test\nvoid a() {}\n',
        ".meta/src/reference/java/IsogramChecker.java": "class IsogramChecker { /* done */ }\n",
    }
    track = make_exercise(
        tmp_path,
        "java",
        "isogram",
        files,
        ["src/main/java/IsogramChecker.java"],
        ["src/test/java/IsogramCheckerTest.java"],
        [".meta/src/reference/java/IsogramChecker.java"],
    )
    [ex] = exercism.load_exercises(track)
    exercism.solution_overlay(ex, tmp_path / "overlay")
    assert "done" in (tmp_path / "overlay" / "src/main/java/IsogramChecker.java").read_text(encoding="utf-8")
    seed = exercism.write_task(ex, tmp_path / "tasks").parent / "seed"
    assert (seed / "pom.xml").is_file() and not (
        seed / "build.gradle"
    ).exists()  # Maven, which runs offline here
    assert "@Disabled" not in (seed / "src/test/java/IsogramCheckerTest.java").read_text(encoding="utf-8")


def test_deprecated_exercises_and_unknown_tracks_are_left_out(tmp_path):
    files = {"isogram.py": "", "isogram_test.py": "", ".meta/example.py": ""}
    make_exercise(
        tmp_path,
        "python",
        "isogram",
        files,
        ["isogram.py"],
        ["isogram_test.py"],
        [".meta/example.py"],
        "deprecated",
    )
    assert exercism.load_exercises(tmp_path / "python") == []
    assert exercism.load_exercises(tmp_path / "cobol") == []


def test_unskip_per_track():
    assert (
        exercism.unskip("javascript", "  xtest('a', () => {});\n  test('b')")
        == "  test('a', () => {});\n  test('b')"
    )
    assert exercism.unskip("typescript", "  xit('a', () => {})") == "  it('a', () => {})"
    cs = '    [Fact(Skip = "Remove this Skip property to run this test")]\n    public void A() {}'
    assert exercism.unskip("csharp", cs) == "    [Fact]\n    public void A() {}"
    assert exercism.unskip("c", "   TEST_IGNORE();   // delete this line to run test\n   x();") == "   x();"
    assert exercism.unskip("ruby", "    # skip\n    skip\n    assert true") == "    # skip\n    assert true"
    cpp = 'TEST_CASE("a") {}\n#if defined(EXERCISM_RUN_ALL_TESTS)\nTEST_CASE("b") {}\n#endif\n'
    assert exercism.unskip("cpp", cpp) == 'TEST_CASE("a") {}\nTEST_CASE("b") {}\n'
    assert exercism.unskip("kotlin", "    @Ignore\n    @Test\n") == "    @Test\n"
    assert exercism.unskip("dart", "  }, skip: true);") == "  }, skip: false);"
    for track in exercism.TRACKS:
        assert not exercism.has_skips(track, exercism.unskip(track, "#[ignore]\nxtest(\nskip\n"))


def test_held_out_is_stable_and_about_one_in_ten():
    slugs = [f"exercise-{i}" for i in range(400)]
    held = [s for s in slugs if exercism.held_out("go", s)]
    assert held == [s for s in slugs if exercism.held_out("go", s)]
    assert 20 <= len(held) <= 60


def test_build_writes_every_known_track_and_validate_keeps_what_passes(tmp_path):
    tracks = rust_track(tmp_path).parent
    files = {"two_fer.py": "", "two_fer_test.py": "", ".meta/example.py": "def two_fer(): ..."}
    make_exercise(
        tracks, "python", "two-fer", files, ["two_fer.py"], ["two_fer_test.py"], [".meta/example.py"]
    )
    out = tmp_path / "tasks"
    built = exercism.build(["rust", "python"], tracks_dir=tracks, out_dir=out)
    assert sorted(built) == ["python_ex_two_fer", "rust_ex_isogram"]

    seen = []

    def runner(task_toml, solution_dir):
        seen.append(task_toml.parent.name)
        assert any(solution_dir.rglob("*.*"))  # the reference solution, laid out on the solution files
        return task_toml.parent.name.startswith("rust"), 1.0, "output"

    manifest = exercism.validate(["rust", "python"], tracks_dir=tracks, out_dir=out, runner=runner)
    assert manifest["rust_ex_isogram"]["passed"] and not manifest["python_ex_two_fer"]["passed"]
    exercism.validate(["rust", "python"], tracks_dir=tracks, out_dir=out, runner=runner)
    assert len(seen) == 2  # resumable: a task already validated is not run again
    assert [p.parent.name for p in exercism.validated_tasks(out)] == ["rust_ex_isogram"]
    split = exercism.held_out("rust", "isogram")
    assert exercism.validated_tasks(out, split="eval" if split else "train")
    assert not exercism.validated_tasks(out, split="train" if split else "eval")
