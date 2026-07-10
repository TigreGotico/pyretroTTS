"""Tests for _letters.py's LETTER_PHONEMES table and spell_word() --
the char embedded command's kCharByChar letter-by-letter spelling mode.

See _letters.py's module docstring for the extraction method (a
single-letter token in sentence-initial position, forcing
WordToPhonemes's real kAlphaTok single-char branch into
SpeakTokenCharByChar) and the documented multi-letter vowel-hiatus
verification caveat.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pyretrotts._letters import LETTER_PHONEMES, spell_word
from pyretrotts._phonemes import _EH_, _IY_, _b_, _f_, _Word_


def test_all_26_letters_present():
    assert set(LETTER_PHONEMES.keys()) == set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def test_b_is_bee():
    assert LETTER_PHONEMES['B'] == [_b_, _IY_]


def test_f_is_ef():
    assert LETTER_PHONEMES['F'] == [_EH_, _f_]


def test_spell_word_prefixes_word_opcode_once():
    result = spell_word("CAB")
    assert result[0] == _Word_
    assert result == [_Word_] + LETTER_PHONEMES['C'] + LETTER_PHONEMES['A'] + LETTER_PHONEMES['B']


def test_spell_word_skips_non_letter_characters():
    # An apostrophe (or any character with no LETTER_PHONEMES entry) is
    # simply skipped, matching the module docstring.
    assert spell_word("A'B") == [_Word_] + LETTER_PHONEMES['A'] + LETTER_PHONEMES['B']


def test_end_to_end_via_synthesize_text_does_not_crash():
    from pyretrotts._data import Fred_Voice
    from pyretrotts.api import synthesize_text

    pcm = synthesize_text(Fred_Voice, "[[char LTRL]]cab[[char NORM]] home")
    assert len(pcm) > 0


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK: {t.__name__}")
    print(f"\n{len(tests)} tests passed")
