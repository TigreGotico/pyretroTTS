"""Bit-exact regression gate over the DECtalk vocal tract model.

Fails on a single differing PCM byte, for any of the ten voices over the fixed
synthetic frame vector. Needs no C reference, so it runs in CI; the digests in
dectalk_golden.json were written only after the ported engine matched the
instrumented C oracle sample for sample on real utterances (see dectalk_golden.py
and test_dectalk_oracle.py).
"""
import pytest
from dectalk_golden import digest, load

from pyretrotts.dectalk.voices import VOICE_NAMES

GOLDENS = load()


def test_golden_file_covers_every_voice():
    assert set(GOLDENS) == set(VOICE_NAMES)


@pytest.mark.parametrize("voice", VOICE_NAMES)
def test_pcm_matches_golden(voice):
    index = VOICE_NAMES.index(voice)
    assert digest(index) == GOLDENS[voice], (
        f"PCM changed for {voice}. Synthesis is deterministic, so this means "
        f"the audio differs from the C-anchored reference. Fix the regression "
        f"-- do not regenerate dectalk_golden.json."
    )


def test_synthesis_is_deterministic():
    assert digest(0) == digest(0)
