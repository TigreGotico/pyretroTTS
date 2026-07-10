"""Translating a score between the two markup dialects."""
import pytest

from pyretrotts._consts import kNoteDur, kNoteDurShift, kNotePitch
from pyretrotts._dectalk import parse
from pyretrotts._embeddedcmd import scan_bracket_commands
from pyretrotts.translate import (
    _midi_to_tone,
    _nearest_length_code,
    _note_command,
    _note_times,
    to_dectalk,
    to_macintalk,
)

# --- the note word --------------------------------------------------------

@pytest.mark.parametrize("midi", [36, 48, 60, 72])
@pytest.mark.parametrize("length_code", range(1, 12))
def test_a_written_note_parses_back_to_the_pitch_and_length_it_encoded(midi, length_code):
    word = scan_bracket_commands(_note_command(midi, length_code) + "la").notes[0]
    assert word & kNotePitch == midi
    assert (word & kNoteDur) >> kNoteDurShift == length_code


def test_the_nearest_length_code_is_chosen():
    times = _note_times(120)
    for code in range(1, 12):
        assert _nearest_length_code(times[code], times) == code


def test_a_midi_note_becomes_a_tone_and_back():
    from pyretrotts._dectalk import tone_to_midi
    for tone in range(1, 38):
        assert _midi_to_tone(tone_to_midi(tone)) == tone


# --- DECtalk -> MacinTalk -------------------------------------------------

def test_phoneme_mode_and_rate_translate():
    out = to_macintalk("[:phone on][:ra 170] aa<250,13>")
    assert "[[mode PHON]]" in out
    assert "[[rate 170]]" in out


def test_a_rest_becomes_a_silence_command():
    assert "[[slnc 500]]" in to_macintalk("[:phone on] _<500>")


def test_the_translation_parses_as_macintalk():
    commands = scan_bracket_commands(to_macintalk("[:phone on] weh<250,13>"))
    assert commands.notes, "the pitch must survive"
    assert commands.raw_phonemes, "the phonemes must survive"


def test_pitch_survives_the_translation():
    from pyretrotts._dectalk import tone_to_midi
    commands = scan_bracket_commands(to_macintalk("[:phone on] aa<250,13>"))
    note = next(iter(commands.notes.values()))
    assert note & kNotePitch == tone_to_midi(13)


# --- MacinTalk -> DECtalk -------------------------------------------------

def test_the_reverse_translation_parses_as_dectalk():
    score = parse(to_dectalk("[[mode PHON]][[note 48.01367]]AA[[mode TEXT]]"))
    assert score.phoneme_mode
    assert score.notes


def test_rate_survives_the_reverse_translation():
    assert "[:ra 170]" in to_dectalk("[[rate 170]][[mode PHON]]AA[[mode TEXT]]")


# --- round trip -----------------------------------------------------------

SOURCE = "[:phone on][:ra 170] weh<250,13>n yu<350,20>"


def test_phonemes_survive_a_round_trip():
    there = [n.phoneme for n in parse(SOURCE).notes]
    back = [n.phoneme for n in parse(to_dectalk(to_macintalk(SOURCE))).notes]
    assert there == back


def test_tones_survive_a_round_trip():
    there = [n.tone for n in parse(SOURCE).notes if n.tone]
    back = [n.tone for n in parse(to_dectalk(to_macintalk(SOURCE))).notes if n.tone]
    assert there == back


def test_durations_quantize_to_the_nearest_note_length():
    """MacinTalk gives a note one of twelve lengths, so 350 ms comes back 375."""
    back = parse(to_dectalk(to_macintalk(SOURCE)))
    written = [n.duration_ms for n in back.notes if n.duration_ms]
    assert written == [250, 375]


def test_the_note_moves_to_the_end_of_its_run():
    """A MacinTalk note applies to a whole phoneme run, not one phoneme."""
    back = parse(to_dectalk(to_macintalk(SOURCE)))
    timed = [i for i, n in enumerate(back.notes) if n.tone is not None]
    # `weh` + `n` is one run; the note lands on `n`, not on `eh`.
    assert timed == [2, 3]


def test_a_translated_score_renders():
    from pyretrotts.engines import MacInTalkEngine, pcm_peak
    pcm = MacInTalkEngine().synthesize(to_macintalk(SOURCE), "Fred")
    assert pcm_peak(pcm) > 500
