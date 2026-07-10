"""DECtalk formant speech synthesis.

    from pylintalker import synthesize_text, pcm_to_wav
    from pylintalker._data import Fred_Voice

    pcm_to_wav(synthesize_text(Fred_Voice, "hello, this is a test."), "out.wav")
"""
from .api import (
    build_phoneme_plan,
    new_voice,
    pcm_to_wav,
    synthesize_phonemes,
    synthesize_text,
)
from .version import __version__

__all__ = [
    "__version__",
    "build_phoneme_plan",
    "new_voice",
    "pcm_to_wav",
    "synthesize_phonemes",
    "synthesize_text",
]
