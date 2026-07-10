"""Port of `Store_F0_and_Time` (`BackEnd.c:337-360`) and `Fill_Pitch_Buf`
(`BackEnd.c:365-671`): turns `Pitch_RaiseAndFall`'s ctrl-bit contour
(`kPitchRise`/`kPitchFall`/`kPitchRise1`/`kPitchFall1` on `phon_Buf_2`
vowels) into the actual `pitch_Buf_Freq`/`pitch_Buf_Time`/`pitch_Buf_Flags`
arrays `api.synthesize_phonemes` consumes (see `_backend.py`'s
`Interpolate_Pitch`/`start_new_pitch_clause`, which already read these).

Call order in the real `ParseSentence`: `Fill_Phon_Buf_2 ->
Pitch_RaiseAndFall -> Mod_Duration -> synth_AdjustPhons2 ->
Calc_Ramp_Steps -> Fill_Pitch_Buf -> StartNew_PitchClause`. So
`fill_pitch_buf()` should run AFTER `_moduration.mod_duration()` (it reads
`vv.dur_Buf`) and after `_backend.calc_ramp_steps()`, and should be
followed by `_backend.start_new_pitch_clause()`.

Two `#if 0`-disabled dead-code blocks in `Fill_Pitch_Buf`
(`BackEnd.c:504-511`, `600-635` -- an alternate stress-alternation scheme
and an "unstressed term vowel" boundary handler) are not ported, matching
the C reference's own compiled behavior (they never execute there either).
"""
from __future__ import annotations

from ._consts import (
    kSilenceTypeField, kSilenceTypeShift, kStressField, kSyllableTypeField,
    kVowelF, kPitchRise, kPitchFall, kPitchRise1, kPitchFall1,
    kPrimOrEmphStress, kEmphaticStress, kTerm_End, kVerb_End,
    kPitchStress_Flg, kPitchRiseFall_Flg, kPitchBoundry_Flg,
    kPhraseReset, kPitchRiseFall1_Flg, kFrameTime, kPhonBuf_Red_Zone,
    kHZ_4, kHZ_6, kHZ_7, kHZ_9, kHZ_10, kHZ_12, kHZ_14, kHZ_18, kHZ_20,
    kHZ_25, kHZ_28,
)
from ._phonemes import _Comma_, _Period_, _Quest_, _Exclam_


def store_f0_and_time(vv, pitch: int, time: int, flags: int) -> None:
    """Port of `Store_F0_and_Time` (`BackEnd.c:337-360`)."""
    if (vv.pitch_Time_Offset + time) >= 0:
        vv.pitch_Buf_Time[vv.pitchBuf_In_Index] = vv.pitch_Time_Offset + time
        vv.pitch_Time_Offset = 0 - time
    else:
        vv.pitch_Buf_Time[vv.pitchBuf_In_Index] = 0

    vv.pitch_Buf_Freq[vv.pitchBuf_In_Index] = pitch
    vv.pitch_Buf_Flags[vv.pitchBuf_In_Index] = flags

    if vv.pitchBuf_In_Index < kPhonBuf_Red_Zone:
        vv.pitchBuf_In_Index += 1


def fill_pitch_buf(vv) -> None:
    """Port of `Fill_Pitch_Buf` (`BackEnd.c:365-671`)."""
    from ._backend import e_get_phon, e_get_phon_ctrl

    pitch_is_fallen = True
    vv.pitchBuf_In_Index = 0
    stress_counter = 0
    cur_baseline = 0
    vv.pitch_Time_Offset = 0
    raise_amt = 0

    for i in range(vv.phonBuf_2_In_Index):
        cur_phon = e_get_phon(vv, i)
        cur_ctrl = e_get_phon_ctrl(vv, i)
        cur_flags = vv.phonFlags2[cur_phon] if 0 <= cur_phon < len(vv.phonFlags2) else 0
        cur_stress = cur_ctrl & kStressField
        cur_syllable_type = cur_ctrl & kSyllableTypeField
        cur_dur = vv.dur_Buf[i]

        prev_ctrl = e_get_phon_ctrl(vv, i - 1)

        if cur_flags & kVowelF:
            # --- PITCH RISE ---
            if (cur_ctrl & kPitchRise) and pitch_is_fallen:
                raise_amt = vv.VP_riseAmt
                if vv.end_Punctuation == _Quest_:
                    raise_amt = raise_amt >> 1
                if cur_ctrl & kPitchFall:
                    time_t = (-80) // kFrameTime
                else:
                    time_t = 0
                store_f0_and_time(vv, raise_amt, time_t, kPitchRiseFall_Flg)
                cur_baseline += raise_amt
                pitch_is_fallen = False

            # --- PITCH RISE1 / FALL1 ---
            if cur_ctrl & kPitchRise1:
                raise_amt1 = vv.VP_riseAmt1
                if vv.end_Punctuation == _Quest_:
                    raise_amt1 = raise_amt1 >> 1
                store_f0_and_time(vv, raise_amt1, 0, kPitchRiseFall1_Flg)
            elif cur_ctrl & kPitchFall1:
                fall_amt1 = vv.VP_fallAmt1
                store_f0_and_time(vv, fall_amt1, 0, kPitchRiseFall1_Flg)

            # --- PRIMARY STRESS ---
            if cur_stress & kPrimOrEmphStress:
                if cur_stress == kEmphaticStress:
                    pitch_t = kHZ_28
                else:
                    pitch_t = kHZ_14

                if stress_counter == 0:
                    pitch_t += kHZ_10
                elif stress_counter == 1:
                    pitch_t += kHZ_9
                elif stress_counter == 2:
                    pitch_t += kHZ_6
                elif stress_counter == 3:
                    pitch_t += kHZ_4

                if vv.end_Punctuation == _Quest_:
                    pitch_t = pitch_t >> 1

                if (cur_ctrl & kPitchFall) or (cur_syllable_type & kTerm_End):
                    time_t = (-60) // kFrameTime
                elif cur_stress == kEmphaticStress:
                    time_t = 0
                else:
                    time_t = cur_dur >> 2

                pitch_t = (vv.VP_stressGain * pitch_t) >> 16

                if (cur_syllable_type & kTerm_End) and (cur_stress != kEmphaticStress):
                    pitch_t = 0 - kHZ_4

                store_f0_and_time(vv, pitch_t, time_t, kPitchStress_Flg)
                stress_counter += 1

            # --- PITCH FALL ---
            if cur_ctrl & kPitchFall:
                time_t = cur_dur - (160 // kFrameTime)
                if time_t < (25 // kFrameTime):
                    time_t = 25 // kFrameTime

                fall_amt = 0
                if cur_syllable_type & kTerm_End:
                    if vv.end_Punctuation == _Comma_:
                        fall_amt = 0 - kHZ_12
                    elif vv.end_Punctuation == _Period_:
                        fall_amt = 0 - kHZ_20
                    elif vv.end_Punctuation == _Quest_:
                        fall_amt = 0 - kHZ_7
                    elif vv.end_Punctuation == _Exclam_:
                        fall_amt = 0 - kHZ_20
                elif cur_syllable_type & kVerb_End:
                    fall_amt = 0
                else:
                    fall_amt = vv.VP_fallAmt

                fall_amt = ((vv.VP_assertiveness * fall_amt) >> 16) - raise_amt

                store_f0_and_time(vv, fall_amt, time_t, kPitchRiseFall_Flg)
                cur_baseline += fall_amt
                pitch_is_fallen = True

            # --- RAISE TYPE BOUNDARY (comma or quest) ---
            if (cur_syllable_type & kTerm_End) and (vv.end_Punctuation in (_Comma_, _Quest_)):
                time_t = 0
                if vv.end_Punctuation == _Quest_:
                    store_f0_and_time(vv, kHZ_18, time_t, kPitchBoundry_Flg)
                    store_f0_and_time(vv, kHZ_25, cur_dur, kPitchBoundry_Flg)
                else:
                    store_f0_and_time(vv, kHZ_7, time_t, kPitchBoundry_Flg)
                    store_f0_and_time(vv, kHZ_10, cur_dur, kPitchBoundry_Flg)

        if (prev_ctrl & kSilenceTypeField) >> kSilenceTypeShift:
            store_f0_and_time(vv, 0 - cur_baseline, 0, kPhraseReset)
            cur_baseline = 0

        vv.pitch_Time_Offset += cur_dur
