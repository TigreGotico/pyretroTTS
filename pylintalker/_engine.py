"""Top-level engine controls: rate, pitch, volume, tempo, pause and resume.

Port of Engine.c, a thin dispatch layer over the synthesizer in `_backend.py`.
Text is spoken through `api.synthesize_text`, not from here: Engine.c's
e_SpeakBuffer/e_UseVoice/e_ResetParams entry points reach into FrontEnd.c and
fsynth.c, whose jobs `api.py` and `_backend.init_voice` do instead.
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
    kMIDI_50HZ,
    kNoError,
    kNormal,
    kOneTwelfth,
    kPaused,
    kPointFive,
    kStopped,
)

# ---------------------------------------------------------------------------
# Error codes (SpeechEqu.h, mirrored in _consts.py)
# ---------------------------------------------------------------------------
# kNoError, kParamError, synthNotReady, kNothingToSpeak already in _consts.py

kBPM_NOTE = 4  # 16th note divisor used by e_SetTempo's kBPM macro


def init_the_globals(vv: VoiceVar) -> None:
    """InitTheGlobals (Engine.c). VoiceVar.__init__ already binds the lookup
    tables (SetTblAddr's job), leaving only these two fields."""
    vv.starting_New_Phon = False
    e_set_tempo(vv, 120)  # default tempo = 120 bpm


def e_open_speech_channel(vv: VoiceVar) -> int:
    """e_OpenSpeechChannel (Engine.c): ready a voice for speaking.

    The letter-to-sound rules Engine.c wires up here are owned by `_engtop.py`
    instead, so only the channel state is set.
    """
    vv.Busy = False
    init_the_globals(vv)
    return kNoError


def e_stop_speech_at(vv: VoiceVar, where_to_pause: int = 0) -> None:
    """e_StopSpeechAt (Engine.c): halt output at the next frame boundary."""
    vv.outputPaused = True
    vv.speechState = kStopped


def e_pause_speech_at(vv: VoiceVar, where_to_pause: int = 0) -> None:
    """e_PauseSpeechAt (Engine.c). Saves the playback position into the
    *_Save1 fields, so e_continue_speech can pick it back up."""
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
    """e_ContinueSpeech (Engine.c). Restores the position e_pause_speech_at
    saved and resumes the frame loop."""
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



def e_get_speech_status(vv: VoiceVar) -> dict:
    """e_GetSpeechStatus (Engine.c), returning a dict rather than filling a
    caller-supplied SpeechStatusInfo struct."""
    return {
        "outputBusy": vv.Busy if vv.speechState != kStopped else False,
        "outputPaused": vv.speechState == kPaused,
        "phonemeCode": 0,
    }


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
    """e_SetSpeechRate (Engine.c:567-580). A singing voice's rate is its
    tempo in beats per minute; everything else is words per minute."""
    if vv.singing:
        vv.tempo = info >> 16
        e_set_tempo(vv, vv.tempo)
    else:
        vv.speech_Rate = info >> 16
        init_rate_params(vv)


def e_set_speech_pitch(vv: VoiceVar, info: int) -> None:
    """e_SetSpeechPitch (Engine.c). Takes a MIDI note in 00nn.ff00 fixed point."""
    param = info >> 8
    if param < kMIDI_50HZ:
        param = 0
    else:
        param -= kMIDI_50HZ
    vv.voiceNaturalPitch = ((param * kOneTwelfth) + kPointFive) >> 16
    vv.VP_baselinePitch = vv.voiceNaturalPitch


def e_set_speech_volume(vv: VoiceVar, info: int) -> None:
    """e_SetSpeechVolume (Engine.c) -> `_backend.synth_set_volume`."""
    synth_set_volume(vv, info)


def e_set_speech_mod(vv: VoiceVar, info: int) -> None:
    """e_SetSpeechMod (Engine.c). Pure arithmetic, fully portable."""
    if info < 0:
        info = 0
    elif info > (100 << 16):
        info = 100 << 16
    vv.VP_pitchRange = info // 50





def e_set_tempo(vv: VoiceVar, tempo: int) -> None:
    """e_SetTempo (Engine.c). Builds the Note_Times[] table that singing
    voices read their note durations from."""
    kBPM = ((60 // 4) * 1000) // kFrameTime  # milliseconds (4 = 16th note)

    if tempo < 20:
        tempo = 20
    elif tempo > 240:
        tempo = 240

    vv.tempo = tempo
    note_16th = kBPM // tempo

    vv.Note_Times[0] = note_16th  # NOT USED (per C comment)
    j = note_16th
    i = 1
    while i < 12:
        vv.Note_Times[i] = j
        i += 1
        vv.Note_Times[i] = j + (j >> 1)  # dotted note
        j <<= 1
        i += 1
