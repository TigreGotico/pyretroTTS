"""DECtalk US in-context article reduction + digit-path numbers vs the oracle.

Two front-end mechanisms, each pinned to its C site:

- **In-context function-word reduction** (`grammar_us.article_a_codes`,
  `lts/ls_task.c:2632-2645`). The single-character word ``a`` reduces to the
  schwa article ``[SPECIALWORD, US_AX]`` when another word follows it in the
  clause (the C's whitespace-followed test); against clause-final punctuation it
  keeps the citation ``[S1, EY]``. `phsort` deletes the `SPECIALWORD`, so the
  post-`phsort` body is the bare ``US_AX``.
- **Digit-path number / currency reading** (`numbers_us.number_token_send_codes`,
  `lts/l_us_pr1.c` `ls_proc_do_number` / `ls_proc_do_digit_group`,
  `lts/ls_task.c` currency). Integers, ordinals, currency and decimals are read
  by shipping fixed phoneme+marker lists (`l_us_con.c`), so the hundreds/scale
  ``and`` carries a `VPSTART` (`pand`) and currency ``dollar(s)`` uses the
  reader's own vowel (`pdollar`), where the word/dictionary path would not.

The CI-safe checks run the two emitters directly, no oracle, no FONIX
dictionary, each with a mutation gate. The framing / ten-voice PCM diffs reuse
the grammar battery golden and are gated on the instrumented oracle and the
FONIX dictionary, mirroring `test_dectalk_grammar`.
"""
import json
import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pyretrotts.dectalk.numbers_us as numbers_us  # noqa: E402
from pyretrotts.dectalk.grammar_us import article_a_codes  # noqa: E402
from pyretrotts.dectalk.numbers_us import number_token_send_codes  # noqa: E402

_GRAMMAR_GOLDEN = os.path.join(
    os.path.dirname(__file__), "dectalk_grammar_golden.json")

# The two mechanisms' battery categories in the grammar golden.
_ARTICLE_CATS = ("articles", "funcword", "conj")
_NUMBER_CATS = ("numbers", "bignumbers", "currency", "decimals")


# ---- CI-safe: mechanism 1, the in-context article reduction ----

def test_article_a_reduces_in_context() -> None:
    """A standalone ``a`` with a following word reduces to the schwa US_AX."""
    assert article_a_codes("a", clause_final=False) == (17,)
    assert article_a_codes("A", clause_final=False) == (17,)


def test_article_a_keeps_citation_clause_final() -> None:
    """A clause-final ``a`` (against punctuation) keeps the citation form."""
    assert article_a_codes("a", clause_final=True) is None


def test_article_only_single_a() -> None:
    """Only the single-character word ``a`` is special-cased."""
    assert article_a_codes("an", clause_final=False) is None
    assert article_a_codes("the", clause_final=False) is None
    assert article_a_codes("cat", clause_final=False) is None


# ---- CI-safe: mechanism 3, the digit-path phone-list reader ----

# Phone lists transcribed independently from `l_us_con.c` for the assertions.
_P1 = [24, 103, 9, 32]              # one:    W S1 AH N
_P3 = [39, 26, 103, 1]             # three:  TH R S1 IY
_P5 = [37, 103, 7, 38]             # five:   F S1 AY V
_P20 = [47, 24, 103, 4, 32, 47, 1]  # twenty: T W S1 EH N T IY
_PHUNDRED = [28, 103, 9, 32, 48, 26, 17, 48]  # HX S1 AH N D R AX D
_PAND = [113, 4, 32, 48, 111]      # VPSTART EH N D WBOUND (leading WBOUND gone)
_PDOLLAR = [111, 48, 103, 6, 27, 15]  # WBOUND D S1 AA LL RR
_P1ST = [37, 103, 15, 41, 47]      # first:  F S1 RR S T


def test_small_integer_uses_punits() -> None:
    assert number_token_send_codes("5") == _P5


def test_two_digit_uses_tens_and_units() -> None:
    assert number_token_send_codes("21") == [*_P20, 111, *_P1]


def test_hundreds_and_carries_vpstart() -> None:
    """`123` reads `one hundred [pand=VPSTART] twenty three`."""
    assert number_token_send_codes("123") == [
        *_P1, 111, *_PHUNDRED, *_PAND, *_P20, 111, *_P3]


def test_currency_uses_pdollar_and_plural() -> None:
    """`$5` reads `five` + `pdollar` + Z (plural)."""
    assert number_token_send_codes("$5") == [*_P5, *_PDOLLAR, 42]


def test_ordinal_uses_pordin() -> None:
    assert number_token_send_codes("1st") == _P1ST


def test_non_numeric_returns_none() -> None:
    assert number_token_send_codes("cat") is None
    assert number_token_send_codes("") is None


def test_number_gate_bites() -> None:
    """Corrupting the `pand` list changes the ported `123` reading."""
    good = number_token_send_codes("123")
    saved = numbers_us._PAND
    try:
        numbers_us._PAND = (numbers_us._VPSTART, numbers_us._AE,
                            numbers_us._N, numbers_us._D, numbers_us._WBOUND)
        assert number_token_send_codes("123") != good
    finally:
        numbers_us._PAND = saved


# ---- oracle + dictionary gated ----

def _load_dict():
    from pyretrotts.dectalk.dictionary import Dictionary

    for cand in (
        os.path.expanduser("~/AgentWorkspaces/ovos/dectalk-c/src/dapi/build/"
                            "dic/7.1.3-arch1-1/us/release/dtalk_us.dic"),
        os.path.expanduser("~/AgentWorkspaces/ovos/dectalk-c/dist/dic/"
                           "dtalk_us.dic"),
    ):
        if os.path.exists(cand):
            return Dictionary.load(cand)
    return None


def _oracle():
    try:
        from tools.dump_dectalk_phonemes import ORACLE_BIN, capture
    except Exception:
        return None
    if not ORACLE_BIN or not os.path.exists(ORACLE_BIN):
        return None
    return capture


def _golden() -> dict:
    with open(_GRAMMAR_GOLDEN) as f:
        return json.load(f)


def _texts(categories) -> list[str]:
    battery = _golden()["battery"]
    seen: list[str] = []
    for cat in categories:
        for t in battery.get(cat, []):
            if t not in seen:
                seen.append(t)
    return seen


@pytest.mark.parametrize("categories,mechanism", [
    (_ARTICLE_CATS, "article"),
    (_NUMBER_CATS, "number"),
])
def test_mechanism_framing_matches_oracle(categories, mechanism) -> None:
    """Each mechanism's PCM-exact battery texts also frame bit-exact vs C."""
    d = _load_dict()
    capture = _oracle()
    if d is None or capture is None:
        pytest.skip("instrumented oracle / FONIX dictionary not available")
    from pyretrotts.dectalk.sentence_us import sentence_to_clauses

    exact_set = set(_golden()["exact"])
    checked = 0
    for text in _texts(categories):
        if text not in exact_set:
            continue
        u = capture(0, text)
        if u is None:
            continue
        checked += 1
        ref = [list(c.symbols) for c in u.clauses]
        mine = [list(c.symbols) for c in sentence_to_clauses(text, d)]
        assert mine == ref, f"{mechanism} framing mismatch for {text!r}"
    assert checked > 0


@pytest.mark.parametrize("categories,mechanism", [
    (_ARTICLE_CATS, "article"),
    (_NUMBER_CATS, "number"),
])
def test_mechanism_pcm_all_voices(categories, mechanism) -> None:
    """Each mechanism's PCM-exact texts stay sample-exact across ten voices."""
    d = _load_dict()
    capture = _oracle()
    if d is None or capture is None:
        pytest.skip("instrumented oracle / FONIX dictionary not available")
    from pyretrotts.dectalk.sentence_us import sentence_to_pcm

    pcm_set = set(_golden()["pcm_exact"])
    exact = total = 0
    for text in _texts(categories):
        if text not in pcm_set:
            continue
        for voice in range(10):
            u = capture(voice, text)
            if u is None:
                continue
            total += 1
            want = struct.pack(f"<{len(u.pcm)}h", *u.pcm)
            exact += sentence_to_pcm(voice, text, d) == want
    assert total > 0
    assert exact == total, f"{mechanism}: {exact}/{total} renders sample-exact"
