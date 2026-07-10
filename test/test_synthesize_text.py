"""End-to-end validation of `pylintalker.api.synthesize_text()`/
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

Bells/Hysterical (`kUseSyncSnd` voices) are included in the all-voices
sweep below: `_moduration.py`'s `sync_On_Marker` branch and the marker
tables extracted from `Sounds.c`'s `Bells_Sound`/`Hysterical_Sound`
headers into `_data.py` (`Bells_Markers`/`Hysterical_Markers`) make them
frame-exact too -- what looked like a fundamental external-sample-audio
gap turned out to be a single missing metadata field (`Frame.marker`,
plus the vowel-duration adjustment `Mod_Duration` computes from it): the
formant synthesis itself never needed the actual embedded PCM sample
bytes, only the marker TIMESTAMPS from the sample header.

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

from test_voices import compare_frames, parse_frames, run_c

import pylintalker._backend as be
from pylintalker._backend import kFrame1
from pylintalker._data import (
    BadNews_Voice,
    Bells_Voice,
    Boing_Voice,
    Bubbles_Voice,
    Cellos_Voice,
    Deranged_Voice,
    Fred_Voice,
    GoodNews_Voice,
    Hysterical_Voice,
    Junior_Voice,
    Kathy_Voice,
    PipeOrgan_Voice,
    Princess_Voice,
    Ralph_Voice,
    Trinoids_Voice,
    Whisper_Voice,
    Zarvox_Voice,
)
from pylintalker.api import synthesize_text

_VOICES = {
    "Fred": (0, Fred_Voice), "Kathy": (1, Kathy_Voice), "Princess": (2, Princess_Voice),
    "Junior": (3, Junior_Voice), "Ralph": (4, Ralph_Voice), "Whisper": (5, Whisper_Voice),
    "Zarvox": (6, Zarvox_Voice), "Trinoids": (7, Trinoids_Voice), "Bubbles": (8, Bubbles_Voice),
    "Boing": (9, Boing_Voice), "Bells": (10, Bells_Voice), "Hysterical": (11, Hysterical_Voice),
    "Deranged": (12, Deranged_Voice), "GoodNews": (13, GoodNews_Voice),
    "BadNews": (14, BadNews_Voice), "PipeOrgan": (15, PipeOrgan_Voice), "Cellos": (16, Cellos_Voice),
}


def _synthesize_text_frames(voice_dict, text):
    """Runs the REAL public `api.synthesize_text()` (not a hand-assembled
    stand-in) and captures its per-frame formant state via
    `_backend.post_frame_hook`, so this file validates exactly what a
    caller of this library gets."""
    frames = []
    frame_num = [0]

    def on_frame(vv):
        zz = vv.synthVars
        fp = zz.frameBuf2 if zz.curFrameBuf == kFrame1 else zz.frameBuf1
        phon_idx = vv.cur_PhonBuf_Index_CF
        phon_id = vv.phon_Buf_2[phon_idx] if phon_idx < len(vv.phon_Buf_2) else 0
        frames.append({
            'num': frame_num[0], 'phon_idx': phon_idx, 'phon_id': phon_id,
            'dur_done': vv.dur_Done_in_Phon_CF,
            'f0': fp.f0, 'f1': fp.f1, 'f2': fp.f2, 'f3': fp.f3,
            'bw1': fp.bw1, 'bw2': fp.bw2, 'bw3': fp.bw3,
            'Av': fp.Av, 'Af': fp.Af,
            'a2': fp.a2, 'a3': fp.a3, 'a4': fp.a4, 'a5': fp.a5, 'a6': fp.a6,
            'AB': fp.AB, 'FNZ': fp.FNZ, 'marker': fp.marker,
        })
        frame_num[0] += 1

    be.post_frame_hook = on_frame
    try:
        synthesize_text(voice_dict, text)
    finally:
        be.post_frame_hook = None
    return frames


def _check(text, voice_name):
    voice_idx, voice_dict = _VOICES[voice_name]
    c_stdout, c_stderr, wav_path = run_c(voice_idx, text)
    c_frames = parse_frames(c_stdout)
    # Guard against the exact false-positive-by-empty-list trap documented
    # in this module's docstring: a real comparison needs real data on
    # both sides.
    assert c_frames, f"{voice_name} {text!r}: parse_frames(c_stdout) returned no frames -- harness invocation likely broken"

    py_frames = _synthesize_text_frames(voice_dict, text)

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
    docstring: a genuine two-word sentence, across all 17 voices."""
    for voice_name in _VOICES:
        _check("hello world", voice_name)


def test_comma_clause_boundary_frame_exact():
    """Regression test for a real bug: `Collect_FE_Tokens` ends its cycle
    on a comma exactly the same way it does on `. ! ?` (confirmed by
    reading `BackEnd.c:3991-4006` -- a comma sets `gotSentence = true` and
    returns), so a comma-containing sentence is actually assembled by the
    real engine as two separate plan-assembly cycles, not one. Before
    `_frontend.split_clauses`/`api.synthesize_text` were updated to split
    on commas too, this produced a genuine frame COUNT mismatch -- e.g.
    Fred's frame count was 693 instead of the real engine's 694 for this
    exact sentence.

    Now asserts full frame-exactness, not just count: a separate bug
    (`_reset_for_clause` missing `songIndex`'s `ParseSentence`-final reset,
    and `synthesize_text` giving each clause an independently-reset
    `VoiceVar` instead of one shared session) used to cause small
    per-clause pitch/formant drift; both are fixed -- see
    `test_end_punctuation_propagation_frame_exact` and
    `test_cross_clause_voicevar_sharing_frame_exact`."""
    _check("good morning everyone, welcome to the show.", "Fred")


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
    `_assembly.collect_fe_tokens` using `_morph.resolve_pos()`'s real
    `kInterr` tag resolution (a real port of `Morph.c`'s `ResolvePOS`),
    matching the C reference's own `YesNo_Phrase` logic
    (`Morph.c:139-144`) rather than a fixed WH-word list.

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
    original placeholder POS selection (`pos_code1[0]`) picked kAdv over
    kPrep for "to" (`pos_code1=[11,12,3,-1]`), wrongly classifying it as a
    SEP6 "content" POS and placing the boundary one word later than the
    real engine. `_morph.resolve_pos()` (a real port of Morph.c's
    `ResolvePOS`) has since replaced that placeholder entirely and
    resolves "to" to kPrep correctly via real context rules, not a
    frequency bias."""
    _check("the quick brown fox jumps over the lazy dog.", "Fred")
    _check("testing one two three", "Fred")
    _check("welcome to the show.", "Fred")


def test_sep1_to_sep5_phrase_boundary_frame_exact():
    """Regression test for `_assembly._place_phrasing`'s SEP1-5 rules
    (`Morph.c:148-256`), the rest of `PlacePhrasing`'s boundary cascade
    beyond the previously-ported SEP6. Unlike SEP6, a SEP1-5 boundary
    inserts an actual `_SIL_` phoneme (`BackEnd.c:3819-3826`: any
    boundary type `>= kBND_Paren_L` other than `kBND_Sep6` gets its own
    phoneme, with the boundary/`kVerb_Start` flags on THAT `_SIL_`, not
    on the next word's first phoneme) -- confirmed via direct frame-count
    comparison against the C reference (a missing SIL shows up as a
    frame-count mismatch, not just a wrong flag bit). Each sentence below
    was confirmed via direct instrumentation to exercise a real SEP1-5
    hit in the C reference (a `_SIL_` phoneme with a nonzero
    `kSilenceTypeField` value in `[7,11]` at a non-clause-final
    position)."""
    _check("i want to go to the store and buy some food.", "Fred")
    _check("the man who lives there is nice.", "Fred")
    _check("she said that he was late.", "Fred")
    _check("many people came to the party.", "Fred")
    _check("he ran quickly and then he stopped.", "Fred")
    _check("the dog and the cat played together.", "Fred")
    _check("they read the letter that arrived.", "Fred")
    _check("this is the book that i read.", "Fred")
    _check("when he arrives we will leave.", "Fred")
    _check("i think that this is a very good idea.", "Fred")


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


def test_cross_clause_voicevar_sharing_frame_exact():
    """Regression test for a real bug reported by a user: a note-driven
    singing voice (Cellos) still sounded wrong on a comma+question
    sentence even after the SEP6/end_Punctuation fixes above.
    `synthesize_text` gave each clause its own independently-reset
    `VoiceVar`, discarding formant-synthesis/frame-buffer state
    (`init_control_blocks`, frame double-buffering) at every clause
    boundary -- audible as a glitch for ordinary voices too, but far more
    noticeable for singing voices, where it sounded like the melody
    restarting. Confirmed via direct comparison: the same sentence
    synthesized as a single clause (no comma) was already frame-exact,
    isolating the bug to the clause-boundary handling itself.

    Fixed by having ALL clauses of one `synthesize_text` call share a
    single `VoiceVar`/frame loop (`Start_Talk` runs once; `ParseSentence`
    -- here, `build_phoneme_plan(vv=vv)` -- simply runs again per clause,
    `BackEnd.c:4264-4298`/`4224-4231`). This uncovered a SECOND, deeper
    bug in the process: `Mod_Duration`'s singing branch advances
    `vv.songIndex` as scratch bookkeeping while assigning note-driven
    durations, but the real `ParseSentence` resets `songIndex` back to 0
    at its very end (`vv->songIndex = vv->lastSongIndex`, `BackEnd.c:4188`)
    before synthesis ever reads it -- a reset this port never modeled,
    because the OLD independently-reset-`VoiceVar`-per-clause approach
    never exposed it (each clause's synthesis `VoiceVar` was fresh and
    had never run `Mod_Duration`, so `songIndex` was accidentally always
    0 already). Confirmed via direct instrumentation: sharing one
    `VoiceVar` without this reset left `songIndex` at 11 instead of 0
    for the second clause, corrupting every note pitch for its whole
    duration. Both fixes are in `_reset_for_clause`/`build_phoneme_plan`
    (`api.py`)."""
    _check("the quick brown fox jumps over the lazy dog, how are you today?", "Cellos")
    _check("good morning everyone, welcome to the show.", "PipeOrgan")
    _check("good morning everyone, welcome to the show.", "GoodNews")
    _check("good morning everyone, welcome to the show.", "BadNews")


def test_kusesyncsnd_marker_frame_exact():
    """Regression test for a real bug: Bells/Hysterical (the two
    `waveType == kUseSyncSnd` voices) previously mismatched the C
    reference only in `Frame.marker` (a metadata field used for external
    sync callbacks) -- audio synthesis itself (`f0`/formants/amplitude)
    was already bit-exact, showing this was never the fundamental
    external-sample-audio gap it was assumed to be. `Mod_Duration`'s
    `sync_On_Marker` branch (`BackEnd.c:1938-1976`) needs a marker-time
    table (`vv.markerBuf`/`vv.lastMarkerIndex`) that the real engine reads
    out of the embedded sample header (`Sounds.c`'s `Bells_Sound`/
    `Hysterical_Sound` arrays: length, marker count, then the marker
    times themselves) -- `vv.sync_On_Marker` was already being set
    correctly (`_backend.init_voice`), but nothing ever populated
    `markerBuf`. Fixed by extracting just the marker-time header (not the
    PCM sample bytes, never needed since this port's formant synthesizer
    never switches glottal source) into `_data.py`'s `Bells_Markers`/
    `Hysterical_Markers`, wired in by `api.new_voice`, and porting
    `Mod_Duration`'s `sync_On_Marker` branch itself in `_moduration.py`."""
    _check("hello world", "Bells")
    _check("hello world", "Hysterical")
    _check("testing one two three", "Bells")
    _check("testing one two three", "Hysterical")


def test_s_morph_frame_exact():
    """Regression test for `_morph.try_s_morph` (`Morph.c`'s `Do_S_Morph`/
    `Store_S_or_Z`, `Morph.c:2306-2322`/`1236-1266`): a word ending in "S"
    with no direct dictionary entry (e.g. "DOGS", "CATS", "WISHES") whose
    root IS a dictionary entry now gets the root's pronunciation plus a
    phonetically-correct plural/3rd-person-singular suffix, instead of
    falling all the way through to `_engtop.engtop()`'s generic
    letter-to-sound rules. Covers all three `Store_S_or_Z` branches: `/z/`
    after a voiced sound ("dogs"), `/s/` after a voiceless consonant
    ("cats"), and `/ɪz/` after a sibilant/palatal ("wishes", "buses")."""
    _check("the dogs bark.", "Fred")
    _check("cats and dogs.", "Fred")
    _check("the wishes came true.", "Fred")
    _check("buses and cars.", "Fred")


def test_do_morph_suffix_frame_exact():
    """Regression test for `_morph.try_do_morph` (`Morph.c`'s `DoMorph`
    suffix functions beyond plain `-S`): a word with no direct dictionary
    entry, ending in one of the ported suffixes, whose root IS a
    dictionary entry, gets the root's real pronunciation plus the
    phonetically-correct suffix phonemes instead of falling through to
    `_engtop.engtop()`'s generic letter-to-sound rules. Covers `-CALLY`
    ("magically", root MAGIC), `-ED`/`-IED` ("timed"/"tried", roots
    TIME/TRY), `-ER`/`-IER` ("shorter"/"readers" via `-ERS`, roots
    SHORT/READ), `-ING` ("timing"/"playing", roots TIME/PLAY), plain
    `-LY` ("talked", via `-ED`, root TALK), `-ES`/`-IES` ("loves"/
    "likes", roots LOVE/LIKE), `-IEST` ("loveliest", root LOVE),
    `-MENT`/`-MENTS` ("government"/"governments", root GOVERN),
    `-ABLE` ("arguable", root ARGUE, via the `-E`-restoring decompose),
    `-INESS`/`-INESSES` ("business"/"businesses", root BUSY, via the
    "-Y" root recovery), `-ISM`/`-ISMS` ("heroism"/"heroisms", root
    HERO), `-OR`/`-ORS` ("editor"/"editors", root EDIT), and the
    `-IZE` family `-IZE`/`-IZED`/`-IZES`/`-IZING`/`-IZINGS`/`-IZER`/
    `-IZERS` ("itemize"/"itemized"/"itemizes"/"itemizing"/"itemizings"/
    "itemizer"/"itemizers", root ITEM -- none of which have "itemize"
    itself as a dictionary entry, so each exercises the `Do_IZE*_Morph`
    fallback rather than the plain suffix decompose)."""
    _check("he timed it perfectly.", "Fred")
    _check("a good timer.", "Fred")
    _check("good timing.", "Fred")
    _check("a shorter path.", "Fred")
    _check("magically appear.", "Fred")
    _check("she talked and played.", "Fred")
    _check("she loves and likes it.", "Fred")
    _check("the readers and offers.", "Fred")
    _check("the loveliest gift.", "Fred")
    _check("the government announced it.", "Fred")
    _check("many governments agreed.", "Fred")
    _check("an arguable point.", "Fred")
    _check("a good business.", "Fred")
    _check("many businesses failed.", "Fred")
    _check("pure heroism.", "Fred")
    _check("many heroisms.", "Fred")
    _check("a careful editor.", "Fred")
    _check("the editors met.", "Fred")
    _check("the management decided.", "Fred")
    _check("they itemize the list.", "Fred")
    _check("she itemized it.", "Fred")
    _check("he itemizes everything.", "Fred")
    _check("they are itemizing it.", "Fred")
    _check("many itemizings occurred.", "Fred")
    _check("a careful itemizer.", "Fred")
    _check("several itemizers helped.", "Fred")


def test_do_morph_pos_from_suffix():
    """Regression test for `_morph.pos_select_for_suffix` (`Morph.c`'s
    `SetPOS_FromSuffix`, `Morph.c:1027-1189`): a word's dictionary root
    can have an AMBIGUOUS POS (e.g. "time" is noun/adj/verb), but most
    suffixes unambiguously force a specific POS on the MORPHED word
    regardless of the root's own candidates (e.g. "-ED" always means
    kVerb: "timed" cannot be a noun even though "time" can be). Before
    this was ported, `_assembly.make_fe_word_token` used the ROOT's own
    (possibly ambiguous) POS codes for every morphed word, which is only
    correct for the two suffix codes that really do leave the root's POS
    untouched (`kS_suffix`, and several suffix fallback codes with no
    `SetPOS_FromSuffix` case, e.g. plain `-IZER`/`-IZING`). Verifies
    `make_fe_word_token("TIMED", None).pos_code1` resolves to `[kVerb,
    kUndefPOS, kUndefPOS, kUndefPOS]`, not the root "TIME"'s own
    (ambiguous) candidate list."""
    from pylintalker._assembly import make_fe_word_token
    from pylintalker._consts import kUndefPOS, kVerb

    tok = make_fe_word_token("TIMED", None)
    assert tok.pos_code1 == [kVerb, kUndefPOS, kUndefPOS, kUndefPOS], tok.pos_code1
    assert tok.comp_pos1 == (1 << kVerb)

    _check("he timed it perfectly.", "Fred")


def test_do_morph_pos_from_suffix_hasalt_zap_pos():
    """Regression test for `_morph.apply_pos_from_suffix`'s `hasAlt`-true
    branch (`SetPOS_FromSuffix`'s `Zap_POS` re-selection, `Morph.c:1027
    -1189`): a homograph root (e.g. "lead" is verb/noun, "tear" is
    verb/noun, "bow" is noun/verb, "wind" is noun/verb) that also gets
    DoMorph'd via a suffix forcing a specific POS should pick whichever
    of the root's two dictionary readings (`pos_code1`/`pos_code2`)
    matches that forced POS, not blindly keep `pos_code1`. Before this
    was ported, `has_alt` was hardcoded `False` for every morphed word,
    so this branch was unreachable; it now uses the root's real
    `has_alt`. Covers roots where the suffix-forced POS matches
    `pos_code1` (the common case): "leaded" (root LEAD, `-ED`->kVerb,
    matches LEAD's own verb reading), "tears" (root TEAR, `-S`->kVerb,
    matches TEAR's own verb reading), "bowed"/"bows" (root BOW,
    `-ED`/`-S`->kVerb, matches one of BOW's noun/verb/noun readings) --
    and the rarer case where it matches `pos_code2` (the ALT reading)
    instead: "winded" (root WIND, `-ED`->kVerb, matching WIND's
    `pos_code2` verb reading, NOT its `pos_code1` noun reading). That
    ALT-reading case also exercises `_morph.try_do_morph`'s
    `build_phon_str`-deferred-to-caller design: the real engine switches
    to the root's ALTERNATE pronunciation (`phon_hold`'s /waɪnd/, not
    `phon_str`'s /wɪnd/) whenever the ALT POS reading wins, which
    `_assembly.make_fe_word_token` now does by choosing `phon_hold` vs
    `phon_str` as `build_phon_str`'s base AFTER `apply_pos_from_suffix`
    resolves `alt_choice` -- confirmed via direct phoneme comparison
    against the C reference (this exact case previously mismatched on
    the vowel phoneme distinguishing /waɪnd/ from /wɪnd/, now fixed)."""
    _check("the leaded gasoline.", "Fred")
    _check("she teared up.", "Fred")
    _check("he bowed to the crowd.", "Fred")
    _check("the archer has two bows.", "Fred")
    _check("he winded up the toy.", "Fred")


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
