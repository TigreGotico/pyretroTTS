"""Tests for `lintalker._phonbuf2` -- `fill_phon_buf_2`
(`BackEnd.c:2469-3067`) and `insert_closure_release` (`formantSynth.c`,
the body of `synth_AdjustPhons2`).

Validated directly against the C reference via `test_voices.py`'s existing
`run_c()`/`parse_sentence_plan()` helpers -- unlike `_assembly.py`'s
`Collect_FE_Tokens` stage, this stage's output (`phon_Buf_2`/
`phon_Ctrl_Buf_2`) IS exposed by the standard `test_harness` (its `S`/`P`/
`N` dump), so no throwaway C instrumentation is needed here.

One remaining class of expected residual difference, from a pipeline stage
that runs AFTER this one and is not yet ported (see docs/architecture.md):
`kPitchRise`/`kPitchFall` (0x20/0x40) ctrl-bit additions at stressed
vowels, from `Pitch_RaiseAndFall`. The pre-existing `kBND_Sep6`
phrase-boundary gap (documented in test_assembly.py) also still applies
where relevant.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

from lintalker._assembly import collect_fe_tokens
from lintalker._phonbuf2 import fill_phon_buf_2, insert_closure_release
from lintalker.api import new_voice
from lintalker._data import Fred_Voice

from test_voices import run_c, parse_sentence_plan

_KPITCHFALL = 0x40
_KPITCHRISE = 0x20
_KBND_SEP6 = 0xC00000


def _run_python(text, voice_dict=Fred_Voice):
    sa = collect_fe_tokens(text)
    vv = new_voice(voice_dict)
    fill_phon_buf_2(vv, sa)
    insert_closure_release(vv)
    n = vv.phonBuf_2_In_Index
    return vv.phon_Buf_2[:n], vv.phon_Ctrl_Buf_2[:n]


def _run_c_plan(voice_idx, text):
    c_stdout, c_stderr, wav = run_c(voice_idx, text)
    phon, ctrl, dur, *_ = parse_sentence_plan(c_stdout)
    return phon, ctrl


def test_hello_phonemes_and_ctrl_match_modulo_pitch_fall():
    py_phon, py_ctrl = _run_python("hello")
    c_phon, c_ctrl = _run_c_plan(0, "hello")
    assert py_phon == c_phon
    masked = [c & ~(_KPITCHFALL | _KPITCHRISE) for c in c_ctrl]
    assert py_ctrl == masked


def test_goodbye_phonemes_and_ctrl_match_modulo_pitch_fall():
    py_phon, py_ctrl = _run_python("goodbye")
    c_phon, c_ctrl = _run_c_plan(0, "goodbye")
    assert py_phon == c_phon
    masked = [c & ~(_KPITCHFALL | _KPITCHRISE) for c in c_ctrl]
    assert py_ctrl == masked


def test_testing_one_two_three_matches_modulo_known_gaps():
    py_phon, py_ctrl = _run_python("testing one two three")
    c_phon, c_ctrl = _run_c_plan(0, "testing one two three")
    assert py_phon == c_phon
    masked = [c & ~(_KPITCHFALL | _KPITCHRISE | _KBND_SEP6) for c in c_ctrl]
    assert py_ctrl == masked


def test_i_am_release_phoneme_matches():
    """"I am." ends in a nasal (_m_) before word-final silence, so
    insert_closure_release() inserts a release phoneme (_IX_/_AX_) --
    verified bit-exact against the C reference, including its ctrl flags
    (kPlosive_Release)."""
    py_phon, py_ctrl = _run_python("I am.")
    c_phon, c_ctrl = _run_c_plan(0, "I am.")
    assert py_phon == c_phon
    masked = [c & ~(_KPITCHFALL | _KPITCHRISE) for c in c_ctrl]
    assert py_ctrl == masked


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
