"""Pre-publication safety check for the FAIR repository.

Walks ONLY an explicit allowlist of project locations. It never enters
data/Downloads (or any other directory not listed below), so private files are
neither read nor listed.

  python tools/check_release.py                    # from the repository root
  python tools/check_release.py --write-allowlist  # regenerate release-files.txt after adding files

Exit code 0 = no findings. Prints the files that are eligible for the public repo and
checks they match release-files.txt exactly, the explicit list used for staging:

  git --literal-pathspecs add --pathspec-from-file=release-files.txt

A secret-named file on disk (backend/.env) is acceptable only when git proves it stays
local: inside a git repository, ignored, not in the index, and absent from history. Such
files are reported by name and never read. Anything else, including any git failure, is a
finding. Tracked secret-named files are flagged even if they are missing from disk.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (directory, recursive). data/ is scanned non-recursively: top-level files only.
SCAN_ROOTS = [
    (Path("."), False),
    (Path("backend"), True),
    (Path("frontend"), True),
    (Path("docs"), True),
    (Path("tools"), True),
    (Path("data"), False),
]
SKIP_DIRS = {
    ".venv", "venv", "node_modules", "dist", "build", "__pycache__", ".pytest_cache",
    ".vite", "runs", "Downloads", ".git", ".idea", ".vscode",
}
ALLOWED_DOTFILES = {".gitignore", ".gitattributes", ".env.example", ".python-version"}
ALLOWLIST_NAME = "release-files.txt"
FORBIDDEN_NAME = re.compile(r"(^\.env$|^\.env\.(?!example$)|\.pem$|\.key$|\.p12$|\.pfx$|^id_rsa|\.sqlite3?$|\.db$)", re.I)
MAX_BYTES = 2_000_000
SECRET_PATTERNS = {
    "openai-style key": re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"),
    "github token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "aws access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "bearer token": re.compile(r"Bearer\s+[A-Za-z0-9._\-]{20,}"),
    "assigned MODEL_API_KEY": re.compile(r"MODEL_API_KEY[ \t]*=[ \t]*['\"]?[A-Za-z0-9._\-]{8,}"),
}
# Large generated lockfile: scanned for secrets, exempt from the size limit.
SIZE_EXEMPT = {"package-lock.json"}


def iter_files(root: Path = ROOT):
    for rel_base, recursive in SCAN_ROOTS:
        base = root / rel_base
        if not base.is_dir():
            continue
        entries = base.rglob("*") if recursive else base.iterdir()
        for p in entries:
            rel_parts = p.relative_to(root).parts
            if any(part in SKIP_DIRS for part in rel_parts):
                continue
            if p.is_file():
                yield p


def _git(root: Path, *args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None


def _is_repo_root(root: Path) -> bool:
    top = _git(root, "rev-parse", "--show-toplevel")
    return bool(top and top.returncode == 0 and Path(top.stdout.strip()).resolve() == root.resolve())


def _stays_local(root: Path, rel: str) -> bool:
    """True only if git proves the file is ignored, untracked, and was never committed."""
    if not _is_repo_root(root):
        return False
    ignored = _git(root, "check-ignore", "-q", "--", rel)
    tracked = _git(root, "ls-files", "--", rel)
    history = _git(root, "log", "--all", "--format=%H", "-1", "--", rel)
    if ignored is None or tracked is None or history is None:
        return False
    return ignored.returncode == 0 and tracked.returncode == 0 and not tracked.stdout.strip() \
        and history.returncode == 0 and not history.stdout.strip()


def _tracked_secret_names(root: Path) -> list[str]:
    if not _is_repo_root(root):
        return []
    listed = _git(root, "ls-files")
    if listed is None or listed.returncode != 0:
        return ["git ls-files failed: tracked files could not be checked"]
    return [f"{rel}: tracked file has a forbidden name (secrets/database)"
            for rel in listed.stdout.splitlines() if FORBIDDEN_NAME.search(rel.rsplit("/", 1)[-1])]


def _is_secret_name(name: str) -> bool:
    return bool(FORBIDDEN_NAME.search(name))


def local_only_secrets(root: Path = ROOT) -> list[str]:
    """Secret-named files that git proves stay out of the release. Names only; never read."""
    return sorted(
        rel for rel in (p.relative_to(root).as_posix() for p in set(iter_files(root)))
        if _is_secret_name(rel.rsplit("/", 1)[-1]) and _stays_local(root, rel)
    )


def check(root: Path = ROOT) -> tuple[list[str], list[str]]:
    files, findings = [], _tracked_secret_names(root)
    local_only = set(local_only_secrets(root))
    for p in sorted(set(iter_files(root))):
        rel = p.relative_to(root).as_posix()
        name = p.name
        if rel in local_only:
            continue
        if name.startswith(".") and name not in ALLOWED_DOTFILES:
            findings.append(f"{rel}: unexpected dotfile")
            continue
        if FORBIDDEN_NAME.search(name):
            findings.append(f"{rel}: forbidden file type (secrets/database)")
            continue
        size = p.stat().st_size
        if size > MAX_BYTES and name not in SIZE_EXEMPT:
            findings.append(f"{rel}: large file ({size:,} bytes)")
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            if p.suffix.lower() not in {".png", ".ico", ".woff", ".woff2"}:
                findings.append(f"{rel}: unexpected binary file")
            files.append(rel)
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{rel}: possible {label}")
        files.append(rel)
    return files, findings


def read_allowlist(root: Path = ROOT) -> list[str] | None:
    path = root / ALLOWLIST_NAME
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


def allowlist_findings(files: list[str], root: Path = ROOT) -> list[str]:
    listed = read_allowlist(root)
    if listed is None:
        return [f"{ALLOWLIST_NAME} is missing (run with --write-allowlist)"]
    out = [f"{p}: in {ALLOWLIST_NAME} but not an eligible file" for p in sorted(set(listed) - set(files))]
    out += [f"{p}: eligible but missing from {ALLOWLIST_NAME}" for p in sorted(set(files) - set(listed))]
    if len(listed) != len(set(listed)):
        out.append(f"{ALLOWLIST_NAME} contains duplicate entries")
    return out


def write_allowlist(files: list[str], root: Path = ROOT) -> None:
    body = "".join(f"{f}\n" for f in sorted(set(files) | {ALLOWLIST_NAME}))
    (root / ALLOWLIST_NAME).write_bytes(body.encode("utf-8"))  # LF endings on every OS


def main() -> int:
    files, findings = check()
    if "--write-allowlist" in sys.argv[1:]:
        if findings:
            print("Refusing to write the allowlist while there are findings:")
            for f in findings:
                print(f"  ! {f}")
            return 1
        write_allowlist(files)
        files, findings = check()
        print(f"Wrote {ALLOWLIST_NAME} ({len(files)} files).")
    findings += allowlist_findings(files)
    print(f"Eligible files ({len(files)}):")
    for f in files:
        print(f"  {f}")
    if findings:
        print(f"\nFINDINGS ({len(findings)}):")
        for f in findings:
            print(f"  ! {f}")
        return 1
    for rel in local_only_secrets():
        print(f"\nLocal only, not part of the release (git-ignored, never committed): {rel}")
    print("\nNo findings. data/Downloads and other unlisted locations were not scanned.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
