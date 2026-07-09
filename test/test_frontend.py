"""Tests for the (partial) FrontEnd.c port in lintalker/_frontend.py.

Scope note: this only tests tokenization + per-word rule-based
letter-to-sound (engtop), NOT a full phoneme plan -- see _frontend.py's
module docstring for why the ctrl/dur assembly stage is not implemented
yet. There is currently no way to diff this against the C test_harness at
matching granularity: test_harness only prints frame-level F/P dump lines
(see lintalker-c/bin/Debug, invoked as `test_harness -v 0 "text"`), it does
not expose a token/word/phoneme-string dump to stdout. Bit-exact validation
of this module against the C reference is therefore deferred until
Fill_Phon_Buf_2 (or an equivalent) is ported and can be driven end-to-end
through api.synthesize_phonemes for frame-level comparison, the same way
test/test_voices.py does for the backend today.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lintalker._frontend import tokenize, words_to_phonemes
from lintalker._phonemes import _Period_, _Comma_, _Quest_, _Exclam_, _Word_


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


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__, '-v']))
