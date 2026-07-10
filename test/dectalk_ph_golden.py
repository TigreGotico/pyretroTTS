"""Shared definitions for the DECtalk `phdraw` frame-drawer golden gate.

`phdraw` is deterministic: the same entry state always draws the same parameters.
`dectalk_ph_golden.json` records a sha256 digest of the sixteen drawn parameters
over a fixed, self-contained set of `DrawFrame` inputs (`SYNTH_DRAW` below,
authored here, containing no DECtalk data).

The digest is anchored to the C reference at write time: `--write` refuses to
regenerate it unless the ported drawer first matches the instrumented C oracle
frame for frame, for all ten voices, over real utterances (see
`verify_against_oracle` and test_dectalk_ph.py). The synthetic vector is only the
deterministic regression tripwire; the proof of correctness is the oracle match
this refuses to skip.

Regenerate only alongside a fresh C comparison:

    DECTALK_SAY=.../dist/say DECTALK_DIR=.../dist python3 test/dectalk_ph_golden.py --write
"""
import hashlib
import json
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.dectalk.ph import DrawFrame, DrawScalars, PhParam, draw_frame

GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "dectalk_ph_golden.json")

_ZERO = PhParam(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)


def _scalars(**kw: int) -> DrawScalars:
    base = dict(
        tcum=0, phon=0, spdefb1off=4096, avglstop=0, f0=1200, f0_dep_tilt=75,
        spdeftltoff=6, breathysw=0, spdeflaxprcnt=0, fvvtran=0, dfvvtran=0,
        tvvbacktr=0, bvvtran=0, dbvvtran=0, breathyah=0, breathytilt=0)
    base.update(kw)
    return DrawScalars(**base)


def _params(**kw: PhParam) -> tuple[PhParam, ...]:
    order = ("F1", "F2", "F3", "FZ", "B1", "B2", "B3",
             "AV", "AP", "A2", "A3", "A4", "A5", "A6", "AB", "TILT")
    return tuple(kw.get(name, _ZERO) for name in order)


def _build_synth_draw() -> list[DrawFrame]:
    """Hand-authored `phdraw` inputs exercising every branch of the drawer.

    Not DECtalk data: synthetic interpolation state in the drawer's own units.
    """
    frames: list[DrawFrame] = []

    # Steady formants, no transition (tcum below every durlin/tbacktr).
    frames.append(DrawFrame(
        _scalars(tcum=0),
        _params(F1=PhParam(500, 40, 0, 0, 0, 0, 0, 0, 40, 0, 0),
                F2=PhParam(1500, 40, 0, 0, 0, 0, 0, 0, 40, 0, 0),
                F3=PhParam(2500, 40, 0, 0, 0, 0, 0, 0, 40, 0, 0),
                B1=PhParam(60, 40, 0, 0, 0, 0, 0, 0, 40, 0, 0),
                AV=PhParam(60, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))))

    # Forward transition decaying, plus PB1 breathy widening.
    frames.append(DrawFrame(
        _scalars(tcum=3, spdefb1off=3600),
        _params(F1=PhParam(500, 40, 0, 0, 800, 200, 0, 0, 40, 0, 0),
                B1=PhParam(90, 40, 0, 0, 400, 100, 0, 0, 40, 0, 0),
                AV=PhParam(60, 0, 0, 0, 240, 40, 0, 0, 0, 0, 0))))

    # Backward transition active (tcum >= tbacktr) with negative btran.
    frames.append(DrawFrame(
        _scalars(tcum=30),
        _params(F1=PhParam(500, 40, 0, 0, 0, 0, -160, 20, 20, 0, 0),
                F3=PhParam(2500, 40, 0, 0, 0, 0, 120, -10, 20, 0, 0),
                AV=PhParam(58, 0, 0, 0, 0, 0, -80, 8, 20, 0, 0))))

    # Diphthong-line advance: tcum > durlin consumes the ndip peek values.
    frames.append(DrawFrame(
        _scalars(tcum=25),
        _params(F1=PhParam(500, 20, 40, 160, 0, 0, 0, 0, 40, 0, 0, 24, 8),
                F2=PhParam(1500, 20, -30, 80, 0, 0, 0, 0, 40, 0, 0, 12, -16))))

    # PF2 vowel-vowel coarticulation (fvvtran forward + bvvtran backward).
    frames.append(DrawFrame(
        _scalars(tcum=15, fvvtran=200, dfvvtran=20, tvvbacktr=10,
                 bvvtran=-96, dbvvtran=8),
        _params(F2=PhParam(1400, 40, 0, 0, 0, 0, 0, 0, 40, 0, 0))))

    # Special-onset constant (tcum < tspesh) on amplitude and formant params.
    frames.append(DrawFrame(
        _scalars(tcum=2),
        _params(F1=PhParam(500, 40, 0, 0, 0, 0, 0, 0, 40, 5, 180),
                A2=PhParam(50, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0),
                AB=PhParam(40, 0, 0, 0, 0, 0, 0, 0, 0, 5, 60))))

    # Post-onset double burst (tcum == tspesh + 1, drawn amplitude >= 10).
    frames.append(DrawFrame(
        _scalars(tcum=6),
        _params(A2=PhParam(55, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0),
                A3=PhParam(50, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0),
                AB=PhParam(45, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0))))

    # AV glottal-stop reduction (AV > 6).
    frames.append(DrawFrame(
        _scalars(tcum=10, avglstop=12),
        _params(AV=PhParam(60, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))))

    # Breathy voice: AV > 40 raises AP and tilts (breathysw == 1).
    frames.append(DrawFrame(
        _scalars(tcum=10, breathysw=1, spdeflaxprcnt=2048,
                 breathyah=10, breathytilt=4),
        _params(AV=PhParam(60, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
                AP=PhParam(20, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))))

    # Spectral-tilt clamp at the high end (low f0 -> large tilt).
    frames.append(DrawFrame(
        _scalars(tcum=10, f0=200, f0_dep_tilt=4096, spdeftltoff=40),
        _params(TILT=PhParam(30, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))))

    # Spectral-tilt clamp at zero (high f0, negative offset).
    frames.append(DrawFrame(
        _scalars(tcum=10, f0=1400, f0_dep_tilt=0, spdeftltoff=0),
        _params(TILT=PhParam(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))))

    return frames


SYNTH_DRAW = _build_synth_draw()

# Real utterances the oracle-anchored check drives before the golden may be
# written (mirrors test_dectalk_ph.py).
ORACLE_TEXTS = [
    "a test one two three",
    "hello there my name is paul",
    "the fish shifts sixty seven",
    "many men running homeward",
]


def digest() -> str:
    """sha256 of the drawn parameters over SYNTH_DRAW."""
    out: list[int] = []
    for frame in SYNTH_DRAW:
        out.extend(draw_frame(frame))
    pcm = struct.pack(f"<{len(out)}h", *out)
    return hashlib.sha256(pcm).hexdigest()


def load() -> dict:
    with open(GOLDEN_PATH) as f:
        return json.load(f)


def verify_against_oracle() -> list[str]:
    """Return the (voice/text) cases whose Python drawer differs from the C oracle.

    Requires an instrumented oracle build; see test_dectalk_ph.py.
    """
    from test_dectalk_ph import ORACLE_BIN, oracle_ph_frames  # noqa: PLC0415

    from pyretrotts.dectalk.voices import VOICE_NAMES  # noqa: PLC0415

    if not os.path.exists(ORACLE_BIN):
        raise SystemExit(
            f"instrumented oracle not found at {ORACLE_BIN}; set DECTALK_SAY. "
            "Refusing to verify.")
    failures: list[str] = []
    for speaker_num in range(len(VOICE_NAMES)):
        for text in ORACLE_TEXTS:
            for frame, expected in oracle_ph_frames(speaker_num, text):
                if draw_frame(frame) != expected:
                    failures.append(f"{VOICE_NAMES[speaker_num]}/{text!r}")
                    break
    return failures


def main() -> None:
    if "--write" not in sys.argv:
        print(f"usage: {sys.argv[0]} --write   (rewrites {GOLDEN_PATH})")
        raise SystemExit(2)
    failures = verify_against_oracle()
    if failures:
        print("Python drawer differs from the C oracle; refusing to write golden:")
        for f in failures:
            print("  " + f)
        raise SystemExit(1)
    golden = {"synth_draw": digest()}
    with open(GOLDEN_PATH, "w") as f:
        json.dump(golden, f, indent=2, sort_keys=True)
        f.write("\n")
    print("verified 10 voices x "
          f"{len(ORACLE_TEXTS)} utterances against the C oracle; wrote {GOLDEN_PATH}")


if __name__ == "__main__":
    main()
