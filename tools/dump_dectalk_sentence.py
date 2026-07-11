"""Capture the oracle's per-clause `phclause` input for a sentence set.

Drives the instrumented oracle over a varied sentence set (multi-word
statements, comma/semicolon lists, questions, numbers, abbreviations, and a
vowelless speller word) and writes, per text, the per-clause `symbols[]` stream
the front end hands to `phclause` -- the pre-`ph/` boundary. The result gates
`test/test_dectalk_sentence.py` in CI without the oracle.

Only texts the ported front end (`pyretrotts.dectalk.sentence_us`) reproduces
bit-exactly are written, so the gate bites on any framing regression; the
remaining texts are recorded under `divergent` with the reason, for the record.

Usage:
    python3 tools/dump_dectalk_sentence.py [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.dectalk.dictionary import Dictionary  # noqa: E402
from pyretrotts.dectalk.sentence_us import sentence_to_clauses  # noqa: E402
from tools.dump_dectalk_phonemes import capture  # noqa: E402

DEFAULT_OUT = os.path.join(
    os.path.dirname(__file__), "..", "test", "dectalk_sentence_golden.json")
DIC = os.path.expanduser(
    "~/AgentWorkspaces/ovos/dectalk-c/dist/dic/dtalk_us.dic")

# A varied set spanning every framing path the port claims to reproduce.
TEXTS = [
    "hello world", "the cat sat", "one two three", "peter piper picked",
    "rain falls down", "the sun is bright", "the big brown fox", "sit down now",
    "good morning sunshine", "the little red hen", "fish swim deep",
    "time flies fast", "stop", "what time is it",
    "yes, no, maybe", "red, green, blue", "one; two", "yes, no, maybe, sure",
    "cwm", "jwt", "tsktsk", "cwtch",
    "5", "21", "99", "$5", "1st",
    "etc.",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    d = Dictionary.load(DIC)
    exact: dict[str, list[list[int]]] = {}
    divergent: dict[str, list[list[int]]] = {}
    for text in TEXTS:
        u = capture(0, text)
        if u is None:
            continue
        ref = [list(c.symbols) for c in u.clauses]
        mine = [list(c.symbols) for c in sentence_to_clauses(text, d)]
        (exact if mine == ref else divergent)[text] = ref

    with open(args.out, "w") as f:
        json.dump({"exact": exact, "divergent": divergent}, f, indent=1)
    print(f"wrote {args.out}: {len(exact)} exact, {len(divergent)} divergent")


if __name__ == "__main__":
    main()
