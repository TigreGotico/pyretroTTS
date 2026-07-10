"""Field-for-field diff of the ported DECtalk allophone-selection stage vs the C.

Drives `allophones.phsort` and `allophones.phalloph` over the symbol / phoneme
streams the instrumented C captures at the stage boundary (`ph_claus.c`, gated on
`DECTALK_SORT_DUMP`; `p_us_tim0.c`, gated on `DECTALK_TIM_DUMP`) and diffs:

- `phsort`: the `phonemes`/`sentstruc`/`nphonetot` it produces from `symbols`;
- `phalloph`: the `allophons`/`allofeats`/`nallotot` it produces from
  `phonemes`/`sentstruc`,

against the C, for all ten voices over a varied utterance set. Skips when the
instrumented `say` is absent.

Usage:
    DECTALK_SAY=.../say ... python3 test/test_dectalk_phalloph.py
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.dectalk.allophones import phalloph, phsort
from tools.dump_dectalk_phalloph import ORACLE_BIN, capture

TEXTS = [
    "a test one two three",
    "hello there my name is paul",
    "the fish shifts sixty seven",
    "many men running homeward",
    "the quick brown fox jumps",
    "ready to go, he wants to eat",
    "strength of the people",
    "little butter kitty water",
    "for the win, out of the box",
    "is it ready? stop that now!",
]


def _run() -> tuple[int, ...]:
    cases = 0
    p_ok = p_tot = s_ok = s_tot = nph_bad = 0
    a_ok = a_tot = f_ok = f_tot = nal_bad = 0
    for sp in range(10):
        for tx in TEXTS:
            cs = capture(sp, tx)
            if cs:
                cases += 1
            for c in cs:
                pho, sst, nph = phsort(c.symbols, c.user_durs)
                nph_bad += nph != len(c.phonemes)
                for g, e in zip(pho, c.phonemes, strict=False):
                    p_tot += 1
                    p_ok += g == e
                for g, e in zip(sst, c.sentstruc, strict=False):
                    s_tot += 1
                    s_ok += g == e
                alo, aft, nal = phalloph(c.phonemes, c.sentstruc, len(c.phonemes))
                nal_bad += nal != c.nallotot
                for g, e in zip(alo, c.allophons, strict=False):
                    a_tot += 1
                    a_ok += g == e
                for g, e in zip(aft, c.allofeats, strict=False):
                    f_tot += 1
                    f_ok += g == e
    return (cases, p_ok, p_tot, s_ok, s_tot, nph_bad,
            a_ok, a_tot, f_ok, f_tot, nal_bad)


@pytest.mark.skipif(
    not ORACLE_BIN or not os.path.exists(ORACLE_BIN),
    reason="instrumented DECtalk oracle not built (set DECTALK_SAY)")
def test_phsort_phalloph_match_oracle():
    (cases, p_ok, p_tot, s_ok, s_tot, nph_bad,
     a_ok, a_tot, f_ok, f_tot, nal_bad) = _run()
    assert cases > 0
    assert nph_bad == 0, f"phsort nphonetot diverged on {nph_bad} clauses"
    assert p_ok == p_tot, f"phsort phonemes: {p_tot - p_ok}/{p_tot} differ"
    assert s_ok == s_tot, f"phsort sentstruc: {s_tot - s_ok}/{s_tot} differ"
    assert nal_bad == 0, f"phalloph nallotot diverged on {nal_bad} clauses"
    assert a_ok == a_tot, f"phalloph allophons: {a_tot - a_ok}/{a_tot} differ"
    assert f_ok == f_tot, f"phalloph allofeats: {f_tot - f_ok}/{f_tot} differ"


def run() -> int:
    if not ORACLE_BIN or not os.path.exists(ORACLE_BIN):
        print(f"SKIP: no instrumented oracle at {ORACLE_BIN!r} (set DECTALK_SAY)")
        return 0
    (cases, p_ok, p_tot, s_ok, s_tot, nph_bad,
     a_ok, a_tot, f_ok, f_tot, nal_bad) = _run()
    print(f"{cases}/100 cases captured (10 voices)")
    print(f"phsort:   phonemes {p_ok}/{p_tot}, sentstruc {s_ok}/{s_tot}, "
          f"nphonetot bad {nph_bad}")
    print(f"phalloph: allophons {a_ok}/{a_tot}, allofeats {f_ok}/{f_tot}, "
          f"nallotot bad {nal_bad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
