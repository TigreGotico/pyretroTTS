"""The engines this package speaks for.

    from pyretrotts.engines import MacInTalkEngine, DECtalkEngine

    MacInTalkEngine().say("hello, this is a test.", "out.wav")
    DECtalkEngine().sing(open("song.EN").read(), "song.wav")

`MacInTalkEngine` is a bit-exact port of Apple's MacinTalk 2/3 synthesizer.
`DECtalkEngine` reads DECtalk's markup and singing notation; until the DECtalk
synthesizer itself is ported (see docs/dectalk-port-plan.md) it voices that
markup through the MacinTalk synthesizer, which is a close relative but not the
same instrument.
"""
from __future__ import annotations

import struct
from abc import ABC, abstractmethod

from . import _data, _dectalk
from ._consts import SamplingRate, kFrameTime
from ._dectalk import DECtalkScore, Note, Segment, tone_to_midi
from ._phonemes import _SIL_
from ._voice import Voice
from .api import pcm_to_wav, synthesize_phonemes, synthesize_text

__all__ = ["Engine", "MacInTalkEngine", "DECtalkEngine", "SAMEngine"]

#: default length for a phoneme the score does not time, in milliseconds
_UNTIMED_MS = 70


def _load_native_dict():
    """Locate and load the FONIX `dtalk_us.dic`, or return None if unavailable.

    Searched at `$DECTALK_DIR/dtalk_us.dic` and the built oracle `dist/`. The
    dictionary is FONIX data, not shipped; without it the native DECtalk path is
    unavailable and rendering falls back to the MacinTalk substitute voices.
    """
    import glob
    import os

    from .dectalk.dictionary import Dictionary

    candidates: list[str] = []
    env = os.environ.get("DECTALK_DIR")
    if env:
        candidates.append(os.path.join(env, "dtalk_us.dic"))
    candidates += glob.glob(
        os.path.expanduser("~/AgentWorkspaces/ovos/dectalk-c/dist/dic/dtalk_us.dic"))
    for path in candidates:
        if os.path.exists(path):
            try:
                return Dictionary.load(path)
            except Exception:
                return None
    return None


class Engine(ABC):
    """A speech synthesizer: text or markup in, 16-bit mono PCM out."""

    #: human-readable engine name
    name: str
    #: the inline markup this engine understands
    dialect: str

    @property
    @abstractmethod
    def voices(self) -> dict[str, Voice]:
        """Every voice this engine can speak in, by name."""

    @abstractmethod
    def synthesize(self, source: str, voice: str) -> bytes:
        """Render `source` in `voice`, returning raw 16-bit mono PCM."""

    def say(self, source: str, path: str, voice: str | None = None) -> str:
        """Render `source` and write it to a WAV file. Returns the path."""
        voice = voice or next(iter(self.voices))
        return pcm_to_wav(self.synthesize(source, voice), path)

    @property
    def sample_rate(self) -> int:
        return SamplingRate


class MacInTalkEngine(Engine):
    """Apple's MacinTalk 2/3, ported bit-exact from the original C.

    Understands `[[...]]` inline commands: `[[pbas 60]]`, `[[rate 240]]`,
    `[[note 60.4]]`, `[[char LTRL]]`, and the rest. See docs/architecture.md.
    """

    name = "MacinTalk"
    dialect = "[[...]]"

    VOICE_NAMES = (
        "Fred", "Kathy", "Princess", "Junior", "Ralph", "Whisper", "Zarvox",
        "Trinoids", "Bubbles", "Boing", "Bells", "Hysterical", "Deranged",
        "GoodNews", "BadNews", "PipeOrgan", "Cellos",
    )

    @property
    def voices(self) -> dict[str, Voice]:
        return {n: getattr(_data, f"{n}_Voice") for n in self.VOICE_NAMES}

    def synthesize(self, source: str, voice: str = "Fred") -> bytes:
        return synthesize_text(self.voices[voice], source)


class DECtalkEngine(Engine):
    """DECtalk's markup and singing notation, voiced on the MacinTalk synthesizer.

    Understands `[: ]` commands -- `[:phone on]`, `[:ra 170]`, `[:dv ...]`, and
    the `[:n?]` voice selects -- and the singing notation `weh<250,13>`, where
    a phoneme carries its own duration in milliseconds and its own pitch.

    The DECtalk synthesizer is not ported yet, so its ten voices are
    approximated by the nearest MacinTalk voice. The notes, rhythm and phonemes
    are the score's; the timbre is not DECtalk's.
    """

    name = "DECtalk"
    dialect = "[: ]"

    #: DECtalk's voices, and the nearest MacinTalk voice standing in for each.
    VOICE_SUBSTITUTES = {
        "Perfect Paul": "Fred",
        "Beautiful Betty": "Kathy",
        "Huge Harry": "Ralph",
        "Frail Frank": "Junior",
        "Doctor Dennis": "Fred",
        "Kit the Kid": "Princess",
        "Uppity Ursula": "Princess",
        "Rough Rita": "Kathy",
        "Whispering Wendy": "Whisper",
        "Variable Val": "Fred",
    }

    #: native DECtalk voice index (`-s N`) per voice name.
    _NATIVE_INDEX = {name: i for i, name in enumerate((
        "Perfect Paul", "Beautiful Betty", "Huge Harry", "Frail Frank",
        "Doctor Dennis", "Kit the Kid", "Uppity Ursula", "Rough Rita",
        "Whispering Wendy", "Variable Val"))}

    def __init__(self, backend: MacInTalkEngine | None = None) -> None:
        self._backend = backend or MacInTalkEngine()
        self._native_dict = _load_native_dict()

    def _native_synthesize(self, text: str, voice: str) -> bytes | None:
        """Render plain text through the ported DECtalk chain, or None if it can't.

        The DECtalk synthesizer runs at 11025 Hz; its output is doubled to the
        22050 Hz this engine reports, so every voice speaks at one rate. Requires
        the FONIX `dtalk_us.dic`; when it is absent (as in CI) this returns None
        and `synthesize` falls back to the MacinTalk substitute.
        """
        if self._native_dict is None or voice not in self._NATIVE_INDEX:
            return None
        from .dectalk.consts import SAMPLE_RATE_HZ
        from .dectalk.sentence_us import sentence_to_pcm

        native = sentence_to_pcm(self._NATIVE_INDEX[voice], text, self._native_dict)
        return _upsample_2x(native) if SAMPLE_RATE_HZ * 2 == SamplingRate else native

    @property
    def voices(self) -> dict[str, Voice]:
        """The DECtalk voice names, each bound to its MacinTalk substitute."""
        macintalk = self._backend.voices
        return {name: macintalk[sub] for name, sub in self.VOICE_SUBSTITUTES.items()}

    def parse(self, source: str) -> DECtalkScore:
        return _dectalk.parse(source)

    def synthesize(self, source: str, voice: str = "Perfect Paul") -> bytes:
        """Render a DECtalk document, singing it if it carries a score."""
        score = self.parse(source)
        if score.notes:
            return self.render(score, default_voice=voice)
        text = score.text or source
        native = self._native_synthesize(text, voice)
        if native is not None:
            return native
        return self._backend.synthesize(text, self.VOICE_SUBSTITUTES[voice])

    def sing(self, source: str, path: str, voice: str = "Perfect Paul") -> str:
        return pcm_to_wav(self.synthesize(source, voice), path)

    def render(self, score: DECtalkScore, default_voice: str = "Perfect Paul") -> bytes:
        """Render a parsed score, honouring each segment's voice."""
        out = bytearray()
        for segment in score.segments:
            out += self._render_segment(segment, segment.voice or default_voice)
        return scale_to_headroom(bytes(out))

    def _render_segment(self, segment: Segment, voice: str) -> bytes:
        base = self.voices.get(voice) or self.voices["Perfect Paul"]
        out = bytearray()
        for tone, run in _runs_by_tone(segment.notes):
            out += self._render_run(base, run, tone)
        return bytes(out)

    def _render_run(self, base: Voice, run: list[Note], tone: int | None) -> bytes:
        """Render a run of phonemes that share one pitch."""
        phonemes = [n.phoneme for n in run]
        durs = [n.frames if n.frames is not None else _UNTIMED_MS // kFrameTime for n in run]

        if all(p == _SIL_ for p in phonemes):
            # A rest. The synthesizer would give it a glottal onset; silence is
            # cheaper and is what the score asks for.
            frames = sum(durs)
            return b"\x00\x00" * (frames * (SamplingRate * kFrameTime // 1000))

        voice = _singing_voice(base, tone)
        return synthesize_phonemes(voice, phonemes, [0] * len(phonemes), durs)


def _runs_by_tone(notes: list[Note]) -> list[tuple[int | None, list[Note]]]:
    """Group consecutive notes that share a pitch.

    A note with no tone of its own sustains the pitch in force, which is how
    the notation writes consonants leading into a sung vowel.
    """
    runs: list[tuple[int | None, list[Note]]] = []
    current: int | None = None
    for note in notes:
        if note.tone is not None:
            current = note.tone
        if runs and runs[-1][0] == current:
            runs[-1][1].append(note)
        else:
            runs.append((current, [note]))
    return runs


def _singing_voice(base: Voice, tone: int | None) -> Voice:
    """`base`, retuned to `tone` and stripped of speech intonation.

    A spoken voice declines in pitch across a phrase and stresses on accent.
    Both fight a written melody, so the contour parameters go to zero and the
    voice's own pitch becomes the note.
    """
    voice = dict(base)
    voice.update(baselineFall=0, intonation=0, pitchRange=0, assertiveness=0)
    if tone is not None:
        voice["pitch"] = _midi_to_hz(tone_to_midi(tone))
    return voice


def _midi_to_hz(midi: int) -> int:
    return max(1, round(440.0 * 2.0 ** ((midi - 69) / 12.0)))


#: leave this much of full scale unused, so a sung note does not clip
_HEADROOM = 0.92


def scale_to_headroom(pcm: bytes, headroom: float = _HEADROOM) -> bytes:
    """Scale `pcm` so its loudest sample sits at `headroom` of full scale.

    Each note is synthesized on its own, at the voice's own gain, so a melody
    reaches full scale wherever two loud vowels meet. Attenuating once, at the
    end, keeps the relative dynamics the score wrote.
    """
    if not pcm:
        return pcm
    samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)
    peak = max(abs(v) for v in samples)
    limit = int(32767 * headroom)
    if peak <= limit or peak == 0:
        return pcm
    gain = limit / peak
    return struct.pack(f"<{len(samples)}h", *(int(v * gain) for v in samples))


def _upsample_2x(pcm: bytes) -> bytes:
    """Double a 16-bit PCM stream's rate by linear interpolation.

    A sample is emitted, then the midpoint to the next, matching how the
    MacinTalk synthesizer doubles its own 11025 Hz core to 22050 Hz.
    """
    if len(pcm) < 2:
        return pcm
    samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)
    doubled: list[int] = []
    for current, following in zip(samples, samples[1:], strict=False):
        doubled.append(current)
        doubled.append((current + following) // 2)
    doubled.append(samples[-1])
    doubled.append(samples[-1])
    return struct.pack(f"<{len(doubled)}h", *doubled)


def pcm_duration(pcm: bytes) -> float:
    """Length of a PCM buffer in seconds."""
    return len(pcm) / 2 / SamplingRate


def pcm_peak(pcm: bytes) -> int:
    """Largest absolute sample, for checking a render is not silence."""
    if not pcm:
        return 0
    return max(abs(v) for v in struct.unpack(f"<{len(pcm) // 2}h", pcm))


# Imported at the end so `pyretrotts.sam.engine` can subclass `Engine` above
# without a circular import. SAM is a separate, differently-licensed engine;
# see NOTICE.
from .sam.engine import SAMEngine  # noqa: E402
