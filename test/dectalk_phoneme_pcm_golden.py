"""Shared definitions for the DECtalk phoneme -> PCM golden gate.

`phclause.speak_phonemes` is deterministic: a given phoneme+stress+sentstruc
`symbols[]` stream and voice always yield the same PCM. `dectalk_phoneme_pcm_golden.json`
records a sha256 digest of `speak_phonemes` evaluated over
`dectalk_phoneme_pcm_vectors.json` -- real per-clause `symbols[]`/`user_durs`
streams captured from the C oracle at the `phclause` input boundary -- for all
ten voices.

The digest is anchored to the C reference at write time: `--write` refuses to
regenerate it unless the port first reproduces the oracle WAV sample for sample,
for all ten voices, over these real captures (see `verify_against_oracle` and
test_dectalk_phoneme_pcm.py). The committed vectors are real captured DECtalk
input, not synthetic.

Regenerate only alongside a fresh C comparison:

    DECTALK_SAY=.../say ... python3 test/dectalk_phoneme_pcm_golden.py --write
"""
import hashlib
import json
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.dectalk.phclause import Clause, speak_phonemes

GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "dectalk_phoneme_pcm_golden.json")
VECTORS_PATH = os.path.join(os.path.dirname(__file__), "dectalk_phoneme_pcm_vectors.json")


def _vectors() -> list[dict]:
    with open(VECTORS_PATH) as f:
        return json.load(f)


def _pcm(voice: int, vec: dict) -> list[int]:
    clauses = [Clause(tuple(c["symbols"]), tuple(c["user_durs"]))
               for c in vec["clauses"]]
    return speak_phonemes(voice, clauses)


def digest() -> str:
    """sha256 of `speak_phonemes`'s PCM over every vector, all ten voices."""
    out: list[int] = []
    for vec in _vectors():
        for voice in range(10):
            out.extend(_pcm(voice, vec))
    pcm = struct.pack(f"<{len(out)}h", *out)
    return hashlib.sha256(pcm).hexdigest()


def sample_count() -> int:
    return sum(len(_pcm(v, vec)) for vec in _vectors() for v in range(10))


def load() -> dict:
    with open(GOLDEN_PATH) as f:
        return json.load(f)


def verify_against_oracle() -> tuple[int, int]:
    """Diff `speak_phonemes` against the oracle WAV, all voices, over the vectors.

    Returns (mismatched_samples, samples_checked). Requires the instrumented `say`.
    """
    from tools.dump_dectalk_phonemes import capture

    bad = 0
    total = 0
    for vec in _vectors():
        for voice in range(10):
            u = capture(voice, vec["text"])
            if u is None:
                continue
            my = speak_phonemes(
                voice, [Clause(c.symbols, c.user_durs) for c in u.clauses])
            n = min(len(my), len(u.pcm))
            bad += sum(1 for a, b in zip(my[:n], u.pcm[:n], strict=False) if a != b)
            bad += abs(len(my) - len(u.pcm))
            total += max(len(my), len(u.pcm))
    return bad, total


if __name__ == "__main__":
    if "--write" in sys.argv:
        bad, total = verify_against_oracle()
        if total == 0:
            sys.exit("refusing to write: no oracle captures (build instrumented say)")
        if bad:
            sys.exit(f"refusing to write: {bad}/{total} PCM samples differ from the C oracle")
        with open(GOLDEN_PATH, "w") as f:
            json.dump({"sha256": digest(), "samples": sample_count()}, f, indent=2)
            f.write("\n")
        print(f"wrote {GOLDEN_PATH}: {total} samples oracle-exact, sha256={digest()}")
    else:
        print(digest())
