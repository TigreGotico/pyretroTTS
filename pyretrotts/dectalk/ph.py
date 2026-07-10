"""DECtalk phoneme frame drawer (`phdraw`, the target-to-frame interpolator).

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/ph/ph_draw.c`, function `phdraw`). FONIX Corporation declares that
source proprietary and confidential. This file is NOT covered by this project's
MIT licence. See NOTICE.

`phdraw` is the last stage of the `ph/` chain: once per output frame it reads the
per-parameter interpolation state (`PARAMETER param[]`, set at each phoneme
boundary by `phsettar`) and writes the Klatt control parameters into
`parstochip[]` -- the frame vector `vtm.py` consumes. This reproduces the
compiled US-English path (`ENGLISH_US`, `OLD_INTONATION_AND_TIMING`, neither
`HLSYN` nor `CHANGES_AFTER_V43`), for which `phdraw` returns at `ph_draw.c:4307`
after the spectral-tilt block; every executable line for that build lies in
`ph_draw.c:345-746`.

The upstream stages (`phsort`, `phalloph`, `us_phtiming`, `phinton`, `phsettar`,
`pht0draw`) are not ported here; the interpolation state they produce is this
drawer's input, captured from the instrumented C oracle by
`tools/dump_dectalk_vtm.parse_ph_dump` and replayed for validation, exactly as
Phase 1 captured this drawer's own output to validate `vtm.py`.

All arithmetic is the reference's fixed point: intermediates are held in C `short`
variables, so every assignment truncates to 16 bits (`s16`), and `DIV_BY8` is an
arithmetic right shift by 3 (`ph_defs.h:382`).
"""
from __future__ import annotations

from dataclasses import dataclass

from .vtm import frac4mul, s16

# German affricate allophone code (`p_all_ph.h`: (PFGR<<PSFONT)|GR_KSX =
# (0x1C<<8)|55). Never appears in the US-English allophone stream; present so the
# double-burst rule at `ph_draw.c:516` is reproduced verbatim.
GRP_KSX = (0x1C << 8) | 55

# `phdraw` draws these sixteen parameters, in this order. Index j into a drawn
# frame maps to the ph parameter enum value j+1 (F1=1 .. TILT=16, `ph_defs.h`);
# F0 (index 0) is drawn by `pht0draw`, not here.
PARAM_NAMES = (
    "F1", "F2", "F3", "FZ", "B1", "B2", "B3",       # first loop (PF1..PB3)
    "AV", "AP", "A2", "A3", "A4", "A5", "A6", "AB", "TILT",  # second loop
)
_J_F2 = 1   # PF2: vowel-vowel F2 coarticulation
_J_B1 = 4   # PB1: breathy-voice bandwidth widening
_J_AV = 7
_J_AP = 8
_J_TILT = 15


@dataclass(frozen=True)
class PhParam:
    """One `PARAMETER` struct's per-frame interpolation state (`ph_defs.h:586`).

    `ndip0`/`ndip1` are the next two `dipspec[]` values `np->ndip` points at; the
    first-loop parameters consume them when a new diphthong line begins.
    """

    tarcur: int
    durlin: int
    deldip: int
    dipcum: int
    ftran: int
    dftran: int
    btran: int
    dbtran: int
    tbacktr: int
    tspesh: int
    pspesh: int
    ndip0: int = 0
    ndip1: int = 0


@dataclass(frozen=True)
class DrawScalars:
    """The `pDph_t`/`pDphsettar` fields `phdraw` reads for one frame."""

    tcum: int
    phon: int
    spdefb1off: int
    avglstop: int
    f0: int
    f0_dep_tilt: int
    spdeftltoff: int
    breathysw: int
    spdeflaxprcnt: int
    fvvtran: int
    dfvvtran: int
    tvvbacktr: int
    bvvtran: int
    dbvvtran: int
    breathyah: int
    breathytilt: int


@dataclass(frozen=True)
class DrawFrame:
    """A single `phdraw` invocation: scalars plus the sixteen `PARAMETER` states."""

    scalars: DrawScalars
    params: tuple[PhParam, ...]


def draw_frame(frame: DrawFrame) -> list[int]:
    """Reproduce one `phdraw` call, returning the sixteen drawn parameters.

    Order matches `PARAM_NAMES`: F1, F2, F3, FZ, B1, B2, B3, AV, AP, A2, A3, A4,
    A5, A6, AB, TILT (i.e. the `parstochip[]` slots `phdraw` writes). Mutation of
    the interpolation state is intentionally not returned: the C oracle recaptures
    each frame's entry state, so the drawer is validated per frame in isolation.
    """
    s = frame.scalars
    p = frame.params
    out = [0] * 16

    # First loop: F[1,2,3], FZ, B[1,2,3] (`ph_draw.c:345-421`).
    for j in range(7):
        q = p[j]
        tarcur = q.tarcur
        deldip = q.deldip
        dipcum = q.dipcum
        ftran = q.ftran
        btran = q.btran

        # New diphthong line segment (`ph_draw.c:361-367`).
        if s.tcum > q.durlin and s.tcum > 0 and q.durlin >= 0:
            deldip = q.ndip1
            tarcur = s16(tarcur + (dipcum >> 3))
            dipcum = 0

        dipcum = s16(dipcum + deldip)
        value = s16(dipcum + ftran)
        if s.tcum >= q.tbacktr:
            value = s16(value + btran)

        # PF2: vowel-vowel coarticulation across a consonant (`ph_draw.c:388-398`).
        if j == _J_F2:
            value = s16(value + s.fvvtran)
            if s.tcum >= s.tvvbacktr:
                value = s16(value + s.bvvtran)

        parp = s16((value >> 3) + tarcur)

        # Special constant onset, else breathy PB1 widening (`ph_draw.c:408-420`).
        if q.tspesh > 0:
            if s.tcum < q.tspesh:
                parp = q.pspesh
        elif j == _J_B1:
            parp = frac4mul(parp, s.spdefb1off)
        out[j] = parp

    # Second loop: AV, AP, A[2..6], AB, TILT (`ph_draw.c:428-606`).
    for j in range(7, 16):
        q = p[j]
        value = s16(q.tarcur + (q.ftran >> 3))
        if s.tcum >= q.tbacktr:
            parp = s16(value + (q.btran >> 3))
        else:
            parp = value

        # Special onset value and post-onset double burst (`ph_draw.c:455-524`).
        if q.tspesh > 0:
            if s.tcum < q.tspesh:
                parp = q.pspesh
            elif (j + 1) > _J_AP + 1 and s.tcum == (q.tspesh + 1) and parp >= 10:
                # (j + 1) is the ph enum value; > AP means the amplitude formants.
                parp = 0 if s.phon == GRP_KSX else s16(parp - 10)
        out[j] = parp

    # Reduce AV if glottal stop (`ph_draw.c:613-616`).
    if out[_J_AV] > 6:
        out[_J_AV] = s16(out[_J_AV] - s.avglstop)

    # Source spectral tilt (`ph_draw.c:634-742`, the non-HLSYN branch).
    temptilt = s16(frac4mul(1400 - s.f0, s.f0_dep_tilt))
    if temptilt < 0:
        temptilt = 0
    temptilt = 12 - temptilt
    if temptilt < 0:
        temptilt = 0
    out[_J_TILT] = s16(out[_J_TILT] + temptilt)
    out[_J_TILT] = s16(out[_J_TILT] + (s.spdeftltoff - 6))

    # Breathy-voice offset (`ph_draw.c:687-725`, the non-HLSYN branch).
    if s.breathysw == 1 and out[_J_AV] > 40:
        breathyah = s16(s.breathyah + 2) if s.breathyah < 27 else s.breathyah
        value = frac4mul(breathyah + 30, s.spdeflaxprcnt)
        if out[_J_AP] < value:
            out[_J_AP] = value
        breathytilt = s16(s.breathytilt + 1) if s.breathytilt < 16 else s.breathytilt
        out[_J_TILT] = s16(out[_J_TILT] + frac4mul(s.spdeflaxprcnt, breathytilt))

    if out[_J_TILT] > 31:
        out[_J_TILT] = 31
    if out[_J_TILT] < 0:
        out[_J_TILT] = 0

    return out
