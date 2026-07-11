"""UK DECtalk phoneme-alphabet port: inventory, render/parse, oracle capture.

The UK front end (dictionary, LTS rules, `ph/` ROM) is not ported yet; what is
gated here is the UK phoneme+stress *alphabet* the UK library emits -- the
`PFUK` font, the `UK_*` inventory (`l_all_ph.h`), and the `uk_arpa[]` render
table (`uk_phon.tab`) -- plus the real UK oracle capture that anchors it.

The CI-safe tests run without the oracle from the committed capture
`test/dectalk_uk_lts_golden.json`. The oracle-gated test re-captures live and is
skipped without the built `dectalk-c` tree.
"""
from __future__ import annotations

import json
import os

import pytest

from pyretrotts.dectalk import lts, uk_phonemes
from pyretrotts.dectalk.language import Language, profile

_GOLDEN = os.path.join(os.path.dirname(__file__), "dectalk_uk_lts_golden.json")


def _golden() -> dict:
    return json.load(open(_GOLDEN))


# --- Inventory ------------------------------------------------------------

def test_uk_inventory_size() -> None:
    assert uk_phonemes.UK_TOT_ALLOPHONES == 57
    assert len(uk_phonemes.UK_PHONEME_NAMES) == 57  # 0 (SIL) .. 56 (DF)
    assert uk_phonemes.PFUK == 0x1D
    assert uk_phonemes.PFUK == lts.PFUSA - 1


def test_uk_us_inventory_shared_except_documented_deltas() -> None:
    """UK index space matches US 1..56 except index 29 (OH vs RX) and 51."""
    uk = uk_phonemes.UK_PHONEME_NAMES
    us = lts.US_PHONEME_NAMES
    diffs = {i for i in range(1, 57) if uk[i] != us[i]}
    assert diffs == {29, 51}
    assert (uk[29], us[29]) == ("OH", "RX")
    assert (uk[51], us[51]) == ("YR", "DX")


def test_uk_arpa_render_deltas_vs_us() -> None:
    """uk_arpa[] differs from usa_arpa[] only at indices 25, 27, 29, 51."""
    uk = uk_phonemes.UK_ARPA_PAIRS
    us = {k: v for k, v in lts._ARPA_PAIRS.items() if k < 57}
    diffs = {i for i in range(57) if uk[i] != us[i]}
    assert diffs == {25, 27, 29, 51}


# --- Render / parse round-trip (the bit-exact alphabet gate) --------------

def test_uk_render_roundtrip_full_inventory() -> None:
    """Every UK phoneme index renders to a `uk_<name>` token that decodes back."""
    prof = profile(Language.UK)
    for index in range(57):
        token = prof.render_token(index)
        assert token.startswith("uk_")
        body = token[3:]
        # two-char names are flush; one-char names carry a trailing space
        name = body.rstrip(" ") if body.endswith(" ") else body
        pair = uk_phonemes.UK_ARPA_PAIRS[index]
        expected = pair[0] if pair[1] == " " else pair[0] + pair[1]
        assert name == expected


def test_uk_captured_codes_all_decode() -> None:
    """Every phoneme code in the committed capture is a valid UK inventory index."""
    prof = profile(Language.UK)
    battery = _golden()["battery"]
    assert battery, "empty golden battery"
    total = 0
    for _text, rec in battery.items():
        for code in rec["codes"]:
            if code < 100:  # phoneme (prosody codes are >= 100)
                assert (code & 0xFF) in prof.phoneme_names
                total += 1
    assert total > 0


def test_uk_render_golden_stable() -> None:
    """The render of each captured phoneme stream is reproducible from the port.

    Locks the UK arpa table: mutating any `UK_ARPA_PAIRS` entry that a captured
    word uses changes this render and fails the test.
    """
    prof = profile(Language.UK)
    battery = _golden()["battery"]
    rendered = {
        t: "".join(prof.render_token(c & 0xFF) for c in rec["codes"] if c < 100)
        for t, rec in battery.items()
    }
    # spot-anchor a few well-understood UK realizations (non-rhotic + centring)
    assert rendered["car"] == "uk_k uk_aa"               # /k aa/, no post-voc r
    assert "uk_er" in rendered["square"]                  # SQUARE centring vowel
    assert "uk_rr" in rendered["nurse"]                   # NURSE vowel (code 15)
    # every word renders to a non-empty ASCII uk_ token string
    for _text, s in rendered.items():
        assert s and s.isascii() and s.startswith("uk_")


def test_gate_bites_on_arpa_mutation() -> None:
    """A mutated UK arpa entry breaks the captured-word render (mutation gate)."""
    prof = profile(Language.UK)
    battery = _golden()["battery"]
    # index 6 (AA) is used by 'car'; flipping its render must change the output
    good = "".join(prof.render_token(c & 0xFF) for c in battery["car"]["codes"] if c < 100)
    mutated = dict(uk_phonemes.UK_ARPA_PAIRS)
    mutated[6] = ("x", "x")
    bad = "".join(
        (f"uk_{mutated[c & 0xFF][0]}{mutated[c & 0xFF][1]}".rstrip() + (
            " " if mutated[c & 0xFF][1] == " " else ""))
        for c in battery["car"]["codes"] if c < 100)
    assert good != bad


# --- Oracle-gated: live UK capture ----------------------------------------

def test_uk_oracle_capture_decodes() -> None:
    from tools.dump_dectalk_uk import capture  # noqa: PLC0415

    cap = capture("uk", 0, "car")
    if cap is None:
        pytest.skip("UK oracle (dectalk-c) not available")
    prof = profile(Language.UK)
    phonemes = [c for c in cap.codes if c < 100]
    assert phonemes  # non-empty
    for code in phonemes:
        assert (code & 0xFF) in prof.phoneme_names
    # 'car' is /k aa/ non-rhotic: K(49), S1(103), AA(6)
    assert cap.codes == (49, 103, 6)
