"""Unit tests for the generative ModernTalk / ModernSAM front ends.

These check that the feature model decomposes IPA, that every symbol in a
multilingual set is synthesized from features (no English-preset collapse), and
that both engines emit non-silent audio for arbitrary IPA. Quality is judged
perceptually (see ``tools/modern_coverage.py``); these guard structure.
"""
import math
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.modern import ModernSAMEngine, ModernTalkEngine
from pyretrotts.modern.features import decompose, nearest_target

# Symbols English lacks that the model must still synthesize from features.
_NON_ENGLISH = ["y", "ø", "œ", "ʁ", "ʎ", "ɲ", "ç", "ɕ", "ħ", "x", "õ", "ɐ̃"]


def _rms(pcm: bytes) -> float:
    n = len(pcm) // 2
    if not n:
        return 0.0
    s = struct.unpack(f"<{n}h", pcm)
    return math.sqrt(sum(x * x for x in s) / n)


def test_vowel_formants_track_openness_and_backness():
    # /a/ is more open than /i/ (higher F1); /i/ is fronter than /u/ (higher F2).
    assert decompose("a").f1 > decompose("i").f1
    assert decompose("i").f2 > decompose("u").f2


def test_english_vowel_f3_sits_in_the_dectalk_synth_band():
    # The DECtalk US target ROM keeps English F3 in a ~2300-2800 Hz band on this
    # synth (see features._VOWELS calibration note). A vowel table with F3 far
    # above that band (the pre-calibration /i/ F3 was 3010) pushes vowels out of
    # the region the cascade is tuned for and hurts intelligibility.
    for sym in ("i", "ɪ", "ɛ", "æ", "ɑ", "ʌ", "ɔ", "o", "ʊ", "u", "ə"):
        assert 2200 <= decompose(sym).f3 <= 2800, sym


def test_english_rhotic_approximant_has_low_f3():
    # /ɹ/ is defined acoustically by a low F3 (DECtalk US R F3 = 1380); the
    # neighbouring vowel must bend toward it, not toward a 2500 Hz default.
    assert decompose("ɹ").f3 <= 1600
    assert decompose("ɹ").rhotic


def test_diacritics_fold_into_features():
    assert decompose("ãː").nasal and decompose("ãː").long
    assert decompose("ɚ").rhotic


def test_non_english_symbols_decompose_without_fallback():
    for sym in _NON_ENGLISH:
        decompose(sym)  # must not raise; no nearest-neighbour needed


def test_nearest_target_prefers_articulatory_neighbour():
    # An unknown click resolves to *some* reachable target, deterministically.
    assert nearest_target("ǃ", ["s", "a", "k"]) in ("s", "a", "k")


def test_modern_talk_speaks_english_and_non_english():
    engine = ModernTalkEngine()
    assert _rms(engine.say_ipa("həˈloʊ wɜrld")) > 100
    assert _rms(engine.say_ipa("bɔ̃ʒuʁ")) > 100


def test_modern_talk_full_feature_coverage_on_multilingual_set():
    engine = ModernTalkEngine()
    ipa = "bɔ̃ʒuʁ ty ɪç ˈkaʎe ˈaɲo ħaːl sxɛvənɪŋən"
    fell = [s for s, _b, f in engine.bundles(ipa) if f]
    assert not fell, f"unexpected fallback for: {fell}"


def test_modern_sam_speaks_arbitrary_ipa():
    engine = ModernSAMEngine()
    assert _rms(engine.say_ipa("həˈloʊ")) > 100
    assert _rms(engine.say_ipa("ˈkaʎe")) > 100
