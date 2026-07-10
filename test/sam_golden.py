"""Shared definitions for SAM's golden PCM regression gate.

SAM is fully deterministic: the same text/phonemes and the same voice knobs
always produce the same bytes. `sam_golden.json` records a sha256 digest of the
16-bit engine output for every voice/text pair below.

The digests are anchored to the C reference: `--write` refuses to regenerate
them unless every case first matches the compiled `oracle` binary sample for
sample (see test/test_sam_oracle.py for the binary). Regenerate only alongside
a fresh C comparison:

    python3 test/sam_golden.py --write
"""
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.sam import sam
from pyretrotts.sam.engine import SAMEngine

GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "sam_golden.json")

ORACLE_BIN = os.environ.get(
    "SAM_ORACLE", os.path.expanduser("~/AgentWorkspaces/ovos/SAM-c/oracle")
)

VOICE_NAMES = list(SAMEngine.VOICE_KNOBS)

# (source, phonetic) per SAM front-end path: reciter text, plosive/flap rules,
# number reading, multi-clause breath insertion, and direct phonetic input.
TEXTS = {
    "text_hello": ("hello world", False),
    "text_flap": ("what time is it", False),
    "text_numbers": ("sixty four", False),
    "text_sentence": ("the quick brown fox jumps over the lazy dog", False),
    "phonetic_vowel": ("AA5", True),
    "phonetic_word": ("/HEHLOW", True),
}


def digest(voice: str, source: str, phonetic: bool) -> str:
    """sha256 of the 16-bit PCM the engine produces for this voice/text."""
    pcm = SAMEngine().synthesize(source, voice, phonetic=phonetic)
    return hashlib.sha256(pcm).hexdigest()


def compute_all() -> dict:
    return {
        voice: {
            name: digest(voice, source, phonetic)
            for name, (source, phonetic) in TEXTS.items()
        }
        for voice in VOICE_NAMES
    }


def _c_pcm8(source: str, phonetic: bool, knobs) -> bytes:
    args = [
        ORACLE_BIN,
        "-pitch", str(knobs.pitch),
        "-speed", str(knobs.speed),
        "-mouth", str(knobs.mouth),
        "-throat", str(knobs.throat),
    ]
    if phonetic:
        args.append("-phonetic")
    args.append(source)
    return subprocess.run(args, capture_output=True, timeout=60).stdout


def verify_against_c() -> list[str]:
    """Return a list of (voice/text) that differ from the C oracle, sample-exact."""
    failures = []
    for voice in VOICE_NAMES:
        knobs = SAMEngine.VOICE_KNOBS[voice]
        for name, (source, phonetic) in TEXTS.items():
            c8 = _c_pcm8(source, phonetic, knobs)
            py8 = sam.render_pcm(
                source, speed=knobs.speed, pitch=knobs.pitch,
                mouth=knobs.mouth, throat=knobs.throat, phonetic=phonetic,
            )
            if bytes(c8) != bytes(py8):
                failures.append(f"{voice}/{name}")
    return failures


def load() -> dict:
    with open(GOLDEN_PATH) as f:
        return json.load(f)


def main() -> None:
    if "--write" not in sys.argv:
        print(f"usage: {sys.argv[0]} --write   (rewrites {GOLDEN_PATH})")
        raise SystemExit(2)
    if not os.path.exists(ORACLE_BIN):
        print(f"C oracle not found at {ORACLE_BIN}; set SAM_ORACLE. Refusing to write.")
        raise SystemExit(1)
    failures = verify_against_c()
    if failures:
        print("Python output differs from the C oracle; refusing to write goldens:")
        for f in failures:
            print("  " + f)
        raise SystemExit(1)
    goldens = compute_all()
    with open(GOLDEN_PATH, "w") as f:
        json.dump(goldens, f, indent=2, sort_keys=True)
        f.write("\n")
    total = sum(len(v) for v in goldens.values())
    print(f"verified {total} cases against C; wrote {total} digests "
          f"({len(goldens)} voices x {len(TEXTS)} texts)")


if __name__ == "__main__":
    main()
