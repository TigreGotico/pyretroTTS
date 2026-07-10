"""Grapheme to phoneme: turn written English into the sounds an engine will say.

Each engine already contains a complete G2P front end, because each has to know
how to pronounce a word before it can synthesize one. This module exposes those
front ends on their own, so they can be used without producing any audio.

    from pyretrotts.g2p import phonemize

    phonemize("hello, this is a test.")
    phonemize("photograph", engine="sam")

The three front ends do not agree, and they are not meant to. MacinTalk and
DECtalk share one: a 15,000-word pronunciation dictionary, a suffix-stripping
morphology pass, and a set of letter-to-sound rules for whatever is left. SAM's
reciter is a single rule engine with no dictionary at all, which is why it is
smaller, faster, and wronger.

    >>> phonemize("photograph")
    ['f', 'OW', 'DX', 'AX', 'g', 'r', 'AE', 'f']
    >>> phonemize("photograph", engine="sam")
    ['F', 'AA', 'T', 'AA', 'G', 'R', 'AE', 'F']

They disagree about both vowels. MacinTalk has the word in its dictionary and
flaps the `t`; SAM sounds it out letter by letter and gets `AA` twice.
"""
from __future__ import annotations

from dataclasses import dataclass

from ._dectalk import PHONEMES as _DECTALK_MNEMONICS
from ._frontend import scan_tokens, words_to_phonemes
from ._phonemes import PHONEME_NAMES_BY_INDEX, kNumPhoneme
from ._rawphon import MAGIC_MAP

__all__ = ["phonemize", "phonemize_words", "Pronunciation", "ENGINES", "phoneme_names"]

#: engine name -> the notation its phonemes are written in
ENGINES = {
    "macintalk": "MacinTalk mnemonics (`IY`, `p`, `AA`)",
    "dectalk": "DECtalk mnemonics (`iy`, `p`, `aa`)",
    "sam": "SAM mnemonics (`IY`, `P`, `AA`)",
}

# phoneme id -> the mnemonic each dialect writes it with
_MACINTALK: dict[int, str] = {}
for (_a, _b), _p in MAGIC_MAP.items():
    _MACINTALK.setdefault(_p, _a + (_b or ""))

_DECTALK: dict[int, str] = {}
for _m, _p in _DECTALK_MNEMONICS.items():
    _DECTALK.setdefault(_p, _m)


@dataclass(frozen=True)
class Pronunciation:
    """One word and the phonemes an engine would say it with."""

    word: str
    phonemes: list[str]
    #: True when the engine knew the word, False when it sounded it out
    from_dictionary: bool = False

    def __str__(self) -> str:
        return f"{self.word}: {' '.join(self.phonemes)}"


def phoneme_names() -> dict[int, str]:
    """Every phoneme id the MacinTalk engine knows, and its name."""
    return dict(PHONEME_NAMES_BY_INDEX)


def _macintalk_phonemes(text: str, table: dict[int, str], markers: bool) -> list[str]:
    """`words_to_phonemes` emits an opcode stream. Ids below `kNumPhoneme` are
    speech sounds; above it sit word boundaries, stress marks and punctuation."""
    out = []
    for phon in words_to_phonemes(text):
        if not markers and phon >= kNumPhoneme:
            continue
        mnemonic = table.get(phon)
        if mnemonic is not None:
            out.append(mnemonic)
    return out


def _sam_phonemes(text: str, phonetic: bool = False) -> list[str]:
    """SAM's reciter turns text into phoneme mnemonics; parser1 turns those
    mnemonics into the phoneme indices the synthesizer speaks."""
    from .sam import prosody, reciter
    from .sam.phonemes import END, mnemonic

    upper = text.upper().encode("latin-1", "replace")
    encoded = upper + b"\x9b" if phonetic else reciter.text_to_phonemes(upper)
    if encoded is None:
        return []

    state = prosody.Buffers(encoded[:254])
    state.phonemeindex[255] = 32
    if not prosody.parser1(state):
        return []

    out: list[str] = []
    for index in state.phonemeindex:
        if index == END:
            break
        name = mnemonic(index).strip()
        if name and name not in ("*", ".", "?", ",", "-"):
            out.append(name)
    return out


def phonemize(text: str, engine: str = "macintalk", markers: bool = False) -> list[str]:
    """The phonemes `engine` would say `text` with, as its own mnemonics.

    With `markers`, MacinTalk and DECtalk also emit the word-boundary and
    stress opcodes their engines carry alongside the sounds. SAM has none.
    Use `phonemize_words` to keep the words apart.
    """
    engine = engine.lower()
    if engine == "macintalk":
        return _macintalk_phonemes(text, _MACINTALK, markers)
    if engine == "dectalk":
        return _macintalk_phonemes(text, _DECTALK, markers)
    if engine == "sam":
        return _sam_phonemes(text)
    raise ValueError(f"unknown engine {engine!r}; expected one of {sorted(ENGINES)}")


def phonemize_words(text: str, engine: str = "macintalk") -> list[Pronunciation]:
    """`text` word by word, each with its own phonemes.

    `from_dictionary` says whether the engine recognized the word or fell back
    to sounding it out. SAM has no dictionary, so it is always False there.
    """
    engine = engine.lower()
    if engine not in ENGINES:
        raise ValueError(f"unknown engine {engine!r}; expected one of {sorted(ENGINES)}")

    from ._lexicon import lookup

    out: list[Pronunciation] = []
    for word, _punct in scan_tokens(text).tokens:
        if engine == "sam":
            out.append(Pronunciation(word, _sam_phonemes(word), from_dictionary=False))
        else:
            table = _MACINTALK if engine == "macintalk" else _DECTALK
            out.append(Pronunciation(
                word,
                _macintalk_phonemes(word, table, markers=False),
                from_dictionary=lookup(word) is not None,
            ))
    return out
