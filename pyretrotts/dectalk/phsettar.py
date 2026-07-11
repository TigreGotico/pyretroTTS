"""DECtalk US-English transition setup (`phsettar`, the target-to-transition stage).

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/ph/ph_setar.c` `phsettar` and the US smooth-rule functions in
`src/dapi/src/ph/p_us_st0.c`, plus `setloc`/`vv_coartic_across_c`/`shrdur` from
`src/dapi/src/ph/ph_sttr2.c`), for the build where `ENGLISH_US`,
`OLD_INTONATION_AND_TIMING`, and `OLD_SETTAR` are defined and `GERMAN`,
`FRENCH`, `LRULES`, `RRULES`, `HLSYN`, `NEW_VTM` are not. FONIX Corporation
declares that source proprietary and confidential. This file is NOT covered by
this project's MIT licence. See NOTICE.

`phsettar` (`ph_setar.c:561`) runs once per phone. For each of the sixteen Klatt
parameters it resolves a start/end target through the target ROM (`gettar` ->
`us_gettar`, ported in `settar.py`), applies coarticulation and the
forward/backward/special smoothing rules, and writes the per-parameter
interpolation state (`tarcur`, `ftran`/`dftran`, `btran`/`dbtran`, `deldip`,
`tbacktr`, `tspesh`/`pspesh`, and the diphthong line in `ndip`) that `draw_frame`
(`ph.py`) then interpolates into `parstochip[]` each frame.

All arithmetic is the reference's fixed point: targets and transition state are C
`short`, so intermediates truncate to 16 bits (`s16`). `mlsh1(x,y)` is
`(x*y) >> 14` truncated to 16 bits; `muldv(x,y,z)` is a 32-bit `x*y/z` with C
truncation toward zero.

`vv_coartic_across_c` (`ph_sttr2.c:357`) has its body commented out in this
source, so the F2 vowel-vowel offsets (`vvbouval`/`vvdurtran` and thus
`fvvtran`/`bvvtran`) are always zero and `tvvbacktr` is `durfon`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .ph import PhParam
from .settar import (
    FEMALE,
    GEN_SIL,
    MALE,
    PARTYP,
    US_TOT_ALLOPHONES,
    Allophones,
    us_gettar,
)
from .targets import PARINI, US_FEATB, US_PLACE
from .targets_transitions import (
    DIVTAB,
    US_BURDR,
    US_FEMLOC,
    US_INHDR,
    US_MALELOC,
    US_PLOCU,
)
from .vtm import s16

# Parameter enum values are 1-based (`ph_defs.h:492-507`); the index used
# throughout is (enum - 1), matching `PARTYP`/`PARINI`.
PF1, PF2, PF3, PFZ = 0, 1, 2, 3
PB1, PB2, PB3 = 4, 5, 6
PAV, PAP, PA2, PA3 = 7, 8, 9, 10
PA6, PAB, PTILT = 13, 14, 15
NPARAM = 16

# `partyp` class codes (`p_us_st0.c`, IS_* macros).
IS_AV_OR_AH = 0
IS_NASAL_ZERO_FREQ = 1
IS_PARALLEL_FORM_AMP = 2
IS_FORM_FREQ = 3
IS_FORM_BW = 4

# begtyp/endtyp class codes (`ph_setar.c:125-129`).
FRONT_VOWEL = 1
BACK_ROUNDED_VOWEL = 3
OBSTRUENT = 4
ROUNDED_SONOR_CONS = 5

# Feature-bit masks (`ph_defs.h`, octal in C).
FSYLL = 0o1
FVOICD = 0o2
FVOWEL = 0o4
FSONOR = 0o20
FOBST = 0o40
FPLOSV = 0o100
FNASAL = 0o200
FCONSON = 0o400
FSONCON = 0o1000
FBURST = 0o4000
FDUMMY_VOWEL = 0o4000
FSTOP = 0o20000
FSTRESS = 0o3
FSTRESS_1 = 0o1
FBOUNDARY = 0o740
FVPNEXT = 0o240
FSENTENDS = 0o400
# `phonemes[SAFETY]` shares the `allophons[]` buffer with the allophone output
# (`ph_claus.c:597`); `phalloph` overwrites `allophons[0..nallotot-1]`, so slots
# at or past `nallotot` still hold the surviving input phonemes.
SAFETY = 8

# place() bits (`ph_defs.h:308-310`, plus F2BACK* used by us_gettar rules).
FDENTAL = 0o2
FPALATL = 0o4
FALVEL = 0o10
F2BACKI = 0o100
F2BACKF = 0o200

# Frame-count constants (`ph_defs.h:408-423`).
NF15MS, NF20MS, NF25MS, NF30MS, NF40MS = 2, 3, 4, 5, 6
NF45MS, NF50MS, NF60MS, NF64MS, NF70MS = 7, 8, 9, 10, 11
NF75MS, NF80MS, NF100MS, NF130MS = 12, 13, 16, 20

# Coarticulation percentages in Q14 (`ph_defs.h:436-439`).
N10PRCNT, N15PRCNT, N20PRCNT, N25PRCNT = 1638, 2457, 3277, 4096

FRAC_ONE = 16384
FRAC_HALF = 8192
NSAMP_FRAME = 71
PFONT = 0xFF00
PVALUE = 0x00FF
PFUSA = 0x1E
PSFONT = 8


def _usp(code: int) -> int:
    return (PFUSA << PSFONT) | code


(USP_IY, USP_IH, USP_EY, USP_EH, USP_AE, USP_AA, USP_AY, USP_AW, USP_AH,
 USP_AO, USP_OW, USP_OY, USP_UH, USP_UW, USP_RR, USP_YU, USP_AX, USP_IX,
 USP_IR, USP_ER, USP_AR, USP_OR, USP_UR, USP_W, USP_YX, USP_R, USP_LL,
 USP_HX, USP_RX, USP_LX, USP_M, USP_N, USP_NX, USP_EL, USP_DZ, USP_EN,
 USP_F, USP_V, USP_TH, USP_DH, USP_S, USP_Z, USP_SH, USP_ZH, USP_P, USP_B,
 USP_T, USP_D, USP_K, USP_G, USP_DX, USP_TX, USP_Q, USP_CH, USP_JH) = (
    _usp(i) for i in range(1, 56))


def _s32(x: int) -> int:
    x &= 0xFFFFFFFF
    return x - 0x100000000 if x >= 0x80000000 else x


def mlsh1(x: int, y: int) -> int:
    """`mlsh1(x,y) = (S16)((S32)(x*y) >> 14)` (`ph_defs.h:768`)."""
    return s16(_s32(_s32(x) * _s32(y)) >> 14)


def muldv(x: int, y: int, z: int) -> int:
    """`muldv(x,y,z) = (S32)x * (S32)y / (S32)z`, C truncation (`ph_defs.h:767`)."""
    p = _s32(_s32(x) * _s32(y))
    q = int(p / z)  # C integer division truncates toward zero.
    return q


def mstofr(nms: int) -> int:
    """`mstofr(nms) = (nms*10) >> 6` (`ph_task.c:1290`)."""
    return (_s32(nms) * 10) >> 6


@dataclass
class Parameter:
    """One Klatt parameter's `PARAMETER` state (`ph_defs.h:586`), mutated in place."""

    tarcur: int = 0
    tarlas: int = 0
    tarnex: int = 0
    tarend: int = 0
    durlin: int = 0
    deldip: int = 0
    dipcum: int = 0
    ftran: int = 0
    dftran: int = 0
    btran: int = 0
    dbtran: int = 0
    tbacktr: int = 0
    tspesh: int = 0
    pspesh: int = 0
    ndip_off: int = 0  # offset into the shared dipspec[] buffer; 0 == NULL


@dataclass
class PhsettarState:
    """Per-clause `phsettar` state: the input stream, the ROM, and the carried
    `PARAMETER` array plus the F2 vowel-vowel and breathy scalars."""

    allophons: tuple[int, ...]
    allofeats: tuple[int, ...]
    allodurs: tuple[int, ...]
    nallotot: int
    malfem: int
    # `gettar`'s USP_K test reads `allophons[]` raw (`ph_setar.c:2072`), so past
    # `nallotot` it sees whatever the shared `phonemes`/`allophons` buffer still
    # holds. `rawbuf` reconstructs that buffer: the `phsort` input phonemes, then
    # the `phalloph` output and its `GEN_SIL` terminator (`ph_aloph1.c:1538`),
    # then the post-`phinton` stream -- so a `phinton` insert overwrites the
    # terminator and re-exposes leftover input, matching the C exactly.
    rawbuf: tuple[int, ...] = ()
    param: list[Parameter] = field(default_factory=lambda: [Parameter() for _ in range(NPARAM)])
    nphone: int = 0
    durfon: int = 0
    phcur: int = 0
    phonex: int = GEN_SIL
    par_type: int = 0
    gencoartic: int = 0
    bouval: int = 0
    durtran: int = 0
    vvbouval: int = 0
    vvdurtran: int = 0
    nasvowel: int = 0
    initsw: int = 0
    breathysw: int = 0
    shrink: int = 0
    shrif: int = 0
    shrib: int = 0
    fvvtran: int = 0
    dfvvtran: int = 0
    tvvbacktr: int = 0
    bvvtran: int = 0
    dbvvtran: int = 0
    breathyah: int = 0
    breathytilt: int = 0
    # dipspec[] scratch buffer shared by all parameters; make_dip writes
    # (time, delta) pairs here and stores each parameter's start offset in
    # Parameter.ndip_off. Non-diphthong phones keep the previous offset, so a
    # parameter's ndip[0]/ndip[1] read whatever now sits at that offset -- the
    # C reads the same stale pointer.
    dipspec: list[int] = field(default_factory=lambda: [0] * 512)
    ndips_ptr: int = 1
    # parstochip[OUT_TLT] from the previous frame, read by the forward TILT rule
    # when phcur == GEN_SIL; supplied by the caller (captured from the oracle).
    prev_tilt: int = 0
    np: int = 0  # current parameter index inside the main loop

    def get_phone(self, n: int) -> int:
        if 0 <= n < self.nallotot:
            return self.allophons[n]
        return GEN_SIL

    def raw_allophon(self, n: int) -> int:
        """`allophons[n]` read raw (no `get_phone` clamp), as `gettar`'s USP_K
        test does (`ph_setar.c:2072`), from the reconstructed shared buffer."""
        if 0 <= n < len(self.rawbuf):
            return self.rawbuf[n]
        return 0

    def feat(self, n: int) -> int:
        if 0 <= n < len(self.allofeats):
            return self.allofeats[n]
        return 0

    def _stream(self) -> Allophones:
        return Allophones(self.allophons, self.allofeats, self.nallotot, self.malfem)


def build_rawbuf(
    phonemes: tuple[int, ...],
    nphonetot: int,
    alloph_ph: tuple[int, ...],
    allophons: tuple[int, ...],
    nallotot: int,
) -> tuple[int, ...]:
    """Reconstruct the shared `allophons[]`/`phonemes[]` buffer past `nallotot`.

    Mirrors the C: `init_phclause` zeroes it (`ph_claus.c:578`); `phsort` lays the
    input phonemes at `[SAFETY..]` with a `GEN_SIL` terminator; `phalloph`
    overwrites `[0..nallo_ph)` and writes its own `GEN_SIL` terminator at
    `nallo_ph` (`ph_aloph1.c:1538`); `phinton` inserts/deletes leave the final
    `[0..nallotot)` stream, so an insert past `nallo_ph` overwrites that
    terminator and re-exposes the untouched leftover input.
    """
    nallo_ph = len(alloph_ph)
    size = max(nallotot, nallo_ph, SAFETY + nphonetot) + 2
    buf = [0] * size
    for i in range(nphonetot):
        buf[SAFETY + i] = phonemes[i]
    buf[SAFETY + nphonetot] = GEN_SIL
    for j in range(nallo_ph):
        buf[j] = alloph_ph[j]
    buf[nallo_ph] = GEN_SIL
    for j in range(nallotot):
        buf[j] = allophons[j]
    return tuple(buf)


def phone_feature(phone: int) -> int:
    return US_FEATB[phone & 0xFF]


def begtyp(phone: int) -> int:
    from .settar import US_BEGTYP
    return US_BEGTYP[phone & 0xFF]


def endtyp(phone: int) -> int:
    from .settar import US_ENDTYP
    return US_ENDTYP[phone & 0xFF]


def ptram(phone: int) -> int:
    from .settar import US_PTRAM
    return US_PTRAM[phone & 0xFF]


def burdr(phone: int) -> int:
    return US_BURDR[phone & 0xFF]


def place(phone: int) -> int:
    return US_PLACE[phone & 0xFF]


def plocu(index: int) -> int:
    return US_PLOCU[index & 0xFF]


def inh_timing(phone: int) -> int:
    if (phone & PVALUE) >= 100:
        return 0
    return US_INHDR[phone & PVALUE]


def _loc_table(st: PhsettarState) -> tuple[int, ...]:
    return US_MALELOC if st.malfem == MALE else US_FEMLOC


def gettar(st: PhsettarState, phone: int) -> int:
    """`gettar` (`ph_setar.c:1879`): wrap `us_gettar` with the neighbour-fallback
    search and the /k/ F2/F3 raise, for the current parameter `st.np`."""
    stream = st._stream()
    index = (0, 1, 2, -1)
    count = 0
    while count <= 3:
        if index[count] == 2 and st.nallotot >= (phone + index[count] + 1):
            count += 1
        idx = index[count]
        tartemp = us_gettar(stream, st.np, phone + idx)
        if st.raw_allophon(phone + idx) == USP_K:
            if st.np == PF2:
                tartemp += 300
            elif st.np == PF3:
                tartemp += 500
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


def _diph(st: PhsettarState, i: int) -> int:
    from .settar import US_FEMDIP, US_MALDIP
    tbl = US_MALDIP if st.malfem == MALE else US_FEMDIP
    return tbl[i]


def us_special_coartic(st: PhsettarState, nfon: int, diphpos: int) -> int:
    """`us_special_coartic` (`p_us_st0.c:324`): vowel F2/F3 context shifts."""
    temp = 0
    foncur = st.get_phone(nfon)
    fonnex = st.get_phone(nfon + 1)
    fonlas = st.get_phone(nfon - 1)
    if st.np == PF3:
        if (phone_feature(foncur) & FVOWEL) != 0 and foncur != USP_RR:
            if (fonlas in (USP_W, USP_R, USP_RX)) or (fonnex in (USP_W, USP_R, USP_RX)):
                temp = -150
    if st.np == PF2:
        if fonnex == USP_LX:
            if (USP_IY <= foncur <= USP_AE) or foncur == USP_IX:
                temp = -150
            if foncur in (USP_AY, USP_OY) and diphpos == 1:
                temp = -250
            if foncur in (USP_AY, USP_OY) and diphpos > 1:
                temp = -350
        if fonlas in (USP_W, USP_LL, USP_LX):
            if (USP_IY <= foncur <= USP_AE) or foncur == USP_IX:
                temp = -150
        if foncur == USP_UW:
            if (place(fonlas) & FALVEL) != 0:
                temp = 200
        if foncur == USP_UW or (foncur == USP_YU and diphpos > 0):
            if (place(fonnex) & FALVEL) != 0:
                temp += 200
        if (st.feat(nfon) & FSTRESS) == 0:
            temp += temp >> 1
            if foncur == USP_YU and diphpos > 0:
                temp = 400
        elif (st.feat(nfon) & FBOUNDARY) >= FVPNEXT:
            temp = temp >> 1
        if temp > 400:
            temp = 400
        if temp < -400:
            temp = -400
    return temp


def getbegtar(st: PhsettarState, nfone: int) -> int:
    """`getbegtar` (`ph_setar.c:1293`).

    The C gates the coarticulation call on `nfone & PFONT` (`ph_setar.c:1312`),
    but `nfone` is a phone index, so that mask is zero and never matches
    `PFUSA<<PSFONT`: `us_special_coartic` is dead here and is not applied."""
    temp = gettar(st, nfone)
    if temp < -1:
        temp = _diph(st, -temp)
    return s16(temp)


def getendtar(st: PhsettarState, nfone: int) -> int:
    """`getendtar` (`ph_setar.c:1358`)."""
    temp = gettar(st, nfone)
    if temp < -1:
        t = -temp
        while _diph(st, t) != -1:
            t += 1
        temp = _diph(st, t - 1)
        if st.par_type == IS_FORM_FREQ:
            temp += us_special_coartic(st, nfone, 0)
    return s16(temp)


def shrdur(st: PhsettarState, durin: int, inhdr_frames: int, shrink: int) -> int:
    """`shrdur` (`ph_sttr2.c:406`): nonlinear diphthong-time shrink/expand."""
    durin = (durin * 10) + 5
    localinhdr = inhdr_frames * NSAMP_FRAME
    halfinhdr = (inhdr_frames * NSAMP_FRAME) >> 1
    halfmaxdur = mlsh1(halfinhdr, shrink)
    foldswitch = 0
    if durin > halfinhdr:
        durin = localinhdr - durin
        foldswitch = 1
    durin = halfinhdr - durin
    durin = mlsh1(((shrink & 0xFFFFFFFF) + FRAC_ONE) >> 1, durin)
    if durin > halfmaxdur:
        durin = halfmaxdur
    durin = halfmaxdur - durin
    if foldswitch == 1:
        durin = halfmaxdur + halfmaxdur - durin
    if durin < NSAMP_FRAME:
        durin = NSAMP_FRAME
    return durin >> 6


def make_dip(st: PhsettarState, pdip: int, inhdr_frames: int, shrink: int) -> None:
    """`make_dip` (`ph_setar.c:1429`): generate a diphthong's straight-line segments."""
    q = st.param[st.np]
    q.ndip_off = st.ndips_ptr
    oldvalue = _diph(st, pdip)
    if st.par_type == IS_FORM_FREQ:
        st.gencoartic = N10PRCNT
        if (st.feat(st.nphone) & FSTRESS) == 0:  # struccur unstressed
            st.gencoartic = N15PRCNT
            if st.np == PF2:
                st.gencoartic = N25PRCNT
        oldvalue += mlsh1(q.tarlas - oldvalue, st.gencoartic)
        oldvalue += us_special_coartic(st, st.nphone, 0)
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
                # The C gates this call on `nphone & PFONT` (`ph_setar.c:1528`),
                # a phone index, so the mask is zero and it is not applied here
                # (unlike the first-value call above, which uses the phone code).
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
    # `np->durlin = *np->ndip++; np->deldip = *np->ndip++;` leaves ndip advanced
    # by two, so the persisted pointer (and the frame drawer's ndip0/ndip1) reads
    # the second segment.
    q.durlin = st.dipspec[q.ndip_off]
    q.deldip = st.dipspec[q.ndip_off + 1]
    q.ndip_off += 2


def setloc(st: PhsettarState, nfonobst: int, nfonsonor: int, initfinso: str,
           nfonvowel: int) -> int:
    """`setloc` (`ph_sttr2.c:69`): obstruent<->sonorant formant locus transition.

    Sets `bouval`/`durtran` from the locus ROM; returns 1 on success. The
    vowel-vowel branch is inert here (`vv_coartic_across_c` body is commented out)."""
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
    ploc = plocu(fonobst + (US_TOT_ALLOPHONES * (sontyx - 1)))
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
        # vv_coartic_across_c leaves vvbouval == 0, so curval is unchanged.
        st.vvbouval = 0
        st.vvdurtran = 0
        delta_freq = muldv(prcnt, curval - locus, 100)
        st.bouval = s16(locus + delta_freq)
    return 1


def us_forw_smooth_rules(st: PhsettarState, pholas: int, fealas: int, feacur: int,
                         struclas: int, struccur: int, feanex: int) -> None:
    """`us_forw_smooth_rules` (`p_us_st0.c:440`)."""
    q = st.param[st.np]
    pt = st.par_type
    if pt == IS_FORM_FREQ:
        if (feacur & FSONOR) != 0:
            if (feacur & FSONCON) == 0:
                st.durtran = NF45MS
                if (fealas & FSONCON) != 0:
                    st.bouval = (st.bouval + q.tarlas) >> 1
                    if pholas == USP_LL and st.np == PF1:
                        st.bouval += 80
                    if pholas == USP_R and st.np != PF1:
                        st.durtran = NF70MS
                else:
                    if st.phcur == USP_HX:
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
                elif ((st.phcur in (USP_N, USP_EN)) and endtyp(pholas) == 1):
                    if st.np == PF2:
                        st.bouval -= 100
                        if (place(pholas) & F2BACKF) != 0:
                            st.bouval -= 100
                    if st.np == PF3:
                        st.bouval -= 100
                elif (st.np == PF2 and st.phcur == USP_M
                        and (place(pholas) & F2BACKF) != 0):
                    st.bouval -= 150
        if ((feacur & FOBST) == 0 and endtyp(pholas) != OBSTRUENT and st.durtran > 0):
            st.durtran = mlsh1(st.durtran, st.shrif) + 1
    elif pt == IS_NASAL_ZERO_FREQ:
        st.durtran = 0
        if (fealas & FNASAL) != 0 and (feacur & FNASAL) == 0:
            st.bouval = 400
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
        if st.nasvowel:
            st.bouval -= 20
        if (fealas & FNASAL) != 0:
            st.bouval = q.tarcur
            if (st.np == PB2 and pholas in (USP_N, USP_EN)
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
        if (st.bouval < temp) or ((fealas & FPLOSV) != 0) or (pholas == USP_JH):
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
            if st.phcur in (USP_CH, USP_JH):
                st.durtran = st.durfon - NF15MS
                st.bouval = q.tarcur - 30
        if st.np == PAP:
            if st.phcur in (GEN_SIL, USP_F, USP_TH, USP_S, USP_SH):
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
    # Final clamps apply to every parameter type (`p_us_st0.c:799-807`).
    if st.durtran > st.durfon:
        st.durtran = st.durfon
    if st.durtran > NF130MS:
        st.durtran = NF130MS
    if st.bouval < 0:
        st.bouval = 0


def us_back_smooth_rules(st: PhsettarState, feacur: int, feanex: int,
                         strucnex: int) -> None:
    """`us_back_smooth_rules` (`p_us_st0.c:830`)."""
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
                    if st.phonex == USP_LL and st.np == PF1:
                        st.bouval += 80
                else:
                    if st.phonex == USP_HX:
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
                elif (st.phcur in (USP_N, USP_EN)) and begtyp(st.phonex) == 1:
                    if st.np == PF2:
                        st.bouval -= 100
                        if (place(st.phonex) & F2BACKI) != 0:
                            st.bouval -= 100
                    if st.np == PF3:
                        st.bouval -= 100
                elif (st.np == PF2 and st.phcur == USP_M
                        and (place(st.phonex) & F2BACKI) != 0):
                    st.bouval -= 150
        if ((feacur & FOBST) == 0 and begtyp(st.phonex) != 4 and st.durtran > 0):
            st.durtran = mlsh1(st.durtran, st.shrib) + 1
    elif pt == IS_NASAL_ZERO_FREQ:
        st.durtran = 0
        if (feanex & FNASAL) != 0 and (feacur & FNASAL) == 0:
            st.bouval = 400
            st.durtran = NF80MS
            if st.phonex == USP_EN:
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
            if (st.np == PB2 and st.phonex in (USP_N, USP_EN)
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
                and st.phcur not in (USP_V, USP_DH, USP_JH, USP_ZH, USP_Z)):
            st.durtran = 0
            if (feacur & FPLOSV) != 0 or st.phcur == USP_CH:
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
            if st.phcur >= USP_P:
                st.durtran = NF15MS
                if st.phcur < USP_CH:
                    temp = q.tarend
            if st.bouval < temp:
                st.bouval = temp - 3
                st.durtran = NF20MS
            if st.np == PAV:
                if (st.bouval < temp) or (temp > 0 and (strucnex & FDUMMY_VOWEL) != 0):
                    st.bouval = temp + 3
                    if st.phonex == GEN_SIL or (strucnex & FDUMMY_VOWEL) != 0:
                        st.durtran = NF75MS
                # The C's `else if (np == PAP)` here is nested inside `if (np ==
                # PAV)` (`p_us_st0.c:1133`), so it is unreachable dead code and
                # PAP.tarend - 6 is never assigned.
            if ((st.phonex >= USP_P)
                    and (((feacur & FNASAL) == 0) or (st.np != PAV))):
                st.durtran = 0
            if st.np == PAP:
                if st.phcur in (USP_F, USP_TH, USP_S, USP_SH):
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


def us_special_rules(st: PhsettarState, fealas: int, feacur: int, feanex: int,
                     struclm2: int, struccur: int, pholas: int, struclas: int) -> None:
    """`us_special_rules` (`p_us_st0.c:1234`): bursts, VOT/aspiration, voicebar."""
    def P(i: int) -> Parameter:
        return st.param[i]

    bdur = burdr(st.phcur)
    if (feacur & FBURST) != 0:
        bdur = mstofr(bdur)
        if (feanex & (FNASAL | FPLOSV)) != 0:
            if place(st.phcur) == place(st.phonex):
                bdur = 0
        if bdur > 1:
            if (feacur & FPLOSV) != 0 and (feanex & FOBST) != 0:
                bdur -= 1
            elif st.durfon < NF50MS:
                bdur -= 1
        closure_dur = st.durfon - bdur
        if st.phcur in (USP_CH, USP_JH):
            if closure_dur > NF80MS:
                closure_dur = NF80MS
        for i in range(PA2, PAB + 1):
            P(i).tspesh = closure_dur
            P(i).pspesh = 0
    vot = 0
    if ((fealas & FPLOSV) != 0 and (fealas & FVOICD) == 0 and (feacur & FSONOR) != 0):
        P(PAP).pspesh = 57
        if begtyp(st.phonex) != 1:
            P(PAP).pspesh = 61
        P(PAV).pspesh = 0
        vot = NF40MS
        if (struccur & FSTRESS_1) == 0:
            vot = NF25MS
            P(PAP).pspesh -= 3
        if (feacur & FSONCON) != 0 or st.phcur == USP_RR:
            P(PAP).pspesh += 3
        if phone_feature(st.get_phone(st.nphone - 2)) == (FOBST + FCONSON):
            if (struclm2 & FBOUNDARY) == 0:
                vot = NF15MS
        elif (feacur & FSYLL) == 0:
            vot += NF20MS
        if vot >= st.durfon:
            vot = st.durfon - 1
        if (vot > (st.durfon >> 1) and (feacur & FSYLL) != 0
                and (struccur & FSTRESS_1) != 0):
            vot = st.durfon >> 1
        if (struccur & FDUMMY_VOWEL) != 0:
            vot = st.durfon
            P(PAP).pspesh -= 3
        P(PAV).tspesh = vot
        P(PAP).tspesh = vot
        P(PB1).tspesh = vot
        P(PB2).tspesh = vot
        P(PB1).pspesh = s16(P(PB1).tarcur + 250)
        P(PB2).pspesh = s16(P(PB2).tarcur + 70)
    if ((feacur & FBURST) != 0 and (feacur & FVOICD) != 0 and (fealas & FVOICD) != 0
            and (feanex & FVOICD) == 0 and st.phcur != USP_TX):
        P(PAV).tspesh = st.durfon - NF15MS
        P(PB1).tspesh = st.durfon
        P(PB2).tspesh = st.durfon
        P(PB3).tspesh = st.durfon
        P(PAV).pspesh = 63
        P(PB1).pspesh = 1000
        P(PB2).pspesh = 1000
        P(PB3).pspesh = 1500


def init_variables(st: PhsettarState):
    """`init_variables` (`ph_setar.c:1764`): set per-phone context and defaults.

    Returns (inhdr_frames, pholas, fealas, feacur, feanex, struclm2, struclas,
    struccur, strucnex)."""
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


def phsettar(st: PhsettarState) -> None:
    """`phsettar` (`ph_setar.c:561`): one phone's worth of target + transition setup."""
    st.param[PAV].tspesh = 0
    st.param[PAB].tspesh = 0
    (inhdr_frames, pholas, fealas, feacur, feanex, struclm2, struclas,
     struccur, strucnex) = init_variables(st)
    if st.phcur == GEN_SIL:
        st.breathysw = 0
    if (struccur & FSENTENDS) != 0:
        st.breathysw = 1
    st.ndips_ptr = 1  # `*ppsNdips = &dipspec[1]` each phone (`ph_setar.c:1825`).

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
        # Rule 6: approx general coartic of tarnex with tarend.
        if st.par_type == IS_FORM_FREQ:
            arg1 = q.tarend - q.tarnex
            q.tarnex = s16(q.tarnex + mlsh1(arg1, N10PRCNT))

        # Rule 7: forward smoothing.
        st.bouval = (q.tarlas + q.tarcur) >> 1
        st.durtran = NF30MS
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

        # Rule 8: backward smoothing.
        st.bouval = (q.tarend + q.tarnex) >> 1
        st.durtran = NF25MS
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

    # Rule 9: special rules that override computed values.
    us_special_rules(st, fealas, feacur, feanex, struclm2, struccur, pholas, struclas)


def to_draw_params(st: PhsettarState) -> tuple[PhParam, ...]:
    """Snapshot the sixteen `PARAMETER` states as `ph.PhParam` for `draw_frame`."""
    out = []
    for q in st.param:
        ndip0 = st.dipspec[q.ndip_off] if q.ndip_off else 0
        ndip1 = st.dipspec[q.ndip_off + 1] if q.ndip_off else 0
        out.append(PhParam(
            tarcur=q.tarcur, durlin=q.durlin, deldip=q.deldip, dipcum=q.dipcum,
            ftran=q.ftran, dftran=q.dftran, btran=q.btran, dbtran=q.dbtran,
            tbacktr=q.tbacktr, tspesh=q.tspesh, pspesh=q.pspesh,
            ndip0=ndip0, ndip1=ndip1))
    return tuple(out)
