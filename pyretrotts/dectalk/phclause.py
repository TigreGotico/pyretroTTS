"""DECtalk US-English clause orchestrator (`phclause`, the phoneme->PCM chain).

Derived from the Fonix/Force DECtalk C source (`dectalk/dectalk`,
`src/dapi/src/ph/ph_claus.c` `phclause`, `ph_claus.c:200`), for the compiled
US-English build (`ENGLISH_US`, `OLD_INTONATION_AND_TIMING`; none of `GERMAN`,
`FRENCH`, `SPANISH`, `ENGLISH_UK`, `HLSYN`, `CHANGES_AFTER_V43`, `EPSON_ARM7`).
FONIX Corporation declares that source proprietary and confidential. This file
is NOT covered by this project's MIT licence. See NOTICE.

`phclause` runs the `ph/` chain in sequence, then a per-frame loop, over a
phoneme+stress+sentence-structure symbol stream (the `lts/`/`cmd/` output, one
`symbols[]` array per clause):

    phsort -> phalloph -> us_phtiming -> phinton -> [per-frame loop]

Each of those stages is ported and bit-exact in isolation (`allophones.py`,
`timing.py`, `intonation.py`, `phsettar.py`, `ph.py`); this file only wires them
together following `ph_claus.c`'s order and glue. The per-frame loop
(`ph_claus.c:362-508`) reproduces, once per 6.4 ms output frame: `pht0draw`
(F0/period), `phdraw` (`draw_frame`/`advance_frame`/`finalize_av`), and
`send_pars`, whose output frames feed `vtm.py`.

Two categories of scalar are speaker-definition state resolved by the Phase-3
`ph/p_us_vdf*.c` layer, which is not ported: the `phdraw` offsets (`spdefb1off`,
`f0_dep_tilt`, `spdeftltoff`, `spdeflaxprcnt`) and the F0 scalars (`f0basefall`,
`f0_lp_filter`, `f0minimum`, `f0scalefac`, `size_hat_rise`, `scale_str_rise`,
`assertiveness`). They are constant per voice; `PH_SPEAKERS` holds them captured
verbatim from one instrumented-oracle run per voice, exactly as `voices.SPEAKERS`
holds the resolved `vtm` speaker state. Variable Val (9) resolves to Perfect
Paul (0) until `[:dv]` overrides it.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import consts as C
from .allophones import QUESTION, _Sort, phalloph
from .engine import synthesize_frames
from .intonation import NORMAL, IntonState, Pht0draw, Pht0drawIn, phinton
from .ph import (
    DrawFrame,
    DrawScalars,
    advance_frame,
    draw_frame,
    finalize_av,
    send_pars,
)
from .phsettar import PhsettarState, build_rawbuf, phsettar, to_draw_params
from .timing import TimingConfig, us_phtiming
from .voices import SPEAKERS

# draw_frame output index -> parstochip slot (matches ph.PARAM_NAMES order).
_X_TO_SLOT = (
    C.OUT_F1, C.OUT_F2, C.OUT_F3, C.OUT_FZ, C.OUT_B1, C.OUT_B2, C.OUT_B3,
    C.OUT_AV, C.OUT_AP, C.OUT_A2, C.OUT_A3, C.OUT_A4, C.OUT_A5, C.OUT_A6,
    C.OUT_AB, C.OUT_TLT,
)


@dataclass(frozen=True)
class PhSpeaker:
    """Speaker-definition scalars the `ph/` chain reads, constant per voice.

    Resolved by the unported `ph/p_us_vdf*.c` (setspdef) layer; captured verbatim
    from the instrumented oracle, one run per voice. `spdefb1off`/`f0_dep_tilt`/
    `spdeftltoff`/`spdeflaxprcnt` feed `phdraw` (`ph.DrawScalars`); the rest feed
    `phinton`/`pht0draw` (`intonation.IntonState`/`Pht0drawIn`). `malfem` selects
    the male/female target ROM in `phsettar`.
    """

    malfem: int
    spdefb1off: int
    f0_dep_tilt: int
    spdeftltoff: int
    spdeflaxprcnt: int
    f0basefall: int
    f0_lp_filter: int
    f0minimum: int
    f0scalefac: int
    size_hat_rise: int
    scale_str_rise: int
    assertiveness: int


# One entry per `-s N` voice (`voices.VOICE_NAMES`), captured from the oracle.
PH_SPEAKERS: tuple[PhSpeaker, ...] = (
    PhSpeaker(1, 4096, 75, 0, 0, 180, 2100, 1220, 4100, 180, 32, 4100),      # 0 Perfect Paul
    PhSpeaker(0, 4096, 75, 1, 3280, 0, 2325, 2080, 9840, 140, 20, 1435),     # 1 Beautiful Betty
    PhSpeaker(1, 4096, 60, 3, 0, 90, 1650, 890, 3280, 200, 30, 4100),        # 2 Huge Harry
    PhSpeaker(1, 5346, 100, 11, 2050, 90, 1500, 1550, 3690, 200, 22, 2665),  # 3 Frail Frank
    PhSpeaker(1, 4818, 100, 25, 2870, 90, 2250, 1100, 5535, 200, 22, 4100),  # 4 Doctor Dennis
    PhSpeaker(0, 5200, 75, 1, 3075, 0, 2250, 3060, 8610, 200, 22, 2665),     # 5 Kit the Kid
    PhSpeaker(0, 4096, 100, 15, 2050, 80, 1950, 2400, 5535, 200, 32, 4100),  # 6 Uppity Ursula
    PhSpeaker(0, 5154, 0, 6, 0, 0, 1950, 1060, 3280, 200, 32, 2665),         # 7 Rough Rita
    PhSpeaker(0, 5608, 100, 25, 3280, 0, 1650, 2000, 7175, 200, 22, 2050),   # 8 Whispering Wendy
    PhSpeaker(1, 4096, 75, 0, 0, 180, 2100, 1220, 4100, 180, 32, 4100),      # 9 Variable Val
)


@dataclass(frozen=True)
class Clause:
    """One clause's front-end output: the `symbols[]`/`user_durs[]` `phclause` reads.

    This is the `lts/`+`cmd/` output for a single clause -- the input `phclause`
    receives per clause. `user_durs` defaults to no per-phone duration override
    (plain `say -a <text>`).
    """

    symbols: tuple[int, ...]
    user_durs: tuple[int, ...] = ()


@dataclass
class _FrameScalars:
    """The F2 vowel-vowel and breathy-voice scalars `phdraw` carries frame to frame."""

    fvvtran: int = 0
    dfvvtran: int = 0
    tvvbacktr: int = 0
    bvvtran: int = 0
    dbvvtran: int = 0
    breathysw: int = 0
    breathyah: int = 0
    breathytilt: int = 0


@dataclass
class _ClauseStream:
    """The post-`phinton` allophone stream plus the `phinton` F0 command output."""

    allophons: list[int]
    allofeats: list[int]
    allodurs: list[int]
    nallotot: int
    malfem: int
    phonemes: list[int]
    nphonetot: int
    alloph_ph: list[int]
    f0tar: list[int]
    f0tim: list[int]
    nf0tot: int
    newparagsw: int


def _front_end(clause: Clause, spk: PhSpeaker, sprate: int) -> _ClauseStream:
    """Run `phsort -> phalloph -> us_phtiming -> phinton` for one clause."""
    symbols = clause.symbols
    user_durs = clause.user_durs or (0,) * len(symbols)

    srt = _Sort(symbols, user_durs, sprate)
    phonemes, sentstruc, nphonetot = srt.run()
    newparagsw = srt.newparagsw
    # `cbsymbol` (the intonation question flag) is 1 for a question clause; the
    # oracle's per-clause value equals clausetype == QUESTION.
    cbsymbol = 1 if srt.clausetype == QUESTION else 0

    allophons, allofeats, nallotot = phalloph(phonemes, sentstruc, nphonetot)

    zeros = (0,) * nallotot
    allodurs = us_phtiming(
        tuple(allophons), tuple(allofeats), zeros, nallotot,
        TimingConfig(sprate=sprate, newparagsw=newparagsw))

    st = IntonState(
        allophons=list(allophons), allofeats=list(allofeats),
        allodurs=list(allodurs), nallotot=nallotot,
        user_f0=[0] * nallotot, user_offset=[0] * nallotot,
        f0mode=NORMAL, cbsymbol=cbsymbol,
        size_hat_rise=spk.size_hat_rise, scale_str_rise=spk.scale_str_rise,
        assertiveness=spk.assertiveness)
    phinton(st)

    return _ClauseStream(
        allophons=st.allophons, allofeats=st.allofeats, allodurs=st.allodurs,
        nallotot=st.nallotot, malfem=spk.malfem,
        phonemes=list(phonemes), nphonetot=nphonetot, alloph_ph=list(allophons),
        f0tar=st.f0tar, f0tim=st.f0tim,
        nf0tot=st.nf0tot, newparagsw=newparagsw)


def _draw_clause(
    stream: _ClauseStream,
    spk: PhSpeaker,
    draw: Pht0draw,
    st: PhsettarState,
    prev_tilt: int,
    delayed: dict[int, int] | None,
) -> tuple[list[list[int]], int, dict[int, int] | None]:
    """Per-frame loop (`ph_claus.c:362-508`) for one clause.

    Runs `phsettar` per phone and, per frame, `pht0draw`, `phdraw`
    (`draw_frame`/`finalize_av`/`advance_frame`), and `send_pars`. `draw` is the
    utterance-wide `Pht0draw` (F0 state persists across clauses); `st` is the
    utterance-wide `PhsettarState`, carrying the `PARAMETER` array, `dipspec`
    buffer and `breathysw` across clauses as the C `pDph_t` does; `prev_tilt` is
    the previous frame's drawn TILT (`parstochip[OUT_TLT]`, read by the forward
    TILT rule at a GEN_SIL boundary); `delayed` is the `send_pars` one-frame delay
    buffer, carried across clauses so priming happens once per utterance. Returns
    the emitted frames, the new `prev_tilt`, and the new delay buffer.
    """
    st.allophons = tuple(stream.allophons)
    st.allofeats = tuple(stream.allofeats)
    st.allodurs = tuple(stream.allodurs)
    st.nallotot = stream.nallotot
    st.malfem = stream.malfem
    st.rawbuf = build_rawbuf(
        tuple(stream.phonemes), stream.nphonetot, tuple(stream.alloph_ph),
        st.allophons, stream.nallotot)
    fls = _FrameScalars()
    frames: list[list[int]] = []

    for nphone in range(stream.nallotot):
        durfon = stream.allodurs[nphone]
        st.nphone = nphone
        st.durfon = durfon
        st.prev_tilt = prev_tilt
        phsettar(st)
        fls.fvvtran, fls.dfvvtran, fls.tvvbacktr = st.fvvtran, st.dfvvtran, st.tvvbacktr
        fls.bvvtran, fls.dbvvtran, fls.breathysw = st.bvvtran, st.dbvvtran, st.breathysw

        for tcum in range(durfon):
            t0 = draw.step()
            # parstochip[OUT_PH/DU/PH2] track pht0draw's segment pointer
            # (`np_drawt0`), not the main-loop audio phone: the F0 segment clock
            # advances that pointer with its own `extrad` plosive/voiceless
            # offsets, so the phone code the vtm reads (only its GEN_SIL bit, for
            # the limit-cycle rampdown) is drawn from there.
            mphone = draw.np_drawt0 if draw.np_drawt0 >= 0 else 0
            mph = stream.allophons[mphone] if mphone < stream.nallotot else 0
            mdu = stream.allodurs[mphone] if mphone < stream.nallotot else 0
            mph2 = stream.allophons[mphone + 1] if mphone + 1 < stream.nallotot else 0

            out = draw_frame(DrawFrame(
                DrawScalars(
                    tcum=tcum, phon=stream.allophons[nphone],
                    spdefb1off=spk.spdefb1off,
                    avglstop=draw.avglstop, f0=draw.f0,
                    f0_dep_tilt=spk.f0_dep_tilt, spdeftltoff=spk.spdeftltoff,
                    breathysw=st.breathysw, spdeflaxprcnt=spk.spdeflaxprcnt,
                    fvvtran=fls.fvvtran, dfvvtran=fls.dfvvtran,
                    tvvbacktr=fls.tvvbacktr, bvvtran=fls.bvvtran,
                    dbvvtran=fls.dbvvtran, breathyah=fls.breathyah,
                    breathytilt=fls.breathytilt),
                to_draw_params(st)))
            prev_tilt = out[15]

            final = list(out)
            finalize_av(final)
            pc = [0] * 20
            for k, slot in enumerate(_X_TO_SLOT):
                pc[slot] = final[k]
            pc[C.OUT_T0] = t0
            pc[C.OUT_PH] = mph
            pc[C.OUT_DU] = mdu
            pc[C.OUT_PH2] = mph2
            frame, delayed = send_pars(pc, delayed)
            if frame is not None:
                frames.append(frame)
            # The breathy ramp keys off the pre-boost AV (ph_draw.c:689).
            advance_frame(st.param, st.dipspec, tcum, out, fls)

    return frames, prev_tilt, delayed


def _pht0src(stream: _ClauseStream, spk: PhSpeaker) -> Pht0drawIn:
    return Pht0drawIn(
        allophons=tuple(stream.allophons), allofeats=tuple(stream.allofeats),
        allodurs=tuple(stream.allodurs), nallotot=stream.nallotot,
        f0tar=tuple(stream.f0tar), f0tim=tuple(stream.f0tim), nf0tot=stream.nf0tot,
        f0mode=NORMAL, f0basefall=spk.f0basefall, f0_lp_filter=spk.f0_lp_filter,
        f0minimum=spk.f0minimum, f0scalefac=spk.f0scalefac,
        newparagsw=stream.newparagsw)


def synthesize_clauses(
    voice: int, clauses: list[Clause], sprate: int = 180,
) -> list[list[int]]:
    """Run the whole `ph/` chain for an utterance; return the vtm-input frames.

    `clauses` is the utterance split into clauses (one `symbols[]` per clause, as
    the front end emits). One `Pht0draw` and one `send_pars` delay buffer span the
    whole utterance, so F0 state and the frame delay carry across clause
    boundaries exactly as the C speech thread does. The first clause seeds
    `nf0ev = -2` (F0 jumps to its initial value on the first speaker load); the
    rest seed `nf0ev = -1`.
    """
    spk = PH_SPEAKERS[voice]
    frames: list[list[int]] = []
    delayed: dict[int, int] | None = None
    draw: Pht0draw | None = None
    st = PhsettarState(allophons=(), allofeats=(), allodurs=(), nallotot=0,
                       malfem=spk.malfem)
    prev_tilt = 0
    for i, clause in enumerate(clauses):
        stream = _front_end(clause, spk, sprate)
        src = _pht0src(stream, spk)
        seed = -2 if i == 0 else -1
        if draw is None:
            draw = Pht0draw(src, nf0ev=seed)
        else:
            draw.new_clause(src, seed)
        cframes, prev_tilt, delayed = _draw_clause(
            stream, spk, draw, st, prev_tilt, delayed)
        frames.extend(cframes)
    return frames


def speak_phonemes(
    voice: int, clauses: list[Clause], sprate: int = 180,
) -> list[int]:
    """Phoneme+stress+sentstruc stream -> PCM for one voice (`phclause` + `vtm`).

    Runs `synthesize_clauses` and feeds the frames through `vtm.py`
    (`engine.synthesize_frames`), returning 11025 Hz 16-bit mono samples.
    """
    frames = synthesize_clauses(voice, clauses, sprate)
    return synthesize_frames(SPEAKERS[voice], frames)
