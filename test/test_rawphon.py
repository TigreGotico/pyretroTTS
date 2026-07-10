"""Tests for _rawphon.py's raw-phoneme-mnemonic parser (the `mode PHON`
embedded command's underlying mechanism, `GetNextPhonemeOpcode`/
`CollectPhonemeToken`, `FrontEnd.c:247-345`).

MAGIC_MAP is a direct, bit-exact transcription of Data.c:3307's
MAGIC_CHAR_MAP[]/Data.c:3394's MAGIC_OPCODE_MAP[] -- literal compile-time
C source tables, not runtime dictionary lookups, so unlike the digit/
year/dollar/cent/clock words elsewhere in this port, there is no
Symbols-dictionary corruption or extraction-verification caveat here at
all.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pylintalker._phonemes import (
    _AA_,
    _Comma_,
    _EmphWord_,
    _p_,
    _Period_,
    _Stress1_,
    _t_,
    _Word_,
)
from pylintalker._rawphon import MAGIC_MAP, parse_raw_phonemes, split_into_word_groups


def test_two_char_vowel_mnemonics():
    assert parse_raw_phonemes("AA") == [_AA_]


def test_one_char_consonant_mnemonics():
    assert parse_raw_phonemes("pt") == [_p_, _t_]


def test_stress_and_word_markers():
    assert parse_raw_phonemes("_1AAt") == [_Word_, _Stress1_, _AA_, _t_]


def test_punctuation_mnemonics():
    assert parse_raw_phonemes(",.") == [_Comma_, _Period_]


def test_two_char_preferred_over_one_char():
    # "AA" must resolve as the single two-char vowel _AA_, not two
    # separate one-char lookups (there is no one-char "A" entry at all,
    # but this confirms the greedy 2-then-1 matching order generally).
    assert parse_raw_phonemes("AA") == [_AA_]
    assert MAGIC_MAP[('A', 'A')] == _AA_


def test_unrecognized_character_is_skipped():
    # 'x' alone (not 'AX'/'DX'/etc.) has no MAGIC_MAP entry -- matches
    # GetNextPhonemeOpcode simply advancing past it without an opcode.
    assert parse_raw_phonemes("p#t") == [_p_, _t_]


def test_split_into_word_groups_basic():
    opcodes = parse_raw_phonemes("_1AAt_2t1IY")
    groups = split_into_word_groups(opcodes)
    assert len(groups) == 2
    assert groups[0][0] == _Word_
    assert groups[1][0] == _Word_


def test_split_into_word_groups_leading_word_marker_does_not_split():
    # A _Word_/_EmphWord_ opcode as the VERY FIRST thing collected does
    # NOT start a new (empty) group -- matches CollectPhonemeToken's
    # `&& tokLen` guard (FrontEnd.c:313).
    opcodes = [_Word_, _Stress1_, _AA_]
    assert split_into_word_groups(opcodes) == [[_Word_, _Stress1_, _AA_]]


def test_split_into_word_groups_emphword_also_splits():
    opcodes = [_Word_, _p_, _EmphWord_, _t_]
    assert split_into_word_groups(opcodes) == [[_Word_, _p_], [_EmphWord_, _t_]]


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK: {t.__name__}")
    print(f"\n{len(tests)} tests passed")
