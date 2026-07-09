"""Tests for the `BackEnd.c` assembly pipeline that turns `_assembly.py`'s
`phon_Buf_1`/`phon_Ctrl_Buf_1` into a full `phon_Buf_2`/`phon_Ctrl_Buf_2`/
`dur_Buf` synthesizable plan: `_phonbuf2.fill_phon_buf_2`,
`_pitchcontour.pitch_raise_and_fall`, `_moduration.mod_duration`,
`_phonbuf2.insert_closure_release`, called in that order -- matching the
real `ParseSentence`'s `Fill_Phon_Buf_2 -> Pitch_RaiseAndFall ->
Mod_Duration -> synth_AdjustPhons2` order. Call order matters: running
`mod_duration()`/`insert_closure_release()` out of order was confirmed to
silently diverge from the C reference (see `_phonbuf2.py`'s module
docstring).

Validated directly against the C reference via `test_voices.py`'s existing
`run_c()`/`parse_sentence_plan()` helpers -- unlike `_assembly.py`'s
`Collect_FE_Tokens` stage, this pipeline's output (`phon_Buf_2`/
`phon_Ctrl_Buf_2`/`dur_Buf`) IS exposed by the standard `test_harness`, so
no throwaway C instrumentation is needed here.

With all four stages wired in this order, phonemes/ctrl/durations are
bit-exact against the C reference with NO masking needed, across 4 voices
and 4 sentences, including the non-punctuation `kBND_Sep6` phrase-boundary
marker on certain dictionary-tagged words (e.g. "ONE") -- `_assembly.py`'s
`collect_fe_tokens` approximates Morph.c's SEP6 rule (content-word ->
function-word POS transition) with a fixed Noun/Verb/Adj/Adv check.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

from lintalker._assembly import collect_fe_tokens
from lintalker._phonbuf2 import fill_phon_buf_2, insert_closure_release
from lintalker._pitchcontour import pitch_raise_and_fall
from lintalker._moduration import mod_duration
from lintalker.api import new_voice
from lintalker._data import Fred_Voice, Kathy_Voice, Junior_Voice, Zarvox_Voice

from test_voices import run_c, parse_sentence_plan

_VOICES = {"Fred": Fred_Voice, "Kathy": Kathy_Voice, "Junior": Junior_Voice, "Zarvox": Zarvox_Voice}
_VOICE_IDX = {"Fred": 0, "Kathy": 1, "Junior": 3, "Zarvox": 6}


def _run_python(text, voice_name="Fred"):
    sa = collect_fe_tokens(text)
    vv = new_voice(_VOICES[voice_name])
    fill_phon_buf_2(vv, sa)
    pitch_raise_and_fall(vv)
    mod_duration(vv)
    insert_closure_release(vv)
    n = vv.phonBuf_2_In_Index
    return vv.phon_Buf_2[:n], vv.phon_Ctrl_Buf_2[:n], vv.dur_Buf[:n]


def _run_c_plan(voice_idx, text):
    c_stdout, c_stderr, wav = run_c(voice_idx, text)
    phon, ctrl, dur, *_ = parse_sentence_plan(c_stdout)
    return phon, ctrl, dur


def test_hello_fully_bit_exact():
    py_phon, py_ctrl, py_dur = _run_python("hello")
    c_phon, c_ctrl, c_dur = _run_c_plan(0, "hello")
    assert py_phon == c_phon
    assert py_ctrl == c_ctrl
    assert py_dur == c_dur


def test_goodbye_fully_bit_exact():
    py_phon, py_ctrl, py_dur = _run_python("goodbye")
    c_phon, c_ctrl, c_dur = _run_c_plan(0, "goodbye")
    assert py_phon == c_phon
    assert py_ctrl == c_ctrl
    assert py_dur == c_dur


def test_i_am_fully_bit_exact():
    """Exercises insert_closure_release's inserted release phoneme
    (_IX_/_AX_ before word-final silence after nasal _m_)."""
    py_phon, py_ctrl, py_dur = _run_python("I am.")
    c_phon, c_ctrl, c_dur = _run_c_plan(0, "I am.")
    assert py_phon == c_phon
    assert py_ctrl == c_ctrl
    assert py_dur == c_dur


def test_testing_one_two_three_fully_bit_exact():
    """Index 7 ("ONE", dictionary-tagged kAdj) carries a kBND_Sep6
    phrase-boundary marker (see test_assembly.py's oracle test)."""
    py_phon, py_ctrl, py_dur = _run_python("testing one two three")
    c_phon, c_ctrl, c_dur = _run_c_plan(0, "testing one two three")
    assert py_phon == c_phon
    assert py_dur == c_dur
    assert py_ctrl == c_ctrl


def test_matches_across_voices():
    """Same four sentences, three more voices (Kathy/Junior/Zarvox)."""
    texts = ["hello", "goodbye", "testing one two three", "I am."]
    for voice_name in ("Kathy", "Junior", "Zarvox"):
        for text in texts:
            py_phon, py_ctrl, py_dur = _run_python(text, voice_name)
            c_phon, c_ctrl, c_dur = _run_c_plan(_VOICE_IDX[voice_name], text)
            assert py_phon == c_phon, f"{voice_name} {text!r} phon mismatch"
            assert py_dur == c_dur, f"{voice_name} {text!r} dur mismatch"
            assert py_ctrl == c_ctrl, f"{voice_name} {text!r} ctrl mismatch"


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
