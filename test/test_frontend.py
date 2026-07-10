"""Tests for the (partial) FrontEnd.c port in pylintalker/_frontend.py.

These tests cover tokenization + per-word rule-based letter-to-sound
(engtop) in isolation. The full pipeline built on top of `tokenize()`
(`_assembly`/`_phonbuf2`/`_pitchcontour`/`_moduration`/`_pitchbuf`) is
validated frame-for-frame against the C reference in
test/test_synthesize_text.py -- see that file and docs/architecture.md
for the end-to-end bit-exactness story.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pylintalker._frontend import split_sentences, tokenize, words_to_phonemes
from pylintalker._phonemes import _Period_, _Quest_, _Word_


def test_tokenize_splits_words_and_punct():
    assert tokenize("Hello, how are you?") == [
        ("HELLO", ","),
        ("HOW", None),
        ("ARE", None),
        ("YOU", "?"),
    ]


def test_tokenize_period_and_exclam():
    assert tokenize("Go now. Wait!") == [
        ("GO", None),
        ("NOW", "."),
        ("WAIT", "!"),
    ]


def test_tokenize_drops_stray_punct():
    assert tokenize("(hi)") == [("HI", None)]


def test_tokenize_keeps_apostrophes():
    assert tokenize("don't stop.") == [("DON'T", None), ("STOP", ".")]


def test_words_to_phonemes_appends_punct_opcode():
    phon = words_to_phonemes("hi.")
    assert phon[-1] == _Period_
    assert phon[0] == _Word_  # engtop() prefixes every word with _Word_


def test_words_to_phonemes_multi_word_has_two_word_markers():
    phon = words_to_phonemes("hi there")
    assert phon.count(_Word_) == 2


def test_words_to_phonemes_question_mark():
    phon = words_to_phonemes("who?")
    assert phon[-1] == _Quest_


def test_split_sentences_basic():
    assert split_sentences("Hello there. How are you? Goodbye now!") == [
        "Hello there.", "How are you?", "Goodbye now!",
    ]


def test_split_sentences_no_terminal_punctuation():
    assert split_sentences("no punctuation at all") == ["no punctuation at all"]


def test_split_sentences_empty():
    assert split_sentences("") == []


def test_split_sentences_single():
    assert split_sentences("One sentence.") == ["One sentence."]


def test_split_sentences_drops_comma_as_boundary():
    # comma is not a sentence terminator
    assert split_sentences("Well, hello there.") == ["Well, hello there."]


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__, '-v']))
