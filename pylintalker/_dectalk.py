"""The classic DECtalk markup dialect: `[: ]` commands and singing notation.

DECtalk is a different engine from the MacinTalk synthesizer this package
ports, but the two are close relatives -- both descend from Klatt's formant
synthesis -- and they share a phoneme inventory almost exactly. This module
reads DECtalk's markup and compiles it onto MacinTalk's phoneme plan, so the
large corpus of hand-written DECtalk songs can be voiced.

Two dialects, side by side:

    MacinTalk   [[pbas 60]] [[rate 240]] [[note 60.4]]
    DECtalk     [:ra 170] [:dv ap 90] weh<250,13>

A phoneme in DECtalk singing carries its own duration and pitch:
`weh<250,13>` is the phonemes `w` and `eh`, lasting 250 ms, on tone 13.
Silence is `_`, so `_<500>` is half a second of nothing.

See docs/history.md for how the two engines relate, and
docs/dectalk-port-plan.md for the state of the native DECtalk port.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from ._consts import kFrameTime
from ._phonemes import (
    _AA_,
    _AE_,
    _AH_,
    _AO_,
    _AR_,
    _AW_,
    _AX_,
    _AY_,
    _CH_,
    _DH_,
    _DX_,
    _EH_,
    _EL_,
    _EN_,
    _ER_,
    _EY_,
    _IH_,
    _IR_,
    _IX_,
    _IY_,
    _JH_,
    _LX_,
    _NG_,
    _OR_,
    _OW_,
    _OY_,
    _QX_,
    _RX_,
    _SH_,
    _SIL_,
    _TH_,
    _TX_,
    _UH_,
    _UR_,
    _UW_,
    _XR_,
    _YU_,
    _ZH_,
    _b_,
    _d_,
    _f_,
    _g_,
    _h_,
    _k_,
    _l_,
    _m_,
    _n_,
    _p_,
    _r_,
    _s_,
    _t_,
    _v_,
    _w_,
    _y_,
    _z_,
)

__all__ = ["DECtalkScore", "Note", "Segment", "parse", "PHONEMES", "VOICE_SELECTS"]

#: DECtalk's phoneme mnemonics, mapped onto this engine's phoneme ids. Written
#: lowercase, as the corpus writes them; matching is case-insensitive.
PHONEMES: dict[str, int] = {
    # vowels
    "aa": _AA_, "ae": _AE_, "ah": _AH_, "ao": _AO_, "aw": _AW_,
    "ax": _AX_, "ay": _AY_, "eh": _EH_, "ey": _EY_, "ih": _IH_,
    "ix": _IX_, "iy": _IY_, "ow": _OW_, "oy": _OY_, "uh": _UH_,
    "uw": _UW_, "yu": _YU_,
    # r-coloured vowels and syllabics
    "er": _ER_, "rr": _ER_, "ir": _IR_, "ar": _AR_, "or": _OR_,
    "ur": _UR_, "xr": _XR_, "el": _EL_, "en": _EN_,
    "lx": _LX_, "rx": _RX_,
    # consonants
    "b": _b_, "ch": _CH_, "d": _d_, "dh": _DH_, "dx": _DX_,
    "f": _f_, "g": _g_, "h": _h_, "hx": _h_, "jh": _JH_,
    "k": _k_, "l": _l_, "m": _m_, "n": _n_, "ng": _NG_, "nx": _NG_,
    "p": _p_, "q": _QX_, "r": _r_, "s": _s_, "sh": _SH_,
    "t": _t_, "th": _TH_, "tx": _TX_, "v": _v_, "w": _w_,
    "y": _y_, "yx": _y_, "z": _z_, "zh": _ZH_,
    # silence
    "_": _SIL_,
}

_MAX_MNEMONIC = max(len(k) for k in PHONEMES)

#: `[:n?]` voice selects, and the DECtalk voice each names.
VOICE_SELECTS: dict[str, str] = {
    "np": "Perfect Paul",
    "nb": "Beautiful Betty",
    "nh": "Huge Harry",
    "nf": "Frail Frank",
    "nd": "Doctor Dennis",
    "nk": "Kit the Kid",
    "nu": "Uppity Ursula",
    "nr": "Rough Rita",
    "nw": "Whispering Wendy",
    "nv": "Variable Val",
}

# A command's arguments run to the closing bracket, or to the next command --
# real scores routinely omit the closing bracket, e.g. `[:ra 170 [:dv hs 95]`.
_COMMAND = re.compile(r"\[:\s*([a-zA-Z]+)((?:(?!\[:)[^\]])*)\]?")
_NOTE = re.compile(r"<\s*(\d+)\s*(?:,\s*(\d+)\s*)?>")


@dataclass(frozen=True)
class Note:
    """One phoneme, with the duration and pitch the score gives it."""

    phoneme: int
    #: milliseconds; None when the score leaves this phoneme's length to the engine
    duration_ms: int | None = None
    #: DECtalk's tone number, verbatim. See `tone_to_midi`.
    tone: int | None = None

    @property
    def frames(self) -> int | None:
        """`duration_ms` in synthesizer frames, or None."""
        if self.duration_ms is None:
            return None
        return max(1, self.duration_ms // kFrameTime)


@dataclass(frozen=True)
class Segment:
    """A run of notes sung by one voice, at one rate.

    Songs commonly alternate voices -- a duet is written as `[:np] ... [:nu]
    ... [:np] ...` -- so a score is a sequence of segments, not one setting.
    """

    notes: list[Note] = field(default_factory=list)
    #: the DECtalk voice named by the `[:n?]` command in force
    voice: str | None = None
    #: words per minute, from `[:ra N]`
    rate: int | None = None
    #: `[:dv]` parameters, e.g. {"hs": 95, "br": 0, "ap": 90}
    voice_params: dict[str, int] = field(default_factory=dict)

    @property
    def duration_ms(self) -> int:
        return sum(n.duration_ms or 0 for n in self.notes)


@dataclass(frozen=True)
class DECtalkScore:
    """A parsed DECtalk document."""

    segments: list[Segment] = field(default_factory=list)
    #: True once `[:phone on]` has been seen
    phoneme_mode: bool = False
    #: any plain text outside phoneme mode
    text: str = ""

    @property
    def notes(self) -> list[Note]:
        return [n for seg in self.segments for n in seg.notes]

    @property
    def voices(self) -> list[str]:
        """Every voice the score calls for, in first-use order."""
        seen = []
        for seg in self.segments:
            if seg.voice and seg.voice not in seen:
                seen.append(seg.voice)
        return seen

    @property
    def duration_ms(self) -> int:
        return sum(seg.duration_ms for seg in self.segments)


# `set_user_target` (`ph_drwt01.c:1955-1984`) reads the tone by magnitude:
# 1..37 is a musical note index, one per semitone, looked up in `notetab[]`
# ("Notes in F0*10 from C2 to C5", `p_us_rom_1997.c:1188`) -- 1 is C2 at 64 Hz,
# 13 is C3, 25 is C4, 37 is C5 at 512 Hz. Anything larger is an absolute
# frequency in Hz, clamped to LOWEST_F0..HIGHEST_F0. The boundary is 37.
TONE_MAX_NOTE = 37
_TONE_MIDI_BASE = 35   # tone 1 -> MIDI 36 (C2); tone 37 -> MIDI 72 (C5)
LOWEST_F0_HZ = 50.0
HIGHEST_F0_HZ = 512.1


def hz_to_midi(hz: float) -> int:
    """A frequency as the nearest MIDI note."""
    if hz <= 0:
        return 0
    return max(0, min(127, round(69 + 12 * math.log2(hz / 440.0))))


def tone_to_midi(tone: int) -> int:
    """DECtalk's tone number as a MIDI note.

    A tone of 37 or less is a scale degree; anything larger is a frequency in
    Hz, clamped the way the engine clamps it.
    """
    if tone <= TONE_MAX_NOTE:
        return _TONE_MIDI_BASE + tone
    return hz_to_midi(min(HIGHEST_F0_HZ, max(LOWEST_F0_HZ, float(tone))))


def _split_mnemonics(stream: str) -> list[int]:
    """Greedy longest-match over `PHONEMES`, as the C tokenizer does.

    Characters matching nothing are skipped, mirroring the reference's habit of
    ignoring what it cannot parse.
    """
    out: list[int] = []
    i, n = 0, len(stream)
    while i < n:
        if stream[i].isspace():
            i += 1
            continue
        for width in range(_MAX_MNEMONIC, 0, -1):
            chunk = stream[i:i + width].lower()
            if chunk in PHONEMES:
                out.append(PHONEMES[chunk])
                i += width
                break
        else:
            i += 1
    return out


def _apply_command(name: str, args: str, state: dict) -> None:
    """Apply one `[: ]` command to the running parser state."""
    name = name.lower()
    args = args.strip()
    fields = args.split()

    if name == "phone":
        state["phoneme_mode"] = not args.lower().startswith("off")
    elif name == "ra" and fields and fields[0].isdigit():
        state["rate"] = int(fields[0])
    elif name == "dv":
        for key, value in zip(fields[::2], fields[1::2], strict=False):
            if value.lstrip("-").isdigit():
                state["voice_params"][key.lower()] = int(value)
    elif name in VOICE_SELECTS:
        state["voice"] = VOICE_SELECTS[name]
    # Anything else -- comments, markers, controls with no counterpart here --
    # is dropped, as an unrecognized bracket command is dropped in _embeddedcmd.


def _read_notes(chunk: str) -> list[Note]:
    """Read a phoneme-mode span into notes.

    A `<duration,tone>` annotation belongs to the phoneme immediately before
    it; earlier phonemes in the same run take their length from the engine.
    """
    notes: list[Note] = []
    chunk = chunk.replace("[", " ").replace("]", " ")
    pos = 0
    for match in _NOTE.finditer(chunk):
        run = _split_mnemonics(chunk[pos:match.start()])
        for phon in run[:-1]:
            notes.append(Note(phon))
        if run:
            notes.append(Note(
                run[-1],
                duration_ms=int(match.group(1)),
                tone=int(match.group(2)) if match.group(2) else None,
            ))
        pos = match.end()
    notes.extend(Note(p) for p in _split_mnemonics(chunk[pos:]))
    return notes


def parse(source: str) -> DECtalkScore:
    """Parse a DECtalk document into a `DECtalkScore`.

    Commands take effect where they appear. A change of voice, rate, or voice
    parameters ends the current segment and starts a new one, which is how a
    duet -- `[:np] ... [:nu] ... [:np] ...` -- becomes three segments.
    """
    state = {"phoneme_mode": False, "voice": None, "rate": None, "voice_params": {}}
    segments: list[Segment] = []
    pending: list[Note] = []
    plain: list[str] = []

    def settings() -> tuple:
        return (state["voice"], state["rate"], tuple(sorted(state["voice_params"].items())))

    def bank(under: tuple) -> None:
        if pending:
            voice, rate, params = under
            segments.append(Segment(list(pending), voice, rate, dict(params)))
            pending.clear()

    def consume(chunk: str) -> None:
        if not chunk.strip():
            return
        if state["phoneme_mode"]:
            pending.extend(_read_notes(chunk))
        else:
            plain.append(chunk)

    pos = 0
    for match in _COMMAND.finditer(source):
        consume(source[pos:match.start()])
        before = settings()
        _apply_command(match.group(1), match.group(2), state)
        if settings() != before:
            bank(before)
        pos = match.end()
    consume(source[pos:])
    bank(settings())

    return DECtalkScore(
        segments=segments,
        phoneme_mode=state["phoneme_mode"],
        text=" ".join(" ".join(plain).split()),
    )
