"""Public synthesis API: phoneme-plan-level (`synthesize_phonemes`,
verified bit-exact against the C reference) and text-level
(`synthesize_text`, built on `_frontend`/`_assembly`/`_phonbuf2`/
`_pitchcontour`/`_moduration` -- see docs/architecture.md for exactly
which stages are ported and which residual gaps remain, e.g. no
`Morph.c`/dictionary-driven compound-noun translation, no non-punctuation
phrase-boundary detection, no embedded commands).
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
from ._consts import SamplingRate, kNoMarker, kSpeakLastFrame, kSpeakNewPhon
from ._embeddedcmd import do_ctrl, scan_bracket_commands
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
    # Do NOT force vv.singing = False here: init_voice() already derives the
    # correct value from numOfNotes (BackEnd.c's ResetVoice sets singing=true
    # when numOfNotes > 1) -- overriding it here silently broke duration
    # timing for every note-driven singing voice (PipeOrgan, Cellos,
    # GoodNews, BadNews) by routing them through Mod_Duration's non-singing
    # duration formula instead of the note-timed one. The exact same bug
    # pattern was previously found and fixed in test/test_voices.py's own
    # setup_python_voice() -- see docs/architecture.md.
    vv.newSentence = True
    vv.start_of_Paragraph_Flag = False
    vv.stress_Active_Time = 0
    vv.user_Pitch_Buf2 = [0] * 512
    vv.controlF0 = vv.VP_baselinePitch
    vv.frameMarker = kNoMarker

    # ResetVoice calls e_SetTempo(vv, vv->tempo) when numOfNotes > 1
    # (BackEnd.c:4364-4368) to populate Note_Times[], which Mod_Duration's
    # singScript/singing branches need for note-driven voices (PipeOrgan,
    # Cellos, GoodNews, BadNews). Harmless no-op for non-singing voices.
    e_set_tempo(vv, vv.tempo)

    # InsertSample (Say.c:1471-1499): for kUseSyncSnd voices (Bells/
    # Hysterical -- init_voice already set vv.sync_On_Marker=True for
    # these), the real engine reads a marker-time table out of the
    # embedded sample-audio header (Sounds.c's Bells_Sound/
    # Hysterical_Sound arrays) into vv.markerBuf/vv.lastMarkerIndex; this
    # port never plays the sample audio itself (the formant synthesizer
    # never switches glottal source), but Mod_Duration's sync_On_Marker
    # branch (_moduration.py) still needs these marker times to compute
    # the same vowel-duration adjustments and kSampleMarker/frameMarker
    # values the real engine produces -- see _data.py's Bells_Markers/
    # Hysterical_Markers (extracted directly from Sounds.c's headers).
    markers = voice_dict.get('markers')
    if markers:
        vv.markerBuf[:len(markers)] = markers
        vv.lastMarkerIndex = len(markers) - 1
    return vv


def _reset_for_clause(vv: VoiceVar) -> None:
    """Mirrors `ParseSentence`'s resets before `Fill_Phon_Buf_2`
    (`BackEnd.c:4167-4178`): every one of these fields is unconditionally
    reset at the START of each clause/sentence cycle, even when reusing
    the same `VoiceVar` across clauses (as `build_phoneme_plan`/
    `synthesize_text` do) -- not just when a fresh `VoiceVar` is created.
    """
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
    `pylintalker._phonemes` for the ids). The `pitch_*` lists are likewise
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
    phoneme sequence (see ``pylintalker._phonemes`` for phoneme ids). ``pitch_*``
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
    """Build a `(phonemes, ctrls, durs, pitch_freq, pitch_time, pitch_flags,
    end_punctuation)` plan from English text, matching `ParseSentence`'s
    real pipeline order:
    `Collect_FE_Tokens -> Fill_Phon_Buf_2 -> Pitch_RaiseAndFall ->
    Mod_Duration -> synth_AdjustPhons2(Insert_Closure_Release) ->
    Calc_Ramp_Steps -> Fill_Pitch_Buf`.

    Verified bit-exact against the C reference for plain single-sentence
    text on dictionary and rule-fallback words alike (see
    `test/test_assembly_pipeline.py`, `test/test_pitchbuf.py`). Known gaps
    (see docs/architecture.md "Known gaps"): no `Morph.c` compound-noun/
    dictionary-decode translation, no embedded commands (`Morph.c`'s SEP6
    content-word/function-word transition IS approximated, see
    `_assembly.py`). `text` is treated as ONE clause -- for multi-clause
    input, use `synthesize_text()`, which splits on clause-terminal
    punctuation and calls this once per clause (see its docstring for
    exactly how state is shared across clauses).

    ``vv``, if given, is reused instead of creating a fresh one -- pass the
    SAME `VoiceVar` across multiple clauses of one utterance (as
    `synthesize_text` does) to preserve state the real engine's
    `ParseSentence` keeps across calls within one `Talk()` session (e.g.
    formant-synthesis/frame-buffer state -- NOT reset per clause the way a
    fresh `VoiceVar` would). `_reset_for_clause` is always applied first,
    mirroring the resets `ParseSentence` itself makes unconditionally at
    the start of every call (`BackEnd.c:4167-4178`), whether or not `vv`
    is fresh.
    """
    if vv is None:
        vv = new_voice(voice_dict)
    _reset_for_clause(vv)

    commands = scan_bracket_commands(text, initial_rate=vv.speech_Rate)
    if commands.queued:
        # The real engine positions each command's effect at a specific
        # phoneme, via an opcode embedded in phon_Buf_1 (StuffBECommand/
        # Parse_Embedded_Command). This pipeline has no equivalent slot, so
        # the command applies at the start of the clause instead of before
        # the word it was written in front of.
        idx = vv.cmdBufCount + vv.ctrlCount
        for _word_index, ctrl_type, ctrl_data in commands.queued:
            vv.CMDQueue[idx] = (ctrl_type, ctrl_data)
            idx += 1
            vv.ctrlCount += 1
        do_ctrl(vv)
    if commands.final_rate is not None:
        # vv->lastRate is a single persistent field, not reset per clause, so
        # a later clause's rate/ratr resolves against this baseline.
        vv.speech_Rate = commands.final_rate

    sa = collect_fe_tokens(commands.text, commands)
    fill_phon_buf_2(vv, sa)
    vv.end_Punctuation = sa.end_punctuation
    pitch_raise_and_fall(vv)
    mod_duration(vv)
    insert_closure_release(vv)
    calc_ramp_steps(vv)
    fill_pitch_buf(vv)
    # ParseSentence's final step (BackEnd.c:4188): Mod_Duration advances
    # songIndex as scratch bookkeeping while assigning note-driven
    # durations, but synthesis (DoNote/DoNoteScript, called per-phon
    # during say_frame) must read notes starting from the beginning of
    # the song again -- confirmed missing via direct comparison against
    # the C reference: a shared VoiceVar across clauses left songIndex at
    # its post-Mod_Duration value (e.g. 11 instead of 0), corrupting
    # every note pitch for the rest of a singing voice's clause.
    vv.songIndex = vv.lastSongIndex
    # ParseSentence's other final-reset field (BackEnd.c:4189): Mod_Duration's
    # sync_On_Marker branch (kUseSyncSnd voices, Bells/Hysterical) also
    # advances markerIndex as scratch bookkeeping while computing
    # vowel-duration adjustments against the marker-time table -- exactly
    # the same songIndex-class bug, confirmed the same way (a shared
    # VoiceVar left markerIndex advanced instead of 0 by the time
    # synthesis's own marker lookup, StartNewPhon, ran).
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
    """Synthesize English text (one or more clauses/sentences) into raw
    16-bit PCM audio. See `build_phoneme_plan` for the single-clause
    pipeline this composes, and its known gaps.

    Input is split on `. , ! ?` (`_frontend.split_clauses`) -- NOT just
    sentence-terminal `. ! ?`: confirmed, by reading `BackEnd.c:3991-4006`,
    that a comma ends a `Collect_FE_Tokens` cycle exactly the same way a
    period/`!`/`?` does, so what reads as one English sentence containing
    a comma is actually assembled by the real engine as two separate
    `Collect_FE_Tokens`/`ParseSentence` cycles, continuing seamlessly
    within one audio stream.

    ALL clauses of one `synthesize_text` call share a SINGLE `VoiceVar`
    and a single `start_talk`/frame loop, matching `Talk()`'s real
    structure (`BackEnd.c:4264-4298`): `Start_Talk` runs once, and
    `ParseSentence` is simply called again for each subsequent clause
    (`e_Fill_Next_Frame`, `BackEnd.c:4224-4231`) -- it does NOT re-run
    `Start_Talk`/`synth_Start_Talk`, which would reset the formant control
    blocks and frame-buffer state (`init_control_blocks`,
    `_backend.synth_start_talk`) mid-utterance. `build_phoneme_plan`
    reapplies `_reset_for_clause`'s `ParseSentence`-equivalent resets
    (including `songIndex`) for every clause, so pitch/portamento and a
    singing voice's note position DO restart at each clause boundary --
    matching the real engine's own behavior, since `ParseSentence`
    unconditionally sets `vv->newSentence = true` and resets `songIndex`
    to 0 every call too. This function is verified frame-exact against
    the C reference across ordinary and note-driven singing voices alike
    (`test/test_synthesize_text.py`), including comma-containing sentences
    that previously caused an audible glitch on singing voices (see
    docs/architecture.md's former "Known gaps" entry for that bug).
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
