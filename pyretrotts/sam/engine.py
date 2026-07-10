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


def _u8_to_s16(pcm8: bytes) -> bytes:
    """Widen SAM's native 8-bit unsigned PCM to 16-bit signed little-endian."""
    return struct.pack(f"<{len(pcm8)}h", *((b - 128) << 8 for b in pcm8))
