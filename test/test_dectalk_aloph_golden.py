"""CI gate for the DECtalk `us_phtiming` duration stage: a digest over real
allophone-stage inputs captured from the C oracle, no C build required.

`dectalk_aloph_golden.json` is anchored to the C oracle at write time (see
`dectalk_aloph_golden.py`; `--write` refuses unless the port reproduces the
oracle `allodurs` field for field over ten voices). This test guards against
drift in the ported duration rules and the timing ROM they read.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from dectalk_aloph_golden import VECTORS_PATH, digest, load


def test_us_phtiming_matches_golden():
    assert digest() == load()["sha256"]


def test_golden_bites_on_a_rule_mutation():
    import pyretrotts.dectalk.timing as timing

    baseline = digest()
    original = timing.NF40MS
    timing.NF40MS = original + 1
    try:
        assert digest() != baseline
    finally:
        timing.NF40MS = original
    assert digest() == baseline


def test_vectors_are_real_multi_voice_captures():
    vecs = json.load(open(VECTORS_PATH))
    assert len(vecs) >= 10
    # Real capture: durations present, phone stream font-coded (0x1E00 | idx).
    assert {v["sp"] for v in vecs} == set(range(10))
    for v in vecs:
        assert len(v["allodurs"]) == v["nallotot"]
        assert all(p == 0 or (p & 0xFF00) == 0x1E00 for p in v["allophons_in"])


def test_min_and_inherent_duration_tables_shape():
    from pyretrotts.dectalk.targets_transitions import US_INHDR
    from pyretrotts.dectalk.timing import US_MINDUR

    assert len(US_MINDUR) == 57
    assert len(US_INHDR) == 57
    assert US_MINDUR[0] == 7 and US_INHDR[0] == 205


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
