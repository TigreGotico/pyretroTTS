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

from pyretrotts.ipa import Stress, parse_ipa
from pyretrotts.modern import ModernSAMEngine, ModernTalkEngine
from pyretrotts.modern.features import decompose, nearest_target
from pyretrotts.modern.prosody import coarticulate, plan_clause, reduce_vowel

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


# --- prosody layer (durations, F0, reduction, coarticulation, boundaries) ---

def _plan(ipa):
    from pyretrotts.modern.features import expand
    clause = parse_ipa(ipa)[0]
    bundles = [decompose(expand(p.symbol)[0]) for p in clause.phones]
    return clause, plan_clause(clause, bundles, 122.0, is_last=True)


def test_stressed_vowel_is_longer_than_unstressed():
    # Klatt 1979: a primary-stressed vowel keeps its full stretchable duration;
    # an unstressed one is shortened. Compare the two non-final /ɑ/ of "ˈtɑtɑn"
    # (both closed, neither clause-final, so only stress differs).
    clause, plans = _plan("ˈtɑtɑn")
    stressed = plans[1]      # ɑ, primary
    unstressed = plans[3]    # ɑ, unstressed, followed by /n/ (not clause-final)
    assert clause.phones[1].stress == Stress.PRIMARY
    assert clause.phones[3].stress == Stress.NONE
    assert stressed.dur_frames > unstressed.dur_frames


def test_f0_declines_across_a_clause():
    # 't Hart declination: an unaccented baseline falls over the clause, so a
    # late unstressed vowel sits below an early one.
    _clause, plans = _plan("ma ma ma ma ma ma")
    f0s = [pl.f0_hz for pl in plans]
    assert f0s[-1] < f0s[0]


def test_primary_accent_raises_f0():
    # An early primary accent (hat rise) lifts F0 above the speaker base before
    # declination pulls it down.
    _clause, plans = _plan("ˈmamamama")
    assert max(pl.f0_hz for pl in plans) > 122.0


def test_pre_boundary_lengthening():
    # The same consonant is longer word-finally (before a word break) than the
    # word-medial one (Wightman 1992). Compare the two /s/ of "sɑs sɑ".
    clause, plans = _plan("sɑs sɑ")
    # phones: s ɑ s | s ɑ ; a word break falls before index 3.
    word_final_s = plans[2]
    word_initial_s = plans[0]
    assert word_final_s.pre_boundary
    assert word_final_s.dur_frames >= word_initial_s.dur_frames


def test_reduce_vowel_centralises_toward_schwa():
    # Lindblom 1963: reduction pulls formants toward the neutral schwa values.
    full = decompose("i")
    reduced = reduce_vowel(full, 0.5)
    schwa = decompose("ə")
    assert abs(reduced.f2 - schwa.f2) < abs(full.f2 - schwa.f2)
    # Zero reduction is a no-op.
    assert reduce_vowel(full, 0.0) == full


def test_coarticulation_glides_formants_between_neighbours():
    # A two-segment stream with different F2 targets: the boundary frames must
    # move toward each other, not stay flat (locus theory, Delattre 1955).
    a, b = 1000, 2000
    frames = [[0] * 20 for _ in range(6)]
    from pyretrotts.dectalk import consts as C
    for k in range(6):
        frames[k][C.OUT_AV] = 60
        frames[k][C.OUT_F2] = a if k < 3 else b
    smoothable = [True] * 6
    seg_id = [0, 0, 0, 1, 1, 1]
    seg_dur = [3, 3, 3, 3, 3, 3]
    out = coarticulate(frames, smoothable, seg_id, seg_dur, (C.OUT_F2,))
    assert a < out[2][C.OUT_F2] <= b   # last frame of seg 0 pulled up toward b
    assert a <= out[3][C.OUT_F2] < b   # first frame of seg 1 pulled down toward a


def test_prosody_keeps_full_feature_coverage():
    # The prosody layer must not introduce any nearest-target fallback.
    engine = ModernTalkEngine()
    ipa = "bɔ̃ʒuʁ ty ɪç ˈkaʎe ˈaɲo ħaːl sxɛvənɪŋən"
    assert not [s for s, _b, f in engine.bundles(ipa) if f]


def test_modern_talk_emits_22050_hz():
    engine = ModernTalkEngine()
    assert engine.sample_rate == 22050
    # The upsampled stream is ~2x the 11025 Hz core length.
    pcm = engine.say_ipa("ɑ")
    assert len(pcm) > 0
