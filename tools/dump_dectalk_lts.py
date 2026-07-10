"""Capture the DECtalk US text front end's output (the phoneme+stress stream).

The genuine `lts/` -> `cmd/` -> `ph/` front end turns written text and `[: ]`
markup into a phoneme+stress stream. The oracle exposes that stream directly
through `[:log phonemes on]` / `TextToSpeechOpenLogFile(h, path, LOG_PHONEMES)`
(`ph/phlog.c`), which prints, per phoneme, the `us_<ARPABET>` name plus the
stress and boundary marks -- exactly the alphabet `pyretrotts/dectalk/lts.py`
models. This tool drives the built oracle library through a tiny C harness and
records that text per input, forming the real-capture golden the port is
diffed against. No source instrumentation is needed.

Because letter-to-sound is voice-independent (the voice only affects the
synthesizer below the phoneme stream), one capture per input string suffices;
the harness runs the default voice.

The captured text descends from FONIX-proprietary dictionaries and rules; the
emitted golden is therefore not covered by this project's MIT licence (see
NOTICE).

Usage:
    python3 tools/dump_dectalk_lts.py [--dist DIR] [--out FILE]

`--dist` is the built oracle `dist/` directory (holding `lib/` and `dic/`).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile

DEFAULT_DIST = os.path.expanduser("~/AgentWorkspaces/ovos/dectalk-c/dist")
DEFAULT_OUT = os.path.join(
    os.path.dirname(__file__), "..", "test", "dectalk_lts_golden.json")

HARNESS_C = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dtk/ttsapi.h>
#ifndef WAVE_MAPPER
#define WAVE_MAPPER ((UINT)-1)
#endif
int main(int argc, char **argv) {
    LPTTS_HANDLE_T h = NULL;
    unsigned int lang = TextToSpeechStartLang("us");
    if (lang & TTS_LANG_ERROR) { fprintf(stderr, "lang err %x\n", lang); return 2; }
    TextToSpeechSelectLang(NULL, lang);
    if (TextToSpeechStartup(&h, WAVE_MAPPER, DO_NOT_USE_AUDIO_DEVICE, NULL, (long)NULL)
        != MMSYSERR_NOERROR) { fprintf(stderr, "startup fail\n"); return 3; }
    if (TextToSpeechOpenLogFile(h, (char *)argv[1], LOG_PHONEMES) != MMSYSERR_NOERROR) {
        fprintf(stderr, "openlog fail\n"); return 4; }
    TextToSpeechSpeak(h, (char *)argv[2], TTS_FORCE);
    TextToSpeechSync(h);
    TextToSpeechCloseLogFile(h);
    TextToSpeechShutdown(h);
    return 0;
}
"""

# Fixed input set covering the categories the front end must handle.
TEXT_SET: dict[str, list[str]] = {
    "dictionary": [
        "cat", "hello world", "computer", "the quick brown fox",
        "dog", "house", "water", "people",
    ],
    "rules_ood": [
        "abcdefg", "zorph", "blornt", "quizzle",
    ],
    "numbers": [
        "123", "42 dogs", "one hundred", "3.14",
    ],
    "abbreviations": [
        "Dr. Smith lives on Main St.", "Mr. Jones", "etc.",
    ],
    "homographs": [
        "read", "I read the book", "wind", "the wind blows",
    ],
    "commands": [
        "[:rate 200]testing", "[:nb]hello", "[:np]hello",
    ],
}


def build_harness(dist: str, workdir: str) -> str:
    src = os.path.join(workdir, "harness.c")
    exe = os.path.join(workdir, "harness")
    with open(src, "w") as f:
        f.write(HARNESS_C)
    subprocess.run(
        ["gcc", src, "-I", os.path.join(dist, "include"),
         "-L", os.path.join(dist, "lib"), "-ltts", "-o", exe],
        check=True)
    return exe


def capture(exe: str, dist: str, text: str) -> str:
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = os.path.join(dist, "lib")
    env["DECTALK_DIR"] = dist
    with tempfile.NamedTemporaryFile("r", suffix=".log", delete=False) as tf:
        logpath = tf.name
    try:
        subprocess.run([exe, logpath, text], env=env, check=True, cwd=dist,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(logpath) as f:
            return f.read()
    finally:
        os.unlink(logpath)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", default=DEFAULT_DIST)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as workdir:
        exe = build_harness(args.dist, workdir)
        golden: dict[str, dict[str, str]] = {}
        for category, texts in TEXT_SET.items():
            golden[category] = {t: capture(exe, args.dist, t) for t in texts}

    with open(args.out, "w") as f:
        json.dump(golden, f, indent=2, ensure_ascii=False)
        f.write("\n")
    total = sum(len(v) for v in golden.values())
    print(f"wrote {total} captures across {len(golden)} categories to {args.out}")


if __name__ == "__main__":
    main()
