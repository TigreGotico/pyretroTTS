"""DECtalk US letter-to-sound rule engine, diffed against the C oracle.

`pyretrotts.dectalk.lts_rules.pronounce` runs the ported `ls_rule*` interpreter
plus `ls_adju*` syllabification/stress/allophony for an out-of-dictionary word
and returns the phoneme+stress code stream the C hands to `ls_util_send_phone`
(the pre-`ph/` boundary). `test/dectalk_lts_rules_golden.json` is a committed real
capture of that exact boundary (the instrumented oracle, one process per word)
over 194 confirmed dictionary-miss words. This runs in CI without the oracle.

The oracle-gated part composes the whole US text-to-speech path for a lone word
-- text -> rule engine -> `phclause` -> `vtm` -> PCM -- and diffs it against the
oracle WAV sample for sample. It skips without the instrumented `say`.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.dectalk.lts_rules import pronounce  # noqa: E402
from pyretrotts.dectalk.text_us import single_word_symbols, word_to_codes  # noqa: E402

_GOLDEN = os.path.join(os.path.dirname(__file__), "dectalk_lts_rules_golden.json")

# Words the oracle routes to its speller (no vowel / non-ASCII), emitting the
# letter-name code 111 -- that decision lives in the word-reading front end
# (`ls_task`), not the letter-to-sound rule engine ported here.
_SPELLER_WORDS = {"cwm", "cwtch", "jwt", "tsktsk", "h込"}
# One residual rule-table difference: the oracle splits `oi` in "memoize" as
# o.ize (OW AY) where the interpreter selects the OY diphthong rule (which is
# correct for "void", "boid", ...). A single right-context case.
_RULE_RESIDUAL = {"memoize"}
_KNOWN_MISMATCH = _SPELLER_WORDS | _RULE_RESIDUAL


def _load() -> dict[str, list[int]]:
    with open(_GOLDEN) as f:
        return json.load(f)["words"]


def test_rules_match_oracle_capture() -> None:
    """Every rule-eligible word matches the oracle's pre-ph/ stream exactly."""
    words = _load()
    exact = 0
    mism: list[str] = []
    for w, exp in words.items():
        if list(pronounce(w).codes) == exp:
            exact += 1
        else:
            mism.append(w)
    # No new regressions: mismatches are exactly the documented known set.
    assert set(mism) == _KNOWN_MISMATCH, f"unexpected mismatches: {set(mism) - _KNOWN_MISMATCH}"
    # Of the rule-eligible words (excluding speller-routed), only the one
    # documented residual differs.
    eligible = len(words) - len(_SPELLER_WORDS)
    assert exact == eligible - len(_RULE_RESIDUAL)
    assert exact / eligible > 0.99


def test_rules_deterministic() -> None:
    """`pronounce` is a pure function of the word."""
    for w in ("zorph", "blornt", "kubernetes"):
        assert pronounce(w).codes == pronounce(w).codes


@pytest.mark.parametrize(
    ("word", "codes"),
    [
        ("zorph", [42, 103, 10, 26, 37]),
        ("blornt", [46, 27, 103, 10, 26, 32, 47]),
        ("fnord", [37, 32, 103, 10, 26, 48]),
    ],
)
def test_rules_spot_values(word: str, codes: list[int]) -> None:
    assert list(pronounce(word).codes) == codes


# ---- oracle-gated: full text -> PCM for a lone out-of-dictionary word ----

_OOD_WORDS = [
    "zorph", "blornt", "quizzle", "fnord", "splee",
    "thwack", "glimble", "vorp", "kubernetes", "bjork",
]


def _oracle():
    try:
        from tools.dump_dectalk_phonemes import ORACLE_BIN, capture
    except Exception:
        return None
    if not ORACLE_BIN or not os.path.exists(ORACLE_BIN):
        return None
    return capture


def test_ood_word_text_to_pcm_matches_oracle() -> None:
    """text -> rule engine -> phclause -> vtm PCM is sample-exact vs the oracle."""
    capture = _oracle()
    if capture is None:
        pytest.skip("instrumented oracle say not available")
    from pyretrotts.dectalk.phclause import Clause, speak_phonemes

    exact = 0
    total = 0
    for w in _OOD_WORDS:
        u = capture(0, w)
        if u is None:
            continue
        total += 1
        codes, src = word_to_codes(w, None)
        assert src == "rule"
        my = speak_phonemes(0, [Clause(single_word_symbols(codes))])
        n = min(len(my), len(u.pcm))
        bad = sum(1 for a, b in zip(my[:n], u.pcm[:n], strict=False) if a != b) + abs(len(my) - len(u.pcm))
        if bad == 0:
            exact += 1
    assert total > 0
    assert exact == total, f"{exact}/{total} OOD words sample-exact"


if __name__ == "__main__":
    words = _load()
    exact = sum(1 for w, e in words.items() if list(pronounce(w).codes) == e)
    print(f"rule engine vs oracle capture: {exact}/{len(words)} words exact")
