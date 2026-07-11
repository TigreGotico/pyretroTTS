"""C vs Python comparison for the DECtalk UK-English `phsettar` transition setup.

Drives the real `libtts_uk.so` through the multilanguage harness (`tools/uksay.c`
via `tools/dump_dectalk_uk.py`), capturing per clause the allophone/feature/
duration stream `phsettar` reads and, per phone, the full sixteen-parameter
`PARAMETER` transition state (`DECTALK_PHS_DUMP`, gated in `ph_setar.c`). The
ported `phsettar_uk.phsettar_uk` is replayed over the identical stream, carrying
its `PARAMETER` state across phones exactly as the C does, and every audio-
relevant field is diffed against the C, phone for phone, for each UK voice.

Skipped when the built UK oracle tree is absent, so it does not run in CI.

The audio-relevant fields (`tarcur`/`durlin`/`deldip`/`dipcum`/`ftran`/`dftran`/
`btran`/`dbtran`/`tbacktr`/`tspesh`/`pspesh`) are the interpolation state
`draw_frame` consumes and must match the C exactly. The `ndip[0]`/`ndip[1]`
pointer peeks are excluded (as in the US `phsettar` test) because on a later
non-diphthong phone the C's pointer has been advanced further by `advance_frame`
during the intervening frames, which this phone-by-phone replay does not run.

Every INTERIOR (non-`GEN_SIL`) phone is required to be field-exact. The boundary
`GEN_SIL` silence is reported separately and not asserted: its TILT target and
transition depend on `parstochip[OUT_TLT]` (the previous drawn frame), which the
phone-by-phone replay cannot reproduce at a clause boundary -- it is validated
instead by the end-to-end frame loop (the UK phoneme->PCM gate).
"""
import os
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from pyretrotts.dectalk.phsettar import PhsettarState  # noqa: E402
from pyretrotts.dectalk.phsettar_uk import phsettar_uk  # noqa: E402
from pyretrotts.dectalk.settar import GEN_SIL  # noqa: E402

try:
    import dump_dectalk_uk as U  # noqa: E402
except ImportError:  # pragma: no cover
    U = None

FIELDS = ("tarcur", "durlin", "deldip", "dipcum", "ftran", "dftran", "btran",
          "dbtran", "tbacktr", "tspesh", "pspesh")

VOICES = 8
TEXTS = [
    "a test one two three",
    "hello there my name is paul",
    "the fish shifts sixty seven",
    "many men running homeward",
    "British weather is quite variable today",
    "the quick brown fox jumps over",
]


def _parse(dump_path):
    clause = None
    out = []
    for line in open(dump_path):
        tok = line.split()
        if not tok:
            continue
        if tok[0] == "A":
            malfem, nallotot = int(tok[1]), int(tok[2])
            rest = tok[3:]
            i = rest.index("|")
            allophons = tuple(int(x) for x in rest[:i])
            rest = rest[i + 1:]
            j = rest.index("|")
            allofeats = tuple(int(x) for x in rest[:j])
            allodurs = tuple(int(x) for x in rest[j + 1:])
            clause = dict(malfem=malfem, nallotot=nallotot, allophons=allophons,
                          allofeats=allofeats, allodurs=allodurs, phones=[])
            out.append(clause)
        elif tok[0] == "P":
            v = [int(x) for x in tok[1:]]
            params = [v[11 + k * 13:11 + (k + 1) * 13] for k in range(16)]
            clause["phones"].append(
                dict(nphone=v[0], durfon=v[1], prev_tilt=v[3], params=params))
    return out


def _got(st, pi):
    q = st.param[pi]
    return [q.tarcur, q.durlin, q.deldip, q.dipcum, q.ftran, q.dftran, q.btran,
            q.dbtran, q.tbacktr, q.tspesh, q.pspesh]


def _capture_all():
    """Yield (voice, text, clauses) for the whole UK battery, or None if no oracle."""
    if U is None:
        return None
    harness = U.build_harness()
    gen, lib, dic = U._paths("uk")
    if not (harness and gen and lib and dic):
        return None
    import glob
    records = []
    with tempfile.TemporaryDirectory() as rundir:
        for src in glob.glob(os.path.join(dic, "*")):
            dst = os.path.join(rundir, os.path.basename(src))
            if not os.path.exists(dst):
                os.symlink(src, dst)
        for voice in range(VOICES):
            for text in TEXTS:
                phs = os.path.join(rundir, "phs.txt")
                if os.path.exists(phs):
                    os.unlink(phs)
                env = dict(os.environ, DECTALK_DIR=rundir, DECTALK_PHS_DUMP=phs)
                env["LD_LIBRARY_PATH"] = os.pathsep.join(
                    [gen, lib, env.get("LD_LIBRARY_PATH", "")])
                subprocess.run(
                    [harness, "uk", str(voice), os.path.join(rundir, "o.wav"), text],
                    cwd=rundir, env=env, capture_output=True, timeout=60)
                if os.path.exists(phs):
                    records.append((voice, text, _parse(phs)))
    return records


def test_uk_phsettar_interior_bit_exact():
    records = _capture_all()
    if not records:
        pytest.skip("no built UK oracle tree (see tools/dump_dectalk_uk.py)")
    interior = interior_miss = silence = silence_miss = 0
    failures = []
    for voice, text, clauses in records:
        for cl in clauses:
            st = PhsettarState(
                allophons=cl["allophons"], allofeats=cl["allofeats"],
                allodurs=cl["allodurs"], nallotot=cl["nallotot"],
                malfem=cl["malfem"])
            for ph in cl["phones"]:
                st.nphone = ph["nphone"]
                st.durfon = ph["durfon"]
                st.prev_tilt = ph["prev_tilt"]
                phsettar_uk(st)
                is_sil = cl["allophons"][ph["nphone"]] == GEN_SIL
                for pi in range(16):
                    got = _got(st, pi)
                    exp = ph["params"][pi]
                    for fi in range(11):
                        if is_sil:
                            silence += 1
                        else:
                            interior += 1
                        if got[fi] != exp[fi]:
                            if is_sil:
                                silence_miss += 1
                            else:
                                interior_miss += 1
                                if len(failures) < 10:
                                    failures.append(
                                        f"v{voice} '{text[:12]}' n{ph['nphone']} "
                                        f"par{pi} {FIELDS[fi]} "
                                        f"got {got[fi]} exp {exp[fi]}")
    print(f"\nINTERIOR audio fields: {interior - interior_miss}/{interior} exact")
    print(f"SILENCE  audio fields: {silence - silence_miss}/{silence} exact "
          f"(boundary TILT, validated end-to-end)")
    assert interior_miss == 0, (
        f"{interior_miss}/{interior} interior audio fields diverge: {failures}")
