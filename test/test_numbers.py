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


def test_is_year_number():
    from lintalker._numbers import is_year_number

    assert is_year_number("1984")
    assert is_year_number("1000") is False  # explicitly excluded (FrontEnd.c:1985)
    assert is_year_number("2023") is False  # only years starting with '1' are detected
    assert is_year_number("123") is False   # not 4 digits
    assert is_year_number("12345") is False


def test_year_to_phonemes_two_groups():
    from lintalker._numbers import year_to_phonemes, _two_digit_phonemes

    assert year_to_phonemes("1984") == [_Word_] + _two_digit_phonemes(1, 9) + _two_digit_phonemes(8, 4)


def test_year_to_phonemes_oh_insertion():
    from lintalker._numbers import year_to_phonemes, _two_digit_phonemes, _OH

    # 1905 -> "nineteen oh five" (second group's tens digit is 0, units isn't)
    assert year_to_phonemes("1905") == [_Word_] + _two_digit_phonemes(1, 9) + _OH + _two_digit_phonemes(0, 5)


def test_year_to_phonemes_round_hundred():
    from lintalker._numbers import year_to_phonemes, _two_digit_phonemes, _HUNDRED

    # 1900 -> "nineteen hundred" (second group is "00")
    assert year_to_phonemes("1900") == [_Word_] + _two_digit_phonemes(1, 9) + _HUNDRED


def test_number_token_reads_as_year_by_default():
    from lintalker._assembly import make_fe_word_token
    from lintalker._numbers import year_to_phonemes, number_to_phonemes

    tok = make_fe_word_token("1984", None)
    assert tok.phon_str == year_to_phonemes("1984")

    # A 4-digit number NOT starting with '1' keeps ordinary cardinal reading.
    tok2 = make_fe_word_token("2023", None)
    assert tok2.phon_str == number_to_phonemes("2023")

    # digit_by_digit mode overrides year detection too.
    from lintalker._numbers import digit_by_digit_phonemes
    tok3 = make_fe_word_token("1984", None, digit_by_digit=True)
    assert tok3.phon_str == digit_by_digit_phonemes("1984")


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


def test_tokenize_dollar_prefix_kept_as_digit_token():
    from lintalker._frontend import tokenize

    dollar_indices = []
    tokens = tokenize("i have $5.", dollar_indices)
    assert tokens == [("I", None), ("HAVE", None), ("5", ".")]
    assert dollar_indices == [2]


def test_dollar_prefix_no_longer_silently_dropped():
    # Regression guard: before dollar-amount reading was ported, "$5"
    # had no alpha characters left after tokenize()'s fallback filter,
    # so the whole token vanished instead of being read as a number.
    from lintalker._frontend import tokenize

    tokens = tokenize("i have $5.")
    words = [w for w, _ in tokens]
    assert "5" in words


def test_dollar_phonemes_plural_and_singular():
    from lintalker._numbers import dollar_phonemes, number_to_phonemes, _DOLLAR

    assert dollar_phonemes("5") == [_Word_] + number_to_phonemes("5")[1:] + _DOLLAR
    assert dollar_phonemes("1") == [_Word_] + number_to_phonemes("1")[1:] + _DOLLAR[:-1]


def test_dollar_amount_reaches_word_token_end_to_end():
    from lintalker._assembly import collect_fe_tokens
    from lintalker._numbers import dollar_phonemes, number_to_phonemes

    sa = collect_fe_tokens("i have $5.")
    dollar_word = sa.words[2]
    assert dollar_word.word == "5"
    assert dollar_word.phon_str == dollar_phonemes("5")
    assert dollar_word.phon_str != number_to_phonemes("5")


def test_dollar_bypasses_year_detection():
    # "$1984" must read as a plain cardinal + "dollars", NOT as a year
    # (SpeakTokenAsNumber's kYearSpecial check explicitly excludes
    # kAddDollar tokens, FrontEnd.c:1982-1983).
    from lintalker._assembly import make_fe_word_token
    from lintalker._numbers import dollar_phonemes, year_to_phonemes

    tok = make_fe_word_token("1984", None, is_dollar=True)
    assert tok.phon_str == dollar_phonemes("1984")
    assert tok.phon_str != year_to_phonemes("1984")


def test_tokenize_decimal_splits_into_three_tokens():
    from lintalker._frontend import tokenize

    frac_indices = []
    tokens = tokenize("it costs 3.14 dollars.", _decimal_frac_out=frac_indices)
    assert tokens == [
        ("IT", None), ("COSTS", None),
        ("3", None), ("POINT", None), ("14", None),
        ("DOLLARS", "."),
    ]
    assert frac_indices == [4]


def test_decimal_no_longer_silently_dropped():
    # Regression guard: before this was ported, "3.14" had no alpha
    # characters left after tokenize()'s fallback filter (digits AND
    # the "." both get stripped), so the whole token vanished.
    from lintalker._frontend import tokenize

    words = [w for w, _ in tokenize("it costs 3.14 dollars.")]
    assert "3" in words and "POINT" in words and "14" in words


def test_decimal_fraction_read_digit_by_digit():
    from lintalker._assembly import collect_fe_tokens
    from lintalker._numbers import digit_by_digit_phonemes, number_to_phonemes

    sa = collect_fe_tokens("it costs 3.14 dollars.")
    frac_word = sa.words[4]
    assert frac_word.word == "14"
    assert frac_word.phon_str == digit_by_digit_phonemes("14")
    assert frac_word.phon_str != number_to_phonemes("14")


def test_decimal_not_applied_to_dollar_prefixed_token():
    # $3.14 isn't handled by the plain-decimal path (the real engine
    # routes it through the SEPARATE "AND ... cents" branch instead,
    # see below) -- so it must not get the plain-decimal "POINT" reading.
    from lintalker._frontend import tokenize

    tokens = tokenize("it costs $3.14 total.")
    words = [w for w, _ in tokens]
    assert "POINT" not in words


def test_tokenize_dollar_decimal_splits_into_dollars_and_and_cents():
    from lintalker._frontend import tokenize

    dollar_indices, cent_indices = [], []
    tokens = tokenize(
        "it costs $5.25 total.", _dollar_out=dollar_indices, _cent_out=cent_indices,
    )
    assert tokens == [
        ("IT", None), ("COSTS", None),
        ("5", None), ("AND", None), ("25", None),
        ("TOTAL", "."),
    ]
    assert dollar_indices == [2]
    assert cent_indices == [4]


def test_cent_phonemes_plural_and_singular():
    from lintalker._numbers import cent_phonemes, number_to_phonemes, _CENT

    assert cent_phonemes("25") == [_Word_] + number_to_phonemes("25")[1:] + _CENT
    assert cent_phonemes("1") == [_Word_] + number_to_phonemes("1")[1:] + _CENT[:-1]


def test_dollar_and_cents_reaches_word_tokens_end_to_end():
    from lintalker._assembly import collect_fe_tokens
    from lintalker._numbers import dollar_phonemes, cent_phonemes

    sa = collect_fe_tokens("it costs $5.25 total.")
    assert sa.words[2].word == "5"
    assert sa.words[2].phon_str == dollar_phonemes("5")
    assert sa.words[3].word == "AND"
    assert sa.words[4].word == "25"
    assert sa.words[4].phon_str == cent_phonemes("25")


def test_cent_amount_reads_as_cardinal_not_digit_by_digit():
    from lintalker._assembly import collect_fe_tokens
    from lintalker._numbers import digit_by_digit_phonemes

    sa = collect_fe_tokens("it costs $5.25 total.")
    assert sa.words[4].phon_str != digit_by_digit_phonemes("25")


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK: {t.__name__}")
    print(f"\n{len(tests)} tests passed")
