"""Sample-for-sample C vs Python comparison for the DECtalk vocal tract model.

Shells out to an instrumented DECtalk `say` build that dumps, per synthesized
frame, the Klatt parameter block fed to the vocal tract model and the samples it
produced, plus the resolved speaker state. The ported `vtm.py` is replayed over
the identical frames and its output is diffed against the C sample for sample,
for each of the ten voices. This is what the golden digests are anchored to. It
is skipped when the instrumented binary is absent, so it does not run in CI.

Build the instrumented oracle from a copy of github.com/dectalk/dectalk:

    # In src/dapi/src/vtm/vtmiont.c, gate on env DECTALK_VTM_DUMP and, right
    # before the OutputData() call, write "F <nspf> <parambuff[1..20]> <iwave>";
    # after read_speaker_definition(phTTS), write the resolved "S ..." state.
    # (docs/dectalk.md gives the exact patch.) Then:
    cd src && ./autogen.sh && ./configure && make
    # point DECTALK_SAY at src/dist/say and DECTALK_DIR at src/dist.

Usage:
    DECTALK_SAY=.../dist/say DECTALK_DIR=.../dist python3 test/test_dectalk_oracle.py
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.dectalk.engine import synthesize_frames
from pyretrotts.dectalk.voices import SPEAKERS, VOICE_NAMES

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from dump_dectalk_vtm import parse_vtm_dump  # noqa: E402

ORACLE_BIN = os.environ.get(
    "DECTALK_SAY",
    os.path.expanduser("~/AgentWorkspaces/ovos/dectalk-c/src/dist/say"))
DECTALK_DIR = os.environ.get(
    "DECTALK_DIR", os.path.join(os.path.dirname(ORACLE_BIN)))

TEXTS = [
    "a test one two three",
    "hello there my name is paul",
    "the fish shifts sixty seven",
    "many men running homeward",
    "one thousand nine hundred",
]


def oracle_frames(speaker_num: int, text: str):
    """Run the instrumented oracle for one voice/text; return (speaker, frames).

    `speaker` maps to `SpeakerState`; `frames` is a list of (parameters, iwave).
    """
    from pyretrotts.dectalk.vtm import SpeakerState

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
        dump_path = tmp.name
    env = dict(os.environ, DECTALK_DIR=DECTALK_DIR, DECTALK_VTM_DUMP=dump_path)
    subprocess.run(
        [ORACLE_BIN, "-s", str(speaker_num), "-e", "1", "-fo", os.devnull,
         "-a", text],
        env=env, capture_output=True, timeout=60)
    raw, frames = parse_vtm_dump(dump_path)
    os.unlink(dump_path)
    fields = SpeakerState.__dataclass_fields__
    speaker = SpeakerState(**{k: raw[k] for k in fields})
    return speaker, frames


def run() -> int:
    if not os.path.exists(ORACLE_BIN):
        print(f"SKIP: no instrumented oracle at {ORACLE_BIN} (set DECTALK_SAY)")
        return 0
    total = 0
    fails = 0
    for speaker_num in range(len(VOICE_NAMES)):
        for text in TEXTS:
            total += 1
            speaker, frames = oracle_frames(speaker_num, text)
            # The resolved speaker state must match the shipped voice table too.
            if speaker != SPEAKERS[speaker_num]:
                fails += 1
                print(f"FAIL {VOICE_NAMES[speaker_num]:18} speaker-state mismatch")
                continue
            samples = synthesize_frames(speaker, [f for f, _ in frames])
            expected = [s for _, w in frames for s in w]
            if samples != expected:
                fails += 1
                diff = sum(1 for a, b in zip(samples, expected, strict=False) if a != b)
                print(f"FAIL {VOICE_NAMES[speaker_num]:18} {text!r:34} "
                      f"n={len(expected)} samplediff={diff}")
    print(f"\n{total - fails}/{total} sample-exact vs C")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(run())
