"""Field-for-field diff of the ported DECtalk duration stage against the C oracle.

Drives `timing.us_phtiming` over the allophone/feature stream the instrumented C
captures at the stage boundary (`p_us_tim0.c`, gated on `DECTALK_TIM_DUMP`) and
diffs the resulting `allodurs` -- and the (possibly `[n]->[d]` mutated) allophone
stream -- against the C, for all ten voices over four utterances. Skips when the
instrumented `say` is absent.

`init_timing` is checked separately: it must reproduce the speaking-rate factors
(`sprat0`/`sprat1`/`sprat2`/`timeref`) the C resolved for every clause.

Usage:
    DECTALK_SAY=.../say ... python3 test/test_dectalk_aloph.py
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.dectalk.timing import TimingConfig, init_timing, us_phtiming
from tools.dump_dectalk_aloph import ORACLE_BIN, capture

TEXTS = [
    "a test one two three",
    "hello there my name is paul",
    "the fish shifts sixty seven",
    "many men running homeward",
]


def _run() -> tuple[int, int, int, int, int]:
    cases = clauses = durs = mism = rate_bad = 0
    for sp in range(10):
        for tx in TEXTS:
            cs = capture(sp, tx)
            if cs:
                cases += 1
            for c in cs:
                clauses += 1
                r = init_timing(c.sprate)
                if (r.sprat0, r.sprat1, r.sprat2, r.timeref) != (
                        c.sprat0, c.sprat1, c.sprat2, c.timeref):
                    rate_bad += 1
                out = us_phtiming(
                    c.allophons_in, c.allofeats, c.user_durs, c.nallotot,
                    TimingConfig(sprate=c.sprate))
                for g, e in zip(out, c.allodurs, strict=False):
                    durs += 1
                    if g != e:
                        mism += 1
    return cases, clauses, durs, mism, rate_bad


@pytest.mark.skipif(
    not ORACLE_BIN or not os.path.exists(ORACLE_BIN),
    reason="instrumented DECtalk oracle not built (set DECTALK_SAY)")
def test_us_phtiming_matches_oracle():
    cases, clauses, durs, mism, rate_bad = _run()
    assert cases > 0
    assert rate_bad == 0, f"init_timing diverged on {rate_bad}/{clauses} clauses"
    assert mism == 0, f"{mism}/{durs} durations differ from the C oracle"


def run() -> int:
    if not ORACLE_BIN or not os.path.exists(ORACLE_BIN):
        print(f"SKIP: no instrumented oracle at {ORACLE_BIN!r} (set DECTALK_SAY)")
        return 0
    cases, clauses, durs, mism, rate_bad = _run()
    print(f"{cases}/40 cases captured; init_timing exact on "
          f"{clauses - rate_bad}/{clauses} clauses")
    print(f"durations: {durs - mism}/{durs} frame-exact vs the C oracle "
          f"({mism} mismatches, {clauses} clauses, 10 voices)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
