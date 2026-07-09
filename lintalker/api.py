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
    vv.singing = False
    vv.newSentence = True
    vv.start_of_Paragraph_Flag = False
    vv.stress_Active_Time = 0
    vv.user_Pitch_Buf2 = [0] * 512
    vv.controlF0 = vv.VP_baselinePitch
    vv.frameMarker = kNoMarker
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
) -> bytes:
    """Synthesize a phoneme plan into raw 16-bit PCM audio (little-endian, mono).

    ``phonemes``/``ctrls``/``durs`` are parallel arrays describing the
    phoneme sequence (see ``lintalker._phonemes`` for phoneme ids). ``pitch_*``
    describe an optional pitch contour overlay, as produced by the C
    reference's frontend.
    """
    phonemes = list(phonemes)
    ctrls = list(ctrls)
    durs = list(durs)
    pitch_freq = list(pitch_freq)
    pitch_time = list(pitch_time)
    pitch_flags = list(pitch_flags)

    if vv is None:
        vv = new_voice(voice_dict)

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
    """Build a `(phonemes, ctrls, durs, pitch_freq, pitch_time, pitch_flags)`
    plan from English text, matching `ParseSentence`'s real pipeline order:
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
    )


def synthesize_text(voice_dict: dict, text: str) -> bytes:
    """Synthesize English text (one or more sentences) into raw 16-bit PCM
    audio. See `build_phoneme_plan` for the single-sentence pipeline this
    composes, and its known gaps.

    Multi-sentence input is split on sentence-terminal punctuation
    (`_frontend.split_sentences`) and each sentence is synthesized
    independently (a fresh `VoiceVar`/baseline pitch per sentence) via
    `build_phoneme_plan` + `synthesize_phonemes`, then the PCM is
    concatenated. This is a documented approximation, not a port of the
    real engine's multi-sentence handling: the C reference keeps one
    `Talk()` session alive across sentence boundaries within a single
    `_SpeakBuffer` call (baseline pitch and compound-noun state persist
    from one sentence to the next; `Collect_FE_Tokens`/`ParseSentence`
    are simply called again, mid-playback, once the current sentence's
    phoneme buffer is exhausted -- confirmed by inspection: feeding
    multi-sentence text to the real `test_harness` CLI only ever dumps one
    sentence's worth of `phon_Buf_2` at a time, i.e. the real engine also
    processes one sentence's plan at a time, just within one continuous
    frame loop rather than independently-reset `VoiceVar`s). This port's
    approximation will sound like a sequence of independently-intoned
    sentences rather than one continuous utterance with cross-sentence
    prosody -- it has not been validated against the C reference at the
    frame level for multi-sentence input the way single-sentence text is
    (`test/test_synthesize_text.py`).
    """
    from ._frontend import split_sentences

    sentences = split_sentences(text)
    if not sentences:
        sentences = [text]

    pcm_chunks = []
    for sentence in sentences:
        phonemes, ctrls, durs, pitch_freq, pitch_time, pitch_flags = build_phoneme_plan(voice_dict, sentence)
        pcm_chunks.append(synthesize_phonemes(voice_dict, phonemes, ctrls, durs, pitch_freq, pitch_time, pitch_flags))
    return b"".join(pcm_chunks)
