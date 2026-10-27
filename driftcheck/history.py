"""Per-function history on main: the first merged version, then every version whose code or docstring changed."""
from __future__ import annotations

from .gitutil import file_versions
from .models import Version, parse_functions


def history(repo: str, path: str, branch: str = "main") -> dict[str, list[Version]]:
    """qualname -> Versions oldest first. versions[0] is the baseline (first merged to main), versions[-1] is current."""
    result: dict[str, list[Version]] = {}
    previous: set[str] = set()
    for sha, date, subject, text in file_versions(repo, path, branch):
        try:
            # later redefinition of a qualname wins, as it does at runtime
            functions = {f.qualname: f for f in parse_functions(text, path)}
        except SyntaxError:
            continue
        for qualname, fn in functions.items():
            kept = result.setdefault(qualname, [])
            # ponytail: a function that disappears and comes back counts as changed, even if identical
            if (
                qualname not in previous
                or kept[-1].function.code_hash != fn.code_hash
                or kept[-1].function.docstring != fn.docstring
            ):
                kept.append(Version(sha, date, subject, fn))
        previous = set(functions)
    return result


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    from .gitutil import git

    with tempfile.TemporaryDirectory() as d:
        def run(*a): git(d, "-c", "user.name=t", "-c", "user.email=t@t", *a)
        def commit(text, msg):
            Path(d, "f.py").write_text(text)
            run("add", ".")
            run("commit", "-qm", msg)

        run("init", "-q", "-b", "main")
        commit("x = 1\n", "init")
        run("checkout", "-qb", "feat")
        commit('def f(a):\n    """Double."""\n    return a\n', "wip")
        commit('def f(a):\n    """Double."""\n    return a * 2\n', "done")
        run("checkout", "-q", "main")
        run("merge", "-q", "--no-ff", "feat", "-m", "Merge feat")
        merge_sha = git(d, "rev-parse", "HEAD").strip()
        commit('def f(a):\n    """Double."""\n    return a*2  # twice\n', "reformat")
        commit('def f(a):\n    """Return a doubled."""\n    return a*2\n', "docstring")
        commit('def f(a):\n    """Return a doubled."""\n    return a * 3\n', "code")

        versions = history(d, "f.py")["f"]
        assert [v.message for v in versions] == ["Merge feat", "docstring", "code"], [v.message for v in versions]
        assert versions[0].sha == merge_sha
        assert "return a * 2" in versions[0].function.source  # merged version, not the WIP one
    print("ok", file=sys.stderr)
