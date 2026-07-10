"""`Search_Suffix`: the suffix table the reference scans, and how."""
from pyretrotts._consts import (
    kCALLY_suffix,
    kED_suffix,
    kIED_suffix,
    kINESS_suffix,
    kING_suffix,
    kLY_suffix,
    kS_suffix,
)
from pyretrotts._morph import SUFFIX_TABLE, search_suffix


def test_the_table_has_the_reference_entries_in_order():
    """Data.c:3848, read forwards. The reference stores each entry reversed."""
    assert len(SUFFIX_TABLE) == 37
    assert SUFFIX_TABLE[0] == ("IZING", 1)
    assert SUFFIX_TABLE[-1] == ("S", kS_suffix)


def test_a_word_with_no_suffix_keeps_its_whole_length():
    assert search_suffix("DOG") == (0, 3)


def test_the_scan_matches_from_the_end_backwards():
    assert search_suffix("WALKING") == (kING_suffix, 4)
    assert search_suffix("JUMPED") == (kED_suffix, 4)
    assert search_suffix("CATS") == (kS_suffix, 3)
    assert search_suffix("QUICKLY") == (kLY_suffix, 5)


def test_a_longer_entry_wins_when_it_comes_first_in_the_table():
    """`IED` precedes `ED`, so `carried` yields the root `carr`, not `carri`."""
    assert search_suffix("CARRIED") == (kIED_suffix, 4)


def test_order_not_length_is_the_tiebreak():
    """`CALLY` sits before `LY`, so `basically` strips five letters."""
    assert search_suffix("BASICALLY") == (kCALLY_suffix, 4)


def test_iness_beats_ness():
    assert search_suffix("HAPPINESS") == (kINESS_suffix, 4)


def test_the_root_keeps_at_least_one_letter():
    """The reference's `len > 1` guard stops a suffix consuming the whole word.

    `ES` matches the `S` entry and leaves the single letter `E`; a bare `S`
    matches nothing, because there would be no root left.
    """
    assert search_suffix("ES") == (kS_suffix, 1)
    assert search_suffix("S") == (0, 1)


def test_a_trailing_apostrophe_is_skipped_before_the_scan():
    suffix_type, _ = search_suffix("DOGS'")
    assert suffix_type == kS_suffix
