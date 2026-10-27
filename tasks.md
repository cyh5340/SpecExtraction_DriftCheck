# Task List — Spec Extraction & Drift Check

Based on `design.md`. Stack: Python + git CLI + tree-sitter (`tree-sitter-language-pack`) for parsing any language. Linking functions to their specs is deterministic (exact text match). The only model call is the final yes/no question, "does this code match this spec?", sent to TypeSafe Jev (`typesafe-sdk`, model `jev-latest`) as a Noul. Usage is in `README.md`.

**First version** = the function as it was in the first commit that merged it into `main` (found by walking `git log --first-parent main`). Work-in-progress commits on feature branches don't count. "Creation" below means that merge.

## Verdicts the tool produces (per function)

| Verdict | Condition |
|---|---|
| `OK` | Current code matches its spec |
| `BASELINE` | No docs existed at creation, so the first version *is* the spec, and the current code still matches it |
| `DRIFT` | The code no longer matches its docs. The report gives one of three reasons: `first_version_mismatch` (docs existed at or before the merge, and the first version merged to main doesn't match them), `modified_after_merge` (the function changed later and no longer matches its current docs, or its first version when it has none), or `docs_changed_after_merge` (the docs changed later, the code didn't, and the two no longer match) |
| `UNKNOWN` | Not enough signal to decide: Jev's probability falls between the thresholds, or Jev rejected the request (e.g. input too long). Needs human review |

## Spec rule (implemented in `classify.py`)

- Spec priority: linked docs, then the docstring or the comment block above the function, then the first merged version itself.
- The first merged version is checked against the docs as they were at creation (Case B).
- The current code is checked against the current docs (Case C). So docs updated together with the code become the spec, and so do docs updated in a separate commit, before or after the code.
- No docs ever (Case A):
  - Unchanged code gives `BASELINE` without calling Jev.
  - A changed signature gives `DRIFT` without calling Jev.
  - Otherwise Jev compares the current code with the first merged version.
- Jev is called only when code or spec changed since the last check.

## Prototype plan — done

Goal (met): `python -m driftcheck --path tests/fixture/` produces a verdict per function as a JSON report, and `python tests/check_fixture.py` compares the verdicts with the expected ones using real Jev. First real run: 7/8 correct (see Known issues).

**Left out of the prototype:**
- **Inputs:** Jira/PR regex and PR text, OpenAPI specs.
- **Analysis:** rename/move tracking.
- **Output:** the Markdown summary.
- **Performance:** result caching, async calls.
- **Long input:** proper handling of input that's too long (such functions get `UNKNOWN`).

Docstring timestamps come from the function's own commit history, so `git blame` isn't needed. Doc section history comes from walking the file's versions on main, not `git log -L`.

| Wave | Task | File | Status |
|---|---|---|---|
| 0 | Shared data model (`Function`, `Version`, `DocSection`, `Spec`, `Result`) and `parse_functions(source, path)` for any language | `models.py` | done |
| 0 | Git helpers: `git()`, `ls_files(repo, suffix, branch, prefix)`, `file_versions()` (first-parent versions of a file on main) | `gitutil.py` | done |
| 1A | Inventory: every function in every source file at the tip of `main`, optionally under one folder | `inventory.py` | done |
| 1B | History: each function's versions on main (first merged version, then every code or docstring change) | `history.py` | done |
| 1C | Docs: split markdown into sections, track each section's versions on main, link sections to functions by exact name | `docs.py` | done |
| 1D | Jev judge: `judge(qualname, spec_text, code) -> float`, thresholds 0.7 / 0.3, loads `./.env` | `judge.py` | done |
| 1E | Signature check: `signature_changed(old, new)` | `inventory.py` | done |
| 1F | Fixtures, two of them: `tests/make_fixture.py` builds a throwaway repo whose mismatching code carries `# mismatch` markers for the stub judge; `tests/fixture/` is real-looking code committed to this repo's `main` (9 PR merges, Python + JS) with `expected.json` | `tests/` | done |
| 2 | Spec selection + classifier (Cases A, B, C, hash-skip, signature check, Jev call, request errors → `UNKNOWN`) | `classify.py` | done |
| 3A | CLI + JSON report: `python -m driftcheck [repo] [--branch] [--path] [--out]` | `__main__.py` | done |
| 3B | End-to-end test with the stub judge: `python -m driftcheck.classify` (8/8) | `classify.py` self-check | done |
| 3C | Real Jev run on `tests/fixture/`: `python tests/check_fixture.py` (7/8) | `tests/check_fixture.py` | done; thresholds not tuned yet |

## Phase 0: Decisions
- [x] Tool language: Python
- [x] Model: TypeSafe Jev via `typesafe-sdk` (`TypeSafeClient().system_one(...)` with a `Noul` question). The key is `TYPESAFE_API_KEY` and the model is `DRIFTCHECK_JEV_MODEL` (default `jev-latest`), read from the environment or `./.env` (template: `.env.example`). The account lists `jev-latest` and `jev-preview`.
- [x] Codebases analyzed: any language tree-sitter supports, detected from the file path.
  - Python files keep the stdlib `ast` parser.
  - Every other language uses the pack's `process()` structure output plus its comment nodes, with no per-language registration.
  - Grammars download on first use per language (network once, then cached).
  - Tested: Python, JavaScript, Go (Java and Rust probed).
- [x] Output format: a JSON report on stdout or `--out`, plus a one-line-per-function summary on stderr. Markdown summary later.
- [ ] Jira/PR integration: suggest later. v1 doesn't read PR/ticket IDs yet.

## Phase 1: Function inventory
- [x] CLI entry: `python -m driftcheck [repo] [--branch main] [--path folder] [--out report.json]`
- [x] List functions in every tracked source file (qualified name, file, line range, signature, code hash)
- [x] Docstring (Python) or the comment block above the function (other languages)

## Phase 2: Git history per function
- [x] Find the first version: the first first-parent commit on `main` that contains the function. Its contents are the baseline, and its date is the creation timestamp.
- [x] List every commit on main that changed the function's code or docstring (comment-only and formatting edits don't count)
- [ ] Handle renames/moves (a renamed function currently looks new)
- [ ] Pull PR numbers and Jira keys out of commit messages with a regex (`#123`, `ABC-123`)

## Phase 3: Documentation discovery and timestamps
- [x] Gather `*.md` files (all of them, or under `--path`)
- [x] Link each function to doc sections by exact identifier match (`func`, `Class.method`, `module.func`, inside or outside code spans), with no fuzzy matching. A bare name shared by several functions links to each of them.
- [x] Functions with no matching doc go to the docstring or baseline path
- [x] Timestamps per doc section, from the section's text changing between versions of the file on main
- [ ] OpenAPI specs and other non-markdown docs

## Phase 4: Spec extraction
- [x] 1. External docs linked to the function: the version current at creation (first check) and the current version (current check)
- [x] 2. Docstring/comment: the current one, dated from the version that introduced its text
- [x] 3. Neither: the code of the first version merged to main as the baseline spec
- [ ] PR/ticket text from the merge as extra baseline context
- [x] Specs stored as raw text, with no LLM: `Spec(qualname, source: doc|comment|baseline, source_ref, text, date)`

## Phase 5: Classification
- [x] Cases A, B and C as in the spec rule above
- [x] Deterministic signature check before calling Jev (baseline path)
- [x] Jev Noul: `state = {spec: {text}, code: {name, source}}`, asking whether `code.source` behaves as `spec.text` describes; the answer is the yes-probability
- [x] Probability to verdict: ≥ 0.7 match, ≤ 0.3 `DRIFT`, in between `UNKNOWN`
- [ ] Tune the thresholds on more labeled cases (only one run on 8 functions so far)
- [ ] Fix the `tests/fixture/src/strings.js::truncate` failure in `python tests/check_fixture.py`: expected `DRIFT` (`modified_after_merge`), got `UNKNOWN`. The only change was the truncation suffix `...` → `…` with docs untouched, and Jev's probability was 0.57, then 0.67 (unsure, and different between runs). Try rewording the Jev question/criteria so that any change to output values or text counts as "different", then rerun the check. Lowering thresholds for this one case doesn't count as a fix. Done when the check passes 8/8 on repeated runs.
- [x] Jev request errors (400/422, e.g. input too long) give `UNKNOWN` instead of stopping the scan; input is never truncated
- [x] Skip Jev when neither code nor spec changed since the last check

## Phase 6: Report
- [x] JSON report per function: verdict, reason, the spec (source, ref, text, date), Jev's probability, evidence (commit SHAs and doc refs)
- [ ] Markdown summary grouped by verdict

## Phase 7: Later
- [ ] GitHub/GitLab API: fetch PR title/body/review comments
- [ ] Jira API: fetch ticket description/acceptance criteria
- [ ] Cache Jev results by (spec hash, code hash)
- [ ] Use `AsyncTypeSafeClient` to check many functions concurrently on large repos
- [ ] Handle functions (spec + code) that exceed Jev's input limit. Today these get `UNKNOWN`. Find the actual limit, then try the `TypeSafe-Danger-Zone-Long-Context` header, or compare just the changed parts of the function.
- [ ] Qualify Go methods by receiver type (`S.M`, not `M`)

## Phase 8: Tests
- [x] Stub-judge end-to-end check: `python -m driftcheck.classify` builds `tests/make_fixture.py`'s repo and asserts all 8 verdicts
- [x] Real-Jev check: `python tests/check_fixture.py` compares `tests/fixture/` results with `expected.json`
- [x] Per-module self-checks: `python -m driftcheck.<module>` for models, gitutil, inventory, history, docs, judge

## Known issues
- **`truncate` (JS) comes back `UNKNOWN`, not `DRIFT`.** The only change was the suffix `...` → `…`. Jev's probability was 0.57, then 0.67, so its answers vary between runs. Option: reword the Jev question so that any change to output text counts as different.
- **The fixture's history is this project's history.** `tests/fixture/` was committed as 10 "Merge PR" commits on this project's `main`. Always scan it with `--path tests/fixture/`, or the tool's own code and these docs get scanned too. Moving the fixture to its own repo would be cleaner.
- **Doc linking limits.** Links are keyed by qualname, so same-named functions in different files share doc links. Bare-name matching on common words (`get`, `run`) can over-link. A deleted doc section still counts as current.
- **Parser limits.** Nested functions are part of their parent. Python definitions under module-level `if`/`try` are skipped. Redefinitions (e.g. a property getter and setter) share one qualname.
