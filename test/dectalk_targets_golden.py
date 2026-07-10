"""Shared definitions for the DECtalk `us_gettar` target-lookup golden gate.

`us_gettar` is deterministic: the same allophone stream always yields the same
target for a given (parameter, phone). `dectalk_targets_golden.json` records a
sha256 digest of `us_gettar` evaluated over a fixed, self-contained set of
`Allophones` streams (`SYNTH_STREAMS` below, authored here) for every parameter
of every phone.

The digest is anchored to the C reference at write time: `--write` refuses to
regenerate it unless the ported lookup first matches the instrumented C oracle
call for call, for all ten voices, over real utterances (see
`verify_against_oracle` and test_dectalk_phsettar.py). The synthetic streams are
only the deterministic regression tripwire; the proof of correctness is the
oracle match this refuses to skip.

Regenerate only alongside a fresh C comparison:

    DECTALK_SAY=.../say ... python3 test/dectalk_targets_golden.py --write
"""
import hashlib
import json
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.dectalk.settar import Allophones, us_gettar

GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "dectalk_targets_golden.json")

# US phone codes (font byte 0x1E | index) and GEN_SIL, plus feature masks, so the
# synthetic streams reach nasal, obstruent, /hx/, dummy-vowel and stress branches.
_SIL = 0x1E00


def _ph(idx: int) -> int:
    return 0x1E00 | idx


def _build_synth_streams() -> list[Allophones]:
    """Hand-authored allophone streams; phone indices span the ROM tables.

    Not captured DECtalk output: synthetic phone/feature sequences chosen to
    exercise the target-selection branches over the real ROM.
    """
    streams: list[Allophones] = []
    # A vowel/consonant sweep bracketed by silence, male and female, with a
    # range of allofeats bitmasks (stress, dummy-vowel, boundary bits).
    phones = (_SIL, _ph(1), _ph(17), _ph(28), _ph(32), _ph(33), _ph(36),
              _ph(47), _ph(53), _ph(55), _ph(4), _ph(9), _SIL)
    feats_a = (0, 1, 3, 0o4000, 2, 0o1, 0, 3, 0o4000, 1, 0, 2, 0)
    feats_b = (0, 3, 0, 2, 0o4001, 0, 3, 1, 0, 0o4000, 2, 1, 0)
    for malfem in (1, 0):
        streams.append(Allophones(phones, feats_a, len(phones), malfem))
        streams.append(Allophones(phones, feats_b, len(phones), malfem))
    return streams


SYNTH_STREAMS = _build_synth_streams()


def digest() -> str:
    """sha256 of us_gettar over every (parameter, phone) of SYNTH_STREAMS.

    Negative diphthong pointers are recorded as-is; values are clamped to the
    signed-16 range they already occupy.
    """
    out: list[int] = []
    for stream in SYNTH_STREAMS:
        for nphone in range(stream.nallotot):
            for npar in range(16):
                v = us_gettar(stream, npar, nphone)
                out.append(v if -0x8000 <= v <= 0x7FFF else v & 0xFFFF)
    pcm = struct.pack(f"<{len(out)}h", *out)
    return hashlib.sha256(pcm).hexdigest()


def load() -> dict:
    with open(GOLDEN_PATH) as f:
        return json.load(f)


def verify_against_oracle() -> int:
    """Return the number of (voice/text) cases whose Python lookup differs from C.

    Requires an instrumented oracle build; see test_dectalk_phsettar.py.
    """
    from test_dectalk_phsettar import ORACLE_BIN, run  # noqa: PLC0415

    if not ORACLE_BIN or not os.path.exists(ORACLE_BIN):
        raise SystemExit(
            f"instrumented oracle not found at {ORACLE_BIN!r}; set DECTALK_SAY. "
            "Refusing to verify.")
    return run()


def main() -> None:
    if "--write" not in sys.argv:
        print(f"usage: {sys.argv[0]} --write   (rewrites {GOLDEN_PATH})")
        raise SystemExit(2)
    if verify_against_oracle() != 0:
        print("Python lookup differs from the C oracle; refusing to write golden.")
        raise SystemExit(1)
    golden = {"synth_streams": digest()}
    with open(GOLDEN_PATH, "w") as f:
        json.dump(golden, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"verified against the C oracle; wrote {GOLDEN_PATH}")


if __name__ == "__main__":
    main()
