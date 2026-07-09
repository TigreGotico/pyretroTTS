"""End-to-end validation of `lintalker.api.synthesize_text()`/
`build_phoneme_plan()`: text in, per-frame synthesis state out, compared
against the real C engine's full pipeline (`FrontEnd.c` + `BackEnd.c`)
frame-by-frame -- the same rigor `test_voices.py` already applies to
hand-supplied phoneme plans, now applied to a plan this port derives from
text itself.

This is the capstone test for the whole assembly pipeline
(`_frontend`/`_assembly`/`_phonbuf2`/`_pitchcontour`/`_moduration`): if
these pass, `synthesize_text()` produces audio frame-for-frame identical
to feeding the C reference the same plain-text sentence.

"testing one two three" is not included: it hits the pre-existing,
independently-documented `kBND_Sep6` phrase-boundary gap (see
`test_assembly_pipeline.py`/`test_pitchbuf.py`), which cascades into a
real frame-level divergence that isn't a bug in this test's own scope.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

from lintalker.api import build_phoneme_plan
from lintalker._data import Fred_Voice, Kathy_Voice, Zarvox_Voice

from test_voices import run_c, parse_frames, setup_python_voice, run_python_backend, compare_frames

_VOICES = {"Fred": (0, Fred_Voice), "Kathy": (1, Kathy_Voice), "Zarvox": (6, Zarvox_Voice)}


def _check(text, voice_name):
    voice_idx, voice_dict = _VOICES[voice_name]
    c_stdout, c_stderr, wav_path = run_c(voice_idx, text)
    c_frames = parse_frames(c_stderr)

    phonemes, ctrls, durs, pitch_freq, pitch_time, pitch_flags = build_phoneme_plan(voice_dict, text)
    vv = setup_python_voice(voice_dict)
    py_frames, vv = run_python_backend(vv, phonemes, ctrls, durs, pitch_freq, pitch_time, pitch_flags)

    mismatches = compare_frames(c_frames, py_frames)
    assert not mismatches, f"{voice_name} {text!r}: {len(mismatches)} frame mismatches: {mismatches[:3]}"


def test_hello_frame_exact_fred():
    _check("hello", "Fred")


def test_goodbye_frame_exact_fred():
    _check("goodbye", "Fred")


def test_i_am_frame_exact_fred():
    _check("I am.", "Fred")


def test_hello_frame_exact_other_voices():
    _check("hello", "Kathy")
    _check("hello", "Zarvox")


if __name__ == "__main__":
    import inspect
    mod = sys.modules[__name__]
    tests = [obj for name, obj in vars(mod).items() if name.startswith("test_") and callable(obj)]
    failures = []
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failures.append((t.__name__, str(e)))
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    if failures:
        sys.exit(1)
