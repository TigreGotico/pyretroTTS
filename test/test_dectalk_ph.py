"""Frame-for-frame C vs Python comparison for the DECtalk `phdraw` frame drawer.

Shells out to an instrumented DECtalk `say` build that dumps, per synthesized
frame, the `phdraw` entry state (the `PARAMETER` interpolation blocks plus the
`pDph_t` scalars it reads) and the sixteen parameters it drew into `parstochip[]`.
The ported `ph.draw_frame` is replayed over the identical entry state and its
output is diffed against the C, frame for frame, for each of the ten voices. This
is what the ph golden digest is anchored to. It is skipped when the instrumented
binary is absent, so it does not run in CI.

Build the instrumented oracle from a copy of github.com/dectalk/dectalk:

    # In src/dapi/src/ph/ph_draw.c, gate on env DECTALK_PH_DUMP and, at phdraw
    # entry, write "E <tcum> <phon> <scalars...> <PARAMETER blocks...>"; right
    # before the non-HLSYN `return` (ph_draw.c:4307), write the drawn
    # "X <F1 F2 F3 FZ B1 B2 B3 AV AP A2 A3 A4 A5 A6 AB TLT>". Then:
    cd src && ./autogen.sh && ./configure && make
    # point DECTALK_SAY at the built say and DECTALK_DIR at its dist directory.

Usage:
    DECTALK_SAY=.../dist/say DECTALK_DIR=.../dist python3 test/test_dectalk_ph.py
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.dectalk.ph import DrawFrame, DrawScalars, PhParam, draw_frame
from pyretrotts.dectalk.voices import VOICE_NAMES

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from dump_dectalk_vtm import parse_ph_dump  # noqa: E402

ORACLE_BIN = os.environ.get(
    "DECTALK_SAY",
    os.path.expanduser("~/AgentWorkspaces/ovos/dectalk-c/dist/say"))
DECTALK_DIR = os.environ.get(
    "DECTALK_DIR", os.path.join(os.path.dirname(ORACLE_BIN)))

TEXTS = [
    "a test one two three",
    "hello there my name is paul",
    "the fish shifts sixty seven",
    "many men running homeward",
]


def build_frame(scalars: list[int], params: list[list[int]]) -> DrawFrame:
    """Assemble a `DrawFrame` from one parsed dump record."""
    return DrawFrame(DrawScalars(*scalars), tuple(PhParam(*p) for p in params))


def oracle_ph_frames(speaker_num: int, text: str):
    """Run the instrumented oracle for one voice/text; yield (DrawFrame, expected)."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
        dump_path = tmp.name
    env = dict(os.environ, DECTALK_DIR=DECTALK_DIR, DECTALK_PH_DUMP=dump_path)
    lib = os.path.join(DECTALK_DIR, "lib")
    if os.path.isdir(lib):
        env["LD_LIBRARY_PATH"] = lib + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    subprocess.run(
        [ORACLE_BIN, "-s", str(speaker_num), "-e", "1", "-fo", os.devnull,
         "-a", text],
        env=env, capture_output=True, timeout=60)
    records = parse_ph_dump(dump_path)
    os.unlink(dump_path)
    return [(build_frame(sc, ps), exp) for sc, ps, exp in records]


def run() -> int:
    if not os.path.exists(ORACLE_BIN):
        print(f"SKIP: no instrumented oracle at {ORACLE_BIN} (set DECTALK_SAY)")
        return 0
    total = frames = fails = 0
    for speaker_num in range(len(VOICE_NAMES)):
        for text in TEXTS:
            total += 1
            case_fail = 0
            for frame, expected in oracle_ph_frames(speaker_num, text):
                frames += 1
                if draw_frame(frame) != expected:
                    case_fail += 1
            if case_fail:
                fails += 1
                print(f"FAIL {VOICE_NAMES[speaker_num]}/{text!r}: "
                      f"{case_fail} frames differ")
    print(f"{total - fails}/{total} cases frame-exact ({frames} frames)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(run())
