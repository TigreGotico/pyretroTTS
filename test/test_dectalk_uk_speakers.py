"""UK per-voice `ph/` speaker scalars vs the oracle.

`phclause.PH_SPEAKERS_UK` holds the eight UK voices' `ph/`-layer speaker scalars.
The five `phdraw` scalars (`malfem`, `spdefb1off`, `f0_dep_tilt`, `spdeftltoff`,
`spdeflaxprcnt`) are measured here from the built `libtts_uk.so` (`DECTALK_PH_DUMP`
E-line for the four `phdraw` offsets, `DECTALK_PHS_DUMP` A-line for `malfem`) and
are byte-identical to the US voices 0..7. The CI-safe test pins the committed
values; the oracle-gated test re-measures and confirms.

The seven F0 scalars (`f0basefall`..`assertiveness`) are the same shared
speaker-def resolution but feed `phinton`/`pht0draw`, whose UK rule bodies are a
separate unported stage (`ph_inton0.c:154`, `ph_drwt01.c:277`, `#ifdef
ENGLISH_UK`); they are not re-measured here.
"""
import glob
import os
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from pyretrotts.dectalk.phclause import PH_SPEAKERS, PH_SPEAKERS_UK  # noqa: E402

try:
    import dump_dectalk_uk as U  # noqa: E402
except ImportError:  # pragma: no cover
    U = None

# Measured (malfem, spdefb1off, f0_dep_tilt, spdeftltoff, spdeflaxprcnt) per UK voice.
_PHDRAW = [
    (1, 4096, 75, 0, 0), (0, 4096, 75, 1, 3280), (1, 4096, 60, 3, 0),
    (1, 5346, 100, 11, 2050), (1, 4818, 100, 25, 2870), (0, 5200, 75, 1, 3075),
    (0, 4096, 100, 15, 2050), (0, 5154, 0, 6, 0),
]


def _phdraw(spk):
    return (spk.malfem, spk.spdefb1off, spk.f0_dep_tilt, spk.spdeftltoff,
            spk.spdeflaxprcnt)


def test_uk_speakers_shape_and_phdraw():
    assert len(PH_SPEAKERS_UK) == 8
    for v, spk in enumerate(PH_SPEAKERS_UK):
        assert _phdraw(spk) == _PHDRAW[v], f"voice {v}"
        # phdraw scalars are identical to US voices 0..7.
        assert _phdraw(spk) == _phdraw(PH_SPEAKERS[v])


def test_uk_speakers_live():
    if U is None:
        pytest.skip("no dump_dectalk_uk harness")
    harness = U.build_harness()
    gen, lib, dic = U._paths("uk")
    if not (harness and gen and lib and dic):
        pytest.skip("no built UK oracle tree")
    with tempfile.TemporaryDirectory() as rundir:
        for src in glob.glob(os.path.join(dic, "*")):
            dst = os.path.join(rundir, os.path.basename(src))
            if not os.path.exists(dst):
                os.symlink(src, dst)
        for voice in range(8):
            phf = os.path.join(rundir, "ph.txt")
            phs = os.path.join(rundir, "phs.txt")
            for f in (phf, phs):
                if os.path.exists(f):
                    os.unlink(f)
            env = dict(os.environ, DECTALK_DIR=rundir,
                       DECTALK_PH_DUMP=phf, DECTALK_PHS_DUMP=phs)
            env["LD_LIBRARY_PATH"] = os.pathsep.join(
                [gen, lib, env.get("LD_LIBRARY_PATH", "")])
            subprocess.run(
                [harness, "uk", str(voice), os.path.join(rundir, "o.wav"),
                 "hello there my name is paul"],
                cwd=rundir, env=env, capture_output=True, timeout=60)
            if not (os.path.exists(phf) and os.path.exists(phs)):
                pytest.skip("no UK PH/PHS dump")
            e = next(x.split() for x in open(phf) if x[0] == "E")
            b1, dt, tlt, lax = int(e[3]), int(e[6]), int(e[7]), int(e[9])
            malfem = next(int(x.split()[1]) for x in open(phs) if x[0] == "A")
            assert (malfem, b1, dt, tlt, lax) == _PHDRAW[voice], f"voice {voice}"
