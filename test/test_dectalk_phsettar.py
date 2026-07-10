"""C vs Python comparison for the DECtalk `us_gettar` target-ROM lookup.

Shells out to an instrumented DECtalk `say` build that dumps, for every
`us_gettar` call, the parameter index, phone index, and returned target value,
plus (once per clause) the `allophons[]`/`allofeats[]` stream and speaker sex it
reads. The ported `settar.us_gettar` is replayed over the identical stream and
its result is diffed against the C, call for call, for each of the ten voices.
This is what the targets golden digest is anchored to. It is skipped when the
instrumented binary is absent, so it does not run in CI.

Build the instrumented oracle from a copy of github.com/dectalk/dectalk:

    # In src/dapi/src/ph/p_us_st0.c, gate on env DECTALK_TAR_DUMP and, at the
    # first parameter of the first phone of each clause, write
    #   "A <malfem> <nallotot> <allophons...>| <allofeats...>";
    # before each return of us_gettar write "G <npar> <nphone> <return>".
    cd src && ./autogen.sh && ./configure && make
    # The US say dlopens libtts_us.so; put both libtts.so and the patched
    # libtts_us.so on LD_LIBRARY_PATH and DECTALK_DIR at a dir holding the dic.

Usage:
    DECTALK_SAY=.../say DECTALK_GEN_LIB=.../us/release DECTALK_US_LIB=.../us/release \
    DECTALK_DIR=.../dic/us/release python3 test/test_dectalk_phsettar.py
"""
import glob
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.dectalk.settar import Allophones, us_gettar
from pyretrotts.dectalk.voices import VOICE_NAMES

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from dump_dectalk_vtm import parse_tar_dump  # noqa: E402

_DTK = os.path.expanduser("~/AgentWorkspaces/ovos/dectalk-c/src")


def _first(pattern: str) -> str:
    hits = sorted(glob.glob(pattern))
    return hits[0] if hits else ""


ORACLE_BIN = os.environ.get(
    "DECTALK_SAY",
    _first(f"{_DTK}/samplosf/build/dtsamples/*/us/release/say"))
GEN_LIB = os.environ.get(
    "DECTALK_GEN_LIB", _first(f"{_DTK}/dtalkml/build/*/us/release"))
US_LIB = os.environ.get(
    "DECTALK_US_LIB", _first(f"{_DTK}/dapi/build/dectalk/*/us/release"))
DIC_DIR = os.environ.get(
    "DECTALK_DIR", _first(f"{_DTK}/dapi/build/dic/*/us/release"))

TEXTS = [
    "a test one two three",
    "hello there my name is paul",
    "the fish shifts sixty seven",
    "many men running homeward",
]


def oracle_tar_records(speaker_num: int, text: str, rundir: str):
    """Run the instrumented oracle for one voice/text; yield (Allophones, calls)."""
    dump_path = os.path.join(rundir, "tar.txt")
    if os.path.exists(dump_path):
        os.unlink(dump_path)
    env = dict(os.environ, DECTALK_DIR=rundir, DECTALK_TAR_DUMP=dump_path)
    env["LD_LIBRARY_PATH"] = os.pathsep.join(
        [GEN_LIB, US_LIB, env.get("LD_LIBRARY_PATH", "")])
    subprocess.run(
        [ORACLE_BIN, "-s", str(speaker_num), "-e", "1", "-fo", os.devnull,
         "-a", text],
        cwd=rundir, env=env, capture_output=True, timeout=60)
    out = []
    for stream, calls in parse_tar_dump(dump_path):
        out.append((
            Allophones(
                allophons=stream["allophons"], allofeats=stream["allofeats"],
                nallotot=stream["nallotot"], malfem=stream["malfem"]),
            calls))
    return out


def run() -> int:
    if not ORACLE_BIN or not os.path.exists(ORACLE_BIN):
        print(f"SKIP: no instrumented oracle at {ORACLE_BIN!r} (set DECTALK_SAY)")
        return 0
    total = fails = calls = miss = 0
    with tempfile.TemporaryDirectory() as rundir:
        # The US say dlopens the dic by name from DECTALK_DIR/cwd.
        for src in glob.glob(os.path.join(DIC_DIR, "*")):
            dst = os.path.join(rundir, os.path.basename(src))
            if not os.path.exists(dst):
                os.symlink(src, dst)
        for speaker_num in range(len(VOICE_NAMES)):
            for text in TEXTS:
                total += 1
                case_fail = 0
                for stream, records in oracle_tar_records(speaker_num, text, rundir):
                    for npar, nphone, expected in records:
                        calls += 1
                        if us_gettar(stream, npar, nphone) != expected:
                            case_fail += 1
                            miss += 1
                if case_fail:
                    fails += 1
                    print(f"FAIL {VOICE_NAMES[speaker_num]}/{text!r}: "
                          f"{case_fail} calls differ")
    print(f"{total - fails}/{total} cases target-exact "
          f"({calls} gettar calls, {miss} mismatches)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(run())
