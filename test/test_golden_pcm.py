"""Bit-exact regression gate over the whole synthesis pipeline.

Fails on a single differing PCM byte, for any of the 17 voices across every
frontend feature. Unlike `test_voices.py` this needs no compiled C reference,
so it runs in CI -- see `golden.py` for how the digests relate to the C engine.
"""
import pytest
from golden import TEXTS, VOICES, digest, load

GOLDENS = load()

CASES = [
    (voice_name, text_name)
    for voice_name in VOICES
    for text_name in TEXTS
]


def test_golden_file_covers_every_voice_and_text():
    assert set(GOLDENS) == set(VOICES)
    for voice_name, by_text in GOLDENS.items():
        assert set(by_text) == set(TEXTS), voice_name


@pytest.mark.parametrize("voice_name,text_name", CASES)
def test_pcm_matches_golden(voice_name, text_name):
    actual = digest(VOICES[voice_name], TEXTS[text_name])
    assert actual == GOLDENS[voice_name][text_name], (
        f"PCM changed for {voice_name}/{text_name}. Synthesis is deterministic, "
        f"so this means the audio output differs from the C reference. "
        f"Fix the regression -- do not regenerate golden_pcm.json."
    )


def test_synthesis_is_deterministic():
    """Two runs of the same input must agree, or the goldens mean nothing."""
    voice = VOICES["Fred"]
    assert digest(voice, TEXTS["dictionary"]) == digest(voice, TEXTS["dictionary"])
