"""The public synthesis API.

`synthesize_text` takes English text; `synthesize_phonemes` and
`synthesize_plan` take a phoneme plan directly, bypassing the text frontend.
All three return raw 16-bit mono PCM, which `pcm_to_wav` writes to a file.

See docs/architecture.md for the pipeline these compose.
"""
from __future__ import annotations

import wave
from collections.abc import Iterable
from dataclasses import dataclass, field

from ._assembly import collect_fe_tokens
from ._backend import (
    VoiceVar,
    calc_ramp_steps,
    e_fill_next_frame,
    init_voice,
    say_frame,
    start_new_pitch_clause,
    start_talk,
)
from ._consts import (
    SamplingRate,
    kMaxMarkers,
    kNoMarker,
    kSpeakLastFrame,
    kSpeakNewPhon,
)
from ._embeddedcmd import scan_bracket_commands
from ._engine import e_set_tempo
from ._frontend import split_clauses
from ._moduration import mod_duration
from ._phonbuf2 import fill_phon_buf_2, insert_closure_release
from ._pitchbuf import fill_pitch_buf
from ._pitchcontour import pitch_raise_and_fall
from ._voice import Voice


def new_voice(voice_dict: Voice) -> VoiceVar:
    """Create and initialize a VoiceVar for the given voice definition."""
    vv = VoiceVar()
    init_voice(vv, voice_dict)
    vv.FEinputDone = True
    # init_voice derives `singing` from the voice's note count. Do not override
    # it: a note-driven voice forced to singing=False gets Mod_Duration's
    # plain duration formula instead of the note-timed one.
    vv.newSentence = True
    vv.start_of_Paragraph_Flag = False
    vv.stress_Active_Time = 0
    vv.user_Pitch_Buf2 = [0] * 512
    vv.controlF0 = vv.VP_baselinePitch
    vv.frameMarker = kNoMarker

    # Populates Note_Times[], which Mod_Duration's note-driven branches read
    # (BackEnd.c:4364-4368). A no-op for voices that do not sing.
    e_set_tempo(vv, vv.tempo)

    # Bells and Hysterical sync their syllables to marker points in their
    # sampled glottal source (InsertSample, Say.c:1471-1499). Mod_Duration's
    # sync_On_Marker branch reads these times to compute vowel durations.
    markers = voice_dict.get('markers')
    if markers:
        vv.markerBuf[:len(markers)] = markers
        vv.lastMarkerIndex = len(markers) - 1
    return vv


def _reset_for_clause(vv: VoiceVar) -> None:
    """Reset the per-clause fields, as `ParseSentence` does at the start of
    every call (`BackEnd.c:4167-4178`) -- including when a `VoiceVar` is being
    reused across the clauses of one utterance."""
    vv.songIndex = 0
    vv.lastSongIndex = 0
    vv.songIndex_Save1 = 0
    vv.songIndex_Save2 = 0
    vv.cmdBufCount = 0
    vv.cmdBufCount_Save1 = 0
    vv.newSentence = True
    vv.markerIndex = 0
    vv.frameMarker = kNoMarker


@dataclass(frozen=True)
class PhonemePlan:
    """Everything the synthesizer needs to voice one clause.

    `phonemes`, `ctrls` and `durs` are parallel: one entry per phoneme (see
    `pyretrotts._phonemes` for the ids). The `pitch_*` lists are likewise
    parallel to each other and describe the clause's pitch contour.
    """

    phonemes: list[int] = field(default_factory=list)
    ctrls: list[int] = field(default_factory=list)
    durs: list[int] = field(default_factory=list)
    pitch_freq: list[int] = field(default_factory=list)
    pitch_time: list[int] = field(default_factory=list)
    pitch_flags: list[int] = field(default_factory=list)
    #: the clause's terminator; Calc_Ramp_Steps halves the pitch decline ramp
    #: for a comma or a question mark, so synthesis must be told which it was.
    end_punctuation: int = 0


def synthesize_phonemes(
    voice_dict: Voice,
    phonemes: Iterable[int],
    ctrls: Iterable[int],
    durs: Iterable[int],
    pitch_freq: Iterable[int] = (),
    pitch_time: Iterable[int] = (),
    pitch_flags: Iterable[int] = (),
    vv: VoiceVar | None = None,
    end_punctuation: int = 0,
) -> bytes:
    """Synthesize a phoneme plan into raw 16-bit PCM audio (little-endian, mono).

    ``phonemes``/``ctrls``/``durs`` are parallel arrays describing the
    phoneme sequence (see ``pyretrotts._phonemes`` for phoneme ids). ``pitch_*``
    describe an optional pitch contour overlay.

    ``end_punctuation`` must be the terminator the clause actually ended on:
    `Calc_Ramp_Steps` (`BackEnd.c:678-739`) reads `vv->end_Punctuation`
    directly rather than deriving it from the phoneme arrays, and halves the
    pitch decline ramp step for a comma or a question mark. Prefer
    `synthesize_plan`, which carries it for you.
    """
    phonemes = list(phonemes)
    ctrls = list(ctrls)
    durs = list(durs)
    pitch_freq = list(pitch_freq)
    pitch_time = list(pitch_time)
    pitch_flags = list(pitch_flags)

    if vv is None:
        vv = new_voice(voice_dict)
    vv.end_Punctuation = end_punctuation

    for i, (p, c, d) in enumerate(zip(phonemes, ctrls, durs, strict=True)):
        vv.phon_Buf_2[i] = p
        vv.phon_Ctrl_Buf_2[i] = c
        vv.dur_Buf[i] = d
    vv.phonBuf_2_In_Index = len(phonemes)

    for i, (f, t, fl) in enumerate(zip(pitch_freq, pitch_time, pitch_flags, strict=True)):
        vv.pitch_Buf_Freq[i] = f
        vv.pitch_Buf_Time[i] = t
        vv.pitch_Buf_Flags[i] = fl
    vv.pitchBuf_In_Index = len(pitch_freq)

    calc_ramp_steps(vv)
    start_new_pitch_clause(vv)

    start_talk(vv)
    while vv.speakState != kSpeakLastFrame:
        say_frame(vv)
        e_fill_next_frame(vv)
    say_frame(vv)

    return bytes(vv.sampleBuffer)


def synthesize_plan(
    voice_dict: Voice, plan: PhonemePlan, vv: VoiceVar | None = None
) -> bytes:
    """Synthesize a `PhonemePlan` into raw 16-bit PCM audio."""
    return synthesize_phonemes(
        voice_dict,
        plan.phonemes, plan.ctrls, plan.durs,
        plan.pitch_freq, plan.pitch_time, plan.pitch_flags,
        vv=vv, end_punctuation=plan.end_punctuation,
    )


def pcm_to_wav(pcm: bytes, path: str, sample_rate: int = SamplingRate) -> str:
    """Write raw 16-bit mono PCM to a WAV file. Returns the path."""
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return path


def build_phoneme_plan(
    voice_dict: Voice, text: str, vv: VoiceVar | None = None
) -> PhonemePlan:
    """Turn one clause of English text into a `PhonemePlan`.

    Runs `ParseSentence`'s pipeline in its own order: Collect_FE_Tokens ->
    Fill_Phon_Buf_2 -> Pitch_RaiseAndFall -> Mod_Duration ->
    Insert_Closure_Release -> Calc_Ramp_Steps -> Fill_Pitch_Buf.

    `text` is treated as a single clause. For anything longer, use
    `synthesize_text`, which splits on clause-terminal punctuation and calls
    this once per clause.

    Pass the same `vv` across the clauses of one utterance to carry the
    formant and frame-buffer state between them; a fresh one restarts it.
    Either way `_reset_for_clause` runs first.
    """
    if vv is None:
        vv = new_voice(voice_dict)
    _reset_for_clause(vv)

    commands = scan_bracket_commands(text, initial_rate=vv.speech_Rate)
    if commands.final_rate is not None:
        # vv->lastRate is a single persistent field, not reset per clause, so
        # a later clause's rate/ratr resolves against this baseline.
        vv.speech_Rate = commands.final_rate

    if commands.tempo is not None:
        e_set_tempo(vv, commands.tempo)
    if commands.notes:
        vv.singing = True  # EC_note sets this in the C source
    if commands.markers:
        # EC_marker: record each marker time, up to kMaxMarkers-1. Beyond that
        # the C source turns marker-synced singing off rather than overflow.
        times = list(commands.markers.values())
        if len(times) < kMaxMarkers:
            for idx, time in enumerate(times):
                vv.markerBuf[idx] = time
            vv.markerIndex = len(times)
            vv.lastMarkerIndex = max(1, len(times))
            vv.sync_On_Marker = True
            vv.singing = True
        else:
            vv.sync_On_Marker = False
            vv.singing = False

    sa = collect_fe_tokens(commands.text, commands)
    # collect_fe_tokens counted each queued command against the phoneme it was
    # written in front of (QueueCommand, BackEnd.c:3592-3599). Load the queue
    # itself; fill_phon_buf_2 carries the per-phoneme counts into
    # user_Cmd_Buf2, and start_new_phon drains them through do_ctrl.
    for idx, (ctrl_type, ctrl_data) in enumerate(sa.queued_commands):
        vv.CMDQueue[idx] = (ctrl_type, ctrl_data)

    fill_phon_buf_2(vv, sa)
    vv.end_Punctuation = sa.end_punctuation
    pitch_raise_and_fall(vv)
    mod_duration(vv)
    insert_closure_release(vv)
    calc_ramp_steps(vv)
    fill_pitch_buf(vv)
    # Mod_Duration advanced songIndex and markerIndex as scratch bookkeeping
    # while assigning durations. Synthesis reads the score and the marker table
    # from the start again, so rewind both (BackEnd.c:4188-4189).
    vv.songIndex = vv.lastSongIndex
    vv.markerIndex = 0

    n = vv.phonBuf_2_In_Index
    pn = vv.pitchBuf_In_Index
    return PhonemePlan(
        phonemes=vv.phon_Buf_2[:n],
        ctrls=vv.phon_Ctrl_Buf_2[:n],
        durs=vv.dur_Buf[:n],
        pitch_freq=vv.pitch_Buf_Freq[:pn],
        pitch_time=vv.pitch_Buf_Time[:pn],
        pitch_flags=vv.pitch_Buf_Flags[:pn],
        end_punctuation=vv.end_Punctuation,
    )


def synthesize_text(voice_dict: Voice, text: str) -> bytes:
    """Synthesize English text into raw 16-bit mono PCM audio.

    Text is split on `. , ! ?` -- a comma included, because a comma ends a
    `Collect_FE_Tokens` cycle exactly as a period does (`BackEnd.c:3991-4006`).
    One English sentence containing a comma is therefore assembled as two
    clauses, spoken without a seam.

    Every clause shares one `VoiceVar` and one frame loop, mirroring `Talk()`
    (`BackEnd.c:4264-4298`): `Start_Talk` runs once, and each later clause
    re-enters `ParseSentence` alone. Re-running `Start_Talk` per clause would
    reset the formant control blocks mid-utterance. Pitch and a singing voice's
    note position do restart at each clause, because `ParseSentence` resets
    them on every call.
    """
    clauses = split_clauses(text)
    if not clauses:
        clauses = [text]

    vv = new_voice(voice_dict)
    for i, clause in enumerate(clauses):
        build_phoneme_plan(voice_dict, clause, vv=vv)
        start_new_pitch_clause(vv)
        vv.cur_PhonBuf_Index_CF = 0
        if i == 0:
            start_talk(vv)
        else:
            vv.speakState = kSpeakNewPhon  # BackEnd.c:4230 -- no Start_Talk on later clauses
        while vv.speakState != kSpeakLastFrame:
            say_frame(vv)
            e_fill_next_frame(vv)
    say_frame(vv)

    return bytes(vv.sampleBuffer)
