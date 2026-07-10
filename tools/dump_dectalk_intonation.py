"""Capture the `ph/` F0/intonation stage boundary from the DECtalk oracle.

The instrumented `phinton` (`ph_inton0.c`) and `pht0draw` (`ph_drwt01.c`), gated
on `DECTALK_INT_DUMP`, write, per clause:

  - ``I nallotot f0mode cbsymbol size_hat_rise scale_str_rise assertiveness |
    <allophons> | <allofeats> | <allodurs> | <user_f0> | <user_offset>`` --
    `phinton`'s input: the post-`us_phtiming` stream and the speaker F0 scalars;
  - ``O nallotot nf0tot | <f0tim> | <f0tar> | <allophons> | <allofeats> |
    <allodurs>`` -- `phinton`'s output: the F0 command arrays and the (now
    longer, reduced-vowel-inserted) allophone stream;
  - ``S nf0ev_seed f0basefall f0_lp_filter f0minimum f0scalefac newparagsw
    f0mode`` -- the `pht0draw` per-clause scalars, dumped on its first frame;
  - one ``T f0prime t0`` line per output frame -- the drawn fundamental and the
    period `parstochip[OUT_T0]` the vocal tract model consumes.

`phinton` inserts phones after `us_phtiming`, so the `O` stream is longer than
the `I` stream; the capture is taken at `phinton`'s own boundary (the `A`-line
`phsettar` stream, captured elsewhere, already reflects the post-`phinton`
length). This module drives the oracle (`capture`) and parses its dump (`parse`)
for `test/test_dectalk_phinton.py`.
"""
from __future__ import annotations

import glob
import os
import subprocess
import tempfile
from dataclasses import dataclass, field

_DTK = os.path.expanduser("~/AgentWorkspaces/ovos/dectalk-c/src")


def _first(pattern: str) -> str:
    hits = sorted(glob.glob(pattern))
    return hits[0] if hits else ""


ORACLE_BIN = os.environ.get(
    "DECTALK_SAY", _first(f"{_DTK}/samplosf/build/dtsamples/*/us/release/say"))
GEN_LIB = os.environ.get("DECTALK_GEN_LIB", _first(f"{_DTK}/dtalkml/build/*/us/release"))
US_LIB = os.environ.get("DECTALK_US_LIB", _first(f"{_DTK}/dapi/build/dectalk/*/us/release"))
DIC_DIR = os.environ.get("DECTALK_DIR", _first(f"{_DTK}/dapi/build/dic/*/us/release"))


@dataclass(frozen=True)
class IntonClause:
    """One captured `phinton`/`pht0draw` invocation (input, output, per-frame T0)."""

    # phinton input.
    nallotot_in: int
    f0mode: int
    cbsymbol: int
    size_hat_rise: int
    scale_str_rise: int
    assertiveness: int
    allophons_in: tuple[int, ...]
    allofeats_in: tuple[int, ...]
    allodurs_in: tuple[int, ...]
    user_f0: tuple[int, ...]
    user_offset: tuple[int, ...]
    # phinton output.
    nallotot_out: int
    nf0tot: int
    f0tim: tuple[int, ...]
    f0tar: tuple[int, ...]
    allophons_out: tuple[int, ...]
    allofeats_out: tuple[int, ...]
    allodurs_out: tuple[int, ...]
    # pht0draw scalars + per-frame output.
    nf0ev_seed: int = -2
    f0basefall: int = 0
    f0_lp_filter: int = 0
    f0minimum: int = 0
    f0scalefac: int = 0
    newparagsw: int = 0
    f0prime: tuple[int, ...] = field(default_factory=tuple)
    t0: tuple[int, ...] = field(default_factory=tuple)


def _split3(rest: list[str]) -> list[list[str]]:
    """Split a `|`-delimited remainder into its pipe-separated groups."""
    groups: list[list[str]] = [[]]
    for tok in rest:
        if tok == "|":
            groups.append([])
        else:
            groups[-1].append(tok)
    return groups


def parse(path: str) -> list[IntonClause]:
    """Read the `I`/`O`/`S`/`T` lines the instrumented stage wrote."""
    clauses: list[IntonClause] = []
    cur: dict | None = None
    f0prime: list[int] = []
    t0: list[int] = []

    def flush() -> None:
        if cur is not None:
            clauses.append(IntonClause(
                f0prime=tuple(f0prime), t0=tuple(t0), **cur))

    for line in open(path):
        t = line.split()
        if not t:
            continue
        if t[0] == "I":
            flush()
            cur = None
            f0prime.clear()
            t0.clear()
            head = [int(x) for x in t[1:7]]
            g = _split3(t[7:])
            cur = dict(
                nallotot_in=head[0], f0mode=head[1], cbsymbol=head[2],
                size_hat_rise=head[3], scale_str_rise=head[4], assertiveness=head[5],
                allophons_in=tuple(int(x) for x in g[1]),
                allofeats_in=tuple(int(x) for x in g[2]),
                allodurs_in=tuple(int(x) for x in g[3]),
                user_f0=tuple(int(x) for x in g[4]),
                user_offset=tuple(int(x) for x in g[5]),
            )
        elif t[0] == "O" and cur is not None:
            g = _split3(t[3:])
            cur.update(
                nallotot_out=int(t[1]), nf0tot=int(t[2]),
                f0tim=tuple(int(x) for x in g[1]),
                f0tar=tuple(int(x) for x in g[2]),
                allophons_out=tuple(int(x) for x in g[3]),
                allofeats_out=tuple(int(x) for x in g[4]),
                allodurs_out=tuple(int(x) for x in g[5]),
            )
        elif t[0] == "S" and cur is not None:
            cur.update(
                nf0ev_seed=int(t[1]), f0basefall=int(t[2]), f0_lp_filter=int(t[3]),
                f0minimum=int(t[4]), f0scalefac=int(t[5]), newparagsw=int(t[6]))
        elif t[0] == "T" and cur is not None:
            f0prime.append(int(t[1]))
            t0.append(int(t[2]))
    flush()
    return clauses


def capture(speaker: int, text: str) -> list[IntonClause]:
    """Run the oracle for one voice/utterance and return its intonation clauses."""
    with tempfile.TemporaryDirectory() as rundir:
        for src in glob.glob(os.path.join(DIC_DIR, "*")):
            dst = os.path.join(rundir, os.path.basename(src))
            if not os.path.exists(dst):
                os.symlink(src, dst)
        dump = os.path.join(rundir, "int.txt")
        env = dict(os.environ, DECTALK_DIR=rundir, DECTALK_INT_DUMP=dump)
        env["LD_LIBRARY_PATH"] = os.pathsep.join(
            [GEN_LIB, US_LIB, env.get("LD_LIBRARY_PATH", "")])
        subprocess.run(
            [ORACLE_BIN, "-s", str(speaker), "-e", "1", "-fo",
             os.path.join(rundir, "o.wav"), "-a", text],
            cwd=rundir, env=env, capture_output=True, timeout=60)
        return parse(dump) if os.path.exists(dump) else []
