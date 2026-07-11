"""ModernTalk: generate Klatt parameter frames from IPA features.

The classic IPA path (:mod:`pyretrotts.ipa`) maps each IPA symbol to the nearest
English phoneme *id* and reads that id's target ROM. ModernTalk instead
generates the ~20-slot Klatt parameter frames directly from the articulatory
:class:`~pyretrotts.modern.features.FeatureBundle`, then renders them through
DECtalk's bit-exact vocal tract model (:func:`pyretrotts.dectalk.engine.
synthesize_frames`). The synthesizer core is untouched and exact; only the front
end -- the stage that decides what frames to feed it -- is generative, so any IPA
phone drives real formant synthesis instead of being replaced by an English
preset.

Frame slots are the ``pyretrotts.dectalk.consts.OUT_*`` indices: F1/F2/F3 and
their bandwidths, the nasal zero FZ, the pitch period T0, and the source
amplitudes AV (voicing), AP (aspiration), AB (bypass/frication) and A2..A6
(parallel-formant frication levels), all in the units the C engine consumed.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..dectalk import consts as C
from ..dectalk.engine import frames_to_wav, synthesize_frames
from ..dectalk.voices import SPEAKERS, VOICE_NAMES
from ..ipa import Stress, parse_ipa
from .features import (
    DECOMPOSABLE_SYMBOLS,
    MANNER_AFFRICATE,
    MANNER_APPROXIMANT,
    MANNER_FRICATIVE,
    MANNER_LATERAL,
    MANNER_NASAL,
    MANNER_STOP,
    MANNER_TAP,
    MANNER_TRILL,
    FeatureBundle,
    decompose,
    expand,
    nearest_target,
)

__all__ = ["ModernTalkEngine", "FrameSpec"]

SAMPLE_RATE_HZ = C.SAMPLE_RATE_HZ  # 11025
_FRAME_MS = C.SAMPLES_PER_FRAME / SAMPLE_RATE_HZ * 1000.0  # ~6.44 ms

# Amplitude levels (dB, as the AMPTABLE index the C engine expects).
_AV_FULL = 60          # full voicing for vowels
_AV_MURMUR = 52        # nasal / voiced-consonant murmur
_AV_APPROX = 56        # approximants and liquids
_AV_BAR = 38           # voice bar under a voiced obstruent closure
_AB_FRIC = 56          # strong frication through the bypass path
_AP_ASPIR = 58         # aspiration / /h/ noise
_BURST = 52            # stop-burst parallel level

# Default per-phone durations in frames (before length/stress scaling).
_DUR = {
    "vowel": 13,
    MANNER_STOP: 4,     # closure; the burst adds one more
    MANNER_FRICATIVE: 9,
    MANNER_AFFRICATE: 8,
    MANNER_NASAL: 8,
    MANNER_APPROXIMANT: 7,
    MANNER_LATERAL: 7,
    MANNER_TRILL: 8,
    MANNER_TAP: 3,
}

# All decomposable symbols, used as the fallback target pool.
_TARGET_POOL = DECOMPOSABLE_SYMBOLS


@dataclass(frozen=True)
class FrameSpec:
    """One Klatt frame plus whether its formants may be smoothed into.

    ``smooth`` is False for stop closures and bursts, whose crisp on/offsets
    carry the place cue and must not be averaged away.
    """

    frame: tuple[int, ...]
    smooth: bool = True


def _blank() -> list[int]:
    f = [0] * 20
    f[C.OUT_F1] = 500
    f[C.OUT_F2] = 1500
    f[C.OUT_F3] = 2500
    f[C.OUT_FZ] = 290
    f[C.OUT_B1] = 60
    f[C.OUT_B2] = 90
    f[C.OUT_B3] = 150
    f[C.OUT_TLT] = 8
    f[C.OUT_DU] = 1
    # A valid pitch period even on silent frames: a zero T0 divides by zero in
    # the glottal loop and latches the oscillator dead for the rest of the run.
    f[C.OUT_T0] = 328  # ~122 Hz
    return f


def _set_pitch(f: list[int], f0_hz: float) -> None:
    # Empirically T0 ~= 40000 / F0 for the 11025 Hz oversampled glottal loop.
    f[C.OUT_T0] = max(60, min(1200, round(40000.0 / max(50.0, f0_hz))))


def _voiced_phone(f: list[int], b: FeatureBundle, av: int) -> None:
    f[C.OUT_F1] = b.f1
    f[C.OUT_F2] = b.f2
    f[C.OUT_F3] = b.f3
    f[C.OUT_AV] = av
    f[C.OUT_PH] = 0x1E11  # nonzero: keep the limit-cycle ramp disengaged
    f[C.OUT_PH2] = 0x1E11
    if b.nasal:
        # Engage the nasal branch: drop the antiresonator zero and widen B1.
        f[C.OUT_FZ] = 250
        f[C.OUT_B1] = 120


def _frication(f: list[int], b: FeatureBundle) -> None:
    """Shape the parallel/bypass branch so noise sits near ``b.fric_center``."""
    f[C.OUT_F2] = b.f2
    f[C.OUT_F3] = max(1600, b.fric_center if b.fric_center < 3000 else b.f3)
    f[C.OUT_PH] = 0x1E11
    f[C.OUT_PH2] = 0x1E11
    center = b.fric_center
    if center >= 4000:            # sibilant /s z/: high-frequency bypass
        f[C.OUT_AB] = _AB_FRIC
        f[C.OUT_A6] = _AB_FRIC
        f[C.OUT_A5] = _AB_FRIC - 4
    elif center >= 2500:          # /ʃ ʒ/, palatal: upper-mid band
        f[C.OUT_A5] = _AB_FRIC
        f[C.OUT_A4] = _AB_FRIC - 2
        f[C.OUT_A3] = _AB_FRIC - 8
    else:                         # velar/uvular/pharyngeal/bilabial: low band
        f[C.OUT_A2] = _AB_FRIC - 4
        f[C.OUT_A3] = _AB_FRIC - 2
        f[C.OUT_AB] = _AB_FRIC - 10
    if b.voiced:
        f[C.OUT_AV] = _AV_MURMUR
        f[C.OUT_F1] = 300


class ModernTalkEngine:
    """Generative Klatt front end that speaks arbitrary IPA.

    ``say_ipa`` accepts any IPA string -- English or not -- and returns 16-bit
    mono PCM at 11025 Hz. Symbols the feature model cannot decompose fall back to
    the articulatorily nearest reachable target rather than an English preset.
    """

    #: base F0 (Hz) per DECtalk speaker; higher voices get a higher pitch floor
    _BASE_F0 = {
        "Perfect Paul": 122, "Huge Harry": 90, "Frail Frank": 105,
        "Doctor Dennis": 110, "Beautiful Betty": 210, "Kit the Kid": 260,
        "Uppity Ursula": 200, "Rough Rita": 190, "Whispering Wendy": 200,
        "Variable Val": 130,
    }

    def __init__(self) -> None:
        self.voices = VOICE_NAMES

    # -- public API ---------------------------------------------------------
    def say_ipa(
        self, ipa: str, voice: str | None = None, path: str | None = None
    ) -> bytes:
        """Render ``ipa`` in ``voice``; return PCM and optionally write a WAV."""
        voice = voice or self.voices[0]
        speaker = SPEAKERS[VOICE_NAMES.index(voice)]
        frames = self._frames_for(ipa, voice)
        pcm = _pack(synthesize_frames(speaker, frames))
        if path is not None:
            with open(path, "wb") as fh:
                fh.write(frames_to_wav(speaker, frames))
        return pcm

    def synthesize_ipa(self, ipa: str, voice: str | None = None) -> list[int]:
        """Return the raw 16-bit sample list for ``ipa``."""
        voice = voice or self.voices[0]
        speaker = SPEAKERS[VOICE_NAMES.index(voice)]
        return synthesize_frames(speaker, self._frames_for(ipa, voice))

    def bundles(self, ipa: str) -> list[tuple[str, FeatureBundle, bool]]:
        """Decompose ``ipa`` to (symbol, bundle, fell_back) triples.

        ``fell_back`` marks symbols resolved through :func:`nearest_target`.
        """
        out: list[tuple[str, FeatureBundle, bool]] = []
        for clause in parse_ipa(ipa):
            for phone in clause.phones:
                segs = expand(phone.symbol)
                bundle, fell = self._bundle(segs[0])
                fell = any(self._bundle(s)[1] for s in segs)
                out.append((phone.symbol, bundle, fell))
        return out

    # -- frame generation ---------------------------------------------------
    def _bundle(self, symbol: str) -> tuple[FeatureBundle, bool]:
        try:
            return decompose(symbol), False
        except KeyError:
            target = nearest_target(symbol, list(_TARGET_POOL))
            return decompose(target), True

    def _frames_for(self, ipa: str, voice: str) -> list[list[int]]:
        base_f0 = self._BASE_F0.get(voice, 122)
        frames: list[FrameSpec] = []
        # Lead-in silence primes the post-speaker-definition ramp.
        for _ in range(3):
            frames.append(FrameSpec(tuple(_blank()), smooth=False))

        clauses = parse_ipa(ipa)
        for clause in clauses:
            rising = clause.terminator == "?"
            n_phones = max(1, len(clause.phones))
            for idx, phone in enumerate(clause.phones):
                # Declination plus a stress bump; a question rises at the end.
                pos = idx / n_phones
                f0 = base_f0 * (1.0 - 0.18 * pos)
                if phone.stress == Stress.PRIMARY:
                    f0 *= 1.12
                elif phone.stress == Stress.SECONDARY:
                    f0 *= 1.05
                if rising and idx >= n_phones - 2:
                    f0 *= 1.15
                segments = expand(phone.symbol)
                for seg in segments:
                    bundle, _ = self._bundle(seg)
                    frames.extend(self._phone_frames(
                        bundle, phone.stress, f0, glide=len(segments) > 1))
            # A short pause between clauses.
            for _ in range(4):
                frames.append(FrameSpec(tuple(_blank()), smooth=False))

        return _smooth_formants(frames)

    def _phone_frames(
        self, b: FeatureBundle, stress: Stress, f0: float, glide: bool = False
    ) -> list[FrameSpec]:
        if b.is_vowel:
            return self._vowel(b, stress, f0, glide)
        if b.manner == MANNER_STOP:
            return self._stop(b, f0)
        if b.manner == MANNER_AFFRICATE:
            return self._stop(b, f0) + self._fricative(b, f0, frames=5)
        if b.manner == MANNER_FRICATIVE:
            return self._fricative(b, f0, frames=_DUR[MANNER_FRICATIVE])
        if b.manner == MANNER_NASAL:
            return self._sonorant(b, f0, _AV_MURMUR, _DUR[MANNER_NASAL])
        if b.manner == MANNER_TRILL:
            return self._trill(b, f0)
        if b.manner == MANNER_TAP:
            return self._sonorant(b, f0, _AV_APPROX, _DUR[MANNER_TAP])
        # approximant / lateral
        dur = _DUR.get(b.manner, 7)
        return self._sonorant(b, f0, _AV_APPROX, dur)

    def _vowel(
        self, b: FeatureBundle, stress: Stress, f0: float, glide: bool = False
    ) -> list[FrameSpec]:
        dur = _DUR["vowel"]
        if glide:               # one half of a diphthong: keep it short
            dur = 7
        if b.long:
            dur = round(dur * 1.6)
        if stress == Stress.PRIMARY:
            dur += 3
        av = _AV_FULL if stress != Stress.NONE else _AV_FULL - 3
        out = []
        for _ in range(dur):
            f = _blank()
            _voiced_phone(f, b, av)
            _set_pitch(f, f0)
            out.append(FrameSpec(tuple(f)))
        return out

    def _sonorant(
        self, b: FeatureBundle, f0: float, av: int, dur: int
    ) -> list[FrameSpec]:
        out = []
        for _ in range(dur):
            f = _blank()
            _voiced_phone(f, b, av)
            if b.lateral:
                f[C.OUT_F3] = min(b.f3, 2500)
                f[C.OUT_B3] = 250
            _set_pitch(f, f0)
            out.append(FrameSpec(tuple(f)))
        return out

    def _stop(self, b: FeatureBundle, f0: float) -> list[FrameSpec]:
        out = []
        # Closure: silence, or a faint voice bar for a voiced stop. PH=0 lets the
        # limit-cycle ramp pull the tail to true silence.
        for _ in range(_DUR[MANNER_STOP]):
            f = _blank()
            if b.voiced:
                f[C.OUT_AV] = _AV_BAR
                f[C.OUT_F1] = 220
                f[C.OUT_PH] = 0x1E11
                f[C.OUT_PH2] = 0x1E11
                _set_pitch(f, f0)
            out.append(FrameSpec(tuple(f), smooth=False))
        # Burst: brief noise at the place's spectral centre, plus aspiration for
        # a voiceless (or aspirated) release.
        burst = _blank()
        burst[C.OUT_F2] = b.f2
        burst[C.OUT_F3] = b.f3
        burst[C.OUT_PH] = 0x1E11
        burst[C.OUT_PH2] = 0x1E11
        if b.fric_center >= 3500:
            burst[C.OUT_A5] = _BURST
            burst[C.OUT_A6] = _BURST
        elif b.fric_center >= 2000:
            burst[C.OUT_A4] = _BURST
            burst[C.OUT_A5] = _BURST
        else:
            burst[C.OUT_A2] = _BURST
            burst[C.OUT_A3] = _BURST
        if not b.voiced or b.aspirated:
            burst[C.OUT_AP] = _AP_ASPIR
        out.append(FrameSpec(tuple(burst), smooth=False))
        # A voiceless stop gets a short aspiration tail so the release is heard
        # as a distinct segment rather than blurring into the next vowel.
        if not b.voiced:
            aspir = _blank()
            aspir[C.OUT_F2] = b.f2
            aspir[C.OUT_F3] = b.f3
            aspir[C.OUT_AP] = _AP_ASPIR - 8
            aspir[C.OUT_PH] = 0x1E11
            aspir[C.OUT_PH2] = 0x1E11
            out.append(FrameSpec(tuple(aspir), smooth=False))
        return out

    def _fricative(self, b: FeatureBundle, f0: float, frames: int) -> list[FrameSpec]:
        out = []
        for _ in range(frames):
            f = _blank()
            _frication(f, b)
            if b.voiced:
                _set_pitch(f, f0)
            # /h/ family: pure aspiration through the cascade, no bypass noise.
            if b.place == "glottal":
                f[C.OUT_AB] = 0
                f[C.OUT_A2] = f[C.OUT_A3] = f[C.OUT_A5] = f[C.OUT_A6] = 0
                f[C.OUT_AP] = _AP_ASPIR
            out.append(FrameSpec(tuple(f), smooth=(b.place != "glottal")))
        return out

    def _trill(self, b: FeatureBundle, f0: float) -> list[FrameSpec]:
        # Approximate a trill by amplitude-modulating a voiced approximant.
        out = []
        for i in range(_DUR[MANNER_TRILL]):
            f = _blank()
            _voiced_phone(f, b, _AV_APPROX if i % 2 == 0 else _AV_BAR)
            _set_pitch(f, f0)
            out.append(FrameSpec(tuple(f), smooth=False))
        return out


def _smooth_formants(specs: list[FrameSpec]) -> list[list[int]]:
    """Three-point moving average of F1/F2/F3 over smoothable frames.

    This is the coarticulation model: formants glide across phone boundaries
    instead of jumping, giving the transitions a listener uses to hear place.
    Stops and bursts (``smooth=False``) are excluded so their cues stay crisp.
    """
    frames = [list(s.frame) for s in specs]
    slots = (C.OUT_F1, C.OUT_F2, C.OUT_F3)
    out = [list(f) for f in frames]
    n = len(frames)
    for i in range(n):
        if not specs[i].smooth:
            continue
        for slot in slots:
            acc = frames[i][slot]
            cnt = 1
            for j in (i - 1, i + 1):
                # Only glide into other smoothable, sound-bearing frames; never
                # average a vowel's formants toward a silent frame's defaults,
                # which would erase the vowel's identity.
                if 0 <= j < n and specs[j].smooth and frames[j][C.OUT_AV] > 0:
                    acc += frames[j][slot]
                    cnt += 1
            out[i][slot] = acc // cnt
    return out


def _pack(samples: list[int]) -> bytes:
    import struct

    return struct.pack(f"<{len(samples)}h", *samples)
