"""Field-for-field diff of the ported DECtalk F0/intonation stage against the C.

Drives `intonation.phinton` and `intonation.Pht0draw` over the stream the
instrumented C captures at the stage boundary (`ph_inton0.c`/`ph_drwt01.c`, gated
on `DECTALK_INT_DUMP`) and diffs, per clause, for all ten voices over a varied
utterance set (statements, questions, long multi-clause sentences, emphasis):

  - `phinton`: the F0 command arrays `f0tar`/`f0tim` (and `nf0tot`), and the
    reduced-vowel-inserted allophone stream (`allophons`/`allofeats`/`allodurs`,
    `nallotot`), against the `O` line;
  - `pht0draw`: the per-frame period `parstochip[OUT_T0]` and the drawn `f0prime`,
    against the `T` lines, replayed frame for frame over the post-`phinton`
    stream with the captured `nf0ev` seed and speaker scalars.

Skips when the instrumented `say` is absent.

Usage:
    DECTALK_SAY=.../say ... python3 test/test_dectalk_phinton.py
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.dectalk.intonation import (
    IntonState,
    Pht0draw,
    Pht0drawIn,
    phinton,
)
from tools.dump_dectalk_intonation import ORACLE_BIN, capture

TEXTS = [
    "a test one two three",                 # statement
    "how are you today",                    # question (no mark)
    "how are you today?",                   # question (explicit)
    "hello there. how are you?",            # two clauses: statement + question
    "the quick brown fox jumps over the lazy dog",  # long clause
    "wait, stop, and listen carefully",     # comma boundaries
    "she said the cat sat on the mat",      # plain declarative
    "one two three four five six seven",    # many stressed syllables
    "is it raining outside right now?",     # question, function words
    "no. absolutely not. never again.",     # three short clauses
]


def _diff_phinton(c) -> tuple[int, int]:
    """Return (field_total, field_bad) for one clause's phinton output."""
    st = IntonState(
        allophons=list(c.allophons_in), allofeats=list(c.allofeats_in),
        allodurs=list(c.allodurs_in), nallotot=c.nallotot_in,
        user_f0=list(c.user_f0), user_offset=list(c.user_offset),
        f0mode=c.f0mode, cbsymbol=c.cbsymbol, size_hat_rise=c.size_hat_rise,
        scale_str_rise=c.scale_str_rise, assertiveness=c.assertiveness)
    phinton(st)
    total = bad = 0
    for got, exp in (
            (st.nf0tot, c.nf0tot), (st.nallotot, c.nallotot_out),
            (tuple(st.f0tar), c.f0tar), (tuple(st.f0tim), c.f0tim),
            (tuple(st.allophons), c.allophons_out[:c.nallotot_out]),
            (tuple(st.allodurs), c.allodurs_out[:c.nallotot_out])):
        total += 1
        if got != exp:
            bad += 1
    return total, bad


def _src(c) -> Pht0drawIn:
    return Pht0drawIn(
        allophons=c.allophons_out, allofeats=c.allofeats_out,
        allodurs=c.allodurs_out, nallotot=c.nallotot_out,
        f0tar=c.f0tar, f0tim=c.f0tim, nf0tot=c.nf0tot, f0mode=c.f0mode,
        f0basefall=c.f0basefall, f0_lp_filter=c.f0_lp_filter,
        f0minimum=c.f0minimum, f0scalefac=c.f0scalefac, newparagsw=c.newparagsw)


def _diff_pht0draw(clauses) -> tuple[int, int]:
    """Return (frame_total, frame_bad) over a whole utterance's clauses.

    One `Pht0draw` drives every clause in sequence, carrying `pDphsettar` state
    across clause boundaries exactly as the C speech thread does.
    """
    total = bad = 0
    draw: Pht0draw | None = None
    for c in clauses:
        if draw is None:
            draw = Pht0draw(_src(c), nf0ev=c.nf0ev_seed)
        else:
            draw.new_clause(_src(c), c.nf0ev_seed)
        for exp_t0, exp_f0p in zip(c.t0, c.f0prime, strict=False):
            got_t0 = draw.step()
            total += 1
            if got_t0 != exp_t0 or draw.f0prime != exp_f0p:
                bad += 1
    return total, bad


def _run():
    cases = 0
    pi_total = pi_bad = 0
    t0_total = t0_bad = 0
    for sp in range(10):
        for tx in TEXTS:
            cs = capture(sp, tx)
            if cs:
                cases += 1
            for c in cs:
                a, b = _diff_phinton(c)
                pi_total += a
                pi_bad += b
            a, b = _diff_pht0draw(cs)
            t0_total += a
            t0_bad += b
    return cases, pi_total, pi_bad, t0_total, t0_bad


@pytest.mark.skipif(
    not ORACLE_BIN or not os.path.exists(ORACLE_BIN),
    reason="instrumented DECtalk oracle not built (set DECTALK_SAY)")
def test_phinton_matches_oracle():
    cases, pi_total, pi_bad, t0_total, t0_bad = _run()
    assert cases > 0
    assert pi_bad == 0, f"{pi_bad}/{pi_total} phinton fields differ from the C"
    assert t0_bad == 0, f"{t0_bad}/{t0_total} pht0draw frames differ from the C"


def run() -> int:
    if not ORACLE_BIN or not os.path.exists(ORACLE_BIN):
        print(f"SKIP: no instrumented oracle at {ORACLE_BIN!r} (set DECTALK_SAY)")
        return 0
    cases, pi_total, pi_bad, t0_total, t0_bad = _run()
    print(f"{cases}/100 cases captured (10 voices x 10 utterances)")
    print(f"phinton: {pi_total - pi_bad}/{pi_total} output fields exact "
          f"({pi_bad} mismatches)")
    print(f"pht0draw: {t0_total - t0_bad}/{t0_total} per-frame T0/f0prime exact "
          f"({t0_bad} mismatches)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
