"""Shared definitions for the DECtalk `phsort`/`phalloph` allophone golden gate.

`phsort` and `phalloph` are deterministic: a given symbol stream always yields
the same phoneme/allophone streams. `dectalk_phalloph_golden.json` records a
sha256 digest of `allophones.phsort` followed by `allophones.phalloph` evaluated
over `dectalk_phalloph_vectors.json` -- real allophone-stage inputs captured from
the C oracle at the `phsort` boundary (the `symbols`/`user_durs` phsort consumes,
plus the `phonemes`/`sentstruc` it produced, which phalloph consumes) for all ten
voices over a varied utterance set.

The digest is anchored to the C reference at write time: `--write` refuses to
regenerate it unless the port first reproduces the oracle's `phonemes`,
`sentstruc`, `allophons`, and `allofeats` field for field, for all ten voices,
over real utterances. The committed vectors are real captured DECtalk data.

Regenerate only alongside a fresh C comparison:

    DECTALK_SAY=.../say ... python3 test/dectalk_phalloph_golden.py --write
"""
import hashlib
import json
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.dectalk.allophones import phalloph, phsort

GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "dectalk_phalloph_golden.json")
VECTORS_PATH = os.path.join(os.path.dirname(__file__), "dectalk_phalloph_vectors.json")

TEXTS = [
    "a test one two three",
    "hello there my name is paul",
    "the fish shifts sixty seven",
    "many men running homeward",
    "the quick brown fox jumps",
    "ready to go, he wants to eat",
    "strength of the people",
    "little butter kitty water",
    "for the win, out of the box",
    "is it ready? stop that now!",
]


def _vectors() -> list[dict]:
    with open(VECTORS_PATH) as f:
        return json.load(f)


def _s16(v: int) -> int:
    return v if -0x8000 <= v <= 0x7FFF else v & 0xFFFF


def _outputs(vec: dict) -> list[int]:
    """phsort then phalloph outputs for one vector, flattened."""
    pho, sst, nph = phsort(tuple(vec["symbols"]), tuple(vec["user_durs"]))
    alo, aft, nal = phalloph(tuple(vec["phonemes"]), tuple(vec["sentstruc"]),
                             len(vec["phonemes"]))
    return [nph, *pho, *[_s16(x) for x in sst],
            nal, *alo, *[_s16(x) for x in aft]]


def digest() -> str:
    """sha256 of phsort+phalloph outputs over every captured vector."""
    out: list[int] = []
    for vec in _vectors():
        out.extend(_s16(x) for x in _outputs(vec))
    pcm = struct.pack(f"<{len(out)}h", *out)
    return hashlib.sha256(pcm).hexdigest()


def load() -> dict:
    with open(GOLDEN_PATH) as f:
        return json.load(f)


def verify_against_oracle() -> tuple[int, int]:
    """Replay phsort+phalloph over the oracle boundary, all voices.

    Returns (mismatches, fields_checked). Requires the instrumented `say`.
    """
    from tools.dump_dectalk_phalloph import capture

    mism = 0
    total = 0
    for sp in range(10):
        for tx in TEXTS:
            for c in capture(sp, tx):
                pho, sst, nph = phsort(c.symbols, c.user_durs)
                alo, aft, nal = phalloph(c.phonemes, c.sentstruc,
                                         len(c.phonemes))
                if nph != len(c.phonemes) or nal != c.nallotot:
                    mism += 1
                for g, e in zip(pho, c.phonemes, strict=False):
                    total += 1
                    mism += g != e
                for g, e in zip(sst, c.sentstruc, strict=False):
                    total += 1
                    mism += g != e
                for g, e in zip(alo, c.allophons, strict=False):
                    total += 1
                    mism += g != e
                for g, e in zip(aft, c.allofeats, strict=False):
                    total += 1
                    mism += g != e
    return mism, total


def _write_vectors() -> int:
    from tools.dump_dectalk_phalloph import capture

    vectors: list[dict] = []
    for sp in range(10):
        for tx in TEXTS:
            for c in capture(sp, tx):
                vectors.append({
                    "symbols": list(c.symbols),
                    "user_durs": list(c.user_durs),
                    "phonemes": list(c.phonemes),
                    "sentstruc": list(c.sentstruc),
                    "nallotot": c.nallotot,
                    "allophons": list(c.allophons),
                    "allofeats": list(c.allofeats),
                })
    with open(VECTORS_PATH, "w") as f:
        json.dump(vectors, f)
        f.write("\n")
    return len(vectors)


if __name__ == "__main__":
    if "--write" in sys.argv:
        n = _write_vectors()
        if n == 0:
            sys.exit("refusing to write: no oracle captures (build instrumented say)")
        mism, total = verify_against_oracle()
        if total == 0:
            sys.exit("refusing to write: no oracle captures (build instrumented say)")
        if mism:
            sys.exit(f"refusing to write: {mism}/{total} fields differ from the C oracle")
        with open(GOLDEN_PATH, "w") as f:
            json.dump({"sha256": digest(), "fields": total, "vectors": n}, f, indent=2)
            f.write("\n")
        print(f"wrote {GOLDEN_PATH}: {n} vectors, {total} fields oracle-exact, "
              f"sha256={digest()}")
    else:
        print(digest())
