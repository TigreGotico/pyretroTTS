"""DECtalk US inflectional-suffix morphology, diffed against the C oracle.

`pyretrotts.dectalk.morph_us` ports the dictionary-miss suffix stripper
(`lts/ls_suff.c` `ls_suff_suffix_find` / `ls_suff_append_pron`) over the verbatim
`suffix_table`/`suffix_index` trie (`suffix_data.py`): a word that misses the
main dictionary has an inflection stripped, the stem re-looked-up, and the
suffix's phonemes appended, selected by a `pfeat` feature test on the stem's last
phoneme -- `dogs` -> `dog` + `Z`, `cats` -> `cat` + `S`, `boxes` -> `box` +
`IX Z`. `text_us.word_to_codes` routes it (`ls_dict.c:450-458`).

The CI-safe checks drive the interpreter with a stub stem dictionary (no oracle,
no FONIX dictionary). The framing / per-category / ten-voice PCM diffs reuse the
grammar battery golden (`dectalk_grammar_golden.json`) and are gated on the
instrumented oracle and the FONIX dictionary, mirroring `test_dectalk_grammar`.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pyretrotts.dectalk.morph_us as morph_us  # noqa: E402
from pyretrotts.dectalk.morph_us import suffix_codes  # noqa: E402

_GRAMMAR_GOLDEN = os.path.join(
    os.path.dirname(__file__), "dectalk_grammar_golden.json")


class _StubDict:
    """A stem-only dictionary: the phoneme+stress payload for known stems."""

    _STEMS = {
        "dog": [48, 103, 10, 50],       # d S1 AA G
        "cat": [49, 103, 5, 47],        # k S1 AE T
        "box": [46, 103, 6, 49, 41],    # b S1 AH K S
        "wish": [24, 103, 2, 43],       # w S1 IH SH
    }

    def lookup(self, word: str):
        stem = self._STEMS.get(word)
        return list(stem) if stem is not None else None


# ---- CI-safe: the suffix strip + sibilant selection (no oracle, no dict) ----

def test_voiced_stem_takes_z() -> None:
    """A voiced non-sibilant stem (`dog`) takes the Z plural (`ls_suff.c`)."""
    assert suffix_codes("dogs", _StubDict()) == [48, 103, 10, 50, 42]


def test_voiceless_stem_takes_s() -> None:
    """A voiceless stem (`cat`) takes the S plural."""
    assert suffix_codes("cats", _StubDict()) == [49, 103, 5, 47, 41]


def test_sibilant_stem_takes_ix_z() -> None:
    """A sibilant stem (`box`, `wish`) takes the IX Z plural after -es."""
    assert suffix_codes("boxes", _StubDict()) == [46, 103, 6, 49, 41, 18, 42]
    assert suffix_codes("wishes", _StubDict()) == [24, 103, 2, 43, 18, 42]


def test_no_strip_without_dictionary_stem() -> None:
    """No result when the stem is not in the dictionary, or the word is short."""
    assert suffix_codes("cats", None) is None
    assert suffix_codes("is", _StubDict()) is None       # <= 2 letters
    assert suffix_codes("xyzzys", _StubDict()) is None    # stem miss
    assert suffix_codes("dog", _StubDict()) is None       # not inflected


def test_golden_gate_bites() -> None:
    """Corrupting the plural phoneme field changes the ported plural output."""
    good = suffix_codes("dogs", _StubDict())
    saved = morph_us.SUFFIX_TABLE
    try:
        mutated = bytearray(saved)
        mutated[31] = 40  # off0 rule default -s phone (Z, 42) -> 40
        morph_us.SUFFIX_TABLE = bytes(mutated)
        assert suffix_codes("dogs", _StubDict()) != good
    finally:
        morph_us.SUFFIX_TABLE = saved


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


def test_inflection_word_codes_match_oracle() -> None:
    """Each inflected battery word composes text -> codes as the oracle does."""
    d = _load_dict()
    capture = _oracle()
    if d is None or capture is None:
        pytest.skip("instrumented oracle / FONIX dictionary not available")
    from pyretrotts.dectalk.text_us import word_to_codes

    for word in ("dogs", "cats", "boxes", "walks", "books", "pens", "hats"):
        u = capture(0, word)
        inner = [c - 7680 if c >= 7680 else c for c in u.clauses[0].symbols[2:-1]]
        codes, _src = word_to_codes(word, d)
        assert codes == inner, f"{word!r}: {codes} != {inner}"


def test_inflection_pcm_all_voices() -> None:
    """The inflection battery is text -> PCM sample-exact across ten voices."""
    d = _load_dict()
    capture = _oracle()
    if d is None or capture is None:
        pytest.skip("instrumented oracle / FONIX dictionary not available")
    from pyretrotts.dectalk.phclause import speak_phonemes
    from pyretrotts.dectalk.sentence_us import sentence_to_clauses

    texts = _golden()["battery"]["inflection"]
    exact = total = 0
    for voice in range(10):
        for text in texts:
            u = capture(voice, text)
            if u is None:
                continue
            total += 1
            my = speak_phonemes(voice, sentence_to_clauses(text, d))
            exact += len(my) == len(u.pcm) and all(
                a == b for a, b in zip(my, u.pcm, strict=False))
    assert total > 0
    assert exact == total, f"{exact}/{total} inflection renders sample-exact"
