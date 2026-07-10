"""Classic formant speech synthesis: MacinTalk and DECtalk.

    from pyretrotts import MacInTalkEngine, DECtalkEngine, SAMEngine

    MacInTalkEngine().say("hello, this is a test.", "out.wav")
    DECtalkEngine().sing("[:phone on] hxeh<200,13>lb<100>ow<400,20>", "hi.wav")
    SAMEngine().say("i am sam.", "sam.wav", "Little Robot")

The lower-level API works one voice at a time:

    from pyretrotts import synthesize_text, pcm_to_wav
    from pyretrotts._data import Fred_Voice

    pcm_to_wav(synthesize_text(Fred_Voice, "hello."), "out.wav")
"""
from .api import (
    PhonemePlan,
    build_phoneme_plan,
    new_voice,
    pcm_to_wav,
    synthesize_phonemes,
    synthesize_plan,
    synthesize_text,
)
from .engines import DECtalkEngine, Engine, MacInTalkEngine, SAMEngine
from .g2p import phonemize, phonemize_words
from .version import __version__

__all__ = [
    "DECtalkEngine",
    "Engine",
    "MacInTalkEngine",
    "PhonemePlan",
    "SAMEngine",
    "__version__",
    "build_phoneme_plan",
    "new_voice",
    "phonemize",
    "phonemize_words",
    "pcm_to_wav",
    "synthesize_phonemes",
    "synthesize_plan",
    "synthesize_text",
]
