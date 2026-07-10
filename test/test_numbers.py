"""Tests for _numbers.py's cardinal-number-to-phonemes port.

See _numbers.py's module docstring for the exact verification status:
individual number words (ZERO-NINETEEN, TWENTY-NINETY, AND) are
extracted bit-exact from the compiled lintalker-c test_harness;
HUNDRED/THOUSAND/MILLION/BILLION are substituted from ordinary
dictionary word lookups since the Symbols dictionary's own numeric-key
lookup for these words is confirmed corrupted in this specific compiled
reference. The assembled multi-digit algorithm is a faithful port of
PartialNumberToPhonemes but is NOT verified end-to-end against a
working reference (none exists for this path -- see
docs/architecture.md).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lintalker._numbers import number_to_phonemes
from lintalker._phonemes import _Word_


def _decode(phons):
    from lintalker import _phonemes as P
    names = {v: k for k, v in vars(P).items() if k.startswith('_') and isinstance(v, int)}
    return [names.get(p, p) for p in phons]


def test_single_digits_match_extracted_words():
    assert number_to_phonemes("0") == [_Word_, 41, 17, 14]
    assert number_to_phonemes("5") == [_Word_, 36, 11, 37]
    assert number_to_phonemes("9") == [_Word_, 34, 11, 34]


def test_teens():
    assert number_to_phonemes("10") == [_Word_, 46, 2, 34]
    assert number_to_phonemes("15") == [_Word_, 36, 1, 36, 46, 0, 34]


def test_tens_with_and_without_units():
    assert number_to_phonemes("20") == [_Word_, 46, 28, 2, 34, 46, 0]
    assert number_to_phonemes("23") == [_Word_] + [46, 28, 2, 34, 46, 0] + [38, 30, 0]


def test_hundreds_with_and_insertion():
    # "and" only inserted when the FULL number has >= 3 digits and
    # something has already been spoken (FrontEnd.c:1836-1842).
    assert number_to_phonemes("100") == [_Word_] + [28, 5, 34] + [32, 5, 34, 47, 30, 8, 47]
    expected_123 = [_Word_] + [28, 5, 34] + [32, 5, 34, 47, 30, 8, 47] + [2, 34, 47] + [46, 28, 2, 34, 46, 0] + [38, 30, 0]
    assert number_to_phonemes("123") == expected_123


def test_no_and_for_round_hundred_multiples_without_trailing_group():
    # "200" -> "two hundred" (no dangling and, since tens/units are 0).
    assert number_to_phonemes("200") == [_Word_] + [46, 15] + [32, 5, 34, 47, 30, 8, 47]


def test_thousands():
    assert number_to_phonemes("1000") == [_Word_] + [28, 5, 34] + [38, 13, 41, 27, 47]
    # "1234" -> "one thousand two hundred and thirty four"
    expected = (
        [_Word_] + [28, 5, 34] + [38, 13, 41, 27, 47]
        + [46, 15] + [32, 5, 34, 47, 30, 8, 47]
        + [2, 34, 47] + [38, 9, 53, 0] + [36, 20]
    )
    assert number_to_phonemes("1234") == expected


def test_prefixed_with_word_opcode():
    result = number_to_phonemes("42")
    assert result[0] == _Word_


def test_zero_alone():
    assert _decode(number_to_phonemes("0"))[1:] == ['_z_', '_IR_', '_OW_']


def test_end_to_end_via_synthesize_text_does_not_crash():
    from lintalker.api import synthesize_text
    from lintalker._data import Fred_Voice

    for text in ["123", "i have 42 apples.", "the year 2023.", "0", "1000000"]:
        pcm = synthesize_text(Fred_Voice, text)
        assert len(pcm) > 0


def test_number_token_gets_kadj_pos():
    from lintalker._assembly import make_fe_word_token
    from lintalker._consts import kAdj

    tok = make_fe_word_token("123", None)
    assert tok.pos_code1[0] == kAdj
    assert tok.pos_choice == kAdj


def test_frontend_tokenize_preserves_digit_tokens():
    from lintalker._frontend import tokenize

    tokens = tokenize("i have 123 dollars.")
    words = [w for w, _ in tokens]
    assert "123" in words


def test_digit_by_digit_reads_each_digit_separately():
    from lintalker._numbers import digit_by_digit_phonemes, _ONES

    assert digit_by_digit_phonemes("123") == [_Word_] + _ONES[1] + _ONES[2] + _ONES[3]
    assert digit_by_digit_phonemes("0") == [_Word_] + _ONES[0]


def test_nmbr_embedded_command_switches_to_digit_by_digit():
    from lintalker._embeddedcmd import scan_bracket_commands
    from lintalker._assembly import collect_fe_tokens
    from lintalker._numbers import digit_by_digit_phonemes, number_to_phonemes

    clean, _cmds, _emph, _sil, _pos, _rates, _final_rate, nmbr = scan_bracket_commands(
        "[[nmbr LTRL]]123"
    )
    assert clean == "123"
    assert nmbr == {0: True}
    sa = collect_fe_tokens(clean, nmbr_overrides=nmbr)
    assert sa.words[0].phon_str == digit_by_digit_phonemes("123")
    assert sa.words[0].phon_str != number_to_phonemes("123")


def test_nmbr_mode_latches_until_switched_back():
    from lintalker._embeddedcmd import scan_bracket_commands
    from lintalker._assembly import collect_fe_tokens
    from lintalker._numbers import digit_by_digit_phonemes, number_to_phonemes

    clean, _cmds, _emph, _sil, _pos, _rates, _final_rate, nmbr = scan_bracket_commands(
        "[[nmbr LTRL]]12 [[nmbr NORM]]34"
    )
    assert nmbr == {0: True, 1: False}
    sa = collect_fe_tokens(clean, nmbr_overrides=nmbr)
    assert sa.words[0].phon_str == digit_by_digit_phonemes("12")
    assert sa.words[1].phon_str == number_to_phonemes("34")


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK: {t.__name__}")
    print(f"\n{len(tests)} tests passed")
