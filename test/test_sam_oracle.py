"""Sample-for-sample C vs Python comparison for SAM.

Shells out to the compiled SAM `oracle` binary (a no-SDL build that writes its
8-bit PCM to stdout) for a matrix of texts and voice knobs, and diffs it against
the Python port's native 8-bit output. This is what the golden digests are
anchored to. It is skipped when the binary is absent, so it does not run in CI.

Build the binary from a read-only checkout of github.com/vidarh/SAM:

    gcc -O2 -o oracle oracle_main.c src/reciter.c src/sam.c src/render.c \\
        src/debug.c src/processframes.c src/createtransitions.c

where oracle_main.c parses -pitch/-speed/-mouth/-throat/-phonetic/-sing and
writes GetBuffer()[:GetBufferLength()//50] to stdout. Point SAM_ORACLE at it.

Usage:
    python3 test/test_sam_oracle.py
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.sam import sam
from pyretrotts.sam.engine import SAMEngine

ORACLE_BIN = os.environ.get(
    "SAM_ORACLE", os.path.expanduser("~/AgentWorkspaces/ovos/SAM-c/oracle")
)

TEXTS = [
    ("hello world", False),
    ("the quick brown fox jumps over the lazy dog", False),
    ("what time is it", False),
    ("cat dog bird fish", False),
    ("sixty four", False),
    ("commodore sixty four", False),
    ("testing one two three four five", False),
    ("zorbnax quixotry", False),
    ("", False),
    ("AA5", True),
    ("/HEHLOW", True),
    ("MAY NEYM IHZ SAEM", True),
    ("AY5 AEM EY TAO4LXKIHNX KAX4MPYUX4TAH", True),
]


def c_pcm(source, phonetic, knobs, sing=False):
    args = [
        ORACLE_BIN,
        "-pitch", str(knobs.pitch),
        "-speed", str(knobs.speed),
        "-mouth", str(knobs.mouth),
        "-throat", str(knobs.throat),
    ]
    if sing:
        args.append("-sing")
    if phonetic:
        args.append("-phonetic")
    args.append(source)
    return subprocess.run(args, capture_output=True, timeout=60).stdout


def run():
    if not os.path.exists(ORACLE_BIN):
        print(f"SKIP: no SAM oracle at {ORACLE_BIN} (set SAM_ORACLE)")
        return 0
    total = 0
    fails = 0
    for voice, knobs in SAMEngine.VOICE_KNOBS.items():
        for source, phonetic in TEXTS:
            for sing in (False, True):
                if sing and not phonetic:
                    continue
                total += 1
                c8 = c_pcm(source, phonetic, knobs, sing)
                py8 = sam.render_pcm(
                    source, speed=knobs.speed, pitch=knobs.pitch,
                    mouth=knobs.mouth, throat=knobs.throat,
                    phonetic=phonetic, singmode=sing,
                )
                if bytes(c8) != bytes(py8):
                    fails += 1
                    diff = sum(1 for a, b in zip(c8, py8, strict=False) if a != b)
                    tag = "sing " if sing else ""
                    print(f"FAIL {voice:18} {tag}{source!r:40} "
                          f"c={len(c8)} py={len(py8)} bytediff={diff}")
    print(f"\n{total - fails}/{total} byte-exact vs C")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(run())
