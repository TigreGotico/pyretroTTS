"""Capture the `ph/` allophone-selection stage boundary from the DECtalk oracle.

`phclause` runs ``phsort -> phalloph -> us_phtiming -> phinton``. Two
instrumentation points in `ph_claus.c` (gated on env vars, kept out of the
read-only checkout) expose this stage's boundary:

  - ``DECTALK_SORT_DUMP`` (`ph_claus.c`, right after ``phsort``) writes per clause
    an ``I`` line -- ``I malfem nsymbtot <symbols> | <user_durs>`` (phsort's input)
    -- and an ``O`` line -- ``O nphonetot <phonemes> | <sentstruc>`` (phsort's
    output, which is phalloph's input);
  - ``DECTALK_TIM_DUMP`` (`p_us_tim0.c`, before ``us_phtiming`` assigns durations)
    writes per clause an ``I`` line -- ``I malfem nallotot ... <allophons> |
    <allofeats> | <user_durs>`` -- whose ``allophons``/``allofeats`` are phalloph's
    output, captured at phalloph's own boundary (``phinton`` inserts further phones
    only after ``us_phtiming``).

This module drives the oracle with both dumps and pairs, per clause, phsort's
input/output and phalloph's output, for `test/test_dectalk_phalloph.py` to replay
`allophones.phsort`/`allophones.phalloph` and diff field for field against the C.
"""
from __future__ import annotations

import glob
import os
import subprocess
import tempfile
from dataclasses import dataclass

from .dump_dectalk_aloph import (
    DIC_DIR,
    GEN_LIB,
    ORACLE_BIN,
    US_LIB,
)
from .dump_dectalk_aloph import (
    parse as _parse_tim,
)


@dataclass(frozen=True)
class SortClause:
    """One captured `phsort` invocation: its input and output arrays."""

    malfem: int
    nsymbtot: int
    symbols: tuple[int, ...]
    user_durs: tuple[int, ...]
    nphonetot: int
    phonemes: tuple[int, ...]
    sentstruc: tuple[int, ...]


@dataclass(frozen=True)
class AllophoneClause:
    """One clause paired across the two dumps: phsort I/O + phalloph output."""

    malfem: int
    # phsort input
    symbols: tuple[int, ...]
    user_durs: tuple[int, ...]
    # phsort output == phalloph input
    phonemes: tuple[int, ...]
    sentstruc: tuple[int, ...]
    # phalloph output == us_phtiming input
    nallotot: int
    allophons: tuple[int, ...]
    allofeats: tuple[int, ...]


def parse_sort(path: str) -> list[SortClause]:
    """Read the `I`/`O` line pairs the instrumented `phsort` wrote."""
    clauses: list[SortClause] = []
    pending: dict | None = None
    for line in open(path):
        t = line.replace("|", " | ").split()
        if not t:
            continue
        if t[0] == "I":
            malfem = int(t[1])
            nsym = int(t[2])
            rest = t[3:]
            a = rest.index("|")
            pending = dict(
                malfem=malfem,
                nsymbtot=nsym,
                symbols=tuple(int(x) for x in rest[:a]),
                user_durs=tuple(int(x) for x in rest[a + 1:]),
            )
        elif t[0] == "O" and pending is not None:
            nph = int(t[1])
            rest = t[2:]
            a = rest.index("|")
            clauses.append(SortClause(
                nphonetot=nph,
                phonemes=tuple(int(x) for x in rest[:a]),
                sentstruc=tuple(int(x) for x in rest[a + 1:]),
                **pending,
            ))
            pending = None
    return clauses


def _link_dic(rundir: str) -> None:
    for src in glob.glob(os.path.join(DIC_DIR, "*")):
        dst = os.path.join(rundir, os.path.basename(src))
        if not os.path.exists(dst):
            os.symlink(src, dst)


def capture(speaker: int, text: str) -> list[AllophoneClause]:
    """Run the oracle for one voice/utterance; pair phsort I/O with phalloph out."""
    with tempfile.TemporaryDirectory() as rundir:
        _link_dic(rundir)
        sort_dump = os.path.join(rundir, "sort.txt")
        tim_dump = os.path.join(rundir, "tim.txt")
        env = dict(
            os.environ,
            DECTALK_DIR=rundir,
            DECTALK_SORT_DUMP=sort_dump,
            DECTALK_TIM_DUMP=tim_dump,
        )
        env["LD_LIBRARY_PATH"] = os.pathsep.join(
            [GEN_LIB, US_LIB, env.get("LD_LIBRARY_PATH", "")])
        subprocess.run(
            [ORACLE_BIN, "-s", str(speaker), "-e", "1", "-fo",
             os.path.join(rundir, "o.wav"), "-a", text],
            cwd=rundir, env=env, capture_output=True, timeout=60)
        if not (os.path.exists(sort_dump) and os.path.exists(tim_dump)):
            return []
        sort = parse_sort(sort_dump)
        tim = _parse_tim(tim_dump)
    out: list[AllophoneClause] = []
    for s, t in zip(sort, tim, strict=False):
        out.append(AllophoneClause(
            malfem=s.malfem,
            symbols=s.symbols,
            user_durs=s.user_durs,
            phonemes=s.phonemes,
            sentstruc=s.sentstruc,
            nallotot=t.nallotot,
            allophons=t.allophons_in,
            allofeats=t.allofeats,
        ))
    return out
