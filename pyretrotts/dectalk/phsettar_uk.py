"""DECtalk UK-English transition setup (`phsettar`, the UK smooth/coartic stage).

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/ph/p_uk_st1.c`: `UKP_special_coartic` (line 305),
`uk_forw_smooth_rules` (446), `uk_back_smooth_rules` (834),
`uk_special_rules` (1240)), together with the shared `phsettar`/`gettar`/
`getbegtar`/`getendtar`/`make_dip`/`setloc` machinery from
`src/dapi/src/ph/ph_setar.c` and `ph_sttr2.c`, for the build where `ENGLISH_UK`,
`OLD_INTONATION_AND_TIMING`, and `OLD_SETTAR` are defined and `GERMAN`,
`FRENCH`, `LRULES`, `RRULES`, `HLSYN`, `NEW_VTM` are not. FONIX Corporation
declares that source proprietary and confidential. This file is NOT covered by
this project's MIT licence. See NOTICE.

This is the British-English analogue of `phsettar.py`. The US path stays byte
identical (`phclause` routes US through `phsettar.phsettar`); UK routes here. The
per-phone state container (`PhsettarState`/`Parameter`), the pure fixed-point
helpers (`mlsh1`/`muldv`/`mstofr`/`shrdur`), and the `to_draw_params` snapshot
are shared with `phsettar.py`.

The shared `ph/` chain reads every per-symbol table (`place`, `begtyp`,
`endtyp`, `phone_feature`, `burdr`, `ptram`, `inh_timing`, `plocu`, the locus
ROM, the diphthong ROM, the target ROM) through the phone's font byte
(`all_*[phone>>8]`, `ph_defs.h`/`ph_setar.c`). In a UK utterance the only two
fonts present are UK (`0x1D`) and the boundary silence `GEN_SIL` (`0x1E00`, the
US font). So every accessor here dispatches by font: UK phones use the UK tables,
`GEN_SIL` uses the US row (`us_*[0]`), exactly as `all_*[0x1E][0]` does.

The `uk_gettar` inner ROM indexer (`settar_uk.py`) is unchanged; this module
ports the four UK rule functions and the neighbour-probing `gettar` wrapper that
dispatches per probe to `uk_gettar`/`us_gettar` by the probed phone's font
(`ph_setar.c:2083-2107`). The `USP_K` F2/F3 raise (`ph_setar.c:2108`) tests a
US-font `[k]`, so it can never match a UK-font phone and is inert here.

The four UK rule functions differ from their US analogues (`p_us_st0.c`) only in:

  * `UKP_special_coartic` (`p_uk_st1.c:305`): F3 is raised (not lowered) before
    `[LX]` by `diphpos` (+150/+250/+350); the `[LX]` F2 lowering is by `diphpos`
    (-150/-250/-350) not vowel range; `[UW]` raising requires a sonorant
    `+alveolar` left context; the unstressed `temp += temp>>1` boost is
    `#ifdef OUTFORUK`, undefined in this build, so it is dropped and the
    phrase-final `temp >>= 1` becomes unconditional.
  * `uk_forw_smooth_rules`/`uk_back_smooth_rules` (`p_uk_st1.c:446`/`834`): the
    nasal-zero boundary is `NASAL_ZERO_BOUNDARY` (370) not 400, and the forward
    `nasvowel` B-widening `bouval -= 20` block is removed. Otherwise identical.
  * `uk_special_rules` (`p_uk_st1.c:1240`): the homorganic no-burst test adds a
    plosive short-circuit and a `MASKFRONT` "both done up front" test; aspiration
    amplitude is 52/54 (US 57/61) keyed on `begtyp(phcur)` not `begtyp(phonex)`;
    an over-long VOT zeroes `AP.pspesh`; the US dummy-vowel VOT override is
    removed; the voicebar block adds a `[JH]` special. The `PAREAL`/`PAREAB`
    burst-area writes target `param[18]`/`param[17]`, parameters the OLD-VTM draw
    stage never reads, so they are inert and not modelled.

All arithmetic is the reference's fixed point (`short`).
"""
from __future__ import annotations

from .phsettar import (
    BACK_ROUNDED_VOWEL,
    DIVTAB,
    F2BACKF,
    F2BACKI,
    FALVEL,
    FBOUNDARY,
    FBURST,
    FCONSON,
    FDENTAL,
    FDUMMY_VOWEL,
    FNASAL,
    FOBST,
    FPALATL,
    FPLOSV,
    FSENTENDS,
    FSONCON,
    FSONOR,
    FSTOP,
    FSTRESS,
    FSTRESS_1,
    FSYLL,
    FVOICD,
    FVOWEL,
    FVPNEXT,
    N10PRCNT,
    N15PRCNT,
    N25PRCNT,
    NF15MS,
    NF20MS,
    NF25MS,
    NF30MS,
    NF40MS,
    NF45MS,
    NF50MS,
    NF60MS,
    NF64MS,
    NF70MS,
    NF75MS,
    NF80MS,
    NF100MS,
    NF130MS,
    NPARAM,
    OBSTRUENT,
    PA2,
    PA3,
    PA6,
    PAB,
    PAP,
    PAV,
    PB1,
    PB2,
    PB3,
    PF1,
    PF2,
    PF3,
    PTILT,
    PVALUE,
    ROUNDED_SONOR_CONS,
    Parameter,
    PhsettarState,
    build_rawbuf,
    mlsh1,
    mstofr,
    muldv,
    shrdur,
    to_draw_params,
    us_back_smooth_rules,
    us_forw_smooth_rules,
    us_special_rules,
)
from .settar import (
    FEMALE,
    GEN_SIL,
    MALE,
    PSFONT,
    US_BEGTYP,
    US_ENDTYP,
    US_PTRAM,
    Allophones,
)
from .settar_uk import uk_gettar
from .targets import PARINI, PARTYP, US_FEATB, US_PLACE
from .targets_transitions import (
    US_BURDR,
    US_INHDR,
    US_PLOCU,
)
from .targets_transitions_uk import (
    UK_BURDR,
    UK_FEMLOC,
    UK_INHDR,
    UK_MALELOC,
    UK_PLOCU,
)
from .targets_uk import (
    UK_BEGTYP,
    UK_ENDTYP,
    UK_FEATB,
    UK_FEMDIP,
    UK_MALDIP,
    UK_PLACE,
    UK_PTRAM,
)
from .vtm import s16

__all__ = ["phsettar_uk", "to_draw_params", "build_rawbuf"]

# Parameter indices reused via helper (`ph_setar.c` derives `&PB3 - np`).
IS_FORM_FREQ = 3
IS_NASAL_ZERO_FREQ = 1
IS_FORM_BW = 4
IS_PARALLEL_FORM_AMP = 2
IS_AV_OR_AH = 0

UK_TOT_ALLOPHONES = 57
PFUK = 0x1D
PFUSA = 0x1E

# Place-of-articulation grouping bits (`ph_defs.h:155,307-318`).
FLABIAL = 0o1
FVELAR = 0o20
BLADEAFFECTED = FDENTAL | FPALATL | FALVEL
MASKFRONT = 0o17

NASAL_ZERO_BOUNDARY = 370  # `ph_defs.h:162` (US smooth rules use the literal 400)


def _ukp(code: int) -> int:
    return (PFUK << PSFONT) | code


(UKP_IY, UKP_IH, UKP_EY, UKP_EH, UKP_AE, UKP_AA, UKP_AY, UKP_AW, UKP_AH,
 UKP_AO, UKP_OW, UKP_OY, UKP_UH, UKP_UW, UKP_RR, UKP_YU, UKP_AX, UKP_IX,
 UKP_IR, UKP_ER, UKP_AR, UKP_OR, UKP_UR, UKP_W, UKP_YX, UKP_R, UKP_LL,
 UKP_HX, UKP_RX, UKP_LX, UKP_M, UKP_N, UKP_NX, UKP_EL, UKP_DZ, UKP_EN,
 UKP_F, UKP_V, UKP_TH, UKP_DH, UKP_S, UKP_Z, UKP_SH, UKP_ZH, UKP_P, UKP_B,
 UKP_T, UKP_D, UKP_K, UKP_G, UKP_DX, UKP_TX, UKP_Q, UKP_CH, UKP_JH) = (
    _ukp(i) for i in range(1, 56))


# --- per-symbol table accessors, dispatched by the phone's font byte ---
# `all_*[phone>>8][phone&0xff]`: UK phones (0x1D) index the UK table, the
# boundary `GEN_SIL` (0x1E00) indexes the US row (`us_*[0]`).

def _is_uk(phone: int) -> bool:
    return (phone >> PSFONT) == PFUK


def phone_feature(phone: int) -> int:
    idx = phone & 0xFF
    return UK_FEATB[idx] if _is_uk(phone) else US_FEATB[idx]


def begtyp(phone: int) -> int:
    idx = phone & 0xFF
    return UK_BEGTYP[idx] if _is_uk(phone) else US_BEGTYP[idx]


def endtyp(phone: int) -> int:
    idx = phone & 0xFF
    return UK_ENDTYP[idx] if _is_uk(phone) else US_ENDTYP[idx]


def ptram(phone: int) -> int:
    idx = phone & 0xFF
    return UK_PTRAM[idx] if _is_uk(phone) else US_PTRAM[idx]


def burdr(phone: int) -> int:
    idx = phone & 0xFF
    return UK_BURDR[idx] if _is_uk(phone) else US_BURDR[idx]


def place(phone: int) -> int:
    idx = phone & 0xFF
    return UK_PLACE[idx] if _is_uk(phone) else US_PLACE[idx]


def plocu(index: int) -> int:
    # `all_plocu[index>>8][index&0xff]`; the fonobst+offset never crosses the
    # 0x1D font boundary for the reached `sontyx` (<=4, offset < 256).
    idx = index & 0xFF
    return UK_PLOCU[idx] if (index >> PSFONT) == PFUK else US_PLOCU[idx]


def inh_timing(phone: int) -> int:
    if (phone & PVALUE) >= 100:
        return 0
    idx = phone & PVALUE
    return UK_INHDR[idx] if _is_uk(phone) else US_INHDR[idx]


def _loc_table(st: PhsettarState) -> tuple[int, ...]:
    return UK_MALELOC if st.malfem == MALE else UK_FEMLOC


def _diph(st: PhsettarState, i: int) -> int:
    # `GEN_SIL` never yields a `<-1` diphthong pointer, so every reached
    # resolution runs with the UK ROM (`last_lang == PFUK`).
    tbl = UK_MALDIP if st.malfem == MALE else UK_FEMDIP
    return tbl[i]


def _stream(st: PhsettarState) -> Allophones:
    return Allophones(st.allophons, st.allofeats, st.nallotot, st.malfem)


def gettar(st: PhsettarState, phone: int) -> int:
    """`gettar` (`ph_setar.c:1915`): the neighbour-probing wrapper -- probe
    self/phnex/phnex+2/phlas until a usable target is found.

    The C dispatches each probe to the per-font inner gettar
    (`all_gettar[phone>>8]`, `ph_setar.c:2083`). In a UK utterance the only
    non-UK phone is the boundary `GEN_SIL` (`0x1E00`, US font), which the C sends
    to `us_gettar` (`p_us_st1.c`); but every row-0 UK/US table is identical and
    both inner functions share the same no-internal-fallback structure, so
    `uk_gettar(GEN_SIL)` equals `us_gettar(GEN_SIL)`. All probes therefore route
    through `uk_gettar`. The neighbour walk (the `-1`/`PARINI` fallback) lives
    here in the wrapper, not in the inner gettar (contrast the older
    `settar.us_gettar`, which carries a now-superseded internal fallback).

    The `USP_K` F2/F3 raise (`ph_setar.c:2108`) tests a US-font `[k]`, so it can
    never match a UK-font phone and is inert here."""
    stream = _stream(st)
    index = (0, 1, 2, -1)
    count = 0
    while count <= 3:
        if index[count] == 2 and st.nallotot >= (phone + index[count] + 1):
            count += 1
        idx = index[count]
        tartemp = uk_gettar(stream, st.np, phone + idx)
        # `allophons[phone+idx] == USP_K` (US font) never matches a UK phone.
        if idx == -1:
            if tartemp > 0:
                return tartemp
            if tartemp < -1:
                t = tartemp
                while _diph(st, -t) != -1:
                    t -= 1
                tartemp = _diph(st, -t - 1)
            if tartemp == -1:
                tartemp = PARINI[st.np]
            return tartemp
        if idx == 0:
            if tartemp != -1:
                return tartemp
        else:  # idx 1 or 2
            if tartemp < -1:
                return _diph(st, -tartemp)
            if tartemp > 0:
                return tartemp
        count += 1
    return 0


def uk_special_coartic(st: PhsettarState, nfon: int, diphpos: int) -> int:
    """`UKP_special_coartic` (`p_uk_st1.c:305`): UK vowel F2/F3 context shifts."""
    temp = 0
    foncur = st.get_phone(nfon)
    fonnex = st.get_phone(nfon + 1)
    fonlas = st.get_phone(nfon - 1)
    if st.np == PF3:
        if (phone_feature(foncur) & FVOWEL) != 0 and foncur != UKP_RR:
            if fonlas in (UKP_W, UKP_R) or fonnex in (UKP_W, UKP_R):
                temp = -150
        if fonnex == UKP_LX:
            if diphpos == 0:
                temp = 150
            if diphpos == 1:
                temp = 250
            if diphpos > 1:
                temp = 350
    if st.np == PF2:
        if fonnex == UKP_LX:
            if diphpos == 0:
                temp = -150
            if diphpos == 1:
                temp = -250
            if diphpos > 1:
                temp = -350
        if fonlas in (UKP_W, UKP_LL, UKP_LX):
            if (UKP_IY <= foncur <= UKP_AE) or foncur == UKP_IX:
                temp = -150
        if foncur == UKP_UW and (phone_feature(fonlas) & FSONOR) != 0:
            if (place(fonlas) & FALVEL) != 0:
                if diphpos > 0:
                    temp += 200
                else:
                    temp = 200
        # The unstressed `temp += temp>>1` boost is `#ifdef OUTFORUK`, undefined
        # in this build; the phrase-final halving loses its `else`.
        if (st.feat(nfon) & FBOUNDARY) >= FVPNEXT:
            temp = temp >> 1
        if temp > 400:
            temp = 400
        if temp < -400:
            temp = -400
    return temp


def getbegtar(st: PhsettarState, nfone: int) -> int:
    """`getbegtar` (`ph_setar.c:1329`)."""
    temp = gettar(st, nfone)
    if temp < -1:
        temp = _diph(st, -temp)
    return s16(temp)


def getendtar(st: PhsettarState, nfone: int) -> int:
    """`getendtar` (`ph_setar.c:1394`)."""
    temp = gettar(st, nfone)
    if temp < -1:
        t = -temp
        while _diph(st, t) != -1:
            t += 1
        temp = _diph(st, t - 1)
        # `getendtar` dispatches special_coartic by font (`ph_setar.c:1416`) with no
        # PFUK branch, so it is never applied for a UK phone.
    return s16(temp)


def make_dip(st: PhsettarState, pdip: int, inhdr_frames: int, shrink: int) -> None:
    """`make_dip` (`ph_setar.c:1465`): generate a diphthong's straight-line segments."""
    q = st.param[st.np]
    q.ndip_off = st.ndips_ptr
    oldvalue = _diph(st, pdip)
    if st.par_type == IS_FORM_FREQ:
        st.gencoartic = N10PRCNT
        if (st.feat(st.nphone) & FSTRESS) == 0:
            st.gencoartic = N15PRCNT
            if st.np == PF2:
                st.gencoartic = N25PRCNT
        oldvalue += mlsh1(q.tarlas - oldvalue, st.gencoartic)
        # `make_dip` dispatches special_coartic by font (`ph_setar.c:1501`) with no
        # PFUK branch, so it is never applied for a UK phone.
    q.tarcur = s16(oldvalue)
    oldtime = 0
    dipsw = 0
    newvalue = oldvalue
    while True:
        if dipsw == 0:
            newvalue = oldvalue
            dipsw += 1
            pdip += 1
        else:
            newvalue = _diph(st, pdip)
            pdip += 1
            if st.par_type == IS_FORM_FREQ:
                if q.tarnex > 0:
                    newvalue += mlsh1(q.tarnex - newvalue, st.gencoartic)
        raw_time = _diph(st, pdip)
        if raw_time != -1:
            newtime = shrdur(st, raw_time, inhdr_frames, shrink)
        else:
            newtime = st.durfon
        st.dipspec[st.ndips_ptr] = s16(newtime)
        st.ndips_ptr += 1
        temp = newtime - oldtime
        if temp == 0:
            st.dipspec[st.ndips_ptr] = 0
        else:
            arg2 = (newvalue - oldvalue) << 3
            if temp < 50:
                st.dipspec[st.ndips_ptr] = mlsh1(DIVTAB[temp], arg2)
            else:
                st.dipspec[st.ndips_ptr] = int(arg2 / temp)
            oldvalue = newvalue
            oldtime = newtime
        st.ndips_ptr += 1
        if _diph(st, pdip) == -1:
            pdip += 1
            break
        pdip += 1
    q.tarend = s16(newvalue)
    q.durlin = st.dipspec[q.ndip_off]
    q.deldip = st.dipspec[q.ndip_off + 1]
    q.ndip_off += 2


def setloc(st: PhsettarState, nfonobst: int, nfonsonor: int, initfinso: str,
           nfonvowel: int) -> int:
    """`setloc` (`ph_sttr2.c:69`): obstruent<->sonorant formant locus transition.

    The vowel-vowel branch is inert (`vv_coartic_across_c` body is commented out
    in this source), so `vvbouval`/`vvdurtran` stay zero."""
    fonobst = st.get_phone(nfonobst)
    fonsonor = st.get_phone(nfonsonor)
    fonvowel = st.get_phone(nfonvowel)
    if initfinso == 'i':
        typob = endtyp(fonobst)
        typso = begtyp(fonsonor)
    else:
        typob = begtyp(fonobst)
        typso = endtyp(fonsonor)
    if st.np > PF3 or typob != OBSTRUENT or typso == OBSTRUENT:
        return 0
    if initfinso == 'i':
        f2backaffil = place(fonsonor) & F2BACKI
        curval = getbegtar(st, nfonsonor)
    else:
        f2backaffil = place(fonsonor) & F2BACKF
        curval = getendtar(st, nfonsonor)
    sontyx = typso
    if typso == ROUNDED_SONOR_CONS:
        sontyx = BACK_ROUNDED_VOWEL
    if typso == 6:
        sontyx = 2
    ploc = plocu(fonobst + (UK_TOT_ALLOPHONES * (sontyx - 1)))
    if ploc == 0:
        return 0
    loc = _loc_table(st)
    ploc = ploc + (3 * st.np)
    locus = loc[ploc]
    prcnt = loc[ploc + 1]
    st.durtran = mstofr(loc[ploc + 2])
    if typso == ROUNDED_SONOR_CONS and st.np > PF1 and (place(fonobst) & (FPALATL | FDENTAL)) == 0:
        prcnt = (prcnt >> 1) + 50
    if f2backaffil != 0 and st.np == PF2:
        prcnt += 25 - (prcnt >> 2)
        st.durtran = (st.durtran >> 1) + 2
    tmp = prcnt
    delta_freq = muldv(tmp, curval - locus, 100)
    st.bouval = s16(locus + delta_freq)
    if ((phone_feature(fonsonor) & FVOWEL) != 0
            and (phone_feature(fonvowel) & FVOWEL) != 0
            and st.np == PF2):
        st.vvbouval = 0
        st.vvdurtran = 0
        delta_freq = muldv(prcnt, curval - locus, 100)
        st.bouval = s16(locus + delta_freq)
    return 1


def uk_forw_smooth_rules(st: PhsettarState, pholas: int, fealas: int, feacur: int,
                         struclas: int, struccur: int, feanex: int) -> None:
    """`uk_forw_smooth_rules` (`p_uk_st1.c:446`)."""
    q = st.param[st.np]
    pt = st.par_type
    if pt == IS_FORM_FREQ:
        if (feacur & FSONOR) != 0:
            if (feacur & FSONCON) == 0:
                st.durtran = NF45MS
                if (fealas & FSONCON) != 0:
                    st.bouval = (st.bouval + q.tarlas) >> 1
                    if pholas == UKP_LL and st.np == PF1:
                        st.bouval += 80
                    if pholas == UKP_R and st.np != PF1:
                        st.durtran = NF70MS
                else:
                    if st.phcur == UKP_HX:
                        st.bouval = (st.bouval + q.tarlas) >> 1
            else:
                if (fealas & FSONCON) == 0:
                    st.bouval = (st.bouval + q.tarcur) >> 1
                    st.durtran = NF30MS
                else:
                    st.durtran = NF30MS
        if st.phcur == GEN_SIL:
            if st.nphone > 1:
                st.bouval = q.tarlas
            else:
                st.bouval = q.tarnex
            st.durtran = st.durfon
        else:
            setloc(st, st.nphone - 1, st.nphone, 'i', st.nphone - 2)
            setloc(st, st.nphone, st.nphone - 1, 'f', st.nphone + 1)
            if (fealas & FPLOSV) != 0 and (fealas & FVOICD) == 0:
                if st.np == PF1:
                    st.bouval += 100
            if (feacur & FOBST) != 0:
                st.durtran = NF30MS
                if st.np == PF1:
                    st.durtran = NF20MS
                if (feacur & FPLOSV) != 0:
                    st.durtran = st.durfon
            if (feacur & FNASAL) != 0:
                st.durtran = st.durfon
                if st.np == PF1:
                    st.durtran = 0
                elif ((st.phcur in (UKP_N, UKP_EN)) and endtyp(pholas) == 1):
                    if st.np == PF2:
                        st.bouval -= 100
                        if (place(pholas) & F2BACKF) != 0:
                            st.bouval -= 100
                    if st.np == PF3:
                        st.bouval -= 100
                elif (st.np == PF2 and st.phcur == UKP_M
                        and (place(pholas) & F2BACKF) != 0):
                    st.bouval -= 150
        if ((feacur & FOBST) == 0 and endtyp(pholas) != OBSTRUENT and st.durtran > 0):
            st.durtran = mlsh1(st.durtran, st.shrif) + 1
    elif pt == IS_NASAL_ZERO_FREQ:
        st.durtran = 0
        if (fealas & FNASAL) != 0 and (feacur & FNASAL) == 0:
            st.bouval = NASAL_ZERO_BOUNDARY
            st.durtran = NF80MS
    elif pt == IS_FORM_BW:
        st.durtran = NF40MS
        if (feacur & FVOICD) != 0:
            if st.np == PB1 and (fealas & FVOICD) == 0:
                st.durtran = NF50MS
                st.bouval = s16(q.tarcur + (st.param[PF1].tarcur >> 3))
        else:
            st.durtran = NF20MS
        if pholas == GEN_SIL:
            st.bouval = q.tarcur + ((PB3 - st.np) * 50)
            st.durtran = NF50MS
        elif st.phcur == GEN_SIL:
            st.bouval = q.tarlas + ((PB3 - st.np) * 50)
            if ((phone_feature(st.get_phone(st.nphone - 2)) & FVOICD) == 0
                    and (struclas & FDUMMY_VOWEL) != 0 and st.np == PB1):
                st.bouval = 260
            st.durtran = NF50MS
        # UK omits the US `if (nasvowel) bouval -= 20` B-widening here.
        if (fealas & FNASAL) != 0:
            st.bouval = q.tarcur
            if (st.np == PB2 and pholas in (UKP_N, UKP_EN)
                    and begtyp(st.phcur) != 1):
                st.bouval += 60
                st.durtran = NF60MS
            if st.np == PB1:
                st.durtran = NF100MS
                st.bouval += 70
        if (feacur & FNASAL) != 0:
            st.durtran = 0
    else:  # IS_PARALLEL_FORM_AMP or IS_AV_OR_AH
        temp = q.tarcur - 10
        if (st.bouval < temp) or ((fealas & FPLOSV) != 0) or (pholas == UKP_JH):
            st.bouval = temp
            if (feacur & FOBST) == 0:
                st.durtran = NF20MS
            if st.np == PAV:
                if pholas == GEN_SIL:
                    if (feacur & FVOICD) != 0:
                        st.durtran = NF45MS
                        st.bouval -= 8
                if (fealas & FOBST) != 0:
                    st.bouval = temp + 6
                if (fealas & FPLOSV) != 0:
                    st.bouval = q.tarcur - 5
        if (fealas & FNASAL) != 0 and (feacur & FVOICD) != 0:
            st.durtran = 0
        if (feacur & FNASAL) != 0:
            if (fealas & FVOICD) != 0:
                if st.np == PAV:
                    st.durtran = 0
        temp = q.tarlas - 10
        if st.bouval < temp:
            st.bouval = temp - 3
            if st.phcur == GEN_SIL:
                st.durtran = NF70MS
            if st.np == PAV:
                st.durtran = 0
        if st.np == PA3:
            if st.phcur in (UKP_CH, UKP_JH):
                st.durtran = st.durfon - NF15MS
                st.bouval = q.tarcur - 30
        if st.np == PAP:
            if st.phcur in (GEN_SIL, UKP_F, UKP_TH, UKP_S, UKP_SH):
                if (fealas & FVOICD) != 0 and (fealas & FOBST) == 0:
                    if st.phcur == GEN_SIL:
                        st.bouval = 52
                        st.durtran = NF80MS
                    else:
                        st.bouval = 48
                        st.durtran = NF45MS
        if st.np == PTILT:
            st.durtran = NF25MS
            if pholas == GEN_SIL:
                st.bouval = q.tarcur
            if st.phcur == GEN_SIL:
                st.bouval = st.prev_tilt
            if (fealas & FSTOP) != 0 or (feacur & FSTOP) != 0:
                st.durtran = 0
    if st.durtran > st.durfon:
        st.durtran = st.durfon
    if st.durtran > NF130MS:
        st.durtran = NF130MS
    if st.bouval < 0:
        st.bouval = 0


def uk_back_smooth_rules(st: PhsettarState, feacur: int, feanex: int,
                         strucnex: int) -> None:
    """`uk_back_smooth_rules` (`p_uk_st1.c:834`)."""
    q = st.param[st.np]
    pt = st.par_type
    if pt == IS_FORM_FREQ:
        if (feacur & FSONOR) != 0:
            st.durtran = NF45MS
            if (feacur & FSONCON) == 0:
                if (feanex & FSONCON) != 0:
                    st.bouval = (st.bouval + q.tarnex) >> 1
                    if st.np == PF3:
                        st.durtran = NF64MS
                    if st.phonex == UKP_LL and st.np == PF1:
                        st.bouval += 80
                else:
                    if st.phonex == UKP_HX:
                        st.bouval = (st.bouval + q.tarend) >> 1
            else:
                st.durtran = NF40MS
                if (feanex & FSONCON) == 0:
                    st.bouval = (st.bouval + q.tarend) >> 1
                    st.durtran = NF20MS
        if st.phonex == GEN_SIL:
            st.durtran = 0
        else:
            setloc(st, st.nphone + 1, st.nphone, 'f', st.nphone + 2)
            setloc(st, st.nphone, st.nphone + 1, 'i', st.nphone - 1)
            if (feacur & FOBST) != 0:
                st.durtran = NF30MS
                if st.np == PF1:
                    st.durtran = NF20MS
                if (feacur & FPLOSV) != 0:
                    st.durtran = st.durfon
                    if st.np == PF1 and (feacur & FVOICD) == 0:
                        st.bouval += 100
            if (feacur & FNASAL) != 0:
                st.durtran = st.durfon
                if st.np == PF1:
                    st.durtran = 0
                elif (st.phcur in (UKP_N, UKP_EN)) and begtyp(st.phonex) == 1:
                    if st.np == PF2:
                        st.bouval -= 100
                        if (place(st.phonex) & F2BACKI) != 0:
                            st.bouval -= 100
                    if st.np == PF3:
                        st.bouval -= 100
                elif (st.np == PF2 and st.phcur == UKP_M
                        and (place(st.phonex) & F2BACKI) != 0):
                    st.bouval -= 150
        if ((feacur & FOBST) == 0 and begtyp(st.phonex) != 4 and st.durtran > 0):
            st.durtran = mlsh1(st.durtran, st.shrib) + 1
    elif pt == IS_NASAL_ZERO_FREQ:
        st.durtran = 0
        if (feanex & FNASAL) != 0 and (feacur & FNASAL) == 0:
            st.bouval = NASAL_ZERO_BOUNDARY
            st.durtran = NF80MS
            if st.phonex == UKP_EN:
                st.durtran = NF130MS
    elif pt == IS_FORM_BW:
        st.durtran = NF40MS
        if (feacur & FVOICD) != 0:
            if st.np == PB1:
                if (feanex & FVOICD) == 0:
                    st.durtran = NF50MS
                    st.bouval = s16(q.tarend + (st.param[PF1].tarcur >> 3))
                    if st.malfem == FEMALE:
                        st.durtran = NF100MS
        else:
            st.durtran = NF20MS
        if st.phonex == GEN_SIL:
            st.bouval = q.tarend + ((PB3 - st.np) * 50)
            st.durtran = NF50MS
        elif st.phcur == GEN_SIL:
            st.bouval = q.tarnex + ((PB3 - st.np) * 50)
            st.durtran = NF50MS
        if (feanex & FNASAL) != 0:
            st.bouval = q.tarend
            if (st.np == PB2 and st.phonex in (UKP_N, UKP_EN)
                    and endtyp(st.phcur) != 1):
                st.bouval += 60
                st.durtran = NF60MS
            if st.np == PB1:
                st.durtran = NF100MS
                st.bouval += 100
        if (feacur & FNASAL) != 0:
            st.durtran = 0
    else:  # amplitudes
        endbsmo = False
        temp = q.tarnex - 10
        if st.bouval < temp:
            st.bouval = temp
            if st.phcur == GEN_SIL:
                st.durtran = NF70MS
        if (st.np == PAV and st.bouval < q.tarnex
                and st.phcur not in (UKP_V, UKP_DH, UKP_JH, UKP_ZH, UKP_Z)):
            st.durtran = 0
            if (feacur & FPLOSV) != 0 or st.phcur == UKP_CH:
                if (feacur & FVOICD) != 0:
                    st.bouval = q.tarend - 3
                    st.durtran = NF45MS
                else:
                    st.bouval = 0
                endbsmo = True
        if not endbsmo:
            if (feanex & FNASAL) != 0 and (feacur & FVOICD) != 0:
                st.durtran = 0
            if (feacur & FNASAL) != 0:
                if ((feanex & FVOICD) != 0 and (feanex & FOBST) == 0
                        and (strucnex & FDUMMY_VOWEL) == 0):
                    st.durtran = 0
                else:
                    st.durtran = NF40MS
            temp = q.tarend - 10
            if st.phcur >= UKP_P:
                st.durtran = NF15MS
                if st.phcur < UKP_CH:
                    temp = q.tarend
            if st.bouval < temp:
                st.bouval = temp - 3
                st.durtran = NF20MS
            if st.np == PAV:
                if (st.bouval < temp) or (temp > 0 and (strucnex & FDUMMY_VOWEL) != 0):
                    st.bouval = temp + 3
                    if st.phonex == GEN_SIL or (strucnex & FDUMMY_VOWEL) != 0:
                        st.durtran = NF75MS
                # The C's `else if (np == PAP)` is nested inside `if (np == PAV)`,
                # so it is unreachable dead code (`p_uk_st1.c:1139`).
            if ((st.phonex >= UKP_P)
                    and (((feacur & FNASAL) == 0) or (st.np != PAV))):
                st.durtran = 0
            if st.np == PAP:
                if st.phcur in (UKP_F, UKP_TH, UKP_S, UKP_SH):
                    if (feanex & FVOICD) != 0 and (feanex & FOBST) == 0:
                        st.bouval = 52
                        st.durtran = NF40MS
                if (feacur & FSYLL) != 0 and st.phonex == GEN_SIL:
                    st.bouval = 52
                    st.durtran = NF130MS
            if st.np == PTILT:
                st.durtran = NF25MS
                if st.phonex == GEN_SIL:
                    st.bouval = q.tarend
                if st.phcur == GEN_SIL:
                    st.bouval = q.tarnex
                if (feanex & FSTOP) != 0 or (feacur & FSTOP) != 0:
                    st.durtran = 0
                if (feacur & FVOICD) != 0 and (feacur & FNASAL) == 0:
                    if st.phonex == GEN_SIL:
                        st.bouval = 15
                        st.durtran = NF130MS
    if st.durtran > NF130MS:
        st.durtran = NF130MS
    if st.durtran > st.durfon:
        st.durtran = st.durfon
    st.param[st.np].tbacktr = s16(st.durfon - st.durtran)
    if st.bouval < 0:
        st.bouval = 0


def uk_special_rules(st: PhsettarState, fealas: int, feacur: int, feanex: int,
                     struclm2: int, struccur: int, pholas: int, struclas: int) -> None:
    """`uk_special_rules` (`p_uk_st1.c:1240`): bursts, VOT/aspiration, voicebar."""
    def P(i: int) -> Parameter:
        return st.param[i]

    bdur = burdr(st.phcur)
    if (feacur & FBURST) != 0:
        bdur = mstofr(bdur)
        if (feanex & (FNASAL | FPLOSV)) != 0:
            # UK: never release a plosive-into-nasal/plosive; the nasal has no
            # place, so the homorganic test adds a MASKFRONT "both up front" test.
            if (feacur & FPLOSV) != 0:
                bdur = 0
            if ((place(st.phcur) | MASKFRONT) == (place(st.phonex) | MASKFRONT)):
                bdur = 0
            elif place(st.phcur) == place(st.phonex):
                bdur = 0
        if bdur > 1:
            if (feacur & FPLOSV) != 0 and (feanex & FOBST) != 0:
                bdur -= 1
            elif st.durfon < NF50MS:
                bdur -= 1
        closure_dur = st.durfon - bdur
        if st.phcur in (UKP_CH, UKP_JH):
            if closure_dur > NF80MS:
                closure_dur = NF80MS
        # The per-place PAREAL/PAREAB writes target param[18]/param[17], never
        # read by the OLD-VTM draw stage -- inert, not modelled.
        for i in range(PA2, PAB + 1):
            P(i).tspesh = closure_dur
            P(i).pspesh = 0
    vot = 0
    if ((fealas & FPLOSV) != 0 and (fealas & FVOICD) == 0 and (feacur & FSONOR) != 0):
        P(PAP).pspesh = 52
        if begtyp(st.phcur) != 1:
            P(PAP).pspesh = 54
        P(PAV).pspesh = 0
        vot = NF40MS
        if (struccur & FSTRESS_1) == 0:
            vot = NF25MS
            P(PAP).pspesh -= 3
        if (feacur & FSONCON) != 0 or st.phcur == UKP_RR:
            P(PAP).pspesh += 3
        if phone_feature(st.get_phone(st.nphone - 2)) == (FOBST + FCONSON):
            if (struclm2 & FBOUNDARY) == 0:
                vot = NF15MS
        elif (feacur & FSYLL) == 0:
            vot += NF20MS
        if vot >= st.durfon:
            vot = st.durfon - 1
            P(PAP).pspesh = 0
        if (vot > (st.durfon >> 1) and (feacur & FSYLL) != 0
                and (struccur & FSTRESS_1) != 0):
            vot = st.durfon >> 1
        # UK omits the US dummy-vowel VOT override here.
        P(PAV).tspesh = vot
        P(PAP).tspesh = vot
        P(PB1).tspesh = vot
        P(PB2).tspesh = vot
        P(PB1).pspesh = s16(P(PB1).tarcur + 250)
        P(PB2).pspesh = s16(P(PB2).tarcur + 70)
    if ((feacur & FBURST) != 0 and (feacur & FVOICD) != 0 and (fealas & FVOICD) != 0
            and (feanex & FVOICD) == 0 and st.phcur != UKP_TX):
        P(PAV).tspesh = st.durfon - NF15MS
        P(PB1).tspesh = st.durfon
        P(PB2).tspesh = st.durfon
        P(PB3).tspesh = st.durfon
        P(PAV).pspesh = 63
        P(PB1).pspesh = 1000
        P(PB2).pspesh = 1000
        P(PB3).pspesh = 1500
        if st.phcur == UKP_JH:
            P(PAV).pspesh = 50
            P(PAP).pspesh = 50
            P(PB1).pspesh = 500
            P(PB2).pspesh = 500
            P(PB3).pspesh = 800


def init_variables(st: PhsettarState):
    """`init_variables` (`ph_setar.c:1800`): set per-phone context and defaults."""
    struclm2 = 0
    if st.nphone == 0:
        pholas = GEN_SIL
        struclas = 0
        if st.initsw == 0:
            st.initsw += 1
            for i in range(NPARAM):
                st.np = i
                st.par_type = PARTYP[i]
                st.param[i].tarend = getbegtar(st, 0)
    else:
        if st.nphone > 1:
            struclm2 = st.allofeats[st.nphone - 2]
        pholas = st.phcur
        struclas = st.allofeats[st.nphone - 1]
    st.phcur = st.allophons[st.nphone]
    struccur = st.allofeats[st.nphone]
    if st.nphone < (st.nallotot - 2):
        st.phonex = st.allophons[st.nphone + 1]
        strucnex = st.allofeats[st.nphone + 1]
    else:
        st.phonex = GEN_SIL
        strucnex = 0
    fealas = phone_feature(pholas)
    feacur = phone_feature(st.phcur)
    feanex = phone_feature(st.phonex)
    inhdr_frames = mstofr(inh_timing(st.phcur))
    if (feacur & FOBST) == 0 and st.phcur != GEN_SIL:
        from .phsettar import FRAC_HALF, FRAC_ONE
        if st.durfon < (inhdr_frames << 1):
            st.shrink = muldv(FRAC_ONE, st.durfon, inhdr_frames)
        else:
            st.shrink = FRAC_ONE + (FRAC_ONE - 1)
        st.shrif = (st.shrink >> 1) + FRAC_HALF
        st.shrib = st.shrif - 1600
    for i in (PAV, PAP, PF1, PB1, PB2, PB3, PA2, PA3, PA6 - 2, PA6 - 1, PA6, PAB, PTILT):
        st.param[i].tspesh = 0
    return (inhdr_frames, pholas, fealas, feacur, feanex, struclm2, struclas,
            struccur, strucnex)


def phsettar_uk(st: PhsettarState) -> None:
    """`phsettar` (`ph_setar.c:600`) for the UK font: one phone's target setup."""
    st.param[PAV].tspesh = 0
    st.param[PAB].tspesh = 0
    (inhdr_frames, pholas, fealas, feacur, feanex, struclm2, struclas,
     struccur, strucnex) = init_variables(st)
    if st.phcur == GEN_SIL:
        st.breathysw = 0
    if (struccur & FSENTENDS) != 0:
        st.breathysw = 1
    st.ndips_ptr = 1
    uk_phone = _is_uk(st.phcur)

    for npar in range(NPARAM):
        st.np = npar
        st.par_type = PARTYP[npar]
        q = st.param[npar]
        q.tarlas = q.tarend
        q.tarnex = getbegtar(st, st.nphone + 1)
        if q.tarnex == 4:
            q.tarnex += 1
        q.tarcur = gettar(st, st.nphone)
        q.dipcum = 0
        if q.tarcur < -1:
            make_dip(st, -q.tarcur, inhdr_frames, st.shrink)
        else:
            q.deldip = 0
            q.durlin = st.durfon
            if st.par_type == IS_FORM_FREQ:
                st.gencoartic = 0
                if (struccur & FSTRESS) == 0:
                    st.gencoartic = N15PRCNT
                    if npar == PF2:
                        st.gencoartic = N25PRCNT
                arg1 = ((q.tarlas + q.tarnex) >> 1) - q.tarcur
                q.tarcur = s16(q.tarcur + mlsh1(arg1, st.gencoartic))
            q.tarend = q.tarcur
        if st.par_type == IS_FORM_FREQ:
            arg1 = q.tarend - q.tarnex
            q.tarnex = s16(q.tarnex + mlsh1(arg1, N10PRCNT))

        st.bouval = (q.tarlas + q.tarcur) >> 1
        st.durtran = NF30MS
        # `phsettar` dispatches the smooth rules by the current phone's font
        # (`ph_setar.c:1016`): a UK phone runs the UK rules, the boundary
        # `GEN_SIL` (US font) runs the US rules.
        if uk_phone:
            uk_forw_smooth_rules(st, pholas, fealas, feacur, struclas, struccur, feanex)
        else:
            us_forw_smooth_rules(st, pholas, fealas, feacur, struclas, struccur, feanex)
        q.ftran = 0
        if st.durtran > 0:
            q.ftran = s16((st.bouval - q.tarcur) << 3)
            if q.ftran != 0:
                q.dftran = mlsh1(q.ftran, DIVTAB[st.durtran])
                q.ftran = s16(q.dftran * st.durtran)
        if npar == PF2:
            st.fvvtran = 0
            st.dfvvtran = 0
            if st.vvdurtran > st.durfon:
                st.vvdurtran = st.durfon
            if st.vvdurtran > 0 and st.vvbouval != 0:
                arg1 = st.vvbouval << 3
                st.dfvvtran = mlsh1(arg1, DIVTAB[st.vvdurtran])
                st.fvvtran = st.dfvvtran * st.vvdurtran
            st.vvdurtran = 0
            st.vvbouval = 0

        st.bouval = (q.tarend + q.tarnex) >> 1
        st.durtran = NF25MS
        if uk_phone:
            uk_back_smooth_rules(st, feacur, feanex, strucnex)
        else:
            us_back_smooth_rules(st, feacur, feanex, strucnex)
        q.btran = 0
        q.dbtran = 0
        if st.durtran > 0:
            temp = s16((st.bouval - q.tarend) << 3)
            if temp != 0:
                q.dbtran = mlsh1(temp, DIVTAB[st.durtran])
        if npar == PF2:
            st.bvvtran = 0
            st.dbvvtran = 0
            st.tvvbacktr = st.durfon
            if st.vvdurtran > st.durfon:
                st.vvdurtran = st.durfon
            if st.vvdurtran > 0 and st.vvbouval != 0:
                st.tvvbacktr = st.durfon - st.vvdurtran
                arg1 = st.vvbouval << 3
                st.dbvvtran = mlsh1(arg1, DIVTAB[st.vvdurtran])
            st.vvdurtran = 0
            st.vvbouval = 0

    if uk_phone:
        uk_special_rules(st, fealas, feacur, feanex, struclm2, struccur, pholas, struclas)
    else:
        us_special_rules(st, fealas, feacur, feanex, struclm2, struccur, pholas, struclas)
