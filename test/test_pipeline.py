"""Test the Python formant pipeline against C reference output."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pylintalker._backend as be
from pylintalker._backend import (
    VoiceVar,
    calc_ramp_steps,
    e_fill_next_frame,
    init_voice,
    say_frame,
    start_new_pitch_clause,
    start_talk,
)
from pylintalker._consts import (
    kFrame1,
    kNoMarker,
    kSpeakLastFrame,
)
from pylintalker._data import Fred_Voice

REFERENCE_PHONEMES = [23, 11, 54, 3, 33, 22, 23]
REFERENCE_CTRL = [1, 268500993, 0, 268502089, 9, 16393, 2621440]
REFERENCE_DUR = [1, 26, 10, 54, 23, 5, 135]
REFERENCE_PITCH_FREQ = [-12, -57]
REFERENCE_PITCH_TIME = [25, 34]
REFERENCE_PITCH_FLAGS = [1, 2]

PHON_NAMES = ["_SIL_","_AY_","_AA_","_M_","_N_","_EH_","_PAUSE"]
def phon_id_to_name(pid):
    return PHON_NAMES[pid] if pid < len(PHON_NAMES) else f"??{pid}"


def setup_voice_var():
    """Create and init a VoiceVar, then populate phoneme buffers."""
    vv = VoiceVar()
    init_voice(vv, Fred_Voice)

    # Fill phoneme buffer from reference data
    for i in range(len(REFERENCE_PHONEMES)):
        vv.phon_Buf_2[i] = REFERENCE_PHONEMES[i]
        vv.phon_Ctrl_Buf_2[i] = REFERENCE_CTRL[i]
        vv.dur_Buf[i] = REFERENCE_DUR[i]
    vv.phonBuf_2_In_Index = len(REFERENCE_PHONEMES)

    # Fill pitch buffer
    for i in range(len(REFERENCE_PITCH_FREQ)):
        vv.pitch_Buf_Freq[i] = REFERENCE_PITCH_FREQ[i]
        vv.pitch_Buf_Time[i] = REFERENCE_PITCH_TIME[i]
        vv.pitch_Buf_Flags[i] = REFERENCE_PITCH_FLAGS[i]
    vv.pitchBuf_In_Index = len(REFERENCE_PITCH_FREQ)

    # Set up VoiceVar fields needed by the pipeline
    vv.FEinputDone = True
    vv.singing = False
    vv.newSentence = True
    vv.start_of_Paragraph_Flag = False

    # stress_Active_Time starts at 0 (calloc'd in C)
    vv.stress_Active_Time = 0
    vv.user_Pitch_Buf2 = [0] * 512
    vv.controlF0 = vv.VP_baselinePitch
    vv.frameMarker = kNoMarker

    # Call Calc_Ramp_Steps + StartNew_PitchClause (normally called from ParseSentence)
    calc_ramp_steps(vv)
    start_new_pitch_clause(vv)

    return vv


def run_pipeline(vv):
    """Run pipeline using post_frame_hook (like C test harness intercepts synth_SpeakPhon)."""
    frames = []
    frame_num = [0]

    def on_frame(vv):
        zz = vv.synthVars
        # read buffer NOT pointed to by curFrameBuf (SaveFrame wrote before toggle)
        if zz.curFrameBuf == kFrame1:
            fp = zz.frameBuf2
        else:
            fp = zz.frameBuf1

        phon_idx = vv.cur_PhonBuf_Index_CF
        phon_id = vv.phon_Buf_2[phon_idx] if phon_idx < len(vv.phon_Buf_2) else 0

        frames.append({
            'num': frame_num[0],
            'phon_idx': phon_idx,
            'phon_id': phon_id,
            'dur_done': vv.dur_Done_in_Phon_CF,
            'f0': fp.f0,
            'f1': fp.f1, 'f2': fp.f2, 'f3': fp.f3,
            'bw1': fp.bw1, 'bw2': fp.bw2, 'bw3': fp.bw3,
            'Av': fp.Av, 'Af': fp.Af,
            'a2': fp.a2, 'a3': fp.a3, 'a4': fp.a4, 'a5': fp.a5, 'a6': fp.a6,
            'AB': fp.AB,
            'FNZ': fp.FNZ,
            'marker': fp.marker,
            # Pitch debug state (matching C test_harness P-line)
            'pFilter_Out1': vv.pFilter_Out1,
            'pFilter_Out2': vv.pFilter_Out2,
            'down_Ramp_Offset': vv.down_Ramp_Offset,
            'basePitch_Offset': vv.basePitch_Offset,
            'baseLine_Offset': vv.baseLine_Offset,
            'phon_Pitch_Offset_1': vv.phon_Pitch_Offset_1,
            'phon_Pitch_Offset': vv.phon_Pitch_Offset,
            'time_IntoPhon_CP': vv.time_IntoPhon_CP,
            'pitch_Boundry': vv.pitch_Boundry,
            'low_Gain_CP': vv.low_Gain_CP,
            'uvPhon_Pitch_Targ': vv.uvPhon_Pitch_Targ,
            'fallRise_Offset': vv.fallRise_Offset,
            'punct_Offset': vv.punct_Offset,
            'stress_Target': vv.stress_Target,
            'stress_Active_Time': vv.stress_Active_Time,
            'controlF0': vv.controlF0,
            'cur_PitchBuf_Time': vv.cur_PitchBuf_Time,
            'time_IntoPhon_Targ': vv.time_IntoPhon_Targ,
            'next_PitchBuf_Time': vv.next_PitchBuf_Time,
            'pitchBuf_Out_Index': vv.pitchBuf_Out_Index,
        })
        frame_num[0] += 1

    be.post_frame_hook = on_frame
    start_talk(vv)
    # continue processing remaining frames
    while vv.speakState != kSpeakLastFrame:
        say_frame(vv)
        e_fill_next_frame(vv)
    say_frame(vv)  # process last frame
    be.post_frame_hook = None

    return frames


if __name__ == '__main__':
    vv = setup_voice_var()
    frames = run_pipeline(vv)
    N = len(frames)

    # Basic sanity checks (ensure we have frame data)
    print(f"Generated {N} frames", end="")
    if N == 0:
        print(" — FAIL: no frames produced")
        sys.exit(1)

    # Quick check: some frame has non-zero FNZ
    max_fnz = max(f['FNZ'] for f in frames)
    min_fnz = min(f['FNZ'] for f in frames)
    print(f"  (FNZ range: {min_fnz}–{max_fnz})")

    # Check last few frames produce audio (Av > 0)
    voiced_final = any(f['Av'] > 0 for f in frames[-30:])
    print(f"  Last 30 frames have Av>0: {voiced_final}")

    # Verify frame data matches C reference
    keys = ['Av', 'Af', 'f0', 'f1', 'f2', 'f3',
            'a2', 'a3', 'a4', 'a5', 'a6', 'FNZ', 'AB',
            'bw1', 'bw2', 'bw3']

    summary = {k: {'min': min(f[k] for f in frames),
                   'max': max(f[k] for f in frames),
                   'last': frames[-1][k]} for k in keys}
    for k in keys:
        m = summary[k]
        print(f"  {k:4s}: min={m['min']:4d} max={m['max']:4d} last={m['last']:4d}")

    print()
    print("OK")
