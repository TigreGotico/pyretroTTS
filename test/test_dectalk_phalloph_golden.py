"""CI gate for the DECtalk `phsort`/`phalloph` allophone stage: a digest over
real allophone-stage inputs captured from the C oracle, no C build required.

`dectalk_phalloph_golden.json` is anchored to the C oracle at write time (see
`dectalk_phalloph_golden.py`; `--write` refuses unless the port reproduces the
oracle `phonemes`/`sentstruc`/`allophons`/`allofeats` field for field over ten
voices). This test guards against drift in the ported allophone-selection rules.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from dectalk_phalloph_golden import VECTORS_PATH, digest, load


def test_phsort_phalloph_matches_golden():
    assert digest() == load()["sha256"]


def test_golden_bites_on_a_rule_mutation():
    import pyretrotts.dectalk.allophones as allophones

    baseline = digest()
    original = allophones.BOUNFTAB
    allophones.BOUNFTAB = tuple(v + 0o40 for v in original)
    try:
        assert digest() != baseline
    finally:
        allophones.BOUNFTAB = original
    assert digest() == baseline


def test_golden_bites_on_an_allophone_mutation():
    import pyretrotts.dectalk.allophones as allophones

    baseline = digest()
    original = allophones.USP_LX
    allophones.USP_LX = allophones.USP_LL
    try:
        assert digest() != baseline
    finally:
        allophones.USP_LX = original
    assert digest() == baseline


def test_vectors_are_real_multi_voice_captures():
    vecs = json.load(open(VECTORS_PATH))
    assert len(vecs) >= 10
    for v in vecs:
        assert v["nallotot"] == len(v["allophons"])
        # Real capture: phone streams are font-coded (0x1E00 | idx) or silence.
        assert all(p == 0 or (p & 0xFF00) == 0x1E00 for p in v["phonemes"])
        assert all(p == 0 or (p & 0xFF00) == 0x1E00 for p in v["allophons"])
        # Input symbols carry the control codes phsort folds into sentstruc.
        assert any(100 <= (s & 0xFF) <= 122 for s in v["symbols"])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
