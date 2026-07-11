"""US `Dr.`/`St.` title-abbreviation disambiguation (`ls_task.c:2910`).

The title reading (`pdoctor`/`psaint`, destressed, before a name) versus the word
reading (`pdrive`/`pstreet`) is selected by the following word's capitalization,
the sentence-initial position, and the clause-final case. These tests pin the
selection rule, the framing against the instrumented oracle, and the text->PCM
sample-exact renders across all ten voices.
"""
from __future__ import annotations

import os
import struct

import pytest

from pyretrotts.dectalk.title_abbrev_us import (
    TITLE_ABBREVIATIONS,
    title_abbrev_body,
)


def _load_dict():
    from pyretrotts.dectalk.dictionary import Dictionary

    cand = os.path.expanduser(
        "~/AgentWorkspaces/ovos/dectalk-c/src/dapi/build/dic/"
        "7.1.3-arch1-1/us/release/dtalk_us.dic")
    return Dictionary.load(cand) if os.path.exists(cand) else None


def _oracle():
    try:
        from tools.dump_dectalk_phonemes import ORACLE_BIN, capture
    except Exception:
        return None
    return capture if ORACLE_BIN and os.path.exists(ORACLE_BIN) else None


# Texts whose framing and PCM are bit-exact vs the oracle (the word-context and
# title-context readings of `dr`/`st`). `mr. jones` is deliberately excluded: it
# has no dedicated title symbol and expands through the ordinary abbreviation
# table.
_TITLE_TEXTS = (
    "dr. smith", "st. john", "the dr. is in", "doctor smith", "i saw dr. smith",
)

_PDOCTOR = (48, 6, 49, 47, 15)
_PDRIVE = (48, 26, 103, 7, 38)


def test_only_dr_and_st_have_title_symbols() -> None:
    assert set(TITLE_ABBREVIATIONS) == {"dr", "st"}


def test_selection_rule() -> None:
    # Following a capitalized name -> title reading.
    assert title_abbrev_body("dr", "Smith", sentence_initial=False) == _PDOCTOR
    # Back-to-back `Dr Dr` -> word reading (the GL 1997 fix).
    assert title_abbrev_body("dr", "Dr", sentence_initial=False) == _PDRIVE
    # Lowercase follower, sentence-initial -> title reading.
    assert title_abbrev_body("dr", "smith", sentence_initial=True) == _PDOCTOR
    # Lowercase follower, mid-sentence -> word reading.
    assert title_abbrev_body("dr", "is", sentence_initial=False) == _PDRIVE
    # Clause-final (no follower) -> word reading.
    assert title_abbrev_body("dr", None, sentence_initial=True) == _PDRIVE
    # Non-title abbreviation -> no dedicated symbol.
    assert title_abbrev_body("mr", "Jones", sentence_initial=True) is None


def test_title_framing_matches_oracle() -> None:
    d = _load_dict()
    capture = _oracle()
    if d is None or capture is None:
        pytest.skip("instrumented oracle / FONIX dictionary not available")
    from pyretrotts.dectalk.sentence_us import sentence_to_clauses

    for text in _TITLE_TEXTS:
        u = capture(0, text)
        if u is None:
            continue
        ref = [list(c.symbols) for c in u.clauses]
        mine = [list(c.symbols) for c in sentence_to_clauses(text, d)]
        assert mine == ref, f"framing mismatch for {text!r}"


def test_title_pcm_all_voices() -> None:
    d = _load_dict()
    capture = _oracle()
    if d is None or capture is None:
        pytest.skip("instrumented oracle / FONIX dictionary not available")
    from pyretrotts.dectalk.sentence_us import sentence_to_pcm

    exact = total = 0
    for text in _TITLE_TEXTS:
        for voice in range(10):
            u = capture(voice, text)
            if u is None:
                continue
            total += 1
            want = struct.pack(f"<{len(u.pcm)}h", *u.pcm)
            exact += sentence_to_pcm(voice, text, d) == want
    assert total > 0
    assert exact == total, f"{exact}/{total} title renders sample-exact"


def test_gate_bites_on_swapped_title_and_word() -> None:
    # Reading `dr. smith` (a title context) with the word body diverges from C.
    d = _load_dict()
    capture = _oracle()
    if d is None or capture is None:
        pytest.skip("instrumented oracle / FONIX dictionary not available")
    from pyretrotts.dectalk import sentence_us, title_abbrev_us

    text = "dr. smith"
    u = capture(0, text)
    want = struct.pack(f"<{len(u.pcm)}h", *u.pcm)
    saved = title_abbrev_us.TITLE_ABBREVIATIONS["dr"]
    try:
        title_abbrev_us.TITLE_ABBREVIATIONS["dr"] = title_abbrev_us._TitleReading(
            title=saved.word, word=saved.title)
        wrong = sentence_us.sentence_to_pcm(0, text, d)
    finally:
        title_abbrev_us.TITLE_ABBREVIATIONS["dr"] = saved
    assert wrong != want
