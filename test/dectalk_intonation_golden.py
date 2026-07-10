"""Shared definitions for the DECtalk `phinton`/`pht0draw` F0 golden gate.

The F0 stage is deterministic: a given post-`us_phtiming` stream and speaker F0
scalars always yield the same F0 command arrays and the same per-frame period.
`dectalk_intonation_golden.json` records a sha256 digest of `intonation.phinton`
plus `intonation.Pht0draw` evaluated over `dectalk_intonation_vectors.json` --
real intonation-stage captures from the C oracle (each utterance's clauses in
order, with the `nf0ev` seed and speaker scalars) across all ten voices.

The digest is anchored to the C at write time: `--write` refuses to regenerate it
unless the port first reproduces the oracle's `f0tar`/`f0tim` and per-frame `T0`
field for field, for all ten voices (see `verify_against_oracle` and
`test_dectalk_phinton.py`). The committed vectors are real captured data.

Regenerate only alongside a fresh C comparison:

    DECTALK_SAY=.../say ... python3 test/dectalk_intonation_golden.py --write
"""
import hashlib
import json
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyretrotts.dectalk.intonation import IntonState, Pht0draw, Pht0drawIn, phinton

GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "dectalk_intonation_golden.json")
VECTORS_PATH = os.path.join(os.path.dirname(__file__), "dectalk_intonation_vectors.json")

# The varied utterance corpus the vectors are captured over (statements,
# questions, multi-clause, emphasis, function-word runs).
TEXTS = [
    "a test one two three",
    "how are you today",
    "how are you today?",
    "hello there. how are you?",
    "the quick brown fox jumps over the lazy dog",
    "wait, stop, and listen carefully",
    "she said the cat sat on the mat",
    "one two three four five six seven",
    "is it raining outside right now?",
    "no. absolutely not. never again.",
]


def _vectors() -> list[dict]:
    with open(VECTORS_PATH) as f:
        return json.load(f)


def _phinton_out(cl: dict) -> tuple[list[int], list[int]]:
    st = IntonState(
        allophons=list(cl["allophons_in"]), allofeats=list(cl["allofeats_in"]),
        allodurs=list(cl["allodurs_in"]), nallotot=cl["nallotot_in"],
        user_f0=list(cl["user_f0"]), user_offset=list(cl["user_offset"]),
        f0mode=cl["f0mode"], cbsymbol=cl["cbsymbol"],
        size_hat_rise=cl["size_hat_rise"], scale_str_rise=cl["scale_str_rise"],
        assertiveness=cl["assertiveness"])
    phinton(st)
    return st.f0tar, st.f0tim


def _values() -> list[int]:
    """Every F0 output value: per clause, f0tar/f0tim, then per-frame T0/f0prime."""
    out: list[int] = []
    for utt in _vectors():
        draw: Pht0draw | None = None
        for cl in utt["clauses"]:
            f0tar, f0tim = _phinton_out(cl)
            out.extend(f0tar)
            out.extend(f0tim)
            src = Pht0drawIn(
                allophons=tuple(cl["allophons_out"]),
                allofeats=tuple(cl["allofeats_out"]),
                allodurs=tuple(cl["allodurs_out"]), nallotot=cl["nallotot_out"],
                f0tar=tuple(cl["f0tar"]), f0tim=tuple(cl["f0tim"]),
                nf0tot=cl["nf0tot"], f0mode=cl["f0mode"],
                f0basefall=cl["f0basefall"], f0_lp_filter=cl["f0_lp_filter"],
                f0minimum=cl["f0minimum"], f0scalefac=cl["f0scalefac"],
                newparagsw=cl["newparagsw"])
            if draw is None:
                draw = Pht0draw(src, nf0ev=cl["nf0ev_seed"])
            else:
                draw.new_clause(src, cl["nf0ev_seed"])
            for _ in range(cl["nframes"]):
                out.append(draw.step())
                out.append(draw.f0prime)
    return out


def digest() -> str:
    """sha256 of every F0 output value over every captured vector."""
    vals = [v if -0x8000 <= v <= 0x7FFF else v & 0xFFFF for v in _values()]
    return hashlib.sha256(struct.pack(f"<{len(vals)}h", *vals)).hexdigest()


def load() -> dict:
    with open(GOLDEN_PATH) as f:
        return json.load(f)


def _capture_vectors() -> list[dict]:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
    from dump_dectalk_intonation import capture

    utts: list[dict] = []
    for sp in range(10):
        for tx in TEXTS:
            clauses = capture(sp, tx)
            utt = {"sp": sp, "text": tx, "clauses": []}
            for c in clauses:
                utt["clauses"].append(dict(
                    nallotot_in=c.nallotot_in, f0mode=c.f0mode, cbsymbol=c.cbsymbol,
                    size_hat_rise=c.size_hat_rise, scale_str_rise=c.scale_str_rise,
                    assertiveness=c.assertiveness,
                    allophons_in=list(c.allophons_in), allofeats_in=list(c.allofeats_in),
                    allodurs_in=list(c.allodurs_in), user_f0=list(c.user_f0),
                    user_offset=list(c.user_offset),
                    nallotot_out=c.nallotot_out, nf0tot=c.nf0tot,
                    f0tar=list(c.f0tar), f0tim=list(c.f0tim),
                    allophons_out=list(c.allophons_out),
                    allofeats_out=list(c.allofeats_out),
                    allodurs_out=list(c.allodurs_out),
                    nf0ev_seed=c.nf0ev_seed, f0basefall=c.f0basefall,
                    f0_lp_filter=c.f0_lp_filter, f0minimum=c.f0minimum,
                    f0scalefac=c.f0scalefac, newparagsw=c.newparagsw,
                    nframes=len(c.t0)))
            utts.append(utt)
    return utts


def verify_against_oracle() -> tuple[int, int]:
    """Replay phinton/pht0draw over the oracle, all voices. Returns (mism, total)."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
    from dump_dectalk_intonation import capture

    mism = total = 0
    for sp in range(10):
        for tx in TEXTS:
            clauses = capture(sp, tx)
            draw: Pht0draw | None = None
            for c in clauses:
                st = IntonState(
                    allophons=list(c.allophons_in), allofeats=list(c.allofeats_in),
                    allodurs=list(c.allodurs_in), nallotot=c.nallotot_in,
                    user_f0=list(c.user_f0), user_offset=list(c.user_offset),
                    f0mode=c.f0mode, cbsymbol=c.cbsymbol,
                    size_hat_rise=c.size_hat_rise, scale_str_rise=c.scale_str_rise,
                    assertiveness=c.assertiveness)
                phinton(st)
                for g, e in ((tuple(st.f0tar), c.f0tar), (tuple(st.f0tim), c.f0tim)):
                    total += 1
                    if g != e:
                        mism += 1
                src = Pht0drawIn(
                    allophons=c.allophons_out, allofeats=c.allofeats_out,
                    allodurs=c.allodurs_out, nallotot=c.nallotot_out,
                    f0tar=c.f0tar, f0tim=c.f0tim, nf0tot=c.nf0tot, f0mode=c.f0mode,
                    f0basefall=c.f0basefall, f0_lp_filter=c.f0_lp_filter,
                    f0minimum=c.f0minimum, f0scalefac=c.f0scalefac,
                    newparagsw=c.newparagsw)
                if draw is None:
                    draw = Pht0draw(src, nf0ev=c.nf0ev_seed)
                else:
                    draw.new_clause(src, c.nf0ev_seed)
                for exp_t0, exp_f0p in zip(c.t0, c.f0prime, strict=False):
                    total += 1
                    if draw.step() != exp_t0 or draw.f0prime != exp_f0p:
                        mism += 1
    return mism, total


if __name__ == "__main__":
    if "--write" in sys.argv:
        mism, total = verify_against_oracle()
        if total == 0:
            sys.exit("refusing to write: no oracle captures (build instrumented say)")
        if mism:
            sys.exit(f"refusing to write: {mism}/{total} F0 values differ from the C oracle")
        with open(VECTORS_PATH, "w") as f:
            json.dump(_capture_vectors(), f)
            f.write("\n")
        with open(GOLDEN_PATH, "w") as f:
            json.dump({"sha256": digest(), "values": len(_values())}, f, indent=2)
            f.write("\n")
        print(f"wrote {GOLDEN_PATH}: {total} F0 values oracle-exact, sha256={digest()}")
    else:
        print(digest())
