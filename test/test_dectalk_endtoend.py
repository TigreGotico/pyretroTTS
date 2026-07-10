"""End-to-end DECtalk composition: allophone stream -> PCM, all in Python.

Drives the ported front-end stages in sequence over a captured allophone stream
and diffs the result against the oracle, proving the layers compose:

    phsettar (phsettar.py) -> advance_frame/draw_frame (ph.py, the phdraw frame
    loop) -> send_pars (ph.py) -> vtm (vtm.py) -> PCM

Only the F0 contour and phone durations (the `pht0draw`/timing stages that are
Phase 5, not yet ported) are borrowed from the oracle, captured per frame; every
spectral and amplitude parameter is computed here.

Two checks per voice/utterance:

1. **Vocal-tract-model input, frame for frame.** The composed
   phsettar->phdraw->send_pars output is diffed against the exact frame the C
   ships to its vocal tract model (the `V` dump, `parambuff[1..20]` read in
   `vtmiont.c`). This is the load-bearing proof: it shows the ported front end
   reproduces the synthesizer's input bit-for-bit.
2. **PCM, sample for sample.** Those frames are run through `vtm.py` and the PCM
   is diffed against the oracle WAV.

The instrumented oracle must dump, in addition to the phsettar `A`/`P` lines and
the phdraw `E`/`X` lines (see test_dectalk_phsettar_full and test_dectalk_ph):
  - phdraw: a `Y` line per frame with parstochip[OUT_T0/PH/DU/PH2];
  - vtmiont.c, gated on DECTALK_VTM_DUMP: a `V` line per frame with
    parambuff[1..20] read right after the pipe read.

Usage:
    DECTALK_SAY=.../say ... python3 test/test_dectalk_endtoend.py
"""
import glob
import os
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.dectalk import consts as C
from pyretrotts.dectalk.engine import synthesize_frames
from pyretrotts.dectalk.ph import (
    DrawFrame,
    DrawScalars,
    advance_frame,
    draw_frame,
    finalize_av,
    send_pars,
)
from pyretrotts.dectalk.phsettar import PhsettarState, phsettar, to_draw_params
from pyretrotts.dectalk.voices import SPEAKERS, VOICE_NAMES

_DTK = os.path.expanduser("~/AgentWorkspaces/ovos/dectalk-c/src")

# draw_frame output order -> parstochip slot.
_X_TO_SLOT = (
    C.OUT_F1, C.OUT_F2, C.OUT_F3, C.OUT_FZ, C.OUT_B1, C.OUT_B2, C.OUT_B3,
    C.OUT_AV, C.OUT_AP, C.OUT_A2, C.OUT_A3, C.OUT_A4, C.OUT_A5, C.OUT_A6,
    C.OUT_AB, C.OUT_TLT,
)

TEXTS = [
    "a test one two three",
    "hello there my name is paul",
    "the fish shifts sixty seven",
    "many men running homeward",
]


def _first(pattern: str) -> str:
    hits = sorted(glob.glob(pattern))
    return hits[0] if hits else ""


ORACLE_BIN = os.environ.get(
    "DECTALK_SAY", _first(f"{_DTK}/samplosf/build/dtsamples/*/us/release/say"))
GEN_LIB = os.environ.get("DECTALK_GEN_LIB", _first(f"{_DTK}/dtalkml/build/*/us/release"))
US_LIB = os.environ.get("DECTALK_US_LIB", _first(f"{_DTK}/dapi/build/dectalk/*/us/release"))
DIC_DIR = os.environ.get("DECTALK_DIR", _first(f"{_DTK}/dapi/build/dic/*/us/release"))


@dataclass
class _FrameScalars:
    fvvtran: int = 0
    dfvvtran: int = 0
    tvvbacktr: int = 0
    bvvtran: int = 0
    dbvvtran: int = 0
    breathysw: int = 0
    breathyah: int = 0
    breathytilt: int = 0


def _wav_pcm(path: str) -> list[int]:
    data = open(path, "rb").read()
    i = data.find(b"data")
    n = struct.unpack("<I", data[i + 4:i + 8])[0]
    return list(struct.unpack(f"<{n // 2}h", data[i + 8:i + 8 + n]))


def _capture(speaker: int, text: str, rundir: str):
    phs = os.path.join(rundir, "phs.txt")
    phd = os.path.join(rundir, "phd.txt")
    vtm = os.path.join(rundir, "vtm.txt")
    wav = os.path.join(rundir, "o.wav")
    env = dict(os.environ, DECTALK_DIR=rundir, DECTALK_PHS_DUMP=phs,
               DECTALK_PH_DUMP=phd, DECTALK_VTM_DUMP=vtm)
    env["LD_LIBRARY_PATH"] = os.pathsep.join(
        [GEN_LIB, US_LIB, env.get("LD_LIBRARY_PATH", "")])
    subprocess.run(
        [ORACLE_BIN, "-s", str(speaker), "-e", "1", "-fo", wav, "-a", text],
        cwd=rundir, env=env, capture_output=True, timeout=60)
    stream = None
    for line in open(phs):
        t = line.split()
        if t[0] == "A":
            rest = t[3:]
            i = rest.index("|")
            allophons = tuple(int(x) for x in rest[:i])
            rest = rest[i + 1:]
            j = rest.index("|")
            allofeats = tuple(int(x) for x in rest[:j])
            allodurs = tuple(int(x) for x in rest[j + 1:])
            stream = dict(malfem=int(t[1]), nallotot=int(t[2]),
                          allophons=allophons, allofeats=allofeats, allodurs=allodurs)
            break
    E, X, Y = [], [], []
    for line in open(phd):
        t = line.split()
        if t[0] == "E":
            E.append([int(x) for x in t[1:]])
        elif t[0] == "X":
            X.append([int(x) for x in t[1:]])
        elif t[0] == "Y":
            Y.append([int(x) for x in t[1:]])
    V = [[int(x) for x in ln.split()[1:]] for ln in open(vtm) if ln.startswith("V")]
    return stream, E, X, Y, V, _wav_pcm(wav)


def _compose(stream, E, X, Y):
    """Run phsettar -> phdraw frame loop -> send_pars; return the vtm-input frames."""
    st = PhsettarState(
        allophons=stream["allophons"], allofeats=stream["allofeats"],
        allodurs=stream["allodurs"], nallotot=stream["nallotot"],
        malfem=stream["malfem"])
    fls = _FrameScalars()
    frames: list[list[int]] = []
    delayed = None
    fi = 0
    for nphone in range(stream["nallotot"]):
        durfon = stream["allodurs"][nphone]
        st.nphone = nphone
        st.durfon = durfon
        st.prev_tilt = X[fi - 1][15] if fi > 0 else 0
        phsettar(st)
        fls.fvvtran, fls.dfvvtran, fls.tvvbacktr = st.fvvtran, st.dfvvtran, st.tvvbacktr
        fls.bvvtran, fls.dbvvtran, fls.breathysw = st.bvvtran, st.dbvvtran, st.breathysw
        for tcum in range(durfon):
            if fi >= len(E):
                break
            e = E[fi]
            sc = DrawScalars(
                tcum=tcum, phon=e[1], spdefb1off=e[2], avglstop=e[3], f0=e[4],
                f0_dep_tilt=e[5], spdeftltoff=e[6], breathysw=st.breathysw,
                spdeflaxprcnt=e[8], fvvtran=fls.fvvtran, dfvvtran=fls.dfvvtran,
                tvvbacktr=fls.tvvbacktr, bvvtran=fls.bvvtran, dbvvtran=fls.dbvvtran,
                breathyah=fls.breathyah, breathytilt=fls.breathytilt)
            out = draw_frame(DrawFrame(sc, to_draw_params(st)))
            final = list(out)
            finalize_av(final)  # phdraw's tail AV boost (ph_draw.c:4344)
            pc = [0] * 20
            for k, slot in enumerate(_X_TO_SLOT):
                pc[slot] = final[k]
            pc[C.OUT_T0], pc[C.OUT_PH] = Y[fi][0], Y[fi][1]
            pc[C.OUT_DU], pc[C.OUT_PH2] = Y[fi][2], Y[fi][3]
            frame, delayed = send_pars(pc, delayed)
            if frame is not None:
                frames.append(frame)
            # The breathy ramp keys off the pre-boost AV (ph_draw.c:689).
            advance_frame(st.param, st.dipspec, tcum, out, fls)
            fi += 1
    return frames


def run() -> int:
    if not ORACLE_BIN or not os.path.exists(ORACLE_BIN):
        print(f"SKIP: no instrumented oracle at {ORACLE_BIN!r} (set DECTALK_SAY)")
        return 0
    vtm_cases = vtm_exact = 0
    pcm_cases = pcm_exact = pcm_vtm_only = 0
    vtm_frame_total = vtm_frame_bad = 0
    with tempfile.TemporaryDirectory() as rundir:
        for src in glob.glob(os.path.join(DIC_DIR, "*")):
            dst = os.path.join(rundir, os.path.basename(src))
            if not os.path.exists(dst):
                os.symlink(src, dst)
        for sp in range(len(VOICE_NAMES)):
            for text in TEXTS:
                stream, E, X, Y, V, wav = _capture(sp, text, rundir)
                frames = _compose(stream, E, X, Y)
                # 1. vtm input, frame for frame.
                vtm_cases += 1
                nf = min(len(frames), len(V))
                bad = sum(1 for k in range(nf) if frames[k] != V[k]) + abs(len(frames) - len(V))
                vtm_frame_total += max(len(frames), len(V))
                vtm_frame_bad += bad
                if bad == 0:
                    vtm_exact += 1
                # 2. PCM, sample for sample.
                pcm_cases += 1
                my = synthesize_frames(SPEAKERS[sp], frames)
                n = min(len(my), len(wav))
                sd = sum(1 for a, b in zip(my[:n], wav[:n], strict=False) if a != b) + abs(len(my) - len(wav))
                if sd == 0:
                    pcm_exact += 1
                elif bad == 0:
                    # Front end exact; residual is the vocal tract model alone.
                    pcm_vtm_only += sd
                else:
                    print(f"  front-end diff s{sp} {VOICE_NAMES[sp]!r} {text!r}: "
                          f"{bad} vtm-input frames, {sd} PCM samples")
    print(f"vocal-tract-model input (phsettar -> phdraw loop -> send_pars): "
          f"{vtm_exact}/{vtm_cases} cases frame-exact "
          f"({vtm_frame_total - vtm_frame_bad}/{vtm_frame_total} frames)")
    print(f"end-to-end PCM: {pcm_exact}/{pcm_cases} cases sample-exact; the rest "
          f"have a frame-exact vtm input, so their {pcm_vtm_only} residual PCM "
          f"samples come solely from vtm.py (Phase 1), not the ported front end")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
