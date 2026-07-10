"""Translate a score between the two markup dialects.

    from pyretrotts.translate import to_macintalk, to_dectalk

    to_macintalk("[:phone on] weh<250,13>")   # -> "[[mode PHON]][[note ...]]weh"

The two engines write the same phonemes down differently, and pitch a note
differently, but the underlying ideas line up:

    DECtalk                      MacinTalk
    [:phone on]                  [[mode PHON]]
    [:ra 170]                    [[rate 170]]
    weh<250,13>                  [[note 48.023]]weh
    _<500>                       [[slnc 500]]

Every one of DECtalk's 55 phonemes has a MacinTalk mnemonic, so phonemes
survive a round trip intact. Pitch survives too: a DECtalk tone is a semitone
index, and a MacinTalk note carries a MIDI number.

Duration is where the two part company. DECtalk times each phoneme in
milliseconds; MacinTalk gives a note one of twelve length codes, indexing a
table the tempo derives. A translated duration therefore lands on the nearest
available length, and translating back does not return the millisecond count
that was written. `_nearest_length_code` says how the choice is made.
"""
from __future__ import annotations

import re

from ._backend import VoiceVar
from ._consts import kFrameTime, kNoteDur, kNoteDurShift, kNotePitch
from ._dectalk import PHONEMES, parse, tone_to_midi
from ._engine import e_set_tempo
from ._rawphon import MAGIC_MAP

__all__ = ["to_macintalk", "to_dectalk", "DEFAULT_TEMPO"]

#: beats per minute a translated score is timed against, when none is given
DEFAULT_TEMPO = 120

#: phoneme id -> the first mnemonic each dialect spells it with
_MACINTALK_MNEMONIC: dict[int, str] = {}
for (_first, _second), _phon in MAGIC_MAP.items():
    _MACINTALK_MNEMONIC.setdefault(_phon, _first + (_second or ""))

_DECTALK_MNEMONIC: dict[int, str] = {}
for _mnemonic, _phon in PHONEMES.items():
    _DECTALK_MNEMONIC.setdefault(_phon, _mnemonic)

_MACINTALK_NOTE = re.compile(r"\[\[\s*note\s+([\d.]+)\s*\]\]", re.IGNORECASE)


def _note_times(tempo: int) -> list[int]:
    """`Note_Times[]` for `tempo`: each length code's duration, in frames."""
    vv = VoiceVar()
    e_set_tempo(vv, tempo)
    return list(vv.Note_Times)


def _nearest_length_code(frames: int, note_times: list[int]) -> int:
    """The length code whose duration is closest to `frames`.

    Codes 1 through 11 are the usable ones: `e_SetTempo` fills them with a
    sixteenth note and its dotted and doubled relatives. Code 0 is written but
    never read, as the C source's own comment says.
    """
    usable = range(1, 12)
    return min(usable, key=lambda code: abs(note_times[code] - frames))


def _note_command(midi: int, length_code: int) -> str:
    """`[[note ...]]` for a MIDI pitch and a length code.

    `Parse_note_Command` reads a fixed-point value whose integer part is the
    pitch and whose fraction carries the length code in `kNoteDur`. The
    fraction is written so that it parses back to the middle of that code's
    range, leaving room for the parser's own rounding.
    """
    target_lsb = (length_code << kNoteDurShift) | (1 << (kNoteDurShift - 1))
    return f"[[note {midi & kNotePitch}.{round(target_lsb / 65536 * 100000):05d}]]"


def to_macintalk(source: str, tempo: int = DEFAULT_TEMPO) -> str:
    """Translate DECtalk markup into MacinTalk markup.

    Phonemes and pitch carry over exactly. Each duration lands on the nearest
    of the twelve note lengths `tempo` provides.
    """
    score = parse(source)
    note_times = _note_times(tempo)
    out: list[str] = [f"[[tmpo {tempo}]]"]

    for segment in score.segments:
        if segment.rate is not None:
            out.append(f"[[rate {segment.rate}]]")
        out.append("[[mode PHON]]")

        for note in segment.notes:
            if note.phoneme == PHONEMES["_"]:
                out.append(f"[[slnc {note.duration_ms or 0}]]")
                continue
            if note.tone is not None:
                frames = note.frames if note.frames is not None else note_times[4]
                out.append(_note_command(
                    tone_to_midi(note.tone), _nearest_length_code(frames, note_times)
                ))
            out.append(_MACINTALK_MNEMONIC[note.phoneme])

        out.append("[[mode TEXT]]")

    if score.text:
        out.append(score.text)
    return "".join(out)


def to_dectalk(source: str, tempo: int = DEFAULT_TEMPO) -> str:
    """Translate MacinTalk markup into DECtalk markup.

    Only what DECtalk has a word for survives: `[[mode PHON]]` phonemes,
    `[[note]]` pitch and length, `[[rate]]`, and `[[slnc]]`. MacinTalk's stress,
    boundary and punctuation opcodes have no DECtalk spelling and are dropped.
    """
    from ._embeddedcmd import scan_bracket_commands

    note_times = _note_times(tempo)
    commands = scan_bracket_commands(source)

    out: list[str] = ["[:phone on]"]
    if commands.final_rate is not None:
        out.append(f"[:ra {commands.final_rate}]")

    # scan_bracket_commands already decoded each phoneme run, keyed by the word
    # index the notes and silences are keyed by.
    for index in sorted(commands.raw_phonemes):
        if index in commands.silences:
            out.append(f"_<{commands.silences[index]}>")

        word = commands.raw_phonemes[index]
        note = commands.notes.get(index)
        for position, phoneme in enumerate(word):
            mnemonic = _DECTALK_MNEMONIC.get(phoneme)
            if mnemonic is None:
                continue  # a stress or boundary opcode DECtalk cannot spell
            # The note belongs to the run; write it on the run's last phoneme,
            # which is where DECtalk's own notation puts it.
            if note is not None and position == len(word) - 1:
                length = (note & kNoteDur) >> kNoteDurShift
                milliseconds = note_times[length or 4] * kFrameTime
                tone = _midi_to_tone(note & kNotePitch)
                out.append(f"{mnemonic}<{milliseconds},{tone}>")
            else:
                out.append(mnemonic)

    return "".join(out)


def _midi_to_tone(midi: int) -> int:
    """A MIDI note as DECtalk's tone number: tone 1 is C2, MIDI 36."""
    return max(1, min(37, midi - 35))
