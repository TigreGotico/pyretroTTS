"""Oracle-anchored golden gate over the whole DECtalk allophone -> PCM chain.

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`). FONIX
Corporation declares that source proprietary and confidential. This file is NOT
covered by this project's MIT licence. See NOTICE.

Captures, per voice, a real allophone stream plus the F0 contour and phone
durations (the Phase-5 `pht0draw`/timing inputs, not yet ported) and the samples
the oracle produced, then gates the composed front end + vocal tract model
(`phsettar -> advance_frame/draw_frame -> finalize_av -> send_pars -> vtm`)
against that PCM. Everything except the borrowed F0/durations is computed here.
The captured stream is DECtalk-derived data, hence the FONIX notice; the gate
runs in CI without the oracle binary.

Regenerate with an instrumented oracle build (see test_dectalk_endtoend.py):

    DECTALK_SAY=.../say ... python3 test/dectalk_endtoend_golden.py --write
"""
import glob
import hashlib
import json
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

GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "dectalk_endtoend_golden.json")
TEXT = "a test"

_X_TO_SLOT = (
    C.OUT_F1, C.OUT_F2, C.OUT_F3, C.OUT_FZ, C.OUT_B1, C.OUT_B2, C.OUT_B3,
    C.OUT_AV, C.OUT_AP, C.OUT_A2, C.OUT_A3, C.OUT_A4, C.OUT_A5, C.OUT_A6,
    C.OUT_AB, C.OUT_TLT,
)
_DTK = os.path.expanduser("~/AgentWorkspaces/ovos/dectalk-c/src")


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


def compose_pcm(speaker_index: int, case: dict) -> list[int]:
    """Run the full chain from a captured stream + borrowed F0/durations to PCM."""
    st = PhsettarState(
        allophons=tuple(case["allophons"]), allofeats=tuple(case["allofeats"]),
        allodurs=tuple(case["allodurs"]), nallotot=case["nallotot"],
        malfem=case["malfem"])
    prosody = case["prosody"]  # per drawn frame, in order
    fls = _FrameScalars()
    frames: list[list[int]] = []
    delayed = None
    prev_tilt = 0
    fi = 0
    for nphone in range(case["nallotot"]):
        durfon = case["allodurs"][nphone]
        st.nphone = nphone
        st.durfon = durfon
        st.prev_tilt = prev_tilt
        phsettar(st)
        fls.fvvtran, fls.dfvvtran, fls.tvvbacktr = st.fvvtran, st.dfvvtran, st.tvvbacktr
        fls.bvvtran, fls.dbvvtran, fls.breathysw = st.bvvtran, st.dbvvtran, st.breathysw
        for tcum in range(durfon):
            if fi >= len(prosody):
                break
            p = prosody[fi]
            sc = DrawScalars(
                tcum=tcum, phon=p["phon"], spdefb1off=p["spdefb1off"],
                avglstop=p["avglstop"], f0=p["f0"], f0_dep_tilt=p["f0_dep_tilt"],
                spdeftltoff=p["spdeftltoff"], breathysw=st.breathysw,
                spdeflaxprcnt=p["spdeflaxprcnt"], fvvtran=fls.fvvtran,
                dfvvtran=fls.dfvvtran, tvvbacktr=fls.tvvbacktr, bvvtran=fls.bvvtran,
                dbvvtran=fls.dbvvtran, breathyah=fls.breathyah,
                breathytilt=fls.breathytilt)
            out = draw_frame(DrawFrame(sc, to_draw_params(st)))
            prev_tilt = out[15]
            final = list(out)
            finalize_av(final)
            pc = [0] * 20
            for k, slot in enumerate(_X_TO_SLOT):
                pc[slot] = final[k]
            pc[C.OUT_T0], pc[C.OUT_PH] = p["T0"], p["PH"]
            pc[C.OUT_DU], pc[C.OUT_PH2] = p["DU"], p["PH2"]
            frame, delayed = send_pars(pc, delayed)
            if frame is not None:
                frames.append(frame)
            advance_frame(st.param, st.dipspec, tcum, out, fls)
            fi += 1
    return synthesize_frames(SPEAKERS[speaker_index], frames)


def _pcm_sha(samples: list[int]) -> str:
    return hashlib.sha256(struct.pack(f"<{len(samples)}h", *samples)).hexdigest()


def _capture(speaker: int, rundir: str):
    phs = os.path.join(rundir, "phs.txt")
    phd = os.path.join(rundir, "phd.txt")
    wav = os.path.join(rundir, "o.wav")
    env = dict(os.environ, DECTALK_DIR=rundir, DECTALK_PHS_DUMP=phs, DECTALK_PH_DUMP=phd)
    env["LD_LIBRARY_PATH"] = os.pathsep.join(
        [GEN_LIB, US_LIB, env.get("LD_LIBRARY_PATH", "")])
    subprocess.run(
        [ORACLE_BIN, "-s", str(speaker), "-e", "1", "-fo", wav, "-a", TEXT],
        cwd=rundir, env=env, capture_output=True, timeout=60)
    stream = None
    for line in open(phs):
        t = line.split()
        if t[0] == "A":
            rest = t[3:]
            i = rest.index("|")
            allophons = [int(x) for x in rest[:i]]
            rest = rest[i + 1:]
            j = rest.index("|")
            allofeats = [int(x) for x in rest[:j]]
            allodurs = [int(x) for x in rest[j + 1:]]
            stream = dict(malfem=int(t[1]), nallotot=int(t[2]), allophons=allophons,
                          allofeats=allofeats, allodurs=allodurs)
            break
    prosody, Y = [], []
    for line in open(phd):
        t = line.split()
        if t[0] == "E":
            v = [int(x) for x in t[1:]]
            prosody.append(dict(phon=v[1], spdefb1off=v[2], avglstop=v[3], f0=v[4],
                                f0_dep_tilt=v[5], spdeftltoff=v[6], spdeflaxprcnt=v[8]))
        elif t[0] == "Y":
            Y.append([int(x) for x in t[1:]])
    for k, y in enumerate(Y):
        prosody[k].update(T0=y[0], PH=y[1], DU=y[2], PH2=y[3])
    stream["prosody"] = prosody
    data = open(wav, "rb").read()
    di = data.find(b"data")
    n = struct.unpack("<I", data[di + 4:di + 8])[0]
    wav_pcm = list(struct.unpack(f"<{n // 2}h", data[di + 8:di + 8 + n]))
    return stream, wav_pcm


def load() -> dict:
    with open(GOLDEN_PATH) as f:
        return json.load(f)


def check() -> list[str]:
    data = load()
    bad: list[str] = []
    for i, name in enumerate(VOICE_NAMES):
        pcm = compose_pcm(i, data["cases"][name])
        if _pcm_sha(pcm) != data["pcm_sha256"][name]:
            bad.append(name)
    return bad


def main() -> None:
    if "--write" not in sys.argv:
        print(f"usage: {sys.argv[0]} --write   (rewrites {GOLDEN_PATH})")
        raise SystemExit(2)
    if not ORACLE_BIN or not os.path.exists(ORACLE_BIN):
        raise SystemExit(f"instrumented oracle not found at {ORACLE_BIN}; set DECTALK_SAY.")
    cases: dict[str, dict] = {}
    shas: dict[str, str] = {}
    mismatches: list[str] = []
    with tempfile.TemporaryDirectory() as rundir:
        for src in glob.glob(os.path.join(DIC_DIR, "*")):
            dst = os.path.join(rundir, os.path.basename(src))
            if not os.path.exists(dst):
                os.symlink(src, dst)
        for i, name in enumerate(VOICE_NAMES):
            stream, wav_pcm = _capture(i, rundir)
            pcm = compose_pcm(i, stream)
            if pcm != wav_pcm:
                mismatches.append(f"{name} ({sum(a != b for a, b in zip(pcm, wav_pcm, strict=False))} samples)")
            cases[name] = stream
            shas[name] = _pcm_sha(wav_pcm)
    if mismatches:
        print("composed chain differs from the oracle WAV; refusing to write goldens:")
        for m in mismatches:
            print("  " + m)
        raise SystemExit(1)
    with open(GOLDEN_PATH, "w") as f:
        json.dump({"text": TEXT, "cases": cases, "pcm_sha256": shas}, f, sort_keys=True)
        f.write("\n")
    print(f"verified {len(VOICE_NAMES)} voices' allophone->PCM chain against the "
          f"oracle WAV over {TEXT!r}; wrote streams + PCM digests")


if __name__ == "__main__":
    main()
