# driftcheck

Checks whether each function in a git repository still matches its original spec, and flags drift. The design is in `design.md`, and the task list and status are in `tasks.md`.

For every function on `main`, driftcheck:

1. Finds its spec: linked markdown docs, then its docstring or the comment block above it, then its first version merged to `main`.
2. Uses git history to work out what existed when: when the function was first merged, when it changed, and when its docs changed.
3. Asks TypeSafe Jev one yes/no question, "does this code behave as this spec describes?", but only when code or spec actually changed.

It works on any language tree-sitter supports. Python uses the stdlib `ast` parser.

## Setup

```
pip install -e .
cp .env.example .env    # then fill in TYPESAFE_API_KEY
```

| Variable | Meaning |
|---|---|
| `TYPESAFE_API_KEY` | TypeSafe API key (required for real runs) |
| `DRIFTCHECK_JEV_MODEL` | Jev model name, default `jev-latest` (`jev-preview` also exists) |

Values come from the environment or from `./.env`, and the environment takes priority. `.env` is gitignored. Tree-sitter grammars download on first use per language, which needs network access once.

## Usage

```
python -m driftcheck [repo] [--branch main] [--path folder] [--out report.json]
```

- `repo`: the git repository to check (default: current directory)
- `--path`: only check code and docs under this folder
- `--out`: write the JSON report to a file instead of stdout. A one-line summary per function always goes to stderr.

Example, run on this repo's test fixture:

```
python -m driftcheck --path tests/fixture/
```

## Verdicts

| Verdict | Meaning |
|---|---|
| `OK` | Current code matches its spec |
| `BASELINE` | No docs ever; the current code still behaves like its first merged version |
| `DRIFT` | Doesn't match. The reason is `first_version_mismatch`, `modified_after_merge` or `docs_changed_after_merge` |
| `UNKNOWN` | Jev was unsure (probability between 0.3 and 0.7) or rejected the request; needs human review |

Each JSON result has `qualname`, `path`, `verdict`, `reason`, `spec` (source `doc`/`comment`/`baseline`, ref, text, date), `probability` (Jev's yes-probability, or null when Jev wasn't asked) and `evidence` (commit SHAs and doc refs).

## Tests

```
python tests/check_fixture.py    # real Jev on tests/fixture/, compared with expected.json (~10 Jev calls)
python -m driftcheck.classify    # stub judge on a generated repo, no API key needed
python -m driftcheck.models      # per-module self-checks: models, gitutil, inventory, history, docs, judge
```

## Layout

| File | Role |
|---|---|
| `driftcheck/models.py` | Data model and the multi-language function parser |
| `driftcheck/gitutil.py` | git helpers (first-parent file versions on main) |
| `driftcheck/inventory.py` | Current functions; signature check |
| `driftcheck/history.py` | Each function's versions on main |
| `driftcheck/docs.py` | Markdown sections, their history, exact-name links to functions |
| `driftcheck/judge.py` | The Jev call and thresholds |
| `driftcheck/classify.py` | Spec selection and verdicts |
| `driftcheck/__main__.py` | Command line |
| `tests/fixture/` | Test code with history on this repo's `main`, plus `expected.json` |
| `tests/make_fixture.py` | Builds a throwaway test repo for the stub judge |
| `tests/check_fixture.py` | Real-Jev fixture check |

Known issues and limits are listed in `tasks.md`.
