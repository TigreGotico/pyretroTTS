"""Wh-question terminator selection and its text->PCM parity."""
from __future__ import annotations

import os
import struct

import pytest

from pyretrotts.dectalk.sentence_us import _PERIOD, _QUEST, _split_clauses

# Wh-questions read with a falling terminator; yes/no questions keep the rise.
_WH_EXACT = ("what is that?", "who are you?", "what time is it?",
             "where is it?", "which way?")
_YESNO = ("do you know?", "can you see?")


def _terminator(text: str) -> int:
    return _split_clauses(text)[-1].terminator


def test_wh_question_reads_as_period() -> None:
    for text in _WH_EXACT:
        assert _terminator(text) == _PERIOD, text


def test_yesno_question_keeps_quest() -> None:
    for text in _YESNO:
        assert _terminator(text) == _QUEST, text


def test_wh_word_only_shifts_a_question() -> None:
    # The wh-terminator applies to `?` clauses, never to a plain statement.
    assert _terminator("what is that") == _PERIOD  # no `?`, already falling
    assert _terminator("go home now.") == _PERIOD
    assert _terminator("is it cold?") == _QUEST     # yes/no keeps the rise


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


def test_wh_question_pcm_all_voices() -> None:
    d = _load_dict()
    capture = _oracle()
    if d is None or capture is None:
        pytest.skip("oracle/dictionary not available")
    from pyretrotts.dectalk.sentence_us import sentence_to_pcm

    exact = total = 0
    for text in _WH_EXACT:
        for voice in range(10):
            u = capture(voice, text)
            if u is None:
                continue
            total += 1
            want = struct.pack(f"<{len(u.pcm)}h", *u.pcm)
            exact += sentence_to_pcm(voice, text, d) == want
    assert total > 0
    assert exact == total, f"{exact}/{total} wh-question renders sample-exact"


# Yes/no questions on a clause-head be-form: the auxiliary carries a leading S2.
_YESNO_AUX = ("are you there?", "is it cold?", "was it good?",
              "were you here?", "is she home?", "are they ready?")


def test_yesno_aux_pcm_all_voices() -> None:
    d = _load_dict()
    capture = _oracle()
    if d is None or capture is None:
        pytest.skip("oracle/dictionary not available")
    from pyretrotts.dectalk.sentence_us import sentence_to_pcm

    exact = total = 0
    for text in _YESNO_AUX:
        for voice in range(10):
            u = capture(voice, text)
            if u is None:
                continue
            total += 1
            want = struct.pack(f"<{len(u.pcm)}h", *u.pcm)
            exact += sentence_to_pcm(voice, text, d) == want
    assert total > 0
    assert exact == total, f"{exact}/{total} yes/no-aux renders sample-exact"


def test_gate_bites_without_head_aux_stress() -> None:
    # Dropping the clause-head be-form set makes `is it cold?` diverge: the S2
    # rule has teeth. Verified against voice 0.
    d = _load_dict()
    capture = _oracle()
    if d is None or capture is None:
        pytest.skip("oracle/dictionary not available")
    from pyretrotts.dectalk import sentence_us

    text = "is it cold?"
    u = capture(0, text)
    want = struct.pack(f"<{len(u.pcm)}h", *u.pcm)
    saved = sentence_us._HEAD_STRESS_AUX
    try:
        sentence_us._HEAD_STRESS_AUX = frozenset()
        wrong = sentence_us.sentence_to_pcm(0, text, d)
    finally:
        sentence_us._HEAD_STRESS_AUX = saved
    assert wrong != want


def test_gate_bites_without_wh_terminator() -> None:
    # A wh-question rendered with QUEST diverges from the oracle: the gate has
    # teeth. Verified against voice 0 of the first wh-question.
    d = _load_dict()
    capture = _oracle()
    if d is None or capture is None:
        pytest.skip("oracle/dictionary not available")
    from pyretrotts.dectalk import sentence_us

    text = _WH_EXACT[0]
    u = capture(0, text)
    want = struct.pack(f"<{len(u.pcm)}h", *u.pcm)
    saved = sentence_us._WH_WORDS
    try:
        sentence_us._WH_WORDS = frozenset()
        wrong = sentence_us.sentence_to_pcm(0, text, d)
    finally:
        sentence_us._WH_WORDS = saved
    assert wrong != want
