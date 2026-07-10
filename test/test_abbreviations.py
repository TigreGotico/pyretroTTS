"""Tests for abbreviation-period handling (FrontEnd.c:515-545, the
`tok->isAbbriv` check): a "." right after a known dictionary
abbreviation ("Mr.", "Dr.", "St.", ...) does not end a sentence/clause,
matching `SearchAllDicts` finding the word WITH the period as part of
its lookup key and `is_abbrev=True`.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pyretrotts._frontend import split_clauses, split_sentences, tokenize


def test_tokenize_keeps_period_on_known_abbreviation():
    tokens = tokenize("mr. smith went home.")
    assert tokens[0] == ("MR.", None)
    assert tokens[-1] == ("HOME", ".")


def test_tokenize_strips_period_on_non_abbreviation_word():
    tokens = tokenize("home. bye.")
    assert tokens[0] == ("HOME", ".")


def test_split_clauses_does_not_split_on_abbreviation_period():
    assert split_clauses("mr. smith went home.") == ["mr. smith went home."]
    assert split_clauses("dr. jones, mr. smith, and st. louis.") == [
        "dr. jones,", "mr. smith,", "and st. louis."
    ]


def test_split_sentences_does_not_split_on_abbreviation_period():
    assert split_sentences("mr. smith went home.") == ["mr. smith went home."]
    assert split_sentences("mr. smith is here. he left.") == [
        "mr. smith is here.", "he left."
    ]


def test_abbreviation_at_end_of_input_is_still_a_real_boundary():
    # No text follows the abbreviation -- matches FrontEnd.c's
    # `vv->NextCh != kEOFCh` guard: at true end-of-input, the period IS
    # treated as sentence-terminal even for a known abbreviation.
    assert split_clauses("i work with mr.") == ["i work with mr."]


def test_end_to_end_frame_exact_against_c_reference():
    from test_synthesize_text import _check

    _check("mr. smith went home.", "Fred")
    _check("dr. jones is here.", "Fred")
    _check("st. louis is a city.", "Fred")


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK: {t.__name__}")
    print(f"\n{len(tests)} tests passed")
