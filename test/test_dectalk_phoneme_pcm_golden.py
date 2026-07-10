"""CI gate for the DECtalk phoneme -> PCM chain: a digest over real per-clause
`symbols[]` streams captured from the C oracle, no C build required.

`dectalk_phoneme_pcm_golden.json` is anchored to the C oracle at write time (see
`dectalk_phoneme_pcm_golden.py`; `--write` refuses unless the port reproduces the
oracle WAV sample for sample over ten voices). This test guards against drift in
the composed `ph/` chain -- `phsort`, `phalloph`, `us_phtiming`, `phinton`,
`phsettar`, the per-frame `phdraw`/`pht0draw`/`send_pars` loop, and `vtm`.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from dectalk_phoneme_pcm_golden import VECTORS_PATH, digest, load


def test_phoneme_pcm_matches_golden():
    assert digest() == load()["sha256"]


def test_golden_bites_on_a_speaker_mutation():
    import pyretrotts.dectalk.phclause as phclause

    baseline = digest()
    original = phclause.PH_SPEAKERS
    mutated = list(original)
    s0 = mutated[0]
    mutated[0] = phclause.PhSpeaker(
        s0.malfem, s0.spdefb1off, s0.f0_dep_tilt, s0.spdeftltoff,
        s0.spdeflaxprcnt, s0.f0basefall, s0.f0_lp_filter, s0.f0minimum + 50,
        s0.f0scalefac, s0.size_hat_rise, s0.scale_str_rise, s0.assertiveness)
    phclause.PH_SPEAKERS = tuple(mutated)
    try:
        assert digest() != baseline
    finally:
        phclause.PH_SPEAKERS = original
    assert digest() == baseline


def test_vectors_are_real_captures():
    vecs = json.load(open(VECTORS_PATH))
    assert len(vecs) >= 10
    for v in vecs:
        assert v["clauses"]
        for c in v["clauses"]:
            assert len(c["symbols"]) == len(c["user_durs"])
            # Real capture: phones are font-coded (0x1E00 | idx) and each clause
            # opens with the GEN_SIL boundary phone.
            assert c["symbols"][0] == 0x1E00
            assert any((s & 0xFF00) == 0x1E00 for s in c["symbols"])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
