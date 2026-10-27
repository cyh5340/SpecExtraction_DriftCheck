"""Current functions at the tip of a branch, and the deterministic signature check."""
from __future__ import annotations

import sys

from .gitutil import git, ls_files
from .models import Function, language, parse_functions


def inventory(repo: str, branch: str = "main", prefix: str = "") -> list[Function]:
    """Every function in every source file (any tree-sitter language) at the tip of `branch`.

    Python files that don't parse are skipped.
    """
    found: list[Function] = []
    for path in filter(language, ls_files(repo, "", branch, prefix)):
        try:
            found += parse_functions(git(repo, "show", f"{branch}:{path}"), path)
        except SyntaxError as e:
            print(f"warning: skipping {path}: {e}", file=sys.stderr)
    return found


def signature_changed(old: Function, new: Function) -> bool:
    return old.args != new.args or old.returns != new.returns


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        def run(*a): git(d, "-c", "user.name=t", "-c", "user.email=t@t", *a)

        run("init", "-q", "-b", "main")
        Path(d, "pkg").mkdir()
        Path(d, "pkg", "a.py").write_text("def f(x): return x\n\nclass K:\n    def m(self, y=1) -> int: return y\n")
        Path(d, "broken.py").write_text("def oops(:\n")
        Path(d, "notes.md").write_text("# not code\n")
        Path(d, "web.js").write_text("function g(a) { return a; }\n")
        run("add", "."); run("commit", "-qm", "init")

        fns = {(f.path, f.qualname): f for f in inventory(d)}
        assert set(fns) == {("pkg/a.py", "f"), ("pkg/a.py", "K.m"), ("web.js", "g")}, fns

        f, m = fns["pkg/a.py", "f"], fns["pkg/a.py", "K.m"]
        same = parse_functions("def f(x):\n    return x + 1\n")[0]
        assert not signature_changed(f, same)  # body change only
        assert signature_changed(f, parse_functions("def f(x, y=2): return x\n")[0])  # new param
        assert signature_changed(f, parse_functions("def f(x=0): return x\n")[0])  # new default
        assert signature_changed(m, parse_functions("def m(self, y=1) -> str: return y\n")[0])  # return type
    print("ok", file=sys.stderr)
