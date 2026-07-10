"""CI gate for the DECtalk F0/intonation stage: a digest over real intonation
captures from the C oracle, no C build required.

`dectalk_intonation_golden.json` is anchored to the C oracle at write time (see
`dectalk_intonation_golden.py`; `--write` refuses unless the port reproduces the
oracle `f0tar`/`f0tim` and per-frame `T0`/`f0prime` field for field over ten
voices). This test guards against drift in the ported `phinton`/`pht0draw` rules
and the F0 ROM tables they read.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from dectalk_intonation_golden import VECTORS_PATH, digest, load


def test_intonation_matches_golden():
    assert digest() == load()["sha256"]


def test_golden_bites_on_a_phinton_mutation():
    import pyretrotts.dectalk.intonation as intonation

    baseline = digest()
    original = intonation.US_F0_STRESS_LEVEL
    intonation.US_F0_STRESS_LEVEL = (1, 72, 31, 281)
    try:
        assert digest() != baseline
    finally:
        intonation.US_F0_STRESS_LEVEL = original
    assert digest() == baseline


def test_golden_bites_on_a_pht0draw_mutation():
    import pyretrotts.dectalk.intonation as intonation

    baseline = digest()
    original = intonation.GETCOSINE
    intonation.GETCOSINE = tuple(v + 1 for v in original)
    try:
        assert digest() != baseline
    finally:
        intonation.GETCOSINE = original
    assert digest() == baseline


def test_vectors_are_real_multi_voice_captures():
    utts = json.load(open(VECTORS_PATH))
    assert {u["sp"] for u in utts} == set(range(10))
    seen_multi_clause = False
    for u in utts:
        assert u["clauses"]
        if len(u["clauses"]) > 1:
            seen_multi_clause = True
        for cl in u["clauses"]:
            # Real capture: font-coded phone stream, f0mode NORMAL, durations present.
            assert cl["f0mode"] == 1
            assert len(cl["allodurs_in"]) == cl["nallotot_in"]
            assert all(p == 0 or (p & 0xFF00) == 0x1E00 for p in cl["allophons_in"])
            # phinton inserts phones: the output stream is >= the input length.
            assert cl["nallotot_out"] >= cl["nallotot_in"]
    assert seen_multi_clause


def test_f0_tables_shape():
    from pyretrotts.dectalk.intonation import (
        GETCOSINE,
        NOTETAB,
        US_F0_PHRASE_POSITION,
        US_F0_STRESS_LEVEL,
        US_F0SEGTARS,
    )

    assert len(US_F0SEGTARS) == 57
    assert len(GETCOSINE) == 64
    assert len(NOTETAB) == 37
    assert US_F0_STRESS_LEVEL == (1, 71, 31, 281)
    assert US_F0_PHRASE_POSITION == (210, 90, 60, 40, 0)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
