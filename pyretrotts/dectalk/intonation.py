"""DECtalk US-English F0/intonation stage (`phinton` + `pht0draw`).

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/ph/ph_inton0.c` `phinton`/`make_f0_command`, and
`src/dapi/src/ph/ph_drwt01.c` `pht0draw` with its helpers `set_user_target`,
`set_tglst`, `filter_commands`, `linear_interp`), for the build where
`ENGLISH_US` and `OLD_INTONATION_AND_TIMING` are defined and `NWSNOAA`,
`ENGLISH_UK`, `GERMAN`, `FRENCH`, `SPANISH`, `HLSYN`, and `F0_QBOUND_PULSE` are
not. FONIX Corporation declares that source proprietary and confidential. This
file is NOT covered by this project's MIT licence. See NOTICE.

`phinton` (`ph_inton0.c:1325`) runs once per clause, after `us_phtiming`. It
walks the allophone/structure/duration stream and, at each syllabic phone and
each clause boundary, emits F0 commands into two parallel arrays: `f0tar[]` (the
target, in Hz*10 plus rule-encoded flags) and `f0tim[]` (frames since the
previous command). It also inserts an extra reduced vowel (`AX`/`IX`) after a
final plosive, so its output stream is longer than its input.

`pht0draw` (`ph_drwt01.c:277`) runs once per output frame. It consumes the F0
command stream and the post-`phinton` allophone/duration stream to draw the
per-frame fundamental `f0prime`, then writes the period `parstochip[OUT_T0] =
400 * 1000 / f0prime` the vocal tract model uses. The hat/impulse/segment
targets are summed and passed through a two-pole low-pass filter
(`filter_commands`), a glottalization dip is applied (`set_tglst`), the value is
scaled to the speaker's range, and a pseudo-jitter is added.

All arithmetic is the reference's fixed point: every intermediate is a C `short`
(width-truncated with `s16`), the target/assertiveness products use `muldv`
(32-bit `x*y/z`, C truncation) and the filter taps use `mlsh1` (`(x*y) >> 14`
truncated to 16 bits), both shared with `phsettar.py`.

`NORMAL`/`HAT_LOCATIONS_SPECIFIED` (`f0mode` 1) is the rule-generated default for
plain text. `HAT_F0_SIZES_SPECIFIED` (3), `SINGING` (4), and
`PHONE_TARGETS_SPECIFIED` (5) are the user-markup modes (slash/backslash, sung
notes, per-phone targets); their `phinton` branches are reproduced, but the
`mstofr` millisecond-to-frame conversion they alone reach is left unresolved
(see `_mstofr`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .phsettar import muldv
from .settar import _phone_feature
from .targets import US_PLACE
from .vtm import s16, s32

# `ph_defs.h:710-716`: f0mode values.
NORMAL = 1
HAT_LOCATIONS_SPECIFIED = 2
HAT_F0_SIZES_SPECIFIED = 3
SINGING = 4
PHONE_TARGETS_SPECIFIED = 5

# Sentinel silence phone (`GEN_SIL`, `l_com_ph.h`): (0x1E<<8) | 0.
GEN_SIL = 0x01E00

# Feature bit read by `phinton`/`set_tglst` (`ph_defs.h`): FSYLL, FVOICD, FVOWEL,
# FPLOSV, FSONCON, FSON2 are the ones this stage tests.
FSYLL = 0o1
FVOICD = 0o2
FVOWEL = 0o4
FPLOSV = 0o100
FSONCON = 0o1000
FSON2 = 0o2000

# Structure bits in `allofeats` (`ph_defs.h:190-296`).
FHATBEG = 0o1000  # struccur & 01000: a hat rise begins here.
FHATEND = 0o2000  # struccur & 02000: a hat fall ends here.
FSENTENDS = 0o400
FBOUNDARY = 0o740
FCBNEXT = 0o340
FVPNEXT = 0o240
FPPNEXT = 0o200
FMBNEXT = 0o100
# `struccur & 0740 == 0440`: sentence-final continuation-rise boundary.
FSENTRISE = 0o440
FINSERTED = 0o4000  # struccur | 004000: the inserted-vowel marker phinton sets.

# `p_us_rom_dectalk_1996m_43f.c:803`: F0 rise as f(stress-level), Hz*10 (order:
# unstressed, primary, secondary, emphasis).
US_F0_STRESS_LEVEL: tuple[int, ...] = (1, 71, 31, 281)

# `p_us_rom_dectalk_1996m_43f.c:795`: F0 rise as f(phrase position), Hz*10.
US_F0_PHRASE_POSITION: tuple[int, ...] = (210, 90, 60, 40, 0)

# `p_us_rom_dectalk_1996m_43f.c:276`: per-phone F0 segment perturbation target,
# Hz*10, indexed by phone & 0xFF (57 phones).
US_F0SEGTARS: tuple[int, ...] = (
    50, 100, 60, 40, 20, 0, 0, 0, 0, 20,
    0, 30, 50, 60, 100, 50, 100, 30, 60, 100,
    60, 0, 30, 80, 60, 60, 0, 0, 200, 0,
    0, -50, -50, -50, 0, -50, -50, 300, -50, 300,
    -50, 300, -50, 300, -50, 300, -50, 300, -50, 300,
    -50, -10, 0, 0, 300, -50, -10,
)

# `p_us_rom_dectalk_1996m_43f.c:813`: note frequency (period-domain) table for the
# SINGING/user-note modes, indexed by (command - 1), 37 entries.
NOTETAB: tuple[int, ...] = (
    640, 678, 718, 761, 806, 854, 905, 959, 1016, 1076,
    1140, 1208, 1280, 1356, 1437, 1522, 1613, 1709, 1810, 1918,
    2032, 2152, 2280, 2416, 2560, 2712, 2874, 3044, 3226, 3418,
    3620, 3836, 4064, 4304, 4560, 4832, 5120,
)

# `p_us_rom_dectalk_1996m_43f.c:1289`: quarter-cosine jitter table, 64 entries.
GETCOSINE: tuple[int, ...] = (
    164, 163, 161, 158, 154, 148, 141, 132,
    123, 112, 100, 86, 72, 56, 38, 20,
    0, -20, -38, -56, -72, -86, -100, -112,
    -123, -132, -141, -148, -154, -158, -161, -163,
    -164, -163, -161, -158, -154, -148, -141, -132,
    -123, -112, -100, -86, -72, -56, -38, -20,
    0, 20, 38, 56, 72, 86, 100, 112,
    123, 132, 141, 148, 154, 158, 161, 163,
)

# `us_place` place-of-articulation table (`targets.US_PLACE`); bit 0o40 marks a
# phone that always forces a glottalization dip in `set_tglst`.
US_PLACE = US_PLACE


def _mstofr(nms: int) -> int:
    """`mstofr` (`ph_prot.h:156`): milliseconds to 6.4 ms frames.

    Reached only from `phinton`'s `HAT_F0_SIZES_SPECIFIED`/`PHONE_TARGETS_SPECIFIED`
    user branches (slash/backslash markup, per-phone `user_offset`). The definition is not
    in the ported translation units; plain text never reaches it. Raised rather
    than silently approximated so a user-mode capture cannot pass unproven.
    """
    raise NotImplementedError("mstofr is unresolved; user-f0 modes are not ported")


@dataclass
class IntonState:
    """The `pDph_t`/`pDphsettar` fields `phinton` reads and writes for one clause.

    `allophons`/`allofeats`/`allodurs`/`user_f0` are the post-`us_phtiming` stream
    (mutable lists: `phinton` inserts a reduced vowel after a final plosive). The
    outputs are `f0tar`/`f0tim`/`nf0tot`.
    """

    allophons: list[int]
    allofeats: list[int]
    allodurs: list[int]
    nallotot: int
    user_f0: list[int]
    user_offset: list[int]
    f0mode: int
    cbsymbol: int
    size_hat_rise: int
    scale_str_rise: int
    assertiveness: int
    # Outputs.
    f0tar: list[int] = field(default_factory=list)
    f0tim: list[int] = field(default_factory=list)
    nf0tot: int = 0


def _make_f0_command(st: IntonState, tar: int, delay: int, cumdur: int) -> int:
    """`make_f0_command` (`ph_inton0.c:2049`): append one F0 command, return the
    updated `cumdur` (the C passes it by pointer)."""
    if (delay + cumdur) < 0:
        delay = -cumdur
    st.f0tim.append(s16(cumdur + delay))
    st.f0tar.append(s16(tar))
    cumdur = s16(-delay)
    if st.nf0tot < 300 - 1:
        st.nf0tot += 1
    return cumdur


def phinton(st: IntonState) -> None:
    """Reproduce `phinton` (`ph_inton0.c:1325`) for the compiled US path.

    Fills `st.f0tar`/`st.f0tim`/`st.nf0tot` and may lengthen the allophone stream
    (the inserted reduced vowel after a final plosive). Handles f0mode NORMAL (the
    default, rule-generated). The user modes' `mstofr` calls raise (`_mstofr`).
    """
    nrises_sofar = 0
    hatsize = 0
    hat_loc_re_baseline = 0
    had_hatbegin = 0
    had_hatend = 0
    st.nf0tot = 0
    st.f0tar = []
    st.f0tim = []
    mf0 = 0
    inputscrewup = 0
    cumdur = 0

    nphon = 0
    while nphon < st.nallotot:
        if nphon > 0:
            pholas = st.allophons[nphon - 1]
            struclas = st.allofeats[nphon - 1]
        else:
            pholas = GEN_SIL
            struclas = 0
        phocur = st.allophons[nphon]
        struccur = st.allofeats[nphon]
        stresscur = struccur & 0o3
        feacur = _phone_feature(phocur)
        if nphon < (st.nallotot - 1):
            phonex = st.allophons[nphon + 1]
        else:
            phonex = 0

        if st.f0mode in (SINGING, PHONE_TARGETS_SPECIFIED):
            if st.user_f0[nphon] != 0:
                cumdur = _make_f0_command(
                    st, s16(2000 + st.user_f0[nphon]), 0, cumdur)
            skiprules = True
        else:
            skiprules = False

        if not skiprules:
            if (struccur & FHATBEG) != 0:
                had_hatbegin = 1
            if (struccur & FHATEND) != 0:
                had_hatend = 1

            if st.f0mode in (NORMAL, HAT_F0_SIZES_SPECIFIED):
                if (feacur & FSYLL) != 0:
                    delayf0 = 0
                    if had_hatbegin:
                        had_hatbegin = 0
                        delayf0 += 1
                        if st.f0mode == NORMAL:
                            hatsize = st.size_hat_rise
                            if st.cbsymbol:
                                hatsize >>= 1
                            hatsize &= 0o37776
                            hatsize |= 0o2
                            delayf0 = 0
                            if (struccur & FHATEND) != 0:
                                delayf0 = -13
                            cumdur = _make_f0_command(st, hatsize, delayf0, cumdur)
                        elif st.f0mode == HAT_F0_SIZES_SPECIFIED:
                            hatsize = ((st.user_f0[mf0] - 200) * 10) + 2
                            if hatsize >= 2000 or hatsize <= 0 or inputscrewup == 1:
                                hatsize = 2
                                inputscrewup = 1
                            delayf0 = _mstofr(st.user_offset[mf0])
                            mf0 += 1
                            cumdur = _make_f0_command(st, hatsize, delayf0, cumdur)
                        hat_loc_re_baseline = s16(hat_loc_re_baseline + hatsize)

                    targf0 = 0
                    if (stresscur & 0o1) != 0:
                        targf0 = s16(
                            US_F0_STRESS_LEVEL[stresscur]
                            + US_F0_PHRASE_POSITION[nrises_sofar])
                        if st.cbsymbol:
                            targf0 >>= 1
                        delayf0 = st.allodurs[nphon] >> 2
                        if (struccur & FHATEND) != 0 or (struccur & FSENTENDS) != 0:
                            delayf0 = -9
                        if stresscur == 0o3:
                            delayf0 = 0
                        if st.f0mode == HAT_F0_SIZES_SPECIFIED:
                            targf0 = ((st.user_f0[mf0] - 1000) * 10) + 1
                            if targf0 >= 2000 or targf0 <= 0 or inputscrewup == 1:
                                targf0 = 1
                                inputscrewup = 1
                            delayf0 = _mstofr(st.user_offset[mf0])
                            mf0 += 1
                        arg1 = st.scale_str_rise
                        if stresscur == 0o3 and arg1 < 16:
                            arg1 = 16
                        targf0 = s16(muldv(arg1, targf0, 32))
                        targf0 |= 0o1
                        cumdur = _make_f0_command(st, targf0, delayf0, cumdur)
                        if nrises_sofar < 4:
                            nrises_sofar += 1

                    if had_hatend:
                        had_hatend = 0
                        if st.f0mode == NORMAL:
                            f0fall = 180
                            delayf0 = st.allodurs[nphon] - 25
                            if delayf0 < 4:
                                delayf0 = 4
                            if (struccur & FBOUNDARY) == FCBNEXT:
                                f0fall = 120
                            if (struccur & FBOUNDARY) == FVPNEXT:
                                f0fall = 0
                            if (struccur & FBOUNDARY) < FVPNEXT:
                                for nphonx in range(nphon + 1, st.nallotot):
                                    if (st.allofeats[nphonx] & FHATBEG) != 0:
                                        f0fall = 0
                                        break
                                    if (_phone_feature(st.allophons[nphonx]) & FSYLL) != 0:
                                        if (st.allofeats[nphonx] & 0o3) == 0:
                                            delayf0 = st.allodurs[nphon] - 8
                                        if (st.allofeats[nphonx] & FBOUNDARY) == FVPNEXT:
                                            f0fall = 0
                                            break
                                        if (st.allofeats[nphonx] & FBOUNDARY) > FVPNEXT:
                                            f0fall = 150
                                            break
                            if (struccur & FBOUNDARY) == FSENTRISE:
                                f0fall = 80
                            f0fall = s16(s32(f0fall * st.assertiveness) >> 12)
                            if st.cbsymbol:
                                f0fall = f0fall >> 1
                            f0fall &= 0o37776
                            f0fall = s16(f0fall + hatsize)
                        elif st.f0mode == HAT_F0_SIZES_SPECIFIED:
                            f0fall = ((st.user_f0[mf0] - 400) * 10) + 2
                            if f0fall >= 2000 or f0fall <= 0 or inputscrewup == 1:
                                f0fall = 2
                                inputscrewup = 1
                            delayf0 = _mstofr(st.user_offset[mf0])
                            mf0 += 1
                        cumdur = _make_f0_command(st, s16(-f0fall), delayf0, cumdur)
                        hat_loc_re_baseline = s16(hat_loc_re_baseline - f0fall)

                    if ((struccur & FBOUNDARY) == FCBNEXT
                            or (struccur & FBOUNDARY) == FSENTRISE):
                        delayf0 = st.allodurs[nphon] - 13
                        if (struccur & FBOUNDARY) == FSENTRISE:
                            cumdur = _make_f0_command(st, 181, delayf0, cumdur)
                            cumdur = _make_f0_command(
                                st, 251, st.allodurs[nphon], cumdur)
                        else:
                            delayf0 += 3
                            cumdur = _make_f0_command(st, 71, delayf0, cumdur)
                            cumdur = _make_f0_command(
                                st, 101, st.allodurs[nphon], cumdur)

                if (feacur & FSYLL) != 0:
                    if (stresscur & 0o1) == 0 or (struccur & FHATEND) == 0:
                        if ((struccur & FBOUNDARY) == 0o400
                                or (struccur & FBOUNDARY) == 0o500):
                            targf0 = -60
                            targf0 = s16(s32(targf0 * st.assertiveness) >> 12)
                            targf0 |= 0o1
                            cumdur = _make_f0_command(
                                st, targf0, st.allodurs[nphon] - 16, cumdur)
                        delayf0 = st.allodurs[nphon] - 13
                        if (struccur & FBOUNDARY) == FSENTRISE:
                            cumdur = _make_f0_command(st, 181, delayf0, cumdur)
                            cumdur = _make_f0_command(
                                st, 251, st.allodurs[nphon], cumdur)
                        if (struccur & FBOUNDARY) == FCBNEXT:
                            delayf0 += 3
                            cumdur = _make_f0_command(st, 71, delayf0, cumdur)
                            cumdur = _make_f0_command(
                                st, 101, st.allodurs[nphon], cumdur)

                if phocur == GEN_SIL:
                    if hat_loc_re_baseline != 0 and st.nf0tot > 0:
                        cumdur = _make_f0_command(
                            st, s16(-hat_loc_re_baseline), 0, cumdur)
                        hat_loc_re_baseline = 0
                    if nphon > 0:
                        nrises_sofar = 1
                    if (struclas & FSENTENDS) != 0:
                        cumdur = _make_f0_command(st, 0, 0, cumdur)
                        hat_loc_re_baseline = 0
                        nrises_sofar = 0

        cumdur = s16(cumdur + st.allodurs[nphon])

        # Insert a reduced vowel after a final plosive (`ph_inton0.c:1988`).
        if (phonex == GEN_SIL
                and ((0x1E << 8) | 45) <= phocur <= ((0x1E << 8) | 50)
                and st.nallotot < 300):
            # Shift [nphon+1 .. nallotot) right by one (`ph_inton0.c:2003`).
            st.allophons.insert(nphon + 1, 0)
            st.allofeats.insert(nphon + 1, 0)
            st.allodurs.insert(nphon + 1, 0)
            st.user_f0.insert(nphon + 1, st.user_f0[nphon])
            new = (0x1E << 8) | 17
            if (pholas < ((0x1E << 8) | 5)
                    or (((0x1E << 8) | 47) <= phocur <= ((0x1E << 8) | 48))):
                new = (0x1E << 8) | 18
            st.allophons[nphon + 1] = new
            st.allodurs[nphon + 1] = 4
            cumdur = s16(cumdur + 4)
            st.allofeats[nphon + 1] = st.allofeats[nphon] | FINSERTED
            st.nallotot += 1
            nphon += 1

        nphon += 1


@dataclass
class Pht0drawIn:
    """The per-clause `pDph_t` state `pht0draw` reads (constant across its frames).

    The allophone stream is the post-`phinton` one; the F0 command arrays are
    `phinton`'s output. The speaker scalars (`f0basefall`, `f0_lp_filter`,
    `f0minimum`, `f0scalefac`) and `newparagsw`/`f0mode` are captured from the
    oracle.
    """

    allophons: tuple[int, ...]
    allofeats: tuple[int, ...]
    allodurs: tuple[int, ...]
    nallotot: int
    f0tar: tuple[int, ...]
    f0tim: tuple[int, ...]
    nf0tot: int
    f0mode: int
    f0basefall: int
    f0_lp_filter: int
    f0minimum: int
    f0scalefac: int
    newparagsw: int


class Pht0draw:
    """`pht0draw` (`ph_drwt01.c:277`) as a per-frame state machine.

    Instantiate once per clause with the `phinton` output and speaker scalars,
    then call `step()` once per output frame. Each call returns the drawn period
    `parstochip[OUT_T0] = 400000 / f0prime` (`ph_drwt01.c:2934`); `f0`/`f0prime`/
    `avglstop` are exposed as attributes for the frame loop that follows.

    `nf0ev` is seeded from `pDph_t->nf0ev` (`init_clause`, `ph_claus.c:531`): -2 on
    the first clause after a speaker load (jump to the initial value), else -1.
    """

    def __init__(self, src: Pht0drawIn, nf0ev: int = -2) -> None:
        self.src = src
        self.nf0ev = nf0ev
        self.f0 = 0
        self.f0prime = 0
        self.avglstop = 0
        # pDphsettar F0 fields carried across frames.
        self.f0beginfall = 0
        self.f0endfall = 0
        self.beginfall = 0
        self.endfall = 0
        self.nframb = 0
        self.tglstp = 0
        self.tglstn = 0
        self.f0las1 = 0
        self.f0las2 = 0
        self.tarhat = 0
        self.tarimp = 0
        self.tarbas = 0
        self.tarseg = 0
        self.tarseg1 = 0
        self.f0a1 = 0
        self.f0a2 = 0
        self.f0b = 0
        self.nimp = 0
        self.newnote = 0
        self.delnote = 0
        self.delcum = 0
        self.f0start = 0
        self.vibsw = 0
        self.timecos10 = 0
        self.timecos15 = 0
        self.timecosvib = 0
        self.dtimf0 = 0
        self.np_drawt0 = -1
        self.npg = -1
        self.phonex_drawt0 = 0
        self.nframs = 0
        self.nfram = 0
        self.nframg = 0
        self.extrad = 0
        self.segdur = 0
        self.segdrg = 0

    def new_clause(self, src: Pht0drawIn, nf0ev: int) -> None:
        """Start the next clause of the same utterance (`init_clause`).

        `pDphsettar`/`pDph_t` F0 state persists across clauses in the C (one
        `pht0draw` state per speech thread); only the F0 command stream and the
        `nf0ev` seed change. On a non-hard init (`nf0ev == -1`) the carried
        `f0`, `timecos*`, `tglstp`, and the derived fall/filter fields survive.
        """
        self.src = src
        self.nf0ev = nf0ev

    def _allo(self, n: int) -> int:
        return self.src.allophons[n] if 0 <= n < len(self.src.allophons) else 0

    def _feat(self, n: int) -> int:
        return self.src.allofeats[n] if 0 <= n < len(self.src.allofeats) else 0

    def _dur(self, n: int) -> int:
        return self.src.allodurs[n] if 0 <= n < len(self.src.allodurs) else 0

    def _set_user_target(self, f0command: int) -> None:
        """`set_user_target` (`ph_drwt01.c:3045`): resolve a `>= 2000` user command."""
        f0command -= 2000
        if f0command <= 37:
            self.newnote = NOTETAB[f0command - 1]
            self.vibsw = 1
            self.delnote = s16((self.newnote - self.f0) >> 2)
        else:
            f0command *= 10
            if f0command < 500:
                f0command = 500
            elif f0command > 5121:
                f0command = 5121
            self.newnote = f0command
            self.vibsw = 0
            self.delnote = s16((self.newnote - self.f0) << 2)
            trandur = self._dur(self.npg + 1)
            if self.delnote > 0:
                self.delnote = s16(self.delnote + (trandur - 1))
            if self.delnote < 0:
                self.delnote = s16(self.delnote - (trandur - 1))
            if trandur != 0:
                self.delnote = int(self.delnote / trandur)
            else:
                self.delnote = self.delnote >> 3
        self.delcum = 0
        self.f0start = self.f0

    def _set_tglst(self) -> None:
        """`set_tglst` (`ph_drwt01.c:3118`): schedule the glottalization dip."""
        if self.nframg >= self.segdrg:
            self.nframg -= self.segdrg
            self.npg += 1
            self.segdrg = self._dur(self.npg)
            if self.tglstp == 0:
                self.tglstp = -200
            if self.tglstp > 0:
                self.tglstp = 0
            self.tglstn = -200
            npg = self.npg
            if ((_phone_feature(self._allo(npg + 1)) & FVOWEL) != 0
                    and (self._feat(npg + 1) & (0o20 & 0o30)) == 0
                    and (self._feat(npg) & FBOUNDARY) >= 0o140
                    and self._allo(npg + 1) != ((0x1E << 8) | 16)):
                if (_phone_feature(self._allo(npg)) & FSYLL) != 0:
                    if ((self._allo(npg) == self._allo(npg + 1)
                            and (self._feat(npg + 1) & 0o1) != 0)
                            or (self._feat(npg) & FBOUNDARY) >= FVPNEXT):
                        self.tglstn = self.segdrg
                elif ((_phone_feature(self._allo(npg)) & FPLOSV) == 0
                        and self._allo(npg) != ((0x1E << 8) | 51)
                        and (self._feat(npg + 1) & 0o1) != 0):
                    self.tglstn = self.segdrg
            if (US_PLACE[self._allo(npg + 1) & 0x00FF] & 0o40) != 0:
                self.tglstn = self.segdrg
            if (US_PLACE[self._allo(npg) & 0x00FF] & 0o40) != 0:
                self.tglstn = self.segdrg
        elif self.nframg == 8 or self.nframg == (self.segdrg - 1):
            self.tglstp = self.tglstn

    def _filter_commands(self, f0in: int) -> None:
        """`filter_commands` (`ph_drwt01.c:3221`): two-pole low-pass of the F0 sum."""
        f0outa = s16(s32(self.f0a1 * f0in) >> 14)
        f0outb = s16(s32(self.f0b * self.f0las1) >> 14)
        f0out1 = s16(f0outa + f0outb)
        self.f0las1 = f0out1
        f0outc = s16(s32(self.f0a2 * s16(f0out1 + s16(self.tarseg1 << 3))) >> 14)
        f0outd = s16(s32(self.f0b * self.f0las2) >> 14)
        f0out2 = s16(f0outc + f0outd)
        self.f0las2 = f0out2
        self.f0 = f0out2 >> 3
        self.f0prime = self.f0

    def _linear_interp(self) -> None:
        """`linear_interp` (`ph_drwt01.c:3293`): the SINGING/user-note interpolator."""
        self.delcum = s32(self.delcum + self.delnote)
        self.f0 = s16(self.f0start + (self.delcum >> 2))
        if self.delnote >= 0:
            if self.f0 > self.newnote:
                self.f0 = self.newnote
                self.f0start = self.newnote
                self.delcum = 0
                self.delnote = 0
        else:
            if self.f0 < self.newnote:
                self.f0 = self.newnote
                self.f0start = self.newnote
                self.delcum = 0
                self.delnote = 0
        self.f0prime = self.f0
        if self.vibsw == 1:
            self.timecosvib += 165
            if self.timecosvib > 4096:
                self.timecosvib -= 4096
            self.f0prime = s16(self.f0prime + (GETCOSINE[self.timecosvib >> 6] >> 3))

    def step(self) -> int:
        """One `pht0draw` call; return `parstochip[OUT_T0]` for this frame."""
        src = self.src

        if self.nf0ev <= -2:
            self.f0beginfall = 1070 + (src.f0basefall >> 1)
            self.f0endfall = 1070 - (src.f0basefall >> 1)
            self.nframb = 0
            self.tglstp = -200
            self.f0las1 = s16(self.f0beginfall << 3)
            self.f0las2 = s16(self.f0beginfall << 3)
            self.f0 = self.f0beginfall
            self.tarhat = 0
            self.tarimp = 0
            self.f0a2 = src.f0_lp_filter
            self.f0b = 16384 - src.f0_lp_filter
            self.f0a1 = s16(self.f0a2 << 3)
            self.newnote = self.f0beginfall
            self.delnote = 0
            self.delcum = 0
            self.f0start = self.f0
            self.vibsw = 0
            self.timecos10 = 0
            self.timecos15 = 0
            self.timecosvib = 0
            self.nf0ev = -1

        if self.nf0ev == -1:
            self.f0las1 = s16(self.f0beginfall << 3)
            self.f0las2 = s16(self.f0beginfall << 3)
            self.beginfall = self.f0beginfall
            self.endfall = self.f0endfall
            self.nframb = 0
            if src.newparagsw != 0:
                self.beginfall += 120
                self.endfall += 70
            self.dtimf0 = src.f0tim[0] if src.nf0tot > 0 else 0
            self.np_drawt0 = -1
            self.npg = -1
            self.nf0ev = 0
            self.nframs = 12 - (src.f0_lp_filter >> 8)
            if src.f0mode < SINGING:
                self.nfram = self.nframs >> 1
            else:
                self.nfram = 0
            self.nframg = 0
            self.extrad = 0
            self.segdur = 0
            self.segdrg = 0
            self.tarhat = 0

        # Consume the F0 commands whose time has arrived (`ph_drwt01.c:2559`).
        while self.nfram >= self.dtimf0 and self.nf0ev < src.nf0tot:
            f0command = src.f0tar[self.nf0ev]
            self.nfram -= self.dtimf0
            self.nf0ev += 1
            self.dtimf0 = src.f0tim[self.nf0ev] if self.nf0ev < len(src.f0tim) else 0
            if f0command == 0:
                self.nframb = 0
                self.tarhat = 0
            elif f0command >= 2000:
                self._set_user_target(f0command)
            elif (f0command & 0o1) == 0:
                self.tarhat = s16(self.tarhat + f0command)
                if f0command < 0:
                    self.tarimp = 0
            else:
                self.tarimp = s16(f0command + f0command)
                self.nimp = 16 - ((src.f0_lp_filter - 1300) >> 8)

        self.tarbas = s16(self.beginfall - self.nframb)
        if self.tarbas > self.endfall:
            self.nframb += 1

        self.nimp -= 1
        if self.nimp < 0:
            self.tarimp = 0

        # Advance the segment target (`ph_drwt01.c:2685`).
        if (self.nframs >= (self.segdur + self.extrad)
                and self.np_drawt0 < (src.nallotot - 1)):
            self.nframs -= self.segdur
            self.np_drawt0 += 1
            self.segdur = self._dur(self.np_drawt0)
            self.extrad = 0
            phocur = self._allo(self.np_drawt0)
            if self.np_drawt0 < src.nallotot:
                self.phonex_drawt0 = self._allo(self.np_drawt0 + 1)
            f0seg = US_F0SEGTARS[phocur & 0x00FF]
            if (self._feat(self.np_drawt0) & 0o3) == 0:
                f0seg = f0seg >> 1
            if (_phone_feature(self.phonex_drawt0) & FVOICD) == 0:
                self.extrad = 2
            if (_phone_feature(phocur) & FVOICD) == 0:
                self.tarseg1 = f0seg
                self.tarseg = 0
                self.extrad = 0
                if (_phone_feature(phocur) & FPLOSV) != 0:
                    self.extrad = 5
            else:
                self.tarseg = f0seg
                self.tarseg1 = 0

        self._set_tglst()

        if src.f0mode < SINGING:
            f0in = s16(self.tarbas + self.tarhat + self.tarimp + self.tarseg)
            self.tarseg = s16(s32(self.tarseg * 16064) >> 14)
            self._filter_commands(f0in)
        else:
            self._linear_interp()

        # Glottalization dip (`ph_drwt01.c:2890`).
        dtglst = self.nframg - self.tglstp
        if dtglst < 0:
            dtglst = -dtglst
        if dtglst <= 7:
            self.f0prime = s16(self.f0prime + ((dtglst * 70) - 550))
        if dtglst <= 5:
            self.avglstop = 6 - dtglst
        else:
            self.avglstop = 0

        if self.f0prime > 5121:
            self.f0prime = 5121
        elif self.f0prime < 500:
            self.f0prime = 500

        if src.f0mode < SINGING:
            self.f0prime = s16(
                src.f0minimum
                + (s32((self.f0prime - 1200) * src.f0scalefac) >> 12))
            self.timecos15 += 43
            if self.timecos15 > 4096:
                self.timecos15 -= 4096
            self.timecos10 += 97
            if self.timecos10 > 4096:
                self.timecos10 -= 4096
            pseudojitter = (GETCOSINE[self.timecos15 >> 6]
                            + GETCOSINE[self.timecos10 >> 6])
            self.f0prime = s16(self.f0prime + (pseudojitter >> 5))
            if self.f0prime > 5121:
                self.f0prime = 5121
            elif self.f0prime < 500:
                self.f0prime = 500
        elif src.f0mode == SINGING:
            self.f0prime = s16(s32(self.f0prime * 4190) >> 12)

        t0 = int((400 * 1000) / self.f0prime)

        self.nfram += 1
        self.nframs += 1
        self.nframg += 1
        return t0
