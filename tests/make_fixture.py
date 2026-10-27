"""Build a throwaway git repo that covers every drift case, with the expected verdict per function.

Standalone on purpose (no driftcheck imports). Any code version that doesn't match the spec it's
supposed to match carries a `# mismatch` comment, so `stub_judge` can play Jev in tests.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from textwrap import dedent

MARK = "# mismatch"


def stub_judge(qualname: str, spec_text: str, code: str) -> float:
    """Stand-in for driftcheck.judge.judge: P(code matches spec)."""
    return 0.0 if MARK in code else 1.0


class _Repo:
    def __init__(self, dest: str):
        self.dest = Path(dest)
        self.dest.mkdir(parents=True, exist_ok=True)
        # every git call gets a later timestamp, so doc-vs-code ordering never ties
        self.clock = datetime(2025, 1, 1, tzinfo=timezone.utc)
        self.code: dict[str, dict[str, str]] = {}  # path -> {block key: source}
        self.docs: dict[str, str] = {}  # documented qualname -> section body
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.com")
        self.git("config", "core.autocrlf", "false")

    def git(self, *args: str) -> str:
        self.clock += timedelta(hours=1)
        stamp = f"{int(self.clock.timestamp())} +0000"
        env = {**os.environ, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
        return subprocess.run(
            ["git", "-C", str(self.dest), *args], check=True, capture_output=True, text=True, env=env
        ).stdout

    def put(self, path: str, key: str, src: str) -> None:
        self.code.setdefault(path, {})[key] = dedent(src).strip() + "\n"

    def doc(self, name: str, body: str) -> None:
        self.docs[name] = " ".join(dedent(body).split())

    def commit(self, msg: str) -> None:
        for path, blocks in self.code.items():
            p = self.dest / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("\n\n".join(blocks.values()), newline="\n")
        if self.docs:
            p = self.dest / "docs" / "api.md"
            p.parent.mkdir(parents=True, exist_ok=True)
            sections = "\n".join(f"## `{name}`\n\n{body}\n" for name, body in self.docs.items())
            p.write_text(f"# API\n\n{sections}", newline="\n")
        self.git("add", "-A")
        self.git("commit", "-qm", msg)

    def branch(self, name: str) -> None:
        self.git("checkout", "-qb", name)

    def merge(self, name: str) -> None:
        # ponytail: in-memory state assumes nothing lands on main while a branch is open
        self.git("checkout", "-q", "main")
        self.git("merge", "-q", "--no-ff", name, "-m", f"Merge {name}")


CALC = "app/calc.py"


def make_fixture(dest: str) -> dict[str, tuple[str, str | None]]:
    r = _Repo(dest)

    # Case 3: the spec lands on main before any code exists
    r.doc("apply_discount", """
        Returns `price` reduced by `percent` percent, for example 200 with 10 gives 180.0.
        The result never goes below 0.""")
    r.commit("docs: specify apply_discount")

    r.branch("feat/basics")
    r.put(CALC, "_imports", "import math")
    r.put(CALC, "sum_two", """
        def sum_two(a, b):
            return a + b""")  # case 1
    r.put(CALC, "clamp_value", """
        def clamp_value(x, lo, hi):
            return max(lo, min(x, hi))""")  # case 2
    r.put(CALC, "average_price", f"""
        def average_price(prices):
            {MARK}
            return sum(prices) / len(prices)""")  # WIP: crashes on [], never reaches main
    r.doc("average_price", "Arithmetic mean of `prices`; returns 0.0 for an empty list.")
    r.put(CALC, "with_tax", """
        def with_tax(amount, rate=0.08):
            return round(amount * (1 + rate), 2)""")  # case 4
    r.doc("with_tax", "Returns `amount` plus tax at `rate`, i.e. amount * (1 + rate), rounded to 2 decimals.")
    r.put(CALC, "shipping_cost", """
        def shipping_cost(weight_kg):
            extra = max(0, math.ceil(weight_kg - 2))
            return 5.0 + 1.5 * extra""")  # case 5
    r.doc("shipping_cost", "Flat 5.00 for parcels up to 2 kg, plus 1.50 for each started kilogram above 2 kg.")
    r.put(CALC, "parse_price", '''
        def parse_price(text):
            """Parse a price string such as "$1,234.50" into a float (1234.5).

            Raises ValueError if the string is empty.
            """
            text = text.strip()
            if not text:
                raise ValueError("empty price")
            return float(text.lstrip("$").replace(",", ""))''')  # case 7
    r.commit("WIP basics")
    r.put(CALC, "average_price", """
        def average_price(prices):
            if not prices:
                return 0.0
            return sum(prices) / len(prices)""")  # case 6
    r.commit("basics: handle empty price lists")
    r.merge("feat/basics")

    r.branch("feat/discount")
    r.put(CALC, "apply_discount", f"""
        def apply_discount(price, percent):
            {MARK}
            return max(0, price - percent)""")  # flat amount, not a percentage
    r.commit("Add apply_discount")
    r.merge("feat/discount")

    r.branch("feat/cart")
    r.put("app/cart.py", "Cart", """
        from dataclasses import dataclass, field


        @dataclass
        class Cart:
            items: list = field(default_factory=list)  # (unit_price, quantity) pairs

            def total(self):
                return sum(unit_price * quantity for unit_price, quantity in self.items)""")  # case 8
    r.doc("Cart.total", "Sum of unit price times quantity over every (unit_price, quantity) pair in the cart's items; 0 for an empty cart.")
    r.commit("Add Cart")
    r.merge("feat/cart")

    r.put(CALC, "clamp_value", f"""
        def clamp_value(x, lo, hi):
            {MARK}
            return min(x, hi)""")  # lower bound dropped
    r.commit("clamp: simplify")

    r.put(CALC, "with_tax", f"""
        def with_tax(amount, rate=0.08):
            {MARK}
            return round(amount * rate, 2)""")  # returns only the tax, docs untouched
    r.commit("tax: return tax amount")

    r.branch("feat/free-shipping")
    r.put(CALC, "shipping_cost", """
        def shipping_cost(weight_kg):
            if weight_kg < 0.5:
                return 0.0
            extra = max(0, math.ceil(weight_kg - 2))
            return 5.0 + 1.5 * extra""")
    r.doc("shipping_cost", "Free for parcels under 0.5 kg. Otherwise flat 5.00 up to 2 kg, plus 1.50 for each started kilogram above 2 kg.")
    r.commit("Free shipping for small parcels")  # code + docs in one commit
    r.merge("feat/free-shipping")

    r.put(CALC, "parse_price", f'''
        def parse_price(text):
            """Parse a price string such as "$1,234.50" into a float (1234.5).

            Raises ValueError if the string is empty.
            """
            text = text.strip()
            if not text:
                raise ValueError("empty price")
            {MARK}
            return int(float(text.lstrip("$").replace(",", "")))''')  # truncates cents, docstring untouched
    r.commit("parse_price: return whole units")

    return {
        "sum_two": ("BASELINE", None),
        "clamp_value": ("DRIFT", "modified_after_merge"),
        "apply_discount": ("DRIFT", "first_version_mismatch"),
        "with_tax": ("DRIFT", "modified_after_merge"),
        "shipping_cost": ("OK", None),
        "average_price": ("OK", None),
        "parse_price": ("DRIFT", "modified_after_merge"),
        "Cart.total": ("OK", None),
    }


def _head_functions(dest: str) -> dict[str, str]:
    found = {}
    for path in (CALC, "app/cart.py"):
        src = Path(dest, path).read_text()
        for node in ast.parse(src).body:
            defs = node.body if isinstance(node, ast.ClassDef) else [node]
            prefix = f"{node.name}." if isinstance(node, ast.ClassDef) else ""
            for d in defs:
                if isinstance(d, ast.FunctionDef):
                    found[prefix + d.name] = ast.get_source_segment(src, d)
    return found


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        dest = sys.argv[1] if len(sys.argv) > 1 else tmp
        assert not Path(dest).exists() or not any(Path(dest).iterdir()), f"{dest} is not empty"
        expected = make_fixture(dest)

        def git(*a): return subprocess.run(["git", "-C", dest, *a], check=True, capture_output=True, text=True).stdout

        assert len(expected) == 8
        assert git("rev-list", "--first-parent", "--count", "main").strip() == "8"
        assert git("rev-list", "--merges", "--count", "main").strip() == "4"
        assert "WIP basics" in git("log", "--format=%s", "main")
        assert "WIP basics" not in git("log", "--first-parent", "--format=%s", "main")

        funcs = _head_functions(dest)
        assert set(funcs) == set(expected), funcs.keys()
        drifting = {q for q, (verdict, _) in expected.items() if verdict == "DRIFT"}
        assert {q for q, src in funcs.items() if MARK in src} == drifting
        assert all(stub_judge(q, "", funcs[q]) == (0.0 if q in drifting else 1.0) for q in funcs)

        # docs must link only by intent: no section names another function's bare name
        api = Path(dest, "docs/api.md").read_text()
        for name, body in re.findall(r"^## `([^`]+)`\n\n(.*)$", api, re.M):
            for other in expected:
                if other != name:
                    bare = other.rsplit(".", 1)[-1]
                    assert not re.search(rf"(?<![\w.]){re.escape(bare)}(?!\w)", body), (name, other)
        assert not any(q in api for q in ("sum_two", "clamp_value", "parse_price"))

        for q, v in expected.items():
            print(f"{q:15} {v}")
        print("ok")
