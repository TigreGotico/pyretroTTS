"""Shared definitions for the DECtalk `us_phtiming` duration golden gate.

`us_phtiming` is deterministic: a given allophone/feature stream and speaking
rate always yield the same per-phone durations. `dectalk_aloph_golden.json`
records a sha256 digest of `timing.us_phtiming` evaluated over
`dectalk_aloph_vectors.json` -- real allophone-stage inputs captured from the C
oracle at the `us_phtiming` boundary (its input `allophons`/`allofeats`/
`user_durs` and the resolved speaking rate) for all ten voices.

The digest is anchored to the C reference at write time: `--write` refuses to
regenerate it unless the port first reproduces the oracle's `allodurs` field for
field, for all ten voices, over real utterances (see `verify_against_oracle` and
test_dectalk_aloph.py). The committed vectors are real captured DECtalk data, not
synthetic.

Regenerate only alongside a fresh C comparison:

    DECTALK_SAY=.../say ... python3 test/dectalk_aloph_golden.py --write
"""
import hashlib
import json
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.dectalk.timing import TimingConfig, us_phtiming

GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "dectalk_aloph_golden.json")
VECTORS_PATH = os.path.join(os.path.dirname(__file__), "dectalk_aloph_vectors.json")


def _vectors() -> list[dict]:
    with open(VECTORS_PATH) as f:
        return json.load(f)


def _durs(vec: dict) -> list[int]:
    return us_phtiming(
        tuple(vec["allophons_in"]),
        tuple(vec["allofeats"]),
        tuple(vec["user_durs"]),
        vec["nallotot"],
        TimingConfig(sprate=vec["sprate"]),
    )


def digest() -> str:
    """sha256 of `us_phtiming`'s `allodurs` over every captured vector."""
    out: list[int] = []
    for vec in _vectors():
        for d in _durs(vec):
            out.append(d if -0x8000 <= d <= 0x7FFF else d & 0xFFFF)
    pcm = struct.pack(f"<{len(out)}h", *out)
    return hashlib.sha256(pcm).hexdigest()


def load() -> dict:
    with open(GOLDEN_PATH) as f:
        return json.load(f)


def verify_against_oracle() -> tuple[int, int]:
    """Replay `us_phtiming` over the oracle at the timing boundary, all voices.

    Returns (mismatches, durations_checked). Requires the instrumented `say`.
    """
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
    from dump_dectalk_aloph import capture

    texts = [
        "a test one two three",
        "hello there my name is paul",
        "the fish shifts sixty seven",
        "many men running homeward",
    ]
    mism = 0
    total = 0
    for sp in range(10):
        for tx in texts:
            for c in capture(sp, tx):
                out = us_phtiming(
                    c.allophons_in, c.allofeats, c.user_durs, c.nallotot,
                    TimingConfig(sprate=c.sprate))
                for g, e in zip(out, c.allodurs, strict=False):
                    total += 1
                    if g != e:
                        mism += 1
    return mism, total


if __name__ == "__main__":
    if "--write" in sys.argv:
        mism, total = verify_against_oracle()
        if total == 0:
            sys.exit("refusing to write: no oracle captures (build instrumented say)")
        if mism:
            sys.exit(f"refusing to write: {mism}/{total} durations differ from the C oracle")
        with open(GOLDEN_PATH, "w") as f:
            json.dump({"sha256": digest(), "durations": total}, f, indent=2)
            f.write("\n")
        print(f"wrote {GOLDEN_PATH}: {total} durations oracle-exact, sha256={digest()}")
    else:
        print(digest())
