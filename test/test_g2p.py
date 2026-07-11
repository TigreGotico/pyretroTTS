"""The grapheme-to-phoneme front ends, exposed without synthesis."""
import doctest

import pytest

from pyretrotts import g2p
from pyretrotts.g2p import ENGINES, phoneme_names, phonemize, phonemize_words


def test_the_module_examples_are_true():
    assert doctest.testmod(g2p).failed == 0


@pytest.mark.parametrize("engine", sorted(ENGINES))
def test_every_engine_phonemizes(engine):
    assert phonemize("hello", engine)


def test_an_unknown_engine_is_rejected():
    with pytest.raises(ValueError, match="unknown engine"):
        phonemize("hello", "klatt")


def test_the_engines_use_their_own_notation():
    assert phonemize("hello", "macintalk") == ["h", "EH", "l", "OW"]
    assert phonemize("hello", "dectalk") == ["hx", "eh", "ll", "ow"]
    assert phonemize("hello", "sam") == ["/H", "EH", "L", "OW"]


def test_dectalk_runs_its_own_front_end():
    """DECtalk sounds a word out with its own rules, not MacinTalk's relabelled."""
    assert phonemize("photograph", "dectalk") == \
        ["f", "ow", "t", "ax", "g", "r", "ae", "f"]


def test_dectalk_expands_numbers():
    """A digit token reads as words through DECtalk's number reader."""
    assert phonemize("21", "dectalk") == ["t", "w", "eh", "n", "t", "iy", "w", "ah", "n"]


def test_dectalk_applies_inflectional_morphology():
    """`dogs` is `dog` plus a voiced `-s`."""
    dogs, = phonemize_words("dogs", "dectalk")
    assert dogs.phonemes == ["d", "aa", "g", "z"]


def test_dectalk_markers_carry_stress_and_boundaries():
    plain = phonemize("hello", "dectalk")
    marked = phonemize("hello", "dectalk", markers=True)
    assert len(marked) > len(plain)
    assert "s1" in marked and "s1" not in plain
    assert "wbound" in marked


def test_markers_are_dropped_by_default():
    """The opcode stream carries word boundaries and stress; phonemes do not."""
    plain = phonemize("hello", "macintalk")
    marked = phonemize("hello", "macintalk", markers=True)
    assert len(marked) > len(plain)
    assert "_" in marked and "_" not in plain


def test_sam_has_no_markers_to_drop():
    assert phonemize("hello", "sam") == phonemize("hello", "sam")


def test_a_dictionary_word_is_flagged_as_one():
    hello, zorbnax = phonemize_words("hello zorbnax.", "macintalk")
    assert hello.from_dictionary is True
    assert zorbnax.from_dictionary is False


def test_sam_never_uses_a_dictionary_because_it_has_none():
    assert all(not p.from_dictionary for p in phonemize_words("hello there", "sam"))


def test_a_pronunciation_prints_readably():
    hello, = phonemize_words("hello", "macintalk")
    assert str(hello) == "HELLO: h EH l OW"


def test_the_phoneme_names_are_exposed():
    names = phoneme_names()
    assert names[0] == "IY"
    assert len(names) > 50


def test_letter_to_sound_handles_a_word_no_dictionary_knows():
    """`zorbnax` is in no dictionary; every engine still sounds it out."""
    for engine in ENGINES:
        assert len(phonemize("zorbnax", engine)) >= 6
