"""Residual US text->PCM edges: the `y`-vowel word-vs-speller decision (`why`)
and the still-open `Dr.`-title abbreviation disambiguation (`dr. smith`)."""
from __future__ import annotations

import os
import struct

import pytest


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


# A token whose only vowel letter is `y` is pronounced, never letter-spelled.
_Y_WORDS = ("why not?", "why", "my", "by", "shy", "gym", "sky", "rhythm")


def test_y_is_a_vowel_not_spelled() -> None:
    from pyretrotts.dectalk.spell_us import is_spelled

    for token in ("why", "my", "gym", "rhythm"):
        assert not is_spelled(token), token
    # A token with no a/e/i/o/u/y is still spelled.
    assert is_spelled("pqr")


def test_y_word_pcm_all_voices() -> None:
    d = _load_dict()
    capture = _oracle()
    if d is None or capture is None:
        pytest.skip("oracle/dictionary not available")
    from pyretrotts.dectalk.sentence_us import sentence_to_pcm

    exact = total = 0
    for text in _Y_WORDS:
        for voice in range(10):
            u = capture(voice, text)
            if u is None:
                continue
            total += 1
            want = struct.pack(f"<{len(u.pcm)}h", *u.pcm)
            exact += sentence_to_pcm(voice, text, d) == want
    assert total > 0
    assert exact == total, f"{exact}/{total} y-word renders sample-exact"


def test_gate_bites_without_y_vowel() -> None:
    # Treating `y` as a non-vowel spells `why` letter by letter, diverging.
    d = _load_dict()
    capture = _oracle()
    if d is None or capture is None:
        pytest.skip("oracle/dictionary not available")
    from pyretrotts.dectalk import sentence_us, spell_us

    text = "why not?"
    u = capture(0, text)
    want = struct.pack(f"<{len(u.pcm)}h", *u.pcm)
    saved = spell_us._VOWELS
    try:
        spell_us._VOWELS = frozenset("aeiou")
        wrong = sentence_us.sentence_to_pcm(0, text, d)
    finally:
        spell_us._VOWELS = saved
    assert wrong != want


def test_dr_title_abbreviation_is_open() -> None:
    # `Dr. <Name>` reads through the unported `pdoctor`/`pdrive` parser
    # disambiguation (`cmd/par_*.c`): the port expands `dr` -> the full word
    # `doctor` (stressed, AO vowel) where the oracle emits the destressed title
    # form (AA vowel). This asserts the known residual, so closing it flips here.
    d = _load_dict()
    capture = _oracle()
    if d is None or capture is None:
        pytest.skip("oracle/dictionary not available")
    from pyretrotts.dectalk.sentence_us import sentence_to_pcm

    text = "dr. smith"
    u = capture(0, text)
    want = struct.pack(f"<{len(u.pcm)}h", *u.pcm)
    assert sentence_to_pcm(0, text, d) != want
