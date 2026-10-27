"""Pick each function's spec and decide its verdict, asking Jev only when code or spec actually changed."""
from __future__ import annotations

from typesafe_sdk import TypeSafeBadRequestError, TypeSafeUnprocessableEntityError

from . import judge as jev
from .docs import doc_history, link
from .history import history
from .inventory import inventory, signature_changed
from .models import DocSection, Function, Result, Spec, Version


def classify(repo: str, branch: str = "main", prefix: str = "") -> list[Result]:
    """Verdict per function on `branch`, only for code and docs under the folder `prefix` when given."""
    functions = inventory(repo, branch, prefix)
    histories = {path: history(repo, path, branch) for path in {f.path for f in functions}}
    docs = doc_history(repo, branch, prefix)
    # ponytail: links are keyed by qualname, so same-named functions in different files share doc links
    links = link(docs, functions)
    return [_classify(histories[f.path][f.qualname], [docs[k] for k in links.get(f.qualname, [])]) for f in functions]


def _classify(versions: list[Version], sections: list[list[DocSection]]) -> Result:
    first, current = versions[0], versions[-1]
    fn, q = current.function, current.function.qualname
    evidence = list(dict.fromkeys([first.sha, current.sha]))
    # spec priority: linked docs > docstring/comment > the first merged version itself
    first_spec = _doc_spec(q, sections, first.date) or _docstring_spec(versions[:1])
    current_spec = _doc_spec(q, sections) or _docstring_spec(versions)
    code_changed = fn.code_hash != first.function.code_hash

    def result(verdict, reason=None, spec=None, p=None) -> Result:
        refs = [spec.source_ref] if spec and spec.source != "baseline" else []
        return Result(q, fn.path, verdict, reason if verdict == "DRIFT" else None, spec, p, evidence + refs)

    def decide(code: Function, spec: Spec, if_match: str, reason: str) -> Result:
        p = _ask(code, spec)
        return result({"match": if_match, "mismatch": "DRIFT"}.get(jev.outcome(p), "UNKNOWN"), reason, spec, p)

    if first_spec:  # Case B: a spec existed at creation, so the first merged version must match it
        checked = decide(first.function, first_spec, "OK", "first_version_mismatch")
        if checked.verdict != "OK" or (not code_changed and current_spec and current_spec.text == first_spec.text):
            return checked  # nothing changed since: no second Jev call
    if current_spec:  # Case C: current code against the current spec (docs updated with the code become the spec)
        return decide(fn, current_spec, "OK", "modified_after_merge" if code_changed else "docs_changed_after_merge")
    # Case A: no spec ever, so the first merged version is the spec
    baseline = Spec(q, "baseline", first.sha, first.function.source, first.date)
    if not code_changed:
        return result("BASELINE", spec=baseline)
    if signature_changed(first.function, fn):
        return result("DRIFT", "modified_after_merge", baseline)  # interface changed: no Jev call needed
    return decide(fn, baseline, "BASELINE", "modified_after_merge")


def _doc_spec(qualname: str, sections: list[list[DocSection]], at=None) -> Spec | None:
    """The linked doc sections as they stood at `at` (latest when None), combined into one spec."""
    # ponytail: doc_history never records a section's deletion, so a removed section still counts as current
    now = [s for s in (_at(versions, at) for versions in sections) if s]
    if not now:
        return None
    ref = ", ".join(f"{s.path}:{s.lineno}-{s.end_lineno}" for s in now)
    return Spec(qualname, "doc", ref, "\n\n".join(s.text for s in now), max(s.date for s in now))


def _at(versions: list[DocSection], at) -> DocSection | None:
    kept = [v for v in versions if at is None or v.date <= at]
    return kept[-1] if kept else None


def _docstring_spec(versions: list[Version]) -> Spec | None:
    """The latest docstring/leading comment, dated from the version that introduced that text."""
    text = versions[-1].function.docstring
    if not text:
        return None
    since = next(v for v in versions if v.function.docstring == text)
    return Spec(since.function.qualname, "comment", since.sha, text, since.date)


def _ask(code: Function, spec: Spec) -> float | None:
    try:
        return jev.judge(code.qualname, spec.text, code.source)
    except (TypeSafeBadRequestError, TypeSafeUnprocessableEntityError):
        return None  # e.g. input too long for Jev: the function becomes UNKNOWN instead of stopping the scan


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
    from make_fixture import make_fixture, stub_judge

    jev.judge = stub_judge
    with tempfile.TemporaryDirectory() as d:
        expected = make_fixture(d)
        got = {r.qualname: (r.verdict, r.reason) for r in classify(d)}
    assert got == expected, {q: (got.get(q), e) for q, e in expected.items() if got.get(q) != e}
    print("ok", file=sys.stderr)
