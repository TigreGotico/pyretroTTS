"""Port of `Pitch_RaiseAndFall` (`BackEnd.c:2127-2295`) and its helpers
`Count_StressVowels_Till_Boundry`, `Any_StressVowels_Remain`,
`Count_Vowels_Till_Boundry` (`BackEnd.c:2041-2126`): flags the
`kPitchRise`/`kPitchFall` ctrl bits on `phon_Buf_2` vowels that mark where
the sentence-level pitch contour rises (first stressed vowel) and falls
(last stressed vowel, or the sentence's only vowel if it has no stress),
plus `kPitchRise1`/`kPitchFall1` word-level rise/fall alternation for
sentences with more than one stress group.

There is a second `Pitch_RaiseAndFall` definition later in `BackEnd.c`
(inside `#if 0`, disabled dead code) -- only the one at `BackEnd.c:2127`
is live in the compiled engine; this ports that one.

Operates on `vv.phon_Buf_2`/`vv.phon_Ctrl_Buf_2` in place (already filled
by `_phonbuf2.fill_phon_buf_2`). Call order in the real `ParseSentence`:
`Fill_Phon_Buf_2 -> Pitch_RaiseAndFall -> Mod_Duration -> synth_AdjustPhons2`
-- so this should run BEFORE `_moduration.mod_duration()` and
`_phonbuf2.insert_closure_release()`, not after.
"""
from __future__ import annotations

from ._backend import VoiceVar
from ._consts import (
    kBoundryTypeField,
    kContent_Word,
    kIsStressed,
    kPitchFall,
    kPitchFall1,
    kPitchRise,
    kPitchRise1,
    kPrimOrEmphStress,
    kSyllableTypeField,
    kTerm_End,
    kVowelF,
    kWord_Start,
)
from ._data import (
    PhonFlags2,
)

kFallen, kRaised, kStart, kFinished = 0, 1, 2, 3


def _flags(phon_flags2, phon):
    if phon is None or not (0 <= phon < len(phon_flags2)):
        return 0
    return phon_flags2[phon]


def count_stress_vowels_till_boundry(vv: VoiceVar, boundry: int, cur_index: int) -> int:
    """`Count_StressVowels_Till_Boundry` (`BackEnd.c:2041-2065`)."""
    count = 0
    for i in range(cur_index, vv.phonBuf_2_In_Index):
        cur_phon = vv.phon_Buf_2[i]
        cur_ctrl = vv.phon_Ctrl_Buf_2[i]
        cur_flags = _flags(PhonFlags2, cur_phon)
        if i != cur_index:
            if (cur_ctrl & kPrimOrEmphStress) and (cur_flags & kVowelF):
                count += 1
        if (cur_ctrl & kSyllableTypeField) >= boundry:
            break
    return count


def any_stress_vowels_remain(vv: VoiceVar, cur_index: int) -> int:
    """`Any_StressVowels_Remain` (`BackEnd.c:2069-2090`)."""
    count = 0
    for i in range(cur_index + 1, vv.phonBuf_2_In_Index):
        cur_phon = vv.phon_Buf_2[i]
        cur_ctrl = vv.phon_Ctrl_Buf_2[i]
        cur_flags = _flags(PhonFlags2, cur_phon)
        if (cur_ctrl & kBoundryTypeField) == kWord_Start:
            break
        if (cur_ctrl & kPrimOrEmphStress) and (cur_flags & kVowelF):
            count += 1
    return count


def count_vowels_till_boundry(vv: VoiceVar, boundry: int, cur_index: int) -> int:
    """`Count_Vowels_Till_Boundry` (`BackEnd.c:2094-2118`)."""
    count = 0
    for i in range(cur_index, vv.phonBuf_2_In_Index):
        cur_phon = vv.phon_Buf_2[i]
        cur_ctrl = vv.phon_Ctrl_Buf_2[i]
        cur_flags = _flags(PhonFlags2, cur_phon)
        if i != cur_index:
            if cur_flags & kVowelF:
                count += 1
        if (cur_ctrl & kSyllableTypeField) >= boundry:
            break
    return count


def pitch_raise_and_fall(vv: VoiceVar) -> None:
    """Port of `Pitch_RaiseAndFall` (`BackEnd.c:2127-2295`)."""

    p_state = kStart
    last_state = kStart
    wd_index = 0
    stress_count = 1
    wd_type = [0] * 64
    first_word = 0
    last_word = 0

    index = 0
    while index < vv.phonBuf_2_In_Index:
        cur_phon = vv.phon_Buf_2[index]
        cur_ctrl = vv.phon_Ctrl_Buf_2[index]
        cur_flags = _flags(PhonFlags2, cur_phon)

        if (p_state == kRaised) and ((cur_ctrl & kBoundryTypeField) == kWord_Start):
            if cur_ctrl & kContent_Word:
                wd_type[wd_index] = kPitchRise1
            else:
                wd_type[wd_index] = kPitchFall1
            if wd_index < 63:
                wd_index += 1
            stress_count = 0
            last_word = index
            if (last_state == kStart) and (p_state == kRaised):
                last_state = kRaised
                first_word = index

        if cur_flags & kVowelF:
            if p_state == kStart:
                if count_vowels_till_boundry(vv, kTerm_End, index) == 0:
                    vv.phon_Ctrl_Buf_2[index] |= kPitchFall
                    p_state = kFinished
                    break
                elif count_stress_vowels_till_boundry(vv, kTerm_End, index) == 0:
                    vv.phon_Ctrl_Buf_2[index] |= kPitchFall
                    p_state = kFinished
                elif cur_ctrl & kIsStressed:
                    vv.phon_Ctrl_Buf_2[index] |= kPitchRise
                    p_state = kRaised
            elif p_state == kRaised:
                if cur_ctrl & kPrimOrEmphStress:
                    stress_count += 1
                if count_vowels_till_boundry(vv, kTerm_End, index) == 0:
                    vv.phon_Ctrl_Buf_2[index] |= kPitchFall
                    p_state = kFallen
                    break
                elif (cur_ctrl & kPrimOrEmphStress) and (count_stress_vowels_till_boundry(vv, kTerm_End, index) == 0):
                    vv.phon_Ctrl_Buf_2[index] |= kPitchFall
                    p_state = kFallen
                    break

        index += 1

    wd_index -= 1
    wd_index -= 1
    if (wd_index > 1) and (p_state != kFinished):
        p_state = kFallen
        i = 0
        while i < wd_index:
            if p_state == kFallen:
                wd_type[i] = kPitchRise1
                p_state = kRaised
            else:
                wd_type[i] = kPitchFall1
                p_state = kFallen
            i += 1
        # C's `for` loop leaves `i == wd_index` on normal exit (no break in
        # this loop); the `while` above preserves that exactly.

        if p_state == kRaised:
            wd_type[i] = kPitchFall1
            wd_index += 1

        action = False
        i = 0
        for index in range(first_word, last_word):
            cur_phon = vv.phon_Buf_2[index]
            cur_flags = _flags(PhonFlags2, cur_phon)
            cur_ctrl = vv.phon_Ctrl_Buf_2[index]

            if (cur_ctrl & kBoundryTypeField) == kWord_Start:
                action = True

            if (cur_flags & kVowelF) and action:
                if not any_stress_vowels_remain(vv, index):
                    action = False
                    if i < wd_index:
                        vv.phon_Ctrl_Buf_2[index] |= wd_type[i]
                    i += 1
