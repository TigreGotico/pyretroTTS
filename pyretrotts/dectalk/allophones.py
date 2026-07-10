"""DECtalk US-English allophone selection (`phsort`/`phalloph`, the `ph/` stage).

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/ph/ph_sort.c` `all_phsort` and `src/dapi/src/ph/ph_aloph1.c`
`phalloph`), for the build where `ENGLISH` and `ENGLISH_US` are defined and
`GERMAN`, `FRENCH`, `SPANISH`, `ENGLISH_UK`, `HLSYN`, `CHANGES_AFTER_V43`,
`NWSNOAA`, `SLOWTALK`, and `NEVER` are not, and `lang_curr == LANG_english`.
FONIX Corporation declares that source proprietary and confidential. This file
is NOT covered by this project's MIT licence. See NOTICE.

`phclause` (`ph_claus.c:200`) runs ``phsort -> phalloph -> us_phtiming ->
phinton`` before the per-frame loop. This module ports the first two:

- `phsort` (`ph_sort.c:428` `all_phsort`) orders the input symbol stream into a
  phoneme stream (`phonemes[]`) and a parallel sentence-structure stream
  (`sentstruc[]`): it drops the control symbols (word/phrase/clause boundaries,
  stress marks, sentence terminators) into structural feature bits and keeps the
  real phonemes, then locates syllable/stress structure and boundary types.
- `phalloph` (`ph_aloph1.c:444`) applies the phonological allophone-selection
  rules: it copies each phoneme to `allophons[]` unless a context/stress/boundary
  rule substitutes a different allophone (postvocalic `/r l/`, flapping,
  glottalization, `/dh/` assimilation, `the/for` unreduction, ...), and it writes
  `allofeats[]` -- the structural bits plus the hat-pattern intonation marks
  (`FHAT_BEGINS`/`FHAT_ENDS`) the downstream stages read.

`allophons[]`/`allofeats[]`/`nallotot` are exactly the stream `timing.us_phtiming`
consumes. All values are C `short`; the US path uses no fixed-point arithmetic.
"""
from __future__ import annotations

from .settar import PFUSA, PSFONT, _phone_feature

GEN_SIL = 0x1E00


def _usp(offset: int) -> int:
    """`USP_x = (PFUSA << PSFONT) | US_x` (`p_all_ph.h`)."""
    return (PFUSA << PSFONT) | offset


# US phone-index offsets (`l_all_ph.h:60-116`); full code is `_usp(offset)`.
US_IY, US_IH, US_EY, US_EH, US_AE, US_AA = 1, 2, 3, 4, 5, 6
US_AH, US_AO, US_OW = 9, 10, 11
US_UH, US_UW, US_RR, US_YU, US_AX, US_IX = 13, 14, 15, 16, 17, 18
US_IR, US_ER, US_AR, US_OR, US_UR = 19, 20, 21, 22, 23
US_Y, US_R, US_LL, US_HX, US_RX, US_LX = 25, 26, 27, 28, 29, 30
US_M, US_N, US_NX, US_EL, US_DZ, US_EN = 31, 32, 33, 34, 35, 36
US_F, US_DH, US_T, US_D, US_DX, US_TX = 37, 40, 47, 48, 51, 52
US_CH, US_JH, US_DF = 54, 55, 56

USP_IY, USP_IH, USP_EY, USP_EH, USP_AE, USP_AA = map(
    _usp, (US_IY, US_IH, US_EY, US_EH, US_AE, US_AA))
USP_AH, USP_AO, USP_OW = map(_usp, (US_AH, US_AO, US_OW))
USP_UH, USP_UW, USP_RR, USP_YU, USP_AX, USP_IX = map(
    _usp, (US_UH, US_UW, US_RR, US_YU, US_AX, US_IX))
USP_IR, USP_ER, USP_AR, USP_OR, USP_UR = map(
    _usp, (US_IR, US_ER, US_AR, US_OR, US_UR))
USP_YX, USP_R, USP_LL, USP_HX, USP_RX, USP_LX = map(
    _usp, (US_Y, US_R, US_LL, US_HX, US_RX, US_LX))
USP_M, USP_N, USP_NX, USP_EL, USP_DZ, USP_EN = map(
    _usp, (US_M, US_N, US_NX, US_EL, US_DZ, US_EN))
USP_F, USP_DH, USP_T, USP_D, USP_DX, USP_TX = map(
    _usp, (US_F, US_DH, US_T, US_D, US_DX, US_TX))
USP_CH, USP_JH, USP_DF = map(_usp, (US_CH, US_JH, US_DF))

# Feature bits in `phone_feature` (`ph_defs.h:284-296`).
FSYLL = 0o1
FVOWEL = 0o4
FSON1 = 0o10
FNASAL = 0o200
FSON2 = 0o2000

# Structure bits in `sentstruc`/`allofeats` (`ph_defs.h:187-257`).
FSTRESS = 0o3
FSTRESS_1 = 0o1
FSTRESS_2 = 0o2
FEMPHASIS = 0o3
FWINITC = 0o4
FMONOSYL = 0o0
FTYPESYL = 0o30
FBOUNDARY = 0o740
FMBNEXT = 0o100
FVPNEXT = 0o240
FCBNEXT = 0o340
FHAT_BEGINS = 0o1000
FHAT_ENDS = 0o2000
FBLOCK = 0o20000

# f0mode / hat-position enums (`ph_defs.h:240,710-712`).
AT_BOTTOM_OF_HAT = 1
AT_TOP_OF_HAT = 2
NORMAL = 1
HAT_LOCATIONS_SPECIFIED = 2
HAT_F0_SIZES_SPECIFIED = 3

US_TOT_ALLOPHONES = 57


def phalloph(
    phonemes: tuple[int, ...],
    sentstruc: tuple[int, ...],
    nphonetot: int,
    cite_it: int = 0,
    f0mode: int = NORMAL,
    mode_citation: int = 1,
) -> tuple[list[int], list[int], int]:
    """`phalloph` (`ph_aloph1.c:444`) for the US path.

    Returns ``(allophons, allofeats, nallotot)`` -- the stream `us_phtiming`
    consumes. `cite_it` mirrors ``(modeflag & MODE_CITATION) && docitation``
    (0 for connected speech, since a phrase of six or more phones clears
    `docitation`); `mode_citation` is the raw ``modeflag & MODE_CITATION`` bit
    (set in the default mode), which the "to"-flap rule gates on independently of
    `docitation`. `f0mode` is `NORMAL` unless the input carried explicit hat
    commands.
    """
    phon = list(phonemes)
    sstr = list(sentstruc)

    def ph(i: int) -> int:
        return phon[i] if 0 <= i < nphonetot else GEN_SIL

    def sst(i: int) -> int:
        return sstr[i] if 0 <= i < nphonetot else 0

    def remaining_stresses_til(msym: int, b_type: int) -> int:
        count = 0
        for m in range(msym, nphonetot):
            if (m != msym and (sst(m) & FSTRESS_1)
                    and (_phone_feature(ph(m)) & FSYLL)):
                count += 1
            if (sst(m) & FBOUNDARY) >= b_type or ph(m) == GEN_SIL:
                return count
        return count

    def promote_last_2(msym: int) -> int:
        done_it = 0
        for m in range(msym, nphonetot):
            if (m != msym and (sst(m) & FSTRESS) == FSTRESS_2
                    and (_phone_feature(ph(m)) & FSYLL)):
                done_it = m
            if (sst(m) & FBOUNDARY) >= FCBNEXT or ph(m) == GEN_SIL:
                if done_it != 0:
                    sstr[done_it] &= ~FSTRESS_2
                    sstr[done_it] |= FSTRESS_1
                    return 1
        return 0

    allophons: list[int] = []
    allofeats: list[int] = []
    nallotot = 0
    delete_short = False
    hatposition = AT_BOTTOM_OF_HAT
    emphasislock = False
    stresses_in_phrase = 0
    last_outph = GEN_SIL

    for n in range(nphonetot):
        curr_inph = phon[n]
        curr_instruc = sstr[n]
        next_inph = phon[n + 1] if n < nphonetot - 1 else GEN_SIL
        curr_outph = curr_inph
        curr_outstruc = curr_instruc
        if n > 0:
            last_outph = allophons[nallotot - 1]

        if not (curr_instruc & FBLOCK):
            # Rule 1a: "the" -> /dh iy/ before a syllabic.
            if ((_phone_feature(ph(n + 1)) & FSYLL) and curr_inph == USP_AX
                    and (curr_instruc & FBOUNDARY) and ph(n - 1) == USP_DH
                    and (sst(n - 1) & FWINITC)):
                curr_outph = USP_IY
            # Rule 1c: clause-final long "a" -> ey (citation).
            if (curr_inph == USP_AX and next_inph == GEN_SIL
                    and n == 1 and cite_it):
                curr_outph = USP_EY
            # Rule 1b: unreduce "for" before a vowel or silence.
            if (curr_inph == USP_F and next_inph == USP_RR
                    and (((not (sst(n + 1) & FSTRESS))
                          and (sst(n + 1) & FTYPESYL) == FMONOSYL) or cite_it)):
                if (_phone_feature(ph(n + 2)) & FSYLL) or ph(n + 2) == GEN_SIL:
                    phon[n + 1] = USP_OR
                    next_inph = USP_OR
            # Rule 1c: clause-initial "and" -> [ae].
            if (curr_inph == GEN_SIL and ph(n + 1) == USP_AE
                    and ph(n + 2) == USP_N and ph(n + 3) == USP_D
                    and (((not (sst(n + 1) & FSTRESS))
                          and (not (sst(n + 3) & FSTRESS))) or cite_it)):
                phon[n + 1] = USP_AE
                next_inph = USP_AE
            # Rule 1c': citation "at" -> [ae].
            if (curr_inph == GEN_SIL and ph(n + 1) == USP_EH
                    and ph(n + 2) == USP_T and cite_it):
                phon[n + 1] = USP_AE
                next_inph = USP_AE

            # Rule 2: postvocalic allophones of /R/ and /LL/.
            if (not (curr_instruc & (FSTRESS | FWINITC))
                    and (_phone_feature(ph(n - 1)) & FVOWEL)):
                if curr_inph == USP_LL:
                    curr_outph = USP_LX
                if curr_inph == USP_R:
                    curr_outph = USP_RX
                    symlas = ph(n - 1)
                    combos = {
                        USP_AX: USP_RR,
                        USP_IY: USP_IR, USP_IH: USP_IR,
                        USP_EY: USP_ER, USP_EH: USP_ER, USP_AE: USP_ER,
                        USP_AA: USP_AR, USP_AH: USP_AR,
                        USP_OW: USP_OR, USP_AO: USP_OR,
                        USP_UW: USP_UR, USP_UH: USP_UR,
                    }
                    if symlas in combos:
                        allophons[nallotot - 1] = combos[symlas]
                        delete_short = True

            # Rule 3 + flapping (a goto-endrul3 chain in the C).
            endrul3 = False
            # 3a: palatalize /t d/ before unstressed /y/.
            if ((next_inph == USP_YU or next_inph == USP_YX)
                    and not (sst(n + 1) & FSTRESS)):
                if curr_inph == USP_T:
                    curr_outph = USP_CH
                    endrul3 = True
                elif curr_inph == USP_D:
                    curr_outph = USP_JH
                    endrul3 = True
            # 3b: glottalize/dentalize word-final /t/; "to" unreduction.
            if not endrul3 and curr_inph == USP_T:
                if (next_inph == USP_LL or next_inph == USP_DH
                        or (((curr_instruc & FBOUNDARY) >= FMBNEXT)
                            and ((_phone_feature(next_inph) & FSON2)
                                 or next_inph == USP_HX))
                        or next_inph == USP_EN):
                    curr_outph = USP_D
                    if _phone_feature(last_outph) & FSON1:
                        curr_outph = USP_TX
                    endrul3 = True
                elif (next_inph == USP_UH
                        and ((not (curr_instruc & FSTRESS)) or cite_it)):
                    if (_phone_feature(ph(n + 2)) & FSYLL) or ph(n + 2) == GEN_SIL:
                        phon[n + 1] = USP_UW
                    elif (not mode_citation
                            and (_phone_feature(last_outph) & FSYLL)
                            and not (_phone_feature(last_outph) & FNASAL)):
                        curr_outph = USP_DF
                        endrul3 = True
            # Flapping rule for non-stressed /t d/.
            if (not endrul3 and (curr_inph == USP_D or curr_inph == USP_T)
                    and not (curr_instruc & FSTRESS)):
                if ((_phone_feature(last_outph) & FSON1)
                        and last_outph != USP_M and last_outph != USP_NX
                        and last_outph != USP_N
                        and (_phone_feature(next_inph) & FSYLL)):
                    flap = None
                    if (curr_instruc & FBOUNDARY) >= FMBNEXT:
                        flap = USP_DF if curr_inph == USP_T else USP_DX
                    elif curr_instruc & FWINITC:
                        if next_inph == USP_AX or next_inph == USP_IX:
                            flap = USP_DF if curr_inph == USP_T else USP_DX
                    elif (((allofeats[nallotot - 1] & FSTRESS)
                           and next_inph == USP_OW)
                          or next_inph == USP_AX or next_inph == USP_RR
                          or next_inph == USP_IY or next_inph == USP_IX
                          or next_inph == USP_EL):
                        flap = USP_DF if curr_inph == USP_T else USP_DX
                    if flap is not None:
                        curr_outph = flap
            # Rule 4: unstressed [dh] assimilation.
            if not endrul3 and curr_inph == USP_DH and not (curr_instruc & FSTRESS):
                if last_outph in (USP_T, USP_TX, USP_D):
                    curr_outph = USP_DZ
                if last_outph == USP_N:
                    curr_outph = USP_N

            # endrul3: hat-pattern intonation rules.
            if curr_inph == GEN_SIL:
                emphasislock = False
            if (f0mode == NORMAL and (_phone_feature(curr_inph) & FSYLL)
                    and (curr_instruc & FSTRESS) and not emphasislock):
                if (hatposition != AT_TOP_OF_HAT
                        and ((curr_instruc & FSTRESS_1)
                             or remaining_stresses_til(n, FCBNEXT) > 0)):
                    curr_outstruc |= FHAT_BEGINS
                    hatposition = AT_TOP_OF_HAT
                if curr_instruc & FSTRESS_1:
                    stresses_in_phrase += 1
                if hatposition == AT_TOP_OF_HAT and (curr_instruc & FSTRESS_1):
                    if (curr_instruc & FEMPHASIS) == FEMPHASIS:
                        emphasislock = True
                    if emphasislock:
                        curr_outstruc |= FHAT_ENDS
                        hatposition = AT_BOTTOM_OF_HAT
                        stresses_in_phrase = 0
                    if remaining_stresses_til(n, FCBNEXT) == 0:
                        if ((curr_instruc & FBOUNDARY) == FVPNEXT
                                and promote_last_2(n)):
                            pass
                        else:
                            curr_outstruc |= FHAT_ENDS
                            hatposition = AT_BOTTOM_OF_HAT
                            stresses_in_phrase = 0
                    if (stresses_in_phrase > 1
                            and remaining_stresses_til(n, FVPNEXT) == 0
                            and remaining_stresses_til(n, FCBNEXT) > 1):
                        curr_outstruc |= FHAT_ENDS
                        hatposition = AT_BOTTOM_OF_HAT
                        stresses_in_phrase = 0

        # skiprules: emit or delete.
        if delete_short:
            delete_short = False
        elif nallotot <= n + 8:
            allophons.append(curr_outph)
            allofeats.append(curr_outstruc)
            nallotot += 1

    if f0mode == HAT_LOCATIONS_SPECIFIED:
        f0mode = NORMAL
    return allophons, allofeats, nallotot


# Control symbol codes (`l_com_ph.h:45-67`), font 0.
BLOCK_RULES, S3, S2, S1, SEMPH = 100, 101, 102, 103, 104
HAT_RISE, HAT_FALL, HAT_RF = 105, 106, 107
SBOUND, MBOUND, HYPHEN, WBOUND = 108, 109, 110, 111
PPSTART, VPSTART, RELSTART = 112, 113, 114
COMMA, PERIOD, QUEST, EXCLAIM = 115, 116, 117, 118
NEW_PARAGRAPH, SPECIALWORD, LINKRWORD, DOUBLCONS = 119, 120, 121, 122
MAX_PHONES = 99
NPHON_MAX = 300

# Additional US phone codes referenced by phsort.
US_S, US_W = 41, 24
USP_S = _usp(US_S)
USP_W = _usp(US_W)
USP_P, USP_B, USP_TH, USP_K, USP_G, USP_SH = map(_usp, (45, 46, 39, 49, 50, 43))

# Structural feature bits (`ph_defs.h`).
FMEDIALSYL = 0o20
FFINALSYL = 0o30
FFIRSTSYL = 0o10
FWBNEXT = 0o140
FSENTENDS = 0o400
FHAT_ROOF = 0o100000
FDOUBLECONS = 0x40000
PRESSBOUND = 0o4000000
FMAXIMUM = 0o10000000000

# f0mode / clausetype enums (`ph_defs.h`).
DECLARATIVE, COMMACLAUSE, EXCLAIMCLAUSE, QUESTION = 0, 1, 2, 3
SINGING, PHONE_TARGETS_SPECIFIED = 4, 5

# `bounftab[]` (`p_us_rom_dectalk_1996m_43f.c:1275`), indexed by `symbol - SBOUND`.
BOUNFTAB: tuple[int, ...] = (
    0o40,   # SBOUND   FSYBNEXT
    0o100,  # MBOUND   FMBNEXT
    0o100,  # HYPHEN   FMBNEXT
    0o140,  # WBOUND   FWBNEXT
    0o200,  # PPSTART  FPPNEXT
    0o240,  # VPSTART  FVPNEXT
    0o300,  # RELSTART FRELNEXT
    0o340,  # COMMA    FCBNEXT
    0o400,  # PERIOD   FPERNEXT
    0o440,  # QUEST    FQUENEXT
    0o500,  # EXCLAIM  FEXCLNEXT
)

# CLUSTER classes (`p_us_sr1.c:50-52`).
NOCLUSTER, CLUSTER, CLUSTER_TRYS = 0, 1, 2


def us_phcluster(f: int, s: int) -> int:
    """`us_phcluster` (`p_us_sr1.c:178`): consonant-cluster class of two phones."""
    if f == USP_P:
        return CLUSTER_TRYS if s in (USP_LL, USP_R) else NOCLUSTER
    if f == USP_B:
        return CLUSTER if s in (USP_LL, USP_R) else NOCLUSTER
    if f == USP_F:
        if s == USP_R:
            return CLUSTER_TRYS
        return CLUSTER if s == USP_LL else NOCLUSTER
    if f == USP_T:
        if s == USP_R:
            return CLUSTER_TRYS
        return CLUSTER if s == USP_W else NOCLUSTER
    if f in (USP_D, USP_TH):
        return CLUSTER if s in (USP_R, USP_W) else NOCLUSTER
    if f == USP_K:
        return CLUSTER_TRYS if s in (USP_R, USP_LL, USP_W) else NOCLUSTER
    if f == USP_G:
        return CLUSTER if s in (USP_R, USP_LL, USP_W) else NOCLUSTER
    if f == USP_S:
        return CLUSTER if s in (
            USP_W, USP_LL, USP_P, USP_T, USP_K, USP_M, USP_N, USP_F) else NOCLUSTER
    if f == USP_SH:
        return CLUSTER if s in (
            USP_W, USP_LL, USP_P, USP_T, USP_R, USP_M, USP_N) else NOCLUSTER
    return NOCLUSTER


def _pf(code: int) -> int:
    """`phone_feature` guarded for the out-of-range boundary-symbol probes the C
    reads past `us_featb` (harmless: those call sites return regardless)."""
    i = code & 0xFF
    return _phone_feature(code) if i < US_TOT_ALLOPHONES else 0


def _is_wboundary(symb: int) -> int:
    return 1 if WBOUND <= symb <= EXCLAIM else 0


class _Sort:
    """Mutable `phsort` state over the growing/shrinking symbol arrays."""

    def __init__(self, symbols: tuple[int, ...], user_durs: tuple[int, ...],
                 sprate: int) -> None:
        self.symbols = list(symbols)
        self.user_durs = list(user_durs)
        self.user_f0 = [0] * len(symbols)
        self.sprate = sprate
        self.phonemes: list[int] = []
        self.sentstruc: list[int] = [0] * NPHON_MAX
        self.nphonetot = 0
        self.did_del = 0
        self.f0mode = NORMAL
        self.number_words = 0
        self.cbsymbol = 0
        self.newparagsw = 0
        self.clausetype = 0
        self.clausenumber = 0
        self.dcommacnt = 0
        self.hat_seen = 0
        self.wordcount = 1

    @property
    def nsymbtot(self) -> int:
        return len(self.symbols)

    def insertphone(self, loc: int, fone: int) -> None:
        if self.nsymbtot >= NPHON_MAX:
            return
        self.symbols.insert(loc, fone)
        self.user_durs.insert(loc, 0)
        self.user_f0.insert(loc, 0)

    def delete_symbol(self, msym: int) -> None:
        self.did_del = 1
        del self.symbols[msym]
        del self.user_durs[msym]
        del self.user_f0[msym]

    def make_phone(self, phoname: int, n: int, curr_dur: int, curr_f0: int) -> None:
        if self.nphonetot > n:
            return
        self.phonemes.append(phoname)
        if self.nphonetot < NPHON_MAX:
            self.nphonetot += 1

    def add_feature(self, feaname: int, location: int) -> None:
        if location < 0 or location >= NPHON_MAX:
            return
        if feaname <= 0 or feaname > FMAXIMUM:
            return
        self.sentstruc[location] |= feaname

    def _currphone(self) -> int:
        return self.nphonetot - 1

    def is_wboundary(self, symb: int) -> int:
        return _is_wboundary(symb)

    def raise_last_stress(self, msym: int) -> None:
        for m in range(msym - 1, 0, -1):
            if (self.symbols[m] & 0x00FF) == S1:
                self.symbols[m] = SEMPH
                return

    def zap_weaker_bound(self, msym1: int, msym2: int) -> None:
        # `zap_weaker_bound` (`ph_sort.c:1920`) collapses two adjacent boundary
        # symbols to one. The compiled 43F oracle keeps the lower-coded (weaker)
        # boundary here -- e.g. a word boundary followed by a preposition-phrase
        # start resolves to the word boundary (`FWBNEXT`), verified field-for-field
        # against the oracle `sentstruc`.
        if self.symbols[msym1] < self.symbols[msym2]:
            if self.symbols[msym2] != HYPHEN:
                self.delete_symbol(msym2)
            return
        if self.symbols[msym1] != HYPHEN:
            self.delete_symbol(msym1)

    def init_med_final(self, msym: int) -> None:
        sylltype = FMONOSYL
        for m in range(self._currphone() - 1, 0, -1):
            if (self.sentstruc[m] & FBOUNDARY) >= FWBNEXT:
                break
            if _pf(self.phonemes[m]) & FSYLL:
                sylltype = FFINALSYL
        for m in range(msym + 1, self.nsymbtot):
            if WBOUND <= self.symbols[m] <= EXCLAIM:
                if sylltype != FMONOSYL:
                    self.add_feature(sylltype, self._currphone())
                return
            if _pf(self.symbols[m]) & FSYLL:
                if sylltype == FFINALSYL:
                    sylltype = FMEDIALSYL
                if sylltype == FMONOSYL:
                    sylltype = FFIRSTSYL

    def get_next_bound_type(self, msym: int) -> None:
        for m in range(msym + 1, self.nsymbtot):
            sy = self.symbols[m] & 0x00FF
            if SBOUND <= sy <= EXCLAIM:
                self.add_feature(BOUNFTAB[self.symbols[m] - SBOUND],
                                 self._currphone())
                return
            if _pf(self.symbols[m]) & FSYLL:
                return

    def get_stress_of_conson(self, msym: int) -> None:
        for m in range(msym + 1, self.nsymbtot):
            sy = self.symbols[m] & 0x00FF
            if sy in (S1, S2, SEMPH):
                mcl = m - msym
                if mcl > 3:
                    return
                if mcl != 1:
                    cl = us_phcluster(self.symbols[m - 2], self.symbols[m - 1])
                    if cl == NOCLUSTER:
                        return
                    if mcl == 3 and (cl != CLUSTER_TRYS
                                     or self.symbols[m - 3] != USP_S):
                        return
                if sy == S1:
                    self.add_feature(FSTRESS_1, self._currphone())
                if sy == S2:
                    self.add_feature(FSTRESS_2, self._currphone())
                if sy == SEMPH:
                    self.add_feature(FEMPHASIS, self._currphone())
                return
            if _pf(sy) & FSYLL:
                return
            if SBOUND <= sy <= EXCLAIM:
                return

    def find_syll_to_stress(self, locend: int, nstartphrase: int) -> int:
        for m in range(locend - 1, nstartphrase - 1, -1):
            if self.symbols[m] == S2:
                self.symbols[m] = S1
                return locend
        locbeg = 0
        for m in range(locend - 1, nstartphrase - 1, -1):
            if self.symbols[m] >= WBOUND:
                locbeg = m
                break
        for m in range(locbeg, locend):
            if _pf(self.symbols[m]) & FSYLL:
                self.insertphone(m, S1)
                return locend + 1
        return locend

    def move_stdangle(self, msym: int) -> None:
        stdangle = self.symbols[msym] & 0x00FF
        durdangle = self.user_durs[msym]
        f0dangle = self.user_durs[msym]
        if stdangle == SEMPH:
            for m in range(msym + 1, self.nsymbtot):
                if self.symbols[m] == S1:
                    self.symbols[m] = SEMPH
                    self.user_durs[m] = durdangle
                    self.user_f0[m] = f0dangle
                    self.delete_symbol(msym)
                    return
                if self.is_wboundary(self.symbols[m]):
                    break
            for m in range(msym + 1, self.nsymbtot):
                if self.symbols[m] == S2:
                    self.symbols[m] = SEMPH
                    self.user_durs[m] = durdangle
                    self.user_f0[m] = f0dangle
                    self.delete_symbol(msym)
                    return
                if self.is_wboundary(self.symbols[m]):
                    break
        if stdangle == S1:
            for m in range(msym + 1, self.nsymbtot):
                if self.symbols[m] == S2:
                    self.symbols[m] = S1
                    self.user_durs[m] = durdangle
                    self.user_f0[m] = f0dangle
                    self.delete_symbol(msym)
                    return
                if self.is_wboundary(self.symbols[m]):
                    break
        for m in range(msym + 1, self.nsymbtot):
            if self.is_wboundary(self.symbols[m]):
                self.delete_symbol(m - 1)
                return
            sy = self.symbols[m] & 0x00FF
            if S2 <= sy <= SEMPH:
                if sy < stdangle:
                    self.symbols[m] = stdangle
                    self.user_durs[m] = durdangle
                    self.user_f0[m] = f0dangle
                self.delete_symbol(m - 1)
                return
            if _pf(self.symbols[m]) & FSYLL:
                self.symbols[m - 1] = stdangle
                self.user_durs[m - 1] = durdangle
                self.user_f0[m - 1] = f0dangle
                return
            self.symbols[m - 1] = self.symbols[m]
            self.user_durs[m - 1] = self.user_durs[m]
            self.user_f0[m - 1] = self.user_f0[m]

    def _interp_user_f0(self, curr_dur: int, curr_f0: int, curr_in_sym: int,
                        mf0: int) -> tuple[int, int, int]:
        if (curr_in_sym in (S1, SEMPH, HAT_RISE, HAT_FALL)
                and self.f0mode != PHONE_TARGETS_SPECIFIED
                and self.f0mode != SINGING):
            if curr_f0 != 0 or self.f0mode == HAT_F0_SIZES_SPECIFIED:
                if curr_f0 < 0:
                    curr_f0 = -curr_f0
                if curr_f0 > 199:
                    curr_f0 = 199
                if curr_in_sym == HAT_RISE:
                    curr_f0 += 200
                elif curr_in_sym == HAT_FALL:
                    curr_f0 += 400
                else:
                    curr_f0 += 1000
                self.user_f0[mf0] = curr_f0
                curr_dur = 0
                curr_f0 = 0
                self.f0mode = HAT_F0_SIZES_SPECIFIED
            mf0 += 1
        elif curr_f0 != 0:
            if self.f0mode != HAT_F0_SIZES_SPECIFIED:
                if (self.f0mode != PHONE_TARGETS_SPECIFIED
                        and (curr_f0 % 1000) <= 37):
                    self.f0mode = SINGING
                elif self.f0mode != SINGING:
                    self.f0mode = PHONE_TARGETS_SPECIFIED
                else:
                    curr_dur = 0
                    curr_f0 = 0
            else:
                curr_dur = 0
                curr_f0 = 0
        return curr_dur, curr_f0, mf0

    def run(self) -> tuple[list[int], list[int], int]:
        # Ensure a leading word boundary.
        if self.nsymbtot > 2 and self.symbols[1] != WBOUND:
            self.insertphone(1, WBOUND)

        # Main loop 1: clean up boundaries and stress marks.
        compound_destress = 0
        nstresses = 0
        nstartphrase = 0
        n = 0
        while n < self.nsymbtot:
            if self.did_del:
                n -= 1
                self.did_del = 0
            s = self.symbols
            if s[n] == HYPHEN:
                compound_destress = 1
            if s[n] == S1 and compound_destress:
                s[n] = S2
                compound_destress = 0
            if s[n] == SPECIALWORD:
                self.delete_symbol(n)
            if (s[n] == NEW_PARAGRAPH
                    and n + 1 < self.nsymbtot and s[n + 1] == NEW_PARAGRAPH):
                self.delete_symbol(n)
            if (s[n] == WBOUND
                    and n + 1 < self.nsymbtot and s[n + 1] == PERIOD):
                self.delete_symbol(n)
            sv = s[n] & 0x00FF
            if HAT_RISE <= sv <= HAT_RF and self.f0mode == NORMAL:
                self.f0mode = HAT_LOCATIONS_SPECIFIED
            if s[n] == PPSTART:
                m = n + 1
                while m < self.nsymbtot:
                    if _is_wboundary(s[m] & 0x00FF):
                        mv = s[m] & 0x00FF
                        if (mv >= COMMA
                                or (mv == PPSTART
                                    and (m + 1 >= self.nsymbtot
                                         or s[m + 1] != USP_W))):
                            s[n] = WBOUND
                            if mv == PPSTART:
                                s[m] = VPSTART
                            if (n + 2 < self.nsymbtot
                                    and s[n + 1] == USP_F and s[n + 2] == USP_RR):
                                s[n + 2] = USP_OR
                            if (m - 2 >= 0
                                    and s[m - 2] == USP_T and s[m - 1] == USP_UH):
                                s[n + 2] = USP_UW
                            if s[n + 1] == S2:
                                s[n + 1] = S1
                            else:
                                self.insertphone(n + 1, S1)
                                self.move_stdangle(n + 1)
                        break
                    m += 1
            sv = s[n] & 0x00FF
            if S2 <= sv <= SEMPH:
                if sv != S2:
                    nstresses += 1
                m = n + 1
                zapped = False
                while (m < self.nsymbtot and (s[m] & 0x00FF) >= MAX_PHONES):
                    mv = s[m] & 0x00FF
                    if mv > WBOUND and mv < NEW_PARAGRAPH and mv != HYPHEN:
                        nstresses -= 1
                        self.delete_symbol(n)
                        zapped = True
                        break
                    m += 1
                if not zapped:
                    mm = s[m] if m < self.nsymbtot else GEN_SIL
                    if not (_pf(mm) & FSYLL):
                        self.move_stdangle(n)
            sv = s[n] & 0x00FF
            if SBOUND <= sv <= EXCLAIM:
                m = n + 1
                if m < self.nsymbtot:
                    mv = s[m] & 0x00FF
                    if SBOUND <= mv <= EXCLAIM:
                        self.zap_weaker_bound(n, m)
            sv = s[n] & 0x00FF
            if self.sprate <= 120:
                if sv in (VPSTART, PPSTART):
                    s[n] = COMMA
            if self.sprate <= 140:
                if s[n] == PPSTART:
                    s[n] = VPSTART
            sv = s[n] & 0x00FF
            if COMMA <= sv <= EXCLAIM:
                if n > 0 and nstresses == 0:
                    n = self.find_syll_to_stress(n, nstartphrase)
                    nstresses = 1
            sv = s[n] & 0x00FF
            if RELSTART <= sv <= EXCLAIM:
                nstresses = 0
                nstartphrase = n
            if (s[n] & 0x00FF) == EXCLAIM:
                self.raise_last_stress(n)
            if (s[n] & 0x00FF) == QUEST:
                self.cbsymbol = 1
            n += 1

        # Main loop 2: emit phonemes and structural feature bits.
        mf0 = 0
        self.nphonetot = 0
        word_init_sw = 0
        in_rhyme = 0
        self.newparagsw = 0
        compound_destress = 0
        self.wordcount = 1
        s = self.symbols
        n = 0
        while n < self.nsymbtot:
            curr_in_phone = s[n]
            curr_in_sym = s[n] & 0x00FF
            curr_dur = self.user_durs[n]
            self.user_durs[n] = 0
            curr_f0 = self.user_f0[n]
            self.user_f0[n] = 0
            curr_dur, curr_f0, mf0 = self._interp_user_f0(
                curr_dur, curr_f0, curr_in_sym, mf0)

            if curr_in_sym < MAX_PHONES:
                self.make_phone(curr_in_phone, n, curr_dur, curr_f0)
                if _pf(curr_in_phone) & FSYLL:
                    in_rhyme = 1
                    word_init_sw = 0
                    self.init_med_final(n)
                else:
                    self.get_stress_of_conson(n)
                if word_init_sw == 1:
                    self.add_feature(FWINITC, self._currphone())
                if in_rhyme == 1:
                    self.get_next_bound_type(n)
            else:
                c = curr_in_sym
                if c == DOUBLCONS:
                    self.add_feature(FDOUBLECONS, self.nphonetot)
                elif c == S1:
                    self.add_feature(FSTRESS_1, self.nphonetot)
                elif c == S2:
                    self.add_feature(FSTRESS_2, self.nphonetot)
                elif c == S3:
                    pass
                elif c == SEMPH:
                    self.add_feature(FEMPHASIS, self.nphonetot)
                elif c == HYPHEN:
                    pass
                elif c == WBOUND:
                    self.number_words += 1
                    word_init_sw = 1
                elif c == PPSTART:
                    word_init_sw = 1
                elif c == VPSTART:
                    word_init_sw = 1
                elif c == RELSTART:
                    word_init_sw = 1
                    if not (n + 1 < self.nsymbtot and s[n + 1] == HYPHEN):
                        word_init_sw = 1
                        compound_destress = 0
                elif c == COMMA:
                    self.clausetype = COMMACLAUSE
                    self.clausenumber += 1
                    self.dcommacnt += 1
                    if self.dcommacnt > 1 or self.number_words > 4:
                        self.clausetype = DECLARATIVE
                    self.make_phone(GEN_SIL, n, curr_dur, curr_f0)
                    word_init_sw = 1
                    compound_destress = 0
                elif c == PERIOD:
                    self.clausetype = DECLARATIVE
                    self.add_feature(FSENTENDS, self.nphonetot)
                    self.clausenumber = 0
                    self.add_feature(FSENTENDS, self.nphonetot)
                    self.make_phone(GEN_SIL, n, curr_dur, curr_f0)
                    word_init_sw = 1
                    compound_destress = 0
                elif c == EXCLAIM:
                    self.clausetype = EXCLAIMCLAUSE
                    self.clausenumber = 0
                    self.make_phone(GEN_SIL, n, curr_dur, curr_f0)
                    word_init_sw = 1
                    compound_destress = 0
                elif c == QUEST:
                    self.clausetype = QUESTION
                    self.clausenumber = 0
                    self.make_phone(GEN_SIL, n, curr_dur, curr_f0)
                    word_init_sw = 1
                    compound_destress = 0
                elif c == HAT_RISE:
                    self.hat_seen += 1
                    self.add_feature(FHAT_BEGINS, self.nphonetot)
                elif c == HAT_FALL:
                    self.hat_seen += 1
                    self.add_feature(FHAT_ENDS, self.nphonetot)
                elif c == HAT_RF:
                    self.hat_seen += 1
                    self.add_feature(FHAT_ROOF, self.nphonetot)
                elif c == BLOCK_RULES:
                    self.add_feature(FBLOCK, self.nphonetot)
                elif c == NEW_PARAGRAPH:
                    self.add_feature(PRESSBOUND, self.nphonetot)
                    self.add_feature(PRESSBOUND, self.nphonetot + 1)
                    self.newparagsw = 1
            n += 1

        return self.phonemes, self.sentstruc[:self.nphonetot], self.nphonetot


def phsort(
    symbols: tuple[int, ...],
    user_durs: tuple[int, ...] | None = None,
    sprate: int = 180,
) -> tuple[list[int], list[int], int]:
    """`all_phsort` (`ph_sort.c:428`) for the US path.

    Returns ``(phonemes, sentstruc, nphonetot)`` -- the stream `phalloph`
    consumes. `sprate` is the resolved speaking rate (the default-mode value is
    180; only the <=140 branches diverge).
    """
    if user_durs is None:
        user_durs = (0,) * len(symbols)
    return _Sort(symbols, user_durs, sprate).run()
