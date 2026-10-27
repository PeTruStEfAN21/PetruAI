"""Exercism practice exercises (MIT) as seeded agent tasks: verifiable work in every language.

Each exercise becomes `<out>/<prefix>_ex_<slug>/task.toml` plus `seed/` (starting code and tests, every test
enabled). The agent must make the exercise's own tests pass without changing them (petru.trajectory restores
the protected tests before the final check). One exercise in ten is held out for evaluation only.

    py -3.14 -m uv run python -m petru_train.exercism build --tracks python,go,rust
    py -3.14 -m uv run python -m petru_train.exercism validate --tracks go
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

TRAINING_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TRAINING_DIR.parent
TRACKS_DIR = TRAINING_DIR / "corpus" / "raw" / "exercism"
TASKS_DIR = TRAINING_DIR / "corpus" / "tasks"
MANIFEST = (
    "validated.json"  # in the tasks folder: which tasks the reference solution passes, per track commit
)
HELD_OUT_EVERY = 10
VERIFY_TIMEOUT_S = 1800
IDLE_PRIORITY_CLASS = 0x40  # Windows: validation compiles while training has the machine
DOC_DIRS = {".meta", ".docs", ".approaches", ".articles"}
GRADLE_FILES = {"build.gradle", "settings.gradle", "gradlew", "gradlew.bat", "gradle"}


@dataclass(frozen=True)
class Track:
    prefix: str  # task-name prefix: the specialist and the dataset language follow from it
    title: str
    skip_marker: str = ""  # regex: a test that does not run until a line is edited
    unskip: tuple[tuple[str, str], ...] = ()  # (regex, replacement), multiline


_JS = (r"\bxtest\(", r"\bxit\(", r"\bxdescribe\(")
_JS_UNSKIP = ((_JS[0], "test("), (_JS[1], "it("), (_JS[2], "describe("))
_BATS_SKIP = r"^\s*\[\[ \$BATS_RUN_SKIPPED == \"true\" \]\] \|\| skip"
TRACKS: dict[str, Track] = {
    "python": Track("python", "Python"),
    "go": Track("go", "Go"),
    "rust": Track("rust", "Rust", r"^\s*#\[ignore\]", ((r"^\s*#\[ignore\]\s*\n", ""),)),
    "c": Track("c", "C", r"TEST_IGNORE\(\)", ((r"^\s*TEST_IGNORE\(\);.*\n?", ""),)),
    "cpp": Track("cpp", "C++", r"EXERCISM_RUN_ALL_TESTS"),  # an #if block, removed by _unskip_cpp
    "csharp": Track("csharp", "C#", r"Skip\s*=", ((r"\[(Fact|Theory)\(Skip\s*=\s*\"[^\"]*\"\)\]", r"[\1]"),)),
    "java": Track("java", "Java", r"^\s*@Disabled\b", ((r"^\s*@Disabled(\(.*\))?\s*\n", ""),)),
    "kotlin": Track("kotlin", "Kotlin", r"^\s*@Ignore\b", ((r"^\s*@Ignore\s*\n", ""),)),
    "javascript": Track("js", "JavaScript", "|".join(_JS), _JS_UNSKIP),
    "typescript": Track("ts", "TypeScript", "|".join(_JS), _JS_UNSKIP),
    "ruby": Track("ruby", "Ruby", r"^\s*skip\s*$", ((r"^\s*skip\s*\n", ""),)),
    "dart": Track("dart", "Dart", r"skip:\s*true", ((r"skip:\s*true", "skip: false"),)),
    "php": Track("php", "PHP"),
    "r": Track("r", "R"),
    "bash": Track("shell", "Bash", _BATS_SKIP, ((_BATS_SKIP + r"\s*\n", ""),)),
    "sqlite": Track("sql", "SQLite"),
}

ANSWERS = [
    "The tests are the specification: keep the given files, names and signatures, and do not edit the tests.",
    "Use only the standard library and what the project already declares; add no dependencies.",
    "Keep the solution simple and readable; run the tests with run_checks until they all pass.",
]

# Exercism's Java exercises build with Gradle (a download per machine); Maven runs the same tests offline.
POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>exercism</groupId><artifactId>{artifact}</artifactId><version>1.0</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.junit.jupiter</groupId><artifactId>junit-jupiter</artifactId><version>5.10.0</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.assertj</groupId><artifactId>assertj-core</artifactId><version>3.25.1</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build><plugins><plugin>
    <groupId>org.apache.maven.plugins</groupId><artifactId>maven-surefire-plugin</artifactId><version>3.5.2</version>
  </plugin></plugins></build>
</project>
"""


@dataclass(frozen=True)
class Exercise:
    track: str
    slug: str
    name: str
    difficulty: int
    dir: Path
    solution: tuple[str, ...]
    test: tuple[str, ...]
    example: tuple[str, ...]
    editor: tuple[str, ...] = ()

    @property
    def task_name(self) -> str:
        return f"{TRACKS[self.track].prefix}_ex_{self.slug.replace('-', '_')}"


def load_exercises(track_dir: Path) -> list[Exercise]:
    """The track's practice exercises that are not deprecated; [] for a track this module does not know."""
    config_file = track_dir / "config.json"
    if track_dir.name not in TRACKS or not config_file.is_file():
        return []
    config = json.loads(config_file.read_text(encoding="utf-8"))
    exercises = []
    for entry in config.get("exercises", {}).get("practice", []):
        folder = track_dir / "exercises" / "practice" / entry["slug"]
        meta_file = folder / ".meta" / "config.json"
        if entry.get("status") == "deprecated" or not meta_file.is_file():
            continue
        files = json.loads(meta_file.read_text(encoding="utf-8")).get("files", {})
        exercises.append(
            Exercise(
                track=track_dir.name,
                slug=entry["slug"],
                name=entry.get("name", entry["slug"]),
                difficulty=int(entry.get("difficulty", 0)),
                dir=folder,
                solution=tuple(files.get("solution", [])),
                test=tuple(files.get("test", [])),
                example=tuple(files.get("example", [])),
                editor=tuple(files.get("editor", [])),
            )
        )
    return exercises


def _unskip_cpp(text: str) -> str:
    """Drop `#if defined(EXERCISM_RUN_ALL_TESTS)` and the `#endif` that closes it; other #if blocks stay."""
    out, stack = [], []
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if re.match(r"#\s*if\s+defined\s*\(\s*EXERCISM_RUN_ALL_TESTS\s*\)", stripped):
            stack.append(True)
            continue
        if re.match(r"#\s*if", stripped):
            stack.append(False)
        elif re.match(r"#\s*endif", stripped) and stack and stack.pop():
            continue
        out.append(line)
    return "".join(out)


def unskip(track: str, text: str) -> str:
    if track == "cpp":
        return _unskip_cpp(text)
    for pattern, replacement in TRACKS[track].unskip:
        text = re.sub(pattern, replacement, text, flags=re.M)
    return text


def has_skips(track: str, text: str) -> bool:
    marker = TRACKS[track].skip_marker
    return bool(marker) and re.search(marker, text, flags=re.M) is not None


def held_out(track: str, slug: str) -> bool:
    """Stable 1-in-10 split: these exercises only ever evaluate, the model never trains on them."""
    return zlib.crc32(f"{track}/{slug}".encode()) % HELD_OUT_EVERY == 0


def _docs(ex: Exercise) -> str:
    parts = []
    for name in ("introduction.md", "instructions.md", "instructions.append.md"):
        doc = ex.dir / ".docs" / name
        if doc.is_file():
            parts.append(doc.read_text(encoding="utf-8").strip())
    return "\n\n".join(parts)


def prompt_for(ex: Exercise) -> str:
    head = (
        f'Solve the Exercism exercise "{ex.name}" in {TRACKS[ex.track].title}. The project already contains '
        f"the starting code ({', '.join(ex.solution)}) and the tests ({', '.join(ex.test)}). Make every test "
        "pass without changing the tests; keep the file names and the public API the tests use. Ask me your "
        "design questions first."
    )
    return f"{head}\n\n{_docs(ex)}"


def _toml_value(value) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(value, ensure_ascii=False)  # a JSON string is a valid TOML basic string


def _ignore(ex: Exercise):
    def ignore(folder: str, names: list[str]) -> set[str]:
        if Path(folder) != ex.dir:
            return set()
        skipped = {n for n in names if n in DOC_DIRS}
        if ex.track == "java":
            skipped |= {n for n in names if n in GRADLE_FILES}
        return skipped

    return ignore


def write_task(ex: Exercise, out_root: Path, commit: str = "") -> Path:
    """`<out_root>/<task>/task.toml` and `seed/`; an existing task folder is rebuilt from scratch."""
    task_dir = out_root / ex.task_name
    shutil.rmtree(task_dir, ignore_errors=True)
    seed = task_dir / "seed"
    shutil.copytree(ex.dir, seed, ignore=_ignore(ex))
    for rel in ex.test:
        test_file = seed / rel
        if test_file.is_file():
            test_file.write_text(unskip(ex.track, test_file.read_text(encoding="utf-8")), encoding="utf-8")
    if ex.track == "java":
        (seed / "pom.xml").write_text(POM.format(artifact=ex.slug), encoding="utf-8")
    fields = {
        "name": ex.task_name,
        "prompt": prompt_for(ex),
        "answers": ANSWERS,
        "checks": [],
        "tier": "quality",
        "seed": "seed",
        "protect": [*ex.test, *ex.editor],
        "split": "eval" if held_out(ex.track, ex.slug) else "train",
        "difficulty": ex.difficulty,
        "source": f"exercism/{ex.track}@{commit}" if commit else f"exercism/{ex.track}",
        "license": "MIT",
    }
    task_toml = task_dir / "task.toml"
    task_toml.write_text("".join(f"{k} = {_toml_value(v)}\n" for k, v in fields.items()), encoding="utf-8")
    return task_toml


def _target_for(example: str, solution: tuple[str, ...]) -> str:
    """Where a reference file goes: the solution file of that name, else of that extension, else its path."""
    path = Path(example)
    for sol in solution:
        if Path(sol).name == path.name:
            return sol
    parts = path.parts
    if parts[:3] == (".meta", "src", "reference"):
        return Path("src", "main", *parts[3:]).as_posix()
    same_ext = [sol for sol in solution if Path(sol).suffix == path.suffix]
    if len(same_ext) == 1:
        return same_ext[0]
    return Path(*parts[1:]).as_posix() if parts[0] == ".meta" else example


def solution_overlay(ex: Exercise, dest: Path) -> None:
    """The reference solution laid out on the solution files, ready to be copied over the seed."""
    for example in ex.example:
        target = dest / _target_for(example, ex.solution)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ex.dir / example, target)


Runner = Callable[[Path, Path], tuple[bool, float, str]]


def _commit(track_dir: Path) -> str:
    proc = subprocess.run(["git", "-C", str(track_dir), "rev-parse", "HEAD"], capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def build(tracks: list[str], tracks_dir: Path = TRACKS_DIR, out_dir: Path = TASKS_DIR) -> list[str]:
    """Write the tasks of these tracks; returns their names."""
    names = []
    for track in tracks:
        commit = _commit(tracks_dir / track)
        for ex in load_exercises(tracks_dir / track):
            write_task(ex, out_dir, commit)
            names.append(ex.task_name)
    return names


def run_verify(task_toml: Path, solution_dir: Path) -> tuple[bool, float, str]:
    """`petru.trajectory --verify-with` in the agent's environment at idle priority; past the timeout, the
    whole process tree is killed."""
    from petru_train.trajectories import kill_tree

    with tempfile.TemporaryDirectory(prefix="petru-validate-", ignore_cleanup_errors=True) as tmp:
        out = Path(tmp) / "result.json"
        cmd = [
            "py", "-3.14", "-m", "uv", "run", "python", "-m", "petru.trajectory", str(task_toml),
            "--verify-with", str(solution_dir), "--out", str(out), "--project", str(Path(tmp) / "project"),
        ]  # fmt: skip
        flags = IDLE_PRIORITY_CLASS if sys.platform == "win32" else 0
        started = time.monotonic()
        proc = subprocess.Popen(
            cmd, cwd=str(REPO_ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags
        )
        try:
            proc.wait(timeout=VERIFY_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            kill_tree(proc.pid)
            return False, time.monotonic() - started, f"timeout after {VERIFY_TIMEOUT_S}s"
        if not out.is_file():
            return False, time.monotonic() - started, "runner error: no result"
        data = json.loads(out.read_text(encoding="utf-8"))
        return bool(data["passed"]), float(data["seconds"]), str(data["check_output"])


def _load_manifest(out_dir: Path) -> dict:
    path = out_dir / MANIFEST
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _save_manifest(out_dir: Path, manifest: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / (MANIFEST + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(out_dir / MANIFEST)


def validate(
    tracks: list[str],
    tracks_dir: Path = TRACKS_DIR,
    out_dir: Path = TASKS_DIR,
    runner: Runner = run_verify,
    force: bool = False,
) -> dict:
    """The reference solution of every exercise against its task; the manifest records what passes, per track
    commit, after each task (resumable)."""
    manifest = _load_manifest(out_dir)
    for track in tracks:
        commit = _commit(tracks_dir / track)
        for ex in load_exercises(tracks_dir / track):
            name = ex.task_name
            if not force and manifest.get(name, {}).get("commit") == commit:
                continue
            task_toml = out_dir / name / "task.toml"
            if not task_toml.is_file():
                write_task(ex, out_dir, commit)
            tests = [task_toml.parent / "seed" / rel for rel in ex.test]
            if any(
                has_skips(track, t.read_text(encoding="utf-8", errors="replace"))
                for t in tests
                if t.is_file()
            ):
                passed, seconds, output = False, 0.0, "skipped tests remain after unskip"
            else:
                with tempfile.TemporaryDirectory(prefix="petru-solution-", ignore_cleanup_errors=True) as tmp:
                    solution_overlay(ex, Path(tmp))
                    passed, seconds, output = runner(task_toml, Path(tmp))
            manifest[name] = {
                "track": track,
                "commit": commit,
                "split": "eval" if held_out(track, ex.slug) else "train",
                "passed": passed,
                "seconds": round(seconds, 1),
                "reason": "" if passed else output[-1500:],
            }
            _save_manifest(out_dir, manifest)
            print(f"{name}: {'PASS' if passed else 'FAIL'} {seconds:.0f}s", flush=True)
    return manifest


def validated_tasks(out_dir: Path = TASKS_DIR, split: str | None = None) -> list[Path]:
    """task.toml of every task whose reference solution passed (optionally only the train or eval split)."""
    manifest = _load_manifest(out_dir)
    return sorted(
        out_dir / name / "task.toml"
        for name, entry in manifest.items()
        if entry.get("passed")
        and (split is None or entry.get("split") == split)
        and (out_dir / name / "task.toml").is_file()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exercism exercises as seeded, validated agent tasks.")
    parser.add_argument("command", choices=["build", "validate"])
    parser.add_argument("--tracks", default=",".join(TRACKS), help="comma-separated Exercism track names")
    parser.add_argument("--force", action="store_true", help="validate again what the manifest already has")
    args = parser.parse_args(argv)
    tracks = [t.strip() for t in args.tracks.split(",") if t.strip()]
    unknown = [t for t in tracks if t not in TRACKS]
    if unknown:
        print(f"unknown tracks: {', '.join(unknown)}", file=sys.stderr)
        return 2
    if args.command == "build":
        print(f"{len(build(tracks))} tasks written to {TASKS_DIR}")
        return 0
    manifest = validate(tracks, force=args.force)
    for track in tracks:
        entries = [e for e in manifest.values() if e["track"] == track]
        print(f"{track}: {sum(e['passed'] for e in entries)}/{len(entries)} validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
