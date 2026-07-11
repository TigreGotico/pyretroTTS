"""Shared definitions for the DECtalk `uk_gettar` target-lookup golden gate.

`uk_gettar` (`settar_uk.py`, ported from `p_uk_st1.c:76`) is deterministic: the
same allophone stream always yields the same target for a given (parameter,
phone). `dectalk_uk_targets_golden.json` records a sha256 digest of `uk_gettar`
evaluated over a fixed, self-contained set of `Allophones` streams for every
parameter of every phone, exercised over the UK target ROM (`targets_uk.py`,
read verbatim from `libtts_uk.so`).

Unlike the US gate, this is a **regression tripwire only**. The UK oracle
library carries no isolated `gettar`/target dump (`DECTALK_TAR_DUMP` is present
only in `libtts_us.so`), so `uk_gettar` cannot be diffed call-for-call against
the C in isolation; it is exercised through the oracle only once the UK
`phsettar` smooth-rules / timing / intonation are ported and the whole
target+transition layer is gated via `DECTALK_PHS_DUMP`. Until then this digest
locks the port against accidental change and, with the ROM being byte-identical
to the compiled library, bites on any logic mutation. `--write` regenerates it
directly (there is no oracle isolation point to refuse against yet).

    python3 test/dectalk_uk_targets_golden.py --write
"""
import hashlib
import json
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.dectalk.settar import Allophones
from pyretrotts.dectalk.settar_uk import uk_gettar

GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "dectalk_uk_targets_golden.json")

# UK phone codes (font byte 0x1D | index) and GEN_SIL, plus feature masks, so the
# synthetic streams reach nasal, obstruent, /hx/, dummy-vowel and stress branches.
_SIL = 0x1E00  # GEN_SIL is language-agnostic (US font high byte).


def _ph(idx: int) -> int:
    return 0x1D00 | idx


def _build_synth_streams() -> list[Allophones]:
    """Hand-authored UK allophone streams spanning the ROM tables.

    Not captured DECtalk output: synthetic phone/feature sequences chosen to
    exercise the target-selection branches over the real UK ROM. Phone indices
    include the nasals (32/33/36), /hx/ (28), /jh/ (55), /ow/ (11) and vowels
    that reach the UK-specific TILT and aspiration rules.
    """
    streams: list[Allophones] = []
    phones = (_SIL, _ph(1), _ph(11), _ph(28), _ph(32), _ph(33), _ph(36),
              _ph(47), _ph(53), _ph(55), _ph(5), _ph(14), _SIL)
    feats_a = (0, 1, 3, 0o4000, 2, 0o1, 0, 3, 0o4000, 1, 0, 2, 0)
    feats_b = (0, 3, 0, 2, 0o4001, 0, 3, 1, 0, 0o4000, 2, 1, 0)
    for malfem in (1, 0):
        streams.append(Allophones(phones, feats_a, len(phones), malfem))
        streams.append(Allophones(phones, feats_b, len(phones), malfem))
    return streams


SYNTH_STREAMS = _build_synth_streams()


def digest() -> str:
    """sha256 of uk_gettar over every (parameter, phone) of SYNTH_STREAMS."""
    out: list[int] = []
    for stream in SYNTH_STREAMS:
        for nphone in range(stream.nallotot):
            for npar in range(16):
                v = uk_gettar(stream, npar, nphone)
                out.append(v if -0x8000 <= v <= 0x7FFF else v & 0xFFFF)
    pcm = struct.pack(f"<{len(out)}h", *out)
    return hashlib.sha256(pcm).hexdigest()


def load() -> dict:
    with open(GOLDEN_PATH) as f:
        return json.load(f)


if __name__ == "__main__":
    if "--write" in sys.argv:
        with open(GOLDEN_PATH, "w") as f:
            json.dump({"sha256": digest()}, f, indent=2)
            f.write("\n")
        print(f"wrote {GOLDEN_PATH}: sha256={digest()}")
    else:
        print(digest())
