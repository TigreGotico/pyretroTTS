"""Port of `Mod_Duration` (`BackEnd.c:1362-2031`): assigns each phoneme's
duration (`vv.dur_Buf`) based on stress, syllable position, phonetic
context (obstruent voicing, clusters, glides), and speaking rate.

Reads `vv.phon_Buf_2`/`vv.phon_Ctrl_Buf_2` (filled by `_phonbuf2.py`) via
the already-ported `e_get_phon`/`e_get_phon_ctrl`. Writes `vv.dur_Buf`.

The `singScript`/`singing` branches (`BackEnd.c:1977-2029`) that stretch/
compress duration to match an embedded note script (GoodNews/BadNews/
PipeOrgan/Cellos) are ported, as is `sync_On_Marker` (`BackEnd.c:1938-1976`,
duration adjustment against a sample-marker table for `kUseSyncSnd`
voices, Bells/Hysterical -- `vv.sync_On_Marker`/`vv.markerBuf`/
`vv.lastMarkerIndex` are set in `api.new_voice()` from the marker tables
extracted into `_data.py`). The `temp = vv.user_Rate_Buf2[i]`
embedded-rate-change check (`BackEnd.c:1900-1915`) is ported
(`_backend.init_rate_params`/`_engine.e_set_tempo`, both pure
arithmetic with no missing dependency -- a previous pass of this
docstring incorrectly assumed `Init_Rate_Params` needed something
unported), but currently unreachable in practice since nothing yet
populates `user_Rate_Buf2` with a nonzero value (the embedded `rate`
command itself isn't ported -- see docs/architecture.md).

Requires `vv.Note_Times` to be populated (`_engine.e_set_tempo`, called
from `api.new_voice()`) for the singScript/singing branches to compute
correct note durations -- an unpopulated (all-zero) `Note_Times` would
silently zero every note's intended duration.
"""
from __future__ import annotations

from dataclasses import dataclass

from ._backend import (
    VoiceVar,
    e_get_phon,
    e_get_phon_ctrl,
    init_rate_params,
)
from ._consts import (
    k1pct,
    kAffricateF,
    kConsonantF,
    kDurStepRes,
    kEmphaticStress,
    kFirst_Syllable_In_Word,
    kFrameTime,
    kFric,
    kGStopF,
    kLowVibrato,
    kMid_Syllable_In_Word,
    kMore_Than_One_Syllable_In_Word,
    kNasalF,
    kNormal_Speech_Rate,
    kNoteDur,
    kNoteDurShift,
    kOneHalf,
    kPlosFricF,
    kPrimOrEmphStress,
    kSampFrameLen,
    kSampleMarker,
    kSecondaryStress,
    kSilenceDuration,
    kSilenceTypeField,
    kSilenceTypeShift,
    kSonorantF,
    kStopF,
    kStressedWInitial,
    kStressField,
    kSyllable_Start,
    kSyllableOrderField,
    kSyllableTypeField,
    kTerm_Bound,
    kTerm_End,
    kVerb_End,
    kVocLiq,
    kVoicedF,
    kVowel1F,
    kVowelF,
    kWord_End,
    kWord_Initial_Consonant,
)
from ._data import (
    PhonFlags2,
)
from ._engine import (
    e_set_tempo,
)
from ._phonemes import _DX_, _LX_, _SH_, _SIL_, _TH_, _l_, _s_, _w_

# BackEnd.c's Mod_Duration has its own local `#define k100pct_Dur 128`
# (percent_Duration's base scale, distinct from k100percent=0x10000).
_K100PCT_DUR = 128
# mt4.h:516 -- `#define pct 655` (0.01 * 65536), same value as k1pct but a
# separate C macro name used throughout this specific function.
_PCT = 655


def _flags(phon_flags2, phon):
    if phon is None or not (0 <= phon < len(phon_flags2)):
        return 0
    return phon_flags2[phon]


@dataclass
class _NoteTiming:
    """Running state the note-driven retiming branches carry between phonemes.

    Each branch waits for a syllable to end, then stretches the vowel it just
    passed so the syllable's total duration matches the note it should occupy.
    """

    first_pass: bool = True   # nothing to retime until one syllable has passed
    total_dur: int = 0        # frames accumulated since the last note boundary
    vowel_index: int = 0      # the vowel to stretch or compress
    note_dur: int = 0         # frames the current note should occupy
    next_note_dur: int = 0    # note-length code read from the score


def _stretch_vowel_to_note(vv: VoiceVar, timing: _NoteTiming, low_vibrato: bool) -> None:
    """Absorb the difference between the note's length and the syllable's."""
    vv.dur_Buf[timing.vowel_index] += timing.note_dur - timing.total_dur
    if vv.dur_Buf[timing.vowel_index] < 4:
        vv.dur_Buf[timing.vowel_index] = 4
    elif low_vibrato and vv.dur_Buf[timing.vowel_index] > 100:
        vv.phon_Ctrl_Buf_2[timing.vowel_index] |= kLowVibrato


def _retime_to_sample_markers(
    vv: VoiceVar, i: int, cur_ctrl: int, cur_flags: int, cur_is_vowel: bool,
    next_phon: int, dur_hold: int, timing: _NoteTiming,
) -> None:
    """Retime against the sampled source's marker table (BackEnd.c:1938-1976).

    Only kUseSyncSnd voices (Bells, Hysterical) take this path: their glottal
    source is a recording whose marker times dictate where syllables may fall.
    """
    if (cur_ctrl & kSyllable_Start) and timing.first_pass:
        vv.phon_Ctrl_Buf_2[i] |= kSampleMarker

    if cur_is_vowel or (cur_ctrl & kTerm_Bound):
        if not (cur_ctrl & kTerm_Bound) and not timing.first_pass:
            if cur_flags & kSonorantF:
                vv.phon_Ctrl_Buf_2[i] |= kSampleMarker
            else:
                vv.phon_Ctrl_Buf_2[i + 1] |= kSampleMarker

        if not timing.first_pass:
            markers = vv.markerBuf
            timing.note_dur = (
                (markers[vv.markerIndex + 1] - markers[vv.markerIndex])
                // (kSampFrameLen >> 1)
            )
            # A silence needs more room than a following phoneme does.
            lead_out = 20 if next_phon == _SIL_ else 10
            vv.dur_Buf[timing.vowel_index] += (timing.note_dur - timing.total_dur) - lead_out
            if vv.dur_Buf[timing.vowel_index] < 4:
                vv.dur_Buf[timing.vowel_index] = 4
            timing.total_dur = 0
            vv.markerIndex += 1
            if vv.markerIndex == vv.lastMarkerIndex:
                vv.markerIndex = 0
        timing.first_pass = False

    if cur_is_vowel:
        timing.vowel_index = i
    timing.total_dur += dur_hold


def _retime_to_note_script(
    vv: VoiceVar, i: int, cur_ctrl: int, cur_flags: int, cur_is_vowel: bool,
    dur_hold: int, timing: _NoteTiming,
) -> None:
    """Retime against the voice's embedded note score (BackEnd.c:1977-2003)."""
    if (cur_flags & kVowelF) or (cur_ctrl & kTerm_Bound):
        if cur_ctrl & kTerm_Bound:
            timing.note_dur = max(timing.note_dur, vv.Note_Times[5])
        else:
            timing.next_note_dur = (vv.notesBuf[vv.songIndex] & kNoteDur) >> kNoteDurShift
            vv.songIndex += 1
        if vv.songIndex >= vv.numOfNotes:
            vv.songIndex = 0

        if not timing.first_pass:
            _stretch_vowel_to_note(vv, timing, low_vibrato=True)
        timing.first_pass = False
        timing.vowel_index = i
        timing.note_dur = vv.Note_Times[timing.next_note_dur]
        timing.total_dur = 0

    timing.total_dur += dur_hold
    if cur_is_vowel:
        timing.vowel_index = i


def _retime_to_note_buffer(
    vv: VoiceVar, i: int, cur_ctrl: int, cur_is_vowel: bool,
    dur_hold: int, timing: _NoteTiming,
) -> None:
    """Retime against per-phoneme notes supplied with the text (BackEnd.c:2004-2029)."""
    timing.next_note_dur = (vv.user_Note_Buf2[i] & kNoteDur) >> kNoteDurShift
    if (timing.next_note_dur != 0) or (cur_ctrl & kTerm_Bound):
        if not timing.first_pass:
            _stretch_vowel_to_note(vv, timing, low_vibrato=True)
        timing.first_pass = False
        timing.vowel_index = i
        timing.note_dur = vv.Note_Times[timing.next_note_dur]
        timing.total_dur = 0

    timing.total_dur += dur_hold
    if cur_is_vowel:
        timing.vowel_index = i


def mod_duration(vv: VoiceVar) -> None:
    """Port of `Mod_Duration`. Writes `vv.dur_Buf[1:vv.phonBuf_2_In_Index]`
    (`vv.dur_Buf[0]` is always 1, matching `BackEnd.c:1397`)."""

    vv.markerIndex = 0
    vv.dur_Buf[0] = 1  # initial SIL = 5ms

    # State for the singScript/singing branches (BackEnd.c:1938-2029):
    # note-driven duration adjustment on vowels, stretching/compressing the
    # naive duration formula's output to match the embedded note script's
    # intended timing.
    emphasis_run = False
    timing = _NoteTiming()

    for i in range(1, vv.phonBuf_2_In_Index):
        cur_phon = e_get_phon(vv, i)
        cur_ctrl = e_get_phon_ctrl(vv, i)
        cur_syllable_type = cur_ctrl & kSyllableTypeField
        cur_stress = cur_ctrl & kStressField
        cur_flags = _flags(PhonFlags2, cur_phon)
        cur_is_vowel = bool(cur_flags & kVowelF)

        prev_phon = e_get_phon(vv, i - 1)
        prev_ctrl = e_get_phon_ctrl(vv, i - 1)
        prev_flags = _flags(PhonFlags2, prev_phon)

        next_phon = e_get_phon(vv, i + 1)
        next_ctrl = e_get_phon_ctrl(vv, i + 1)
        next_flags = _flags(PhonFlags2, next_phon)

        next2_phon = e_get_phon(vv, i + 2)
        next2_ctrl = e_get_phon_ctrl(vv, i + 2)
        next2_flags = _flags(PhonFlags2, next2_phon)

        percent_duration = _K100PCT_DUR
        fixed_duration = 0
        max_dur = vv.maxDurTbl[cur_phon]
        min_dur = vv.minDurTbl[cur_phon]
        dur_hold = 0
        set_the_dur = False

        # --- #1 Pause insertion ---
        if cur_phon == _SIL_:
            temp_s = (cur_ctrl & kSilenceTypeField) >> kSilenceTypeShift
            if temp_s:
                dur_hold = vv.BoundryDurTbl[temp_s]
            else:
                dur_hold = 200
            dur_hold = (dur_hold * vv.rate_Ratio) >> 16
            if (not vv.singing) and (cur_ctrl & kSilenceDuration):
                dur_hold = vv.user_Note_Buf2[i]
            if dur_hold < 10:
                dur_hold = 10
            set_the_dur = True

        if not set_the_dur:
            # --- #2 Clause-final lengthening ---
            if cur_syllable_type & kTerm_End:
                if cur_flags & kStopF:
                    fixed_duration = 0
                elif (cur_flags & kVoicedF) and (cur_flags & kFric):
                    fixed_duration = 20
                elif (cur_flags & kVocLiq) and (next_flags & kPlosFricF) and not (next_flags & kVoicedF):
                    fixed_duration = 15
                else:
                    fixed_duration = 40

                if next_flags & kSonorantF:
                    fixed_duration -= 20

                if (vv.phonBuf_2_In_Index < 10) and cur_stress and cur_is_vowel:
                    fixed_duration += (10 - vv.phonBuf_2_In_Index) * 5

            if cur_is_vowel:
                # --- #3 Non-phrase-final shortening of vowels ---
                if cur_syllable_type < kVerb_End:
                    percent_duration = (percent_duration * 60 * _PCT) >> 16

                # --- #4 Non-word-final shortening of vowels ---
                if not (cur_stress & kPrimOrEmphStress) and not (cur_ctrl & kMore_Than_One_Syllable_In_Word):
                    if cur_stress & kSecondaryStress:
                        percent_duration = (percent_duration * 85 * _PCT) >> 16
                    else:
                        percent_duration = (percent_duration * 55 * _PCT) >> 16
                elif (cur_ctrl & kMore_Than_One_Syllable_In_Word) and (cur_syllable_type < kWord_End) and not (cur_stress & kPrimOrEmphStress):
                    if (cur_ctrl & kSyllableOrderField) <= kFirst_Syllable_In_Word:
                        percent_duration = (percent_duration * 85 * _PCT) >> 16
                    else:
                        percent_duration = (percent_duration * 80 * _PCT) >> 16

                # --- #5 Polysyllabic shortening ---
                if cur_ctrl & kMore_Than_One_Syllable_In_Word:
                    percent_duration = (percent_duration * 80 * _PCT) >> 16

            # --- #6 Non-word-initial consonant shortening ---
            if (not cur_is_vowel) and not (cur_ctrl & kWord_Initial_Consonant):
                if (cur_flags & kFric) and (cur_syllable_type & kWord_End):
                    fixed_duration += 20
                else:
                    percent_duration = (percent_duration * 85 * _PCT) >> 16

            # --- #7 Unstressed shortening ---
            if not (cur_stress & kPrimOrEmphStress):
                if not (cur_flags & kPlosFricF) and not (cur_flags & kGStopF):
                    min_dur = min_dur - (min_dur >> 2)

                if cur_is_vowel:
                    if (cur_ctrl & kSyllableOrderField) == kMid_Syllable_In_Word:
                        percent_duration = (percent_duration * 55 * _PCT) >> 16
                    else:
                        percent_duration = (percent_duration * 70 * _PCT) >> 16
                else:
                    if _w_ <= cur_phon <= _l_:
                        percent_duration = (percent_duration * 60 * _PCT) >> 16
                    else:
                        percent_duration = (percent_duration * 70 * _PCT) >> 16

            # --- #8 Lengthening for emphasis ---
            # Runs from an emphatically stressed vowel until the next word-
            # initial consonant or unemphasized vowel ends it.
            if (cur_ctrl & kWord_Initial_Consonant) or (cur_is_vowel and (cur_stress != kEmphaticStress)):
                emphasis_run = False
            if cur_stress == kEmphaticStress:
                emphasis_run = True
            if emphasis_run:
                if cur_is_vowel:
                    fixed_duration += 60
                else:
                    fixed_duration += 20

            # --- #9 Postvocalic context of vowels ---
            voc_flag = False
            the_obstr = _SIL_
            num_1 = 0x10000  # k100percent
            if cur_is_vowel or (
                ((cur_flags & kVocLiq) or (cur_flags & kNasalF))
                and not (cur_ctrl & kStressedWInitial)
                and (next_flags & kPlosFricF)
            ):
                if not (next_flags & kVowelF) and not (next_ctrl & kStressedWInitial):
                    the_obstr = next_phon
                    if (
                        ((next_flags & kVocLiq) or (next_flags & kNasalF))
                        and not (next2_ctrl & kStressedWInitial)
                        and (next2_flags & kPlosFricF)
                    ):
                        voc_flag = True
                        the_obstr = next2_phon

                    if the_obstr != _SIL_:
                        obstr_flags = _flags(PhonFlags2, the_obstr)
                        if not (obstr_flags & kVoicedF):
                            fixed_duration = fixed_duration - (fixed_duration >> 1)
                            num_1 = k1pct * 80
                            if obstr_flags & (kStopF | kAffricateF):
                                num_1 = k1pct * 55
                        elif obstr_flags & kPlosFricF:
                            num_1 = k1pct * 120
                            if not (obstr_flags & kStopF) and (the_obstr != _DX_) and (cur_flags & kPrimOrEmphStress):
                                fixed_duration += 25
                        elif obstr_flags & kNasalF:
                            num_1 = k1pct * 85

                if (cur_syllable_type < kTerm_End) or voc_flag:
                    num_1 = (num_1 >> 1) + kOneHalf

                percent_duration = (percent_duration * num_1) >> 16

            # --- #10 Shortening/lengthening in clusters ---
            if cur_is_vowel:
                if next_flags & kVowelF:
                    fixed_duration += 30
                if (
                    ((cur_ctrl & kSyllableOrderField) == kFirst_Syllable_In_Word)
                    and (cur_ctrl & kPrimOrEmphStress)
                    and not (prev_ctrl & kWord_Initial_Consonant)
                ):
                    fixed_duration += 25
                if next_phon == _LX_:
                    fixed_duration -= 20
            elif cur_flags & kConsonantF:
                if (next_flags & kConsonantF) and (cur_syllable_type < kTerm_End):
                    num_1 = k1pct * 55
                    if (cur_flags & kNasalF) and (next_ctrl & kWord_Initial_Consonant):
                        num_1 = k1pct * 150
                    min_dur = min_dur - (min_dur >> 2)
                    if (cur_phon == _s_) or (cur_phon == _TH_):
                        if next_flags & kStopF:
                            num_1 = k1pct * 50
                        if next_phon == _SH_:
                            dur_hold = 12
                            set_the_dur = True
                    if not set_the_dur:
                        percent_duration = (percent_duration * num_1) >> 16

                if not set_the_dur and (prev_flags & kConsonantF):
                    num_1 = k1pct * 55
                    min_dur = min_dur - (min_dur >> 2)
                    if cur_flags & kStopF:
                        if prev_phon == _s_:
                            num_1 = k1pct * 60
                        elif (prev_flags & kNasalF) and not cur_stress:
                            num_1 = k1pct * 10
                    percent_duration = (percent_duration * num_1) >> 16

            if not set_the_dur:
                # --- #11 Lengthening due to plosive aspiration ---
                if (cur_flags & kSonorantF) and not (prev_flags & kVoicedF) and (prev_flags & kStopF):
                    fixed_duration += 20

                # --- #12 Lengthening due to glide ---
                if (cur_flags & kVowel1F) and (prev_flags & 0x100) and not (prev_flags & kNasalF):  # kSonorConsonF
                    if fixed_duration == 0:
                        fixed_duration = 20

                # --- Lengthen short phrases ---
                if (vv.phonBuf_2_In_Index < 10) and (min_dur != max_dur):
                    fixed_duration += (5 - (vv.phonBuf_2_In_Index >> 1)) * kFrameTime

                # --- Check for rate change (BackEnd.c:1900-1915) ---
                temp = vv.user_Rate_Buf2[i]
                if temp != 0:
                    if vv.singing:
                        vv.tempo = temp
                        e_set_tempo(vv, vv.tempo)
                    else:
                        vv.speech_Rate = temp
                        init_rate_params(vv)

                dur_hold = ((percent_duration * (max_dur - min_dur)) >> 7) + min_dur
                if (vv.speech_Rate != kNormal_Speech_Rate) and (dur_hold != 0):
                    dur_hold = (dur_hold * vv.rate_Ratio_LowGain) >> 16
                    fixed_duration = (fixed_duration * vv.rate_Ratio) >> 16
                dur_hold += fixed_duration

        # --- Set_The_Dur ---
        dur_hold = (dur_hold * vv.user_Dur_Buf2[i]) >> kDurStepRes
        dur_hold //= kFrameTime

        if (cur_phon != _SIL_) and (dur_hold < 8 // kFrameTime):
            dur_hold = 8 // kFrameTime

        vv.dur_Buf[i] = dur_hold

        # Note-driven voices retime the durations just computed, stretching or
        # compressing each syllable to land on its note. Ordinary voices skip
        # all three branches (BackEnd.c:1938-2029).
        if vv.sync_On_Marker:
            _retime_to_sample_markers(
                vv, i, cur_ctrl, cur_flags, cur_is_vowel, next_phon, dur_hold, timing
            )
        elif vv.singScript:
            _retime_to_note_script(vv, i, cur_ctrl, cur_flags, cur_is_vowel, dur_hold, timing)
        elif vv.singing:
            _retime_to_note_buffer(vv, i, cur_ctrl, cur_is_vowel, dur_hold, timing)
