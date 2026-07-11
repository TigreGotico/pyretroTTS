"""Capture the oracle's per-clause `phclause` input for the grammar battery.

Drives the instrumented oracle over a battery that stresses exactly the paths
the word-level syntactic marking touches -- dictionary verbs (VPSTART),
closed-class prep-phrase words (`for`/`and`/`to`, PPSTART), prepositions,
function words, plurals, questions, numbers and abbreviations -- and records,
per text, the per-clause `symbols[]` stream the front end hands to `phclause`
(the pre-`ph/` boundary) plus whether the port reproduces it framing-exact and
voice-0 PCM-exact.

Only texts the port (`pyretrotts.dectalk.sentence_us`) reproduces framing-exact
are written under `exact`, so the CI gate bites on any regression; the rest are
recorded under `divergent` with the ported framing, for the record and the
measured per-category table in `test/test_dectalk_grammar.py`.

Usage:
    python3 tools/dump_dectalk_grammar.py [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.dectalk.dictionary import Dictionary  # noqa: E402
from pyretrotts.dectalk.sentence_us import (  # noqa: E402
    sentence_to_clauses,
    sentence_to_pcm,
)
from tools.dump_dectalk_phalloph import DIC_DIR  # noqa: E402
from tools.dump_dectalk_phonemes import capture  # noqa: E402

DEFAULT_OUT = os.path.join(
    os.path.dirname(__file__), "..", "test", "dectalk_grammar_golden.json")

# The per-category battery. Each list stresses one path that the word-level
# syntactic marking (grammar_us.py) reaches.
BATTERY: dict[str, list[str]] = {
    "plain": [
        "the cat sat", "hello world", "peter piper picked", "rain falls down",
        "the sun is bright", "the big brown fox", "sit down now",
        "good morning sunshine", "the little red hen", "fish swim deep",
        "time flies fast", "the quick brown fox jumps",
    ],
    "comma": ["yes, no, maybe", "red, green, blue", "one; two",
              "yes, no, maybe, sure"],
    "speller": ["cwm", "jwt", "tsktsk", "cwtch"],
    "numbers": ["5", "21", "99", "$5", "1st", "100", "123", "2005",
                "one hundred and five"],
    "questions": ["what time is it", "are you there", "what is that"],
    "abbrev": ["etc.", "doctor smith is here", "mister jones went home",
               "dr. smith"],
    "verbs": ["birds sing", "he went home", "she runs to the store",
              "i went to the park"],
    "funcword": ["you are here", "that is a cat", "give it to me",
                 "it is on the table"],
    "conj": ["a dog and a cat", "dogs and cats", "he runs and jumps",
             "run for the hills"],
}


def _pcm(u) -> bytes:
    return struct.pack(f"<{len(u.pcm)}h", *u.pcm)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    dic = os.path.join(DIC_DIR, "dtalk_us.dic")
    d = Dictionary.load(dic)
    exact: dict[str, list[list[int]]] = {}
    divergent: dict[str, dict] = {}
    pcm_exact: list[str] = []
    for texts in BATTERY.values():
        for text in texts:
            u = capture(0, text)
            if u is None:
                continue
            ref = [list(c.symbols) for c in u.clauses]
            mine = [list(c.symbols) for c in sentence_to_clauses(text, d)]
            if _pcm(u) == sentence_to_pcm(0, text, d):
                pcm_exact.append(text)
            if mine == ref:
                exact[text] = ref
            else:
                divergent[text] = {"ref": ref, "mine": mine}

    with open(args.out, "w") as f:
        json.dump({"battery": BATTERY, "exact": exact,
                   "divergent": divergent, "pcm_exact": sorted(pcm_exact)},
                  f, indent=1)
    print(f"wrote {args.out}: {len(exact)} framing-exact, "
          f"{len(pcm_exact)} voice-0 pcm-exact, {len(divergent)} divergent")


if __name__ == "__main__":
    main()
