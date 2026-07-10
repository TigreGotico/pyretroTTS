"""DECtalk US-English duration assignment (`us_phtiming`, the `ph/` timing stage).

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/ph/p_us_tim0.c` `us_phtiming`/`durfon`, with `init_timing`,
`inh_timing`, and `min_timing` from `src/dapi/src/ph/ph_timng.c`), for the build
where `ENGLISH_US` and `OLD_INTONATION_AND_TIMING` are defined and `GERMAN`,
`FRENCH`, `SPANISH`, `ENGLISH_UK`, `HLSYN`, `CHANGES_AFTER_V43`, `SLOWTALK`,
`CHANGES_FOR_V44`, and `NEWTYPING_MODE` are not, and `bInTypingMode` is FALSE.
FONIX Corporation declares that source proprietary and confidential. This file
is NOT covered by this project's MIT licence. See NOTICE.

`us_phtiming` (`p_us_tim0.c:90`) runs once per clause. For each allophone it
applies the numbered duration rules (pause syntax, clause-final lengthening,
polysyllabic and cluster shortening, postvocalic-consonant effects, ...) to the
inherent and minimum inherent durations, scales by speaking rate, and writes
`allodurs[nphon]` in 6.4 ms frames, then runs a syllable-level time-alignment
adjustment pass over the sonorants of each completed syllable.

All arithmetic is the reference's fixed point: durations are C `short` and every
intermediate truncates to 16 bits; `mlsh1(x,y)` is `(x*y) >> 14` truncated to 16
bits and `muldv(x,y,z)` a 32-bit `x*y/z` truncating toward zero, both shared
with `phsettar.py`.

`us_mindur` (minimum inherent durations, ms) is read verbatim from the compiled
US voice ROM `p_us_rom_dectalk_1996m_43f.c` (`VOICE_ROM_DECTALK_1996M_43F`); the
inherent durations `us_inhdr` live in `targets_transitions.US_INHDR`.
"""
from __future__ import annotations

from dataclasses import dataclass

from .phsettar import mlsh1, muldv
from .settar import GEN_SIL, _phone_feature, _usp
from .targets_transitions import US_INHDR
from .vtm import s16, s32

# `p_us_rom_dectalk_1996m_43f.c:84` `us_mindur[]` (57 phones, minimum inherent
# duration in ms), indexed by phone & 0xFF.
US_MINDUR: tuple[int, ...] = (
    7, 80, 80, 110, 80, 80, 90, 100, 110, 70, 100, 90,
    110, 80, 80, 90, 100, 50, 50, 120, 120, 120, 120, 120,
    15, 30, 30, 40, 35, 70, 70, 60, 35, 50, 110, 35,
    100, 60, 55, 40, 35, 65, 60, 60, 50, 70, 60, 50,
    40, 75, 65, 20, 50, 5, 100, 70, 20,
)

# Feature bits in `phone_feature` (`ph_defs.h:284-296`).
FSYLL = 0o1
FVOICD = 0o2
FVOWEL = 0o4
FSON1 = 0o10
FSONOR = 0o20
FOBST = 0o40
FPLOSV = 0o100
FNASAL = 0o200
FCONSON = 0o400
FSONCON = 0o1000
FSON2 = 0o2000

# Structure bits in `allofeats` / `sentstruc` (`ph_defs.h:190-296`).
FNOSTRESS = 0
FSTRESS_1 = 0o1
FSTRESS = 0o3
FEMPHASIS = 0o3
FWINITC = 0o4
FMONOSYL = 0o0
FFIRSTSYL = 0o10
FMEDIALSYL = 0o20
FTYPESYL = 0o30
FBOUNDARY = 0o740
FMBNEXT = 0o100
FWBNEXT = 0o140
FPPNEXT = 0o200
FVPNEXT = 0o240
FCBNEXT = 0o340
FSENTENDS = 0o400
FHAT_ENDS = 0o2000
FISBOUND = 0o3000000

# Phone codes referenced by name (`l_us_ph.h`).
USP_YU = _usp(16)
USP_AX = _usp(17)
USP_IX = _usp(18)
USP_W = _usp(24)
USP_LL = _usp(27)
USP_HX = _usp(28)
USP_RX = _usp(29)
USP_LX = _usp(30)
USP_N = _usp(32)
USP_NX = _usp(33)
USP_EN = _usp(36)
USP_TH = _usp(39)
USP_S = _usp(41)
USP_SH = _usp(43)
USP_T = _usp(47)
USP_D = _usp(48)
USP_DX = _usp(51)
USP_Q = _usp(53)
USP_CH = _usp(54)
USP_DF = _usp(56)
USP_IY = _usp(1)
USP_AE = _usp(5)

# `ph_defs.h`: fixed-point/duration constants.
FRAC_ONE = 16384
FRAC_HALF = 8192
NF7MS = 1
NF15MS = 2
NF20MS = 3
NF25MS = 4
NF30MS = 5
NF40MS = 6
N10PRCNT = 1638
N25PRCNT = 4096
N35PRCNT = 5734
N50PRCNT = 8192
N60PRCNT = 9831
N70PRCNT = 11469
N80PRCNT = 13108
N85PRCNT = 13927
N120PRCNT = 19661
N150PRCNT = 24576
NORMAL = 1
SINGING = 4

# `ph_timng.c`.
BASE_ASP = 500
MAX_ASP_COMMA = 8
MIN_ASP_COMMA = -4
MAX_ASP_PERIOD = 20
MIN_ASP_PERIOD = -10


def _cdiv(a: int, b: int) -> int:
    """C integer division truncating toward zero."""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def inh_timing(phone: int) -> int:
    """`inh_timing` (`ph_timng.c:448`): inherent duration (ms) for a US phone."""
    if (phone & 0xFF) >= 100:
        return 0
    return US_INHDR[phone & 0xFF]


def min_timing(phone: int) -> int:
    """`min_timing` (`ph_timng.c:401`): minimum inherent duration (ms)."""
    if (phone & 0xFF) >= 100:
        return 0
    return US_MINDUR[phone & 0xFF]


@dataclass
class TimingConfig:
    """Per-clause scalars `us_phtiming` reads outside the allophone stream.

    Defaults match a plain `say -a <text>` clause: no user prosodics, the
    English `nfperiod`/`nfcomma`, aspiration reset to zero.
    """

    sprate: int = 180
    nfcomma: int = 16
    nfperiod: int = 75
    compause: int = 0
    perpause: int = 0
    newparagsw: int = 0
    f0mode: int = NORMAL
    asperation: int = 0


@dataclass
class _Rate:
    sprat0: int = 0
    sprat1: int = 0
    sprat2: int = 0
    timeref: int = 0


def init_timing(sprate: int) -> _Rate:
    """`init_timing` (`ph_timng.c:174`) for `LANG_english`: speaking-rate factors."""
    r = _Rate()
    r.timeref = _cdiv(16000, sprate)
    if sprate > 250:
        r.sprat0 = 250 + ((sprate - 250) >> 1)
    else:
        r.sprat0 = sprate
    if r.sprat0 >= 180:
        temp3 = 220
        temp2 = 425 - r.sprat0
    else:
        temp3 = 120
        temp2 = 300 - r.sprat0
    if temp2 < 0:
        temp2 = 1
    r.sprat1 = muldv(FRAC_ONE, temp2, temp3)
    if r.sprat0 > 180:
        temp2 = 460 - r.sprat0
        temp3 = 280
        if temp2 <= 0:
            temp2 = 1
        r.sprat2 = muldv(FRAC_ONE, temp2, temp3)
    else:
        r.sprat2 = ((r.sprat1 + FRAC_ONE) & 0xFFFF) >> 1
    return r


def us_phtiming(
    allophons: tuple[int, ...],
    allofeats: tuple[int, ...],
    user_durs: tuple[int, ...],
    nallotot: int,
    cfg: TimingConfig,
) -> list[int]:
    """`us_phtiming` (`p_us_tim0.c:90`): assign `allodurs[nphon]` in frames.

    `allofeats`/`user_durs` are indexed like `allophons` (offset already applied
    by the caller). Returns the `allodurs` list of length `nallotot`.
    """
    rate = init_timing(cfg.sprate)
    sprat0, sprat1, sprat2 = rate.sprat0, rate.sprat1, rate.sprat2
    timeref = rate.timeref
    asperation = cfg.asperation

    allodurs = [0] * nallotot

    def phone(n: int) -> int:
        # `allophons[]` beyond `nallotot` is the zero-initialized array tail.
        return allophons[n] if 0 <= n < len(allophons) else 0

    def feats(n: int) -> int:
        return allofeats[n] & 0xFFFFFFFF if 0 <= n < len(allofeats) else 0

    pholas = GEN_SIL
    struclas = 0
    fealas = _phone_feature(GEN_SIL)
    emphasissw = False
    stcnt = 0
    syldur = 0
    vowcnt = 0
    # `phonex_timing`/`strucnex`/`feanex` are updated only while
    # `nphon < nallotot - 1`; on the last phone they keep the prior value.
    phonex = 0
    strucnex = 0
    feanex = 0

    for nphon in range(nallotot):
        if nphon > 0:
            pholas = allophons[nphon - 1]
            struclas = feats(nphon - 1)
            fealas = _phone_feature(pholas)
        phocur = allophons[nphon]
        struccur = feats(nphon)
        strucboucur = struccur & FBOUNDARY
        feacur = _phone_feature(phocur)
        feasyllabiccur = feacur & FSYLL
        strucstresscur = struccur & FSTRESS

        if nphon < nallotot - 1:
            phonex = phone(nphon + 1)
            strucnex = feats(nphon + 1)
            feanex = _phone_feature(phonex)

        durxx = 0

        if user_durs[nphon] != 0:
            durxx = ((s32(user_durs[nphon] + 4) * 10) >> 6)
        elif phocur == GEN_SIL:
            if ((feanex & FVOICD) and (feanex & FOBST)) or (feanex & FPLOSV):
                dpause = 1
            else:
                dpause = 0
            asperation = _cdiv(asperation - BASE_ASP, 10)
            if nphon > 1:
                if (struclas & FBOUNDARY) == FCBNEXT:
                    if asperation > MAX_ASP_COMMA:
                        asperation = MAX_ASP_COMMA
                    asperation = MIN_ASP_COMMA
                    dpause = cfg.nfcomma + cfg.compause + asperation
                if ((struclas & FBOUNDARY) & FSENTENDS) != 0:
                    if asperation > MAX_ASP_PERIOD:
                        asperation = MAX_ASP_PERIOD
                    asperation = MIN_ASP_PERIOD
                    dpause = cfg.nfperiod + cfg.perpause + asperation
            elif cfg.newparagsw != 0:
                dpause = cfg.nfperiod
            asperation = 0
            dpause = mlsh1(dpause, sprat1)
            if dpause < NF7MS:
                dpause = NF7MS
            durxx = dpause
        else:
            durinh = ((inh_timing(phocur) * 10) + 50) >> 6
            durmin = ((min_timing(phocur) * 10) + 50) >> 6
            deldur = 0
            prcnt = 128

            # Rule 2: clause-final rime lengthening.
            if strucboucur >= FCBNEXT:
                deldur = NF40MS
                if (feacur & FVOICD) and (feacur & FOBST):
                    deldur = NF20MS
                if feacur & FPLOSV:
                    deldur = 0
                if (phocur in (USP_RX, USP_LX)) and (feanex & FOBST) and not (feanex & FVOICD):
                    deldur = NF15MS
                if (nallotot < 10) and feasyllabiccur and strucstresscur:
                    deldur += (NF30MS - (nallotot >> 1))
                if feanex & FSON1:
                    deldur -= NF20MS

            # Rule 3.
            if feasyllabiccur:
                if ((strucboucur < FVPNEXT) and (cfg.sprate > 160)) or (strucboucur < FPPNEXT):
                    prcnt = mlsh1(N70PRCNT, prcnt)

            # Rule 4/5.
            if feasyllabiccur:
                if ((strucstresscur & FSTRESS_1) == 0) and ((struccur & FTYPESYL) == FMONOSYL):
                    arg1 = N85PRCNT
                    if strucstresscur == 0:
                        arg1 = N70PRCNT
                    prcnt = mlsh1(arg1, prcnt)
                elif ((struccur & FTYPESYL) != FMONOSYL) and (strucboucur < FWBNEXT):
                    arg1 = N85PRCNT
                    if (struccur & FTYPESYL) > FFIRSTSYL:
                        arg1 = N85PRCNT
                    prcnt = mlsh1(arg1, prcnt)
                if (struccur & FTYPESYL) != FMONOSYL:
                    prcnt = mlsh1(prcnt, N80PRCNT)

            # Rule 6.
            if (feasyllabiccur == 0) and ((struccur & FWINITC) == 0):
                if (feacur & FOBST) and not (feacur & FPLOSV) and ((struccur & FBOUNDARY) == FWBNEXT):
                    deldur += NF20MS
                else:
                    prcnt = mlsh1(prcnt, N85PRCNT)

            # Rule 7.
            if (strucstresscur & FSTRESS_1) == 0:
                if (durmin < durinh) and ((feacur & FOBST) == 0):
                    if strucstresscur == 0:
                        durmin = durmin >> 1
                    else:
                        durmin -= (durmin >> 2)
                if feasyllabiccur:
                    if (struccur & FTYPESYL) == FMEDIALSYL:
                        prcnt = prcnt >> 1
                    else:
                        prcnt = mlsh1(prcnt, N70PRCNT)
                    if phocur in (USP_AX, USP_IX):
                        if (pholas == USP_DX) or (phonex == USP_DX) or (phonex == USP_HX):
                            deldur += NF25MS
                else:
                    if USP_W <= phocur <= USP_LL:
                        prcnt = prcnt >> 1
                    else:
                        prcnt = mlsh1(prcnt, N70PRCNT)
            else:
                if feasyllabiccur:
                    if (struccur & FHAT_ENDS) and (strucboucur < FVPNEXT) and (strucboucur > FMBNEXT):
                        deldur += NF25MS

            # Rule 8.
            if (struccur & FWINITC) or (feasyllabiccur and (strucstresscur != FEMPHASIS)):
                emphasissw = False
            if strucstresscur == FEMPHASIS:
                emphasissw = True
            if emphasissw:
                deldur += NF20MS
                if feasyllabiccur:
                    deldur += NF40MS

            # Rule 9: postvocalic-consonant effects.
            psonsw = 0
            arg1 = FRAC_ONE
            posvoc = GEN_SIL
            if feasyllabiccur or (
                (USP_RX <= phocur <= USP_NX)
                and ((struccur & (FSTRESS | FWINITC)) == 0)
                and (feanex & FOBST)
            ):
                if ((feanex & FSYLL) == 0) and ((strucnex & (FSTRESS | FWINITC)) == 0):
                    posvoc = phonex
                    if (
                        (USP_RX <= posvoc <= USP_NX)
                        and (_phone_feature(phone(nphon + 2)) & FOBST)
                        and ((feats(nphon + 2) & (FSTRESS | FWINITC)) == 0)
                    ):
                        psonsw = 1
                        posvoc = phone(nphon + 2)
                    if posvoc != GEN_SIL:
                        if (_phone_feature(posvoc) & FVOICD) == 0:
                            deldur = deldur - (deldur >> 1)
                            arg1 = N80PRCNT
                            if (_phone_feature(posvoc) & FPLOSV) or (posvoc == USP_CH):
                                arg1 = N70PRCNT
                        else:
                            if (_phone_feature(posvoc) & FOBST) and phocur != USP_EN:
                                arg1 = N120PRCNT
                                if (
                                    (_phone_feature(posvoc) & FPLOSV) == 0
                                    and (posvoc != USP_DX)
                                    and (feacur & FSYLL)
                                ):
                                    deldur += NF25MS
                            elif _phone_feature(posvoc) & FNASAL:
                                arg1 = N85PRCNT
                if (strucboucur < FVPNEXT) or (psonsw == 1):
                    arg1 = FRAC_HALF + (arg1 >> 1)
                if (
                    (phocur == USP_N and phonex == USP_T)
                    and ((strucnex & (FWINITC | FSTRESS)) == 0)
                ):
                    arg1 = N10PRCNT
                    if (
                        (_phone_feature(phone(nphon + 2)) & FSYLL)
                        and ((feats(nphon + 2) & FMEDIALSYL) == 0)
                    ):
                        # Change to [d] after durations (mutates the stream).
                        allophons = allophons[:nphon + 1] + (USP_D,) + allophons[nphon + 2:]
                        arg1 = N70PRCNT
                prcnt = mlsh1(arg1, prcnt)

            # Rule 10/11/12 (syllabic) or Rule 13 (consonant clusters).
            if feasyllabiccur:
                if feanex & FSYLL:
                    deldur += NF30MS
                if (
                    (struccur & FTYPESYL) == FFIRSTSYL
                    and (struccur & FSTRESS_1)
                    and ((struclas & FWINITC) == 0)
                ):
                    deldur += NF25MS
                if phonex == USP_LX:
                    deldur -= NF20MS
            else:
                if feacur & FCONSON:
                    if (feanex & FCONSON) and (strucboucur < FVPNEXT):
                        arg1 = N70PRCNT
                        if (feacur & FNASAL) and (strucnex & FWINITC):
                            arg1 = N150PRCNT
                        else:
                            durmin -= (durmin >> 2)
                        if phocur in (USP_S, USP_TH):
                            if feanex & FPLOSV:
                                arg1 = FRAC_HALF
                            if phonex == USP_SH:
                                durxx = NF15MS
                                _store(allodurs, nphon, durxx)
                                continue
                        prcnt = mlsh1(arg1, prcnt)
                    if (fealas & FCONSON) and ((struclas & FBOUNDARY) < FVPNEXT):
                        arg1 = N70PRCNT
                        durmin -= (durmin >> 2)
                        if feacur & FPLOSV:
                            if pholas == USP_S:
                                arg1 = N60PRCNT
                            if fealas & FNASAL:
                                if strucstresscur == 0:
                                    arg1 = 1638
                        prcnt = mlsh1(arg1, prcnt)

            # Rule 14.
            if feacur & FSON1:
                if (fealas & FVOICD) == 0 and (fealas & FPLOSV):
                    deldur += NF20MS
            # Rule 15.
            if feacur & FVOWEL:
                if pholas == GEN_SIL:
                    deldur += NF20MS
            # Rule 16.
            if feacur & FVOWEL:
                if (fealas & FSON2) and ((fealas & FNASAL) == 0):
                    if deldur == 0:
                        deldur = NF20MS
            # Rule 17.
            if (nallotot < 10) and (durinh != durmin):
                prcnt += 30
            # Rule 19.
            if (
                phocur == USP_TH
                and ((struccur & FTYPESYL) == FMONOSYL)
                and (strucboucur >= FWBNEXT)
                and (strucstresscur == FNOSTRESS)
            ):
                prcnt = mlsh1(prcnt, N60PRCNT)
            # Rule 20.
            if (
                phocur == USP_IY
                and ((struccur & FBOUNDARY) > FMBNEXT)
                and (strucstresscur == FNOSTRESS)
                and ((struccur & FTYPESYL) == FMONOSYL)
            ):
                prcnt = mlsh1(prcnt, N150PRCNT)
            # Rule 21.
            if (
                (feacur & FPLOSV)
                and (fealas & FPLOSV)
                and (feanex & FOBST)
                and (strucboucur > FMBNEXT)
            ):
                durmin = durmin >> 1
                prcnt = mlsh1(prcnt, N25PRCNT)
            # Rule 23.
            if phonex == USP_DF:
                prcnt = mlsh1(prcnt, N35PRCNT)
            if (feanex & FPLOSV) and (feacur & FCONSON):
                durmin = durmin >> 1
                prcnt = mlsh1(prcnt, N50PRCNT)

            # Finish up.
            durxx = s16((prcnt * (durinh - durmin)) >> 7)
            durxx = s16(durxx + durmin)
            if (sprat0 != 180) and (durxx != 0):
                durxx = mlsh1(durxx, sprat2) + 1
                deldur = mlsh1(deldur, sprat1)
            durxx = s16(durxx + deldur)
            if durxx < 0:
                durxx = 1

            allodurs[nphon] = durxx
            if allophons[nphon] != 0:
                syldur += durxx
            if (feacur & FSONOR) and allophons[nphon] != 0:
                vowcnt += 1

            if (((struccur & FISBOUND) == FISBOUND) and nphon != 0) or (nphon == nallotot - 2):
                if vowcnt == 1:
                    adjust = timeref - (syldur >> 1)
                elif vowcnt == 2:
                    adjust = (timeref - (syldur >> 1)) >> 1
                elif vowcnt == 3:
                    adjust = ((timeref - (syldur >> 1)) >> 3) * 3
                elif vowcnt == 4:
                    adjust = (timeref - (syldur >> 1)) >> 2
                elif vowcnt == 5:
                    adjust = (timeref - (syldur >> 1)) >> 3
                else:
                    adjust = (timeref - (syldur >> 1)) >> 4
                if sprat0 <= 250:
                    adjust = 0
                elif sprat0 >= 325:
                    adjust = adjust >> 1
                elif sprat0 >= 250:
                    adjust = adjust >> 2
                if user_durs[nphon] != 0 or cfg.f0mode == SINGING:
                    adjust = 0
                endcnt = nphon
                while stcnt - endcnt:
                    if 0 < allophons[endcnt] <= 7:
                        allodurs[endcnt] = s16(allodurs[endcnt] + adjust)
                        if allodurs[endcnt] <= 6:
                            allodurs[endcnt] = 6
                    endcnt -= 1
                stcnt = nphon
                syldur = 0
                vowcnt = 0

        # break3:
        if durxx <= 0:
            durxx = 1
        _store(allodurs, nphon, durxx)

    return allodurs


def _store(allodurs: list[int], nphon: int, durxx: int) -> None:
    allodurs[nphon] = durxx
