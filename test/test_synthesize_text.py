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

IMPORTANT HISTORY -- read before trusting a green run of this file: this
module previously called `parse_frames(c_stderr)` instead of
`parse_frames(c_stdout)` (`parse_frames` reads the harness's `F `-prefixed
stdout lines; stderr never contains them). That made `c_frames` always
empty, so `compare_frames(c_frames, py_frames)` -- which zips the two
lists together -- iterated zero times and reported "no mismatches"
regardless of what `py_frames` actually contained. Every test in this file
was a false positive until this was caught (by a human noticing
`synthesize_text()`'s actual audio output sounded wrong for several
voices, despite this suite reporting all green). Once fixed, running the
real comparison across all 17 voices with a genuine two-word sentence
("hello world" -- the single-word sentences used until then never
exercised a second stress event) immediately surfaced a real, unrelated
bug: `VP_stressGain` was missing a percent-to-16.16-fixed-point scale
(`(stressGain << 16) / 100`, confirmed against `Say.c:1289-1290`) that
every other percent-style voice parameter already has, corrupting the
primary/emphatic stress pitch bump for every voice whenever a stressed
vowel wasn't also at a sentence/clause boundary (which the single-word
test sentences always were, by construction, masking the bug). Both bugs
are now fixed; this file's assertions are real. Moral: an empty expected
list satisfying `all()`/`zip()`-based comparisons silently is a classic
trap -- assert on `len(c_frames) > 0` (or an exact length match) whenever
a test's "expected" data comes from parsing external output, not just
absence of mismatches.

Bells/Hysterical are excluded from the all-voices sweep below: they hit
the pre-existing, independently-documented `kUseSyncSnd` external
sample-marker gap (see docs/architecture.md), which shows up here as a
genuine frame-COUNT mismatch, not just value differences.

TWO FURTHER REAL BUGS found via a broader multi-sentence sweep (a user
report that several voices "still sound like shit" on ordinary sentences,
despite this file being green): (1) `build_phoneme_plan`'s internal
`VoiceVar` computed `end_Punctuation` correctly before running its own
`Calc_Ramp_Steps`, but that value was never passed to the SEPARATE
`VoiceVar` `synthesize_phonemes`/`run_python_backend` use for the actual
synthesis pass, which re-ran `Calc_Ramp_Steps` from scratch with
`end_Punctuation` still 0 -- silently doubling the pitch decline rate
(`Calc_Ramp_Steps` halves it for `_Comma_`/`_Quest_`, `BackEnd.c:715-716`)
for every comma-containing or yes/no-question sentence, on every voice.
Fixed by making `build_phoneme_plan` return `end_punctuation` as a 7th
value and threading it through. (2) `_assembly.collect_fe_tokens` didn't
model ANY non-punctuation phrase boundary (the pre-existing, narrower
`kBND_Sep6` gap on "ONE" turned out to be the SAME missing mechanism, just
first observed on a single word) -- a missing `kPhraseReset` pitch-buffer
entry mid-sentence silently made `down_Ramp_Offset` (hence `f0`) drift for
the rest of the sentence on ordinary prose like "the quick brown fox jumps
over the lazy dog." Fixed with a Morph.c `PlacePhrasing` SEP6
approximation (content-word -> function-word POS transition) -- see
`_assembly.py`'s docstring at that code and docs/architecture.md.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

from lintalker.api import build_phoneme_plan
from lintalker._frontend import split_clauses
from lintalker._data import (
    Fred_Voice, Kathy_Voice, Princess_Voice, Junior_Voice, Ralph_Voice,
    Whisper_Voice, Zarvox_Voice, Trinoids_Voice, Bubbles_Voice, Boing_Voice,
    Deranged_Voice, GoodNews_Voice, BadNews_Voice, PipeOrgan_Voice, Cellos_Voice,
)

from test_voices import run_c, parse_frames, setup_python_voice, run_python_backend, compare_frames

_VOICES = {
    "Fred": (0, Fred_Voice), "Kathy": (1, Kathy_Voice), "Princess": (2, Princess_Voice),
    "Junior": (3, Junior_Voice), "Ralph": (4, Ralph_Voice), "Whisper": (5, Whisper_Voice),
    "Zarvox": (6, Zarvox_Voice), "Trinoids": (7, Trinoids_Voice), "Bubbles": (8, Bubbles_Voice),
    "Boing": (9, Boing_Voice), "Deranged": (12, Deranged_Voice), "GoodNews": (13, GoodNews_Voice),
    "BadNews": (14, BadNews_Voice), "PipeOrgan": (15, PipeOrgan_Voice), "Cellos": (16, Cellos_Voice),
}


def _check(text, voice_name):
    voice_idx, voice_dict = _VOICES[voice_name]
    c_stdout, c_stderr, wav_path = run_c(voice_idx, text)
    c_frames = parse_frames(c_stdout)
    # Guard against the exact false-positive-by-empty-list trap documented
    # in this module's docstring: a real comparison needs real data on
    # both sides.
    assert c_frames, f"{voice_name} {text!r}: parse_frames(c_stdout) returned no frames -- harness invocation likely broken"

    # Mirror api.synthesize_text()'s real clause-splitting (on `. , ! ?`,
    # not just sentence-terminal punctuation -- see _frontend.split_clauses)
    # rather than assembling the whole input as one clause, since a comma
    # ends a Collect_FE_Tokens cycle in the real engine too.
    py_frames = []
    for clause in split_clauses(text):
        phonemes, ctrls, durs, pitch_freq, pitch_time, pitch_flags, end_punctuation = build_phoneme_plan(voice_dict, clause)
        vv = setup_python_voice(voice_dict)
        vv.end_Punctuation = end_punctuation
        clause_frames, vv = run_python_backend(vv, phonemes, ctrls, durs, pitch_freq, pitch_time, pitch_flags)
        py_frames.extend(clause_frames)

    assert len(py_frames) == len(c_frames), (
        f"{voice_name} {text!r}: frame count mismatch (c={len(c_frames)}, py={len(py_frames)})"
    )
    mismatches = compare_frames(c_frames, py_frames)
    assert not mismatches, f"{voice_name} {text!r}: {len(mismatches)} frame mismatches: {mismatches[:3]}"


def test_hello_frame_exact_fred():
    _check("hello", "Fred")


def test_goodbye_frame_exact_fred():
    _check("goodbye", "Fred")


def test_i_am_frame_exact_fred():
    _check("I am.", "Fred")


def test_hello_world_frame_exact_all_voices():
    """The real regression test for both bugs described in the module
    docstring: a genuine two-word sentence, across every voice except the
    two with the pre-existing, independently-documented kUseSyncSnd gap."""
    for voice_name in _VOICES:
        _check("hello world", voice_name)


def test_comma_clause_boundary_frame_count():
    """Regression test for a real bug: `Collect_FE_Tokens` ends its cycle
    on a comma exactly the same way it does on `. ! ?` (confirmed by
    reading `BackEnd.c:3991-4006` -- a comma sets `gotSentence = true` and
    returns), so a comma-containing sentence is actually assembled by the
    real engine as two separate plan-assembly cycles, not one. Before
    `_frontend.split_clauses`/`api.synthesize_text` were updated to split
    on commas too, this produced a genuine frame COUNT mismatch (not just
    a numeric drift) -- e.g. Fred's frame count was 693 instead of the
    real engine's 694 for this exact sentence.

    NOTE: this only asserts frame count, not full bit-exactness --  a
    separate, still-open issue causes small (initially +/-1, growing to
    +/-2 or +/-3) f0 drift over long, multi-syllable sustained pitch
    ramps in ANY sufficiently long sentence (not specific to commas or to
    this fix); see docs/architecture.md's "Known gaps" for the
    reproduction and current understanding."""
    text = "good morning everyone, welcome to the show."
    voice_idx, voice_dict = _VOICES["Fred"]
    c_stdout, c_stderr, wav_path = run_c(voice_idx, text)
    c_frames = parse_frames(c_stdout)
    assert c_frames

    py_frames = []
    for clause in split_clauses(text):
        phonemes, ctrls, durs, pf, pt, pfl, end_punctuation = build_phoneme_plan(voice_dict, clause)
        vv = setup_python_voice(voice_dict)
        vv.end_Punctuation = end_punctuation
        clause_frames, vv = run_python_backend(vv, phonemes, ctrls, durs, pf, pt, pfl)
        py_frames.extend(clause_frames)

    assert len(py_frames) == len(c_frames), (
        f"frame count mismatch (c={len(c_frames)}, py={len(py_frames)})"
    )


def test_wh_question_vs_yesno_question_frame_exact():
    """Regression test for a real bug: a trailing "?" was always mapped to
    _Quest_/kBND_Quest (rising question intonation), but the real engine
    (Morph.c's PlacePhrasing/YesNo_Phrase, BackEnd.c's Fill_Pitch_Buf RAISE
    TYPE BOUNDARY section) only keeps that rising intonation for a genuine
    yes/no question -- a WH-question (clause starts with how/what/why/who/
    whose/which/when/where) has its terminal mark silently downgraded to
    _Period_/kBND_Decl (falling/declarative intonation), confirmed by
    direct instrumentation of the C reference: "how are you today?" produces
    only 3 pitch-buffer entries in the real engine (matching a period-ended
    sentence), not 5 (what a straight _Quest_ mapping produces). Fixed in
    `_assembly.collect_fe_tokens` via a fixed WH-word set (no POS dictionary
    lookup is ported, so this approximates Morph.c's kInterr tag check --
    see docs/architecture.md "Known gaps").

    Both "how are you today?" and "are you happy?" (a genuine yes/no
    question, correctly keeping _Quest_/kBND_Quest) are asserted
    frame-exact -- the latter also exercises the `end_Punctuation`
    propagation fix (see `test_end_punctuation_propagation_frame_exact`),
    since `_Quest_` is one of the two terminators `Calc_Ramp_Steps` halves
    the pitch decline ramp for."""
    _check("how are you today?", "Fred")
    _check("are you happy?", "Fred")


def test_end_punctuation_propagation_frame_exact():
    """Regression test for a real bug: `build_phoneme_plan`'s internal
    `VoiceVar` set `end_Punctuation` correctly before running its own
    `Calc_Ramp_Steps`, but that value was never passed to the SEPARATE
    `VoiceVar` `synthesize_phonemes`/`run_python_backend` use for the
    actual synthesis pass -- which re-ran `Calc_Ramp_Steps` from scratch
    with `end_Punctuation` still at its default (0), silently skipping the
    `>>= 1` halve `Calc_Ramp_Steps` applies for `_Comma_`/`_Quest_`
    (`BackEnd.c:715-716`), doubling the pitch decline ramp step for the
    rest of the clause. Confirmed via direct instrumentation: Fred's
    `down_Ramp_Step` for "good morning everyone," came out as 31531
    instead of the real engine's 15765 (exactly 2x) before this fix.
    Fixed by having `build_phoneme_plan` return `end_punctuation` as a 7th
    value (see `api.py`) and threading it through
    `synthesize_phonemes`/`synthesize_text`. A comma clause and a genuine
    yes/no question (the two terminators `Calc_Ramp_Steps` halves for) are
    both covered here since either could regress independently."""
    _check("good morning everyone,", "Fred")
    _check("are you happy?", "Fred")


def test_sep6_phrase_boundary_frame_exact():
    """Regression test for a real bug: `_assembly.collect_fe_tokens` did
    not model ANY non-punctuation phrase boundary. The pre-existing,
    narrower `kBND_Sep6` gap (previously only observed on the single word
    "ONE" in "testing one two three", masked out in
    `test_assembly.py`/`test_assembly_pipeline.py`) turned out to be the
    SAME missing mechanism as a much more general, high-impact bug: a
    missing `kPhraseReset` pitch-buffer entry mid-sentence (`BackEnd.c:
    640-645`) silently made `down_Ramp_Offset` -- and therefore `f0` --
    drift for the rest of ANY ordinary sentence containing a
    content-word-to-function-word transition (e.g. a verb followed by a
    preposition, as in "jumps over"), which is most sentences longer than
    a few words. Fixed with a `Morph.c` `PlacePhrasing` SEP6 approximation
    in `_assembly.py` (content-word -> function-word POS transition,
    Noun/Verb/Adj/Adv -> anything else, unless the current word is
    clause-final) -- see that code's docstring and docs/architecture.md.
    Exercising this also required fixing a second, compounding bug: the
    POS-choice placeholder (`pos_code1[0]`) picked kAdv over kPrep for
    "to" (`pos_code1=[11,12,3,-1]`), wrongly classifying it as a SEP6
    "content" POS and placing the boundary one word later than the real
    engine -- fixed with a narrow bias toward kPrep when it's among the
    candidates (see `make_fe_word_token`'s docstring)."""
    _check("the quick brown fox jumps over the lazy dog.", "Fred")
    _check("testing one two three", "Fred")
    _check("welcome to the show.", "Fred")


def test_note_driven_singing_voices_frame_exact():
    """Regression test for a real bug: api.new_voice() used to force
    vv.singing = False unconditionally, overriding init_voice()'s correct
    derivation from numOfNotes (BackEnd.c's ResetVoice sets singing=true
    when numOfNotes > 1) -- exactly the same bug pattern previously found
    and fixed in this test file's own setup_python_voice() helper. This
    silently routed PipeOrgan/Cellos/GoodNews/BadNews through
    Mod_Duration's non-singing duration formula instead of the
    note-timed one, producing audibly wrong (too short/long) note
    durations. Also requires vv.Note_Times to be populated via
    e_set_tempo() (now wired into api.new_voice()) -- an unpopulated
    Note_Times would silently zero every note's intended duration."""
    _check("hello world", "PipeOrgan")
    _check("hello world", "Cellos")
    _check("hello world", "GoodNews")
    _check("hello world", "BadNews")
    _check("hello world", "Deranged")


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
