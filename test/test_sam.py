"""Unit tests for the SAM port: reciter, phoneme tables, and prosody.

The expected values are taken from the C reference: the reciter strings and the
final phoneme buffers are `sam -debug` dumps, and the table values are the
SamTabs.h literals.
"""
import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.sam import phonemes, prosody, reciter
from pyretrotts.sam.engine import SAMEngine, SamVoice
from pyretrotts.sam.phonemes import (
    FLAG_DIP_YX,
    FLAG_VOWEL,
    PHONEME_LENGTH_TABLE,
    PHONEME_STRESSED_LENGTH_TABLE,
)

# --- reciter --------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    (b"HELLO", b" /HEHLOW \x9b"),
    (b"CAT", b" KAET \x9b"),
    (b"WORLD", b" WERLD \x9b"),
    (b"THE QUICK BROWN FOX", b" DHAX KWIHK BROWN FAAKS \x9b"),
    (b"TESTING", b" TEHSTIHNX \x9b"),
    (b"123", b"  WAH4N TUW4 THRIY4 \x9b"),
])
def test_reciter_matches_c(text, expected):
    assert reciter.text_to_phonemes(text) == expected


def test_reciter_terminates_with_end_marker():
    out = reciter.text_to_phonemes(b"SAM")
    assert out is not None and out[-1] == 0x9B


# --- phoneme tables -------------------------------------------------------

def test_mnemonics():
    assert phonemes.mnemonic(5) == "IY"
    assert phonemes.mnemonic(9) == "AA"
    assert phonemes.mnemonic(72) == "K"   # K* -> single character
    assert phonemes.mnemonic(31) == "Q"


def test_flag_words_from_samtabs():
    assert phonemes.flags(0) == 0x8000            # silence
    assert phonemes.flags(9) == 0x00A4            # AA: vowel + dip_yx + voiced
    assert phonemes.flags(9) & FLAG_VOWEL
    assert phonemes.flags(9) & FLAG_DIP_YX


def test_length_tables():
    assert PHONEME_LENGTH_TABLE[9] == 0x0B        # AA base length 11
    assert PHONEME_STRESSED_LENGTH_TABLE[9] == 0x0F  # AA stressed length 15


def test_flags_reproduce_out_of_bounds_end_read():
    # The T/D and vowel-length rules read flags[255]; the reference build's
    # out-of-bounds byte has the vowel bit set, so those rules fire on it.
    assert phonemes.flags(255) & FLAG_VOWEL


# --- prosody: parser1 -----------------------------------------------------

def _buffers(phon: bytes) -> prosody.Buffers:
    st = prosody.Buffers(phon + b"\x9b")
    st.phonemeindex[255] = 32
    return st


def test_parser1_tokenises_two_char_and_stress():
    st = _buffers(b"AA5")
    assert prosody.parser1(st) is True
    assert st.phonemeindex[0] == 9      # AA
    assert st.stress[0] == 5
    assert st.phonemeindex[1] == phonemes.END


def test_parser1_rejects_unknown_symbol():
    st = _buffers(b"AA9")   # '9' is not a stress digit (1..8)
    assert prosody.parser1(st) is False


# --- prosody: full stage, compared to sam -debug --------------------------

def _pipeline(phon: bytes):
    st = _buffers(phon)
    assert prosody.parser1(st)
    prosody.parser2(st)
    prosody.copy_stress(st)
    prosody.set_phoneme_length(st)
    prosody.adjust_lengths(st)
    prosody.code41240(st)
    x = 0
    while True:
        if st.phonemeindex[x] > 80:
            st.phonemeindex[x] = phonemes.END
            break
        x = (x + 1) & 0xFF
        if x == 0:
            break
    prosody.insert_breath(st)
    out = []
    i = 0
    while st.phonemeindex[i] != phonemes.END:
        out.append((st.phonemeindex[i], st.phonemeLength[i], st.stress[i]))
        i += 1
    return out


def test_parser2_softens_t_before_r_to_ch():
    # TRIY: "T R -> CH R"; then CH is doubled and lengths assigned (sam -debug).
    assert _pipeline(b"TRIY") == [(42, 6, 0), (23, 5, 0), (5, 8, 0)]


def test_code41240_expands_stop_consonant():
    # KAA: K stays K* (AA carries the dip-yx flag), expanded into 72,73,74.
    assert _pipeline(b"KAA") == [(72, 6, 0), (73, 1, 0), (74, 4, 0), (9, 11, 0)]


def test_stressed_vowel_length():
    # AA5: stressed AA takes its stressed length of 15.
    assert _pipeline(b"AA5") == [(9, 15, 5)]


# --- engine ---------------------------------------------------------------

def _peak(pcm: bytes) -> int:
    samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)
    return max((abs(v) for v in samples), default=0)


def test_engine_surface():
    e = SAMEngine()
    assert e.name == "SAM"
    assert e.dialect
    assert e.sample_rate == 22050
    assert len(e.voices) == 6
    assert "Sam" in e.voices


def test_voices_are_knob_presets():
    e = SAMEngine()
    assert e.voices["Sam"] == SamVoice(72, 64, 128, 128)
    assert all(isinstance(v, SamVoice) for v in e.voices.values())


def test_synthesize_text_and_phonetic():
    e = SAMEngine()
    spoken = e.synthesize("hello world")
    assert len(spoken) > 4000 and _peak(spoken) > 1000
    phon = e.speak_phonemes("/HEHLOW")
    assert _peak(phon) > 1000


def test_native_8bit_widens_to_16bit():
    # A single byte of native output becomes one 16-bit sample: (b-128)<<8.
    from pyretrotts.sam.engine import _u8_to_s16
    assert _u8_to_s16(bytes([128, 0, 255])) == struct.pack("<3h", 0, -32768, 32512)


def test_voice_knobs_change_the_audio():
    e = SAMEngine()
    assert e.synthesize("hello", "Sam") != e.synthesize("hello", "Little Robot")
