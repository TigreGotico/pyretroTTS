"""Shared definitions for the golden PCM regression gate.

The synthesizer is fully deterministic: the same voice and the same text always
produce the same bytes. `golden_pcm.json` records a sha256 digest of that output
for every voice/text pair below, and `test_golden_pcm.py` re-derives them.

The digests were captured from output verified sample-for-sample against the C
reference (`test_voices.py --all`). Regenerate them only together with a fresh
run of that comparison:

    python3 test/golden.py --write
    python3 test/test_voices.py --all
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pylintalker import _data
from pylintalker.api import synthesize_text

GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "golden_pcm.json")

VOICE_NAMES = [
    "Fred", "Kathy", "Princess", "Junior", "Ralph", "Whisper", "Zarvox",
    "Trinoids", "Bubbles", "Boing", "Bells", "Hysterical", "Deranged",
    "GoodNews", "BadNews", "PipeOrgan", "Cellos",
]

VOICES = {name: getattr(_data, f"{name}_Voice") for name in VOICE_NAMES}

# One text per frontend stage the synthesizer can route through, so a digest
# change localizes the break: dictionary lookup, letter-to-sound fallback,
# suffix morphology, each number/date/currency/clock reader, multi-clause
# splitting, and embedded bracket commands.
TEXTS = {
    "dictionary": "hello, this is a test.",
    "letter_to_sound": "zorbnax quixotry.",
    "morphology": "the walking cats jumped quickly.",
    "cardinal": "123",
    "year": "in 1984 it began.",
    "currency": "$5.25",
    "clock": "the meeting is at 3:45.",
    "embedded": "[[rate240]]fast [[char LTRL]]DEC",
}


def digest(voice_dict: dict, text: str) -> str:
    """sha256 of the raw PCM `synthesize_text` produces for this voice/text."""
    return hashlib.sha256(synthesize_text(voice_dict, text)).hexdigest()


def compute_all() -> dict:
    """Digest every voice against every text, keyed {voice: {text_name: digest}}."""
    return {
        voice_name: {
            text_name: digest(voice_dict, text)
            for text_name, text in TEXTS.items()
        }
        for voice_name, voice_dict in VOICES.items()
    }


def load() -> dict:
    with open(GOLDEN_PATH) as f:
        return json.load(f)


def main() -> None:
    if "--write" not in sys.argv:
        print(f"usage: {sys.argv[0]} --write   (rewrites {GOLDEN_PATH})")
        raise SystemExit(2)
    goldens = compute_all()
    with open(GOLDEN_PATH, "w") as f:
        json.dump(goldens, f, indent=2, sort_keys=True)
        f.write("\n")
    total = sum(len(v) for v in goldens.values())
    print(f"wrote {total} digests ({len(goldens)} voices x {len(TEXTS)} texts)")


if __name__ == "__main__":
    main()
