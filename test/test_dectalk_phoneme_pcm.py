"""Phoneme stream -> PCM for the DECtalk port, diffed sample-for-sample vs the oracle.

Drives the whole `ph/` chain in Python -- `phclause.speak_phonemes`
(`phsort -> phalloph -> us_phtiming -> phinton -> per-frame loop -> vtm`) -- over
the phoneme+stress+sentence-structure `symbols[]` stream the oracle emits per
clause (captured at the `phclause` input boundary), for all ten voices over a
varied utterance set, and diffs the resulting PCM against the oracle WAV sample
for sample.

This is the milestone: phoneme-to-speech composed entirely in Python, with only
the front-of-`ph/` text layer (`lts/`/`cmd/`) borrowed from the oracle as the
`symbols[]` input. Every downstream stage runs in the port.

Skips when the instrumented `say` is absent.

Usage:
    DECTALK_SAY=.../say ... python3 test/test_dectalk_phoneme_pcm.py
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.dectalk.phclause import Clause, speak_phonemes
from tools.dump_dectalk_phonemes import ORACLE_BIN, capture

TEXTS = [
    "a test one two three",             # statement
    "hello there my name is paul",      # statement
    "the fish shifts sixty seven",      # fricative clusters
    "many men running homeward",        # nasals
    "the quick brown fox jumps",        # plosive clusters
    "ready to go, he wants to eat",     # comma clause, function words
    "strength of the people",           # consonant cluster
    "little butter kitty water",        # flapping
    "for the win, out of the box",      # function words, comma
    "is it ready? stop that now!",      # question + exclamation (multi-clause)
    "what is that? really?",            # two questions
    "no. absolutely not. never again.",  # three short clauses
    "hello there. how are you?",        # statement then question
]


def _run() -> tuple[int, int, int, int]:
    cases = exact = 0
    samp_total = samp_bad = 0
    for sp in range(10):
        for tx in TEXTS:
            u = capture(sp, tx)
            if u is None:
                continue
            cases += 1
            my = speak_phonemes(
                sp, [Clause(c.symbols, c.user_durs) for c in u.clauses])
            n = min(len(my), len(u.pcm))
            bad = sum(1 for a, b in zip(my[:n], u.pcm[:n], strict=False) if a != b)
            bad += abs(len(my) - len(u.pcm))
            samp_total += max(len(my), len(u.pcm))
            samp_bad += bad
            if bad == 0:
                exact += 1
    return cases, exact, samp_total, samp_bad


@pytest.mark.skipif(
    not ORACLE_BIN or not os.path.exists(ORACLE_BIN),
    reason="instrumented DECtalk oracle not built (set DECTALK_SAY)")
def test_phoneme_pcm_matches_oracle():
    cases, exact, samp_total, samp_bad = _run()
    assert cases > 0
    assert samp_bad == 0, f"{samp_bad}/{samp_total} PCM samples differ"
    assert exact == cases, f"{cases - exact}/{cases} cases not sample-exact"


def run() -> int:
    if not ORACLE_BIN or not os.path.exists(ORACLE_BIN):
        print(f"SKIP: no instrumented oracle at {ORACLE_BIN!r} (set DECTALK_SAY)")
        return 0
    cases, exact, samp_total, samp_bad = _run()
    print(f"phoneme -> PCM: {exact}/{cases} cases sample-exact "
          f"({samp_total - samp_bad}/{samp_total} samples), 10 voices")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
