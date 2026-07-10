"""Bit-exact regression gate over the DECtalk `phdraw` frame drawer.

Fails on a single differing drawn parameter over the fixed synthetic frame
vector. Needs no C reference, so it runs in CI; the digest in
dectalk_ph_golden.json was written only after the ported drawer matched the
instrumented C oracle frame for frame on real utterances, for all ten voices
(see dectalk_ph_golden.py and test_dectalk_ph.py).
"""
from dectalk_ph_golden import digest, load


def test_golden_file_has_synth_digest():
    assert set(load()) == {"synth_draw"}


def test_drawn_params_match_golden():
    assert digest() == load()["synth_draw"], (
        "Drawn parameters changed. The frame drawer is deterministic, so this "
        "means the output differs from the C-anchored reference. Fix the "
        "regression -- do not regenerate dectalk_ph_golden.json."
    )


def test_drawer_is_deterministic():
    assert digest() == digest()
