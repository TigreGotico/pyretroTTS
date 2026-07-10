"""Oracle-anchored golden gate over the DECtalk vocal tract model.

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/vtm/vtm1.c`). FONIX Corporation declares that source proprietary
and confidential. This file is NOT covered by this project's MIT licence. See
NOTICE.

The synthetic `dectalk_golden.py` vector is self-contained (no DECtalk data) but,
because its frames never reproduce the post-speaker-definition ramp a real
utterance drives, it did not exercise the `ldspdef` silence path and so could not
catch a `vtm.py` regression there. This gate closes that gap: it captures the
*real* Klatt parameter frames the C ships to its vocal tract model
(`parambuff[1..20]`, dumped in `vtmiont.c`) and the samples that model returns
(`iwave`), for every voice over a real utterance, and asserts `vtm.py` reproduces
those samples exactly. The captured frames are DECtalk-derived data, hence the
FONIX notice; they run in CI without the oracle binary.

Regenerate only with an instrumented oracle build (see test_dectalk_endtoend.py
for the `parambuff`/`iwave` dumps):

    DECTALK_SAY=.../say ... python3 test/dectalk_vtm_pcm_golden.py --write
"""
import glob
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.dectalk.engine import synthesize_frames
from pyretrotts.dectalk.voices import SPEAKERS, VOICE_NAMES

GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "dectalk_vtm_pcm_golden.json")
TEXT = "a test"

_DTK = os.path.expanduser("~/AgentWorkspaces/ovos/dectalk-c/src")


def _first(pattern: str) -> str:
    hits = sorted(glob.glob(pattern))
    return hits[0] if hits else ""


ORACLE_BIN = os.environ.get(
    "DECTALK_SAY", _first(f"{_DTK}/samplosf/build/dtsamples/*/us/release/say"))
GEN_LIB = os.environ.get("DECTALK_GEN_LIB", _first(f"{_DTK}/dtalkml/build/*/us/release"))
US_LIB = os.environ.get("DECTALK_US_LIB", _first(f"{_DTK}/dapi/build/dectalk/*/us/release"))
DIC_DIR = os.environ.get("DECTALK_DIR", _first(f"{_DTK}/dapi/build/dic/*/us/release"))


def _iwave_sha(samples: list[int]) -> str:
    return hashlib.sha256(struct.pack(f"<{len(samples)}h", *samples)).hexdigest()


def _capture(speaker: int, rundir: str):
    """Return (parambuff_frames, iwave) the C vocal tract model consumed/produced."""
    vtm = os.path.join(rundir, "v.txt")
    iw = os.path.join(rundir, "iw.txt")
    env = dict(os.environ, DECTALK_DIR=rundir, DECTALK_VTM_DUMP=vtm,
               DECTALK_IWAVE_DUMP=iw)
    env["LD_LIBRARY_PATH"] = os.pathsep.join(
        [GEN_LIB, US_LIB, env.get("LD_LIBRARY_PATH", "")])
    subprocess.run(
        [ORACLE_BIN, "-s", str(speaker), "-e", "1", "-fo", os.devnull, "-a", TEXT],
        cwd=rundir, env=env, capture_output=True, timeout=60)
    frames = [[int(x) for x in ln.split()[1:]] for ln in open(vtm) if ln.startswith("V")]
    samples = [int(x) for ln in open(iw) if ln.startswith("W") for x in ln.split()[1:]]
    return frames, samples


def load() -> dict:
    with open(GOLDEN_PATH) as f:
        return json.load(f)


def check() -> list[str]:
    """Return voices whose `vtm.py` output differs from the captured oracle iwave."""
    data = load()
    bad: list[str] = []
    for i, name in enumerate(VOICE_NAMES):
        frames = data["frames"][name]
        out = synthesize_frames(SPEAKERS[i], frames)
        if _iwave_sha(out) != data["iwave_sha256"][name]:
            bad.append(name)
    return bad


def main() -> None:
    if "--write" not in sys.argv:
        print(f"usage: {sys.argv[0]} --write   (rewrites {GOLDEN_PATH})")
        raise SystemExit(2)
    if not ORACLE_BIN or not os.path.exists(ORACLE_BIN):
        raise SystemExit(f"instrumented oracle not found at {ORACLE_BIN}; set DECTALK_SAY.")
    frames_by_voice: dict[str, list[list[int]]] = {}
    sha_by_voice: dict[str, str] = {}
    mismatches: list[str] = []
    with tempfile.TemporaryDirectory() as rundir:
        for src in glob.glob(os.path.join(DIC_DIR, "*")):
            dst = os.path.join(rundir, os.path.basename(src))
            if not os.path.exists(dst):
                os.symlink(src, dst)
        for i, name in enumerate(VOICE_NAMES):
            frames, iwave = _capture(i, rundir)
            # The gate is only trustworthy if the port already matches the C.
            if synthesize_frames(SPEAKERS[i], frames) != iwave:
                mismatches.append(name)
            frames_by_voice[name] = frames
            sha_by_voice[name] = _iwave_sha(iwave)
    if mismatches:
        print("vtm.py differs from the C oracle; refusing to write goldens:")
        for m in mismatches:
            print("  " + m)
        raise SystemExit(1)
    with open(GOLDEN_PATH, "w") as f:
        json.dump({"text": TEXT, "frames": frames_by_voice,
                   "iwave_sha256": sha_by_voice}, f, sort_keys=True)
        f.write("\n")
    print(f"verified {len(VOICE_NAMES)} voices against the C oracle over "
          f"{TEXT!r}; wrote parambuff frames + iwave digests")


if __name__ == "__main__":
    main()
