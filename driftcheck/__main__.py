"""python -m driftcheck [repo] [--branch main] [--path folder] [--out report.json]"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .classify import classify


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="driftcheck", description="Check whether each function still matches its original spec.")
    ap.add_argument("repo", nargs="?", default=".", help="git repository to check (default: current directory)")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--path", default="", help="only check code and docs under this folder")
    ap.add_argument("--out", help="write the JSON report to this file instead of stdout")
    args = ap.parse_args(argv)

    results = classify(args.repo, args.branch, args.path)
    report = json.dumps([asdict(r) for r in results], indent=2, default=str)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
    else:
        print(report)
    for r in results:  # human summary on stderr, so stdout stays pure JSON
        p = "" if r.probability is None else f"p={r.probability:.2f}"
        print(f"{r.verdict:9} {r.reason or '':25} {p:7} {r.path}::{r.qualname}", file=sys.stderr)


if __name__ == "__main__":
    main()
