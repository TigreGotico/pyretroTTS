"""Port of `Fill_Phon_Buf_2` (`BackEnd.c:2469-3067`), the context-sensitive
phonetic rule pass that turns `phon_Buf_1`/`phon_Ctrl_Buf_1` (this port's
`SentenceAssembly.phon_buf`/`ctrl_buf`, from `_assembly.py`) into
`phon_Buf_2`/`phon_Ctrl_Buf_2` -- allophone selection (dark L, R-coloring,
t/d-flapping, glottalization, DH-vowelizing, y-slurring, EN/EL syllabic
consonants, glottal-stop insertion).

Writes directly into a `VoiceVar` instance's `phon_Buf_2`/`phon_Ctrl_Buf_2`/
`user_*_Buf2` fields (already pre-allocated, zero-filled, in `_backend.py`'s
`VoiceVar.__init__`), matching the C convention of writing into `vv->...`
in place. Since this port has no embedded-command/singing input
(`EmbeddedCmd.c`/`Morph.c` not ported -- see `docs/architecture.md`), the
`user_Cmd_Buf1`/`user_Pitch_Buf1`/`user_Dur_Buf1`/`user_Note_Buf1`/
`user_Rate_Buf1` inputs `Fill_Phon_Buf_2` reads are always zero here, so the
corresponding `user_*_Buf2` outputs are always zero/default too -- this
port omits modeling `user_*_Buf1` at all rather than threading zeros
through unnecessarily.

`vv->synthTech == kFormantSynth` gates several rules in the C source; this
port only targets formant-synth voices (the only kind ported), so those
checks are always true here and are omitted.

Also includes `insert_closure_release()`, a port of `Insert_Closure_Release`
(`formantSynth.c` -- the body of `synth_AdjustPhons2`, called right after
`Mod_Duration` in the real `ParseSentence`): inserts a release phoneme
(`_IX_`/`_AX_`) before word-final silence after a phoneme with
`kHasReleaseF` (plosives), shifting `dur_Buf` entries too. CALL ORDER
MATTERS: `_moduration.mod_duration()` must run BEFORE
`insert_closure_release()` (matching `ParseSentence`'s
`Fill_Phon_Buf_2 -> Pitch_RaiseAndFall -> Mod_Duration -> synth_AdjustPhons2`
order) -- calling it the other way round lets `mod_duration` overwrite the
release phoneme's hardcoded duration with its own generic formula, which
was confirmed to diverge from the C reference until the call order was
fixed (see `test/test_phonbuf2.py`).

NOT included here (called from `ParseSentence` around `Fill_Phon_Buf_2`,
BackEnd.c:4165-4186, not yet ported): `synth_AdjustPhons1` (a true no-op in
the C reference -- confirmed by reading its empty body in
`formantSynth.c`) and `Pitch_RaiseAndFall`. `Mod_Duration` is ported in
`_moduration.py` (see its own module docstring for scope/gaps).
`Fill_Pitch_Buf`/`StartNew_PitchClause` (`Calc_Ramp_Steps`/
`start_new_pitch_clause` are already ported in `_backend.py`, but nothing
yet calls `Fill_Pitch_Buf` to populate `pitch_Buf_Freq`/`pitch_Buf_Time`/
`pitch_Buf_Flags` from text -- those buffers are currently only reachable
via a hand-supplied plan, e.g. `test/test_pipeline.py`'s reference
constants).
"""
from __future__ import annotations

from ._consts import (
    kFrontF, kHasReleaseF, kNasalF, kPlosFricF, kPrimOrEmphStress,
    kPrimaryStress, kSonorConsonF, kSonorantF, kSyllableTypeField,
    kVowel1F, kVowelF, kWord_End, kWord_Initial_Consonant, kWord_Start,
    kStressField, kDur_One,
)
from ._phonemes import (
    _SIL_, _AA_, _AE_, _AH_, _AO_, _AR_, _AX_, _AY_,
    _b_, _CH_, _d_, _DD_, _DH_, _DX_, _EH_, _EL_, _EN_, _ER_, _EY_,
    _f_, _g_, _h_, _IH_, _IR_, _IX_, _IY_, _JH_,
    _k_, _l_, _n_, _OR_, _OW_, _p_, _QX_, _r_, _RX_, _s_, _t_,
    _TX_, _TH_, _UH_, _UR_, _UW_, _v_, _XR_, _y_, _YU_, _z_,
)


def _flags(phon_flags2, phon):
    if phon is None or not (0 <= phon < len(phon_flags2)):
        return 0
    return phon_flags2[phon]


def fill_phon_buf_2(vv, sa) -> None:
    """Port of `Fill_Phon_Buf_2`. Reads `sa.phon_buf`/`sa.ctrl_buf`
    (`phon_Buf_1`/`phon_Ctrl_Buf_1`), writes `vv.phon_Buf_2`/
    `vv.phon_Ctrl_Buf_2`/`vv.user_*_Buf2`, sets `vv.phonBuf_2_In_Index`.
    """
    from ._data import PhonFlags2

    phon_buf_1 = sa.phon_buf
    ctrl_buf_1 = sa.ctrl_buf
    n = len(phon_buf_1)

    vv.phonBuf_2_In_Index = 0
    last_stored_phon = _SIL_
    last_user_pitch = 0

    def get(i):
        if 0 <= i < n:
            return phon_buf_1[i], ctrl_buf_1[i]
        return _SIL_, 0

    for out_index in range(n):
        cur_phon, cur_ctrl = phon_buf_1[out_index], ctrl_buf_1[out_index]
        cur_flags = _flags(PhonFlags2, cur_phon)
        cur_syll = cur_ctrl & 0x0300  # kSyllableOrderField

        next_phon, next_ctrl = get(out_index + 1)
        next_flags = _flags(PhonFlags2, next_phon)
        next2_phon, next2_ctrl = get(out_index + 2)
        next3_phon, _ = get(out_index + 3)

        prev_phon, prev_ctrl = get(out_index - 1)
        prev_flags = _flags(PhonFlags2, prev_phon)
        prev2_phon, _ = get(out_index - 2)
        prev2_flags = _flags(PhonFlags2, prev2_phon)
        prev3_phon, _ = get(out_index - 3)
        prev3_flags = _flags(PhonFlags2, prev3_phon)

        if out_index == 0:
            last_stored_phon = _SIL_
        else:
            last_stored_phon = vv.phon_Buf_2[vv.phonBuf_2_In_Index - 1]
        last_flags = _flags(PhonFlags2, last_stored_phon)

        # No embedded-command/singing input is ported, so there is never an
        # override -- user_dur defaults to kDur_One (100%, the C reference's
        # own "no override" value; NOT 0, which would zero every duration
        # once Set_The_Dur divides by it), the rest to 0.
        from ._consts import kDur_One
        user_cmd = user_pitch = user_note = user_rate = 0
        user_dur = kDur_One

        target_phon = cur_phon
        del_fwd = False
        insert_glot = False
        stuff_buff = False  # True once a `goto STUFF_BUFF` is hit

        # --- EN rule (BackEnd.c:2604-2616) ---
        if (cur_phon == _n_) and (prev_phon == _IX_):
            if (prev2_flags & kPlosFricF) and (prev2_phon != _b_) and (prev2_phon != _g_):
                if not ((prev2_phon == _d_) and (prev3_flags & kVowelF)):
                    vv.phon_Buf_2[vv.phonBuf_2_In_Index - 1] = _EN_
                    del_fwd = True

        # --- EL rule (BackEnd.c:2618-2628) ---
        if not stuff_buff and (cur_phon == _l_) and not (cur_ctrl & (kPrimOrEmphStress | kWord_Initial_Consonant)):
            if (prev_phon == _AX_) or (prev_phon == _UH_):
                vv.phon_Buf_2[vv.phonBuf_2_In_Index - 1] = _EL_
                del_fwd = True
                stuff_buff = True

        if not stuff_buff:
            # --- dark-L / R-coloring rule (BackEnd.c:2631-2673) ---
            if not (cur_ctrl & (kPrimOrEmphStress | kWord_Initial_Consonant)) and (prev_flags & kVowel1F):
                if cur_phon == _l_:
                    target_phon = None  # _LX_, set below (avoid None import clutter)
                    from ._phonemes import _LX_
                    target_phon = _LX_
                elif cur_phon == _r_:
                    from ._phonemes import _RX_
                    target_phon = _RX_
                    if prev_phon in (_UW_, _UH_):
                        vv.phon_Buf_2[vv.phonBuf_2_In_Index - 1] = _UR_
                        del_fwd = True
                    elif prev_phon in (_AO_, _OW_):
                        vv.phon_Buf_2[vv.phonBuf_2_In_Index - 1] = _OR_
                        del_fwd = True
                    elif prev_phon == _AA_:
                        vv.phon_Buf_2[vv.phonBuf_2_In_Index - 1] = _AR_
                        del_fwd = True
                    elif prev_phon in (_AH_, _AX_):
                        vv.phon_Buf_2[vv.phonBuf_2_In_Index - 1] = _ER_
                        del_fwd = True
                    elif prev_phon in (_IH_, _IY_):
                        vv.phon_Buf_2[vv.phonBuf_2_In_Index - 1] = _IR_
                        del_fwd = True
                    elif prev_phon in (_AE_, _EH_, _EY_):
                        vv.phon_Buf_2[vv.phonBuf_2_In_Index - 1] = _XR_
                        del_fwd = True

            # --- yUW -> YU rule (BackEnd.c:2683-2701) ---
            if (
                (prev_ctrl & kWord_Initial_Consonant) and (prev_phon == _y_)
                and (cur_phon == _UW_) and (next_phon != _r_)
                and ((cur_ctrl & kSyllableTypeField) >= kWord_End)
            ):
                vv.phon_Buf_2[vv.phonBuf_2_In_Index - 1] = _YU_
                vv.phon_Ctrl_Buf_2[vv.phonBuf_2_In_Index - 1] = cur_ctrl
                del_fwd = True

            # --- DHAH -> DHIY rule (BackEnd.c:2705-2714) ---
            if (
                (next_flags & kVowelF) and (cur_phon == _AH_)
                and (cur_ctrl & kSyllableTypeField) and (prev_phon == _DH_)
                and (prev_ctrl & kWord_Initial_Consonant)
                and (next_ctrl & kPrimOrEmphStress)
            ):
                target_phon = _IY_

            # --- EHnd -> AEnd rule (BackEnd.c:2751-2762) ---
            if (
                (cur_phon == _SIL_) and (next_phon == _EH_)
                and (next2_phon == _n_) and (next3_phon == _d_)
                and (next_ctrl & kPrimOrEmphStress)
            ):
                phon_buf_1[out_index + 1] = _AE_
                next_phon = _AE_
                next_flags = _flags(PhonFlags2, next_phon)

            # --- glottal rule (BackEnd.c:2766-2771) ---
            if (
                (cur_flags & kVowelF) and (next_flags & kVowelF)
                and (next_ctrl & kPrimOrEmphStress) and (cur_ctrl & kWord_End)
            ):
                insert_glot = True

            # --- dental->affricate y-slur rule (BackEnd.c:2775-2796) ---
            if ((next_phon == _YU_) or (next_phon == _y_)) and not (next_ctrl & kPrimOrEmphStress):
                if cur_phon == _d_:
                    target_phon = _JH_
                    stuff_buff = True

        if not stuff_buff:
            # --- t rules (BackEnd.c:2801-2868) ---
            if cur_phon == _t_:
                if (
                    (next_phon == _UW_) and ((next_ctrl & kSyllableTypeField) >= kWord_End)
                    and not (cur_ctrl & kPrimOrEmphStress)
                    and ((next2_phon == _SIL_) or (_flags(PhonFlags2, next2_phon) & kVowelF))
                ):
                    phon_buf_1[out_index + 1] = _UW_
                else:
                    sub_t_glot = False
                    if (next_phon == _l_) or (next_phon == _DH_):
                        sub_t_glot = True
                    elif (cur_ctrl & kSyllableTypeField) >= kWord_End:
                        if ((_flags(PhonFlags2, next_phon) & kSonorConsonF) and (next_phon != _EN_)) or (next_phon == _h_):
                            sub_t_glot = True
                    elif (next_phon == _EN_) or ((next_phon == _IX_) and (next2_phon == _n_)):
                        sub_t_glot = True

                    if sub_t_glot:
                        if last_flags & kSonorantF:
                            target_phon = _TX_
                        else:
                            target_phon = _d_
                        stuff_buff = True

        skip_flap = False
        if not stuff_buff:
            # --- dental flap DX rules (BackEnd.c:2873-2988) ---
            if (cur_phon == _d_) or (cur_phon == _t_):
                if (next_phon == _IX_) and (next2_phon == _n_):
                    if cur_phon == _t_:
                        skip_flap = True
                    elif not (prev_flags & kVowelF):
                        skip_flap = True

                if not skip_flap and (next_flags & kVowelF) and (last_flags & kSonorantF) and not (last_flags & kNasalF):
                    if next_ctrl & kWord_Start:
                        target_phon = _DX_
                    elif not (cur_ctrl & kPrimOrEmphStress):
                        if cur_ctrl & kWord_Initial_Consonant:
                            if next_phon in (_AX_, _IX_, _UH_):
                                target_phon = _DX_
                        elif cur_phon == _t_:
                            if next_phon == _OW_:
                                if (vv.phon_Ctrl_Buf_2[vv.phonBuf_2_In_Index - 1] & kStressField) and (
                                    (next2_phon != _r_) or (next2_ctrl & kWord_Initial_Consonant)
                                ):
                                    target_phon = _DX_
                            elif (next_phon in (_AH_, _AX_)) and (next2_phon == _r_) and not (next_ctrl & kPrimaryStress):
                                if not (cur_ctrl & kWord_Initial_Consonant) and not (next_ctrl & kPrimaryStress):
                                    target_phon = _DX_
                            elif next_phon == _ER_:
                                if not (cur_ctrl & kWord_Initial_Consonant):
                                    target_phon = _DX_
                            elif (
                                (next_phon in (_AX_, _IY_, _IX_, _EL_))
                                and ((next2_phon != _r_) or (next2_ctrl & kWord_Initial_Consonant))
                                and not (next_ctrl & kPrimaryStress)
                            ):
                                target_phon = _DX_
                        else:  # cur_phon == _d_
                            if next_phon == _OW_:
                                if vv.phon_Ctrl_Buf_2[vv.phonBuf_2_In_Index - 1] & kStressField:
                                    target_phon = _DX_
                            elif next_phon in (_AX_, _IY_, _IX_, _EL_, _ER_, _IH_, _AH_, _AA_):
                                target_phon = _DX_

            # --- DH rules (BackEnd.c:2994-3016) ---
            if (cur_phon == _DH_) and not (cur_ctrl & kPrimaryStress):
                if last_stored_phon in (_t_, _TX_, _d_):
                    target_phon = _DD_
                elif last_stored_phon == _n_:
                    target_phon = _n_

        # --- STUFF_BUFF (BackEnd.c:3021-3067) ---
        if not del_fwd:
            idx = vv.phonBuf_2_In_Index
            vv.phon_Buf_2[idx] = target_phon
            vv.phon_Ctrl_Buf_2[idx] = cur_ctrl
            vv.user_Cmd_Buf2[idx] = user_cmd
            vv.user_Pitch_Buf2[idx] = user_pitch + last_user_pitch
            vv.user_Dur_Buf2[idx] = user_dur
            vv.user_Note_Buf2[idx] = user_note
            vv.user_Rate_Buf2[idx] = user_rate

            from ._consts import kPhonBuf_Red_Zone
            if vv.phonBuf_2_In_Index < kPhonBuf_Red_Zone:
                vv.phonBuf_2_In_Index += 1

            if insert_glot:
                idx = vv.phonBuf_2_In_Index
                vv.phon_Buf_2[idx] = _QX_
                vv.phon_Ctrl_Buf_2[idx] = 0
                vv.user_Cmd_Buf2[idx] = 0
                vv.user_Pitch_Buf2[idx] = vv.user_Pitch_Buf2[idx - 1]
                vv.user_Dur_Buf2[idx] = kDur_One
                vv.user_Note_Buf2[idx] = 0
                vv.user_Rate_Buf2[idx] = 0
                if vv.phonBuf_2_In_Index < kPhonBuf_Red_Zone:
                    vv.phonBuf_2_In_Index += 1
        else:
            idx = vv.phonBuf_2_In_Index - 1
            vv.user_Cmd_Buf2[idx] += user_cmd
            vv.user_Pitch_Buf2[idx] += user_pitch
            if user_dur != kDur_One:
                vv.user_Dur_Buf2[idx] = user_dur
            if user_rate != 0:
                vv.user_Rate_Buf2[idx] = user_rate

            if cur_ctrl & 0x10000000:  # kSyllable_Start
                if out_index + 1 < n:
                    ctrl_buf_1[out_index + 1] |= 0x10000000

        last_user_pitch += user_pitch


def insert_closure_release(vv) -> None:
    """Port of `Insert_Closure_Release` (`formantSynth.c`, the body of
    `synth_AdjustPhons2`). Inserts a release phoneme (`_IX_`/`_AX_`) before
    word-final silence after a phoneme with `kHasReleaseF` (plosives).
    Operates on `vv.phon_Buf_2`/`vv.phon_Ctrl_Buf_2`/`vv.dur_Buf`/
    `vv.user_*_Buf2` in place, mirroring the C convention.
    """
    from ._consts import kFrameTime, kHasReleaseF, kPhonBuf_Red_Zone, kPlosive_Release, kDur_One
    from ._data import PhonFlags2
    from ._backend import e_get_phon

    i = 0
    while i < vv.phonBuf_2_In_Index:
        cur_phon = e_get_phon(vv, i)
        cur_flags = _flags(PhonFlags2, cur_phon)
        prev_phon = e_get_phon(vv, i - 1)
        next_phon = e_get_phon(vv, i + 1)

        if next_phon == _SIL_:
            if (cur_flags & kHasReleaseF) and (vv.phonBuf_2_In_Index < kPhonBuf_Red_Zone):
                # Make room for the plosive release.
                for index in range(vv.phonBuf_2_In_Index, i, -1):
                    src, dest = index - 1, index
                    vv.phon_Buf_2[dest] = vv.phon_Buf_2[src]
                    vv.phon_Ctrl_Buf_2[dest] = vv.phon_Ctrl_Buf_2[src]
                    vv.dur_Buf[dest] = vv.dur_Buf[src]
                    vv.user_Cmd_Buf2[dest] = vv.user_Cmd_Buf2[src]
                    vv.user_Pitch_Buf2[dest] = vv.user_Pitch_Buf2[src]
                    vv.user_Dur_Buf2[dest] = vv.user_Dur_Buf2[src]
                    vv.user_Note_Buf2[dest] = vv.user_Note_Buf2[src]
                    vv.user_Rate_Buf2[dest] = vv.user_Rate_Buf2[src]

                vv.phon_Ctrl_Buf_2[i + 1] = vv.phon_Ctrl_Buf_2[i] | kPlosive_Release
                i += 1
                vv.phonBuf_2_In_Index += 1

                # Decide if voiced release is AX or IX.
                if (_flags(PhonFlags2, prev_phon) & kFrontF) or (cur_phon == _t_) or (cur_phon == _d_):
                    vv.phon_Buf_2[i] = _IX_
                else:
                    from ._phonemes import _AX_
                    vv.phon_Buf_2[i] = _AX_

                vv.dur_Buf[i] = 25 // kFrameTime
                vv.user_Cmd_Buf2[i] = 0
                vv.user_Pitch_Buf2[i] = vv.user_Pitch_Buf2[i - 1]
                vv.user_Dur_Buf2[i] = kDur_One
                vv.user_Note_Buf2[i] = 0
                vv.user_Rate_Buf2[i] = 0
        i += 1
