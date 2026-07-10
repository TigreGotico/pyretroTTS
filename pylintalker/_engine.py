"""
Top-level engine API: init/reset/speak/status/rate/pitch/volume controls.

Port of Engine.c. Engine.c is a thin dispatch layer: it wires together
functions that either already live in ``_backend.py`` (ported from
Fsynth.c/BackEnd.c/formantSynth.c) or that would live in the *not yet
ported* FrontEnd.c (text parsing/tokenization -> phoneme-buffer filling).

What's real here (faithfully ported, same names/shapes as Engine.c):
    e_set_tempo, e_get_speech_rate/pitch/volume/mod, e_set_speech_rate/
    pitch/volume/mod, e_pause_speech_at, e_continue_speech,
    e_get_speech_status, e_stop_speech_at, e_reinit_voice, InitTheGlobals
    equivalent (init_the_globals), e_open_speech_channel skeleton.

What's stubbed (raises NotImplementedError if actually called), and why:
    * `e_start_parse` (FrontEnd.c `e_StartParse`) -- text tokenization,
      number/abbreviation/punctuation normalization, and dictionary lookup
      via `english_lex`. None of FrontEnd.c is ported. This is the only
      thing standing between "phoneme plan in" (fully working today via
      `_backend.py`) and "raw text in".
    * `Init_Rate_Params`, `ResetVoice`, `NewVoice`, `Start_Talk` (as a
      *voice-swap* operation) -- these are fsynth.c functions Engine.c
      calls directly that are NOT present in `_backend.py` under any name
      (only `init_voice`, `start_talk`, `start_new_pitch_clause`,
      `synth_set_volume` are ported, and they cover a different slice of
      fsynth.c than what `e_SetSpeechRate`/`e_ResetParams`/`e_UseVoice`
      need). Calling `e_set_speech_rate` in the non-singing branch, or
      `e_reinit_voice`/`e_use_voice`, will raise NotImplementedError with a
      clear message pointing at the missing upstream function.

To exercise this module standalone (no FrontEnd.c/Morph.c/english_lex),
skip `e_speak_buffer` (which requires `e_start_parse`) and instead fill
`vv.phon_Buf_2`/`vv.phon_Ctrl_Buf_2`/`vv.dur_Buf` directly -- exactly what
tests/test_voices.py already does when comparing `_backend.py` against the
C harness's extracted sentence plan -- then call `start_talk`/
`e_fill_next_frame` from `_backend.py` as usual. `e_open_speech_channel`,
`e_set_tempo`, `e_get_speech_status`, `e_pause_speech_at`/
`e_continue_speech`, and the rate/pitch/volume/mod getters and setters
(mod branch, singing-rate branch) all work today without any FrontEnd.c
dependency.
"""
from __future__ import annotations

from ._backend import (
    VoiceVar,
    init_rate_params,
    start_talk,
    synth_set_volume,
)
from ._consts import (
    kFrameTime,
    kImmediate,
    kMIDI_50HZ,
    kNoError,
    kNormal,
    kNoSpeechInterrupt,
    kNothingToSpeak,
    kOneTwelfth,
    kPaused,
    kPointFive,
    kStopped,
    synthNotReady,
)

# ---------------------------------------------------------------------------
# Error codes (SpeechEqu.h, mirrored in _consts.py)
# ---------------------------------------------------------------------------
# kNoError, kParamError, synthNotReady, kNothingToSpeak already in _consts.py

kBPM_NOTE = 4  # 16th note divisor used by e_SetTempo's kBPM macro


def init_the_globals(vv: VoiceVar) -> None:
    """InitTheGlobals (Engine.c). Table pointers are already wired onto
    VoiceVar by its own __init__ in _backend.py (SetTblAddr's job), so this
    only needs to set the two fields Engine.c sets explicitly."""
    vv.starting_New_Phon = False
    e_set_tempo(vv, 120)  # default tempo = 120 bpm


def e_open_speech_channel(vv: VoiceVar) -> int:
    """e_OpenSpeechChannel (Engine.c).

    The real function also points vv->hash/vv->rule into vv->Rules (the
    letter-to-sound rule blob) and calls the front-end's e_InitFE via a
    function-pointer table -- neither of those exist in this port (rule
    hookup lives in _engtop.py instead, and there is no FrontEnd.c port to
    init). This just sets the fields Engine.c sets directly on vv.
    """
    vv.Busy = False
    init_the_globals(vv)
    return kNoError


def e_stop_speech_at(vv: VoiceVar, where_to_pause: int = 0) -> None:
    """e_StopSpeechAt (Engine.c). The real e_AbortParse (FrontEnd.c) call
    is skipped -- there is no in-flight front-end parse to abort in this
    port; only backend/frame-fill state is stopped."""
    vv.outputPaused = True
    vv.speechState = kStopped


def e_pause_speech_at(vv: VoiceVar, where_to_pause: int = 0) -> None:
    """e_PauseSpeechAt (Engine.c). Saves backend playback-position state
    into the *_Save1 fields, exactly as in C."""
    vv.outputPaused = True
    vv.speechState = kPaused
    vv.Busy = False

    vv.lastWordStart = vv.nLastWordStart
    vv.pFilter_Out1_Save1 = vv.pFilter_Out1_Save2
    vv.pFilter_Out2_Save1 = vv.pFilter_Out2_Save2
    vv.down_Ramp_Offset_Save1 = vv.down_Ramp_Offset_Save2
    vv.fallRise_Offset_Save1 = vv.fallRise_Offset_Save2
    vv.fallRise1_Offset_Save1 = vv.fallRise1_Offset_Save2
    vv.stress_Target_Save1 = vv.stress_Target_Save2
    vv.punct_Offset_Save1 = vv.punct_Offset_Save2

    vv.next_PitchBuf_Time_Save1 = vv.next_PitchBuf_Time_Save2
    vv.phon_Index_Targ_Save1 = vv.phon_Index_Targ_Save2
    vv.phon_Index_CP_Save1 = vv.phon_Index_CP_Save2
    vv.pitchBuf_Out_Index_Save1 = vv.pitchBuf_Out_Index_Save2
    vv.time_IntoPhon_CP_Save1 = vv.time_IntoPhon_CP_Save2
    vv.cur_Phon_Dur_CC_Save1 = vv.cur_Phon_Dur_CC_Save2
    vv.cur_PhonDur_CP_Save1 = vv.cur_PhonDur_CP_Save2
    vv.time_IntoPhon_Targ_Save1 = vv.time_IntoPhon_Targ_Save2
    vv.cur_PitchBuf_Time_Save1 = vv.cur_PitchBuf_Time_Save2
    vv.cmdBufCount_Save1 = vv.cmdBufCount_Save2
    vv.songIndex_Save1 = vv.songIndex_Save2
    vv.VP_baselinePitch_Save1 = vv.VP_baselinePitch_Save2


def e_continue_speech(vv: VoiceVar) -> None:
    """e_ContinueSpeech (Engine.c). Restores backend playback-position
    state from the *_Save2 fields and resumes via start_talk (_backend.py)."""
    if vv.outputPaused and vv.speechState == kPaused:
        vv.outputPaused = False
        vv.speechState = kNormal
        vv.Busy = True

        vv.cur_PhonBuf_Index_CF = vv.nLastWordStart

        vv.pFilter_Out1 = vv.pFilter_Out1_Save2
        vv.pFilter_Out2 = vv.pFilter_Out2_Save2
        vv.down_Ramp_Offset = vv.down_Ramp_Offset_Save2
        vv.fallRise_Offset = vv.fallRise_Offset_Save2
        vv.fallRise1_Offset = vv.fallRise1_Offset_Save2
        vv.stress_Target = vv.stress_Target_Save2
        vv.punct_Offset = vv.punct_Offset_Save2

        vv.next_PitchBuf_Time = vv.next_PitchBuf_Time_Save2
        vv.phon_Index_Targ = vv.phon_Index_Targ_Save2
        vv.phon_Index_CP = vv.phon_Index_CP_Save2
        vv.pitchBuf_Out_Index = vv.pitchBuf_Out_Index_Save2
        vv.time_IntoPhon_CP = vv.time_IntoPhon_CP_Save2
        vv.cur_Phon_Dur_CC = vv.cur_Phon_Dur_CC_Save2
        vv.cur_PhonDur_CP = vv.cur_PhonDur_CP_Save2
        vv.time_IntoPhon_Targ = vv.time_IntoPhon_Targ_Save2
        vv.cur_PitchBuf_Time = vv.cur_PitchBuf_Time_Save2
        vv.cmdBufCount = vv.cmdBufCount_Save2
        vv.songIndex = vv.songIndex_Save2
        vv.VP_baselinePitch = vv.VP_baselinePitch_Save2

        start_talk(vv)


def e_speak_buffer(vv: VoiceVar, text_buf, byte_len: int, control_flags: int) -> int:
    """e_SpeakBuffer (Engine.c).

    STUBBED: real body calls e_StartParse (FrontEnd.c, not ported) then
    Talk (BackEnd.c -- also not ported as a single "run the whole plan"
    entry point in _backend.py; callers currently drive start_talk() /
    e_fill_next_frame() manually per tests/test_voices.py). This function
    is kept only to document the control-flow Engine.c uses around it
    (busy/interrupt checks) and will raise if actually invoked.
    """
    if not (control_flags & kNoSpeechInterrupt):
        if vv.Busy:
            e_stop_speech_at(vv, kImmediate)
    elif vv.Busy:
        return synthNotReady

    if not text_buf or len(text_buf) == 0:
        return kNothingToSpeak

    vv.Busy = True
    raise NotImplementedError(
        "e_speak_buffer requires e_StartParse (FrontEnd.c) and Talk "
        "(BackEnd.c), neither of which is ported. Fill vv.phon_Buf_2 / "
        "vv.phon_Ctrl_Buf_2 / vv.dur_Buf directly and call "
        "pylintalker._backend.start_talk()/e_fill_next_frame() instead."
    )


def e_get_speech_status(vv: VoiceVar) -> dict:
    """e_GetSpeechStatus (Engine.c). Returns a dict instead of filling a
    caller-supplied SpeechStatusInfo* struct."""
    status = {}
    if getattr(vv, "speechState", kStopped) != kStopped:
        status["outputBusy"] = vv.Busy
        status["phonemeCode"] = 0
    else:
        status["outputBusy"] = False
        status["phonemeCode"] = 0
    status["outputPaused"] = (getattr(vv, "speechState", kStopped) == kPaused)
    status["inputBytesLeft"] = getattr(vv, "StrEOF", 0) - getattr(vv, "StrPos", 0)
    return status


def e_get_speech_rate(vv: VoiceVar) -> int:
    """e_GetSpeechRate (Engine.c). Fixed-point 0xxx.0000 (16.16)."""
    if vv.singing:
        return vv.tempo << 16
    return vv.speech_Rate << 16


def e_get_speech_pitch(vv: VoiceVar) -> int:
    """e_GetSpeechPitch (Engine.c). Fixed-point 00nn.ff00."""
    return ((vv.VP_baselinePitch * 12) + kMIDI_50HZ) << 8


def e_get_speech_volume(vv: VoiceVar) -> int:
    """e_GetSpeechVolume (Engine.c). Fixed-point 0000.xx00."""
    return vv.user_Volume << 8


def e_get_speech_mod(vv: VoiceVar) -> int:
    """e_GetSpeechMod (Engine.c). Fixed-point 0xxx.0000."""
    return vv.VP_pitchRange * 50


def e_set_speech_rate(vv: VoiceVar, info: int) -> None:
    """e_SetSpeechRate (Engine.c:567-580). Pure fixed-point arithmetic,
    fully portable -- `Init_Rate_Params` (`BackEnd.c:4303-4327`, not
    `fsynth.c` as a previous pass of this docstring incorrectly claimed)
    is itself pure arithmetic with no missing dependency, ported as
    `_backend.init_rate_params` and reused here."""
    if vv.singing:
        vv.tempo = info >> 16
        e_set_tempo(vv, vv.tempo)
    else:
        vv.speech_Rate = info >> 16
        init_rate_params(vv)


def e_set_speech_pitch(vv: VoiceVar, info: int) -> None:
    """e_SetSpeechPitch (Engine.c). Pure fixed-point arithmetic, fully
    portable -- no missing dependency."""
    param = info >> 8
    if param < kMIDI_50HZ:
        param = 0
    else:
        param -= kMIDI_50HZ
    vv.voiceNaturalPitch = ((param * kOneTwelfth) + kPointFive) >> 16
    vv.VP_baselinePitch = vv.voiceNaturalPitch


def e_set_speech_volume(vv: VoiceVar, info: int) -> None:
    """e_SetSpeechVolume (Engine.c) -> SetVolume (fsynth.c), which _is_
    ported as synth_set_volume in _backend.py."""
    synth_set_volume(vv, info)


def e_set_speech_mod(vv: VoiceVar, info: int) -> None:
    """e_SetSpeechMod (Engine.c). Pure arithmetic, fully portable."""
    if info < 0:
        info = 0
    elif info > (100 << 16):
        info = 100 << 16
    vv.VP_pitchRange = info // 50


def e_reset_params(vv: VoiceVar) -> None:
    """e_ResetParams (Engine.c).

    STUBBED: real code calls e_ResetFE (FrontEnd.c, not ported) and
    ResetVoice (fsynth.c, not ported in _backend.py under any name).
    """
    raise NotImplementedError(
        "e_reset_params requires e_ResetFE (FrontEnd.c) and ResetVoice "
        "(fsynth.c), neither of which is ported."
    )


def e_use_voice(vv: VoiceVar, voice_dict: dict) -> int:
    """e_UseVoice (Engine.c).

    STUBBED: real code calls synth_Init (function-pointer table, fsynth.c)
    then NewVoice (fsynth.c). _backend.py's init_voice() covers a
    different, larger slice of NewVoice's job (it is used directly by
    tests/test_voices.py to load a voice dict), but the exact split of
    responsibilities between synth_Init/NewVoice/init_voice was not
    possible to confirm without the fsynth.c port, so this is left
    stubbed rather than guessed.
    """
    raise NotImplementedError(
        "e_use_voice requires synth_Init + NewVoice (fsynth.c); use "
        "pylintalker._backend.init_voice(vv, voice_dict) directly instead."
    )


def e_reinit_voice(vv: VoiceVar) -> None:
    """e_ReinitVoice (Engine.c) -> ResetVoice (fsynth.c, not ported)."""
    raise NotImplementedError(
        "e_reinit_voice requires ResetVoice (fsynth.c), which is not "
        "ported in _backend.py."
    )


def e_set_tempo(vv: VoiceVar, tempo: int) -> None:
    """e_SetTempo (Engine.c). Fully portable -- pure arithmetic building
    the Note_Times[] duration table used by singing mode."""
    kBPM = ((60 // 4) * 1000) // kFrameTime  # milliseconds (4 = 16th note)

    if tempo < 20:
        tempo = 20
    elif tempo > 240:
        tempo = 240

    vv.tempo = tempo
    note_16th = kBPM // tempo

    if not hasattr(vv, "Note_Times"):
        vv.Note_Times = [0] * 16  # mt4.h: short Note_Times[16]

    vv.Note_Times[0] = note_16th  # NOT USED (per C comment)
    j = note_16th
    i = 1
    while i < 12:
        vv.Note_Times[i] = j
        i += 1
        vv.Note_Times[i] = j + (j >> 1)  # dotted note
        j <<= 1
        i += 1
