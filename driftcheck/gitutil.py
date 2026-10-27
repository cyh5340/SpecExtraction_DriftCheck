"""Thin git CLI helpers shared by inventory, history and docs."""
from __future__ import annotations

import subprocess
from datetime import datetime


def git(repo: str, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", repo, *args], check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout


def ls_files(repo: str, suffix: str, branch: str = "main", prefix: str = "") -> list[str]:
    """Paths ending in `suffix` tracked at the tip of `branch`, optionally only under the folder `prefix`."""
    paths = git(repo, "ls-tree", "-r", "--name-only", branch, *(["--", prefix] if prefix else [])).splitlines()
    return [p for p in paths if p.endswith(suffix)]


def file_versions(repo: str, path: str, branch: str = "main") -> list[tuple[str, datetime, str, str]]:
    """(sha, date, subject, text) for each first-parent commit on `branch` that changed `path`, oldest first.

    For a merge commit the date is when it landed on `branch`, so feature-branch commits never appear.
    Commits where the file was deleted are skipped.
    """
    log = git(repo, "log", "--first-parent", "--reverse", "--format=%H%x1f%cI%x1f%s", branch, "--", path)
    versions = []
    for line in log.splitlines():
        sha, date, subject = line.split("\x1f", 2)
        try:
            text = git(repo, "show", f"{sha}:{path}")
        except subprocess.CalledProcessError:
            continue  # deleted in this commit
        versions.append((sha, datetime.fromisoformat(date), subject, text))
    return versions


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        def run(*a): git(d, "-c", "user.name=t", "-c", "user.email=t@t", *a)
        def write(text): Path(d, "f.py").write_text(text)

        run("init", "-q", "-b", "main")
        write("v1\n"); run("add", "."); run("commit", "-qm", "one")
        run("checkout", "-qb", "feat")
        write("wip\n"); run("commit", "-qam", "wip")
        write("v2\n"); run("commit", "-qam", "done")
        run("checkout", "-q", "main")
        Path(d, "other.txt").write_text("x"); run("add", "."); run("commit", "-qm", "unrelated")
        run("merge", "-q", "--no-ff", "feat", "-m", "Merge feat")

        got = [(subj, text) for _, _, subj, text in file_versions(d, "f.py")]
        assert got == [("one", "v1\n"), ("Merge feat", "v2\n")], got
        assert ls_files(d, ".py") == ["f.py"]
    print("ok", file=sys.stderr)
