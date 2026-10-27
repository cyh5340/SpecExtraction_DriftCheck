"""Run driftcheck with real Jev on tests/fixture/ (committed to this repo's main) and compare with expected.json.

Usage: python tests/check_fixture.py    (needs TYPESAFE_API_KEY in the environment or ./.env)
Exits 1 if any function's verdict, reason or spec source differs from expected.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = "tests/fixture/"
sys.path.insert(0, str(ROOT))

from driftcheck.classify import classify  # noqa: E402

expected = json.loads((ROOT / FIXTURE / "expected.json").read_text(encoding="utf-8"))
got = {f"{r.path}::{r.qualname}": r for r in classify(str(ROOT), "main", FIXTURE)}
keys = sorted(expected.keys() | got.keys())

failures = 0
for key in keys:
    want, r = expected.get(key), got.get(key)
    if want is None or r is None:
        failures += 1
        print(f"FAIL {key}: {'not in expected.json' if want is None else 'not found by driftcheck'}")
        continue
    actual = (r.verdict, r.reason, r.spec.source if r.spec else None)
    wanted = (want["verdict"], want.get("reason"), want["spec_source"])
    ok = actual == wanted
    failures += not ok
    p = "" if r.probability is None else f"p={r.probability:.2f}"
    print(f"{'ok  ' if ok else 'FAIL'} {key:45} {'/'.join(map(str, actual)):45} {p:7}" + ("" if ok else f" expected {'/'.join(map(str, wanted))}"))

print(f"\n{len(keys) - failures}/{len(keys)} match")
sys.exit(1 if failures else 0)
