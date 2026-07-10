"""Verify the DECtalk US text front end against real oracle captures.

Two gates:

* Render round-trip over the committed real-capture golden
  (`test/dectalk_lts_golden.json`, from `tools/dump_dectalk_lts.py`): every
  `us_<name>` phoneme token the oracle wrote must decode through
  `lts.phoneme_spans` and re-render byte-identically. This runs in CI without
  the oracle and bites on any ARPABET-table mutation.

* Dictionary phoneme payload: for a curated set of dictionary hits, the phoneme
  code sequence `dictionary.Dictionary.lookup` returns must equal the phonemes
  the oracle emitted for the same text. Needs the FONIX `dtalk_us.dic`; skipped
  when absent.

Homographs (`wind`, `read` as verb/noun) are excluded: their disambiguation is
the part-of-speech stage, not ported.
"""
from __future__ import annotations

import json
import os

import pytest

from pyretrotts.dectalk import lts
from pyretrotts.dectalk.dictionary import Dictionary

_HERE = os.path.dirname(__file__)
GOLDEN = os.path.join(_HERE, "dectalk_lts_golden.json")
DIC = os.path.expanduser(
    "~/AgentWorkspaces/ovos/dectalk-c/dist/dic/dtalk_us.dic")


def _load_golden() -> dict[str, dict[str, str]]:
    with open(GOLDEN) as f:
        return json.load(f)


def _all_captures() -> list[tuple[str, str, str]]:
    out = []
    for cat, items in _load_golden().items():
        for text, log in items.items():
            out.append((cat, text, log))
    return out


@pytest.mark.parametrize("cat,text,log", _all_captures())
def test_render_roundtrip(cat: str, text: str, log: str) -> None:
    """Every oracle phoneme token decodes and re-renders identically."""
    spans = lts.phoneme_spans(log)
    for code, start, end in spans:
        raw = log[start:end]
        assert lts.render_symbol(lts.Symbol(code)) == raw, (text, raw)


def test_phoneme_codes_bijective() -> None:
    """The `l_us_ph.h` name<->code map is a bijection."""
    assert len(lts.US_PHONEME_NAMES) == len(lts.US_PHONEME_CODES) == 57
    for name, code in lts.US_PHONEME_CODES.items():
        assert lts.US_PHONEME_NAMES[code] == name


# Curated dictionary hits (single words and multiword phrases), none homographs.
DICT_CASES = [
    "cat", "computer", "dog", "water", "people", "house",
    "hello world", "the quick brown fox",
]


def _phonemes(codes: list[int]) -> list[int]:
    return [c for c in codes if c < 57]


@pytest.mark.skipif(not os.path.exists(DIC), reason="dtalk_us.dic absent")
def test_dictionary_phonemes_match_oracle() -> None:
    d = Dictionary.load(DIC)
    golden = _load_golden()
    flat = {t: log for items in golden.values() for t, log in items.items()}
    for text in DICT_CASES:
        oracle = [c for c, _s, _e in lts.phoneme_spans(flat[text])]
        got: list[int] = []
        for word in text.split():
            codes = d.lookup(word)
            assert codes is not None, f"dict miss: {word}"
            got.extend(_phonemes(codes))
        assert got == oracle, text


@pytest.mark.skipif(not os.path.exists(DIC), reason="dtalk_us.dic absent")
def test_out_of_dictionary_words_miss() -> None:
    """OOD words are dictionary misses (the rule engine is not ported)."""
    d = Dictionary.load(DIC)
    for word in ["zorph", "blornt", "quizzle"]:
        assert d.lookup(word) is None, word


# --- [: ] command parser (cmd.py) -------------------------------------------
from pyretrotts.dectalk import cmd  # noqa: E402


def test_cmd_tokenize_text_and_commands() -> None:
    ev = cmd.tokenize("[:nb]hello [:rate 200]world")
    assert ev == [
        cmd.Command("nb", ""),
        cmd.TextRun("hello "),
        cmd.Command("rate", "200"),
        cmd.TextRun("world"),
    ]


def test_cmd_unclosed_command_runs_to_next() -> None:
    ev = cmd.tokenize("[:ra 170 [:nb]x")
    assert ev[0] == cmd.Command("ra", "170")
    assert ev[1] == cmd.Command("nb", "")
    assert ev[2] == cmd.TextRun("x")


def test_cmd_runs_carry_control() -> None:
    r = cmd.runs("[:np]one[:nu][:rate 300]two")
    assert [(x.control.voice, x.control.rate, x.text) for x in r] == [
        (0, None, "one"),
        (6, 300, "two"),
    ]


def test_cmd_phoneme_mode_flag() -> None:
    r = cmd.runs("plain[:phoneme on]phon[:phoneme off]plain2")
    assert [(x.control.phoneme_mode, x.text) for x in r] == [
        (False, "plain"),
        (True, "phon"),
        (False, "plain2"),
    ]
