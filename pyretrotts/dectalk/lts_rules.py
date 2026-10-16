"""DECtalk US letter-to-sound rule engine (`lts/ls_rule*.c`, `ls_adju*.c`,
`l_us_ad1.c`, `l_us_ru1.c`, ACNA `ENGLISH_US` build).

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/lts/`). FONIX Corporation declares that source proprietary and
confidential; the extracted rule tables (`lts_rules_data.py`) are FONIX data.
This file and any phonemes it produces are NOT covered by this project's MIT
licence. See NOTICE.

For an out-of-dictionary alphabetic word this reproduces the compiled US path:

    ls_rule_lts        graphemes -> rule match -> phoneme+stress PHONE chain
    ls_adju_allo1      plural/-ed allophony (adds vowels)
    ls_adju_sylables   syllable boundaries, drag stress to syllable start
    delete_geminate    geminate-pair deletion
    ls_adju_stress     suffix/prefix/best-default stress placement
    ls_adju_allo2      vowel reduction + final allophonic sweep
    ls_rule_lts_out    emit the phoneme+stress+boundary send stream

The output list is the sequence of raw `ph` codes the C hands to
`ls_util_send_phone` (US phoneme font indices plus prosody codes S1=103, S2=102,
SBOUND=108, MBOUND=109, HYPHEN=110): the pre-`ph/` boundary, before the
downstream reductions that the public LOG_PHONEMES output folds in.

Scoped out (dictionary miss / stub in this port): number and abbreviation
expansion, homograph part-of-speech selection, ACNA name-language identification
(`lsa_us.c`; ordinary words run the default language tag 0), and non-US
languages.
"""
from __future__ import annotations

from dataclasses import dataclass

from .lts_rules_data import FEATS, LSBTAB, LSFOLD, LSWTAB, PFEAT, PREFTAB

# --- Grapheme codes (ls_defs.h, ENGLISH) ---
GEOS = 0
GA = 1
GC = 3
GD = 4
GE = 5
GG = 7
GH = 8
GI = 9
GJ = 10
GO = 15
GQ = 17
GS = 19
GU = 21
GY = 25
GGU = 27
GQU = 28
GQUOTE = 29
GMBOUND = 30
NGRAPH = 31
GRANGE = 31
GDISJ = 32
GFEAT = 33
GWBOUND = 34

NGWORD = 128

# --- Grapheme feature bits (ls_defs.h) ---
FVOC = 0x0002
FCONS = 0x0004
FSIB = 0x0040
FGEM = 0x0200
FSYL = 0x8000

# --- Phoneme feature bits (ls_defs.h) ---
PCONS = 0x0001
PVOC = 0x0002
PVOICE = 0x0008
PSIB = 0x0010
POBS = 0x0020

# --- PHONE flags (ls_defs.h) ---
PFDASH = 0x01
PFSTAR = 0x02
PFHASH = 0x04
PFPLUS = 0x08
PFSYLAB = 0x10
PFRFUSE = 0x20
PFLEFTC = 0x40
PFBLOCK = 0x80
PFBOUND = PFDASH | PFSTAR | PFHASH
PFMORPH = PFDASH | PFSTAR | PFHASH | PFPLUS

# --- rpart / prosody codes (l_com_ph.h, ls_defs.h) ---
SIL = 0
S2 = 102
S1 = 103
SBOUND = 108
MBOUND = 109
HYPHEN = 110
COMMA = 115
PERIOD = 116

DASH = SBOUND
STAR = MBOUND
HASH = HYPHEN
PLUS = PERIOD
EQUAL = COMMA

TWOPH = 0x80
MSKPH = 0x7F

# Internal stress codes (PHO_SYM_TOT == 122 for US).
PHO_SYM_TOT = 122
SNONE = PHO_SYM_TOT + 0
SUN = PHO_SYM_TOT + 1
SSEC = PHO_SYM_TOT + 2
SPRI = PHO_SYM_TOT + 3
S1LEFT = PHO_SYM_TOT + 4
S2LEFT = PHO_SYM_TOT + 5

# --- US phoneme codes (l_all_ph.h) ---
US_IY = 1
US_EY = 3
US_EH = 4
US_AE = 5
US_AA = 6
US_AY = 7
US_AH = 9
US_UW = 14
US_RR = 15
US_AX = 17
US_IX = 18
US_W = 24
US_Y = 25
US_R = 26
US_LL = 27
US_M = 31
US_N = 32
US_NX = 33
US_EL = 34
US_F = 37
US_TH = 39
US_S = 41
US_Z = 42
US_SH = 43
US_P = 45
US_B = 46
US_T = 47
US_D = 48
US_K = 49
US_G = 50
US_CH = 54
US_JH = 55

# --- prefix-table flag bits (ls_defs.h) ---
PLENGTH = 0x0F
PCONT = 0x10
PRCON = 0x20
PRVOC = 0x40
P2SYL = 0x80

# --- env-match / cluster (l_us_ad1.c) ---
ILLEGAL = 0
OK = 1
TRYS = 2

FORW = 0
BACK = 1

NSYL = 10


def _wtab(n: int) -> int:
    return LSWTAB[n] & 0xFFFF


def _btabb(n: int) -> int:
    return LSBTAB[n] & 0xFF


def _btabw(n: int) -> int:
    return (LSBTAB[n + 1] << 8) | LSBTAB[n]


def _is_vowel(g: int) -> bool:
    return g in (GA, GE, GI, GO, GU, GY)


class _Graph:
    __slots__ = ("g_graph", "g_feats")

    def __init__(self) -> None:
        self.g_graph = 0
        self.g_feats = 0


class _Phone:
    __slots__ = ("fp", "bp", "flag", "stress", "sphone", "uphone")

    def __init__(self) -> None:
        self.fp = self
        self.bp = self
        self.flag = 0
        self.stress = SNONE
        self.sphone = SIL
        self.uphone = SIL


def _pfeat(sphone: int) -> int:
    if 0 <= sphone < len(PFEAT):
        return PFEAT[sphone]
    return 0


def _is_cons(pp: _Phone) -> bool:
    return (_pfeat(pp.sphone) & PCONS) != 0


def _is_voc(pp: _Phone) -> bool:
    return (_pfeat(pp.sphone) & PVOC) != 0


def _is_obs(pp: _Phone) -> bool:
    return (_pfeat(pp.sphone) & POBS) != 0


class _Lts:
    """Working state for one word (mirrors the C ``pLts_t`` fields used here)."""

    def __init__(self) -> None:
        self.graph = [_Graph() for _ in range(NGWORD)]
        self.head = _Phone()
        self.head.fp = self.head
        self.head.bp = self.head
        self.rpart = 0
        self.sylp: list[_Phone] = [self.head] * NSYL
        self.nsyl = 0
        self.rsyl = -1
        self.psyl = -1

    # ---- PHONE list helpers ----
    def add_phone(self, sph: int, uph: int) -> None:
        pp = _Phone()
        fp = self.head.fp
        self.head.fp = pp
        pp.fp = fp
        fp.bp = pp
        pp.bp = self.head
        pp.flag = 0
        pp.sphone = sph
        pp.uphone = uph
        pp.stress = SNONE

    def ins_phone(self, fpp: _Phone, sph: int, uph: int, stress: int) -> bool:
        ipp = _Phone()
        bpp = fpp.bp
        bpp.fp = ipp
        ipp.fp = fpp
        fpp.bp = ipp
        ipp.bp = bpp
        ipp.sphone = sph
        ipp.uphone = uph
        ipp.flag = fpp.flag
        fpp.flag = 0
        ipp.stress = stress
        fpp.stress = SNONE
        return True

    def del_phone(self, dpp: _Phone) -> None:
        bpp = dpp.bp
        fpp = dpp.fp
        bpp.fp = fpp
        fpp.bp = bpp

    def delgemphone(self, pp: _Phone, ph: int) -> None:
        bp = pp.bp
        pp.sphone = ph
        pp.flag |= bp.flag
        if bp.stress > pp.stress:
            pp.stress = bp.stress
        self.del_phone(bp)

    # ---- grapheme construction (ls_rule_add_graph) ----
    def add_graph(self, gp0: int, g: int, insert: int) -> bool:
        graph = self.graph
        gp = gp0  # local; C passes gp by value
        if (
            _is_vowel(g)
            and gp > 1
            and graph[gp - 1].g_graph == GU
            and (graph[gp - 2].g_graph == GG or graph[gp - 2].g_graph == GQ)
        ):
            gp -= 1
            if graph[gp - 1].g_graph == GG:
                graph[gp - 1].g_graph = GGU
            else:
                graph[gp - 1].g_graph = GQU
            value = False
        else:
            value = True

        if insert:
            ep1 = gp
            while graph[ep1].g_graph != GEOS:
                ep1 += 1
            while ep1 != gp:
                ep3 = ep1 + 1
                if ep3 <= NGWORD - 1:
                    graph[ep3].g_graph = graph[ep1].g_graph
                    graph[ep3].g_feats = graph[ep1].g_feats
                ep1 -= 1
            ep3 = ep1 + 1
            graph[ep3].g_graph = graph[ep1].g_graph
            graph[ep3].g_feats = graph[ep1].g_feats

        graph[gp].g_graph = g
        graph[gp].g_feats = FEATS[g] & 0xFFFF
        if g == GY:
            if gp == 0:
                graph[gp].g_feats |= FCONS
            else:
                graph[gp].g_feats |= FVOC
                graph[gp].g_feats |= FSYL
        if gp != 0:
            g1 = graph[gp - 1].g_graph
            if (g1 == GS or g1 == GC) and g == GH:
                graph[gp].g_feats |= FSIB
            elif g1 == GD and (g == GG or g == GJ):
                graph[gp].g_feats |= FSIB
            if (graph[gp].g_feats & FCONS) != 0 and g1 == g:
                graph[gp].g_feats |= FGEM
            if (graph[gp - 1].g_feats & FSYL) != 0:
                graph[gp].g_feats |= FSYL
        return value

    # ---- environment match (ls_rule_env_match) ----
    def env_match(self, ep1: int, gp: int, d: int) -> int | None:
        graph = self.graph
        npat = _btabb(ep1)
        ep1 += 1
        ep2 = ep1 + npat
        while ep1 != ep2:
            type_ = _btabb(ep1)
            ep1 += 1
            if type_ == GRANGE:
                llim = _btabb(ep1)
                ep1 += 1
                hlim = _btabb(ep1)
                ep1 += 1
                while llim:
                    llim -= 1
                    gp1 = self.env_match(ep1, gp, d)
                    if gp1 is None:
                        return None
                    gp = gp1
                while hlim:
                    hlim -= 1
                    gp1 = self.env_match(ep1, gp, d)
                    if gp1 is None:
                        break
                    gp = gp1
                npat = _btabb(ep1)
                ep1 += 1
                ep1 += npat
            elif type_ == GDISJ:
                npat = _btabb(ep1)
                ep1 += 1
                ep3 = ep1 + npat
                while True:
                    if ep1 == ep3:
                        return None
                    gp1 = self.env_match(ep1, gp, d)
                    if gp1 is not None:
                        break
                    npat = _btabb(ep1)
                    ep1 += 1
                    ep1 += npat
                gp = gp1
                ep1 = ep3
            elif type_ == GFEAT:
                mask = _btabw(ep1)
                ep1 += 2
                test = _btabw(ep1)
                ep1 += 2
                if d == FORW:
                    if graph[gp].g_graph == GEOS:
                        return None
                    gp += 1
                else:
                    if gp == 0:
                        return None
                    gp -= 1
                if (graph[gp].g_feats & mask) != test:
                    return None
            elif type_ == GMBOUND:
                if d == FORW:
                    if graph[gp].g_graph == GEOS:
                        return None
                    if graph[gp + 1].g_graph == GMBOUND:
                        gp += 1
                    else:
                        if graph[gp + 1].g_graph != 0:
                            return None
                else:
                    if gp != 0:
                        gp -= 1
                        if graph[gp].g_graph != GMBOUND:
                            return None
            elif type_ == GWBOUND:
                if d == FORW:
                    if graph[gp].g_graph == GEOS or graph[gp + 1].g_graph != GEOS:
                        return None
                else:
                    if gp != 0:
                        return None
            else:
                if d == FORW:
                    if graph[gp].g_graph == GEOS:
                        return None
                    gp += 1
                else:
                    if gp == 0:
                        return None
                    gp -= 1
                if graph[gp].g_graph != type_:
                    return None
        return gp

    # ---- rule match (ls_rule_rule_match, ACNA path, lang tags 0) ----
    def rule_match(self, gp1: int, def_lang: int, sel_lang: int) -> int:
        graph = self.graph
        gp1 -= 1
        g = graph[gp1].g_graph
        rulep = _wtab(2 * g + 0)
        nrule = _wtab(2 * g + 1)
        self.rpart = 0
        while nrule:
            nrule -= 1
            gp2 = gp1
            lang = _wtab(rulep + 0)
            specific = lang & 0x8000
            lang &= 0x7FFF
            fail = False
            if specific and lang != sel_lang:
                fail = True
            elif not specific and lang != def_lang and lang != sel_lang:
                fail = True
            if not fail:
                xrule = _wtab(rulep + 1)
                if xrule != 0:
                    while True:
                        gg = _btabb(xrule)
                        xrule += 1
                        if gg == GEOS:
                            break
                        if gp2 == 0:
                            fail = True
                            break
                        gp2 -= 1
                        if graph[gp2].g_graph != gg:
                            fail = True
                            break
            if not fail:
                xrule = _wtab(rulep + 4)
                if xrule != 0 and self.env_match(xrule, gp1, FORW) is None:
                    fail = True
            if not fail:
                xrule = _wtab(rulep + 3)
                if xrule != 0 and self.env_match(xrule, gp2, BACK) is None:
                    fail = True
            if not fail:
                gp1 = gp2
                self.rpart = _wtab(rulep + 2)
                break
            rulep += 5
        return gp1

    # ---- main driver (ls_rule_lts) ----
    def rule_lts(self, letters: str, def_lang: int, sel_lang: int) -> None:
        gp1 = 0
        for ch in letters:
            lch = LSFOLD[ord(ch) & 0xFF] if ord(ch) < 256 else ord(ch)
            if ord("a") <= lch <= ord("z"):
                if self.add_graph(gp1, lch - ord("a") + GA, 0):
                    gp1 += 1
            elif lch == ord("'"):
                if self.add_graph(gp1, GQUOTE, 0):
                    gp1 += 1

        graph = self.graph
        graph[gp1].g_graph = GEOS
        graph[gp1].g_feats = FEATS[GEOS] & 0xFFFF
        self.head.fp = self.head
        self.head.bp = self.head
        ssflag = False

        while gp1 != 0:
            gp2 = self.rule_match(gp1, def_lang, sel_lang)
            while gp1 != gp2:
                gp1 -= 1
            if self.rpart != 0:
                rpart = self.rpart
                if _btabb(rpart) != GEOS:
                    while True:
                        g = _btabb(rpart)
                        rpart += 1
                        if g == GEOS:
                            break
                        if gp1 < NGWORD - 1:
                            if self.add_graph(gp1, g, 1):
                                gp1 += 1
                    graph[gp1].g_graph = GEOS
                    graph[gp1].g_feats = FEATS[GEOS] & 0xFFFF
                else:
                    rpart += 1
                rsflag = False
                while True:
                    g = _btabb(rpart)
                    rpart += 1
                    if g == SIL:
                        break
                    if g == DASH:
                        pp2 = self.head.fp
                        if pp2 is not self.head:
                            pp2.flag |= PFDASH
                        ssflag = False
                        rsflag = False
                    elif g == STAR:
                        pp2 = self.head.fp
                        if pp2 is not self.head:
                            pp2.flag |= PFSTAR
                        ssflag = False
                        rsflag = False
                    elif g == HASH:
                        pp2 = self.head.fp
                        if pp2 is not self.head:
                            pp2.flag |= PFHASH
                        ssflag = False
                        rsflag = False
                    elif g == PLUS:
                        pp2 = self.head.fp
                        if pp2 is not self.head:
                            pp2.flag |= PFPLUS
                    elif g == EQUAL:
                        pp2 = self.head.fp
                        if not ssflag and pp2 is not self.head:
                            pp2.flag |= PFSYLAB
                    else:
                        if SNONE <= g <= S2LEFT:
                            if g != SUN:
                                rsflag = True
                            pp2 = self.head.fp
                            if not ssflag and pp2 is not self.head:
                                pp2.stress = g
                        elif (g & TWOPH) != 0:
                            uph = _btabb(rpart)
                            rpart += 1
                            self.add_phone(g & MSKPH, uph)
                        else:
                            self.add_phone(g, SIL)
                if rsflag:
                    ssflag = True

        # allo1 + syllabification, per PFBOUND chunk
        pp1 = self.head.fp
        while pp1 is not self.head:
            pp2 = pp1
            pp3 = pp2.fp
            while pp3 is not self.head and (pp3.flag & PFBOUND) == 0:
                pp3 = pp3.fp
            self.allo1(pp2, pp3)
            self.sylables(pp2, pp3)
            pp1 = pp3

        self.delete_geminate_pairs()

        pstype = SPRI
        pp1 = self.head.fp
        while pp1 is not self.head:
            pp2 = pp1
            pp3 = pp2.fp
            while pp3 is not self.head and (pp3.flag & PFBOUND) == 0:
                pp3 = pp3.fp
            self.stress(pp2, pp3, pstype, sel_lang)
            pstype = SSEC
            pp1 = pp3

        self.allo2()

    # ---- ls_rule_delete_geminate_pairs ----
    def delete_geminate_pairs(self) -> None:
        pp1 = self.head.fp
        while pp1 is not self.head:
            ph1 = pp1.sphone
            ph2 = pp1.bp.sphone
            if (ph1 == US_LL and ph2 == US_EL) or (ph1 == US_EL and ph1 == US_LL):
                self.delgemphone(pp1, US_EL)
                pp1 = pp1.fp
                continue
            if (pp1.flag & PFMORPH) == 0:
                if (ph1 == US_T and ph2 == US_TH) or (ph1 == US_TH and ph2 == US_T):
                    self.delgemphone(pp1, US_TH)
                    pp1 = pp1.fp
                    continue
                if (ph1 == US_S and ph2 == US_SH) or (ph1 == US_SH and ph2 == US_S):
                    self.delgemphone(pp1, US_SH)
                    pp1 = pp1.fp
                    continue
                if ph1 == ph2 and _is_cons(pp1):
                    self.delgemphone(pp1, pp1.sphone)
                    pp1 = pp1.fp
                    continue
            pp1 = pp1.fp

    # ---- ls_adju_allo1 (US) ----
    def allo1(self, fpp: _Phone, lpp: _Phone) -> None:
        pp1 = fpp
        while pp1 is not lpp:
            if (
                pp1.sphone == US_Z
                and (pp1.flag & PFMORPH) != 0
                and pp1.fp is lpp
                and pp1 is not fpp
            ):
                pp2 = pp1.bp
                i = _pfeat(pp2.sphone)
                if (i & (PCONS | PSIB)) == (PCONS | PSIB):
                    if not self.ins_phone(pp1, US_IX, SIL, SUN):
                        return
                    pp1 = pp1.fp
                    continue
                if (i & (PCONS | PVOICE)) == PCONS:
                    pp1.sphone = US_S
                    pp1 = pp1.fp
                    continue
            if (
                pp1.sphone == US_D
                and (pp1.flag & PFMORPH) != 0
                and pp1.fp is lpp
                and pp1 is not fpp
            ):
                pp2 = pp1.bp
                i = pp2.sphone
                if i == US_T or i == US_D:
                    if not self.ins_phone(pp1, US_IX, SIL, SUN):
                        return
                    pp1 = pp1.fp
                    continue
                if (_pfeat(i) & (PCONS | PVOICE)) == PCONS:
                    pp1.sphone = US_T
                    pp1 = pp1.fp
                    continue
            pp1 = pp1.fp

    # ---- ls_adju_sylables ----
    def sylables(self, fpp: _Phone, lpp: _Phone) -> None:
        lsp = None
        pp1 = fpp
        while pp1 is not lpp:
            if (pp1.flag & PFSYLAB) != 0:
                lsp = pp1
                break
            pp1 = pp1.fp
        while pp1 is not fpp:
            stype = SNONE
            while True:
                pp2 = pp1.bp
                if not _is_cons(pp2):
                    break
                pp1 = pp2
                if pp1.stress != SNONE:
                    stype = pp1.stress
                    pp1.stress = SNONE
                if pp1 is fpp:
                    break
            if pp1 is fpp:
                if lsp is not None:
                    lsp.flag &= ~PFSYLAB
                    stype = lsp.stress
                    lsp.stress = SNONE
                pp1.flag |= PFSYLAB
                pp1.stress = stype
                break
            pp1 = pp1.bp
            pp1.flag |= PFLEFTC
            if pp1.stress != SNONE:
                stype = pp1.stress
                pp1.stress = SNONE
            out = False
            if (pp1.flag & PFMORPH) != 0 or pp1 is fpp:
                out = True
            else:
                pp2 = pp1.bp
                if not _is_cons(pp2):
                    out = True
            if not out:
                pp1 = pp2
                pp1.flag |= PFLEFTC
                if pp1.stress != SNONE:
                    stype = pp1.stress
                    pp1.stress = SNONE
                if (pp1.flag & PFMORPH) != 0 or pp1 is fpp:
                    out = True
                else:
                    pp2 = pp1.bp
                    if not _is_cons(pp2):
                        out = True
                if not out:
                    type_ = _cluster(pp2.sphone, pp1.sphone)
                    if type_ == ILLEGAL:
                        out = True
                    else:
                        pp1 = pp2
                        pp1.flag |= PFLEFTC
                        if pp1.stress != SNONE:
                            stype = pp1.stress
                            pp1.stress = SNONE
                        if (
                            type_ == TRYS
                            and (pp1.flag & PFMORPH) == 0
                            and pp1 is not fpp
                        ):
                            pp2 = pp1.bp
                            if pp2.sphone == US_S or pp2.sphone == US_SH:
                                pp1 = pp2
                                pp1.flag |= PFLEFTC
                                if pp1.stress != SNONE:
                                    stype = pp1.stress
                                    pp1.stress = SNONE
            pp1.flag |= PFSYLAB
            pp1.stress = stype
            lsp = pp1

    # ---- ls_adju_stress ----
    def unstressed(self, n: int) -> bool:
        pp = self.sylp[n]
        while _is_cons(pp):
            pp = pp.fp
        return pp.sphone == US_EL

    def suffixscan(self, fpp: _Phone, lpp: _Phone) -> bool:
        self.nsyl = 0
        self.rsyl = -1
        self.psyl = -1
        pp = fpp
        while pp is not lpp:
            if (pp.flag & PFSYLAB) != 0:
                if self.nsyl >= NSYL:
                    return False
                if pp.stress != SNONE:
                    if self.rsyl < 0:
                        self.rsyl = self.nsyl
                    if self.psyl < 0 and pp.stress >= SPRI:
                        self.psyl = self.nsyl
                self.sylp[self.nsyl] = pp
                self.nsyl += 1
            pp = pp.fp
        if self.rsyl < 0:
            self.rsyl = self.nsyl
        return True

    def prefixscan(self, fpp: _Phone, lpp: _Phone, lang_tag: int) -> bool:
        pp1 = fpp
        csyl = 0
        while True:  # loop:
            if csyl >= self.nsyl - 1:
                return True
            p = 0
            restart = False
            while (PREFTAB[p + 1] & PLENGTH) != 0:
                length = PREFTAB[p + 1] & PLENGTH
                if PREFTAB[p] != 0xFF and PREFTAB[p] != lang_tag:
                    p += length + 2
                    continue
                base = p + 1  # after ptp++
                pp2 = pp1
                ok = True
                for i in range(length):
                    if pp2 is lpp or pp2.sphone != PREFTAB[base + 1 + i]:
                        ok = False
                        break
                    pp2 = pp2.fp
                if not ok:
                    p = base + length + 1
                    continue
                if pp2 is not lpp and (pp2.flag & PFLEFTC) == 0:
                    p = base + length + 1
                    continue
                if (PREFTAB[base] & PRCON) != 0 and (pp2 is lpp or not _is_cons(pp2)):
                    p = base + length + 1
                    continue
                if (PREFTAB[base] & PRVOC) != 0 and (pp2 is lpp or not _is_voc(pp2)):
                    p = base + length + 1
                    continue
                self.sylp[csyl].flag |= PFRFUSE
                csyl += 1
                if (PREFTAB[base] & P2SYL) != 0 and csyl < self.nsyl - 1:
                    self.sylp[csyl].flag |= PFRFUSE
                    csyl += 1
                if (PREFTAB[base] & PCONT) == 0:
                    return True
                pp1 = pp2
                restart = True
                break
            if restart:
                continue
            if csyl >= self.nsyl - 1:
                return True
            if (
                pp1 is not lpp
                and _is_voc(pp1)
                and (pp1 := pp1.fp) is not lpp
                and _is_cons(pp1)
                and (pp2 := pp1.fp) is not lpp
                and (pp2.flag & PFSYLAB) != 0
                and pp1.sphone == pp2.sphone
            ):
                self.sylp[csyl].flag |= PFRFUSE
            return True

    def best2syl(self) -> None:
        pp = self.sylp[0]
        ph = pp.sphone
        if ph == US_AE and (pp.fp.flag & PFSYLAB) != 0:
            self.psyl = 1
            return
        if _is_voc(pp) and _is_cons(pp.fp) and _is_cons(pp.fp.fp):
            if ph in (US_AE, US_EH, US_IX, US_AH) or ph == 2:  # US_IH == 2
                self.psyl = 1
                return
        self.psyl = 0

    def bestdefault(self) -> None:
        rsyl = self.rsyl
        if rsyl <= 1:
            self.psyl = 0
        elif rsyl == 2:
            self.best2syl()
        elif rsyl == 3:
            self.psyl = 0
            if _is_cons(self.sylp[2].bp):
                self.psyl = 1
        else:
            if (
                self.sylp[rsyl - 1].bp.sphone == US_IY
                and self.sylp[rsyl - 1].sphone == US_AX
            ):
                self.psyl = rsyl - 3
            else:
                self.psyl = rsyl - 2

    def final_fixes(self) -> None:
        last = SPRI
        while self.psyl != 0 and self.sylp[self.psyl - 1].stress != SNONE:
            self.psyl -= 1
            last = self.sylp[self.psyl].stress
        while self.psyl != 0:
            self.psyl -= 1
            if last == SUN:
                if self.sylp[self.psyl].stress == SNONE:
                    self.sylp[self.psyl].flag |= PFBLOCK
                last = SSEC
            else:
                last = SUN
            if self.sylp[self.psyl].stress == SNONE:
                self.sylp[self.psyl].stress = SUN
        pp = self.head.fp
        if (
            pp.sphone == US_AX
            and (pp := pp.fp) is not self.head
            and pp.sphone == US_N
            and (pp := pp.fp) is not self.head
            and (pp.flag & PFSYLAB) != 0
        ):
            pp = self.head.fp
            pp.sphone = US_AH
            pp.uphone = SIL
            pp.stress = SPRI
        if self.nsyl == 3:
            pp = self.head.bp
            if pp.sphone == US_AA and pp.uphone == US_AX:
                self.sylp[2].flag &= ~PFBLOCK

    def _spread_reduction(self, pstype: int) -> None:
        self.sylp[self.psyl].stress = pstype
        csyl = self.psyl + 1
        isreduced = True
        while csyl < self.nsyl:
            if not isreduced:
                if self.sylp[csyl].stress == SNONE:
                    self.sylp[csyl].flag |= PFBLOCK
                isreduced = True
            else:
                isreduced = False
            if self.sylp[csyl].stress == SNONE:
                self.sylp[csyl].stress = SUN
            csyl += 1
        self.final_fixes()

    def stress(self, fpp: _Phone, lpp: _Phone, pstype: int, sel_lang: int) -> None:
        if not self.suffixscan(fpp, lpp):
            return
        if not self.prefixscan(fpp, lpp, sel_lang):
            return
        if self.psyl >= 0:
            type_ = self.sylp[self.psyl].stress
            if type_ == S1LEFT or type_ == S2LEFT:
                if self.psyl != 0:
                    self.sylp[self.psyl].stress = SUN
                    self.psyl -= 1
                    if type_ == S2LEFT and self.psyl != 0:
                        self.sylp[self.psyl].stress = SUN
                        self.psyl -= 1
            while self.psyl != 0 and self.unstressed(self.psyl):
                self.psyl -= 1
            while self.psyl < self.nsyl - 1 and (self.sylp[self.psyl].flag & PFRFUSE) != 0:
                self.psyl += 1
            while self.psyl < self.nsyl - 1 and self.unstressed(self.psyl):
                self.psyl += 1
            self._spread_reduction(pstype)
            return
        if (self.sylp[0].flag & PFRFUSE) != 0:
            self.psyl = 0
            while self.psyl < self.nsyl - 1 and (self.sylp[self.psyl].flag & PFRFUSE) != 0:
                self.psyl += 1
            while self.psyl < self.nsyl - 1 and self.unstressed(self.psyl):
                self.psyl += 1
            self._spread_reduction(pstype)
            return
        self.bestdefault()
        self._spread_reduction(pstype)

    # ---- ls_adju_allo2 (US) ----
    def allo2(self) -> None:
        head = self.head
        sthis = SNONE
        fthis = 0
        pp1 = head.fp
        while pp1 is not head:
            if (pp1.flag & PFSYLAB) != 0:
                sthis = pp1.stress
                fthis = pp1.flag
            if (fthis & PFBLOCK) == 0 and (pp1.uphone != SIL and sthis == SUN):
                pp1.sphone = pp1.uphone
                pp1.uphone = SIL
            pp1 = pp1.fp

        head.sphone = SIL
        head.uphone = SIL
        head.flag = PFMORPH
        sthis = SNONE
        sleft = SNONE
        pp1 = head.fp
        while pp1 is not head:
            ph1 = pp1.sphone
            if (pp1.flag & PFSYLAB) != 0:
                sleft = sthis
                sthis = pp1.stress
            if sthis == SUN and (ph1 == US_AX or ph1 == US_IX):
                pp2 = pp1.fp
                if (
                    pp2.sphone == US_LL
                    and (pp2.flag & PFSYLAB) == 0
                    and (pp2.fp.flag & PFMORPH) != 0
                ):
                    self.del_phone(pp2)
                    pp1.sphone = US_EL
                    pp1 = pp1.fp
                    continue
            if (
                sthis != SUN
                and (ph1 == US_LL or ph1 == US_R)
                and _is_obs(pp1.bp)
                and (pp1.fp.flag & PFMORPH) != 0
            ):
                pp1.sphone = US_RR
                if ph1 == US_LL:
                    pp1.sphone = US_EL
                pp1 = pp1.fp
                continue
            if (
                ph1 == US_AX
                and (pp2 := pp1.fp).sphone == US_R
                and (pp2.flag & PFSYLAB) == 0
            ):
                self.del_phone(pp2)
                pp2 = pp1.fp
                if pp2.sphone == US_R:
                    if (pp2.flag & PFSYLAB) == 0:
                        self.del_phone(pp2)
                        pp1.sphone = US_RR
                else:
                    pp1.sphone = US_RR
                pp1 = pp1.fp
                continue
            if ph1 == US_N:
                pp2 = pp1.fp
                if pp2.sphone == US_UW:
                    pp3 = pp2.fp
                    if pp3.sphone == US_EL and (pp3.fp.flag & PFMORPH) != 0:
                        if not self.ins_phone(pp2, US_Y, SIL, SNONE):
                            return
                        pp1 = pp2
                        continue
            if (
                ph1 == US_N
                and ((pp2 := pp1.fp).sphone == US_K or pp2.sphone == US_G)
                and (pp2.flag & PFSYLAB) == 0
            ):
                pp1.sphone = US_NX
                pp1 = pp1.fp
                continue
            if ph1 == US_G or ph1 == US_K:
                repl = US_JH if ph1 == US_G else US_S
                pp2 = pp1.fp
                done = False
                if (
                    pp2.sphone == US_AY
                    and (pp2 := pp2.fp).sphone == US_Z
                    and (pp2.fp.flag & PFMORPH) != 0
                ):
                    pp1.sphone = repl
                    pp1 = pp1.fp
                    done = True
                elif pp2.sphone == US_IX:
                    pp2 = pp2.fp
                    if pp2.sphone == US_D and (pp2.fp.flag & PFMORPH) != 0:
                        pp1.sphone = repl
                        pp1 = pp1.fp
                        done = True
                    elif pp2.sphone == US_Z:
                        pp3 = pp2.fp
                        if pp3.sphone == US_AX and (pp3 := pp3.fp).sphone == US_M and (
                            pp3.fp.flag & PFMORPH
                        ) != 0:
                            pp1.sphone = repl
                            pp1 = pp1.fp
                            done = True
                    if not done and pp2.sphone == US_S:
                        pp3 = pp2.fp
                        if pp3.sphone == US_T and (pp3.fp.flag & PFMORPH) != 0:
                            pp1.sphone = repl
                            pp1 = pp1.fp
                            done = True
                if done:
                    continue
            if ph1 == US_D:
                pp2 = pp1.fp
                if (
                    pp2.sphone == US_UW
                    and ((pp2 := pp2.fp).sphone == US_LL or pp2.sphone == US_EL)
                    and (pp2.fp.flag & PFMORPH) != 0
                ):
                    pp1.sphone = US_JH
                    pp1 = pp1.fp
                    continue
            if ph1 == US_S:
                pp2 = pp1.bp
                if (
                    pp2.sphone == US_K
                    and pp2.bp.sphone == US_IX
                    and sleft == SUN
                    and _is_voc(pp1.fp)
                    and sthis != SUN
                ):
                    pp2.sphone = US_G
                    pp1.sphone = US_Z
                    continue
                pp2 = pp1.bp
                if pp2.sphone == US_S:
                    pp3 = pp1.fp
                    if pp3.sphone == US_UW and (pp3.fp.flag & PFMORPH) != 0:
                        if (pp2.flag & PFSYLAB) != 0:
                            return
                        self.del_phone(pp2)
                        pp1.sphone = US_SH
                        pp1 = pp1.fp
                        continue
                pp2 = pp1.fp
                if pp2.sphone == US_IY:
                    pp3 = pp2.fp
                    if pp3.sphone == US_AX:
                        pp4 = pp3.fp
                        if pp4.sphone == US_S and (pp4.fp.flag & PFMORPH) != 0:
                            if (pp2.flag & PFSYLAB) != 0:
                                return
                            self.del_phone(pp2)
                            pp1.sphone = US_SH
                            pp1 = pp1.fp
                            continue
            if ph1 == US_T:
                pp2 = pp1.fp
                if pp2.sphone == US_UW:
                    pp3 = pp2.fp
                    if (pp3.flag & PFMORPH) != 0:
                        pp1.sphone = US_CH
                        pp1 = pp1.fp
                        continue
                    if pp3.sphone == US_EL and (pp3.fp.flag & PFMORPH) != 0:
                        pp1.sphone = US_CH
                        pp1 = pp1.fp
                        continue
                    if (
                        pp3.sphone == US_EY
                        and (pp4 := pp3.fp).sphone == US_R
                        and (pp4 := pp4.fp).sphone == US_IY
                        and (pp4.fp.flag & PFMORPH) != 0
                    ):
                        pp1.sphone = US_CH
                        pp1 = pp1.fp
                        continue
                else:
                    if pp2.sphone == US_IY:
                        pp3 = pp2.fp
                        if pp3.sphone == US_AX and (pp3.fp.flag & PFMORPH) != 0:
                            if (pp2.flag & PFSYLAB) != 0:
                                return
                            self.del_phone(pp2)
                            pp1.sphone = US_SH
                            pp1 = pp1.fp
                            continue
                        if (
                            pp3.sphone == US_EY
                            and (pp4 := pp3.fp).sphone == US_T
                            and (pp4 := pp4.fp).sphone == US_RR
                            and (pp4.fp.flag & PFMORPH) != 0
                        ):
                            pp1.sphone = US_SH
                            pp1 = pp1.fp
                            continue
            pp1 = pp1.fp

    # ---- ls_rule_lts_out ----
    def emit(self) -> list[int]:
        out: list[int] = []
        pp1 = self.head.fp
        s = 0
        while pp1 is not self.head:
            if (pp1.flag & PFDASH) != 0:
                out.append(SBOUND)
            if (pp1.flag & PFSTAR) != 0:
                out.append(MBOUND)
            if (pp1.flag & PFHASH) != 0:
                out.append(HYPHEN)
            if (pp1.flag & PFSYLAB) != 0:
                s = pp1.stress
            if s != SUN and not _is_cons(pp1):
                if s == SPRI:
                    out.append(S1)
                elif s == SSEC:
                    out.append(S2)
                s = SUN
            out.append(pp1.sphone)
            pp1 = pp1.fp
        return out


# US_IH is 2; used by best2syl.
US_IH = 2


def _cluster(f: int, s: int) -> int:
    if f == US_P:
        if s == US_LL or s == US_R:
            return TRYS
    elif f == US_B:
        if s == US_LL or s == US_R:
            return OK
    elif f == US_F:
        if s == US_R:
            return TRYS
        if s == US_LL:
            return OK
    elif f == US_T:
        if s == US_R:
            return TRYS
        if s == US_W:
            return OK
    elif f == US_D or f == US_TH:
        if s == US_W or s == US_R:
            return OK
    elif f == US_K:
        if s == US_W or s == US_LL or s == US_R:
            return TRYS
    elif f == US_G:
        if s == US_W or s == US_LL or s == US_R:
            return OK
    elif f == US_S:
        if s in (US_W, US_LL, US_P, US_T, US_K, US_M, US_N, US_F):
            return OK
    elif f == US_SH:
        if s in (US_W, US_LL, US_R, US_P, US_T, US_M, US_N):
            return OK
    return ILLEGAL


@dataclass(frozen=True)
class RuleResult:
    """Phoneme+stress send stream for one out-of-dictionary word."""

    codes: tuple[int, ...]


def pronounce(word: str, def_lang: int = 0, sel_lang: int = 0) -> RuleResult:
    """Run the US letter-to-sound rules for an out-of-dictionary word.

    Returns the sequence of raw phoneme+prosody codes the engine hands to
    `ls_util_send_phone` (the pre-`ph/` boundary): US phoneme font indices
    interleaved with S1/S2 stress and SBOUND/MBOUND/HYPHEN markers.
    """
    lts = _Lts()
    lts.rule_lts(word, def_lang, sel_lang)
    return RuleResult(tuple(lts.emit()))
