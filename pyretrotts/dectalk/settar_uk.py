"""DECtalk UK-English target lookup (`uk_gettar`, the target-ROM indexer).

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/ph/p_uk_st1.c`, function `uk_gettar` at line 76). FONIX
Corporation declares that source proprietary and confidential. This file is NOT
covered by this project's MIT licence. See NOTICE.

`uk_gettar` is the British-English analogue of `us_gettar` (`settar.py`): for one
parameter of one phone it reads the UK target ROM (`targets_uk.py`) and applies
the UK context rules that select or shift a Klatt target (or a negative pointer
into the UK diphthong ROM). `phsettar` (`ph_setar.c:561`) dispatches to it via
the per-phone font byte (`all_gettar[0x1D] == uk_gettar`, `ph_setar.c:351`).

It differs from `us_gettar` in exactly the ways the C differs
(`p_uk_st1.c:96-300` vs `p_us_st0.c:67-308`):

  * No `-1` fallback chain for the formant-freq/bandwidth params. The US path
    walks phnex/phnex+2/phlas and finally `PARINI` when the ROM holds `-1`; the
    UK ROM has no reached `-1` there, so `uk_gettar` returns the ROM value
    directly (the C's `if (tartemp < -1)` re-read is dead after the early
    `return`, `p_uk_st1.c:100-108`).
  * The unstressed reduction `-4` (`FSTRESS == 0`) applies to **both** AV and AP
    in UK (`p_uk_st1.c:198-204`, outside the AV/AP split), where US applies it to
    AV only.
  * Aspiration amplitude for `[h]` is 50, or 52 before a non-front onset
    (`p_uk_st1.c:184-192`), where US uses 53/60.
  * TILT adds `+10` for `[ow]` (`p_uk_st1.c:296`, `else if phone == UKP_OW`).
  * The AV `sprate < 100 && phone == USP_Q` reduction (`p_uk_st1.c:163-165`) is
    inert: `USP_Q` carries the US font byte (`0x1E`), so it can never equal a
    UK-font phone; it is documented, not modelled.

All arithmetic is the reference's fixed point (`tartemp` is a C `short`).
"""
from __future__ import annotations

from .settar import (
    A2,
    AV,
    B2,
    B3,
    F1,
    FDUMMY_VOWEL,
    FNASAL,
    FOBST,
    FPLOSV,
    FSTOP,
    FSTRESS,
    FSTRESS_1,
    FSYLL,
    FVOICD,
    FZ,
    GEN_SIL,
    MALE,
    PSFONT,
    PVALUE,
    TILT,
    Allophones,
)
from .targets import PARTYP
from .targets_uk import (
    UK_BEGTYP,
    UK_ENDTYP,
    UK_FEATB,
    UK_FEMAMP,
    UK_FEMTAR,
    UK_MALAMP,
    UK_MALTAR,
    UK_PLACE,
    UK_PTRAM,
)
from .vtm import s16

UK_TOT_ALLOPHONES = 57
PFUK = 0x1D
NON_NASAL_ZERO = 290  # ph_defs.h:161
NASAL_ZERO_CONS = 400  # ph_defs.h:163
F2BACKI = 0o100
F2BACKF = 0o200


def _ukp(code: int) -> int:
    return (PFUK << PSFONT) | code


# UK phone codes referenced by name in `uk_gettar` (`p_all_ph.h`).
UKP_N = _ukp(32)
UKP_NX = _ukp(33)
UKP_EN = _ukp(36)
UKP_HX = _ukp(28)
UKP_JH = _ukp(55)
UKP_OW = _ukp(11)


def _phone_feature(phone: int) -> int:
    """`phone_feature(a,b) = all_featb[b>>8][b&0xff]`; UK/GEN_SIL -> UK_FEATB."""
    return UK_FEATB[phone & 0xFF]


def _begtyp(phone: int) -> int:
    return UK_BEGTYP[phone & 0xFF]


def _endtyp(phone: int) -> int:
    return UK_ENDTYP[phone & 0xFF]


def _ptram(phone: int) -> int:
    return UK_PTRAM[phone & 0xFF]


def uk_gettar(stream: Allophones, npar: int, nphone: int) -> int:
    """Reproduce one `uk_gettar` call for parameter `npar` (0..15) of phone `nphone`.

    Returns the target value, or a negative value < -1 that is a `-pointer` into
    the UK diphthong ROM (the caller resolves it). Mirrors `p_uk_st1.c:76-300`.
    """
    p_tar = UK_MALTAR if stream.malfem == MALE else UK_FEMTAR
    p_amp = UK_MALAMP if stream.malfem == MALE else UK_FEMAMP

    if npar < FZ - 1:
        pphotr = npar * UK_TOT_ALLOPHONES
    else:
        pphotr = (npar - 1) * UK_TOT_ALLOPHONES

    phlas = stream.get_phone(nphone - 1)
    phone = stream.get_phone(nphone)
    phnex = stream.get_phone(nphone + 1)
    phcur = phone
    par_type = PARTYP[npar]

    tartemp = 0

    if par_type > 2:  # IS_FORM_FREQ_OR_BW: F1,F2,F3,B1,B2,B3
        tartemp = p_tar[(phone & PVALUE) + pphotr]
        if tartemp < -1:
            return tartemp  # -pointer into p_diph (no US-style -1 fallback in UK)
        # Fricatives have higher F1 if preceded by a vowel.
        if (npar == F1 - 1
                and _phone_feature(phone) & FOBST != 0
                and _phone_feature(phone) & FSTOP == 0
                and _phone_feature(phlas) & FSYLL != 0):
            tartemp += 40
        # B2 of /n/ before non-front vowels.
        if (phone in (UKP_N, UKP_EN)) and npar == B2 - 1:
            if _begtyp(phnex) != 1:
                tartemp += 60
        # B3 of /n/ adjacent to high-front vowels.
        if (phone in (UKP_N, UKP_EN, UKP_NX)) and npar == B3 - 1:
            if (UK_PLACE[phnex & PVALUE] & F2BACKI != 0
                    or UK_PLACE[phlas & PVALUE] & F2BACKF != 0):
                tartemp = 1600

    elif par_type == 1:  # IS_NASAL_ZERO_FREQ: FZ
        tartemp = NON_NASAL_ZERO
        if _phone_feature(phone) & FNASAL != 0:
            tartemp = NASAL_ZERO_CONS

    elif par_type == 0:  # IS_AV_OR_AH: AV, AP
        if npar == AV - 1:
            tartemp = p_tar[(phone & PVALUE) + pphotr]
            # p_uk_st1.c:163-165 `sprate < 100 && phone == USP_Q` is inert for
            # UK-font phones (USP_Q carries the US font byte) -- not modelled.
            if stream.feat(nphone) & FDUMMY_VOWEL != 0:
                tartemp -= 7
            if (_phone_feature(phone) & FPLOSV != 0
                    and _phone_feature(phlas) & FVOICD == 0):
                tartemp = 0
            if (phone == UKP_HX
                    and _phone_feature(phlas) & FVOICD != 0
                    and stream.feat(nphone) & FSTRESS_1 == 0):
                tartemp = 54
        else:  # AP: aspiration amplitude
            if phone == UKP_HX:
                tartemp = 50
                if _begtyp(phnex) != 1:
                    tartemp = 52
            else:
                tartemp = 0
        # Unstressed reduction applies to both AV and AP in UK.
        if stream.feat(nphone) & FSTRESS == 0:
            tartemp -= 4
            if tartemp < 0:
                tartemp = 0

    elif par_type == 2:  # IS_PARALLEL_FORM_AMP: A2..AB, TILT
        if npar != TILT - 1:
            ptr = _ptram(phone)
            if ptr > 0:
                begtypnex = _begtyp(phnex) - 1
                if phnex == GEN_SIL:
                    begtypnex = _endtyp(phlas) - 1
                if begtypnex == 4:
                    begtypnex = 2
                idx = ptr + (npar - A2 + 1 + (6 * begtypnex))
                tartemp = p_amp[idx]
                if stream.feat(nphone + 1) & FDUMMY_VOWEL != 0:
                    if tartemp >= 4:
                        tartemp -= 4
        else:  # TILT
            tartemp = 0
            if phone == GEN_SIL:
                tartemp = 0
            if phone == UKP_HX:
                tartemp = 20
            elif stream.feat(nphone) & FDUMMY_VOWEL != 0:
                tartemp = 20
            elif _phone_feature(phone) & FOBST != 0:
                tartemp = 7
                if (_phone_feature(phone) & FVOICD != 0
                        and (_phone_feature(phone) & FPLOSV != 0
                             or phcur == UKP_JH)):
                    tartemp = 40
            elif _phone_feature(phone) & FNASAL != 0:
                tartemp = 6
            elif _begtyp(phone) == 1 or _endtyp(phone) == 1:
                if stream.malfem == MALE:
                    tartemp += 3
                else:
                    tartemp += 6
            elif phone == UKP_OW:
                tartemp += 10

    return s16(tartemp)
