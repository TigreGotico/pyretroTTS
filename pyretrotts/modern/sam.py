"""ModernSAM: generate three-oscillator parameters from IPA features.

SAM's renderer (:mod:`pyretrotts.sam.render`) drives three oscillators -- two
sine formants (F1, F2) and a rectangle-wave F3 -- from per-frame frequency codes
and 4-bit amplitudes, and produces consonant noise only from a fixed 1-bit sample
ROM. ModernSAM fills the renderer's ``frequency1/2/3``, ``amplitude1/2/3`` and
``pitches`` arrays directly from the articulatory
:class:`~pyretrotts.modern.features.FeatureBundle`, bypassing SAM's phoneme
tables and reciter, then runs SAM's own inner synthesis loop.

The fidelity ceiling is low and honest. SAM's frequency codes are single bytes
(coarse quantisation), its only true noise source is the 8-bit sample ROM, and
its output is 8-bit unsigned at ~22 kHz. This front end approximates obstruents
with the rectangle oscillator rather than the sample ROM, so fricatives and stops
read as buzzy rather than noisy. Vowels and sonorants -- which SAM's oscillators
can actually voice -- are where the generative approach pays off here.
"""
from __future__ import annotations

from ..ipa import Stress, parse_ipa
from ..sam.engine import _u8_to_s16
from ..sam.render import Renderer
from .features import (
    DECOMPOSABLE_SYMBOLS,
    MANNER_AFFRICATE,
    MANNER_FRICATIVE,
    MANNER_STOP,
    FeatureBundle,
    decompose,
    expand,
    nearest_target,
)

__all__ = ["ModernSAMEngine"]

SAMPLE_RATE = 22050

# Hz -> SAM frequency byte. Calibrated against SAM's own voiced-formant tables:
# with the default mouth/throat knobs, F1 codes span ~10-27 for 270-750 Hz and
# F2 codes ~24-86 for 800-2300 Hz (see render.Renderer.set_mouth_throat).
_F1_DIV = 24
_F2_DIV = 27
_F3_DIV = 28

# 4-bit amplitudes (0..15). F1 carries the most energy.
_AMP_VOWEL = (15, 13, 11)
_AMP_SONORANT = (13, 10, 7)
_AMP_FRIC = (4, 6, 14)     # push energy into the buzzy F3 oscillator
_AMP_SILENCE = (0, 0, 0)

# Per-phone frame counts (SAM frame = one array position).
_DUR_VOWEL = 5
_DUR_CONS = 3

_TARGET_POOL = DECOMPOSABLE_SYMBOLS


def _clamp(v: int, lo: int, hi: int) -> int:
    return lo if v < lo else hi if v > hi else v


class ModernSAMEngine:
    """Generative three-oscillator front end that speaks arbitrary IPA on SAM.

    ``say_ipa`` returns 16-bit mono PCM at 22050 Hz. Expect a buzzy, low-fidelity
    result: this exists to show the feature model driving a second, weaker
    synthesizer, not to rival ModernTalk.
    """

    #: (pitch, mouth, throat) presets, mirroring SAM's manual voices.
    _VOICES = {
        "Sam": (64, 128, 128),
        "Elf": (64, 160, 110),
        "Little Robot": (60, 190, 190),
        "Little Old Lady": (32, 145, 145),
    }

    def __init__(self) -> None:
        self.voices = tuple(self._VOICES)

    def say_ipa(
        self, ipa: str, voice: str | None = None, path: str | None = None
    ) -> bytes:
        """Render ``ipa`` in ``voice``; return PCM and optionally write a WAV."""
        voice = voice or self.voices[0]
        pitch, mouth, throat = self._VOICES[voice]
        renderer = Renderer(speed=72, pitch=pitch, mouth=mouth,
                            throat=throat, singmode=False)
        n = self._fill(renderer, ipa, pitch)
        renderer._process_frames(n)
        pcm = _u8_to_s16(renderer.pcm())
        if path is not None:
            _write_wav(pcm, path, SAMPLE_RATE)
        return pcm

    def bundles(self, ipa: str) -> list[tuple[str, FeatureBundle, bool]]:
        """Decompose ``ipa`` to (symbol, bundle, fell_back) triples."""
        out: list[tuple[str, FeatureBundle, bool]] = []
        for clause in parse_ipa(ipa):
            for phone in clause.phones:
                try:
                    out.append((phone.symbol, decompose(phone.symbol), False))
                except KeyError:
                    tgt = nearest_target(phone.symbol, list(_TARGET_POOL))
                    out.append((phone.symbol, decompose(tgt), True))
        return out

    def _fill(self, r: Renderer, ipa: str, pitch: int) -> int:
        """Write oscillator frames into ``r`` and return the frame count."""
        pos = 0
        for clause in parse_ipa(ipa):
            for phone in clause.phones:
                for seg in expand(phone.symbol):
                    try:
                        b = decompose(seg)
                    except KeyError:
                        b = decompose(nearest_target(seg, list(_TARGET_POOL)))
                    pos = self._emit(r, b, phone.stress, pitch, pos)
                    if pos >= 254:
                        return pos
        return pos

    def _emit(
        self, r: Renderer, b: FeatureBundle, stress: Stress, pitch: int, pos: int
    ) -> int:
        f1 = _clamp(b.f1 // _F1_DIV, 5, 40)
        f2 = _clamp(b.f2 // _F2_DIV, 15, 120)
        f3 = _clamp(b.f3 // _F3_DIV, 60, 150)
        if b.is_vowel:
            dur = _DUR_VOWEL + (2 if b.long else 0)
            amps = _AMP_VOWEL
            frames = [(f1, f2, f3, amps)] * dur
        elif b.manner == MANNER_STOP:
            frames = [(f1, f2, f3, _AMP_SILENCE)] * 2  # closure
            frames += [(f1, f2, f3, _AMP_FRIC)]        # burst
        elif b.manner in (MANNER_FRICATIVE, MANNER_AFFRICATE):
            # Buzzy stand-in for frication via the F3 rectangle oscillator.
            f3 = _clamp(b.fric_center // _F3_DIV, 60, 150)
            frames = [(f1, f2, f3, _AMP_FRIC)] * _DUR_CONS
        else:  # nasal, approximant, lateral, trill, tap
            frames = [(f1, f2, f3, _AMP_SONORANT)] * _DUR_CONS
        pval = _clamp(pitch - (8 if stress == Stress.PRIMARY else 0), 16, 255)
        for f1v, f2v, f3v, (a1, a2, a3) in frames:
            if pos >= 255:
                break
            r.frequency1[pos] = f1v
            r.frequency2[pos] = f2v
            r.frequency3[pos] = f3v
            r.amplitude1[pos] = a1
            r.amplitude2[pos] = a2
            r.amplitude3[pos] = a3
            r.pitches[pos] = pval
            r.sampled_consonant_flag[pos] = 0
            pos += 1
        return pos


def _write_wav(pcm: bytes, path: str, rate: int) -> None:
    import struct

    data = len(pcm)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data, b"WAVE", b"fmt ", 16, 1, 1,
        rate, rate * 2, 2, 16, b"data", data)
    with open(path, "wb") as fh:
        fh.write(header + pcm)
