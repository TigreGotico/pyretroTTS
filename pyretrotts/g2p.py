"""Grapheme to phoneme: turn written English into the sounds an engine will say.

Each engine already contains a complete G2P front end, because each has to know
how to pronounce a word before it can synthesize one. This module exposes those
front ends on their own, so they can be used without producing any audio.

    from pyretrotts.g2p import phonemize

    phonemize("hello, this is a test.")
    phonemize("photograph", engine="dectalk")
    phonemize("photograph", engine="sam")

The three front ends do not agree, and they are not meant to. Each is the
engine's own, ported from its own source: MacinTalk reads a 7,173-word
dictionary, then a suffix-stripping morphology pass, then letter-to-sound rules;
DECtalk runs its own letter-to-sound rules and inflectional morphology; SAM's
reciter is a single rule engine with no dictionary at all.

    >>> phonemize("photograph")
    ['f', 'OW', 'DX', 'AX', 'g', 'r', 'AE', 'f']
    >>> phonemize("photograph", engine="dectalk")
    ['f', 'ow', 't', 'ax', 'g', 'r', 'ae', 'f']
    >>> phonemize("photograph", engine="sam")
    ['F', 'AA', 'T', 'AA', 'G', 'R', 'AE', 'F']

They disagree about the vowels and the notation. MacinTalk has the word in its
dictionary and flaps the `t`; DECtalk sounds it out with its own rules; SAM does
too, letter by letter, and gets `AA` twice.

DECtalk's dictionary is not distributed with this package, so its front end here
pronounces every word from rules and morphology. Install a DECtalk dictionary to
give it dictionary lookups.
"""
from __future__ import annotations

from dataclasses import dataclass

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

# MacinTalk phoneme id -> the mnemonic its dialect writes it with
_MACINTALK: dict[int, str] = {}
for (_a, _b), _p in MAGIC_MAP.items():
    _MACINTALK.setdefault(_p, _a + (_b or ""))

# DECtalk's own control symbols (stress, boundaries, clause terminators), by the
# raw code value the front end emits. `phonemize(..., markers=True)` keeps these.
_DECTALK_CONTROL: dict[int, str] = {
    101: "s3", 102: "s2", 103: "s1", 104: "semph",
    108: "sbound", 109: "mbound", 110: "hyphen", 111: "wbound",
    112: "ppstart", 113: "vpstart", 114: "relstart",
    115: "comma", 116: "period", 117: "quest", 118: "exclaim",
}


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


def _dectalk_names(codes: list[int], markers: bool) -> list[str]:
    """DECtalk send codes -> mnemonics. Sounds are lowercase ARPABET; the stress
    and boundary symbols come through only with `markers`."""
    from .dectalk.lts import SIL, US_PHONEME_NAMES, arpa_name

    out: list[str] = []
    for code in codes:
        value = code & 0x00FF
        if value in US_PHONEME_NAMES and value != SIL:
            out.append(arpa_name(code))
        elif markers and value in _DECTALK_CONTROL:
            out.append(_DECTALK_CONTROL[value])
    return out


def _dectalk_phonemes(text: str, markers: bool) -> list[str]:
    """DECtalk's front end over whole text: numbers and punctuation expand, and
    each clause is framed as the synthesizer would receive it."""
    from .dectalk.sentence_us import sentence_to_clauses

    out: list[str] = []
    for clause in sentence_to_clauses(text, _dectalk_dictionary()):
        out.extend(_dectalk_names(list(clause.symbols), markers))
    return out


def _dectalk_dictionary():
    """The DECtalk dictionary to consult, or None to pronounce from rules. The
    dictionary is not distributed with this package."""
    return None


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
        return _dectalk_phonemes(text, markers)
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

    out: list[Pronunciation] = []
    for word, _punct in scan_tokens(text).tokens:
        if engine == "sam":
            out.append(Pronunciation(word, _sam_phonemes(word), from_dictionary=False))
        elif engine == "dectalk":
            out.append(_dectalk_word(word))
        else:
            from ._lexicon import lookup
            out.append(Pronunciation(
                word,
                _macintalk_phonemes(word, _MACINTALK, markers=False),
                from_dictionary=lookup(word) is not None,
            ))
    return out


def _dectalk_word(word: str) -> Pronunciation:
    """One word through DECtalk's front end: dictionary if installed, else the
    rules and inflectional morphology."""
    from .dectalk.text_us import word_to_codes

    codes, source = word_to_codes(word, _dectalk_dictionary())
    return Pronunciation(
        word,
        _dectalk_names(codes, markers=False),
        from_dictionary=source == "dict",
    )
