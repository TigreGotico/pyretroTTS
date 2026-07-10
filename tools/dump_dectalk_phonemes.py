"""Capture the input to `phclause` (the `lts/`/`cmd/` output) from the oracle.

`phclause` (`ph_claus.c:200`) receives, per clause, a `symbols[]` phoneme +
stress + sentence-structure stream and an optional `user_durs[]`. The
`DECTALK_SORT_DUMP` instrumentation point (`ph_claus.c`, right after `phsort`,
gated on the env var and kept out of the read-only checkout) writes that input as
the `I` line `I malfem nsymbtot <symbols> | <user_durs>`, one per clause.

This module drives the oracle once per voice/utterance and returns, paired: the
per-clause `symbols`/`user_durs`/`malfem` (the whole `phclause` input, split into
clauses as the front end splits it) and the oracle's output WAV PCM for the whole
utterance. `test/test_dectalk_phoneme_pcm.py` replays `phclause.speak_phonemes`
over the symbols and diffs the PCM sample for sample.
"""
from __future__ import annotations

import glob
import os
import struct
import subprocess
import tempfile
from dataclasses import dataclass

from .dump_dectalk_phalloph import (
    DIC_DIR,
    GEN_LIB,
    ORACLE_BIN,
    US_LIB,
    parse_sort,
)


@dataclass(frozen=True)
class PhonemeClause:
    """One clause's `phclause` input (the `symbols`/`user_durs` stream)."""

    malfem: int
    symbols: tuple[int, ...]
    user_durs: tuple[int, ...]


@dataclass(frozen=True)
class Utterance:
    """One voice/utterance: its clauses' input streams plus the oracle PCM."""

    clauses: tuple[PhonemeClause, ...]
    pcm: tuple[int, ...]


def _wav_pcm(path: str) -> tuple[int, ...]:
    data = open(path, "rb").read()
    i = data.find(b"data")
    n = struct.unpack("<I", data[i + 4:i + 8])[0]
    return tuple(struct.unpack(f"<{n // 2}h", data[i + 8:i + 8 + n]))


def capture(speaker: int, text: str) -> Utterance | None:
    """Run the oracle for one voice/utterance; return its clauses + PCM."""
    with tempfile.TemporaryDirectory() as rundir:
        for src in glob.glob(os.path.join(DIC_DIR, "*")):
            dst = os.path.join(rundir, os.path.basename(src))
            if not os.path.exists(dst):
                os.symlink(src, dst)
        sort_dump = os.path.join(rundir, "sort.txt")
        wav = os.path.join(rundir, "o.wav")
        env = dict(os.environ, DECTALK_DIR=rundir, DECTALK_SORT_DUMP=sort_dump)
        env["LD_LIBRARY_PATH"] = os.pathsep.join(
            [GEN_LIB, US_LIB, env.get("LD_LIBRARY_PATH", "")])
        subprocess.run(
            [ORACLE_BIN, "-s", str(speaker), "-e", "1", "-fo", wav, "-a", text],
            cwd=rundir, env=env, capture_output=True, timeout=60)
        if not (os.path.exists(sort_dump) and os.path.exists(wav)):
            return None
        clauses = tuple(
            PhonemeClause(malfem=s.malfem, symbols=s.symbols, user_durs=s.user_durs)
            for s in parse_sort(sort_dump))
        return Utterance(clauses=clauses, pcm=_wav_pcm(wav))
