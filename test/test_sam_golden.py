"""Bit-exact regression gate over SAM's synthesis pipeline.

Fails on a single differing PCM byte, for any of the six voices across every
front-end path. Needs no C reference, so it runs in CI; the digests in
sam_golden.json were captured from output verified sample-for-sample against the
C binary (see test_sam_oracle.py and sam_golden.py).
"""
import pytest
from sam_golden import TEXTS, VOICE_NAMES, digest, load

GOLDENS = load()

CASES = [(voice, text_name) for voice in VOICE_NAMES for text_name in TEXTS]


def test_golden_file_covers_every_voice_and_text():
    assert set(GOLDENS) == set(VOICE_NAMES)
    for voice, by_text in GOLDENS.items():
        assert set(by_text) == set(TEXTS), voice


@pytest.mark.parametrize("voice,text_name", CASES)
def test_pcm_matches_golden(voice, text_name):
    source, phonetic = TEXTS[text_name]
    actual = digest(voice, source, phonetic)
    assert actual == GOLDENS[voice][text_name], (
        f"PCM changed for {voice}/{text_name}. Synthesis is deterministic, so "
        f"this means the audio differs from the C reference. Fix the regression "
        f"-- do not regenerate sam_golden.json."
    )


def test_synthesis_is_deterministic():
    source, phonetic = TEXTS["text_hello"]
    assert digest("Sam", source, phonetic) == digest("Sam", source, phonetic)
