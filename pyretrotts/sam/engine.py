"""The `SAMEngine`: Software Automatic Mouth behind the shared Engine ABC.

Derived from vidarh/SAM, which is an opcode-by-opcode translation of SoftVoice,
Inc.'s 6502 program; NOT covered by this project's MIT licence; see NOTICE.

SAM has no named voices -- it has four integer knobs (speed, pitch, throat,
mouth). The six presets below are the well-known voices from SAM's manual,
expressed as knob sets. SAM renders 8-bit unsigned PCM natively; `synthesize`
widens it to the 16-bit signed PCM the ABC promises at the very edge.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from functools import lru_cache

from .._dectalk import PHONEMES as _DECTALK_PHONEMES
from .._pitch import fundamental
from ..engines import Engine
from . import sam


@dataclass(frozen=True)
class SamVoice:
    """One SAM voice, as its four render knobs (each 0..255)."""

    speed: int
    pitch: int
    throat: int
    mouth: int


class SAMEngine(Engine):
    """Don't Ask Software's SAM (1982), ported bit-exact from the C source.

    Its input is SAM phoneme mnemonics with stress digits (``/HEHLOW``,
    ``AA5``); plain text is run through SAM's reciter first. Voice character is
    the four knobs, exposed here as six named presets.
    """

    name = "SAM"
    #: SAM phoneme notation: two-char mnemonics, `/` diacritics, stress digits.
    dialect = "/HELLOW"

    #: The manual's voices, as (speed, pitch, throat, mouth) knob presets.
    VOICE_KNOBS = {
        "Sam": SamVoice(72, 64, 128, 128),
        "Elf": SamVoice(72, 64, 110, 160),
        "Little Robot": SamVoice(92, 60, 190, 190),
        "Stuffy Guy": SamVoice(82, 72, 110, 105),
        "Little Old Lady": SamVoice(82, 32, 145, 145),
        "Extra-Terrestrial": SamVoice(100, 64, 150, 200),
    }

    @property
    def voices(self) -> dict[str, SamVoice]:
        """The six preset voices, each a SamVoice knob set (not a Klatt Voice)."""
        return dict(self.VOICE_KNOBS)

    def synthesize(self, source: str, voice: str = "Sam", phonetic: bool = False) -> bytes:
        """Render `source` in `voice`, returning raw 16-bit mono PCM.

        `phonetic=True` treats `source` as SAM phoneme mnemonics directly;
        otherwise the reciter converts English text first.
        """
        knobs = self.VOICE_KNOBS[voice]
        pcm8 = sam.render_pcm(
            source,
            speed=knobs.speed,
            pitch=knobs.pitch,
            mouth=knobs.mouth,
            throat=knobs.throat,
            phonetic=phonetic,
        )
        return _u8_to_s16(pcm8)

    def speak_phonemes(self, source: str, voice: str = "Sam") -> bytes:
        """Render SAM phoneme mnemonics directly, bypassing the reciter."""
        return self.synthesize(source, voice, phonetic=True)

    def _render_ipa(self, clauses: list, voice: str) -> bytes:
        """Render IPA by translating it to SAM mnemonics and voicing them."""
        from ..ipa import ipa_to_native

        source, _fallbacks = ipa_to_native("sam", clauses)
        return self.synthesize(source, voice, phonetic=True)

    def sing(self, source: str, voice: str = "Sam") -> bytes:
        """Sing a DECtalk score, in SAM's voice.

        SAM has a `singmode` that holds pitch flat instead of applying sentence
        inflection, so it can hit a written note once the knobs are solved for
        that note's frequency and length. Every one of DECtalk's phonemes has a
        SAM spelling, though several collapse -- see `DECTALK_TO_SAM`.
        """
        from .._dectalk import parse, tone_to_midi

        knobs = self.VOICE_KNOBS[voice]
        out = bytearray()
        for note in parse(source).notes:
            out += self._render_note(note, knobs, tone_to_midi)
        return _u8_to_s16(bytes(out))

    def _render_note(self, note, knobs: SamVoice, tone_to_midi) -> bytes:
        mnemonic = DECTALK_TO_SAM.get(_DECTALK_MNEMONIC.get(note.phoneme, ""))
        milliseconds = note.duration_ms or _UNTIMED_MS

        if mnemonic is None:  # silence
            return b"\x80" * round(SAMPLE_RATE * milliseconds / 1000)

        if note.tone is None:
            pitch = knobs.pitch
        else:
            # An unstressed vowel drifts below the pitch knob; a stressed one
            # holds it. Only vowels take a stress digit.
            if _is_vowel(mnemonic):
                mnemonic += _SUNG_STRESS
            pitch = tuned_knob(mnemonic, _midi_to_hz(tone_to_midi(note.tone)), knobs)
        source, speed = _solve(mnemonic, milliseconds, knobs, pitch)
        return sam.render_pcm(source, speed=speed, pitch=pitch, mouth=knobs.mouth,
                              throat=knobs.throat, singmode=True, phonetic=True)


def _u8_to_s16(pcm8: bytes) -> bytes:
    """Widen SAM's native 8-bit unsigned PCM to 16-bit signed little-endian."""
    return struct.pack(f"<{len(pcm8)}h", *((b - 128) << 8 for b in pcm8))


# --- singing ---------------------------------------------------------------

#: samples per second SAM renders at
SAMPLE_RATE = 22050

#: how long a phoneme the score does not time gets, in milliseconds
_UNTIMED_MS = 70

#: DECtalk's phoneme mnemonics, in SAM's. Every one of DECtalk's 58 speech
#: sounds has a SAM spelling, though several collapse: SAM has no `yu`, no
#: distinct r-coloured vowels, and one `t` where DECtalk also has `tx`.
DECTALK_TO_SAM = {
    "aa": "AA", "ae": "AE", "ah": "AH", "ao": "AO", "aw": "AW", "ax": "AX",
    "ay": "AY", "eh": "EH", "ey": "EY", "ih": "IH", "ix": "IX", "iy": "IY",
    "ow": "OW", "oy": "OY", "uh": "UH", "uw": "UW", "yu": "UW",
    "er": "ER", "rr": "ER", "ir": "ER", "ar": "AA", "or": "AO", "ur": "UH",
    "xr": "ER", "el": "UL", "en": "UM", "lx": "LX", "rx": "RX",
    "b": "B", "ch": "CH", "d": "D", "dh": "DH", "dx": "DX", "f": "F",
    "g": "G", "h": "/H", "hx": "/H", "jh": "J", "k": "K", "l": "L",
    "m": "M", "n": "N", "ng": "NX", "nx": "NX", "p": "P", "q": "Q",
    "r": "R", "s": "S", "sh": "SH", "t": "T", "th": "TH", "tx": "T",
    "v": "V", "w": "W", "y": "Y", "yx": "YX", "z": "Z", "zh": "ZH",
}

#: phoneme id -> the DECtalk mnemonic that names it
_DECTALK_MNEMONIC: dict[int, str] = {}
for _mnemonic, _phoneme in _DECTALK_PHONEMES.items():
    _DECTALK_MNEMONIC.setdefault(_phoneme, _mnemonic)

# f0 = _PITCH_SCALE / (knob - _PITCH_OFFSET), fitted against the rendered
# fundamental across the knob's usable range. Within 0.5% over C2 to C5.
_PITCH_SCALE = 6813.0
_PITCH_OFFSET = 6.9
_MIN_KNOB, _MAX_KNOB = 8, 255

#: SAM's stress digits run 1..8; the middle one sings a note without colouring it
_SUNG_STRESS = "5"

_REFERENCE_SPEED = 72
#: how far either side of the predicted knob to look for one that lands
_SEARCH = 3
_MIN_SPEED, _MAX_SPEED = 4, 255
_MAX_REPEATS = 16


def _is_vowel(mnemonic: str) -> bool:
    from .phonemes import FLAG_VOWEL, SIGN_INPUT_TABLE1, flags

    for index in range(len(SIGN_INPUT_TABLE1)):
        from .phonemes import mnemonic as name_of
        try:
            if name_of(index).strip() == mnemonic:
                return bool(flags(index) & FLAG_VOWEL)
        except IndexError:
            break
    return False


def pitch_knob(hz: float) -> int:
    """The `pitch` knob whose arithmetic gives a fundamental of `hz`."""
    if hz <= 0:
        return _MAX_KNOB
    return max(_MIN_KNOB, min(_MAX_KNOB, round(_PITCH_SCALE / hz + _PITCH_OFFSET)))


@lru_cache(maxsize=4096)
def tuned_knob(mnemonic: str, hz: float, knobs: SamVoice) -> int:
    """The `pitch` knob that actually renders closest to `hz`.

    SAM's pitch arithmetic is eight-bit and not monotonic: a handful of knob
    values land an octave from where `pitch_knob` predicts. Rendering a short
    probe at each candidate and measuring costs a few milliseconds and is
    cached, so a song pays it once per distinct note.
    """
    model = pitch_knob(hz)
    best, best_error = model, float("inf")
    for candidate in range(max(_MIN_KNOB, model - _SEARCH), min(_MAX_KNOB, model + _SEARCH) + 1):
        pcm8 = sam.render_pcm(mnemonic, speed=_REFERENCE_SPEED, pitch=candidate,
                              mouth=knobs.mouth, throat=knobs.throat,
                              singmode=True, phonetic=True)
        rendered = fundamental(_u8_to_s16(pcm8))
        if rendered <= 0:
            continue
        error = abs(rendered - hz)
        if error < best_error:
            best, best_error = candidate, error
    return best


def _midi_to_hz(midi: int) -> float:
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


def _rendered_ms(source: str, speed: int, knobs: SamVoice, pitch: int) -> float:
    pcm8 = sam.render_pcm(source, speed=speed, pitch=pitch, mouth=knobs.mouth,
                          throat=knobs.throat, singmode=True, phonetic=True)
    return 1000.0 * len(pcm8) / SAMPLE_RATE


def _solve(mnemonic: str, target_ms: int, knobs: SamVoice, pitch: int) -> tuple[str, int]:
    """The phoneme string and `speed` knob that render closest to `target_ms`.

    A phoneme's length is close to linear in the speed knob, so one render
    gives the slope and a second corrects it. The knob saturates at 255, so a
    note too long for one repetition is written as several, which multiply its
    length exactly.
    """
    repeats = 1
    while repeats < _MAX_REPEATS and _rendered_ms(mnemonic * repeats, _MAX_SPEED,
                                                  knobs, pitch) < target_ms:
        repeats += 1
    source = mnemonic * repeats

    reference = _rendered_ms(source, _REFERENCE_SPEED, knobs, pitch)
    if reference <= 0:
        return source, _REFERENCE_SPEED
    speed = max(_MIN_SPEED, min(_MAX_SPEED, round(_REFERENCE_SPEED * target_ms / reference)))

    actual = _rendered_ms(source, speed, knobs, pitch)
    if actual > 0:
        speed = max(_MIN_SPEED, min(_MAX_SPEED, round(speed * target_ms / actual)))
    return source, speed
