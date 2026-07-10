"""Shared definitions for the DECtalk vocal tract model's golden PCM gate.

The synthesizer is deterministic: the same Klatt parameter frames and the same
voice always produce the same samples. `dectalk_golden.json` records a sha256
digest of the 16-bit output for every voice over a fixed, self-contained frame
vector (`SYNTH_FRAMES` below, authored here, containing no DECtalk data).

The digests are anchored to the C reference at write time: `--write` refuses to
regenerate them unless the ported engine first matches the instrumented C
oracle sample for sample, for all ten voices, over real utterances (see
`verify_against_oracle` and test_dectalk_oracle.py). The synthetic vector is
only the deterministic regression tripwire; the proof of correctness is the
oracle match this refuses to skip.

Regenerate only alongside a fresh C comparison:

    DECTALK_SAY=.../dist/say DECTALK_DIR=.../dist python3 test/dectalk_golden.py --write
"""
import hashlib
import json
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.dectalk import consts
from pyretrotts.dectalk.engine import synthesize_frames
from pyretrotts.dectalk.voices import SPEAKERS, VOICE_NAMES

GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "dectalk_golden.json")


def _frame(**kw: int) -> list[int]:
    f = [0] * 20
    f[consts.OUT_PH] = 250  # non-silence phoneme code: suppress the ramp-down
    for name, value in kw.items():
        f[getattr(consts, name)] = value
    return f


def _build_synth_frames() -> list[list[int]]:
    """A deterministic exercise of voicing, frication, nasality and aspiration.

    Not DECtalk data: hand-authored Klatt frames in the engine's own units.
    """
    frames: list[list[int]] = []
    # Two leading frames (the engine forces the post-speaker-def pair to silence).
    frames.append(_frame())
    frames.append(_frame())
    # A voiced vowel with a falling pitch.
    for t0 in (110, 116, 122, 128):
        frames.append(_frame(OUT_F1=500, OUT_F2=1500, OUT_F3=2500,
                             OUT_B1=60, OUT_B2=90, OUT_B3=150,
                             OUT_T0=t0, OUT_AV=60))
    # A nasal, moving the nasal zero.
    for fz in (250, 400) * 2:
        frames.append(_frame(OUT_F1=480, OUT_F2=1200, OUT_F3=2500, OUT_FZ=fz,
                             OUT_B1=90, OUT_B2=90, OUT_B3=150,
                             OUT_T0=124, OUT_AV=58))
    # A voiceless fricative burst through the parallel branch.
    for _ in range(4):
        frames.append(_frame(OUT_F2=1800, OUT_F3=2600,
                             OUT_A2=50, OUT_A3=55, OUT_A4=50, OUT_A5=40,
                             OUT_A6=30, OUT_AB=40, OUT_B2=200, OUT_B3=250))
    # Aspiration plus voicing.
    for _ in range(3):
        frames.append(_frame(OUT_F1=520, OUT_F2=1400, OUT_F3=2500,
                             OUT_B1=90, OUT_B2=120, OUT_B3=200,
                             OUT_T0=126, OUT_AV=55, OUT_AP=45))
    # Trailing silence, letting the filters ring down.
    frames.append(_frame())
    frames.append(_frame())
    return frames


SYNTH_FRAMES = _build_synth_frames()

# Real utterances the oracle-anchored check drives before goldens may be written.
ORACLE_TEXTS = [
    "a test one two three",
    "hello there my name is paul",
    "the fish shifts sixty seven",
    "many men running homeward",
]


def digest(voice_index: int) -> str:
    """sha256 of the 16-bit PCM the engine produces for a voice over SYNTH_FRAMES."""
    samples = synthesize_frames(SPEAKERS[voice_index], SYNTH_FRAMES)
    pcm = struct.pack(f"<{len(samples)}h", *samples)
    return hashlib.sha256(pcm).hexdigest()


def compute_all() -> dict:
    return {VOICE_NAMES[i]: digest(i) for i in range(len(VOICE_NAMES))}


def load() -> dict:
    with open(GOLDEN_PATH) as f:
        return json.load(f)


def verify_against_oracle() -> list[str]:
    """Return the (voice/text) cases whose Python output differs from the C oracle.

    Requires an instrumented oracle build; see test_dectalk_oracle.py.
    """
    from test_dectalk_oracle import ORACLE_BIN, oracle_frames  # noqa: PLC0415

    if not os.path.exists(ORACLE_BIN):
        raise SystemExit(
            f"instrumented oracle not found at {ORACLE_BIN}; set DECTALK_SAY. "
            "Refusing to verify.")
    failures: list[str] = []
    for speaker_num in range(len(VOICE_NAMES)):
        for text in ORACLE_TEXTS:
            speaker, frames = oracle_frames(speaker_num, text)
            samples = synthesize_frames(speaker, [f for f, _ in frames])
            expected = [s for _, w in frames for s in w]
            if samples != expected:
                failures.append(f"{VOICE_NAMES[speaker_num]}/{text!r}")
    return failures


def main() -> None:
    if "--write" not in sys.argv:
        print(f"usage: {sys.argv[0]} --write   (rewrites {GOLDEN_PATH})")
        raise SystemExit(2)
    failures = verify_against_oracle()
    if failures:
        print("Python output differs from the C oracle; refusing to write goldens:")
        for f in failures:
            print("  " + f)
        raise SystemExit(1)
    goldens = compute_all()
    with open(GOLDEN_PATH, "w") as f:
        json.dump(goldens, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"verified {len(VOICE_NAMES)} voices x {len(ORACLE_TEXTS)} utterances "
          f"against the C oracle; wrote {len(goldens)} digests")


if __name__ == "__main__":
    main()
