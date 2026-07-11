"""Capture the UK (or any non-US) DECtalk oracle: raw phoneme stream + PCM.

The stock `say` binary refuses `-l <lang>` unless its `TextToSpeechEnumLangs`
reports `MultiLang` (`samplosf/src/dtsamples/say.c:491`), which the Linux build
does not, so this drives the multilanguage API directly through the tiny
`tools/uksay.c` harness: it calls `TextToSpeechStartLang(lang)` (which dlopens
`libtts_<lang>.so`, `dtalk_ml.c:379`), `TextToSpeechStartupEx`, and renders one
utterance to a WAV file.

The raw pre-`ph/` phoneme+stress stream is captured from the `DECTALK_LTS_DUMP`
instrumentation of `ls_util_send_phone` (`lts/ls_util.c`), which writes each raw
`ph` code (index < 100, prosody >= 100) one per line -- the boundary the task
targets, not the reduction-polluted `LOG_PHONEMES`.

This mirrors `tools/dump_dectalk_phonemes.py` but for a chosen language. The
per-language libraries and dictionaries live under the built oracle tree
(`~/AgentWorkspaces/ovos/dectalk-c`). Guaranteed identical to the compiled
reference: it runs the real library.
"""
from __future__ import annotations

import glob
import os
import struct
import subprocess
import tempfile
from dataclasses import dataclass

_DTK = os.path.expanduser("~/AgentWorkspaces/ovos/dectalk-c/src")
_HARNESS_SRC = os.path.join(os.path.dirname(__file__), "uksay.c")
_HARNESS_BIN = os.path.join(tempfile.gettempdir(), "pyretrotts_uksay")


def _first(pattern: str) -> str:
    hits = sorted(glob.glob(pattern))
    return hits[0] if hits else ""


def _paths(lang: str) -> tuple[str, str, str]:
    gen = os.environ.get("DECTALK_GEN_LIB", _first(f"{_DTK}/dtalkml/build/*/us/release"))
    lib = _first(f"{_DTK}/dapi/build/dectalk/*/{lang}/release")
    dic = _first(f"{_DTK}/dapi/build/dic/*/{lang}/release")
    return gen, lib, dic


def build_harness() -> str | None:
    """Compile `uksay.c` against the generic multilanguage library; cache it."""
    gen, _lib, _dic = _paths("us")
    inc = _first(f"{_DTK}/dapi/build/dectalk/*/us/release/include/dtk")
    if not (gen and inc and os.path.exists(_HARNESS_SRC)):
        return None
    if not os.path.exists(_HARNESS_BIN):
        rc = subprocess.run(
            ["gcc", "-o", _HARNESS_BIN, _HARNESS_SRC, "-I", inc,
             "-L", gen, "-ltts", f"-Wl,-rpath,{gen}"],
            capture_output=True)
        if rc.returncode != 0 or not os.path.exists(_HARNESS_BIN):
            return None
    return _HARNESS_BIN


@dataclass(frozen=True)
class UkCapture:
    """One UK/lang utterance: raw pre-`ph/` phoneme+stress codes and the PCM."""

    codes: tuple[int, ...]
    pcm: tuple[int, ...]


def _wav_pcm(path: str) -> tuple[int, ...]:
    data = open(path, "rb").read()
    i = data.find(b"data")
    n = struct.unpack("<I", data[i + 4:i + 8])[0]
    return tuple(struct.unpack(f"<{n // 2}h", data[i + 8:i + 8 + n]))


def capture(lang: str, speaker: int, text: str) -> UkCapture | None:
    """Run the oracle for one lang/voice/utterance; raw codes + PCM, or None."""
    harness = build_harness()
    gen, lib, dic = _paths(lang)
    if not (harness and gen and lib and dic):
        return None
    with tempfile.TemporaryDirectory() as rundir:
        for src in glob.glob(os.path.join(dic, "*")):
            dst = os.path.join(rundir, os.path.basename(src))
            if not os.path.exists(dst):
                os.symlink(src, dst)
        lts_dump = os.path.join(rundir, "lts.txt")
        wav = os.path.join(rundir, "o.wav")
        env = dict(os.environ, DECTALK_DIR=rundir, DECTALK_LTS_DUMP=lts_dump)
        env["LD_LIBRARY_PATH"] = os.pathsep.join(
            [gen, lib, env.get("LD_LIBRARY_PATH", "")])
        subprocess.run(
            [harness, lang, str(speaker), wav, text],
            cwd=rundir, env=env, capture_output=True, timeout=60)
        if not (os.path.exists(lts_dump) and os.path.exists(wav)):
            return None
        codes = tuple(
            int(line) for line in open(lts_dump).read().split() if line.strip())
        return UkCapture(codes=codes, pcm=_wav_pcm(wav))
