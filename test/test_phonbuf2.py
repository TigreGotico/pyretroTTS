"""Tests for `lintalker._phonbuf2` (`fill_phon_buf_2`, `insert_closure_release`)
and `lintalker._moduration.mod_duration`.

Validated directly against the C reference via `test_voices.py`'s existing
`run_c()`/`parse_sentence_plan()` helpers -- unlike `_assembly.py`'s
`Collect_FE_Tokens` stage, this stage's output (`phon_Buf_2`/
`phon_Ctrl_Buf_2`/`dur_Buf`) IS exposed by the standard `test_harness` (its
`S`/`P`/`N` dump), so no throwaway C instrumentation is needed here.

Call order matters: `mod_duration()` must run BEFORE
`insert_closure_release()` (matching `ParseSentence`'s real order) -- see
`_phonbuf2.py`'s module docstring for why the reverse order silently
diverges.

One remaining class of expected residual difference, from a pipeline stage
that runs AFTER these and is not yet ported (see docs/architecture.md):
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
from lintalker._moduration import mod_duration
from lintalker.api import new_voice
from lintalker._data import Fred_Voice, Kathy_Voice, Junior_Voice, Zarvox_Voice

from test_voices import run_c, parse_sentence_plan

_KPITCHFALL = 0x40
_KPITCHRISE = 0x20
_KBND_SEP6 = 0xC00000

_VOICES = {"Fred": Fred_Voice, "Kathy": Kathy_Voice, "Junior": Junior_Voice, "Zarvox": Zarvox_Voice}
_VOICE_IDX = {"Fred": 0, "Kathy": 1, "Junior": 3, "Zarvox": 6}


def _run_python(text, voice_name="Fred"):
    sa = collect_fe_tokens(text)
    vv = new_voice(_VOICES[voice_name])
    fill_phon_buf_2(vv, sa)
    mod_duration(vv)
    insert_closure_release(vv)
    n = vv.phonBuf_2_In_Index
    return vv.phon_Buf_2[:n], vv.phon_Ctrl_Buf_2[:n], vv.dur_Buf[:n]


def _run_c_plan(voice_idx, text):
    c_stdout, c_stderr, wav = run_c(voice_idx, text)
    phon, ctrl, dur, *_ = parse_sentence_plan(c_stdout)
    return phon, ctrl, dur


def test_hello_phon_ctrl_dur_match_modulo_pitch():
    py_phon, py_ctrl, py_dur = _run_python("hello")
    c_phon, c_ctrl, c_dur = _run_c_plan(0, "hello")
    assert py_phon == c_phon
    assert py_dur == c_dur
    masked = [c & ~(_KPITCHFALL | _KPITCHRISE) for c in c_ctrl]
    assert py_ctrl == masked


def test_goodbye_phon_ctrl_dur_match_modulo_pitch():
    py_phon, py_ctrl, py_dur = _run_python("goodbye")
    c_phon, c_ctrl, c_dur = _run_c_plan(0, "goodbye")
    assert py_phon == c_phon
    assert py_dur == c_dur
    masked = [c & ~(_KPITCHFALL | _KPITCHRISE) for c in c_ctrl]
    assert py_ctrl == masked


def test_testing_one_two_three_matches_modulo_known_gaps():
    py_phon, py_ctrl, py_dur = _run_python("testing one two three")
    c_phon, c_ctrl, c_dur = _run_c_plan(0, "testing one two three")
    assert py_phon == c_phon
    assert py_dur == c_dur
    masked = [c & ~(_KPITCHFALL | _KPITCHRISE | _KBND_SEP6) for c in c_ctrl]
    assert py_ctrl == masked


def test_i_am_release_phoneme_and_duration_match():
    """"I am." ends in a nasal (_m_) before word-final silence, so
    insert_closure_release() inserts a release phoneme (_IX_/_AX_) with a
    hardcoded duration -- verified bit-exact against the C reference,
    including phonemes, durations (specifically the shifted/inserted
    duration slots), and ctrl flags (kPlosive_Release)."""
    py_phon, py_ctrl, py_dur = _run_python("I am.")
    c_phon, c_ctrl, c_dur = _run_c_plan(0, "I am.")
    assert py_phon == c_phon
    assert py_dur == c_dur
    masked = [c & ~(_KPITCHFALL | _KPITCHRISE) for c in c_ctrl]
    assert py_ctrl == masked


def test_matches_across_voices():
    """Same four sentences, three more voices (Kathy/Junior/Zarvox) --
    phonemes and durations only (ctrl already covered above)."""
    texts = ["hello", "goodbye", "testing one two three", "I am."]
    for voice_name in ("Kathy", "Junior", "Zarvox"):
        for text in texts:
            py_phon, _, py_dur = _run_python(text, voice_name)
            c_phon, _, c_dur = _run_c_plan(_VOICE_IDX[voice_name], text)
            assert py_phon == c_phon, f"{voice_name} {text!r} phon mismatch"
            assert py_dur == c_dur, f"{voice_name} {text!r} dur mismatch"


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
