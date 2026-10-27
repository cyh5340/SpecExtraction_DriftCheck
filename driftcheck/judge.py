"""The one model call: ask Jev whether a function's code matches its spec text."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from typesafe_sdk import Noul, TypeSafeClient


def _load_dotenv(path: str = ".env") -> None:
    """KEY=VALUE lines from ./.env into os.environ. Variables already set in the environment win."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return
    for line in lines:
        key, sep, value = line.partition("=")
        if sep and key.strip() and not key.lstrip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_dotenv()
MODEL = os.environ.get("DRIFTCHECK_JEV_MODEL", "jev-latest")
MATCH_AT = 0.7  # docs' starting thresholds; tune on the fixture repo
MISMATCH_AT = 0.3

QUESTION = Noul(
    instructions="Does the function in `code.source` behave as `spec.text` describes, "
    "including its inputs, outputs and behavior?",
    criteria={
        "true": "The code does what the spec describes: same inputs, outputs and behavior.",
        "false": "The code contradicts the spec or does something different from what it describes.",
    },
)


def judge(qualname: str, spec_text: str, code: str) -> float | None:
    """Jev's probability that `code` matches `spec_text`. The input is never truncated.

    Always returns a float today: the API has no documented "input too long" error to map to None,
    so oversized input raises like any other API error.
    """
    # ponytail: no too-long handling; see the tasks.md Phase 7 item once the real limit is known
    with TypeSafeClient() as client:
        response = client.system_one(
            state={"spec": {"text": spec_text}, "code": {"name": qualname, "source": code}},
            questions={"matches": QUESTION},
            model=MODEL,
        )
    return response.nouls["matches"].noul


def outcome(p: float | None) -> Literal["match", "mismatch", "unknown"]:
    if p is None:
        return "unknown"
    if p >= MATCH_AT:
        return "match"
    if p <= MISMATCH_AT:
        return "mismatch"
    return "unknown"


if __name__ == "__main__":
    assert outcome(0.7) == "match" and outcome(0.3) == "mismatch"
    assert outcome(0.5) == "unknown" and outcome(None) == "unknown"
    if os.environ.get("TYPESAFE_API_KEY"):
        code = "def add(a, b):\n    return a + b\n"
        print("match:", judge("add", "Returns the sum of a and b.", code))
        print("mismatch:", judge("add", "Returns a minus b.", code))
    else:
        print("live check skipped: TYPESAFE_API_KEY not set")
    print("ok")
