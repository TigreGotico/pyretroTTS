"""C vs Python comparison for the DECtalk UK-English duration stage (`uk_phtiming`).

Two gates:

* **CI-safe golden** (`dectalk_uk_timing_vectors.json`): real per-clause captures
  from `libtts_uk.so` -- the post-`phalloph` allophone/feature stream, the
  per-clause rate factors (`sprat0`/`sprat1`/`sprat2`/`timeref`/effective rate),
  `number_words`, and the `allodurs` the C wrote. `uk_phtiming` is replayed over
  each and every duration must match. Runs without the oracle. Mutation-biting.
* **oracle-gated** (`test_uk_timing_live`): drives the built `libtts_uk.so` through
  the multilanguage harness with a temporary UK timing dump (`DECTALK_UKTIM_DUMP`,
  a snippet added to `p_uk_tim.c` in the instrumented build copy, kept out of the
  read-only checkout) and diffs `uk_phtiming` against the C clause for clause.
  Skipped when the built UK oracle tree is absent.

`DECTALK_UKTIM_DUMP` is needed because the stock instrumentation carries a timing
dump only in `p_us_tim0.c` (US); the UK path `uk_phtiming` (`p_uk_tim.c`) has none.
It writes, per clause, an `H` line (rate factors + `number_words` + `nallotot` +
the entry `allophons`/`allofeats`) after `init_timing`, and a `D` line (the final
`allodurs`) after the loop, so the syllable time-alignment pass is captured.
"""
import glob
import json
import os
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from pyretrotts.dectalk.timing import TimingConfig  # noqa: E402
from pyretrotts.dectalk.timing_uk import _Rate, uk_phtiming  # noqa: E402

try:
    import dump_dectalk_uk as U  # noqa: E402
except ImportError:  # pragma: no cover
    U = None

_VECTORS = os.path.join(os.path.dirname(__file__), "dectalk_uk_timing_vectors.json")

# UK per-clause pause frames (`ph_claus.c:229-230`, `LANG_british`).
UK_NFCOMMA = 14
UK_NFPERIOD = 94

VOICES = 8
TEXTS = [
    "a test one two three", "hello there my name is paul",
    "the fish shifts sixty seven", "many men running homeward",
    "British weather is quite variable today", "the quick brown fox jumps over",
    "what is that", "stop", "one two three four five six seven",
]


def _run(rec):
    rate = _Rate(sprat0=rec["sprat0"], sprat1=rec["sprat1"], sprat2=rec["sprat2"],
                 timeref=rec["timeref"], sprate=rec["sprate"])
    cfg = TimingConfig(sprate=rec["sprate"] - 20, nfcomma=UK_NFCOMMA,
                       nfperiod=UK_NFPERIOD)
    return uk_phtiming(
        tuple(rec["allo"]), tuple(rec["feat"]), (0,) * rec["nallo"], rec["nallo"],
        cfg, number_words=rec["nw"], rate=rate)


def test_uk_timing_golden():
    """`uk_phtiming` reproduces every captured `allodurs`, CI-safe."""
    recs = json.load(open(_VECTORS))
    total = miss = 0
    fails = []
    for rec in recs:
        got = _run(rec)
        for i in range(rec["nallo"]):
            total += 1
            if got[i] != rec["durs"][i]:
                miss += 1
                if len(fails) < 10:
                    fails.append(f"v{rec['voice']} '{rec['text'][:10]}' n{i} "
                                 f"got {got[i]} exp {rec['durs'][i]}")
    assert miss == 0, f"{miss}/{total} UK durations diverge: {fails}"
    assert total >= 1000


def test_uk_timing_gate_bites():
    """A one-frame mutation of the pause floor must break the golden."""
    recs = json.load(open(_VECTORS))
    rec = next(r for r in recs if r["nallo"] > 3)
    good = _run(rec)
    # nfperiod 94 -> 75 shifts the trailing sentence pause.
    cfg = TimingConfig(sprate=rec["sprate"] - 20, nfcomma=UK_NFCOMMA, nfperiod=75)
    rate = _Rate(sprat0=rec["sprat0"], sprat1=rec["sprat1"], sprat2=rec["sprat2"],
                 timeref=rec["timeref"], sprate=rec["sprate"])
    bad = uk_phtiming(tuple(rec["allo"]), tuple(rec["feat"]), (0,) * rec["nallo"],
                      rec["nallo"], cfg, number_words=rec["nw"], rate=rate)
    assert bad != good


def _parse(path):
    clauses = []
    H = None
    for line in open(path):
        tok = line.split()
        if not tok:
            continue
        if tok[0] == "H":
            segs = line.split("|")
            head = [int(x) for x in segs[0].split()[1:]]
            H = dict(sprat0=head[0], sprat1=head[1], sprat2=head[2],
                     timeref=head[3], sprate=head[4], nw=head[5], nallo=head[6],
                     allo=[int(x) for x in segs[1].split()],
                     feat=[int(x) for x in segs[2].split()])
        elif tok[0] == "D":
            segs = line.split("|")
            H["durs"] = [int(x) for x in segs[1].split()]
            clauses.append(H)
            H = None
    return clauses


def test_uk_timing_live():
    """Diff `uk_phtiming` against the live `libtts_uk.so`, all voices/texts."""
    if U is None:
        pytest.skip("no dump_dectalk_uk harness")
    harness = U.build_harness()
    gen, lib, dic = U._paths("uk")
    if not (harness and gen and lib and dic):
        pytest.skip("no built UK oracle tree")
    tim_dump_present = False
    total = miss = clauses = clause_miss = 0
    fails = []
    with tempfile.TemporaryDirectory() as rundir:
        for src in glob.glob(os.path.join(dic, "*")):
            dst = os.path.join(rundir, os.path.basename(src))
            if not os.path.exists(dst):
                os.symlink(src, dst)
        for voice in range(VOICES):
            for text in TEXTS:
                tf = os.path.join(rundir, "ukt.txt")
                if os.path.exists(tf):
                    os.unlink(tf)
                env = dict(os.environ, DECTALK_DIR=rundir, DECTALK_UKTIM_DUMP=tf)
                env["LD_LIBRARY_PATH"] = os.pathsep.join(
                    [gen, lib, env.get("LD_LIBRARY_PATH", "")])
                subprocess.run(
                    [harness, "uk", str(voice),
                     os.path.join(rundir, "o.wav"), text],
                    cwd=rundir, env=env, capture_output=True, timeout=60)
                if not os.path.exists(tf):
                    continue
                tim_dump_present = True
                for cl in _parse(tf):
                    got = _run(dict(cl, voice=voice, text=text))
                    clauses += 1
                    bad = False
                    for i in range(cl["nallo"]):
                        total += 1
                        if got[i] != cl["durs"][i]:
                            miss += 1
                            bad = True
                            if len(fails) < 10:
                                fails.append(f"v{voice} '{text[:10]}' n{i} "
                                             f"got {got[i]} exp {cl['durs'][i]}")
                    clause_miss += bad
    if not tim_dump_present:
        pytest.skip("libtts_uk.so has no DECTALK_UKTIM_DUMP (rebuild p_uk_tim.c)")
    print(f"\nUK timing: {clauses - clause_miss}/{clauses} clauses, "
          f"{total - miss}/{total} durations exact")
    assert miss == 0, f"{miss}/{total} UK durations diverge: {fails}"
