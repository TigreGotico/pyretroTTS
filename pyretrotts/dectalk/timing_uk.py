"""DECtalk UK-English duration assignment (`uk_phtiming`, the `ph/` timing stage).

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/ph/p_uk_tim.c` `uk_phtiming`, included through `ph/ph_time1.c`;
with `init_timing`, `inh_timing`, and `min_timing` from `ph/ph_timng.c`), for the
build where `ENGLISH` and `ENGLISH_UK` and `OLD_INTONATION_AND_TIMING` are defined
and `GERMAN`, `FRENCH`, `SPANISH`, `HLSYN`, `CHANGES_AFTER_V43`, `SLOWTALK`,
`NEWTYPING_MODE`, `FASTTALK`, `TOMBUCHLER`, and `NEVER_USED` are not, and
`bInTypingMode` is FALSE. FONIX Corporation declares that source proprietary and
confidential. This file is NOT covered by this project's MIT licence. See NOTICE.

`uk_phtiming` (`p_uk_tim.c:107`) runs once per clause. It is the UK-parameterized
analogue of `us_phtiming` (`timing.us_phtiming`); this module keeps the US path
untouched and models the UK deltas verified against `p_uk_tim.c`:

* `init_timing` (`ph_timng.c:190`) for `LANG_british` adds 20 to the speaking rate
  before deriving `timeref` and the rate factors, then subtracts 40 from `sprat0`
  (floor 65) under `#ifdef ENGLISH_UK`. So a `-r 180` clause runs at effective
  rate 200 with `sprat0 = 160` (`timeref 80`, `sprat1 19114`, `sprat2 17749`);
* `GEN_SIL` pause: `dpause 4/5` (US `1/0`), pause floor 2 (US `NF7MS == 1`), and
  the next-phone gate `feanex & (FVOICD | FOBST)` (US required both bits);
* Rule 2 clause-final lengthening also requires `number_words >= 4`, and uses only
  `[LX]` (US used `[RX], [LX]`);
* the nasal-lengthening rules (`:398-411`), the `durmin < 6` floor in Rule 7
  (`:509`), Rule 6 boundary `>= FWBNEXT` (US `== FWBNEXT`), the Rule 9 nasal
  `N70PRCNT` (US `N85PRCNT`) and the `arg1 < 500 -> 4196` clamp (`:690`), the
  Rule 13 plosive-plosive `arg1` guard and nasal `N120PRCNT` (US `N150PRCNT`),
  the voiced/voiceless plosive rule (`:850`), Rule 18 (`FSONCON` after obstruent,
  `:867`), Rule 17 `prcnt += 10` (US `+= 30`), the dropped Rule 20 (`#ifdef
  OUTFORNOW`), Rule 23 gated on `prcnt > 50` with `N40PRCNT` (US `N35PRCNT`
  unconditional), the `[RR]` `durmin` floor 13 (`:931`), the unvoiced-after-vowel
  Rule 25 (`N130PRCNT`, `:938`), the word-initial `[HX]` Rule 26 (`N60PRCNT`,
  `:949`), the absolute stop-`durmin` floors 6/6/14 (`:960-994`);
* the syllable time-alignment pass keys off each stressed syllabic (US off syllable
  boundaries), counts sonorants (`FSON1`) not vowels, uses `timeref - syldur` (US
  `timeref - (syldur >> 1)`), the `sprat0 <= 150` / `>> 2` / `nphon < 3 >> 3`
  scaling, and only lengthens non-nasal sonorants with `endcnt >= 2`.

All arithmetic is the reference's fixed point: durations are C `short` and every
intermediate truncates to 16 bits; `mlsh1(x,y)` is `(x*y) >> 14` truncated to 16
bits and `muldv(x,y,z)` a 32-bit `x*y/z` truncating toward zero, both shared with
`phsettar.py`. `uk_mindur` (minimum inherent durations, ms) is read verbatim from
the compiled UK voice ROM `p_uk_rom.c`; the inherent durations `uk_inhdr` live in
`targets_transitions_uk.UK_INHDR` (accessed through `phsettar_uk`).
"""
from __future__ import annotations

from dataclasses import dataclass

from .phsettar import mlsh1, muldv
from .phsettar_uk import (
    PFUK,
    PSFONT,
    UKP_AX,
    UKP_CH,
    UKP_D,
    UKP_DX,
    UKP_DZ,
    UKP_EN,
    UKP_HX,
    UKP_IX,
    UKP_LL,
    UKP_LX,
    UKP_N,
    UKP_NX,
    UKP_Q,
    UKP_RR,
    UKP_S,
    UKP_SH,
    UKP_T,
    UKP_TH,
    UKP_W,
    _ukp,
    phone_feature,
)
from .settar import GEN_SIL
from .targets_transitions_uk import UK_INHDR
from .timing import (
    BASE_ASP,
    FBOUNDARY,
    FCBNEXT,
    FEMPHASIS,
    FHAT_ENDS,
    FMBNEXT,
    FMEDIALSYL,
    FMONOSYL,
    FNOSTRESS,
    FPPNEXT,
    FSENTENDS,
    FSTRESS,
    FSTRESS_1,
    FTYPESYL,
    FVPNEXT,
    FWBNEXT,
    FWINITC,
    MAX_ASP_COMMA,
    MAX_ASP_PERIOD,
    MIN_ASP_COMMA,
    MIN_ASP_PERIOD,
    NF15MS,
    NF20MS,
    NF25MS,
    NF30MS,
    NF40MS,
    SINGING,
    TimingConfig,
    _cdiv,
)
from .vtm import s16, s32

# Feature bits (`ph_defs.h:284-300`).
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
FSTOP = 0o20000
FFIRSTSYL = 0o10
FSYLL = 0o1

# Percentage constants (`ph_defs.h:435-478`).
FRAC_ONE = 16384
FRAC_HALF = 8192
N10PRCNT = 1638
N25PRCNT = 4096
N40PRCNT = 6554
N50PRCNT = 8192
N60PRCNT = 9831
N70PRCNT = 11469
N80PRCNT = 13108
N85PRCNT = 13927
N90PRCNT = 13927   # note: N90PRCNT == N85PRCNT in the reference (ph_defs.h:458)
N100PRCNT = 16384
N120PRCNT = 19661
N130PRCNT = 21298
N150PRCNT = 24576
N160PRCNT = 26215

# Part-of-speech word features (`ph_defs.h:185,266-269`).
WORDFEAT = 0xFFFF0000
F_NOUN = 0o2000000
F_ADJ = 0o4000000
F_VERB = 0o10000000
F_FUNC = 0o20000000

# UK phone code for `[DF]` (index 56); not in the phsettar_uk 1..55 tuple.
UKP_DF = _ukp(56)

# `p_uk_rom.c:142` `uk_mindur[]` (57 phones, minimum inherent duration in ms),
# indexed by phone & 0xFF. Differs from `us_mindur` at indices 1, 2, 29, 32, 51.
UK_MINDUR: tuple[int, ...] = (
    7, 70, 60, 110, 80, 80, 90, 100, 110, 70, 100, 90,
    110, 80, 80, 90, 100, 50, 50, 120, 120, 120, 120, 120,
    15, 30, 30, 40, 35, 80, 70, 60, 50, 50, 110, 35,
    100, 60, 55, 40, 35, 65, 60, 60, 50, 70, 60, 50,
    40, 75, 65, 160, 50, 5, 100, 70, 20,
)


def _uk(phone: int) -> bool:
    return (phone >> PSFONT) == PFUK


def uk_inh_timing(phone: int) -> int:
    """`inh_timing` (`ph_timng.c:227`) for `LANG_british`."""
    if (phone & 0xFF) >= 100:
        return 0
    return UK_INHDR[phone & 0xFF]


def uk_min_timing(phone: int) -> int:
    """`min_timing` (`ph_timng.c:180`) for `LANG_british`."""
    if (phone & 0xFF) >= 100:
        return 0
    return UK_MINDUR[phone & 0xFF]


@dataclass
class _Rate:
    sprat0: int = 0
    sprat1: int = 0
    sprat2: int = 0
    timeref: int = 0
    sprate: int = 0


def uk_init_timing(sprate: int) -> _Rate:
    """`init_timing` (`ph_timng.c:190`) for `LANG_british` with `ENGLISH_UK`.

    Returns the rate factors and the effective (mutated) speaking rate: the UK
    branch adds 20 to `sprate` before deriving `timeref` and the factors, and the
    rest of `uk_phtiming` reads that mutated rate.
    """
    r = _Rate()
    sprate = sprate + 20
    r.sprate = sprate
    r.timeref = _cdiv(16000, sprate)
    if sprate > 250:
        r.sprat0 = 250 + ((sprate - 250) >> 1)
    else:
        r.sprat0 = sprate
    # #ifdef ENGLISH_UK
    r.sprat0 -= 40
    if r.sprat0 <= 65:
        r.sprat0 = 65
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


def uk_phtiming(
    allophons: tuple[int, ...],
    allofeats: tuple[int, ...],
    user_durs: tuple[int, ...],
    nallotot: int,
    cfg: TimingConfig,
    number_words: int = 0,
    rate: _Rate | None = None,
) -> list[int]:
    """`uk_phtiming` (`p_uk_tim.c:107`): assign `allodurs[nphon]` in frames.

    `allofeats`/`user_durs` are indexed like `allophons`. `number_words` is the
    per-clause word count (`ph_sort.c` `number_words`) Rule 2 reads. Returns the
    `allodurs` list of length `nallotot`.

    `init_timing` (`ph_timng.c:180`) recomputes the rate factors and adds 20 to the
    speaking rate only when `sprate != sprlast`, so the first clause of an utterance
    latches them and later clauses reuse the same `_Rate`. Pass a precomputed `rate`
    to reproduce that latch across a multi-clause utterance; otherwise it is derived
    from `cfg.sprate` for a lone clause.
    """
    if rate is None:
        rate = uk_init_timing(cfg.sprate)
    sprat0, sprat1, sprat2 = rate.sprat0, rate.sprat1, rate.sprat2
    timeref = rate.timeref
    sprate = rate.sprate  # effective (mutated) rate the rest of the loop reads
    asperation = cfg.asperation

    allophons = tuple(allophons)
    allodurs = [0] * nallotot

    def phone(n: int) -> int:
        return allophons[n] if 0 <= n < len(allophons) else 0

    def feats(n: int) -> int:
        return allofeats[n] & 0xFFFFFFFF if 0 <= n < len(allofeats) else 0

    pholas = GEN_SIL
    struclas = 0
    fealas = phone_feature(GEN_SIL)
    emphasissw = False
    stcnt = 0
    syldur = 0
    sonocnt = 0
    phonex = 0
    strucnex = 0
    feanex = 0

    for nphon in range(nallotot):
        if nphon > 0:
            pholas = allophons[nphon - 1]
            struclas = feats(nphon - 1)
            fealas = phone_feature(pholas)
        phocur = allophons[nphon]
        struccur = feats(nphon)
        strucboucur = struccur & FBOUNDARY
        feacur = phone_feature(phocur)
        feasyllabiccur = feacur & FSYLL
        strucstresscur = struccur & FSTRESS

        if nphon < nallotot - 1:
            phonex = phone(nphon + 1)
            strucnex = feats(nphon + 1)
            feanex = phone_feature(phonex)

        wordfeat = feats(nphon) & WORDFEAT

        durxx = 0

        if user_durs[nphon] != 0:
            durxx = ((s32(user_durs[nphon] + 4) * 10) >> 6)
            durxx = _finish_break3(durxx, 0, sprat0, sprat2, sprat1)
            allodurs[nphon] = durxx if durxx > 0 else 1
            (stcnt, syldur, sonocnt) = _post_loop(
                allodurs, allophons, feats, phone_feature, nphon, nallotot,
                allodurs[nphon], feacur, struccur, feasyllabiccur,
                strucstresscur, timeref, sprat0, user_durs, cfg,
                stcnt, syldur, sonocnt)
            continue

        durinh = ((uk_inh_timing(phocur) * 10) + 50) >> 6
        durmin = ((uk_min_timing(phocur) * 10) + 50) >> 6

        # Part-of-speech shortening (`p_uk_tim.c:216-249`).
        if wordfeat and nphon < nallotot - 3:
            if wordfeat & F_NOUN:
                wordfeat = N120PRCNT
            elif wordfeat & F_ADJ:
                wordfeat = N100PRCNT
            elif wordfeat & F_VERB:
                wordfeat = N70PRCNT
            elif wordfeat & F_FUNC:
                if nallotot > 7 and not (phone_feature(phocur) & FOBST):
                    wordfeat = N80PRCNT
                else:
                    wordfeat = N100PRCNT
            else:
                wordfeat = N100PRCNT
        else:
            wordfeat = N100PRCNT

        deldur = 0
        prcnt = 128
        if wordfeat:
            prcnt = mlsh1(wordfeat, prcnt)

        if phocur == GEN_SIL:
            if (feanex & (FVOICD | FOBST)) or (feanex & FPLOSV):
                dpause = 4
            else:
                dpause = 5
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
            if dpause < 2:
                dpause = 2
            durxx = _finish_break3(dpause, 0, sprat0, sprat2, sprat1)
            allodurs[nphon] = durxx if durxx > 0 else 1
            (stcnt, syldur, sonocnt) = _post_loop(
                allodurs, allophons, feats, phone_feature, nphon, nallotot,
                allodurs[nphon], feacur, struccur, feasyllabiccur,
                strucstresscur, timeref, sprat0, user_durs, cfg,
                stcnt, syldur, sonocnt)
            continue

        # Rule 2: clause-final rime lengthening.
        if strucboucur >= FCBNEXT and number_words >= 4:
            deldur = NF40MS
            if (feacur & FVOICD) and (feacur & FOBST):
                deldur = NF20MS
            if feacur & FPLOSV:
                deldur = 0
            if (phocur == UKP_LX) and (feanex & FOBST) and not (feanex & FVOICD):
                deldur = NF15MS
            if (nallotot < 10) and feasyllabiccur and strucstresscur:
                deldur += (NF30MS - (nallotot >> 1))
            if feanex & FSON1:
                deldur -= NF20MS

        # Rule 3: shorten non-phrase-final syllabics.
        if feasyllabiccur:
            if ((strucboucur < FVPNEXT) and (sprate > 160)) or (strucboucur < FPPNEXT):
                prcnt = mlsh1(N80PRCNT, prcnt)

        # Nasal-lengthening rules (`p_uk_tim.c:398-411`).
        if (feacur & FNASAL) and (fealas & FNASAL):
            if phocur != pholas:
                deldur += NF30MS
        if (feacur & FNASAL) and (strucstresscur == 0) and (strucboucur >= FVPNEXT):
            deldur += NF40MS

        # Rule 4/5.
        if feasyllabiccur:
            if (struccur & FTYPESYL) == FMONOSYL:
                arg1 = N90PRCNT
                if (strucstresscur & FSTRESS_1) == 0:
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
            if (feacur & FOBST) and not (feacur & FPLOSV) and ((struccur & FBOUNDARY) >= FWBNEXT):
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
                if durmin < 6:
                    durmin = 6
            if feasyllabiccur:
                if (struccur & FTYPESYL) == FMEDIALSYL:
                    prcnt -= prcnt >> 2
                else:
                    prcnt = mlsh1(prcnt, N70PRCNT)
                if phocur in (UKP_AX, UKP_IX):
                    if (pholas == UKP_DX) or (phonex == UKP_DX) or (phonex == UKP_HX):
                        deldur += NF15MS
            else:
                if UKP_W <= phocur <= UKP_LL:
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
            (UKP_LX <= phocur <= UKP_NX)
            and ((struccur & (FSTRESS | FWINITC)) == 0)
            and (feanex & FOBST)
        ):
            if ((feanex & FSYLL) == 0) and ((strucnex & (FSTRESS | FWINITC)) == 0):
                posvoc = phonex
                if (
                    (UKP_LX <= posvoc <= UKP_NX)
                    and (phone_feature(phone(nphon + 2)) & FOBST)
                    and ((feats(nphon + 2) & (FSTRESS | FWINITC)) == 0)
                ):
                    psonsw = 1
                    posvoc = phone(nphon + 2)
                if posvoc != GEN_SIL:
                    if (phone_feature(posvoc) & FVOICD) == 0:
                        deldur = deldur - (deldur >> 1)
                        arg1 = N80PRCNT
                        if (phone_feature(posvoc) & FPLOSV) or (posvoc == UKP_CH):
                            arg1 = N70PRCNT
                    else:
                        if (phone_feature(posvoc) & FOBST) and phocur != UKP_EN:
                            arg1 = N120PRCNT
                            if (
                                (phone_feature(posvoc) & FPLOSV) == 0
                                and (posvoc != UKP_DX)
                                and (feacur & FSYLL)
                            ):
                                deldur += NF25MS
                        elif phone_feature(posvoc) & FNASAL:
                            arg1 = N70PRCNT
            if (strucboucur < FVPNEXT) or (psonsw == 1):
                arg1 = FRAC_HALF + (arg1 >> 1)
            if (
                (phocur == UKP_N and phonex == UKP_T)
                and ((strucnex & (FWINITC | FSTRESS)) == 0)
            ):
                arg1 = N10PRCNT
                if (
                    (phone_feature(phone(nphon + 2)) & FSYLL)
                    and ((feats(nphon + 2) & FMEDIALSYL) == 0)
                ):
                    allophons = allophons[:nphon + 1] + (UKP_D,) + allophons[nphon + 2:]
                    arg1 = N70PRCNT
            if arg1 < 500:
                arg1 = 4196
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
            if phonex == UKP_LX:
                prcnt = mlsh1(N70PRCNT, prcnt)
        else:
            if feacur & FCONSON:
                if (feanex & FCONSON) and (strucboucur < FVPNEXT):
                    if ((feanex & FPLOSV) == 0) or ((feacur & FPLOSV) == 0):
                        arg1 = N70PRCNT
                    if (feacur & FNASAL) and (strucnex & FWINITC):
                        arg1 = N120PRCNT
                    else:
                        durmin -= (durmin >> 2)
                    if phocur in (UKP_S, UKP_TH):
                        if feanex & FPLOSV:
                            arg1 = FRAC_HALF
                        if phonex == UKP_SH:
                            durxx = NF15MS
                            allodurs[nphon] = durxx
                            durxx = _finish_break3(durxx, deldur, sprat0, sprat2, sprat1)
                            allodurs[nphon] = durxx if durxx > 0 else 1
                            (stcnt, syldur, sonocnt) = _post_loop(
                                allodurs, allophons, feats, phone_feature, nphon,
                                nallotot, allodurs[nphon], feacur, struccur,
                                feasyllabiccur, strucstresscur, timeref, sprat0,
                                user_durs, cfg, stcnt, syldur, sonocnt)
                            continue
                    prcnt = mlsh1(arg1, prcnt)
                if (fealas & FCONSON) and ((struclas & FBOUNDARY) < FVPNEXT):
                    arg1 = N70PRCNT
                    durmin -= (durmin >> 2)
                    if feacur & FPLOSV:
                        if pholas == UKP_S:
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
            prcnt += 10

        # Voiced/voiceless plosive rule (`p_uk_tim.c:850`).
        if (feacur & FPLOSV) and (feacur & FOBST):
            arg1 = N80PRCNT
            if phone_feature(phone(nphon + 1)) & FVOICD:
                arg1 = N70PRCNT
            prcnt = mlsh1(arg1, prcnt)

        # Rule 18: prevocalic clustered semivowels (`p_uk_tim.c:867`).
        if (feacur & FSONCON) and (fealas & FOBST):
            prcnt = mlsh1(prcnt, N70PRCNT)

        # Rule 19.
        if (
            phocur == UKP_TH
            and ((struccur & FTYPESYL) == FMONOSYL)
            and (strucboucur >= FWBNEXT)
            and (strucstresscur == FNOSTRESS)
        ):
            prcnt = mlsh1(prcnt, N60PRCNT)

        # Rule 20 is `#ifdef OUTFORNOW` in the UK build -- dropped.

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
        if phonex == UKP_DF:
            if prcnt > 50:
                prcnt = mlsh1(prcnt, N40PRCNT)

        # [RR] durmin floor (`p_uk_tim.c:931`).
        if phocur == UKP_RR:
            if durmin <= 13:
                durmin = 13

        # Rule 25: lengthen unvoiced cons after vowel (`p_uk_tim.c:938`).
        if (fealas & FVOICD) and ((feacur & FVOICD) == 0):
            deldur += deldur >> 1
            prcnt = mlsh1(N130PRCNT, prcnt)

        # Rule 26: shorten word-initial [HX] (`p_uk_tim.c:949`).
        if (phocur == UKP_HX) and (struccur & FWINITC):
            prcnt = mlsh1(N60PRCNT, prcnt)

        # Absolute stop-`durmin` floors (`p_uk_tim.c:960-994`).
        fc = phone_feature(phocur)
        if (fc & FOBST) and (fc & FSTOP) and (fc & FPLOSV) and phone(nphon + 1) != UKP_DZ:
            if (struccur & FBOUNDARY) >= FWBNEXT:
                prcnt = mlsh1(N160PRCNT, prcnt)
                deldur += 6
            fn = phone_feature(phone(nphon + 1))
            if fn & FVOICD:
                if durmin <= 6:
                    durmin = 6
            else:
                if (fn & FCONSON) and (fn & FSTOP) and (fn & FOBST):
                    if durmin <= 6:
                        durmin = 6
                else:
                    if durmin <= 14:
                        durmin = 14

        durxx = s16((prcnt * (durinh - durmin)) >> 7)
        durxx = s16(durxx + durmin)
        if phocur == UKP_Q and sprate < 75:
            durxx = 1 + (80 - sprate)

        durxx = _finish_break3(durxx, deldur, sprat0, sprat2, sprat1)
        allodurs[nphon] = durxx if durxx > 0 else 1

        (stcnt, syldur, sonocnt) = _post_loop(
            allodurs, allophons, feats, phone_feature, nphon, nallotot,
            allodurs[nphon], feacur, struccur, feasyllabiccur, strucstresscur,
            timeref, sprat0, user_durs, cfg, stcnt, syldur, sonocnt)

    return allodurs


def _finish_break3(durxx: int, deldur: int, sprat0: int, sprat2: int, sprat1: int) -> int:
    """`break3` (`p_uk_tim.c:1010-1034`): speaking-rate scaling + additive `deldur`."""
    if (sprat0 != 180) and (durxx != 0):
        durxx = mlsh1(durxx, sprat2) + 1
        deldur = mlsh1(deldur, sprat1)
    durxx = s16(durxx + deldur)
    if durxx < 0:
        durxx = 1
    return durxx


def _post_loop(
    allodurs, allophons, feats, feat, nphon, nallotot, durxx, feacur, struccur,
    feasyllabiccur, strucstresscur, timeref, sprat0, user_durs, cfg,
    stcnt, syldur, sonocnt,
):
    """Per-phone bookkeeping + syllable time-alignment pass (`p_uk_tim.c:1037-1179`).

    `adjust` persists across the back-scan: the C halves it whenever a phone is
    already short (`allodurs[endcnt] <= 8`) and keeps that halved value for the
    remaining phones, and it mutates already-written `allodurs[endcnt]` in place.
    """
    if allophons[nphon] != GEN_SIL:
        syldur += durxx
    if (feat(allophons[nphon]) & FSON1) and allophons[nphon] != 0:
        sonocnt += 1

    if (struccur & FSTRESS) and feasyllabiccur:
        adjust = _sono_adjust(sonocnt, timeref, syldur)
        if sprat0 <= 150:
            adjust = 0
        adjust = s16(adjust) >> 2
        if nphon < 3:
            adjust = adjust >> 3
        if user_durs[nphon] != 0 or cfg.f0mode == SINGING:
            adjust = 0
        endcnt = nphon - 1
        while endcnt != stcnt and endcnt >= 0:
            ph = allophons[endcnt]
            if (feat(ph) & FSON1) and not (feat(ph) & FNASAL):
                if endcnt >= 2:
                    if allodurs[endcnt] <= 8:
                        adjust = adjust >> 1
                    allodurs[endcnt] = s16(allodurs[endcnt] + adjust)
                    if allodurs[endcnt] <= 6:
                        allodurs[endcnt] = 6
            endcnt -= 1
        stcnt = nphon
        syldur = 0
        sonocnt = 0
    return stcnt, syldur, sonocnt


def _sono_adjust(sonocnt: int, timeref: int, syldur: int) -> int:
    """`switch(sonocnt)` adjust (`p_uk_tim.c:1066-1108`)."""
    d = timeref - syldur
    if sonocnt == 1:
        return d
    if sonocnt == 2:
        return d >> 1
    if sonocnt == 3:
        return (d >> 3) * 3
    if sonocnt == 4:
        return d >> 2
    if sonocnt == 5:
        return d >> 3
    if sonocnt == 6:
        return d >> 4
    if sonocnt == 7:
        return d >> 5
    if sonocnt == 8:
        return d >> 6
    if sonocnt == 9:
        return d >> 7
    if sonocnt == 10:
        return d >> 8
    return d >> 7
