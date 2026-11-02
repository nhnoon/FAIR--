"""The release checker must flag secrets and never descend into Downloads."""

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_release", ROOT / "tools" / "check_release.py")
check_release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_release)


def make_repo(tmp_path: Path) -> Path:
    (tmp_path / "backend" / "app").mkdir(parents=True)
    (tmp_path / "data" / "Downloads" / "private").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "ok.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "data" / "fair_bench_v1.csv").write_text("a,b\n", encoding="utf-8")
    # Planted in the private folder: must never be listed or read.
    (tmp_path / "data" / "Downloads" / "private" / "leak.txt").write_text("sk-" + "A" * 30, encoding="utf-8")
    return tmp_path


def test_clean_repo_has_no_findings_and_skips_downloads(tmp_path):
    root = make_repo(tmp_path)
    files, findings = check_release.check(root)
    assert findings == []
    assert "backend/app/ok.py" in files and "data/fair_bench_v1.csv" in files
    assert not any("Downloads" in f for f in files)


def test_secrets_and_env_files_are_flagged(tmp_path):
    root = make_repo(tmp_path)
    var = "MODEL_API_KEY"  # built at runtime so this test file itself stays clean for the scanner
    (root / "backend" / ".env").write_text(f"{var}=abc\n", encoding="utf-8")
    (root / "backend" / "app" / "leak.py").write_text('KEY = "sk-' + "B" * 30 + '"\n', encoding="utf-8")
    (root / "backend" / "app" / "conf.txt").write_text(f"{var}=realvalue123\n", encoding="utf-8")
    _, findings = check_release.check(root)
    joined = "\n".join(findings)
    assert "backend/.env" in joined
    assert "backend/app/leak.py: possible openai-style key" in joined
    assert "backend/app/conf.txt: possible assigned MODEL_API_KEY" in joined


def test_empty_template_value_is_not_a_finding(tmp_path):
    root = make_repo(tmp_path)
    (root / "backend" / ".env.example").write_text("MODEL_API_KEY=\nMODEL_NAME=muse-spark-1.3\n", encoding="utf-8")
    _, findings = check_release.check(root)
    assert findings == []


# ------------------------------------------- local secrets vs. release contents

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
KEY_LINE = "MODEL_API_KEY" + "=realvalue123\n"  # built at runtime so this test file stays clean for the scanner


def git(root, *args):
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                   check=True, capture_output=True)


def git_repo(tmp_path, ignore=".env\n"):
    root = make_repo(tmp_path)
    git(root, "init", "-q")
    (root / ".gitignore").write_text(ignore, encoding="utf-8")
    (root / "backend" / ".env").write_text(KEY_LINE, encoding="utf-8")
    return root


@needs_git
def test_ignored_never_committed_env_is_local_only(tmp_path):
    root = git_repo(tmp_path)
    files, findings = check_release.check(root)
    assert findings == []
    assert "backend/.env" not in files  # also never eligible for release-files.txt
    assert check_release.local_only_secrets(root) == ["backend/.env"]


@needs_git
def test_env_that_is_not_ignored_is_flagged(tmp_path):
    root = git_repo(tmp_path, ignore="")
    _, findings = check_release.check(root)
    assert "backend/.env: unexpected dotfile" in findings
    assert check_release.local_only_secrets(root) == []


@needs_git
def test_force_added_env_is_flagged_even_though_ignored(tmp_path):
    root = git_repo(tmp_path)
    git(root, "add", "-f", "backend/.env")
    _, findings = check_release.check(root)
    assert "backend/.env: unexpected dotfile" in findings
    assert any("tracked file has a forbidden name" in f for f in findings)


@needs_git
def test_env_committed_in_history_is_flagged_even_after_untracking(tmp_path):
    root = git_repo(tmp_path)
    git(root, "add", "-f", "backend/.env")
    git(root, "commit", "-qm", "oops")
    git(root, "rm", "-q", "--cached", "backend/.env")
    git(root, "commit", "-qm", "untrack")
    _, findings = check_release.check(root)
    assert "backend/.env: unexpected dotfile" in findings


@needs_git
def test_tracked_env_missing_from_disk_is_flagged(tmp_path):
    root = git_repo(tmp_path)
    git(root, "add", "-f", "backend/.env")
    (root / "backend" / ".env").unlink()
    _, findings = check_release.check(root)
    assert any(f.startswith("backend/.env: tracked file") for f in findings)


@needs_git
def test_secret_inside_an_eligible_file_is_still_flagged_with_a_local_env_present(tmp_path):
    root = git_repo(tmp_path)
    (root / "backend" / "app" / "conf.txt").write_text(KEY_LINE, encoding="utf-8")
    _, findings = check_release.check(root)
    assert findings == ["backend/app/conf.txt: possible assigned MODEL_API_KEY"]


@needs_git
def test_ignored_file_with_an_ordinary_name_gets_no_exemption(tmp_path):
    root = git_repo(tmp_path, ignore=".env\nnotes.txt\n")
    (root / "backend" / "notes.txt").write_text(KEY_LINE, encoding="utf-8")
    _, findings = check_release.check(root)
    assert "backend/notes.txt: possible assigned MODEL_API_KEY" in findings


def test_git_failure_fails_closed(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    (root / "backend" / ".env").write_text(KEY_LINE, encoding="utf-8")
    monkeypatch.setattr(check_release, "_git", lambda *_a, **_k: None)
    _, findings = check_release.check(root)
    assert "backend/.env: unexpected dotfile" in findings


def test_real_repository_passes():
    files, findings = check_release.check(ROOT)
    assert findings == [], findings
    assert not any(f.startswith("data/Downloads") for f in files)
    assert "data/fair_bench_v1.csv" in files


def test_real_allowlist_matches_eligible_files_exactly():
    files, _ = check_release.check(ROOT)
    assert check_release.allowlist_findings(files, ROOT) == []
    listed = check_release.read_allowlist(ROOT)
    for forbidden in ("Downloads", ".venv", "node_modules", "dist/", "__pycache__"):
        assert not any(forbidden in p for p in listed)
    assert not any(p.endswith("/.env") or p == ".env" for p in listed)


def test_allowlist_drift_is_reported(tmp_path):
    root = make_repo(tmp_path)
    files, _ = check_release.check(root)
    assert check_release.allowlist_findings(files, root) == ["release-files.txt is missing (run with --write-allowlist)"]
    check_release.write_allowlist(files, root)
    files, _ = check_release.check(root)
    assert check_release.allowlist_findings(files, root) == []
    (root / "backend" / "app" / "new.py").write_text("y = 2\n", encoding="utf-8")
    files, _ = check_release.check(root)
    assert check_release.allowlist_findings(files, root) == [
        "backend/app/new.py: eligible but missing from release-files.txt"]
