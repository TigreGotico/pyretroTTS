"""DECtalk US sentence front end, diffed against the C oracle.

`pyretrotts.dectalk.sentence_us` turns whole text into the per-clause `symbols[]`
streams the C hands to `phclause` (the pre-`ph/` boundary): it splits on
punctuation into clauses, frames each word with an inter-word boundary marker,
closes each clause with the intonation terminator, and expands numbers,
abbreviations, and vowelless speller words to words first.

`test/dectalk_sentence_golden.json` is a committed real capture of that boundary
(the instrumented oracle) over the texts the port reproduces bit-exactly. The
dict-free paths (the speller, clause splitting, number/abbreviation expansion)
are gated in CI without the oracle; the dictionary-dependent framing and the
whole-sentence text->PCM diff across the ten voices are gated on the FONIX
dictionary and the instrumented oracle respectively.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.dectalk.numbers_us import (  # noqa: E402
    say_cardinal,
    say_digits,
    say_ordinal,
)
from pyretrotts.dectalk.sentence_us import (  # noqa: E402
    _COMMA,
    _EXCLAIM,
    _PERIOD,
    _QUEST,
    ABBREVIATIONS,
    _TitleWord,
    _expand_token,
    _split_clauses,
    sentence_to_clauses,
)
from pyretrotts.dectalk.title_abbrev_us import (  # noqa: E402
    _PDOCTOR,
    _PDRIVE,
    _PSAINT,
    _PSTREET,
)
from pyretrotts.dectalk.spell_us import is_spelled  # noqa: E402

_GOLDEN = os.path.join(os.path.dirname(__file__), "dectalk_sentence_golden.json")
_DIC = os.path.expanduser(
    "~/AgentWorkspaces/ovos/dectalk-c/dist/dic/dtalk_us.dic")


def _golden() -> dict[str, list[list[int]]]:
    with open(_GOLDEN) as f:
        return json.load(f)["exact"]


def _load_dict():
    from pyretrotts.dectalk.dictionary import Dictionary

    if not os.path.exists(_DIC):
        return None
    return Dictionary.load(_DIC)


# ---- CI-safe: clause splitting and terminators (no dictionary) ----

def test_clause_splitting_terminators() -> None:
    """Each punctuation mark closes a clause with its intonation terminator."""
    cl = _split_clauses("red, green, blue")
    assert [c.terminator for c in cl] == [_COMMA, _COMMA, _PERIOD]
    assert [c.words for c in cl] == [("red",), ("green",), ("blue",)]
    assert [c.terminator for c in _split_clauses("one; two")] == [_COMMA, _PERIOD]
    assert [c.terminator for c in _split_clauses("go now")] == [_PERIOD]
    assert [c.terminator for c in _split_clauses("really?")] == [_QUEST]
    assert [c.terminator for c in _split_clauses("stop!")] == [_EXCLAIM]


def test_clause_framing_shape() -> None:
    """A framed clause is FONT, then WBOUND+word bodies, then the terminator."""
    (clause,) = sentence_to_clauses("hello world", None)
    syms = clause.symbols
    assert syms[0] == 7680  # leading font silence
    assert syms[-1] == _PERIOD
    assert syms.count(111) == 2  # one word boundary marker per word


# ---- CI-safe: speller matches the oracle capture (no dictionary) ----

def test_speller_matches_oracle_capture() -> None:
    """Vowelless tokens are spelled letter by letter, bit-exact vs the oracle."""
    golden = _golden()
    spelled = {t: g for t, g in golden.items() if is_spelled(t)}
    assert spelled, "golden carries no speller words"
    for text, exp in spelled.items():
        mine = [list(c.symbols) for c in sentence_to_clauses(text, None)]
        assert mine == exp, f"speller mismatch for {text!r}"


def test_speller_selection() -> None:
    assert is_spelled("cwm") and is_spelled("jwt") and is_spelled("tsktsk")
    assert not is_spelled("cat") and not is_spelled("hello")
    assert not is_spelled("123") and not is_spelled("")


# ---- CI-safe: number and abbreviation word sequences (no dictionary) ----

def test_cardinal_expansion() -> None:
    assert say_cardinal(0) == ["zero"]
    assert say_cardinal(21) == ["twenty", "one"]
    assert say_cardinal(99) == ["ninety", "nine"]
    assert say_cardinal(123) == ["one", "hundred", "and", "twenty", "three"]
    assert say_cardinal(2005) == ["two", "thousand", "and", "five"]
    assert say_cardinal(1000000) == ["one", "million"]


def test_ordinal_and_digits() -> None:
    assert say_ordinal(1) == ["first"]
    assert say_ordinal(21) == ["twenty", "first"]
    assert say_digits("14") == ["one", "four"]


def test_number_token_kept_for_digit_path() -> None:
    # A numeric/currency token is kept whole; `_word_symbols` reads it through
    # the digit path (`number_token_send_codes`), not the word layer.
    assert _expand_token("3.14") == ["3.14"]
    assert _expand_token("$5") == ["$5"]
    assert _expand_token("1st") == ["1st"]
    assert _expand_token("cat") == ["cat"]


def test_abbreviation_expansion() -> None:
    assert _expand_token("Dr") == ["doctor"]
    assert _expand_token("etc") == ["etcetera"]
    # A period closing a known abbreviation does not split the clause.
    (clause,) = _split_clauses("etc. and so on")
    assert clause.words == ("etcetera", "and", "so", "on")
    assert clause.terminator == _PERIOD
    # Without the period, `Dr` is an ordinary abbreviation and expands to a word.
    (clause,) = _split_clauses("Dr Smith")
    assert clause.words == ("doctor", "Smith")


def test_title_abbreviation_reaches_the_clause() -> None:
    """`Dr.`/`St.` route into the fixed title phone list, not the word table.

    `title_abbrev_body` is unit-tested in `test_dectalk_title.py`. This asserts
    the other half: that `_split_clauses` reaches that path, carries the body
    into `clause.words` as a `_TitleWord`, and consumes the period. Both
    readings appear, so the test fails if the router always picks one.
    """
    # Capitalized follower -> title reading (`pdoctor`), period consumed.
    (clause,) = _split_clauses("Dr. Smith")
    assert clause.words == (_TitleWord(_PDOCTOR), "Smith")
    assert clause.terminator == _PERIOD
    # Clause-final -> word reading (`pdrive`), so the router is not fixed.
    (clause,) = _split_clauses("the Dr.")
    assert clause.words == ("the", _TitleWord(_PDRIVE))
    # `St.` uses its own pair, not `Dr.`'s.
    (clause,) = _split_clauses("St. Peter")
    assert clause.words == (_TitleWord(_PSAINT), "Peter")
    (clause,) = _split_clauses("the St.")
    assert clause.words == ("the", _TitleWord(_PSTREET))


def test_all_abbreviations_have_words() -> None:
    assert all(v and all(w.isalpha() for w in v) for v in ABBREVIATIONS.values())


# ---- dictionary-gated: full framing matches the golden capture ----

def test_framing_matches_golden() -> None:
    """Every golden text reframes bit-exactly to the oracle's `phclause` input."""
    d = _load_dict()
    if d is None:
        pytest.skip("FONIX dtalk_us.dic not available")
    golden = _golden()
    for text, exp in golden.items():
        mine = [list(c.symbols) for c in sentence_to_clauses(text, d)]
        assert mine == exp, f"framing mismatch for {text!r}"


def test_golden_gate_bites() -> None:
    """A perturbed terminator no longer matches the golden (the gate has teeth)."""
    golden = _golden()
    text = "hello world"
    good = [list(c.symbols) for c in sentence_to_clauses(text, None)]
    mutated = [list(good[0][:-1]) + [_QUEST]]  # period -> question
    assert mutated != golden[text]


# ---- oracle-gated: whole-sentence text -> PCM across the ten voices ----

_PCM_TEXTS = [
    "hello world", "one two three", "red, green, blue", "cwm",
    "fish swim deep", "yes, no, maybe",
]


def _oracle():
    try:
        from tools.dump_dectalk_phonemes import ORACLE_BIN, capture
    except Exception:
        return None
    if not ORACLE_BIN or not os.path.exists(ORACLE_BIN):
        return None
    return capture


def test_sentence_text_to_pcm_all_voices() -> None:
    """text -> phonemes -> vtm PCM is sample-exact vs the oracle, all ten voices."""
    capture = _oracle()
    d = _load_dict()
    if capture is None or d is None:
        pytest.skip("instrumented oracle / FONIX dictionary not available")
    from pyretrotts.dectalk.phclause import speak_phonemes

    exact = 0
    total = 0
    for voice in range(10):
        for text in _PCM_TEXTS:
            u = capture(voice, text)
            if u is None:
                continue
            total += 1
            my = speak_phonemes(voice, sentence_to_clauses(text, d))
            if len(my) == len(u.pcm) and all(
                    a == b for a, b in zip(my, u.pcm, strict=False)):
                exact += 1
    assert total > 0
    assert exact == total, f"{exact}/{total} sentences sample-exact"


if __name__ == "__main__":
    d = _load_dict()
    golden = _golden()
    if d is not None:
        ok = sum(
            1 for t, e in golden.items()
            if [list(c.symbols) for c in sentence_to_clauses(t, d)] == e)
        print(f"framing vs oracle golden: {ok}/{len(golden)} texts exact")
