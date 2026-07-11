"""DECtalk US word-level syntactic marking, diffed against the C oracle.

`pyretrotts.dectalk.grammar_us` reproduces the phrase markers the word-reading
path inserts into the `phclause` `symbols[]` stream: `VPSTART` before a
dictionary verb (`ls_dict.c:759-763`), and `PPSTART` before the closed-class
prep-phrase words `for`/`and`/`to` (`l_us_con.c` `sdic[]`) and any dictionary
prep-phrase word. `sentence_us` emits these ahead of each word's phonemes.

`test/dectalk_grammar_golden.json` is a committed real capture of that boundary
(the instrumented oracle) over a category battery, recording the texts the port
reproduces framing-exact and voice-0 PCM-exact. The unit checks and the
mutation gate run in CI without the oracle; the full framing and the
per-category / ten-voice PCM diffs are gated on the FONIX dictionary and the
instrumented oracle.
"""
import json
import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pyretrotts.dectalk.grammar_us as grammar_us  # noqa: E402
from pyretrotts.dectalk.grammar_us import word_markers  # noqa: E402
from pyretrotts.dectalk.sentence_us import sentence_to_clauses  # noqa: E402

_GOLDEN = os.path.join(os.path.dirname(__file__), "dectalk_grammar_golden.json")

_WBOUND, _PPSTART, _VPSTART = 111, 112, 113


def _golden() -> dict:
    with open(_GOLDEN) as f:
        return json.load(f)


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
    try:
        from tools.dump_dectalk_phalloph import DIC_DIR

        cand = os.path.join(DIC_DIR, "dtalk_us.dic")
        if os.path.exists(cand):
            return Dictionary.load(cand)
    except Exception:
        pass
    return None


class _StubDict:
    """A dictionary returning a fixed form class, for the unit checks."""

    def __init__(self, fc: int | None) -> None:
        self._fc = fc

    def lookup_fc(self, word: str) -> int | None:
        return self._fc


# ---- CI-safe: the marker decision (no dictionary, no oracle) ----

def test_sdic_words_get_prep_phrase_marker() -> None:
    """`for`/`and`/`to` carry a leading WBOUND then PPSTART regardless of dict."""
    for w in ("for", "and", "to"):
        assert word_markers(w, None) == (_WBOUND, _PPSTART)
    assert set(grammar_us.SDIC) == {"for", "and", "to"}


def test_dictionary_verb_gets_verb_phrase_marker() -> None:
    """A word whose form class is VPHRASE or exactly FC_VERB gets VPSTART."""
    fc_verb = 0x00020000
    fc_vphrase = 0x00020000 | 0x02000000
    assert word_markers("sing", _StubDict(fc_verb)) == (_VPSTART,)
    assert word_markers("went", _StubDict(fc_vphrase)) == (_VPSTART,)


def test_dictionary_prep_and_plain_words() -> None:
    """A PPHRASE word gets WBOUND+PPSTART; a plain noun gets no leading marker."""
    fc_pphrase = 0x00001000 | 0x02000000
    assert word_markers("aboard", _StubDict(fc_pphrase)) == (_WBOUND, _PPSTART)
    assert word_markers("cat", _StubDict(0x00000400)) is None  # FC_NOUN
    assert word_markers("cat", None) is None  # no dict, not sdic


def test_bare_preposition_gets_no_marker() -> None:
    """`in`/`on` (FC_PREP without FC_CHARACTER) get no phrase marker."""
    assert word_markers("in", _StubDict(0x00801000)) is None


# ---- CI-safe: the golden gate has teeth ----

def test_golden_gate_bites(monkeypatch) -> None:
    """Neutralizing the verb marker changes a golden verb text's framing."""
    golden = _golden()
    exact = golden["exact"]
    verb_text = next(
        (t for t in golden["battery"]["verbs"] if t in exact), None)
    if verb_text is None:
        pytest.skip("no verb text in the framing-exact golden set")
    d = _load_dict()
    if d is None:
        pytest.skip("FONIX dtalk_us.dic not available")
    good = [list(c.symbols) for c in sentence_to_clauses(verb_text, d)]
    assert good == exact[verb_text]
    monkeypatch.setattr(grammar_us, "word_markers", lambda w, dic: None)
    import pyretrotts.dectalk.sentence_us as su

    monkeypatch.setattr(su, "word_markers", lambda w, dic: None)
    mutated = [list(c.symbols) for c in sentence_to_clauses(verb_text, d)]
    assert mutated != exact[verb_text]


# ---- dictionary-gated: full framing matches the golden capture ----

def test_framing_matches_golden() -> None:
    """Every framing-exact golden text reframes bit-exactly to the oracle."""
    d = _load_dict()
    if d is None:
        pytest.skip("FONIX dtalk_us.dic not available")
    for text, exp in _golden()["exact"].items():
        mine = [list(c.symbols) for c in sentence_to_clauses(text, d)]
        assert mine == exp, f"framing mismatch for {text!r}"


# ---- oracle-gated: per-category framing / PCM match rate ----

def _oracle():
    try:
        from tools.dump_dectalk_phonemes import ORACLE_BIN, capture
    except Exception:
        return None
    if not ORACLE_BIN or not os.path.exists(ORACLE_BIN):
        return None
    return capture


def test_per_category_match_rate() -> None:
    """Re-measure the per-category framing/PCM rate; must not regress the golden."""
    capture = _oracle()
    d = _load_dict()
    if capture is None or d is None:
        pytest.skip("instrumented oracle / FONIX dictionary not available")
    from pyretrotts.dectalk.sentence_us import sentence_to_pcm

    golden = _golden()
    exact_set = set(golden["exact"])
    pcm_set = set(golden["pcm_exact"])
    f_hits = p_hits = 0
    for cat, texts in golden["battery"].items():
        fok = ftot = pok = ptot = 0
        for text in texts:
            u = capture(0, text)
            if u is None:
                continue
            ref = [list(c.symbols) for c in u.clauses]
            mine = [list(c.symbols) for c in sentence_to_clauses(text, d)]
            ftot += 1
            fok += ref == mine
            refpcm = struct.pack(f"<{len(u.pcm)}h", *u.pcm)
            ptot += 1
            pok += refpcm == sentence_to_pcm(0, text, d)
        f_hits += fok
        p_hits += pok
        print(f"{cat:10} framing {fok}/{ftot}   pcm {pok}/{ptot}")
    # The live measurement must reproduce at least the recorded golden subset.
    assert f_hits >= len(exact_set)
    assert p_hits >= len(pcm_set)


def test_pcm_exact_all_voices() -> None:
    """Each voice-0 PCM-exact text stays sample-exact across the ten voices."""
    capture = _oracle()
    d = _load_dict()
    if capture is None or d is None:
        pytest.skip("instrumented oracle / FONIX dictionary not available")
    from pyretrotts.dectalk.phclause import speak_phonemes

    texts = _golden()["pcm_exact"]
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
    assert exact == total, f"{exact}/{total} renders sample-exact"
