"""Markdown sections, their history on main, and exact-name links to functions."""
from __future__ import annotations

import re

from .gitutil import file_versions, ls_files
from .models import DocSection, Function

_HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")


def split_sections(text: str) -> list[tuple[str, int, int, str]]:
    """(heading, lineno, end_lineno, text) per ATX heading, 1-based lines. Text before the first heading is heading ""."""
    lines = text.splitlines()
    starts: list[tuple[str, int]] = [("", 0)]
    in_fence = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence and (m := _HEADING.match(line)):
            starts.append((m.group(1), i))
    sections = []
    seen: dict[str, int] = {}
    for n, (heading, start) in enumerate(starts):
        end = starts[n + 1][1] if n + 1 < len(starts) else len(lines)
        body = "\n".join(lines[start:end])
        if heading == "" and not body.strip():
            continue  # no preamble
        seen[heading] = seen.get(heading, 0) + 1
        if seen[heading] > 1:
            heading = f"{heading} ({seen[heading]})"  # repeated heading in one file
        sections.append((heading, start + 1, end, body))
    return sections


def doc_history(repo: str, branch: str = "main", prefix: str = "") -> dict[tuple[str, str], list[DocSection]]:
    """(path, heading) -> versions of that section, oldest first, kept only when its text changed."""
    history: dict[tuple[str, str], list[DocSection]] = {}
    for path in ls_files(repo, ".md", branch, prefix):
        for sha, date, _, text in file_versions(repo, path, branch):
            for heading, lineno, end_lineno, body in split_sections(text):
                kept = history.setdefault((path, heading), [])
                if not kept or kept[-1].text != body:
                    kept.append(DocSection(path, heading, lineno, end_lineno, body, sha, date))
    return history


def link(docs: dict[tuple[str, str], list[DocSection]], functions: list[Function]) -> dict[str, list[tuple[str, str]]]:
    """qualname -> keys of sections that name the function exactly in any version. No fuzzy matching."""
    # ponytail: bare-name matching on common words ("get", "run") is noisy; restrict bare names to code spans if it is
    links: dict[str, list[tuple[str, str]]] = {}
    for fn in functions:
        module = fn.path.rsplit(".", 1)[0].replace("/", ".")  # path minus extension: app/calc.go -> app.calc
        names = {fn.qualname, fn.qualname.rsplit(".", 1)[-1], f"{module}.{fn.qualname}", f"{module.rsplit('.', 1)[-1]}.{fn.qualname}"}
        pattern = re.compile("|".join(rf"(?<![\w.]){re.escape(n)}(?!\w)" for n in sorted(names, key=len, reverse=True)))
        keys = [key for key, versions in docs.items() if any(pattern.search(v.text) for v in versions)]
        if keys:
            links[fn.qualname] = keys
    return links


if __name__ == "__main__":
    import sys
    import tempfile
    from datetime import datetime
    from pathlib import Path

    from .gitutil import git
    from .models import parse_functions

    md = "intro\n# Add\nuse `add(a, b)`\n```\n# not a heading\n```\n## Shop.total ##\ntext\n# Add\nagain\n"
    secs = split_sections(md)
    assert [(h, a, b) for h, a, b, _ in secs] == [("", 1, 1), ("Add", 2, 6), ("Shop.total", 7, 8), ("Add (2)", 9, 10)], secs
    assert "# not a heading" in secs[1][3]

    fns = parse_functions("def add(a, b): pass\nclass Shop:\n    def total(self): pass\ndef adder(): pass\n", "pkg/calc.py")
    now = datetime.now()
    docs = {
        ("a.md", "x"): [DocSection("a.md", "x", 1, 1, "call add() here", "s", now)],
        ("a.md", "y"): [DocSection("a.md", "y", 1, 1, "see Shop.total and calc.adder", "s", now)],
        ("a.md", "z"): [DocSection("a.md", "z", 1, 1, "address, other.add, adding", "s", now)],
        ("a.md", "w"): [DocSection("a.md", "w", 1, 1, "pkg.calc.Shop.total.", "s", now)],
    }
    assert link(docs, fns) == {"add": [("a.md", "x")], "Shop.total": [("a.md", "y"), ("a.md", "w")], "adder": [("a.md", "y")]}, link(docs, fns)

    with tempfile.TemporaryDirectory() as d:
        def run(*a): git(d, "-c", "user.name=t", "-c", "user.email=t@t", *a)

        run("init", "-q", "-b", "main")
        Path(d, "api.md").write_text("# A\nold\n# B\nsame\n")
        run("add", "."); run("commit", "-qm", "one")
        Path(d, "api.md").write_text("# A\nnew\n# B\nsame\n")
        run("commit", "-qam", "two")
        hist = doc_history(d)
        assert len(hist[("api.md", "A")]) == 2 and len(hist[("api.md", "B")]) == 1, hist
        assert hist[("api.md", "B")][0].lineno == 3
    print("ok", file=sys.stderr)
