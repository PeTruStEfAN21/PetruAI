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
    assert data["solution"] == ["src/lib.rs", "Cargo.toml"]  # all that leaves the agent's project
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


def test_cpp_projects_build_whatever_the_folder_is_called(tmp_path):
    cmake = "get_filename_component(exercise ${CMAKE_CURRENT_SOURCE_DIR} NAME)\nproject(${exercise} CXX)\n"
    files = {
        "CMakeLists.txt": cmake,
        "two_fer.cpp": "",
        "two_fer.h": "",
        "two_fer_test.cpp": "",
        ".meta/example.cpp": "",
    }
    track = make_exercise(
        tmp_path,
        "cpp",
        "two-fer",
        files,
        ["two_fer.cpp", "two_fer.h"],
        ["two_fer_test.cpp"],
        [".meta/example.cpp"],
    )
    [ex] = exercism.load_exercises(track)
    seed = exercism.write_task(ex, tmp_path / "tasks").parent / "seed"
    text = (seed / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "get_filename_component" not in text and "set(exercise two-fer)" in text


def test_c_projects_get_a_cmake_build_that_registers_the_unity_tests(tmp_path):
    makefile = "LIBS = -lm\nCFLAGS += -DUNITY_SUPPORT_64 -DUNITY_INCLUDE_DOUBLE -DUNITY_OUTPUT_COLOR\n"
    files = {
        "makefile": makefile,
        "isogram.c": "",
        "isogram.h": "",
        "test_isogram.c": "",
        "test-framework/unity.c": "",
        ".meta/example.c": "",
    }
    track = make_exercise(
        tmp_path, "c", "isogram", files, ["isogram.c", "isogram.h"], ["test_isogram.c"], [".meta/example.c"]
    )
    [ex] = exercism.load_exercises(track)
    seed = exercism.write_task(ex, tmp_path / "tasks").parent / "seed"
    text = (seed / "CMakeLists.txt").read_text(encoding="utf-8")
    assert not (seed / "makefile").exists() and "add_test(" in text and "test-framework/unity.c" in text
    assert "UNITY_INCLUDE_DOUBLE" in text and "UNITY_SUPPORT_64" in text


def test_js_and_ts_projects_run_jest_through_npm_after_an_install(tmp_path):
    package = {
        "scripts": {"test": "corepack pnpm jest", "lint": "corepack pnpm eslint ."},
        "packageManager": "pnpm@9.15.2",
        "devDependencies": {
            "jest": "^30.2.0",
            "eslint": "^9.28.0",
            "babel-jest": "^30.3.0",
            "typescript": "^5",
        },
    }
    files = {
        "package.json": json.dumps(package),
        "yarn.lock": "",
        ".yarnrc.yml": "",
        "test-runner.mjs": "",
        "bob.ts": "",
        "bob.test.ts": "xit('a', () => {})\n",
        ".meta/proof.ci.ts": "",
    }
    track = make_exercise(
        tmp_path, "typescript", "bob", files, ["bob.ts"], ["bob.test.ts"], [".meta/proof.ci.ts"]
    )
    [ex] = exercism.load_exercises(track)
    task_toml = exercism.write_task(ex, tmp_path / "tasks")
    data = tomllib.loads(task_toml.read_text(encoding="utf-8"))
    seed = task_toml.parent / "seed"
    rewritten = json.loads((seed / "package.json").read_text(encoding="utf-8"))
    assert rewritten["scripts"] == {"test": "jest"} and "packageManager" not in rewritten
    assert set(rewritten["devDependencies"]) == {"jest", "babel-jest", "typescript"}
    assert not any((seed / name).exists() for name in ("yarn.lock", ".yarnrc.yml", "test-runner.mjs"))
    assert data["setup"][0].startswith("npm install") and "package.json" in data["protect"]


def test_an_exercise_is_held_out_in_every_language_or_in_none():
    slugs = [f"exercise-{i}" for i in range(200)]
    for slug in slugs:
        assert (
            exercism.held_out("go", slug)
            == exercism.held_out("python", slug)
            == exercism.held_out("rust", slug)
        )


def test_the_split_follows_the_exercise_not_the_manifest(tmp_path):
    held = next(s for s in (f"ex-{i}" for i in range(100)) if exercism.held_out("go", s))
    kept = next(s for s in (f"ex-{i}" for i in range(100)) if not exercism.held_out("go", s))
    manifest = {}
    for slug in (held, kept):
        name = f"go_ex_{slug.replace('-', '_')}"
        (tmp_path / name).mkdir()
        (tmp_path / name / "task.toml").write_text('prompt = "p"\n', encoding="utf-8")
        manifest[name] = {"track": "go", "split": "train", "passed": True}  # a split written by an older rule
    (tmp_path / exercism.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    assert [p.parent.name for p in exercism.validated_tasks(tmp_path, split="eval")] == [
        f"go_ex_{held.replace('-', '_')}"
    ]


def test_rewriting_the_toml_leaves_the_seed_alone(tmp_path):
    track = rust_track(tmp_path)
    [ex] = exercism.load_exercises(track)
    task_toml = exercism.write_task(ex, tmp_path / "tasks")
    marker = task_toml.parent / "seed" / "marker.txt"
    marker.write_text("in use by a validation", encoding="utf-8")
    task_toml.write_text('name = "old"\nprompt = "p"\n', encoding="utf-8")
    exercism.write_task(ex, tmp_path / "tasks", reseed=False)
    assert (
        marker.is_file() and tomllib.loads(task_toml.read_text(encoding="utf-8"))["name"] == "rust_ex_isogram"
    )
