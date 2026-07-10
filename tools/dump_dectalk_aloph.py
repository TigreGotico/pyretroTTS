"""Capture the `ph/` allophone/duration stage boundary from the DECtalk oracle.

The instrumented `us_phtiming` (`p_us_tim0.c`, gated on `DECTALK_TIM_DUMP`)
writes two lines per clause:

  - ``I malfem nallotot sprat0 sprat1 sprat2 timeref <allophons> | <allofeats> |
    <user_durs>`` -- the stage input: the allophone/feature stream `phalloph`
    produced (before `us_phtiming` assigns durations) plus the speaking-rate
    factors `init_timing` resolved;
  - ``O nallotot <allodurs> | <allophons>`` -- the stage output: the per-phone
    durations in 6.4 ms frames and the (possibly mutated) allophone stream.

`allofeats` is dumped with two trailing padding entries (`nallotot + 2`), matching
what `us_phtiming` may read at the stream end.

This module both drives the oracle (`capture`) and parses its dump (`parse`), for
`test/test_dectalk_aloph.py` to replay `timing.us_phtiming` over the captured
input and diff its `allodurs`/allophone output against the C.
"""
from __future__ import annotations

import glob
import os
import subprocess
import tempfile
from dataclasses import dataclass

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
class TimingClause:
    """One captured `us_phtiming` invocation (its input and output)."""

    malfem: int
    nallotot: int
    sprat0: int
    sprat1: int
    sprat2: int
    timeref: int
    sprate: int
    allophons_in: tuple[int, ...]
    allofeats: tuple[int, ...]
    user_durs: tuple[int, ...]
    allodurs: tuple[int, ...]
    allophons_out: tuple[int, ...]


def parse(path: str) -> list[TimingClause]:
    """Read the `I`/`O` line pairs the instrumented `us_phtiming` wrote."""
    clauses: list[TimingClause] = []
    pending: dict | None = None
    for line in open(path):
        t = line.split()
        if not t:
            continue
        if t[0] == "I":
            head = [int(x) for x in t[1:8]]
            rest = t[8:]
            a = rest.index("|")
            b = rest.index("|", a + 1)
            pending = dict(
                malfem=head[0], nallotot=head[1], sprat0=head[2], sprat1=head[3],
                sprat2=head[4], timeref=head[5], sprate=head[6],
                allophons_in=tuple(int(x) for x in rest[:a]),
                allofeats=tuple(int(x) for x in rest[a + 1:b]),
                user_durs=tuple(int(x) for x in rest[b + 1:]),
            )
        elif t[0] == "O" and pending is not None:
            rest = t[2:]
            a = rest.index("|")
            clauses.append(TimingClause(
                allodurs=tuple(int(x) for x in rest[:a]),
                allophons_out=tuple(int(x) for x in rest[a + 1:]),
                **pending,
            ))
            pending = None
    return clauses


def capture(speaker: int, text: str) -> list[TimingClause]:
    """Run the oracle for one voice/utterance and return its timing clauses."""
    with tempfile.TemporaryDirectory() as rundir:
        for src in glob.glob(os.path.join(DIC_DIR, "*")):
            dst = os.path.join(rundir, os.path.basename(src))
            if not os.path.exists(dst):
                os.symlink(src, dst)
        dump = os.path.join(rundir, "tim.txt")
        env = dict(os.environ, DECTALK_DIR=rundir, DECTALK_TIM_DUMP=dump)
        env["LD_LIBRARY_PATH"] = os.pathsep.join(
            [GEN_LIB, US_LIB, env.get("LD_LIBRARY_PATH", "")])
        subprocess.run(
            [ORACLE_BIN, "-s", str(speaker), "-e", "1", "-fo",
             os.path.join(rundir, "o.wav"), "-a", text],
            cwd=rundir, env=env, capture_output=True, timeout=60)
        return parse(dump) if os.path.exists(dump) else []
