"""DECtalk US-English target lookup (`us_gettar`, the target-ROM indexer).

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/ph/p_us_st0.c`, function `us_gettar`, the variant compiled for the
US build where `OLD_SETTAR` is defined). FONIX Corporation declares that source
proprietary and confidential. This file is NOT covered by this project's MIT
licence. See NOTICE.

`us_gettar` is the layer directly below `phsettar`: for one parameter of one
phone it reads the target ROM in `targets.py` and applies the context rules that
select or shift a Klatt target value (or a negative pointer into the diphthong
ROM). `phsettar` (`ph_setar.c:561`) calls it once per parameter per phone and
then wraps the result in coarticulation and forward/backward/special smoothing
(the transition state `phdraw` consumes) -- that wrapping is not ported here.

All arithmetic is the reference's fixed point: `tartemp` is a C `short`, so every
value truncates to 16 bits (`s16`).

Constants transcribed from the compiled headers:
  US_TOT_ALLOPHONES 57      l_all_ph.h:344 (VOICE_ROM_DECTALK_1996M_43F)
  PVALUE 0x00FF, PSFONT 8, PFUSA 0x1E, GEN_SIL 0x1E00   cm_defs.h, ph_defs.h
  param enum F1..TILT (1-based)                          ph_defs.h:492-507
  feature masks (octal)                                  ph_defs.h:187-322
  MALE 1 / FEMALE 0                                      ph_defs.h:707-708
"""
from __future__ import annotations

from dataclasses import dataclass

from .targets import (
    PARINI,
    PARTYP,
    US_BEGTYP,
    US_ENDTYP,
    US_FEATB,
    US_FEMAMP,
    US_FEMDIP,
    US_FEMTAR,
    US_MALAMP,
    US_MALDIP,
    US_MALTAR,
    US_PLACE,
    US_PTRAM,
)
from .vtm import s16

US_TOT_ALLOPHONES = 57
PVALUE = 0x00FF
PSFONT = 8
PFUSA = 0x1E
GEN_SIL = 0x1E00
MALE = 1
FEMALE = 0

# Parameter enum values (`ph_defs.h:492-507`); npar = enum - 1.
F1 = 1
FZ = 4
B2 = 6
B3 = 7
AV = 8
A2 = 10
TILT = 16

# Feature-bit masks (`ph_defs.h`, octal in C).
FSYLL = 0o1
FVOICD = 0o2
FVOWEL = 0o4
FOBST = 0o40
FPLOSV = 0o100
FNASAL = 0o200
FSTOP = 0o20000
FDUMMY_VOWEL = 0o4000
FSTRESS = 0o3
FSTRESS_1 = 0o1
F2BACKI = 0o100
F2BACKF = 0o200


def _usp(code: int) -> int:
    return (PFUSA << PSFONT) | code


# US phone codes referenced by name in `us_gettar` (`l_all_ph.h`).
USP_HX = _usp(28)
USP_N = _usp(32)
USP_NX = _usp(33)
USP_EN = _usp(36)
USP_JH = _usp(55)


@dataclass(frozen=True)
class Allophones:
    """The phone/feature stream `us_gettar` reads, plus the speaker sex.

    Captured from the oracle at each `phsettar` call: the whole `allophons[]` and
    `allofeats[]` arrays for the clause, `nallotot`, and `malfem`. `us_gettar` is
    replayed over these for each (parameter, phone) pair.
    """

    allophons: tuple[int, ...]
    allofeats: tuple[int, ...]
    nallotot: int
    malfem: int

    def get_phone(self, n: int) -> int:
        """`get_phone` (`ph_defs.h:933`): the phone at n, or GEN_SIL out of range."""
        if 0 <= n < self.nallotot:
            return self.allophons[n]
        return GEN_SIL

    def feat(self, n: int) -> int:
        """`allofeats[n]` with the same range guard the C loop guarantees."""
        return self.allofeats[n] if 0 <= n < len(self.allofeats) else 0


def _phone_feature(phone: int) -> int:
    """`phone_feature(a,b) = all_featb[b>>8][b&0xff]`; US/GEN_SIL -> US_FEATB."""
    return US_FEATB[phone & 0xFF]


def _begtyp(phone: int) -> int:
    return US_BEGTYP[phone & 0xFF]


def _endtyp(phone: int) -> int:
    return US_ENDTYP[phone & 0xFF]


def _ptram(phone: int) -> int:
    return US_PTRAM[phone & 0xFF]


def us_gettar(stream: Allophones, npar: int, nphone: int) -> int:
    """Reproduce one `us_gettar` call for parameter `npar` (0..15) of phone `nphone`.

    Returns the target value, or a negative value < -1 that is a `-pointer` into
    the diphthong ROM (the caller resolves it). Mirrors `p_us_st0.c:67-308`.
    """
    p_tar = US_MALTAR if stream.malfem == MALE else US_FEMTAR
    p_diph = US_MALDIP if stream.malfem == MALE else US_FEMDIP
    p_amp = US_MALAMP if stream.malfem == MALE else US_FEMAMP

    # pphotr: no maltar block for the PAP parameter, so >=FZ shifts down one.
    if npar < FZ - 1:
        pphotr = npar * US_TOT_ALLOPHONES
    else:
        pphotr = (npar - 1) * US_TOT_ALLOPHONES

    phlas = stream.get_phone(nphone - 1)
    phone = stream.get_phone(nphone)
    phnex = stream.get_phone(nphone + 1)
    phcur = stream.get_phone(nphone)
    par_type = PARTYP[npar]

    tartemp = 0

    if par_type > 2:  # IS_FORM_FREQ_OR_BW: F1,F2,F3,B1,B2,B3
        tartemp = p_tar[(phone & PVALUE) + pphotr]
        if tartemp < -1:
            return tartemp  # -pointer into p_diph
        if tartemp == -1:
            tartemp = p_tar[(phnex & PVALUE) + pphotr]
            if tartemp == -1:
                nn = stream.get_phone(nphone + 2)
                tartemp = p_tar[(nn & PVALUE) + pphotr]
                if tartemp == -1:
                    tartemp = p_tar[(phlas & PVALUE) + pphotr]
                    if tartemp < -1:
                        while p_diph[-tartemp] != -1:
                            tartemp -= 1
                        tartemp = p_diph[-tartemp - 1]
                    if tartemp == -1:
                        tartemp = PARINI[npar]
        if tartemp < -1:
            tartemp = p_diph[-tartemp]
        # Fricatives have higher F1 if preceded by a vowel.
        if (npar == F1 - 1
                and _phone_feature(phone) & FOBST != 0
                and _phone_feature(phone) & FSTOP == 0
                and _phone_feature(phlas) & FSYLL != 0):
            tartemp += 40
        # B2 of /n/ before non-front vowels.
        if (phone in (USP_N, USP_EN)) and npar == B2 - 1:
            if _begtyp(phnex) != 1:
                tartemp += 60
        # B3 of /n/ adjacent to high-front vowels.
        if (phone in (USP_N, USP_EN, USP_NX)) and npar == B3 - 1:
            if (US_PLACE[phnex & PVALUE] & F2BACKI != 0
                    or US_PLACE[phlas & PVALUE] & F2BACKF != 0):
                tartemp = 1600

    elif par_type == 1:  # IS_NASAL_ZERO_FREQ: FZ
        tartemp = 290
        if _phone_feature(phone) & FNASAL != 0:
            tartemp = 400

    elif par_type == 0:  # IS_AV_OR_AH: AV, AP
        if npar == AV - 1:
            tartemp = p_tar[(phone & PVALUE) + pphotr]
            if stream.feat(nphone) & FDUMMY_VOWEL != 0:
                tartemp -= 7
            if (_phone_feature(phone) & FPLOSV != 0
                    and _phone_feature(phlas) & FVOICD == 0):
                tartemp = 0
            if (phone == USP_HX
                    and _phone_feature(phlas) & FVOICD != 0
                    and stream.feat(nphone) & FSTRESS_1 == 0):
                tartemp = 54
            if stream.feat(nphone) & FSTRESS == 0:
                tartemp -= 4
                if tartemp < 0:
                    tartemp = 0
        else:  # AP: aspiration amplitude
            if phone == USP_HX:
                tartemp = 53
                if _begtyp(phnex) != 1:
                    tartemp = 60
            else:
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
            if phone == USP_HX:
                tartemp = 20
            elif stream.feat(nphone) & FDUMMY_VOWEL != 0:
                tartemp = 20
            elif _phone_feature(phone) & FOBST != 0:
                tartemp = 7
                if (_phone_feature(phone) & FVOICD != 0
                        and (_phone_feature(phone) & FPLOSV != 0
                             or phcur == USP_JH)):
                    tartemp = 40
            elif _phone_feature(phone) & FNASAL != 0:
                tartemp = 6
            elif _begtyp(phone) == 1 or _endtyp(phone) == 1:
                if stream.malfem == FEMALE:
                    tartemp += 6
                else:
                    tartemp += 3

    return s16(tartemp)
