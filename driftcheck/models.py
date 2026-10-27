"""Shared data model, plus the one parser every stage uses (inventory, history, signature check)."""
from __future__ import annotations

import ast
import copy
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

import tree_sitter_language_pack as tslp

SpecSource = Literal["doc", "comment", "baseline"]
Verdict = Literal["OK", "BASELINE", "DRIFT", "UNKNOWN"]
DriftReason = Literal["first_version_mismatch", "modified_after_merge", "docs_changed_after_merge"]


@dataclass(frozen=True)
class Function:
    qualname: str  # "func" or "Class.method"
    path: str  # repo-relative, forward slashes
    lineno: int
    end_lineno: int
    args: str  # Python: ast.unparse of the parameters ("a, b=1, *, c"); other languages: the whole signature line
    returns: str | None  # Python: the return annotation; other languages: None (it's part of `args`)
    docstring: str | None  # Python docstring, or the comment block directly above the function
    code_hash: str  # formatting and comment edits don't change it
    source: str  # source text of the def


@dataclass(frozen=True)
class Version:
    """A function as it was in one first-parent commit on main."""
    sha: str
    date: datetime
    message: str
    function: Function


@dataclass(frozen=True)
class DocSection:
    """A markdown section (heading to next heading) as it was in one commit."""
    path: str
    heading: str
    lineno: int
    end_lineno: int
    text: str
    sha: str
    date: datetime


@dataclass(frozen=True)
class Spec:
    qualname: str
    source: SpecSource
    source_ref: str  # "docs/api.md:10-24" or a commit SHA
    text: str
    date: datetime


@dataclass
class Result:
    qualname: str
    path: str
    verdict: Verdict
    reason: DriftReason | None = None
    spec: Spec | None = None
    probability: float | None = None  # Jev's P(code matches spec); None when Jev wasn't asked
    evidence: list[str] = field(default_factory=list)  # commit SHAs and doc refs


NOT_CODE = {"markdown", "json", "yaml", "toml", "xml", "html", "css", "csv", "ini", "rst", "dockerfile", "make"}
FUNCTION_KINDS = {"Function", "Method"}  # str() of tslp's StructureKind; its class attributes aren't comparable values
COMMENT_STARTS = ("//", "/*", "*", "#", "--", ";")


def language(path: str) -> str | None:
    """Tree-sitter language name for a source file, or None for unknown and non-code files."""
    lang = tslp.detect_language_from_path(path)
    return None if lang in NOT_CODE else lang


def parse_functions(source: str, path: str = "x.py") -> list[Function]:
    """Every top-level function and class/impl/struct method in `source`, for any tree-sitter language.

    Functions nested inside functions are part of their parent's body, not listed separately.
    Python raises SyntaxError on invalid code; other languages return what they can parse.
    """
    lang = language(path)
    if lang == "python":
        return _parse_python(source, path)
    return _parse_tree_sitter(source, path, lang) if lang else []


def _parse_tree_sitter(source: str, path: str, lang: str) -> list[Function]:
    # ponytail: grammars download on first use per language (needs network once, then cached).
    # Go methods are named without their receiver type ("M", not "S.M"); qualify them if real repos collide.
    data = source.encode()
    comments = []

    def collect(node) -> None:
        if "comment" in node.type:
            comments.append((node.start_byte, node.end_byte))
        for child in node.children:
            collect(child)

    collect(tslp.get_parser(lang).parse(data).root_node)
    lines = source.splitlines()
    found: list[Function] = []

    def visit(items, prefix: str) -> None:
        for item in items:
            if str(item.kind) in FUNCTION_KINDS and item.name and item.span:
                found.append(_ts_function(item, prefix + item.name, path, data, comments, lines))
            elif item.children:
                visit(item.children, f"{prefix}{item.name}." if item.name else prefix)

    config = tslp.ProcessConfig(language=lang, imports=False, exports=False)
    visit(tslp.process(source, config).structure, "")
    return found


def _ts_function(item, qualname: str, path: str, data: bytes, comments, lines: list[str]) -> Function:
    start, end = item.span.start_byte, item.span.end_byte
    code = b"".join(  # the function's bytes with its comments cut out
        data[a:b] for a, b in zip([start] + [e for s, e in comments if start <= s < end],
                                  [s for s, e in comments if start <= s < end] + [end])
    ).decode()
    return Function(
        qualname=qualname,
        path=path,
        lineno=item.span.start_line + 1,
        end_lineno=item.span.end_line + 1,
        args=" ".join((item.signature or "").split()),
        returns=None,
        docstring=item.doc_comment or _comment_above(lines, item.span.start_line),
        code_hash=hashlib.sha256(" ".join(code.split()).encode()).hexdigest(),
        source=data[start:end].decode(),
    )


def _comment_above(lines: list[str], start_line: int) -> str | None:
    """The comment block directly above line `start_line` (0-based), skipping attribute/annotation lines."""
    block = []
    for line in reversed(lines[:start_line]):
        stripped = line.strip()
        if stripped.startswith(("@", "#[")):
            continue
        if not stripped.startswith(COMMENT_STARTS):
            break
        block.append(stripped)
    return "\n".join(reversed(block)) or None


def _parse_python(source: str, path: str) -> list[Function]:
    # ponytail: defs under module-level if/try blocks are skipped, and redefinitions (e.g. property
    # getter + setter) appear twice under one qualname; handle these if real repos need it
    found: list[Function] = []

    def visit(body: list[ast.stmt], prefix: str) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                visit(node.body, f"{prefix}{node.name}.")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found.append(_function(node, prefix + node.name, path, source))

    visit(ast.parse(source).body, "")
    return found


def _function(node: ast.FunctionDef | ast.AsyncFunctionDef, qualname: str, path: str, source: str) -> Function:
    doc = ast.get_docstring(node)
    stripped = copy.copy(node)
    stripped.body = node.body[1:] if doc is not None else node.body
    return Function(
        qualname=qualname,
        path=path,
        lineno=node.lineno,
        end_lineno=node.end_lineno,
        args=ast.unparse(node.args),
        returns=ast.unparse(node.returns) if node.returns else None,
        docstring=doc,
        code_hash=hashlib.sha256(ast.dump(stripped).encode()).hexdigest(),
        source=ast.get_source_segment(source, node),
    )


if __name__ == "__main__":
    src = '''
def top(a, b=1) -> int:
    """Add."""
    return a + b

class C:
    async def m(self):
        def inner(): pass
        return inner
'''
    fns = {f.qualname: f for f in parse_functions(src, "x.py")}
    assert set(fns) == {"top", "C.m"}, fns
    assert fns["top"].args == "a, b=1" and fns["top"].returns == "int"
    assert fns["top"].docstring == "Add." and fns["C.m"].docstring is None
    assert fns["top"].source.startswith("def top") and fns["top"].lineno == 2
    # docstring, formatting and comment edits keep the hash; a code edit changes it
    reformatted = parse_functions('def top(a, b = 1) -> int:\n    """Changed."""\n    return a+b  # note\n')[0]
    assert reformatted.code_hash == fns["top"].code_hash
    changed = parse_functions('def top(a, b=1) -> int:\n    """Add."""\n    return a - b\n')[0]
    assert changed.code_hash != fns["top"].code_hash

    # other languages go through tree-sitter
    js = parse_functions(
        "/** Adds two. */\nfunction add(a, b = 1) { return a + b; }\n"
        "class Cart {\n  // Sum of prices.\n  total(items) { const f = () => 1; return 0; }\n}\n",
        "web/cart.js",
    )
    jfns = {f.qualname: f for f in js}
    assert set(jfns) == {"add", "Cart.total"}, jfns  # the arrow function nested in total isn't listed
    assert jfns["add"].docstring == "/** Adds two. */" and jfns["Cart.total"].docstring == "// Sum of prices."
    assert jfns["add"].args == "function add(a, b = 1)" and jfns["add"].lineno == 2
    reformatted = parse_functions("function add(a, b = 1) {\n  // note\n  return a + b;\n}\n", "x.js")[0]
    assert reformatted.code_hash == jfns["add"].code_hash
    assert parse_functions("function add(a, b = 1) { return a - b; }\n", "x.js")[0].code_hash != jfns["add"].code_hash
    go = parse_functions("package p\n\n// Add adds.\n// Twice.\nfunc Add(a int, b int) int { return a + b }\n", "p.go")
    assert [(f.qualname, f.docstring) for f in go] == [("Add", "// Add adds.\n// Twice.")], go
    assert parse_functions("# Title\n", "README.md") == [] and parse_functions("x", "data.unknownext") == []
    print("ok")
