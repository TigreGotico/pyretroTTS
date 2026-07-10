"""The DECtalk markup dialect: commands, phoneme mnemonics, singing notation."""
import pytest

from pyretrotts._consts import kFrameTime
from pyretrotts._dectalk import (
    PHONEMES,
    TONE_MAX_NOTE,
    hz_to_midi,
    parse,
    tone_to_midi,
)
from pyretrotts._phonemes import _AA_, _EH_, _IY_, _JH_, _SIL_, _w_

# --- tone semantics -------------------------------------------------------
# set_user_target (ph_drwt01.c:1955-1984) reads the tone by magnitude: 1..37 is
# a semitone index into notetab[] ("Notes in F0*10 from C2 to C5"), anything
# larger is an absolute frequency in Hz.

@pytest.mark.parametrize("tone,midi,note", [(1, 36, "C2"), (13, 48, "C3"),
                                            (25, 60, "C4"), (37, 72, "C5")])
def test_tone_is_a_semitone_index_from_c2_to_c5(tone, midi, note):
    assert tone_to_midi(tone) == midi, note


def test_the_note_range_spans_exactly_three_octaves():
    assert tone_to_midi(TONE_MAX_NOTE) - tone_to_midi(1) == 36


def test_a_tone_above_the_note_range_is_a_frequency_in_hz():
    assert tone_to_midi(110) == hz_to_midi(110)   # A2
    assert tone_to_midi(220) == hz_to_midi(220)   # A3


def test_a_frequency_above_the_engines_ceiling_is_clamped():
    # HIGHEST_F0 is 512.1 Hz, so a wild value lands on the top note, not above it.
    assert tone_to_midi(1190) == tone_to_midi(512)


# --- phoneme mnemonics ----------------------------------------------------

def test_mnemonics_match_longest_first():
    # "jhiy" is `jh` + `iy`, not `j` + `h` + `iy`.
    score = parse("[:phone on] jhiy")
    assert [n.phoneme for n in score.notes] == [_JH_, _IY_]


def test_mnemonics_are_case_insensitive():
    assert parse("[:phone on] AA").notes[0].phoneme == _AA_
    assert parse("[:phone on] aa").notes[0].phoneme == _AA_


def test_underscore_is_silence():
    assert PHONEMES["_"] == _SIL_


def test_unknown_characters_are_skipped():
    score = parse("[:phone on] w#eh")
    assert [n.phoneme for n in score.notes] == [_w_, _EH_]


# --- singing notation -----------------------------------------------------

def test_a_note_annotates_the_phoneme_before_it():
    score = parse("[:phone on] weh<250,13>")
    w, eh = score.notes
    assert (w.phoneme, w.duration_ms, w.tone) == (_w_, None, None)
    assert (eh.phoneme, eh.duration_ms, eh.tone) == (_EH_, 250, 13)


def test_duration_without_a_tone_is_allowed():
    note, = parse("[:phone on] aa<300>").notes
    assert note.duration_ms == 300 and note.tone is None


def test_duration_converts_to_frames():
    note, = parse("[:phone on] aa<250,13>").notes
    assert note.frames == 250 // kFrameTime


def test_an_untimed_phoneme_has_no_frames():
    assert parse("[:phone on] aa").notes[0].frames is None


def test_score_duration_sums_its_notes():
    score = parse("[:phone on] aa<200,13> _<300> iy<100,20>")
    assert score.duration_ms == 600


# --- commands -------------------------------------------------------------

def test_phoneme_mode_gates_the_score():
    assert parse("hello world").notes == []
    assert parse("[:phone on] aa<100,13>").notes != []


def test_text_outside_phoneme_mode_is_kept_separately():
    score = parse("hello there")
    assert score.text == "hello there" and not score.notes


def test_rate_and_voice_and_designer_voice_are_read():
    score = parse("[:phone on][:np][:ra 170][:dv hs 95 br 0 ap 90] aa<100,13>")
    segment, = score.segments
    assert segment.voice == "Perfect Paul"
    assert segment.rate == 170
    assert segment.voice_params == {"hs": 95, "br": 0, "ap": 90}


def test_an_unclosed_command_does_not_swallow_the_next_one():
    # Real scores write `[:ra 170 [:dv hs 95]`, omitting the first bracket.
    score = parse("[:phone on][:ra 170 [:dv hs 95] aa<100,13>")
    segment, = score.segments
    assert segment.rate == 170
    assert segment.voice_params == {"hs": 95}


def test_unrecognized_commands_are_dropped():
    score = parse("[:phone on][:bogus 1] aa<100,13>")
    assert len(score.notes) == 1


# --- segments -------------------------------------------------------------

def test_a_voice_change_starts_a_new_segment():
    score = parse("[:phone on][:np] aa<100,13> [:nu] iy<100,20> [:np] aa<100,13>")
    assert [s.voice for s in score.segments] == [
        "Perfect Paul", "Uppity Ursula", "Perfect Paul",
    ]
    assert score.voices == ["Perfect Paul", "Uppity Ursula"]


def test_notes_reach_the_segment_that_was_in_force():
    score = parse("[:phone on][:np] aa<100,13> [:nu] iy<200,20>")
    first, second = score.segments
    assert [n.phoneme for n in first.notes] == [_AA_]
    assert [n.phoneme for n in second.notes] == [_IY_]
    assert second.notes[0].duration_ms == 200


def test_a_score_with_no_voice_command_is_one_segment():
    score = parse("[:phone on] aa<100,13> iy<100,20>")
    assert len(score.segments) == 1 and score.segments[0].voice is None
