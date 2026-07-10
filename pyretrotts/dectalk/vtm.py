"""DECtalk vocal tract model (VTM1 integer Klatt cascade/parallel synthesizer).

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/vtm/vtm1.c`, whose header reads "Copyright (c) 1984 by Dennis H.
Klatt" and "Klatt synthesizer ... J. Acoust. Soc. Am., Mar. 1980"). FONIX
Corporation declares that source proprietary and confidential. This file is
NOT covered by this project's MIT licence. See NOTICE.

This reproduces `speech_waveform_generator` for the US-English build path
(`VTM1`, `PC_SAMPLE_RATE == 11025`, `SAMPLE_RATE_INCREASE`): a per-frame loop
of 71 samples driving a cascade branch (nasal zero/pole, five cascade
formants) excited by the glottal source, summed with a parallel branch (six
formants plus a bypass path) excited by frication noise. All arithmetic is the
reference's fixed point; every intermediate is width-truncated as the C is.

The frame parameters and the resolved speaker state that this consumes are
produced upstream by `ph/` (not ported in Phase 1); they are captured from the
C oracle by `tools/dump_dectalk_vtm.py` and replayed here for validation.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import consts as C
from .tables import (
    AMPTABLE,
    AZERO_TAB,
    B0,
    BZERO_TAB,
    COSINE_TABLE,
    CZERO_TAB,
    RADIUS_TABLE,
)

_INV = C.INV_RATE_SCALE
_RATE = C.RATE_SCALE


def s16(x: int) -> int:
    """Truncate to a signed 16-bit value, as a C assignment to S16 does."""
    x &= 0xFFFF
    return x - 0x10000 if x >= 0x8000 else x


def s32(x: int) -> int:
    """Truncate to a signed 32-bit value, as a C 32-bit int op does."""
    x &= 0xFFFFFFFF
    return x - 0x100000000 if x >= 0x80000000 else x


def frac4mul(x: int, y: int) -> int:
    """(x * (S32)y) >> 12, in 32-bit arithmetic (`viphdefs.h`)."""
    return s32(x * y) >> 12


def frac1mul(x: int, y: int) -> int:
    """(x * (S32)y) >> 15, in 32-bit arithmetic (`viphdefs.h`)."""
    return s32(x * y) >> 15


# Resolved per-speaker constants that `read_speaker_definition` derives once
# and the frame loop reads. Names mirror the C `pVtm_t` fields.
@dataclass(frozen=True)
class SpeakerState:
    fnscal: int
    avgain: int
    APgain: int
    AFgain: int
    Aturb: int
    k1: int
    k2: int
    t0jitr: int
    r1cg: int
    r2cg: int
    r3cg: int
    rnpa: int
    R4ca: int
    R4cb: int
    R4cc: int
    R5ca: int
    R5cb: int
    R5cc: int
    R4pb: int
    r4pc: int
    R5pb: int
    r5pc: int
    r6pb: int
    r6pc: int
    rnpb: int
    rnpc: int
    rlpa: int
    rlpb: int
    rlpc: int
    noiseb: int


def d2pole_cf123(f: int, bw: int, gain: int) -> tuple[int, int, int]:
    """Cascade formant 1/2/3 coefficients (a as S32, b/c as S16)."""
    f = s16(frac1mul(_INV, f))
    bw = s16(frac1mul(_INV, bw))
    if f >= 4500 or bw > 4950:
        f = C.SAMPLE_RATE_HZ >> 1
        bw = C.SAMPLE_RATE_HZ >> 2
    radius = RADIUS_TABLE[bw >> 3]
    b = s16(frac4mul(radius, COSINE_TABLE[f >> 3]))
    c = s16(-frac4mul(radius, radius))
    temp = s32(4096 - b - c)
    a = s32(frac4mul(gain, temp) << 1)
    return a, b, c


def d2pole_cf45(f: int, bw: int, gain: int) -> tuple[int, int, int]:
    """Cascade formant 4/5 coefficients; the resonator is zapped out of band."""
    f = s16(frac1mul(_INV, f))
    bw = s16(frac1mul(_INV, bw))
    if f >= 4500 or bw > 4950:
        b = 0
        c = 0
    else:
        radius = RADIUS_TABLE[bw >> 3]
        b = s16(frac4mul(radius, COSINE_TABLE[f >> 3]))
        c = s16(-frac4mul(radius, radius))
    temp = s32(4096 - b - c)
    a = s16(frac4mul(gain, temp) << 1)
    return a, b, c


def d2pole_pf(f: int, bw: int, gain: int) -> tuple[int, int, int]:
    """Parallel formant coefficients; zapped to silence when out of band."""
    f = s16(frac1mul(_INV, f))
    bw = s16(frac1mul(_INV, bw))
    if f >= 4500 or bw > 4950:
        return 0, 0, 0
    radius = RADIUS_TABLE[bw >> 3]
    b = s16(frac4mul(radius, COSINE_TABLE[f >> 3]))
    c = s16(-frac4mul(radius, radius))
    temp = s32(4096 - b - c)
    a = s16(frac4mul(gain, temp) << 1)
    return a, b, c


@dataclass
class VtmState:
    """Mutable per-utterance state, all zero at process start (fresh calloc).

    `read_speaker_definition` loads `spk` and sets `ldspdef = 1`, `t0jitr`, and
    the fixed noise/nasal/low-pass coefficients; the rest stay zero.
    """

    spk: SpeakerState
    ldspdef: int = 1
    # Random generator and its low-pass memory.
    randomx: int = 0
    nolast: int = 0
    # Pi-rotated antiresonator memory (noise).
    ablas1: int = 0
    ablas2: int = 0
    # Glottal source and voicing.
    voice0: int = 0
    a: int = 0
    b: int = 0
    avlin: int = 0
    avlind: int = 0
    aturb1: int = 0
    nper: int = 0
    T0: int = 0
    nopen: int = 0
    nmod: int = 0
    t0jitr: int = 0
    decay: int = 0
    one_minus_decay: int = 0
    vlast: int = 0
    rampdown: int = 0
    # Down-sampling low-pass filter memory and fixed coefficients.
    rlpd1: int = 0
    rlpd2: int = 0
    # Cascade coefficients set pitch-synchronously.
    R1ca: int = 0
    r1cb: int = 0
    r1cc: int = 0
    R2ca: int = 0
    r2cb: int = 0
    r2cc: int = 0
    R3ca: int = 0
    r3cb: int = 0
    r3cc: int = 0
    rnza: int = 0
    rnzb: int = 0
    rnzc: int = 0
    # Cascade filter memory.
    r1cd1: int = 0
    r1cd2: int = 0
    r2cd1: int = 0
    r2cd2: int = 0
    r3cd1: int = 0
    r3cd2: int = 0
    r4cd1: int = 0
    r4cd2: int = 0
    r5cd1: int = 0
    r5cd2: int = 0
    rnpd1: int = 0
    rnpd2: int = 0
    rnzd1: int = 0
    rnzd2: int = 0
    # Parallel filter memory.
    r2pd1: int = 0
    r2pd2: int = 0
    r3pd1: int = 0
    r3pd2: int = 0
    r4pd1: int = 0
    r4pd2: int = 0
    r5pd1: int = 0
    r5pd2: int = 0
    r6pd1: int = 0
    r6pd2: int = 0
    iwave: list[int] = field(default_factory=list)


def _two_pole(inp: int, d1: int, d2: int, a: int, b: int, c: int) -> tuple[int, int]:
    """`two_pole_filter`: returns (new_delay_1 = output, new_delay_2)."""
    temp1 = s32(c * d2)
    new_d2 = d1
    temp1 = s32(temp1 + s32(b * d1))
    temp1 = s32(temp1 + s32(a * inp))
    new_d1 = s32(temp1 >> 12)
    return new_d1, new_d2


def _two_zero(inp: int, d1: int, d2: int, a: int, b: int, c: int) -> tuple[int, int, int]:
    """`two_zero_filter`: returns (output, new_delay_1, new_delay_2)."""
    temp1 = s32(c * d2)
    temp1 = s32(temp1 + s32(b * d1))
    temp1 = s32(temp1 + s32(a * inp))
    out = s32(temp1 >> 12)
    return out, inp, d1


def process_frame(st: VtmState, frame: list[int]) -> list[int]:
    """Synthesize one 71-sample frame. `frame` is `variabpars[0..19]`.

    Mutates `st` and returns the frame's 16-bit samples (also in `st.iwave`).
    """
    spk = st.spk
    v = list(frame)  # variabpars

    # First two frames after a speaker definition are forced to silence.
    if st.ldspdef >= 1:
        st.ldspdef += 1
        for i in (C.OUT_AV, C.OUT_AP, C.OUT_A2, C.OUT_A3, C.OUT_A4,
                  C.OUT_A5, C.OUT_A6, C.OUT_AB):
            v[i] = 0
        st.avlin = 0
    if st.ldspdef >= 3:
        st.ldspdef = -1

    # Pitch period, scaled for 11025 Hz (SAMPLE_RATE_INCREASE).
    T0inS4 = s16(frac1mul(_RATE, v[C.OUT_T0]) << 1)

    fnscal = spk.fnscal
    F1inHZ = s16(frac4mul(v[C.OUT_F1], fnscal) + s16((4096 - fnscal) >> 4))
    F2inHZ = s16(frac4mul(v[C.OUT_F2], fnscal) + s16((4096 - fnscal) >> 3))
    F3inHZ = s16(frac4mul(v[C.OUT_F3], fnscal))
    FZinHZ = s16(frac1mul(_INV, v[C.OUT_FZ]))

    B1inHZ = v[C.OUT_B1]
    B2inHZ = v[C.OUT_B2]
    B3inHZ = v[C.OUT_B3]
    AVinDB = v[C.OUT_AV]
    APinDB = v[C.OUT_AP]

    TILTDB = v[C.OUT_TLT] - 12

    APlin = AMPTABLE[APinDB + 10]
    r2pg = AMPTABLE[v[C.OUT_A2] + 13]
    r3pg = AMPTABLE[v[C.OUT_A3] + 10]
    r4pa = AMPTABLE[v[C.OUT_A4] + 7]
    r5pa = AMPTABLE[v[C.OUT_A5] + 6]
    r6pa = AMPTABLE[v[C.OUT_A6] + 5]
    ABlin = AMPTABLE[v[C.OUT_AB] + 5]

    APlin = frac4mul(APlin, spk.APgain)
    r2pg = frac1mul(r2pg, spk.AFgain)
    r3pg = frac1mul(r3pg, spk.AFgain)
    r4pa = frac1mul(r4pa, spk.AFgain)
    r5pa = frac1mul(r5pa, spk.AFgain)
    r6pa = frac1mul(r6pa, spk.AFgain)
    ABlin = frac4mul(ABlin, spk.AFgain)

    r2pa, r2pb, r2pc = d2pole_pf(F2inHZ, 210, r2pg)
    r3pa, r3pb, r3pc = d2pole_pf(F3inHZ, 280, r3pg)

    r6pb, r6pc = C.R6PB, C.R6PC
    R4pb, r4pc = spk.R4pb, spk.r4pc
    R5pb, r5pc = spk.R5pb, spk.r5pc
    R4ca, R4cb, R4cc = spk.R4ca, spk.R4cb, spk.R4cc
    R5ca, R5cb, R5cc = spk.R5ca, spk.R5cb, spk.R5cc

    out_wave = [0] * C.SAMPLES_PER_FRAME

    for ns in range(C.SAMPLES_PER_FRAME):
        # Noise generator.
        st.randomx = s16(st.randomx * C.RANMUL + C.RANADD)
        noise = st.randomx >> 2
        noise = s16(noise + frac1mul(24574, st.nolast))
        st.nolast = noise
        # Pi-rotated antiresonator (special-cased three-zero filter).
        temp0 = s32(C.NOISEC * st.ablas2)
        temp0 = s32(temp0 + s32(spk.noiseb * st.ablas1))
        st.ablas2 = st.ablas1
        st.ablas1 = noise
        noise = s16(noise + s16(temp0 >> 12))
        # Amplitude-modulate noise during the closed half-period.
        if st.nper < st.nmod:
            noise = noise >> 1

        # Glottal source, oversampled four times.
        voice = 0
        for _ in range(4):
            if st.nper > (st.T0 - st.nopen):
                st.a = s16(st.a - st.b)
                st.voice0 = s16(st.voice0 + (st.a >> 4))
                st.avlind = st.avlin
            else:
                st.voice0 = 0

            voice = frac4mul(st.voice0, spk.avgain)

            if st.nper == st.T0:
                st.nper = 0
                st.avlin = AMPTABLE[AVinDB + 4]
                st.T0 = s16(T0inS4)
                st.T0 = s16(st.T0 + frac4mul(st.t0jitr, st.T0))
                st.t0jitr = -st.t0jitr
                st.aturb1 = s16(spk.Aturb << 2)
                if F1inHZ < 250:
                    F1inHZ = 250
                st.decay = s32(1094 * TILTDB)
                st.one_minus_decay = 32767 - st.decay if st.decay >= 0 else 32767
                st.nmod = 0
                if st.avlin > 0:
                    st.nmod = st.T0 >> 1
                st.nopen = s16(frac1mul(spk.k1, st.T0) + spk.k2)
                st.nopen = s16(st.nopen + (TILTDB << 2))
                if st.nopen < 40:
                    st.nopen = 40
                elif st.nopen > 263:
                    st.nopen = 263
                if st.nopen >= ((st.T0 * 3) >> 2):
                    st.nopen = (st.T0 * 3) >> 2

                st.b = B0[st.nopen - 40]
                temp = s32(st.b + 1)
                if st.nopen > 95:
                    temp = s32(temp * st.nopen)
                    st.a = s16(frac1mul(10923, temp))
                else:
                    temp = s32(frac1mul(10923, temp))
                    st.a = s16(temp * st.nopen)

                st.R3ca, st.r3cb, st.r3cc = d2pole_cf123(F3inHZ, B3inHZ, spk.r3cg)
                st.R2ca, st.r2cb, st.r2cc = d2pole_cf123(F2inHZ, B2inHZ, spk.r2cg)
                st.R1ca, st.r1cb, st.r1cc = d2pole_cf123(F1inHZ, B1inHZ, spk.r1cg)
                if st.R1ca > 16383:
                    st.R1ca = 16383
                st.R1ca = s16(st.R1ca << 1)

                # Nasal-zero antiresonator by table lookup (11025 Hz path).
                temp = (FZinHZ >> 3) - 31
                if temp > 34:
                    temp = 34
                st.rnza = AZERO_TAB[temp]
                st.rnzb = BZERO_TAB[temp]
                st.rnzc = CZERO_TAB[temp]

            # Down-sampling low-pass filter (40 kHz -> 10 kHz).
            st.rlpd1, st.rlpd2 = _two_pole(
                voice, st.rlpd1, st.rlpd2, spk.rlpa, spk.rlpb, spk.rlpc)
            voice = st.rlpd1
            st.nper += 1

        # Spectral tilt (one-pole).
        voice = s32(frac1mul(st.one_minus_decay, voice) + frac1mul(st.decay, st.vlast))
        st.vlast = voice
        # Breathiness, then variable voicing gain, then aspiration.
        voice = s16(voice + frac1mul(st.aturb1, noise))
        voice = frac4mul(st.avlind, voice)
        voice = s16(voice + frac1mul(APlin, noise))

        # Cascade branch.
        rnzout, st.rnzd1, st.rnzd2 = _two_zero(
            voice, st.rnzd1, st.rnzd2, st.rnza, st.rnzb, st.rnzc)
        st.rnpd1, st.rnpd2 = _two_pole(
            rnzout, st.rnpd1, st.rnpd2, spk.rnpa, spk.rnpb, spk.rnpc)
        st.r5cd1, st.r5cd2 = _two_pole(
            st.rnpd1, st.r5cd1, st.r5cd2, R5ca, R5cb, R5cc)
        st.r4cd1, st.r4cd2 = _two_pole(
            st.r5cd1, st.r4cd1, st.r4cd2, R4ca, R4cb, R4cc)
        st.r3cd1, st.r3cd2 = _two_pole(
            st.r4cd1, st.r3cd1, st.r3cd2, st.R3ca, st.r3cb, st.r3cc)
        st.r2cd1, st.r2cd2 = _two_pole(
            st.r3cd1, st.r2cd1, st.r2cd2, st.R2ca, st.r2cb, st.r2cc)
        st.r1cd1, st.r1cd2 = _two_pole(
            st.r2cd1, st.r1cd1, st.r1cd2, st.R1ca, st.r1cb, st.r1cc)
        out = st.r1cd1

        # Parallel branch, summed with alternating sign.
        st.r6pd1, st.r6pd2 = _two_pole(noise, st.r6pd1, st.r6pd2, r6pa, r6pb, r6pc)
        out = st.r6pd1 - out
        st.r5pd1, st.r5pd2 = _two_pole(noise, st.r5pd1, st.r5pd2, r5pa, R5pb, r5pc)
        out = st.r5pd1 - out
        st.r4pd1, st.r4pd2 = _two_pole(noise, st.r4pd1, st.r4pd2, r4pa, R4pb, r4pc)
        out = st.r4pd1 - out
        st.r3pd1, st.r3pd2 = _two_pole(noise, st.r3pd1, st.r3pd2, r3pa, r3pb, r3pc)
        out = st.r3pd1 - out
        st.r2pd1, st.r2pd2 = _two_pole(noise, st.r2pd1, st.r2pd2, r2pa, r2pb, r2pc)
        out = st.r2pd1 - out
        about = frac1mul(ABlin, noise)
        out = about - out

        # Limit-cycle ramp-down toward silence (NO_LIMIT_CYCLE_RAMPDOWN unset).
        if st.avlind == 0 and (v[C.OUT_PH] & C.PVALUE) == 0:
            st.rampdown += 4
            if st.rampdown >= 4096:
                st.rampdown = 4096
            if st.rampdown >= 0:
                out = frac4mul(out, 4096 - st.rampdown)
        else:
            st.rampdown = 0

        if out > 16383:
            out = 16383
        elif out < -16384:
            out = -16384
        out_wave[ns] = s16(out << 1)

    st.iwave = out_wave
    return out_wave
