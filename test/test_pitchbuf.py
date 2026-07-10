"""Tests for `pylintalker._pitchbuf` (`store_f0_and_time`, `fill_pitch_buf`),
the port of `Fill_Pitch_Buf`/`Store_F0_and_Time` (`BackEnd.c:337-671`).

Validated directly against the C reference's pitch buffer dump (the `N`
lines in `test_harness`'s output, parsed by `test_voices.parse_sentence_plan`
into `pitch_freq`/`pitch_time`/`pitch_flags`).

Pipeline call order (matching `ParseSentence`):
`Fill_Phon_Buf_2 -> Pitch_RaiseAndFall -> Mod_Duration ->
Insert_Closure_Release -> Calc_Ramp_Steps -> Fill_Pitch_Buf`. Also:
`vv.end_Punctuation` must be copied from `SentenceAssembly.end_punctuation`
before calling `pitch_raise_and_fall`/`fill_pitch_buf` (neither
`_assembly.py` nor `_phonbuf2.py` write it to `vv` themselves).

"testing one two three" is deliberately NOT tested here: it hits the
pre-existing, independently-documented `kBND_Sep6` phrase-boundary gap
(see `test_assembly_pipeline.py`), and that missing boundary marker
changes when a `kPhraseReset` pitch event fires, cascading into a real
pitch-buffer length/value mismatch that isn't a bug in this module -- it's
the same root cause, just visible one stage further downstream. "hello",
"goodbye", and "I am." don't exercise that gap and are fully bit-exact.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

from test_voices import parse_sentence_plan, run_c

from pylintalker._assembly import collect_fe_tokens
from pylintalker._backend import calc_ramp_steps
from pylintalker._data import Fred_Voice, Junior_Voice, Kathy_Voice, Zarvox_Voice
from pylintalker._moduration import mod_duration
from pylintalker._phonbuf2 import fill_phon_buf_2, insert_closure_release
from pylintalker._pitchbuf import fill_pitch_buf
from pylintalker._pitchcontour import pitch_raise_and_fall
from pylintalker.api import new_voice

_VOICES = {"Fred": Fred_Voice, "Kathy": Kathy_Voice, "Junior": Junior_Voice, "Zarvox": Zarvox_Voice}
_VOICE_IDX = {"Fred": 0, "Kathy": 1, "Junior": 3, "Zarvox": 6}


def _run_python(text, voice_name="Fred"):
    sa = collect_fe_tokens(text)
    vv = new_voice(_VOICES[voice_name])
    fill_phon_buf_2(vv, sa)
    vv.end_Punctuation = sa.end_punctuation
    pitch_raise_and_fall(vv)
    mod_duration(vv)
    insert_closure_release(vv)
    calc_ramp_steps(vv)
    fill_pitch_buf(vv)
    n = vv.pitchBuf_In_Index
    return vv.pitch_Buf_Freq[:n], vv.pitch_Buf_Time[:n], vv.pitch_Buf_Flags[:n]


def _run_c_pitch(voice_idx, text):
    c_stdout, c_stderr, wav = run_c(voice_idx, text)
    _, _, _, freq, time, flags = parse_sentence_plan(c_stdout)
    return freq, time, flags


def test_hello_pitch_buf_bit_exact():
    py = _run_python("hello")
    c = _run_c_pitch(0, "hello")
    assert py == c


def test_goodbye_pitch_buf_bit_exact():
    py = _run_python("goodbye")
    c = _run_c_pitch(0, "goodbye")
    assert py == c


def test_i_am_pitch_buf_bit_exact():
    py = _run_python("I am.")
    c = _run_c_pitch(0, "I am.")
    assert py == c


def test_pitch_buf_matches_across_voices():
    for voice_name in ("Kathy", "Junior", "Zarvox"):
        for text in ("hello", "goodbye", "I am."):
            py = _run_python(text, voice_name)
            c = _run_c_pitch(_VOICE_IDX[voice_name], text)
            assert py == c, f"{voice_name} {text!r} pitch buf mismatch"


if __name__ == "__main__":
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
