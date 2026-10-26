import subprocess
from pathlib import Path

import pytest

from petru_train.repos import PERMISSIVE, RepoInfo, clone, read_catalog, verify_license, write_catalog


def api_returning(payload):
    def api(path: str) -> dict:
        assert path == "repos/o/r"
        return payload

    return api


def payload(spdx):
    return {
        "html_url": "https://github.com/o/r",
        "license": None if spdx is None else {"spdx_id": spdx},
        "stargazers_count": 10,
        "pushed_at": "2026-10-01T00:00:00Z",
        "default_branch": "main",
        "language": "Python",
    }


def test_permissive_set_matches_the_design():
    assert {
        "MIT",
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "ISC",
        "0BSD",
        "CC0-1.0",
        "Unlicense",
    } <= PERMISSIVE
    assert not {"GPL-3.0", "AGPL-3.0", "LGPL-2.1", "NOASSERTION"} & PERMISSIVE


def test_verify_license_accepts_permissive():
    info = verify_license("o/r", api=api_returning(payload("MIT")))
    assert info.ok and info.spdx == "MIT" and info.stars == 10 and info.language == "Python"
    assert info.url == "https://github.com/o/r" and info.name == "o__r" and info.verified_at


@pytest.mark.parametrize("spdx", ["NOASSERTION", None, "GPL-3.0", "AGPL-3.0", "LGPL-2.1", "BUSL-1.1"])
def test_verify_license_rejects_unknown_and_copyleft(spdx):
    info = verify_license("o/r", api=api_returning(payload(spdx)))
    assert info.ok is False and info.spdx == spdx


def test_verify_license_survives_api_errors():
    def api(path):
        raise RuntimeError("gh: HTTP 404")

    info = verify_license("o/r", api=api)
    assert info.ok is False and info.spdx is None and "404" in (info.error or "")


def test_catalog_round_trip(tmp_path):
    infos = [
        RepoInfo(
            "https://github.com/o/r", "MIT", True, 10, "2026-10-01T00:00:00Z", "main", "Python", "2026-10-26"
        ),
        RepoInfo(
            "https://github.com/o/s",
            "Apache-2.0",
            True,
            5,
            "2026-09-01T00:00:00Z",
            "master",
            "Dart",
            "2026-10-26",
        ),
    ]
    infos[0].commit = "a" * 40
    path = write_catalog(infos, tmp_path / "repos.toml")
    assert read_catalog(path) == infos
    assert 'license = "MIT"' in path.read_text(encoding="utf-8")


def test_write_catalog_keeps_only_ok_repos(tmp_path):
    bad = RepoInfo("https://github.com/o/g", "GPL-3.0", False, 1, "", "main", "C", "2026-10-26")
    good = RepoInfo("https://github.com/o/r", "MIT", True, 1, "", "main", "C", "2026-10-26")
    assert read_catalog(write_catalog([bad, good], tmp_path / "r.toml")) == [good]


def test_clone_shallow_records_commit_and_is_idempotent(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=source, check=True)
    (source / "a.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=source, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "Add a module"], cwd=source, check=True)
    info = RepoInfo(source.as_uri(), "MIT", True, 0, "", "master", "Python", "2026-10-26")
    info.name = "o__r"
    dest = clone(info, tmp_path / "raw")
    assert dest == tmp_path / "raw" / "o__r" and (dest / "a.py").is_file()
    assert len(info.commit) == 40
    first = info.commit
    assert clone(info, tmp_path / "raw") == dest and info.commit == first


def test_clone_refuses_when_disk_is_low(tmp_path):
    info = RepoInfo("https://github.com/o/r", "MIT", True, 0, "", "main", "Python", "2026-10-26")
    with pytest.raises(RuntimeError, match="free disk"):
        clone(info, tmp_path / "raw", free_gb=lambda _: 5.0)
    assert not (tmp_path / "raw" / "o__r").exists()


def test_seed_list_exists_and_has_no_forbidden_repos():
    seed = Path(__file__).resolve().parents[1] / "corpus" / "seed_repos.txt"
    lines = [line.strip() for line in seed.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) >= 30 and all("/" in line for line in lines if not line.startswith("#"))
    assert not {"calcom/cal.com", "n8n-io/n8n", "grafana/grafana"} & set(lines)
