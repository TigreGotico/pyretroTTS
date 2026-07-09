"""Public synthesis API: phoneme-plan-level (`synthesize_phonemes`,
verified bit-exact against the C reference) and text-level
(`synthesize_text`, built on `_frontend`/`_assembly`/`_phonbuf2`/
`_pitchcontour`/`_moduration` -- see docs/architecture.md for exactly
which stages are ported and which residual gaps remain, e.g. no
`Morph.c`/dictionary-driven compound-noun translation, no non-punctuation
phrase-boundary detection, no embedded commands).
"""
from __future__ import annotations

import struct
import wave
from typing import Iterable, Optional

from ._backend import (
    VoiceVar,
    calc_ramp_steps,
    e_fill_next_frame,
    say_frame,
    start_new_pitch_clause,
    start_talk,
)
from ._backend import init_voice
from ._consts import SamplingRate, kNoMarker, kSpeakLastFrame


def new_voice(voice_dict: dict) -> VoiceVar:
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
    from ._engine import e_set_tempo
    e_set_tempo(vv, vv.tempo)
    return vv


def synthesize_phonemes(
    voice_dict: dict,
    phonemes: Iterable[int],
    ctrls: Iterable[int],
    durs: Iterable[int],
    pitch_freq: Iterable[int] = (),
    pitch_time: Iterable[int] = (),
    pitch_flags: Iterable[int] = (),
    vv: Optional[VoiceVar] = None,
    end_punctuation: int = 0,
) -> bytes:
    """Synthesize a phoneme plan into raw 16-bit PCM audio (little-endian, mono).

    ``phonemes``/``ctrls``/``durs`` are parallel arrays describing the
    phoneme sequence (see ``lintalker._phonemes`` for phoneme ids). ``pitch_*``
    describe an optional pitch contour overlay, as produced by the C
    reference's frontend.

    ``end_punctuation`` must be the same value `build_phoneme_plan` computed
    for this plan (its 7th return value) whenever the plan came from real
    text ending in a comma or question mark: `Calc_Ramp_Steps`
    (`BackEnd.c:678-739`) halves the pitch decline ramp step for those two
    terminators, and it reads `vv->end_Punctuation` directly, not something
    derived from the phoneme/ctrl arrays -- omitting it silently doubles the
    pitch decline rate for the whole clause. This was a real, confirmed bug:
    `build_phoneme_plan`'s own internal `VoiceVar` set `end_Punctuation`
    correctly before running its own `Calc_Ramp_Steps` pass, but that value
    never reached the SEPARATE `VoiceVar` this function creates for the
    actual synthesis pass, which re-runs `Calc_Ramp_Steps` from scratch with
    `end_Punctuation` still at its default (0) -- affecting every
    comma-containing or yes/no-question sentence, on every voice.
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

    for i, (p, c, d) in enumerate(zip(phonemes, ctrls, durs)):
        vv.phon_Buf_2[i] = p
        vv.phon_Ctrl_Buf_2[i] = c
        vv.dur_Buf[i] = d
    vv.phonBuf_2_In_Index = len(phonemes)

    for i, (f, t, fl) in enumerate(zip(pitch_freq, pitch_time, pitch_flags)):
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


def pcm_to_wav(pcm: bytes, path: str, sample_rate: int = SamplingRate) -> str:
    """Write raw 16-bit mono PCM to a WAV file. Returns the path."""
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return path


def build_phoneme_plan(voice_dict: dict, text: str):
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
    dictionary-decode translation, no non-punctuation phrase-boundary
    detection (e.g. a narrow `kBND_Sep6` gap on certain dictionary-tagged
    words), no embedded commands. `text` is treated as ONE sentence --
    for multi-sentence input, use `synthesize_text()`, which splits on
    sentence-terminal punctuation and calls this once per sentence (see
    its docstring for what that approximates and doesn't).
    """
    from ._assembly import collect_fe_tokens
    from ._phonbuf2 import fill_phon_buf_2, insert_closure_release
    from ._pitchcontour import pitch_raise_and_fall
    from ._moduration import mod_duration
    from ._pitchbuf import fill_pitch_buf

    sa = collect_fe_tokens(text)
    vv = new_voice(voice_dict)
    fill_phon_buf_2(vv, sa)
    vv.end_Punctuation = sa.end_punctuation
    pitch_raise_and_fall(vv)
    mod_duration(vv)
    insert_closure_release(vv)
    calc_ramp_steps(vv)
    fill_pitch_buf(vv)

    n = vv.phonBuf_2_In_Index
    pn = vv.pitchBuf_In_Index
    return (
        vv.phon_Buf_2[:n], vv.phon_Ctrl_Buf_2[:n], vv.dur_Buf[:n],
        vv.pitch_Buf_Freq[:pn], vv.pitch_Buf_Time[:pn], vv.pitch_Buf_Flags[:pn],
        vv.end_Punctuation,
    )


def synthesize_text(voice_dict: dict, text: str) -> bytes:
    """Synthesize English text (one or more clauses/sentences) into raw
    16-bit PCM audio. See `build_phoneme_plan` for the single-clause
    pipeline this composes, and its known gaps.

    Input is split on `. , ! ?` (`_frontend.split_clauses`) -- NOT just
    sentence-terminal `. ! ?` -- and each clause is synthesized
    independently (a fresh `VoiceVar`/baseline pitch per clause) via
    `build_phoneme_plan` + `synthesize_phonemes`, then the PCM is
    concatenated. Splitting on commas too is not an approximation: it's
    confirmed, by reading `BackEnd.c:3991-4006`, to be what the real
    engine's `Collect_FE_Tokens` itself does -- a comma sets
    `gotSentence = true` and returns exactly the same way a period/`!`/`?`
    does, so what reads as one English sentence containing a comma is
    actually assembled by the real engine as two separate
    `Collect_FE_Tokens`/`ParseSentence` cycles, continuing seamlessly
    within one audio stream. Splitting on commas here was added after a
    frame-level comparison against the C reference found a genuine frame
    COUNT mismatch on comma-containing sentences when the whole thing was
    assembled as a single clause -- not merely a small numeric drift.

    What IS still an approximation, not a bit-exact port: the C reference
    keeps one `Talk()` session alive across ALL clause/sentence boundaries
    within a single `_SpeakBuffer` call (baseline pitch and compound-noun
    state persist from one clause to the next; `Collect_FE_Tokens`/
    `ParseSentence` are simply called again, mid-playback, reusing the
    same `VoiceVar`), whereas this function uses an independently-reset
    `VoiceVar` per clause. This means cross-clause prosody continuity
    (the pitch baseline carrying over, rather than resetting) is not
    preserved -- verified via `test/test_synthesize_text.py`'s frame-level
    comparisons, which pass for comma-containing sentences (frame count
    and per-frame formant state now match) but were not specifically
    checked for pitch-contour continuity across the clause boundary itself.
    """
    from ._frontend import split_clauses

    clauses = split_clauses(text)
    if not clauses:
        clauses = [text]

    pcm_chunks = []
    for clause in clauses:
        phonemes, ctrls, durs, pitch_freq, pitch_time, pitch_flags, end_punctuation = build_phoneme_plan(voice_dict, clause)
        pcm_chunks.append(synthesize_phonemes(
            voice_dict, phonemes, ctrls, durs, pitch_freq, pitch_time, pitch_flags,
            end_punctuation=end_punctuation,
        ))
    return b"".join(pcm_chunks)
