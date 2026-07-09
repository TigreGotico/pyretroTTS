"""Public phoneme-level synthesis API.

This is the layer that is actually working today: given an already-built
phoneme plan (phoneme ids, control words, durations, and an optional pitch
contour) plus a voice definition dict, it drives the ported formant
synthesizer (:mod:`lintalker._backend`) and returns 16-bit PCM audio.

There is no English text-to-phoneme frontend yet (that requires porting
Morph.c/FrontEnd.c/EngToP.c and the english_lex dictionary from the C
reference) — see the package README for status. Until that lands, callers
must supply phoneme plans themselves.
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
